#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Offline flash-access policy probes. No camera access or firmware output.

Run the actual guard, backend mode selection, and direct page-program prefix.
Stop at diagnostic/controller boundaries; do not simulate successful NAND writes.
"""
import argparse
from pathlib import Path
import struct

from penf_emulator import BASE, ENGINE, Region, firmware
from penf_probe import ProbeState, CALLER
from penf_repack_preflight import save, sha
from penf_disasm import window, DEFAULT_IMAGE, DEFAULT_OBJDUMP


def guard_case(mode, address, size=2048):
    s = ProbeState(0x6013005e, 0xf0, 20, bytes(16),
                   dict(a0=address, a1=0, d0=size))
    s.ram('guard_mode', 0x61171110, struct.pack('<H', mode))
    # First diagnostic scratch write is sufficient to distinguish rejection;
    # no controller state or diagnostic service is modeled.
    r = s.run({CALLER+7, 0x6007d97b}, limit=300)
    assert r['status'] == 'breakpoint', (r['status'], r.get('fault'))
    returned = s.regs['pc'] == CALLER+7
    expected = mode & 0xff00 == 0x100 or (mode != 0 and address == 0x40120000)
    assert returned == expected
    return dict(mode=hex(mode), address=hex(address), size=size,
                guard_returned=returned, rejected_before_controller_write=not returned,
                stop=hex(s.regs['pc']), instructions=s.steps,
                stack_restored=returned and s.regs['sp']==0x18018000)


def backend_case(address, mode):
    s = ProbeState(0x6013024b, 0xf0, 36, bytes(2048),
                   dict(a0=address, a1=0x20000000, d0=2048, d1=mode))
    s.ram('guard_mode_initially_zero', 0x61171110, bytes(2))
    r = s.run({0x60071408}, limit=200)
    assert r['status'] == 'breakpoint' and s.regs['pc'] == 0x60071408, r.get('fault')
    value = int.from_bytes(s.read(0x61171110,2), 'little')
    assert value == (0x109 if address == 0x80000000 else 0x101)
    return dict(address=hex(address), backend_mode=mode,
                guard_before='0x0', guard_at_write_dispatch=hex(value),
                stop=hex(s.regs['pc']), instructions=s.steps,
                models=[], limit='Stops before lower block writer; no flash operations.')


def direct_page_prefix():
    s = ProbeState(0x60021e3e, 0xf0, 36, bytes(16),
                   dict(d0=0x61000000, d1=0x403a0000, a0=2048))
    # Deliberately leave the access-guard RAM unmapped. A read of it would stop.
    # Native page translation: the main image starts in block 29. This fixture
    # states only that this particular logical block has not been remapped.
    s.ram('identity_mapping_for_block_29', 0x61171fc0+29*8,
          struct.pack('<I',29))
    for address in (0x98800128, 0x98d011c0, 0x98d01800, 0x98d01804):
        s.regions.append(Region('controller_capture_'+hex(address), address,
                                bytes(4), 'rw', True))
    writes = []
    hooks = {0x60021e87, 0x60021e8f, 0x60021e9c, 0x60021ea8,
             0x60021eb0, 0x60021eb7, 0x60021ec3}
    locations = {0x60021e87:(0x98800128,'d1'), 0x60021e8f:(0x98d011c0,'d0'),
                 0x60021e9c:(0x98d01800,'d1'), 0x60021ea8:(0x98d01804,'d0'),
                 0x60021eb0:(0x98d01804,'d0'), 0x60021eb7:(0x98d01804,'d0')}
    for _ in range(10):
        r = s.run(hooks, limit=300)
        assert r['status'] == 'breakpoint', (r['status'],r.get('fault'))
        pc = s.regs['pc']
        if pc == 0x60021ec3:
            break
        address, reg = locations[pc]
        value = s.regs[reg]
        writes.append(dict(pc=hex(pc), address=hex(address), value=hex(value)))
        step = s.run(hooks-{pc}, limit=1)
        assert step['status'] == 'instruction_limit' and step['completed'] == 1
        assert int.from_bytes(s.read(address,4),'little') == value
    assert s.regs['pc'] == 0x60021ec3
    assert [(w['address'],w['value']) for w in writes] == [
        ('0x98800128','0x80'), ('0x98d011c0','0x1'),
        ('0x98d01800','0x8000740'), ('0x98d01804','0x1402101'),
        ('0x98d01804','0x1000000'), ('0x98d01804','0x0')]
    return dict(entry='0x60021e3e', flash_destination='0x403a0000',
                guard_ram='unmapped; any access would stop',
                controller_writes=writes, stop=hex(s.regs['pc']),
                instructions=s.steps, modeled_functions=[],
                assumptions=['block 29 maps to itself',
                             'controller registers represented by capture memory',
                             'initial 0x98800128 value is zero'],
                limits='Native prefix emits a program request without reading the guard. '
                       'Stops before completion polling. No DMA, physical NAND operation, '
                       'hardware write protection or successful programming is modeled/proven.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    out = parser.parse_args().out
    out.mkdir(parents=True, exist_ok=True)
    b = firmware()
    windows = {
        'guard-setter-and-policy': (0x6013004c,0x601301c3),
        'backend-update-dispatch': (0x60130365,0x6013038c),
        'direct-page-program': (0x60021e3e,0x60021f42),
        'page-map': (0x6002189d,0x600218de),
        'address-translators': (0x6002213b,0x6002221e),
        'cmio-export-descriptor': (0x604bf77c,0x604bf7a4),
        'cmio-export-and-size': (0x604db0f1,0x604db123),
    }
    for name,(start,end) in windows.items():
        (out/(name+'.asm')).write_text(window(b,DEFAULT_IMAGE,DEFAULT_OBJDUMP,start,end))
    cases = [guard_case(mode,address) for mode in (0,0x203,0x101)
             for address in (0x40120000,0x403a0000,0x41800000,0x80000000)]
    cases.append(guard_case(0x109,0x80000000))
    backend = [backend_case(address,mode) for address in (0x403a0000,0x80000000)
               for mode in (1,8)]
    direct = direct_page_prefix()
    blob = b[0x6067e000-BASE:0x6069b240-BASE]
    reference = Path('analysis/orf_probe/unknown-block2.bin').read_bytes()
    assert len(blob)==119360 and blob==reference and blob[:4]==b'CMIO'
    paths = [Path(__file__), Path('tools/penf_update_probe.py'),Path('tools/penf_probe.py'),
             Path('tools/penf_boot_emulator.py'),Path('tools/penf_emulator.py'),ENGINE]
    report = dict(main_sha256=sha(b), source_sha256={str(p):sha(p.read_bytes()) for p in paths},
                  guard_cases=cases, backend_cases=backend, direct_page_prefix=direct,
                  cmio=dict(bytes=len(blob), sha256=sha(blob), exact_orf_match=True),
                  scope='Offline native branch/request evidence only. No camera I/O, '
                        'firmware mutation, installable output or claim of hardware unlock.')
    save(out,'audit',report)
    print(f'PASS: {len(cases)} guard cases, {len(backend)} backend cases, '
          'one direct page-program prefix, exact CMIO match.')


if __name__ == '__main__':
    main()
