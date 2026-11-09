#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native load/execute/reload checks of seven padded section interiors.

Synthetic sentinels exist only in RAM; there is no update container or device
access. Execution and alias permissions are emulator models, not an MPU audit.
"""
import argparse
import json
from pathlib import Path
import struct

from penf_emulator import BASE, ROOT, firmware
from penf_probe import ProbeState, CALLER, LOGS
from penf_repack_preflight import save, sha


def load(s, section, payload):
    target=0x600421e1
    s.write(CALLER,b'\xdd'+struct.pack('<i',target-CALLER)+b'\0\0\xcb')
    s.regs=dict(pc=CALLER,sp=0x18018000,psw=0)
    low=int(section['destination'],16);high=int(section['end_exclusive'],16)
    flash=int(section['flash_source'],16)
    services={0x60069606:'storage lock',0x600696f9:'storage unlock',
              0x6006be0f:'diagnostic trace',0x600226be:'read indication',
              0x6006906e:'completion event',0x6006da8c:'section-6 initializer dispatcher'}
    hooks=LOGS|set(services)|{CALLER+7,0x600224c2}
    reads=[];completions=[]
    for _ in range(40):
        r=s.run(hooks,limit=10000);pc=s.regs['pc']
        if r['status']!='breakpoint' or pc==CALLER+7:break
        if pc in LOGS:s.diagnostic()
        elif pc in services:
            row=dict(entry=hex(pc),name=services[pc],d0=s.regs['d0'],d1=s.regs['d1'])
            if pc==0x6006906e:completions.append(row)
            s.events.append(dict(kind='model',**row));s.return_from_model(0)
        else:
            source,dest,size=s.regs['a0'],s.regs['a1'],s.regs['d1']
            # Alias conversion depends on the native helper's address ranges.
            expected_source=flash+0x40000000 if flash<0x41000000 else flash
            assert (source,dest,size)==(expected_source,low+0x40000000,high-low)
            offset=flash-0x403a0020;data=payload[offset:offset+size]
            assert len(data)==size
            s.write(dest,data);reads.append(dict(source=hex(source),destination=hex(dest),bytes=size))
            s.events.append(dict(kind='model',name='successful logical read',**reads[-1]))
            s.return_from_model(0)
    expected=payload[low-BASE:high-BASE]
    report=dict(returned=s.regs['pc']==CALLER+7,pc=hex(s.regs['pc']),reads=reads,
        stack_restored=s.regs['sp']==0x18018000,completions=completions,
        exact_section=s.read(low,high-low)==expected,sha256=sha(s.read(low,high-low)))
    assert report['returned'] and report['stack_restored'] and report['exact_section'],(report,s.events[-1])
    assert len(reads)==len(completions)==1 and completions[0]['d1']==1<<(section['id']-1)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    audit_path=ROOT/'analysis/code_space/verified/audit.json'
    candidates=json.loads(audit_path.read_text())['candidates']
    sections=json.loads((ROOT/'analysis/preset_startup_final/audit.json').read_text())['startup_sections']
    reports=[]
    for candidate in candidates:
        section=next(x for x in sections if x['id']==candidate['section'])
        low=int(section['destination'],16);high=int(section['end_exclusive'],16)
        start=int(candidate['proposed_start'],16);end=int(candidate['proposed_end_exclusive'],16)
        payload=bytearray(firmware())
        # Fill the entire interior, leaving original boundary padding intact.
        marker=bytes((i*37+section['id'])&255 for i in range(end-start))
        payload[start-BASE:end-BASE]=marker
        tag=0x12340000+section['id']
        code=b'\xfc\xcc'+struct.pack('<I',tag)+b'\xdf\0\0'
        payload[start-BASE:start-BASE+len(code)]=code
        s=ProbeState(0x600421e1,0,0,bytes(16),{})
        s.ram('section_selection',0x61c583fc,struct.pack('<I',section['id'])+bytes(8))
        s.ram('loaded_section',low,b'\xa5'*(high-low),executable=True)
        first=load(s,section,payload)
        s.write(CALLER,b'\xdd'+struct.pack('<i',start-CALLER)+b'\0\0\xcb')
        s.regs=dict(pc=CALLER,sp=0x18018000,psw=0)
        result=s.run({CALLER+7},limit=100)
        assert s.regs['pc']==CALLER+7 and s.regs['d0']==tag and s.regs['sp']==0x18018000
        execution=dict(returned=True,result=hex(tag),instructions=result['completed'])
        # A subsequent load should reinstall these same bytes from the same
        # supplied logical image, not select an unmodified alternate copy.
        s.write(start,b'\x55'*(end-start))
        second=load(s,section,payload)
        row=dict(section=section['id'],candidate_start=hex(start),candidate_bytes=end-start,
            first_load=first,marker_execution=execution,reload=second,
            events=s.events,source_image_checksums_repaired=False,
            scope='Supplied decoded logical image, not a validated update package. Loader does not inspect '
                  'an image checksum in this slice. Cache/flash/kernel services modeled; no later application lifecycle.')
        save(args.out,'section-'+str(section['id']),row)
        reports.append({k:v for k,v in row.items() if k!='events'})
        print('section',section['id'],'load / marker execution / reload passed',flush=True)
    save(args.out,'summary',dict(all_assertions_passed=True,sections=len(reports),results=reports,
        source_sha256={str(path.relative_to(ROOT)):sha(path.read_bytes()) for path in
          (Path(__file__).resolve(),audit_path,ROOT/'tools/penf_update_probe.py',ROOT/'tools/penf_probe.py',
           ROOT/'tools/penf_boot_emulator.py',ROOT/'tools/penf_emulator.py')},
        limits='No whole-boot integrity conclusion; no firmware container saved. Physical execution permissions, '
               'cache coherence and freedom from later runtime writes remain outside this probe.'))


if __name__=='__main__':main()
