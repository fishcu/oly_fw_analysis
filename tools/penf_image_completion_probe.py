#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native image-resource ownership and completion continuations.

Offline only. Shared fixtures are imported unchanged; only reviewed OS and
hardware exclusion calls are modeled. Unknown instructions/accesses stop.
"""
import argparse
import json
from pathlib import Path
import struct
import sys

from penf_image_ownership_probe import (
    Harness, Fixture, word, invoke, returned, resume, at, BASE, CALLER,
    CHECKPOINT_SHA, DEFAULT_IMAGE, DEFAULT_OBJDUMP, ENGINE, sha, window,
)
from penf_compact_ownership_probe import prepare, refresh, select, half, RING, INDICES, SNAPSHOT

SP = 0x18018000
OPERATION = 0x2a000000
EVENT_CONTEXT = 0xa1c701b4
EVENT_QUEUE = 0xa1c6e36c


class Execution:
    """Uncontended exclusions at two distinct, reviewed native wrappers."""
    callbacks = {0x60557305, 0x6055726d, 0x60557293}
    hooks = callbacks | {0x60039214, 0x600316cb, 0x600317b3, 0x60086c0b,
                         0x60086c54, 0x60070bc0, 0x60070cb1}
    families = {
        'pool': (0x6054a4ee, 0x6054a4fb, 0x6054a50d, 0x6054a51e,
                 0x6054a533, 0x6054a53b, 0x6054a547, 0, 0x111b0011, 0x111b0011),
        'slot': (0x605562af, 0x605562bd, 0x605562d4, 0x605562e6,
                 0x605562f7, 0x60556300, 0x6055630d, 2, 0x121a0012, 18),
    }

    def __init__(self, h):
        self.h, self.s = h, h.s
        self.phase, self.family, self.events = 0, None, []

    def handle(self):
        s = self.s; pc, ret, arg = s.regs['pc'], s.regs['mdr'], s.regs['d0']
        if pc in self.callbacks:
            assert self.family == 'slot' and self.phase == 4
            self.events.append(dict(operation='native protected store', callback=hex(pc),
                                    index=arg, value=s.regs['d1']))
            r = s.run(self.hooks-{pc}, limit=1)
            assert r['status'] == 'instruction_limit'
            return
        if pc == 0x60039214:
            assert self.phase == 0
            matches = [name for name, row in self.families.items() if ret == row[0]]
            assert len(matches) == 1, (hex(pc), hex(ret))
            self.family = matches[0]
        row = self.families[self.family]
        pcs = (0x60039214, 0x600316cb, 0x60086c0b, 0x60070bc0,
               0x60070cb1, 0x60086c54, 0x600317b3)
        names = ('task context', 'dispatch disable', 'interrupt save', 'hardware acquire',
                 'hardware release', 'interrupt restore', 'dispatch enable')
        assert (pc, ret) == (pcs[self.phase], row[self.phase]), (hex(pc), hex(ret), self.phase)
        result = 0
        if self.phase == 2:
            assert arg == row[7]; result = 0x2400
        elif self.phase == 3:
            assert (arg, s.regs['d1']) == (row[8], 255); result = row[8] & 0xffff
        elif self.phase == 4:
            assert arg == row[9]
        elif self.phase == 5:
            assert arg == 0x2400
        self.events.append(dict(family=self.family, operation=names[self.phase], entry=hex(pc),
                                caller_return=hex(ret), argument=hex(arg), result=hex(result)))
        self.phase = (self.phase+1) % 7
        if self.phase == 0: self.family = None
        s.return_from_model(result)

    def run(self, stops, result=None):
        hooks = self.hooks | self.h.exclusion.hooks | set(stops)
        first, start = len(self.events), self.s.steps
        for _ in range(300):
            r = result if result is not None else resume(self.s, hooks)
            result = None
            pc = self.s.regs['pc']
            if r['status'] != 'breakpoint' or pc in stops:
                return dict(execution=r, instructions=self.s.steps-start, models=self.events[first:])
            ret = self.s.regs['mdr']
            regular = ret in (0x60549dd4,0x60549de3,0x60549e11,0x60549e19,
                              0x6053974d,0x60539757)
            if regular:
                self.h.exclusion.handle(self.s)
                self.events.append(dict(operation='existing memory exclusion', **self.h.exclusion.events[-1]))
            else:
                self.handle()
        raise AssertionError('unexpected repeated boundary')

    def call(self, target, mask, frame, regs=None, stops=()):
        r = invoke(self.s, target, mask, frame, regs, stops=self.hooks|self.h.exclusion.hooks|set(stops))
        result = self.run({CALLER+7, *stops}, r)
        result['instructions'] += r['instructions']
        if self.s.regs['pc'] == CALLER+7:
            returned(self.s, result['execution'])
            assert self.phase == 0
            self.h.exclusion.balanced()
        return result

    def block(self, start, stop, regs=None, words=()):
        self.s.regs = dict(pc=start, sp=SP, psw=0, **(regs or {}))
        for offset, value in words:
            self.s.write(SP+offset, struct.pack('<I', value))
        r = self.run({stop}); at(self.s, r['execution'], stop)
        assert self.phase == 0
        return r


def setup(f, fill, profile=1):
    h = Harness(f, profile, fill); h.refresh(profile); preparation = prepare(h)
    h.s.ram('buffer_operation40', OPERATION, bytes(40), aliases=False)
    return h, Execution(h), preparation


def allocate(e):
    s = e.s
    allocation = e.call(0x605488ae, 0xf0, 40, dict(d0=0x700, a0=OPERATION+26))
    handle = half(s, OPERATION+26)
    assert handle >> 8 == 7 and handle & 255
    assert s.regs['d0'] == 0
    return handle, allocation


def release_block(e, handle, hint=4):
    s = e.s
    s.write(OPERATION+10, struct.pack('<H', handle))
    s.write(SP, bytes(128))
    r = e.block(0x60554f30, 0x60554f7c, dict(d3=0),
                ((4, OPERATION), (12, hint)))
    r['remaining_references'] = half(s, SP+54)
    r['handle'] = hex(handle)
    r['hint'] = hint
    assert s.regs['d3'] == 0
    return r


def lifetime(f, profile, fill):
    h, e, preparation = setup(f, fill, profile); s = h.s
    handle, allocation = allocate(e)
    retain = e.call(0x60548a92, 0xf0, 36, dict(d0=handle))
    assert s.regs['d0'] == 0
    set_handle = e.call(0x6055620b, 0, 4, dict(d0=0, d1=handle))
    set_active = e.call(0x6055619b, 0xc0, 12, dict(d0=0, d1=2))
    first_refresh = refresh(h); before = h.values()
    held = s.read(RING, 632)
    snapshot = invoke(s, 0x605553bf, 0, 0); returned(s, snapshot)
    first_release = release_block(e, handle)
    assert first_release['remaining_references'] == 1
    assert s.read(RING, 632) == held
    edit = h.edit(910, 53+(profile % 3+1)); after = h.values()
    assert before != after
    selection = select(s, 1)
    next_active = e.call(0x6055619b, 0xc0, 12, dict(d0=1, d1=2))
    next_refresh = refresh(h)
    assert s.read(RING, 632) == held and s.read(SNAPSHOT, 632) == held
    second_release = release_block(e, handle)
    assert second_release['remaining_references'] == 0
    expected = bytearray(held); expected[24:26] = bytes(2); expected[612:614] = bytes(2)
    assert s.read(RING, 632) == expected
    assert struct.unpack('<12h', s.read(RING+632+382, 24)) == after
    # Reallocation of the real pixel resource and selection of the released
    # ring slot are separate native operations, both now permitted.
    reused_handle, reallocation = allocate(e)
    assert reused_handle == handle
    s.write(INDICES+2, struct.pack('<H', 4))  # explicit selector starting point
    reuse = select(s, 0)
    reuse_handle = e.call(0x6055620b, 0, 4, dict(d0=0, d1=reused_handle))
    reuse_active = e.call(0x6055619b, 0xc0, 12, dict(d0=0, d1=2))
    reuse_refresh = refresh(h)
    assert struct.unpack('<12h', s.read(RING+382, 24)) == after
    assert s.read(SNAPSHOT, 632) == held
    return dict(kind='real_reference_release_and_reuse', profile=profile, fill=hex(fill),
                preparation=preparation, allocation=allocation, retain=retain,
                set_handle=set_handle, state_operations=[set_active, next_active, reuse_active],
                refreshes=[first_refresh, next_refresh, reuse_refresh], snapshot=snapshot,
                old_values=before, new_values=after, edit=edit,
                releases=[first_release, second_release], reallocation=reallocation,
                reused_handle=hex(reused_handle), reuse_handle=reuse_handle,
                selections=[selection, reuse], old_snapshot_sha256=sha(held),
                one_reference_preserves_slot=True, final_reference_frees_matching_slot=True,
                final_release_only_changes_handle_and_state=True, snapshot_survives_reuse=True)


def event_acquisition(f, profile, fill):
    h, e, preparation = setup(f, fill, profile); s = h.s
    s.ram('native_event_context40', EVENT_CONTEXT, bytes([fill])*40)
    s.ram('native_event_init_output', 0x61bcab8e, bytes([fill])*2)
    init = invoke(s, 0x6057595d, 0, 0, dict(a0=EVENT_CONTEXT)); returned(s, init)
    controls = []
    for address in (0xa1c6ffe5, 0xa1c6fc00):
        data = f.read(address ^ 0xc0000000, 1)
        assert data == b'\0'
        s.ram('captured_event_control_'+hex(address), address, data)
        controls.append(dict(address=hex(address), value=data.hex()))
    # Exact declared queue representation: eight halfword entries, sentinel5,
    # byte write/read indices. Enqueue and dequeue below are native.
    s.ram('explicit_empty_event_queue', EVENT_QUEUE, struct.pack('<8HBB', *([5]*8), 0, 0))
    old_state = e.call(0x6055619b, 0xc0, 12, dict(d0=0, d1=2))
    old_refresh = refresh(h); old_values = h.values(); held = s.read(RING, 632)
    selection = select(s, 1)
    pending = e.call(0x6055619b, 0xc0, 12, dict(d0=1, d1=1))
    queued = e.call(0x60558eb8, 0x80, 8, dict(d0=1))
    assert s.regs['d0'] == 0
    edit = h.edit(910, 53+(profile % 3+1)); new_values = h.values()
    assert new_values != old_values
    # Begin at the real worker's successful event-wait return. Supply its
    # 20-byte packet with returned event bit1; no physical interrupt claimed.
    s.write(SP, bytes(64)); s.write(SP+20, struct.pack('<5I', 0, 1023, 1, 1, 0xffffffff))
    delivered = e.block(0x60574cac, 0x605750fd,
                         dict(d0=0, a2=EVENT_CONTEXT, a3=SP+20))
    assert s.regs['d0'] == 17 and s.regs['a1'] == EVENT_CONTEXT
    assert half(s, INDICES+4) == 1 and half(s, RING+632+612) == 2
    assert struct.unpack('<12h', s.read(RING+632+382, 24)) == new_values
    assert s.read(RING, 632) == held
    assert s.read(EVENT_QUEUE, 18) == struct.pack('<8HBB', *([5]*8), 1, 1)
    acquired = s.read(RING+632, 632)
    later_edit = h.edit(910, 53+profile)
    assert h.values() == old_values
    # A repeated capture event for a slot already in state2 is consumed but
    # does not run the state1->2 refresh or dispatch another event17.
    requeued = e.call(0x60558eb8, 0x80, 8, dict(d0=1))
    s.write(SP, bytes(64)); s.write(SP+20, struct.pack('<5I', 0, 1023, 1, 1, 0xffffffff))
    repeated = e.block(0x60574cac, 0x60574c8a,
                        dict(d0=0, a2=EVENT_CONTEXT, a3=SP+20))
    assert s.read(RING+632, 632) == acquired and s.read(RING, 632) == held
    assert s.read(EVENT_QUEUE, 18) == struct.pack('<8HBB', *([5]*8), 2, 2)
    return dict(kind='worker_event_acquisition', profile=profile, fill=hex(fill),
                preparation=preparation, context_initialization=init, captured_controls=controls,
                old_state=old_state, old_refresh=old_refresh, selection=selection,
                pending=pending, enqueue=queued, edit_after_enqueue=edit,
                worker_delivery=delivered, old_values=old_values, acquired_values=new_values,
                later_edit=later_edit, reenqueue=requeued, repeated_event=repeated,
                old_slot_unchanged=True, pending_slot_reads_at_activation=True,
                repeated_active_event_does_not_refresh=True,
                stop='before605750fd state-dependent event17 dispatch, not ISP submission')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True); p.add_argument('--quick', action='store_true')
    args = p.parse_args(); args.out.mkdir(parents=True, exist_ok=False)
    f = Fixture(); cases = []
    for fill in ((0xa5,) if args.quick else (0, 0xa5)):
        for profile in ((1,) if args.quick else (1, 2, 3)):
            cases.append(lifetime(f, profile, fill))
            print(f'COLOR{profile}, fill {fill:#x}: reference-count release and reuse passed', flush=True)
            cases.append(event_acquisition(f, profile, fill))
            print(f'COLOR{profile}, fill {fill:#x}: worker acquisition and repeated-event control passed', flush=True)
    spans = {
        'native-reference-zero-gate': (0x60554f30, 0x60554f7c),
        'pool-critical-section': (0x6054a4b0, 0x6054a54e),
        'slot-critical-section': (0x60556293, 0x6055631a),
        'resource-release-wrapper': (0x6056bfcf, 0x6056c08b),
        'release-type-bookkeeping': (0x6056c31a, 0x6056c380),
        'matching-handle-release': (0x60556899, 0x605569a1),
        'worker-event-delivery': (0x60574c8a, 0x60574d1e),
        'event-context-init-and-handler': (0x6057595d, 0x60575b4f),
        'event-index-enqueue': (0x60558e34, 0x60558ef5),
        'event-index-dequeue': (0x605569ce, 0x60556a12),
        'outer-release-interrupt-scope': (0x60554e3d, 0x60554fac),
        'capture-start-and-end-wrappers': (0x605504ec, 0x605505ae),
        'exposure-callback-release-call': (0x60245d55, 0x60245df0),
    }
    folder = args.out/'disassembly'; folder.mkdir()
    for name, (lo, hi) in spans.items():
        (folder/(name+'.asm')).write_text(window(f.image, DEFAULT_IMAGE, DEFAULT_OBJDUMP, lo, hi))
    root = Path.cwd(); sources = {Path(__file__).resolve()}
    for module in list(sys.modules.values()):
        file = getattr(module, '__file__', None)
        if file and Path(file).resolve().is_relative_to(root/'tools'):
            sources.add(Path(file).resolve())
    report = dict(main_sha256=sha(f.image), checkpoint_sha256=CHECKPOINT_SHA,
        engine_sha256=sha(ENGINE.read_bytes()),
        source_sha256={str(p.relative_to(root)): sha(p.read_bytes()) for p in sorted(sources)},
        spans={k: list(map(hex, v)) for k, v in spans.items()}, cases=cases,
        limits=[
            'Native allocation, retain, release, zero-reference decision and matching-slot notification; no fake resource handles or supplied remaining count.',
            'Uncontended regular-task OS/hardware exclusion modeled at exact reviewed callers, with balanced phases and arguments.',
            'Initial compact states, handle attachment and selector starting point are explicit test operations; complete take-info builder not replayed.',
            'Release continuation begins at60554f30 with supplied outer descriptor and slot hint. Physical completion/event ingress and higher caller timing remain open.',
            'Global632-byte snapshot is independently copied but not claimed permanently owned by an image.',
            'Native event-context initialization, explicit empty queue, native enqueue/dequeue. Event1 is supplied at the worker wait-return boundary; interrupt ingress is not modeled.',
            'Successful pending-slot acquisition stops before state-dependent event17 dispatch; repeated active-slot event returns to worker wait without refresh.',
            'No new H/L transport storage, firmware hook, flashable image or physical-camera validation.',
        ])
    (args.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f'{len(cases)} completion cases passed.', flush=True)


if __name__ == '__main__':
    main()
