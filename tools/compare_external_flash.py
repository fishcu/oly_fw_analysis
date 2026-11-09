#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Compare native photographic-flash reply parsers across four camera images."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import re
import struct
import subprocess

from penf_external_flash_probe import CAMERAS
from penf_disasm import DEFAULT_OBJDUMP
from penf_probe import ProbeState, CALLER
from penf_hsl_context_probe import finished
from penf_repack_preflight import sha,save

IMAGES=CAMERAS+[('OM-5',Path('analysis/om5_1200/00_0100_40780020.decoded.bin'),0x60021020)]


def asm(path,base,start,stop):
    return subprocess.check_output([str(DEFAULT_OBJDUMP.resolve()),'-b','binary','-m','mn10300',
        '-D','-z','--insn-width=16',f'--adjust-vma={base:#x}',f'--start-address={start:#x}',
        f'--stop-address={stop:#x}',str(path)],text=True)


def normalized(text,start,size,identifier):
    result=[];calls={}
    for line in text.splitlines():
        m=re.match(r'^([0-9a-f]+):\s+(?:[0-9a-f]{2} )+\s*\t(.*)$',line)
        if not m:continue
        address=int(m[1],16);instruction=m[2]
        if instruction.startswith('call\t'):
            target=re.search(r'0x[0-9a-f]+',instruction)[0]
            calls.setdefault(target,'helper'+str(len(calls)))
            instruction=instruction.replace(target,calls[target])
        def symbol(m):
            token=m[0];v=int(token,0) if token.startswith('0x') else int(token)
            if start<=v<start+size:return 'parser+'+hex(v-start)
            if identifier-0x600<=v<identifier+0xc00:return 'state'+f'{v-identifier:+#x}'
            return token
        instruction=re.sub(r'0x[0-9a-f]+|(?<![a-z0-9])\d{9,}',symbol,instruction)
        result.append(f'{address-start:03x} '+instruction)
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    # ID choices include the common special cases and an unnamed EXIF-ID hypothesis.
    vectors=[bytes([i,0,f,0,0,0]) for i in (0,9,10,13,54,77,127) for f in (0,64)]
    vectors += [bytes([13]+[(1<<bit) if j==byte else 0 for j in range(1,6)])
                for byte in range(1,6) for bit in range(8)]
    vectors=list(dict.fromkeys(vectors))
    report=[];all_outputs={};norms={}
    for name,path,base in IMAGES:
        b=path.read_bytes();matches=list(re.finditer(re.escape(bytes.fromhex('2c86000408fcdc')),b))
        assert len(matches)==1;off=matches[0].start();start=base+off
        rx=struct.unpack_from('<I',b,off+7)[0];identifier=struct.unpack_from('<I',b,off+0x36)[0]
        size=0x1bb if name=='PEN-F' else 0x1f0
        text=asm(path,base,start,start+size);(args.out/(name+'-parser.asm')).write_text(text)
        norms[name]=normalized(text,start,size,identifier)
        (args.out/(name+'-parser.normalized.txt')).write_text('\n'.join(norms[name])+'\n')
        rows=[];outputs=[]
        for data in vectors+[None]:
            q=data+bytes([(134+sum(data))&255]) if data is not None else bytes([13,0,0,0,0,0,0])
            s=ProbeState(start,0xf0,20 if name=='PEN-F' else 24,bytes(16),{})
            s.regions=[replace(r,address=base,data=b) if r.name=='main' else r for r in s.regions]
            s.ram('flash_state',identifier-0x600,bytes(0x1200),aliases=False)
            s.write(identifier,bytes.fromhex('efbe'));s.write(rx,q)
            r=s.run({CALLER+7},limit=2000);finished(s,r)
            value=s.regs['d0'];parsed=s.read(identifier,32)
            if data is None:assert value==0x2c2a and parsed[:2]==bytes.fromhex('efbe')
            else:
                assert value==(1 if q[0]==77 else 0) and int.from_bytes(parsed[:2],'little')==q[0]
                if q[0]!=77:assert parsed[18]==(2 if q[2]&64 else 1)
            outputs.append((value,parsed))
            rows.append(dict(reply=q.hex(),return_value=hex(value),parsed_state=parsed.hex(),instructions=s.steps))
        all_outputs[name]=outputs
        report.append(dict(camera=name,path=str(path),sha256=sha(b),base=hex(base),parser=hex(start),
            rx=hex(rx),identifier=hex(identifier),parser_bytes=size,cases=rows))
        print(name,len(rows),'native parser cases passed',flush=True)
    assert norms['E-P7']==norms['OM-3']==norms['OM-5']
    assert all_outputs['E-P7']==all_outputs['OM-3']==all_outputs['OM-5']
    differences=[]
    for i,((ra,a),(rb,b)) in enumerate(zip(all_outputs['PEN-F'],all_outputs['E-P7'])):
        assert ra==rb and a[:2]==b[:2] and a[18]==b[18]
        if a[:19]!=b[:19]:
            differences.append(dict(reply=report[0]['cases'][i]['reply'],
                changed_offsets=[hex(j) for j in range(19) if a[j]!=b[j]],
                penf=a[:19].hex(),newer=b[:19].hex()))
    save(args.out,'audit',dict(all_assertions_passed=True,cameras=report,
        normalized_ep7_om3_om5_parsers_identical=True,newer_32byte_state_results_identical=True,
        id_return_and_capability_class_identical=True,older_common_field_differences=differences,
        scope='Synthetic valid and invalid command-0x86 replies; no captured FL-LM3 traffic. '
              'Native helper calls run, with explicit state RAM. No power electronics, transport, '
              'device detection or firing modeled. No assertion of equivalent whole drivers.',
        script_sha256=sha(Path(__file__).read_bytes())))


if __name__=='__main__':main()
