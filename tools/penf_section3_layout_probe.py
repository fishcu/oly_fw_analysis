#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Execute the section-3 loader with an explicit, successful logical-flash model.

Only JSON reports are saved. This checks native address/length selection and
byte placement, not NAND physics, pre-main boot, cache coherence or recovery.
"""
import argparse
from pathlib import Path
import struct

from penf_emulator import BASE, ROOT, firmware, ENGINE
from penf_probe import ProbeState, CALLER, LOGS
from penf_repack_preflight import build_candidate, save, sha

START, END = 0x60432800, 0x6069b800
FLASH = 0x407b1800
FIELD = 0x60622d84
CAVE_START, CAVE_END = 0x6069b26c, 0x6069b800


def probe(payload):
    # Callback has its own MOVM prologue, hence caller mask/frame are both zero.
    s = ProbeState(0x600421e1, 0, 0, bytes(16), {})
    s.ram('selected_section', 0x61c583fc, struct.pack('<I', 3) + bytes(8))
    # Poison the destination to show it really is loaded, rather than relying
    # on the disassembler's flat-image mapping already containing the bytes.
    s.ram('section3_destination', START, b'\xa5'*(END-START), executable=True)
    services = {0x60069606: 'storage semaphore acquired',
                0x600696f9: 'storage semaphore released',
                0x6006be0f: 'diagnostic trace suppressed',
                0x600226be: 'storage read indication acknowledged',
                0x6006906e: 'completion event set'}
    hooks = LOGS | set(services) | {CALLER+7, 0x600224c2}
    reads, completions = [], []
    for _ in range(40):
        result = s.run(hooks, limit=10000)
        pc = s.regs['pc']
        if result['status'] != 'breakpoint' or pc == CALLER+7:
            break
        if pc in LOGS:
            s.diagnostic()
        elif pc in services:
            row = dict(entry=hex(pc), name=services[pc], d0=s.regs['d0'], d1=s.regs['d1'])
            if pc == 0x6006906e:
                completions.append(row)
            s.events.append(dict(kind='model', **row))
            s.return_from_model(0)
        else:
            source, target, size = s.regs['a0'], s.regs['a1'], s.regs['d1']
            # Native address conversion has already executed. This model
            # accepts only the exact reviewed section-3 logical read.
            assert (source, target, size) == (FLASH+0x40000000, START+0x40000000, END-START)
            offset = source - 0x40000000 - 0x403a0020
            data = payload[offset:offset+size]
            assert len(data) == size
            s.write(target, data)
            row = dict(source=hex(source), destination=hex(target), bytes=size,
                       logical_flash=hex(FLASH), decoded_offset=hex(offset), sha256=sha(data))
            reads.append(row)
            s.events.append(dict(kind='model', name='successful logical flash read', **row))
            s.return_from_model(0)
    expected = payload[START-BASE:END-BASE]
    loaded = s.read(START, END-START)
    report = dict(scope='Native section callback, address conversion and flash wrappers; '
        'successful low-level logical read, semaphore, indication and event services modeled. '
        'Starts at callback, not power-on. RAM aliasing explicit; hardware NAND/ECC/cache not modeled.',
        returned=s.regs['pc'] == CALLER+7, pc=hex(s.regs['pc']),
        instructions=s.steps, stack_restored=s.regs['sp'] == 0x18018000,
        reads=reads, completions=completions, loaded_sha256=sha(loaded),
        expected_sha256=sha(expected), exact_section_loaded=loaded == expected,
        cached_uncached_equal=loaded == s.read(START+0x40000000, END-START),
        lightness_bytes=s.read(FIELD, 2).hex(),
        old_padding_entire_suffix_ff=s.read(CAVE_START, CAVE_END-CAVE_START) == b'\xff'*(CAVE_END-CAVE_START),
        descriptor_hex=s.read(0x60026d94, 12).hex(), events=s.events)
    return report, loaded


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    main, candidate, _, _, _ = build_candidate()
    reports, loads = [], []
    for name, payload, expected_field in [('stock', main.payload, '0000'),
                                          ('L7', candidate.payload, '2c01')]:
        r, loaded = probe(payload)
        save(args.out, name, r)
        assert r['returned'] and r['stack_restored'], r['events'][-1]
        assert r['exact_section_loaded'] and r['cached_uncached_equal']
        assert len(r['reads']) == len(r['completions']) == 1
        assert r['completions'][0]['d1'] == 4  # 1 << (section ID - 1)
        assert r['lightness_bytes'] == expected_field
        assert r['old_padding_entire_suffix_ff']
        reports.append(r)
        loads.append(loaded)
        print(name + ': exact section loaded; L=' + expected_field, flush=True)
    diffs = [i for i, (a, b) in enumerate(zip(*loads)) if a != b]
    assert diffs == [FIELD-START, FIELD-START+1]
    # Loader descriptors and all pre-table bytes retain their stock positions.
    assert main.payload[:FIELD-BASE] == candidate.payload[:FIELD-BASE]
    save(args.out, 'summary', dict(all_assertions_passed=True,
        section3_descriptor=hex(0x60026d94), destination=hex(START),
        end_exclusive=hex(END), bytes=END-START, logical_flash_source=hex(FLASH),
        changed_runtime_addresses=[hex(START+i) for i in diffs],
        changed_logical_flash_addresses=[hex(FLASH+i) for i in diffs],
        old_padding=dict(start=hex(CAVE_START), end_exclusive=hex(CAVE_END),
                         logical_flash_start=hex(FLASH+CAVE_START-START),
                         loaded_unchanged=True, later_ownership_proven=False,
                         used_by_current_candidate=False),
        source_sha256={str(path.relative_to(ROOT)): sha(path.read_bytes()) for path in
            (Path(__file__).resolve(), ROOT/'tools/penf_repack_preflight.py',
             ROOT/'tools/penf_update_probe.py',ROOT/'tools/penf_probe.py', ROOT/'tools/penf_boot_emulator.py',
             ROOT/'tools/penf_emulator.py', ENGINE)}))


if __name__ == '__main__':
    main()
