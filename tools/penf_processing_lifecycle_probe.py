#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Connected native processing lifecycle; explicit hardware and OS boundaries.

Imports prior pinned probes unchanged. No camera or installable firmware output.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import struct
import sys
from penf_processing_dispatch_probe import DispatchExecution, Fixture, search_bit
from penf_processing_job_probe import (setup, populate, construct, conversion, word,
    invoke, returned, BASE, CALLER, ENGINE, CHECKPOINT_SHA, DEFAULT_IMAGE,
    DEFAULT_OBJDUMP, sha, window)


class Lifecycle(DispatchExecution):
    hooks=DispatchExecution.hooks | {0x6003952f,0x600690e9,0x60030c1d}

    def __init__(self,h):
        super().__init__(h)
        self.in_irq=False
        self.flags={}

    def handle(self):
        s=self.s;pc=s.regs['pc'];ret=s.regs['mdr']
        if pc==0x60039214 and ret==0x604a65cc:
            assert not self.in_irq
            self.events.append(dict(operation='regular completion cleanup context',entry=hex(pc),caller_return=hex(ret)))
            s.return_from_model(0);return
        if pc==0x60030c1d:
            assert not self.in_irq and ret==0x604bedb7
            flag,mask=s.regs['d0'],s.regs['d1']
            assert flag==219 and mask==0x7fffffff
            self.flags[flag]=self.flags.get(flag,0)&mask
            self.events.append(dict(operation='modeled OS flag clear',flag=flag,mask=hex(mask)))
            s.return_from_model(0);return
        if pc==0x60039214 and ret==0x604bec04:
            assert self.in_irq
            self.events.append(dict(operation='explicit interrupt context',entry=hex(pc),caller_return=hex(ret)))
            s.return_from_model(1);return
        if pc==0x600690e9:
            assert self.in_irq and ret==0x604bec1e
            flag,bits=s.regs['d0'],s.regs['d1']
            assert flag==219 and bits==0x80000000
            self.flags[flag]=self.flags.get(flag,0)|bits
            self.events.append(dict(operation='modeled OS flag set from native IRQ callback',flag=flag,bits=hex(bits)))
            s.return_from_model(0);return
        return super().handle()


def make_job(f,fill=0xa5,profile=1,configure=None):
    h,_,prep=setup(f,profile,fill);s=h.s;e=Lifecycle(h)
    if configure is not None: configure(h,e)
    # The connected path allocates more than the earlier short fixture. Keep
    # checkpoint-owned heap entries reserved, particularly the captured task
    # object at61246700; an all-free heap would overlap that live fixture.
    reserved=f.read(0x61c556b4,16)
    assert reserved==bytes.fromhex('92000000000000000000000000000000')
    s.write(0xa1c556b4,reserved)
    prep['checkpoint_reserved_heap_bitmap']=reserved.hex()
    i,a,alloc=h.allocate();pop=populate(h,i,a)
    job,ctor=construct(h,e,i,a,1)
    ctor['tail24_after_constructor']=s.read(job+14920,24).hex()
    converted=conversion(h,e,job,i,h.values())
    maps=[]
    for ptr in struct.unpack_from('<3I',f.image,0x606268a4-BASE):
        data=f.read(ptr,4);assert data==bytes(4)
        s.ram('captured_stage_bitmap_'+hex(ptr),ptr,data)
        maps.append(dict(address=hex(ptr),value=data.hex()))
    s.ram('native_processing_id_bitmaps',0xa1c61e1c,bytes([fill])*32)
    ids=invoke(s,0x604bcf01,0x80,4);returned(s,ids)
    cache_base=struct.unpack_from('<I',f.image,0x606312c8-BASE)[0]
    cache_count=f.image[0x606312d4-BASE];assert cache_count==2
    cache=f.read(cache_base,cache_count*8408);assert cache==bytes(cache_count*8408)
    s.ram('captured_cpu0_two_stage_cache_rows',cache_base,cache)
    s.ram('native_processing_hardware_reference_bytes',0x8ff00198,bytes([fill])*12,aliases=False)
    refs=invoke(s,0x604b31b9,0,4);returned(s,refs)
    s.write(job+14920,bytes(range(24)))
    return h,e,job,dict(preparation=prep,allocation=alloc,population=pop,
        constructor=ctor,conversion=converted,ids=ids,hardware_reference_init=refs,maps=maps)


def map_hardware(s):
    # Initial hardware readback only for the reviewed control bank. Clock and
    # coefficient/LUT ranges are write captures, not permissive device RAM.
    for name,base,size,readable in [
        ('clock_requests',0x988000d4,8,False),
        ('clock_releases',0x988000e0,8,False),
        ('engine_control',0x9e000000,0x200,True),
        ('input_configuration',0x9e000200,0x200,False),
        ('router0',0x9e000400,0x200,False),
        ('router1',0x9e004400,0x200,False),
        ('coeff0',0x9e001800,0x500,False),
        ('coeff1',0x9e005800,0x500,False),
        ('aux_coeff0',0x9e00142c,320,False),
        ('aux_coeff1',0x9e00542c,320,False),
        ('pipeline_configuration0',0x9e003800,0x400,False),
        ('secondary_pipeline0',0x9e009c00,0x400,False),
        ('pipeline_start0',0x9e014000,16,False),
        ('lut0',0x9e00a400,0x2800,False),
        ('lut1',0x9e00cc00,0x2800,False),
    ]:
        s.ram(name,base,bytes(size),aliases=False)
        if not readable:
            s.regions=[replace(r,permissions='w') if r.name==name else r for r in s.regions]
    s.ram('explicit_empty_lut_cache_ids',0xa1c61df8,bytes(8))



def map_job_slots(h):
    s,f=h.s,h.f
    s.ram('captured_cpu0_hardware_job_slots',0x618a3c24,f.read(0x618a3c24,8*44))
    s.ram('captured_irq_shadow',0xa1bf33cc,f.read(0x61bf33cc,488))
    s.ram('irq_controller_write_capture',0x99200000,bytes(488),aliases=False)
    s.regions=[replace(r,permissions='w') if r.name=='irq_controller_write_capture' else r for r in s.regions]
    # Only these two secondary status/configuration registers are read by IRQ98.
    # Split the prior output-only range; do not grant reads to the entire bank.
    old=next(r for r in s.regions if r.name=='secondary_pipeline0')
    s.regions.remove(old)
    for suffix,offset,size,permission in [('before',0,32,'w'),('status',32,8,'rw'),('after',40,984,'w')]:
        s.regions.append(replace(old,name=old.name+'_'+suffix,address=old.address+offset,
                                 data=old.data[offset:offset+size],permissions=permission))


def owned_state(s,job):
    return {hex(p):s.read(p,n).hex() for p,n in [(0x618a3c24,44),(0x618a3d84,4),
        (0xa1c61e1c,32),(0x8ff00198,12),(job+14076,52),(job+14920,24),
        (0xa1c556b4,16),(0xa1c5569c,24)]}


def irq(e,status,mask,secondary):
    s=e.s
    # Explicit external device status; masks ordinarily come from native start.
    # The mask=0 case is an intentional negative control.
    s.write(0x9e000068,bytes(4));s.write(0x9e000070,struct.pack('<I',status))
    s.write(0x9e000078,bytes(4));s.write(0x9e00007c,struct.pack('<I',mask))
    s.write(0x9e009c24,struct.pack('<I',secondary))
    e.in_irq=True
    r=e.call(0x604bd30c,0,0);returned(s,r['execution'])
    e.in_irq=False
    return dict(status=hex(status),mask=hex(mask),secondary_status=secondary,execution=r,
                pending_flags={str(k):hex(v) for k,v in e.flags.items()})


def lifecycle(f,fill,profile):
    h,e,j,prep=make_job(f,fill,profile);s=h.s;map_hardware(s);map_job_slots(h)
    values=h.values();held=s.read(j+36,6032);trailer=s.read(j+14920,24)
    submitted=e.call(0x604c2447,0xf0,32,dict(d0=j,d1=0xffff))
    returned(s,submitted['execution']);assert s.regs['d0']==0
    assert word(s,0x618a3c24+4)==0x604c4011 and word(s,0x618a3c24+8)==j+14076
    assert word(s,0x618a3c24+12)==0x80003019
    assert s.read(0x99200000+98*4,4)==s.read(0xa1bf33cc+98*4,4)
    assert struct.unpack('<12b',s.read(j+12228+1076,12))==values
    output=word(s,j+13360)
    coeff=s.read(0x9e001800+0x2d8,292)
    assert coeff==s.read(output+0x2a4,292)
    retained=owned_state(s,j)
    waiting=e.call(0x604c2732,0xb0,16,dict(d0=j),stops=(0x6003952f,))
    assert s.regs['pc']==0x6003952f and s.regs['mdr']==0x604bed05
    assert (s.regs['d0'],s.regs['d1'],s.regs['a1'])==(219,0x80000000,1)
    saved=dict(s.regs);stack=s.read(0x18010000,0x10000)
    # While jobA waits, use the registered settings route and native capture
    # population/conversion to prepare B. This is an explicit host schedule.
    switch=h.edit(910,53+(profile%3+1));new=h.values();assert new!=values
    ib,ab,alloc=h.allocate();pop=populate(h,ib,ab)
    jb,ctor=construct(h,e,ib,ab,2);conv=conversion(h,e,jb,ib,new)
    held_b=s.read(jb+36,6032)
    assert s.read(j+36,6032)==held and s.read(j+14920,24)==trailer
    controls=[]
    for name,status,mask,secondary in [('no_status',0,256,1),('masked',256,0,1),('secondary_not_done',256,256,0)]:
        before=owned_state(s,j);r=irq(e,status,mask,secondary)
        assert not e.flags and owned_state(s,j)==before
        controls.append(dict(name=name,**r,no_notification=True,all_ownership_preserved=True))
    before_irq=owned_state(s,j)
    completion=irq(e,256,256,1)
    assert e.flags=={219:0x80000000}
    assert s.read(j+36,6032)==held and s.read(jb+36,6032)==held_b
    after_irq=owned_state(s,j)
    # IRQ only signals; it has not dropped the stage token, hardware ref or heap.
    assert after_irq==before_irq and word(s,0x618a3c24)!=0
    assert s.read(0x8ff00198,1)==b'\x01'
    s.write(0x18010000,stack);s.regs=saved
    s.write(saved['a0'],struct.pack('<I',e.flags[saved['d0']]))
    s.return_from_model(0)
    cleanup=e.run({CALLER+7,0x6003952f});returned(s,cleanup['execution'])
    assert s.regs['d0']==0 and e.flags=={219:0}
    assert word(s,0x618a3c24)==0 and s.read(0x8ff00198,12)==bytes(12)
    assert s.read(0xa1c61e1c,32)==bytes(32) and s.read(0x618a3d84,4)==bytes(4)
    assert s.read(j+14076,52)==bytes(52) and s.read(j+14920,24)==trailer
    assert s.read(j+36,6032)==held and s.read(jb+36,6032)==held_b
    cleaned=owned_state(s,j)
    freed=e.call(0x604c2082,0xa0,12,dict(d0=j));returned(s,freed['execution'])
    assert s.read(jb+36,6032)==held_b
    other=e.call(0x604c2082,0xa0,12,dict(d0=jb));returned(s,other['execution'])
    assert s.read(0xa1c556b4,16)==f.read(0x61c556b4,16) and s.read(0xa1c5569c,24)==bytes(24)
    # Capture release/reuse and two-job coefficient isolation are independently
    # covered by job-final. Here prove that actual stage reservations can be
    # acquired again after a real callback/cleanup; retain the new job for reuse.
    jc,cc=construct(h,e,ib,ab,3);vc=conversion(h,e,jc,ib,new)
    again=e.call(0x604c2447,0xf0,32,dict(d0=jc,d1=0xffff));returned(s,again['execution'])
    assert s.regs['d0']==0 and word(s,0x618a3c24+8)==jc+14076
    assert struct.unpack('<12b',s.read(jc+12228+1076,12))==new
    return dict(profile=profile,fill=hex(fill),preparation=prep,submission=submitted,
        old_saturation=values,new_saturation=new,coefficient_sha256=sha(coeff),
        native_slot=0,native_irq=98,callback=['0x604c4011',hex(j+14076)],
        retained_state=retained,wait=waiting,wait_registers=saved,profile_switch=switch,
        second_job=dict(allocation=alloc,population=pop,constructor=ctor,conversion=conv),
        negative_irq_controls=controls,completion_irq=completion,state_after_irq=after_irq,
        cleanup=cleanup,state_after_cleanup=cleaned,destructors=[freed,other],
        reservation_reuse=dict(constructor=cc,conversion=vc,submission=again),
        original_parameters_survive_pending_profile_switch=True,
        callback_signals_before_cleanup=True,cleanup_releases_native_tokens=True,
        destructor_preserves_second_job=True,trailer_survives_to_destructor=True)


WINDOWS={
    'worker-submit-then-finish':(0x60518d86,0x60518e2b),
    'submit-slot-and-start':(0x604b3eb0,0x604b4030),
    'actual-start-mask':(0x604b473e,0x604b488a),
    'irq98-registration':(0x604bd030,0x604bd089),
    'irq98-completion':(0x604bd30c,0x604bd3be),
    'real-job-callback':(0x604c4011,0x604c41a0),
    'wait-signal-clear':(0x604bebfb,0x604bee12),
    'stage-cleanup':(0x604c2c28,0x604c2ceb),
}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    f=Fixture();cases=[]
    for fill in (0,0xa5):
        for profile in (1,2,3):
            cases.append(lifecycle(f,fill,profile));print(f'profile {profile}, fill {fill:02x}: completed',flush=True)
    sources={Path(__file__).resolve()};root=Path.cwd()
    for module in list(sys.modules.values()):
        file=getattr(module,'__file__',None)
        if file and Path(file).resolve().is_relative_to(root/'tools'):sources.add(Path(file).resolve())
    report=dict(main_sha256=sha(f.image),checkpoint_sha256=CHECKPOINT_SHA,
        engine_sha256=sha(ENGINE.read_bytes()),source_sha256={str(x.relative_to(root)):sha(x.read_bytes()) for x in sorted(sources)},
        cases=cases,limits=[
            'Native launch and finish execute in the same order as worker60518d86; outer worker logging/mailbox wrapper is not replayed.',
            'No pixel processing, interrupt-controller delivery or real RTOS scheduler. External hardware status and OS flag semantics are explicit models.',
            'Only native selected bank0 mask80003019 is tested; other imaging paths are not covered.',
            'The final re-submitted job deliberately remains pending at the observation boundary.',
            '24-byte canary is an observed candidate, not a deployed storage extension; scoped BSCH correction remains active.'])
    (args.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    for name,(lo,hi) in WINDOWS.items():(args.out/(name+'.asm')).write_text(window(f.image,DEFAULT_IMAGE,DEFAULT_OBJDUMP,lo,hi))


if __name__=='__main__':main()
