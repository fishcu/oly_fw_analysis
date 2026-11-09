#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native processing-job construction, allocation class and parameter lifetime.

Offline investigation. Extends the reviewed ownership harness without changing
older pinned reproductions. Unknown memory/instructions stop.
"""
import argparse
import json
from pathlib import Path
import struct
import sys

from penf_image_completion_probe import Execution
from penf_capture_conversion_probe import (
    Harness, Fixture, word, invoke, returned, prepare, populate, CAPTURE_BYTES,
    DESCRIPTOR, BASE, CALLER, CHECKPOINT_SHA, DEFAULT_IMAGE, DEFAULT_OBJDUMP,
    ENGINE, sha, window,
)

PARAMS = 0x2c000000
HEAP_BASE, HEAP_STRIDE = 0x6122a540, 0x4040
JOB_BYTES = 14920


class JobExecution(Execution):
    hooks = Execution.hooks | {0x600233f9, 0x60023495, 0x60524033}

    def __init__(self, h):
        super().__init__(h)
        self.heap_phase, self.heap_kind = 0, None
        self.blocks = set()
        self.map_heap_payload = True

    def handle(self):
        s = self.s; pc, ret, arg = s.regs['pc'], s.regs['mdr'], s.regs['d0']
        if pc == 0x60524033:
            assert arg == 0
            address,size=word(s,s.regs['sp']+4),word(s,s.regs['sp']+8)
            assert address == 0xa2f29c00 and size == 32768
            s.ram('native_selected_color_processing_buffer',address,bytes([self.h.fill])*size)
            self.events.append(dict(operation='map native selected COLOR processing buffer',address=hex(address),bytes=size))
            step=s.run(self.hooks-{pc},limit=1)
            assert step['status']=='instruction_limit'
            return
        if pc in (0x600233f9, 0x60023495):
            address = s.regs['a0']
            if address:
                if address >= 0xa1221fc0:
                    base,stride,capacity,size = 0xa1221fc0,192,178,128
                else:
                    base,stride,capacity,size = HEAP_BASE,HEAP_STRIDE,64,16384
                index = (address-base)//stride
                assert address == base+index*stride and 0 <= index < capacity
                if self.map_heap_payload and address not in self.blocks:
                    s.ram('native_job_heap_'+hex(address), address, bytes([self.h.fill])*size)
                    self.blocks.add(address)
                self.events.append(dict(operation='native selected heap block', address=hex(address), slot=index, bytes=size,
                                        payload_mapped=self.map_heap_payload))
            step = s.run(self.hooks-{pc}, limit=1)
            assert step['status'] == 'instruction_limit'
            return
        starts = {0x600235a7:'allocate', 0x600235db:'free'}
        if pc == 0x60086c0b and ret in starts:
            assert self.heap_phase == 0 and self.phase == 0
            self.heap_kind = starts[ret]
        if self.heap_kind is None:
            return super().handle()
        rets = ((0x600235a7,0x600235b8,0x600235c4,0x600235cc) if self.heap_kind=='allocate'
                else (0x600235db,0x600235ec,0x600235f8,0x60023600))
        pcs = (0x60086c0b,0x60070bc0,0x60070cb1,0x60086c54)
        assert (pc, ret) == (pcs[self.heap_phase], rets[self.heap_phase]), (hex(pc),hex(ret))
        expected = (1,0x0a09000a,10,0x2400)
        results = (0x2400,10,0,0)
        assert arg == expected[self.heap_phase]
        if self.heap_phase == 1: assert s.regs['d1'] == 255
        result = results[self.heap_phase]
        self.events.append(dict(operation='reviewed heap exclusion', kind=self.heap_kind,
                                phase=self.heap_phase, entry=hex(pc), caller_return=hex(ret),
                                argument=hex(arg), result=hex(result)))
        self.heap_phase = (self.heap_phase+1) % 4
        if self.heap_phase == 0: self.heap_kind = None
        s.return_from_model(result)


def setup(f, profile, fill):
    h=Harness(f,profile,fill);h.refresh(profile);preparation=prepare(h);s=h.s
    s.ram('explicit_empty_cpu0_large_heap_bitmap',0xa1c556b4,bytes(16))
    s.ram('explicit_empty_uncached_small_heap_bitmap',0xa1c5569c,bytes(24))
    s.ram('explicit_large_heap_cursor',0xa1c554c8,struct.pack('<I',0xffffffff))
    s.ram('job_parameters_and_status',PARAMS,bytes(64),aliases=False)
    s.ram('native_processing_lock_bytes',0x8ff001b0,bytes([fill])*4,aliases=False)
    s.ram('uncontended_processing_atomic_lock',0x8fe00006,bytes(2),aliases=False)
    r=invoke(s,0x604fa059,0x80,4);returned(s,r)
    preparation['processing_lock_initialization']=r
    cache=f.read(0x61c621f8,400)
    assert cache == bytes(400)
    s.ram('captured_four_processing_cache_rows',0xa1c621f8,cache)
    policy=f.read(0x618b510e,2)
    assert policy == bytes(2)
    s.ram('captured_processing_diagnostic_policy',0x618b510e,policy)
    s.ram('explicit_empty_nine_job_metadata_records',0xa1c67cb4,bytes(180))
    e=JobExecution(h)
    return h,e,preparation


def construct(h, e, index, address, logical_id, callback=True):
    s=h.s
    s.write(PARAMS, bytes(64))
    mode=invoke(s,0x60522f23,0x30,8,dict(d1=address,a0=PARAMS+8,a1=PARAMS+9,d0=PARAMS+10))
    returned(s,mode)
    # Constants from the still/recview wrapper. Format+16 is an explicit zero
    # fixture; +18 selects 4:3. Full peripheral descriptor is not supplied.
    s.write(PARAMS+18,b'\x01');s.write(PARAMS+19,b'\x01');s.write(PARAMS+24,b'\x01')
    metadata=invoke(s,0x60525680,0xf0,16,dict(d0=logical_id,a0=0,d1=index,a1=PARAMS+4))
    returned(s,metadata)
    if callback: s.write(PARAMS,struct.pack('<I',0x6051fbcc))
    parameters=s.read(PARAMS,32).hex()
    r=e.call(0x604c1c0a,0xf0,40,dict(a0=PARAMS,a1=PARAMS+40,d0=0))
    returned(s,r['execution']);assert e.heap_phase == 0
    job=s.regs['d0']
    return job,dict(mode=mode,metadata=metadata,parameters_hex=parameters,
                    construction=r,job=hex(job),status=int.from_bytes(s.read(PARAMS+40,2),'little'))


def conversion(h,e,job,index,expected):
    s=h.s;s.write(DESCRIPTOR,bytes(376));s.write(DESCRIPTOR+8,b'\x05')
    access=invoke(s,0x60521f80,0xe0,16,dict(d0=index,a0=DESCRIPTOR+124));returned(s,access)
    capture=word(s,DESCRIPTOR+124);before=s.read(capture,CAPTURE_BYTES)
    r=e.call(0x6052010f,0xf0,48,dict(a0=job+36,a1=DESCRIPTOR,d0=0))
    returned(s,r['execution']);assert s.regs['d0']==0
    assert s.read(capture,CAPTURE_BYTES)==before
    assert struct.unpack('<12b',s.read(job+36+5684,12))==tuple(expected)
    ready=e.call(0x604c20ce,0xf0,104,dict(d0=job))
    returned(s,ready['execution']);assert s.regs['d0']==0
    assert struct.unpack('<12b',s.read(job+36+5684,12))==tuple(expected)
    stages=struct.unpack('<48I',s.read(job+11868,192))
    return dict(accessor=access,converter=r,preparation=ready,
                prepared_stage_records=[list(map(hex,stages[i:i+3])) for i in range(0,48,3)],
                native_callbacks={str(offset):hex(word(s,job+offset)) for offset in (12176,12180,12184)},
                prepared_parameters_sha256=sha(s.read(job+36,6032)))


def coefficients(h,e,job,expected,ordinal):
    # Separate fixtures, not job-relative scratch which could overlap another
    # native heap allocation. Reuse stock packer and selector unchanged.
    s=h.s;request=0x2d000000+ordinal*0x10000;context=request+0x1000;output=request+0x2000
    for name,ptr,size in [('request',request,1132),('context',context,192),('coefficients',output,5632)]:
        s.ram(name+hex(request),ptr,bytes(size),aliases=False)
    p=e.call(0x604c3051,0xf0,28,dict(a0=job,a1=request,d0=0));returned(s,p['execution'])
    assert struct.unpack('<12b',s.read(request+1076,12))==tuple(expected)
    s.write(context+4,struct.pack('<4I',request,0,output,output+5212))
    s.write(context+56,struct.pack('<I',0xffffffff));s.write(context+100,struct.pack('<I',0xffffffff))
    c=e.call(0x604f747f,0xf0,20,dict(a0=context));returned(s,c['execution'])
    pointers=struct.unpack_from('<12I',h.f.image,0x6062fef8-BASE)
    values=[]
    for sector,value in enumerate(expected):
        record=(sector%2)*6+sector//2
        amplitude=struct.unpack_from('<h',h.f.image,0x60622d74+record*28+14-BASE)[0]
        gain=struct.unpack_from('<H',h.f.image,pointers[record]-BASE+2*(value<0))[0]
        n=((amplitude*gain)>>8)*value
        expected_s=(1 if n>=0 else -1)*(abs(n)//5)
        actual=struct.unpack('<3h',s.read(output+0x2a4+record*24+18,6))
        assert actual==(0,expected_s,0)
        values.append(actual)
    return dict(packer=p,selector=c,HSL=values,neutral_HL_stock=True,
                coefficient_sha256=sha(s.read(output+0x2a4,292)))


def lifetime(f,profile,fill):
    h,e,preparation=setup(f,profile,fill);s=h.s
    before=h.values();ia,a,aa=h.allocate();pa=populate(h,ia,a)
    ja,ca=construct(h,e,ia,a,1);assert ja==HEAP_BASE and ca['status']==0
    canary=bytes(range(24));s.write(ja+JOB_BYTES,canary)
    va=conversion(h,e,ja,ia,before);held=s.read(ja+36,6032)
    switch=h.edit(910,53+(profile%3+1));after=h.values();assert before!=after
    ib,b,ab=h.allocate();pb=populate(h,ib,b)
    jb,cb=construct(h,e,ib,b,2);assert jb and jb!=ja and cb['status']==0
    vb=conversion(h,e,jb,ib,after)
    assert s.read(ja+36,6032)==held and s.read(ja+JOB_BYTES,24)==canary
    release=h.release(ia);ic,c,ac=h.allocate();assert (ic,c)==(ia,a)
    pc=populate(h,ic,c);assert h.capture_values(c)==after
    ka=coefficients(h,e,ja,before,0);kb=coefficients(h,e,jb,after,1)
    assert s.read(ja+36,6032)==held and s.read(ja+JOB_BYTES,24)==canary
    first=e.call(0x604c2082,0xa0,12,dict(d0=ja));returned(s,first['execution'])
    assert s.regs['d0']==0 and e.heap_phase==0
    bitmap_after_first=s.read(0xa1c556b4,16).hex()
    kb2=coefficients(h,e,jb,after,2)
    assert kb2['coefficient_sha256']==kb['coefficient_sha256']
    second=e.call(0x604c2082,0xa0,12,dict(d0=jb));returned(s,second['execution'])
    assert s.regs['d0']==0 and e.heap_phase==0
    assert s.read(0xa1c556b4,16)==bytes(16)
    assert s.read(0xa1c5569c,24)==bytes(24)
    # Allocation class comparison is real allocator execution; this does not
    # modify the stock constructor's request or qualify a new struct member.
    sizes=[]
    e.map_heap_payload=False  # class/free tests do not read or write payload
    for size in (14920,14944,16384):
        alloc=e.call(0x600233bd,0,4,dict(d0=size));returned(s,alloc['execution'])
        ptr=s.regs['a0'];assert HEAP_BASE<=ptr<HEAP_BASE+64*HEAP_STRIDE
        freed=e.call(0x600233fc,0,4,dict(a0=ptr));returned(s,freed['execution'])
        assert s.read(0xa1c556b4,16)==bytes(16)
        sizes.append(dict(requested=size,address=hex(ptr),allocate=alloc,free=freed))
    return dict(kind='native_job_lifetime',profile=profile,fill=hex(fill),preparation=preparation,
                capture_allocations=[aa,ab,ac],populations=[pa,pb,pc],constructors=[ca,cb],
                conversions=[va,vb],old_values=before,new_values=after,profile_switch=switch,
                capture_release=release,coefficients=[ka,kb,kb2],job_releases=[first,second],
                heap_bitmap_after_first_release=bitmap_after_first,allocation_sizes=sizes,
                prior_image_keeps_values=True,reused_capture_does_not_change_job=True,
                first_job_free_preserves_second=True,all_heap_allocations_released=True,
                canary_offset=JOB_BYTES,canary_hex=canary.hex(),canary_survives_tested_calls=True,
                canary_is_not_a_qualified_HL_field=True)


def missing_callback(f,fill):
    h,e,preparation=setup(f,1,fill);s=h.s
    i,a,allocation=h.allocate();population=populate(h,i,a)
    job,result=construct(h,e,i,a,1,False)
    assert job==0 and result['status']==40655
    assert s.read(0xa1c556b4,16)==bytes(16)
    return dict(kind='missing_allocation_callback_control',fill=hex(fill),preparation=preparation,
                allocation=allocation,population=population,constructor=result,
                failure_is_fixture_not_camera=True,allocated_jobs_freed=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--quick',action='store_true')
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    f=Fixture();cases=[]
    for fill in ((0xa5,) if args.quick else (0,0xa5)):
        for profile in ((1,) if args.quick else (1,2,3)):
            cases.append(lifetime(f,profile,fill))
            print(f'COLOR{profile}, fill{fill:#x}: real job lifetime passed',flush=True)
        cases.append(missing_callback(f,fill))
        print(f'fill{fill:#x}: missing callback cleanup control passed',flush=True)
    spans={
        'job-constructor':(0x604c1c0a,0x604c2082),
        'job-free':(0x604c2082,0x604c20ce),
        'job-preparation':(0x604c20ce,0x604c2447),
        'native-job-callback':(0x6051fbcc,0x6051fe71),
        'job-metadata-registration':(0x60525680,0x6052573a),
        'native-buffer-allocator':(0x60524000,0x60524055),
        'allocation-classes':(0x600233bd,0x60023498),
        'heap-critical-and-pools':(0x6002359d,0x60023733),
        'job-constructor-wrapper':(0x60524ed0,0x60525079),
        'processing-worker':(0x60518d86,0x60518e80),
        'stage-dispatch':(0x604c2447,0x604c2526),
    }
    folder=args.out/'disassembly';folder.mkdir()
    for name,(lo,hi) in spans.items():
        (folder/(name+'.asm')).write_text(window(f.image,DEFAULT_IMAGE,DEFAULT_OBJDUMP,lo,hi))
    root=Path.cwd();sources={Path(__file__).resolve()}
    for module in list(sys.modules.values()):
        file=getattr(module,'__file__',None)
        if file and Path(file).resolve().is_relative_to(root/'tools'): sources.add(Path(file).resolve())
    report=dict(main_sha256=sha(f.image),checkpoint_sha256=CHECKPOINT_SHA,
        engine_sha256=sha(ENGINE.read_bytes()),
        source_sha256={str(p.relative_to(root)):sha(p.read_bytes()) for p in sorted(sources)},
        spans={k:list(map(hex,v)) for k,v in spans.items()},cases=cases,
        limits=[
            'Native constructor, COLOR allocation callback, normal memory manager, converter, preparation, coefficient selection and destructor run. No pixel rendering or asynchronous submission/completion.',
            'Heap bitmaps and metadata records explicitly empty; CPU0 fixture; job/context blocks and one32768-byte COLOR buffer mapped only after native allocation.',
            'Actual capture crop producer, input pixel buffers and outer job format are not supplied; full-frame geometry and wrapper header choices are explicit fixtures.',
            'Uncontended exclusions modeled at checked callers. Processing atomic byte lock executes against explicit initially-clear RAM; not a multicore concurrency simulation.',
            'Twenty-four-byte canary beyond logical14920-byte job survives tested paths only. A future14944-byte request stays in the16384-byte size class; no H/L field, snapshot transport, dispatcher completion or universal unused-tail claim is established.',
            'Two jobs coexist; explicit calls test constructor/preparation/free contract, not real kernel timing. Prepared job destruction is not evidence of physical image completion.',
            'No changed firmware instructions, flashable image or camera test.'
        ])
    (args.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'{len(cases)} processing-job cases passed.',flush=True)


if __name__=='__main__':
    main()
