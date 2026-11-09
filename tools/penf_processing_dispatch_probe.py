#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Bounded job-dispatch continuation with manual-backed BSCH correction.

The bundled GNU core has incomplete BSCH Dm,Dn semantics. Keep earlier engine
artifacts unchanged: model only the exact reviewed instruction at604fc296.
"""
import argparse
import json
from pathlib import Path
import struct
import sys
from penf_processing_job_probe import (
    JobExecution, Fixture, setup, populate, construct, conversion, invoke,
    returned, BASE, CALLER, ENGINE, CHECKPOINT_SHA, DEFAULT_IMAGE, DEFAULT_OBJDUMP,
    sha, window,
)

BSCH = 0x604fc296
MANUAL = Path('research/mn103-core-mode/mn103sa7d-a7g.txt')


def search_bit(source, position):
    start=(position & 31)-1
    if start < 0: start=31
    masked=source & ((1 << (start+1))-1)
    return (masked.bit_length()-1, False) if masked else (0, True)


class DispatchExecution(JobExecution):
    hooks=JobExecution.hooks | {BSCH}

    def handle(self):
        s=self.s
        if s.regs['pc'] == 0x60039214 and s.regs['mdr'] == 0x604a662d:
            assert self.phase == 0 and self.heap_phase == 0
            self.events.append(dict(operation='reviewed regular task context',entry='0x60039214',
                                    caller_return='0x604a662d',result=0))
            s.return_from_model(0)
            return
        if s.regs['pc'] == BSCH:
            assert s.read(BSCH,2)==b'\xf6\x71'
            source,position=s.regs['d0'],s.regs['d1']
            result,missing=search_bit(source,position)
            s.regs['d1']=result
            s.regs['psw']=(s.regs['psw'] & ~4) | (4 if missing else 0)
            s.regs['pc']+=2
            self.events.append(dict(operation='manual-backed BSCH instruction',pc=hex(BSCH),
                                    source=hex(source),position=position,result=result,C=int(missing),
                                    source_manual_page='XVI-67',other_flags_undefined=True))
            return
        return super().handle()


def bit_controls(f):
    h,_,_=setup(f,1,0xa5);s=h.s;e=DispatchExecution(h)
    cases=[]
    for bitmap,expected in [(0,31),(0xffffffff,255)]+[(0xffffffff ^ (1<<b),b) for b in range(32)]:
        r=e.call(0x604fc293,0,0,dict(d0=bitmap))
        returned(s,r['execution']);assert s.regs['d0']==expected
        cases.append(dict(bitmap=hex(bitmap),expected=expected,execution=r))
    # The helper always starts at0. Exercise the instruction's other starts
    # directly and compare to the manual's descending search description.
    for source,position,expected,carry in [(0x80000001,31,0,0),(0x80000001,0,31,0),
                                           (0x80000000,31,0,1),(0x10,0x105,4,0),
                                           (0x10,4,0,1),(0,0,0,1)]:
        s.regs=dict(pc=BSCH,d0=source,d1=position,psw=0x2400)
        e.handle()
        assert (s.regs['d1'],int(bool(s.regs['psw']&4)))==(expected,carry)
        cases.append(dict(source=hex(source),start=position,expected=expected,C=carry,direct_instruction=True))
    return cases


def frontier(f,fill):
    h,old,preparation=setup(f,1,fill);s=h.s
    e=DispatchExecution(h)
    i,a,allocation=h.allocate();population=populate(h,i,a)
    job,constructor=construct(h,e,i,a,1)
    prepared=conversion(h,e,job,i,h.values())
    maps=[]
    for ptr in struct.unpack_from('<3I',f.image,0x606268a4-BASE):
        data=f.read(ptr,4);assert data==bytes(4)
        s.ram('captured_stage_bitmap_'+hex(ptr),ptr,data)
        maps.append(dict(address=hex(ptr),value=data.hex()))
    s.ram('native_processing_id_bitmaps',0xa1c61e1c,bytes([fill])*32)
    ids=invoke(s,0x604bcf01,0x80,4);returned(s,ids)
    assert s.read(0xa1c61e1c,32)==bytes(32)
    cache_base=struct.unpack_from('<I',f.image,0x606312c8-BASE)[0]
    cache_count=f.image[0x606312d4-BASE]
    assert cache_count==2
    cache=f.read(cache_base,cache_count*8408)
    assert cache==bytes(cache_count*8408)
    s.ram('captured_cpu0_two_stage_cache_rows',cache_base,cache)
    maps.append(dict(address=hex(cache_base),bytes=len(cache),sha256=sha(cache),stride=8408))
    s.ram('native_processing_hardware_reference_bytes',0x8ff00198,bytes([fill])*12,aliases=False)
    hardware_refs=invoke(s,0x604b31b9,0,4);returned(s,hardware_refs)
    assert s.read(0x8ff00198,12)==bytes(12)
    canary=bytes(range(24));s.write(job+14920,canary)
    r=e.call(0x604c2447,0xf0,32,dict(d0=job,d1=0xffff))
    assert r['execution']['status']=='memory_fault'
    assert r['execution']['fault']['pc']==0x604b31dc
    assert r['execution']['fault']['address']==0x988000d4
    assert r['execution']['fault']['access']=='write'
    assert s.read(job+14920,24)==canary
    assert s.read(0x8ff00198,1)==b'\x01'
    # Native submission604b3eb0 keeps its context in a2 across the call to
    # the hardware-reference helper. This is the real constructed job path.
    assert s.regs['mdr']==0x604b3f36
    context=s.regs['a2']
    request=int.from_bytes(s.read(context+4,4),'little')
    output=int.from_bytes(s.read(context+12,4),'little')
    values=list(struct.unpack('<12b',s.read(request+1076,12)))
    expected_values=list(h.values())
    assert values==expected_values
    rows=[struct.unpack('<3h',s.read(output+0x2a4+((i%2)*6+i//2)*24+18,6)) for i in range(12)]
    pointers=struct.unpack_from('<12I',f.image,0x6062fef8-BASE)
    for i,value in enumerate(values):
        record=(i%2)*6+i//2
        amplitude=struct.unpack_from('<h',f.image,0x60622d74+record*28+14-BASE)[0]
        gain=struct.unpack_from('<H',f.image,pointers[record]-BASE+2*(value<0))[0]
        n=((amplitude*gain)>>8)*value
        assert rows[i]==(0,(1 if n>=0 else -1)*(abs(n)//5),0)
    return dict(fill=hex(fill),preparation=preparation,allocation=allocation,population=population,
                constructor=constructor,prepared=prepared,captured_maps=maps,id_initialization=ids,
                hardware_reference_initialization=hardware_refs,dispatch=r,registers=s.regs,
                native_submission=dict(entry='0x604b3eb0',context=hex(context),request=hex(request),
                                       coefficients=hex(output),saturation=values,HSL=rows,
                                       callback_pair=list(map(hex,struct.unpack('<2I',s.read(request,8)))),
                                       captured_saturation=expected_values,uses_capture_saturation=values==expected_values,
                                       color_mask=hex(int.from_bytes(s.read(output+0x3c4,4),'little')),
                                       coefficient_sha256=sha(s.read(output+0x2a4,292))),
                trailer_survives_to_hardware_frontier=True,
                stage_bitmap=hex(int.from_bytes(s.read(0x618a3d84,4),'little')),
                processing_id_bitmaps=s.read(0xa1c61e1c,32).hex())


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    f=Fixture();controls=bit_controls(f);print(f'{len(controls)} BSCH controls passed',flush=True)
    cases=[]
    for fill in (0,0xa5):
        c=frontier(f,fill);cases.append(c)
        print(json.dumps(c['dispatch']['execution'],indent=2),flush=True)
    root=Path.cwd();sources={Path(__file__).resolve()}
    for module in list(sys.modules.values()):
        file=getattr(module,'__file__',None)
        if file and Path(file).resolve().is_relative_to(root/'tools'): sources.add(Path(file).resolve())
    report=dict(main_sha256=sha(f.image),checkpoint_sha256=CHECKPOINT_SHA,engine_sha256=sha(ENGINE.read_bytes()),
                source_sha256={str(p.relative_to(root)):sha(p.read_bytes()) for p in sorted(sources)},
                manual=dict(path=str(MANUAL),sha256=sha(MANUAL.read_bytes()),page='XVI-67'),
                instruction_controls=controls,cases=cases,
                limits=['Exact BSCH opcode at604fc296 modeled from the local processor manual; global engine unchanged.',
                        'No asynchronous kernel schedule or physical pixel processing supplied. Stop before store2048 to988000d4; no hardware success supplied.',
                        'Explicit initially-clear atomic lock plus native bitmap/reference-byte initializers. Two8408-byte cache rows come from declared CPU0 table/count and captured zero contents.',
                        'Undefined BSCH V/N/Z preserved; reviewed helper immediately branches on C only.'])
    (args.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    for name,lo,hi in [('bit-search-helper',0x604fc293,0x604fc2a0),('stage-token',0x604beb78,0x604bec38),
                       ('hardware-reference-and-writes',0x604b31b9,0x604b322c),
                       ('processing-id-allocation',0x604bcf01,0x604bcfa0),
                       ('stage-cache-acquisition',0x604f8d4b,0x604f8df4),
                       ('regular-task-check',0x604a6625,0x604a6692)]:
        (args.out/(name+'.asm')).write_text(window(f.image,DEFAULT_IMAGE,DEFAULT_OBJDUMP,lo,hi))


if __name__=='__main__':main()
