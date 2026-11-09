#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Validate and compare archived PEN-F 3100 stock with the supplied video hack.

Produces evidence, decoded main blocks and disassembly; no patched update.
"""
import argparse
import json
from pathlib import Path
import struct

from oly_container import parse, reconstruct, sha256
from penf_disasm import DEFAULT_IMAGE, DEFAULT_OBJDUMP, window
from penf_landmarks import BASE, MAIN_SHA256

STOCK_MAIN_SHA = '3d5963c6d9385aafc99ff51892ec706bef1c4783a84f586179271a64b8401bfd'
STOCK_SHA = '212a1c14ac5ebf615ce18896f45d5382eabc99d700acd24fa21841eafeea4b4c'
PATCH_SHA = 'c3b287871164efcf98dd23c1ba45246fa5fd815cb89d52d378903d5a5c53561d'


def differences(before, after):
    if len(before) != len(after):
        raise ValueError('different sizes')
    spans, start = [], None
    for i, (a, b) in enumerate(zip(before, after)):
        if a != b and start is None:
            start = i
        if a == b and start is not None:
            spans.append((start, i))
            start = None
    if start is not None:
        spans.append((start, len(before)))
    return [{'offset': hex(i), 'bytes': j-i, 'stock_hex': before[i:j].hex(),
             'patched_hex': after[i:j].hex()} for i, j in spans]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--stock', type=Path, default=Path('research/updater/archived-stock-3100.bin'))
    ap.add_argument('--patched', type=Path, default=Path('firmware_files/e1229999.bin'))
    ap.add_argument('--current-main', type=Path, default=DEFAULT_IMAGE)
    ap.add_argument('--objdump', type=Path, default=DEFAULT_OBJDUMP)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        ap.error('output directory must not already exist')
    stock, patched = args.stock.read_bytes(), args.patched.read_bytes()
    if sha256(stock) != STOCK_SHA:
        ap.error('requires the exact archived PEN-F 3100 stock image')
    if sha256(patched) != PATCH_SHA:
        ap.error('requires the exact supplied historical hack')
    a, b = parse(stock), parse(patched)  # validates every outer checksum
    if sha256(a[0].payload) != STOCK_MAIN_SHA:
        ap.error('requires the identified archived 3100 stock main block')
    if len(a) != len(b):
        raise ValueError('different block counts')
    reports = []
    for x, y in zip(a, b):
        if x.header != y.header:
            raise ValueError('different header layout, model or build')
        reports.append({
            'block': x.index, 'kind': hex(x.kind), 'version': hex(struct.unpack_from('<H', x.header, 16)[0]),
            'stock_payload_sha256': sha256(x.payload), 'patched_payload_sha256': sha256(y.payload),
            'payload_differences': differences(x.payload, y.payload),
            'trailer_differences': differences(x.trailer, y.trailer),
        })
    if reconstruct(a) != stock or reconstruct(b) != patched:
        raise ValueError('round-trip mismatch')
    current = args.current_main.read_bytes()
    if sha256(current) != MAIN_SHA256:
        ap.error('requires exact current 3101 main block for the routine comparison')
    # This instruction-aligned window includes both changed immediate operands.
    start, stop = 0x60566309, 0x6056634a
    old_routine = a[0].payload[start-BASE:stop-BASE]
    new_routine = current[start-BASE:stop-BASE]
    args.out.mkdir(parents=True)
    for name, data in [('stock', a[0].payload), ('patched', b[0].payload)]:
        path = args.out / f'{name}-3100-main.bin'
        path.write_bytes(data)
        (args.out / f'{name}-recording-limit.asm').write_text(
            window(data, path, args.objdump, start, stop))
    (args.out / 'current-3101-recording-limit.asm').write_text(
        window(current, args.current_main, args.objdump, start, stop))
    report = {
        'stock_file': str(args.stock), 'stock_sha256': sha256(stock),
        'patched_file': str(args.patched), 'patched_sha256': PATCH_SHA,
        'bytes_each': len(stock), 'outer_checksums_valid': True,
        'both_exact_roundtrips': True, 'blocks': reports,
        'whole_container_differences': differences(stock, patched),
        'analysis_base': hex(BASE),
        'routine_start': hex(start), 'routine_stop_exclusive': hex(stop),
        'routine_identical_in_stock_3100_and_3101': old_routine == new_routine,
        'immediates': [
            {'instruction': '0x6056631e', 'operand_offset': '0x5452ff',
             'input_mode_values': [3, 6], 'stock': 1740, 'patched': 32400},
            {'instruction': '0x60566324', 'operand_offset': '0x545305',
             'input_mode_values': [4], 'stock': 7200, 'patched': 32400},
        ],
        'hardware_tested': False, 'modified_update_created': False,
        'interpretation': 'Constants strongly match recording durations in seconds: 29 min / 2 h become 9 h. Numeric recording-mode names not yet traced.',
    }
    (args.out / 'historical-diff.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'blocks'}, indent=2))


if __name__ == '__main__':
    main()
