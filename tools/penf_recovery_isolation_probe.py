#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native recovery excerpts with COLOR code/data and proposed caves inaccessible.

Also follows the diagnostic flash command up to its I/O request. All tests
are offline; no command is sent to a camera and no update image is saved.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import struct

from penf_emulator import ROOT, BASE, Region, firmware
import penf_update_probe as updater
import penf_input_recovery_probe as sd
from penf_repack_preflight import save, sha
from penf_disasm import window, DEFAULT_IMAGE, DEFAULT_OBJDUMP
from penf_landmarks import COLOR_TABLE_ADDRESS, COLOR_TABLE_SIZE

ORIGINAL_STATE = updater.ProbeState


def without_ranges(regions, holes):
    result = list(regions)
    for lo, hi in holes:
        rebuilt = []
        for r in result:
            end = r.address+len(r.data)
            if end <= lo or hi <= r.address:
                rebuilt.append(r)
                continue
            assert not r.capture and r.alias_of is None
            if r.address < lo:
                rebuilt.append(replace(r, name=r.name+f'_before_{lo:x}', data=r.data[:lo-r.address]))
            if hi < end:
                rebuilt.append(replace(r, name=r.name+f'_after_{hi:x}', address=hi, data=r.data[hi-r.address:]))
        result = rebuilt
    return result


def isolated_update(out):
    audit = json.loads((ROOT/'analysis/code_space/verified/audit.json').read_text())
    holes = [(int(r['proposed_start'],16),int(r['proposed_end_exclusive'],16)) for r in audit['candidates']]
    holes += [(0x604f6a2e,0x604f8461), (COLOR_TABLE_ADDRESS,COLOR_TABLE_ADDRESS+COLOR_TABLE_SIZE)]

    class GuardedState(ORIGINAL_STATE):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.regions = without_ranges(self.regions, holes)
            self.events.append(dict(kind='model', name='runtime ranges inaccessible',
                ranges=[[hex(a),hex(z)] for a,z in holes],
                limit='Input package bytes remain readable; only runtime code/data is excluded.'))

    updater.ProbeState = sd.ProbeState = GuardedState
    results = []
    try:
        package = updater.synthetic_block(kind=0x100,address=0x403a0000)
        for mode in (0,2):
            r,s = updater.update_probe(package, mode)
            save(out, 'isolated-updater-mode'+str(mode),r)
            assert r['returned'] and r['result'] == 0
            assert len(r['write_requests']) == (1 if mode==0 else 0)
            results.append(dict(mode=mode,instructions=r['instructions']))
            if mode==2:
                decoded = s.read(updater.BUFFER,len(package))
        r,s = updater.update_probe(decoded,1)
        save(out,'isolated-updater-mode1',r)
        assert r['returned'] and r['result']==0 and len(r['write_requests'])==1
        results.append(dict(mode=1,instructions=r['instructions']))
        r,s = sd.sd_client(package)
        save(out,'isolated-sd-client',r)
        assert r['request'] and r['request']['data_sha256']==sha(package)
        for active in (False,True):
            report,state = sd.sd_service(package,r['request'],active)
            save(out,'isolated-sd-service-'+str(int(active)),report)
            assert report['dispatch'] and report['dispatch']['data_sha256']==sha(package)
    finally:
        updater.ProbeState = sd.ProbeState = ORIGINAL_STATE
    return dict(excluded_runtime_ranges=[[hex(a),hex(z)] for a,z in holes],updater_cases=results,
        native_SD_client_and_both_service_branches_passed=True,
        qualification='Native excerpts with synthetic valid main component; filesystem and kernel APIs modeled; '
          'flash requests trapped. Does not establish physical activation, complete FAT/USB execution or recovery after a startup failure.')


def diagnostic_flash_request(out):
    args = ['flash','oly','fmem','40000000','2048','101']
    argv = 0x19000000
    strings = 0x19000100
    blob = b'';pointers=[]
    for arg in args:
        pointers.append(strings+len(blob));blob+=arg.encode()+b'\0'
    s=ORIGINAL_STATE(0x600725a4,0,0,bytes(16),dict(a0=argv,d0=len(args)))
    s.ram('argv',argv,struct.pack('<6I',*pointers),aliases=False)
    s.ram('strings',strings,blob,aliases=False)
    s.ram('debug_flash_destination',0x6117119c,bytes(4))
    # Native locale setup 60143f13 fills these pointers from stock constants;
    # sscanf 60144dcb stores the returned pointer at 61bc1d78.
    s.ram('libc_locale_pointers',0x61bc1a40,bytes(0x34))
    # 61bc1d70 starts at zero in this synthetic parser-state scenario.
    s.ram('libc_scanf_state',0x61bc1d70,bytes(12))
    # 60144e3a clears this 255-byte sscanf character-class scratch array.
    s.ram('libc_scanf_character_set',0x61bc1c70,bytes(255))
    # 60145433 accumulates numeric input here; our longest token is 8 bytes.
    s.ram('libc_numeric_token',0x61bc1a74,bytes(32))
    b=firmware()
    s.regions.append(Region('relocated_helpers',0x47000800,b[0x113c9e0:0x113c9e0+0x1800],'rx'))
    hooks=updater.LOGS|{0x60022ee7,0x600720e1,updater.CALLER+7}
    request=None
    for _ in range(40):
        result=s.run(hooks,limit=100000)
        pc=s.regs['pc']
        if result['status']!='breakpoint' or pc==updater.CALLER+7:
            break
        if pc==0x600720e1:
            request=dict(mode=hex(s.regs['d1']),bytes=s.regs['d0'],
                source=hex(s.regs['a1']),destination=hex(s.regs['a0']))
            break
        if pc in updater.LOGS:s.diagnostic()
        else:
            s.events.append(dict(kind='model',name='timer fixed at zero'))
            s.return_from_model(0)
    report=dict(arguments=args,request=request,instructions=s.steps,pc=hex(s.regs['pc']),events=s.events,
        limit='Synthetic local command invocation, stopping before I/O; no boot bytes read. '
              'The dispatcher supports writes for other modes. Transport and ownership of the hardcoded RAM buffer are not established.')
    save(out,'diagnostic-flash-request',report)
    assert request==dict(mode='0x101',bytes=2048,source='0x40000000',destination='0xa1000000'), (report['pc'],report['events'][-1].get('result',{}).get('fault'))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    isolation=isolated_update(args.out)
    print('Six isolated updater/client/service scenarios passed',flush=True)
    diagnostic=diagnostic_flash_request(args.out)
    print('Native debug parser produced bounded logical-flash read request',flush=True)
    for name,start,end in [('debug-flash-parser',0x600725a4,0x600726a0),
                            ('read-dispatch',0x600720e1,0x600721aa)]:
        (args.out/(name+'.asm')).write_text(window(firmware(),DEFAULT_IMAGE,DEFAULT_OBJDUMP,start,end))
    save(args.out,'summary',dict(all_assertions_passed=True,main_sha256=sha(firmware()),
        isolation=isolation,diagnostic_read_request=diagnostic['request'],
        source_sha256={str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in
          (Path(__file__).resolve(),ROOT/'tools/penf_landmarks.py',ROOT/'tools/penf_update_probe.py',ROOT/'tools/penf_probe.py',ROOT/'tools/penf_input_recovery_probe.py',
           ROOT/'tools/penf_boot_emulator.py',ROOT/'tools/penf_emulator.py',ROOT/'analysis/code_space/verified/audit.json')}))


if __name__=='__main__':
    main()
