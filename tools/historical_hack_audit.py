#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Exact diffs and bounded native execution of three independently obtained hacks.

No generated update files. Historical downloads are read-only inputs.
"""
import argparse
from dataclasses import replace
from pathlib import Path
import struct

from oly_container import parse,reconstruct,replace_payload
from penf_repack_preflight import sha,save
from penf_historical_diff import differences
from penf_probe import ProbeState, CALLER
from penf_hsl_context_probe import finished
from penf_disasm import window,DEFAULT_OBJDUMP

BASE=0x60021020
CASES=[dict(name='PEN-F-3100',stock='research/updater/archived-stock-3100.bin',
    hack='firmware_files/e1229999.bin',
    stock_sha='212a1c14ac5ebf615ce18896f45d5382eabc99d700acd24fa21841eafeea4b4c',
    hack_sha='c3b287871164efcf98dd23c1ba45246fa5fd815cb89d52d378903d5a5c53561d',
    patches=[(0x5452ff,'cc06','907e'),(0x545305,'201c','907e')],
    duration=0x60566309,logger=0x60550db1),
  dict(name='E-M1-II-3001',stock='e-m1_hack/original_fw/3.0/OLY_E_125_3001_0000_0000.BIN',
    hack='e-m1_hack/hacked_fw/3.0/e1259999.bin',
    stock_sha='36a36af129baea94b4df983c8f14ea90acaeb9905cf420252efdad2fa9844317',
    hack_sha='845a3e73cf143cbd7400f5bbec41675540930e5ab7cd1c5a2ed8e7a68b30b49e',
    patches=[(0x3333b8,'1ca006c814a003c810a008c8','fccc1000007060881cdf801c'),
             (0x631d6f,'c807','cbcb')],duration=0x603543d2,logger=0x60062a37,
    stacking=0x60652d28,guard=0x606525c7,lens_getter=0x60227064,lens_offset=1092,
    debug=0x622ee2f0,allowlist=0x60748485),
  dict(name='E-M5-II-4100',stock='research/historical_hacks_2026/em5ii_stock/OLY_E_118_4100_0000_0000.BIN',
    hack='research/historical_hacks_2026/e1189999.bin',
    stock_sha='c03050db130b051e446fa08dec1ad6f29afc890308888383428f4938a57edef0',
    hack_sha='f07cd122c7273d467edb6d7260b7ddb9c90cdc2c4bd95efb8d5131ace12368ee',
    patches=[(0x3f2ad5,'c807','cbcb'),(0x534866,'cc06','907e'),(0x53486c,'201c','907e')],
    duration=0x60555870,logger=0x60539e6c,stacking=0x60413a8e,guard=0x604138f8,
    lens_getter=0x6014b867,lens_offset=576,debug=0x6187f9bc,allowlist=0x605e3c30)]


def state(image,entry,mask,frame,regs):
    s=ProbeState(entry,mask,frame,bytes(16),regs)
    s.regions=[replace(r,data=image) if r.name=='main' else r for r in s.regions]
    return s


def duration(c,image,modified):
    rows=[]
    for mode in (0,3,4,6,8,9,65535):
        dest=0x19000000;s=state(image,c['duration'],0,0,dict(d0=mode,a0=dest))
        s.ram('duration',dest,bytes.fromhex('a5a5a5a5'),aliases=False)
        modeled=[]
        for _ in range(3):
            r=s.run({CALLER+7,c['logger']},limit=2000)
            if s.regs['pc']!=c['logger']:break
            modeled.append(hex(c['logger']));s.return_from_model(0)
        finished(s,r);value=struct.unpack('<I',s.read(dest,4))[0]
        modes=(3,4,6,8,9) if c['name']=='E-M1-II-3001' else (3,4,6)
        if modified and c['name']=='E-M1-II-3001':expected,rc=0x70000010,0
        elif mode not in modes:expected,rc=0xa5a5a5a5,0x9d06
        else:expected,rc=(32400 if modified else (7200 if mode==4 else 1740)),0
        assert (value,s.regs['d0'])==(expected,rc)
        rows.append(dict(mode=mode,value=value,result=hex(rc),instructions=s.steps,modeled_diagnostics=modeled))
    return rows


def stacking(c,image,modified):
    rows=[];allowed=struct.unpack_from('<9I',image,c['allowlist']-BASE)
    assert allowed[-1]==0xffffffff
    for lens,ready,present in [(allowed[0],1,True),(0xabcdef01,1,True),
                                (0xabcdef01,0,True),(0xabcdef01,1,False)]:
        obj=0x19001000;s=state(image,c['stacking'],0xc0,52,{})
        s.ram('debug_flags',c['debug'],bytes(4),aliases=False)
        raw=bytearray(0x500);raw[c['lens_offset']:c['lens_offset']+4]=bytes([
            (lens>>16)&255,(lens>>24)&255,lens&255,(lens>>8)&255])
        s.ram('lens_object',obj,raw,aliases=False)
        hooks={CALLER+7,c['guard'],c['lens_getter']};modeled=[]
        for _ in range(4):
            r=s.run(hooks,limit=4000);pc=s.regs['pc']
            if pc==CALLER+7:break
            assert r['status']=='breakpoint' and pc in hooks,r
            if pc==c['guard']:s.return_from_model(ready)
            else:
                s.return_from_model(0);s.regs['a0']=obj if present else 0
            modeled.append(hex(pc))
        finished(s,r)
        expected=int(bool(ready and present and (modified or lens in allowed[:-1])))
        assert s.regs['d0']==expected
        rows.append(dict(lens_id=hex(lens),prerequisite=ready,lens_object_present=present,
            result=expected,modeled_functions=modeled,instructions=s.steps))
    return dict(allowlist=[hex(x) for x in allowed],cases=rows)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    reports=[]
    for c in CASES:
        raw=[Path(c[k]).read_bytes() for k in ('stock','hack')]
        assert [sha(b) for b in raw]==[c['stock_sha'],c['hack_sha']]
        blocks=[parse(b) for b in raw]
        assert all(reconstruct(b)==r for b,r in zip(blocks,raw))
        a,b=blocks;payload=bytearray(a[0].payload)
        for offset,before,after in c['patches']:
            before,after=bytes.fromhex(before),bytes.fromhex(after)
            assert payload[offset:offset+len(before)]==before
            payload[offset:offset+len(after)]=after
        assert reconstruct([replace_payload(a[0],payload)]+a[1:])==raw[1]
        row=dict(camera=c['name'],stock_path=c['stock'],hack_path=c['hack'],
            stock_sha256=sha(raw[0]),hack_sha256=sha(raw[1]),bytes_each=len(raw[0]),
            exact_reconstruction=True,all_checksums_valid=True,exact_roundtrips=True,
            encoded_differences=differences(*raw),blocks=[],native=[])
        for x,y in zip(a,b):
            row['blocks'].append(dict(kind=hex(x.kind),version=hex(struct.unpack_from('<H',x.header,16)[0]),
                headers_identical=x.header==y.header,trailer_metadata_identical=x.trailer[:28]==y.trailer[:28],
                decoded_differences=differences(x.payload,y.payload),checksum_before=x.trailer[-4:].hex(),
                checksum_after=y.trailer[-4:].hex()))
        for modified,block in enumerate((a[0],b[0])):
            native=dict(modified=bool(modified),duration=duration(c,block.payload,modified))
            if 'stacking' in c:native['stacking']=stacking(c,block.payload,modified)
            row['native'].append(native)
        reports.append(row);save(args.out,c['name'],row)
        print(c['name'],'exact reconstruction and native behavior passed',flush=True)
    save(args.out,'summary',dict(all_assertions_passed=True,cameras=reports,
        scope='Native patched routines and unchanged prerequisite gates; synthetic lens object and '
              'modeled prerequisite/lens lookup/diagnostic services. No camera execution or recovery proof.',
        script_sha256=sha(Path(__file__).read_bytes())))


if __name__=='__main__':main()
