#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Bounded capture readiness transports and settings-inhibit scope.

Native packet construction/callbacks/dispatch; explicit in-memory OS transport
models and supplied external-flash state. No scheduler, peripheral or firmware
modification. Unrecognized calls and accesses remain strict stops.
"""
import argparse
import json
from pathlib import Path
import struct
import sys

from penf_capture_transition_probe import setup
from penf_image_ownership_probe import Harness, word
from penf_profile_context_probe import (
    Fixture, invoke, returned, at, resume, current_record, CALLER, CHECKPOINT_SHA,
)
from penf_disasm import BASE, DEFAULT_IMAGE, DEFAULT_OBJDUMP, window, refs
from penf_emulator import ENGINE
from oly_container import sha256

SP = 0x18018000
CALLBACKS = 0x61869614
PACKET = 0x22000000
INHIBIT = 0x6189a4b0


class Transport:
    """Only the reviewed pool/mailbox/event/queue ABI; never infer readiness."""
    hooks = {0x60039214, 0x60033a80, 0x60036a44, 0x6003403a,
             0x60035592, 0x6006906e, 0x60069429, 0x6006932d}

    def __init__(self, s, fill):
        self.s, self.fill = s, fill
        self.mailbox, self.queues, self.events = [], {}, []
        self.blocks, self.freed = [], []

    def handle(self):
        s = self.s
        pc, ret = s.regs['pc'], s.regs['mdr']
        d0, a0 = s.regs['d0'], s.regs.get('a0', 0)
        event = dict(entry=hex(pc), caller_return=hex(ret))
        if pc == 0x60039214:
            assert ret in (0x601ca1f4, 0x601ca314)
            event['operation'] = 'supplied ordinary task context'
        elif pc == 0x60033a80:
            assert ret == 0x601ca210 and d0 == 1
            block = 0x21000000 + 32*len(self.blocks)
            s.ram('modeled_message_pool_'+hex(block), block, bytes([self.fill])*20)
            self.blocks.append(block)
            s.write(a0, struct.pack('<I', block))
            event.update(operation='pool1 allocate', block=hex(block))
        elif pc == 0x60036a44:
            assert ret == 0x601ca25b and d0 == 1 and a0 in self.blocks
            self.mailbox.append(a0)
            event.update(operation='mailbox1 enqueue', block=hex(a0),
                         payload=s.read(a0+8, 12).hex())
        elif pc == 0x6006906e:
            assert ret == 0x601ca32d and (d0, s.regs['d1']) == (78, 1)
            event['operation'] = 'event78 signal1; scheduling not modeled'
        elif pc == 0x6003403a:
            assert ret == 0x601ca2c6 and d0 == 1 and self.mailbox
            block = self.mailbox.pop(0)
            s.write(a0, struct.pack('<I', block))
            event.update(operation='mailbox1 receive', block=hex(block))
        elif pc == 0x60035592:
            assert ret == 0x601ca307 and d0 == 1
            assert a0 in self.blocks and a0 not in self.freed and a0 not in self.mailbox
            self.freed.append(a0)
            # Poison after native copying to establish that dispatch uses its
            # private stack message, not the released pooled allocation.
            s.write(a0+8, bytes([0xdd])*12)
            event.update(operation='pool1 release and payload poison', block=hex(a0))
        elif pc in (0x60069429, 0x6006932d):
            assert s.regs['d1'] == 0xffffffff
            ptr, size = struct.unpack('<2I', s.read(a0, 8))
            queue = self.queues.setdefault(d0, [])
            if pc == 0x60069429:
                assert ret in (0x601ca09b,0x602cf78a) and (d0, size) in ((104,16),(96,16),(109,12))
                if ret == 0x602cf78a:
                    assert (d0,size)==(109,12)
                payload = s.read(ptr, size)
                queue.append(payload)
                event['operation'] = 'queue write'
            else:
                assert ret == 0x601ca149 and (d0, size) == (109,12) and queue
                payload = queue.pop(0)
                assert len(payload) == size
                s.write(ptr, payload)
                event['operation'] = 'queue read'
            event.update(queue=d0, payload=payload.hex())
        else:
            raise AssertionError(hex(pc))
        self.events.append(event)
        s.return_from_model(0)

    def run(self, stops, result=None):
        first = len(self.events)
        for _ in range(100):
            r = result if result is not None else resume(self.s, set(stops)|self.hooks)
            result = None
            assert r['status'] == 'breakpoint', r
            if self.s.regs['pc'] in stops:
                return dict(execution=r, models=self.events[first:])
            self.handle()
        raise AssertionError('unexpected repeated boundary')

    def call(self, target, mask, frame, regs):
        r = invoke(self.s, target, mask, frame, regs, stops=self.hooks)
        result = self.run({CALLER+7}, r)
        returned(self.s, result['execution'])
        return result

    def block(self, start, stops, regs=None, words=()):
        s = self.s
        s.regs = dict(pc=start, sp=SP, psw=0, **(regs or {}))
        for offset, value in words:
            s.write(SP+offset, struct.pack('<I', value))
        return self.run(set(stops))


def external_worker(t, request, state=0, count=0):
    """Actual command gate/dispatch/reply from the post-receive loop boundary.

    State0 skips peripheral execution. State2/count0 must stop at the hardware
    command routine, while a nested request only increments the hold counter.
    These are explicit worker states, not inferred accessory configurations.
    """
    s = t.s
    s.ram('external_flash_diagnostics_off',0x61889304,bytes(4))
    s.ram('external_flash_explicit_state_and_hold',0x6188976c,
          struct.pack('<HHHH',state,count,0,0))
    s.ram('external_flash_status_query',0x6188957c,bytes(2))
    packet_words = struct.unpack('<4I',request)
    r = t.block(0x602cf6df,(0x602cf7ac,0x602d00b9),
                dict(d3=0xffff,d2=0,a2=SP+72,a3=SP+56),
                ((20,SP+40),(36,0),*((40+4*i,x) for i,x in enumerate(packet_words))))
    assert int.from_bytes(s.read(0x6188976e,2),'little')==count+1
    peripheral = state==2 and count==0
    assert s.regs['pc']==(0x602d00b9 if peripheral else 0x602cf7ac)
    if peripheral:
        assert s.regs['d0']==2 and not t.queues.get(109)
    else:
        assert len(t.queues[109])==1
        payload=t.queues[109][0]
        assert struct.unpack_from('<H',payload)[0]==0
        assert struct.unpack_from('<2I',payload,4)==(43,2)
    return dict(state=state,initial_hold_count=count,peripheral_boundary=peripheral,**r)


def transport_case(fill, order, bypass=None):
    s, preparation = setup(fill)
    s.write(SP-1024, bytes([fill])*2048)
    returned(s, invoke(s, 0x602352ab, 0xc0, 28, dict(d0=0x04008000,d1=0)))
    s.ram('native_callback_registration_destination', CALLBACKS, bytes([fill])*12)
    s.ram('explicit_secondary_readiness_selector', 0x6186921d,
          bytes([1 if bypass is None else bypass]))
    t = Transport(s, fill)
    registration = t.block(0x6024a7c6, (0x6024a81d,))
    assert struct.unpack('<3I',s.read(CALLBACKS,12)) == (0x6024b3b8,0x6024b3ca,0x6024b3dc)
    packet = t.queues[104].pop(0)
    assert struct.unpack('<4I', packet) == (109,21,47,CALLBACKS)
    s.ram('native_request_copied_by_transport', PACKET, packet, aliases=False)
    # Start after worker47's peripheral prerequisites. The native helper reads
    # callback0 from the exact registered table and calls it. Hardware work
    # before/after this helper is not silently replaced by success.
    callback = t.call(0x60236588, 0, 4, dict(a0=CALLBACKS))
    assert len(t.mailbox) == 1
    payload = s.read(t.mailbox[0]+8,12)
    assert struct.unpack_from('<H',payload)[0] == 0
    assert struct.unpack_from('<2I',payload,4) == (18,0)
    secondary = t.block(0x6024a8d2, (0x6024a916,), dict(a2=SP+8))
    if bypass is None:
        request43 = t.queues[96].pop(0)
        assert struct.unpack('<4I',request43) == (109,43,2,2)
        reply = external_worker(t,request43)
        assert struct.unpack_from('<H',t.queues[109][0])[0] == 0
        assert struct.unpack_from('<2I',t.queues[109][0],4) == (43,2)
    else:
        assert not t.queues.get(96) and word(s,0x61865834) == 0x04000000
        reply = None
    deliveries = []
    for i, command in enumerate(order):
        start, end = ((0x6023489f,0x60234956) if command == 18
                      else (0x60234ad2,0x60234b95))
        r = t.block(start, (end,0x6024a95b),
                    dict(a3=0x60331fa8,d3=0xffff,a2=0xffff), ((24,SP+40),))
        last = i == len(order)-1
        assert s.regs['pc'] == (0x6024a95b if last else end), r
        assert word(s,0x61865834) == (0 if last else (0x8000 if command==18 else 0x04000000))
        assert s.read(0x61865818,2) == struct.pack('<H',13 if last else 12)
        deliveries.append(dict(command=command, remaining=hex(word(s,0x61865834)), **r))
    assert (s.regs['d0'],s.regs['d1']) == (12,0)
    assert len(t.freed)==1 and not t.mailbox and not t.queues.get(109)
    return dict(kind='native_readiness_transports',fill=hex(fill),order=order,
                selector_bypass=bypass, preparation=preparation,
                registration=registration, callback=callback,
                secondary_request_or_bypass=secondary, external_flash_worker=reply,
                deliveries=deliveries, pooled_message_released_before_dispatch=True,
                limitation='Native callback helper begins after unexecuted worker47 prerequisites; '
                           'external-flash state0/post-receive context and task ordering supplied; '
                           'stop before state13 body')


def external_control(fill,count):
    s,preparation=setup(fill)
    s.write(SP-1024,bytes([fill])*2048)
    t=Transport(s,fill)
    result=external_worker(t,struct.pack('<4I',109,43,2,2),state=2,count=count)
    return dict(kind='external_flash_worker_boundary',fill=hex(fill),
                preparation=preparation,**result)


def inhibit_case(f, profile, fill):
    h = Harness(f,profile,fill)
    s = h.s
    h.refresh(profile)
    initial = h.values()
    index, address, allocation = h.allocate()
    key = 931+12*(profile-1)
    before = current_record(f,s,key)
    requested = 5 if before != 5 else -5
    setter = invoke(s,0x602f0d06,0,0,dict(d0=1))
    returned(s,setter)
    rejected = h.edit(key,requested)
    assert rejected['result']==1 and current_record(f,s,key)==before
    populated = h.populate(index)
    assert s.read(INHIBIT,1)==b'\x01' and h.capture_values(address)==initial
    # The real transaction commit bypasses this public-API inhibit. Test the
    # native internal record writer while the flag stays set, using an existing
    # effective saturation ID, without changing the stored profile array.
    value = 4 if initial[0] != 4 else -4
    raw_write = invoke(s,0x602f02b4,0xe0,20,dict(d0=919,d1=value & 0xffffffff))
    returned(s,raw_write)
    assert current_record(f,s,919)==value and s.read(INHIBIT,1)==b'\x01'
    second, other, allocation2 = h.allocate()
    populated2 = h.populate(second)
    assert h.capture_values(other)==(value,)+initial[1:]
    assert h.capture_values(address)==initial
    clear = invoke(s,0x602f0d06,0,0,dict(d0=0))
    returned(s,clear)
    accepted = h.edit(key,requested)
    assert accepted['result']==0 and current_record(f,s,key)==requested
    assert h.capture_values(address)==initial
    return dict(kind='settings_inhibit_scope',profile=profile,fill=hex(fill),
                allocation=allocation,flag_set=setter,public_edit_rejected=rejected,
                capture_while_inhibited=populated,internal_write=raw_write,
                second_allocation=allocation2,second_capture=populated2,
                flag_clear=clear,public_edit_after_clear=accepted,
                limitation='Forced calls demonstrate API scope, not a real-camera interleaving; '
                           'allocation exclusion remains the prior explicit model')


WINDOWS = {
    'state12-request-and-callbacks':(0x6024a733,0x6024a919),
    'callback-message-senders':(0x6024b3b8,0x6024b3ee),
    'worker104-loop-dispatch':(0x601c9495,0x601c95b8),
    'worker47-and-callbacks':(0x60236283,0x602365bb),
    'queue-wrappers-and-reply':(0x601ca08a,0x601ca16e),
    'mailbox-wrappers':(0x601ca1ec,0x601ca330),
    'task127-input-registration':(0x602347ae,0x60234846),
    'task127-loop':(0x60234846,0x60234bc5),
    'public-settings-inhibit':(0x602b9f33,0x602b9f52),
    'internal-settings-write':(0x602f0298,0x602f02ff),
    'inhibit-byte-get-set':(0x602f0d06,0x602f0d18),
    'external-flash-task-and-reply':(0x602cf50b,0x602cf7c8),
    'external-flash-command-dispatch':(0x602cf7c8,0x602cfaec),
    'external-flash-command-gate':(0x602cef0e,0x602cf10e),
    'external-flash-command-work':(0x602cfda2,0x602d00b9),
}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    args = p.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    cases = [transport_case(fill,order) for fill in (0,0xa5)
             for order in ((18,43),(43,18))]
    cases += [transport_case(fill,(18,),bypass) for fill in (0,0xa5) for bypass in (0,2)]
    cases += [external_control(fill,count) for fill in (0,0xa5) for count in (0,1)]
    f = Fixture()
    cases += [inhibit_case(f,profile,fill) for fill in (0,0xa5) for profile in (1,2,3)]
    out = args.out/'disassembly'
    out.mkdir()
    for name,(lo,hi) in WINDOWS.items():
        (out/(name+'.asm')).write_text(window(f.image,DEFAULT_IMAGE,DEFAULT_OBJDUMP,lo,hi))
    sources = {Path(__file__),ENGINE}
    sources.update(Path(m.__file__) for m in tuple(sys.modules.values())
                   if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==Path('tools').resolve())
    report = dict(cases=cases,main_sha256=sha256(f.image),checkpoint_sha256=CHECKPOINT_SHA,
                  camera_used=False,firmware_modified=False,
                  source_sha256={str(p):sha256(p.read_bytes()) for p in sorted(sources)},
                  windows={k:[hex(a) for a in v] for k,v in WINDOWS.items()},
                  raw_inhibit_reference_candidates={hex(a):[[hex(x) for x in group] for group in refs(f.image,a)]
                                                    for a in (INHIBIT,0x602f0d06,0x602f0d0f)},
                  worker47_table_entry=hex(struct.unpack_from('<I',f.image,0x601ca774+47*4-BASE)[0]))
    assert report['worker47_table_entry']=='0x60236283'
    (args.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'{len(cases)} readiness transport / settings-inhibit cases passed; {args.out}')


if __name__=='__main__':
    main()
