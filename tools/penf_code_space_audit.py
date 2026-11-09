#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Rank loaded padding conservatively; no installable images or camera I/O.

Reference scans detect literal address and relative-transfer candidates, not
all computed accesses. A clean scan is not a lifetime/ownership proof.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

from penf_emulator import BASE, ROOT, firmware
from oly_container import parse


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pointer_candidates(data, low, high):
    result = []
    # Search every byte alignment, using the upper halfword as an efficient
    # prefilter. Match starts can overlap.
    for upper in range(low >> 16, ((high-1) >> 16)+1):
        pattern = re.compile(rb'(?=(..' + re.escape(struct.pack('<H', upper)) + rb'))', re.S)
        for match in pattern.finditer(data):
            value = struct.unpack('<I', match.group(1))[0]
            if low <= value < high:
                result.append(dict(offset=hex(match.start()), value=hex(value)))
    return result


def branch_candidates(data, mapping, ranges):
    results = [[] for _ in ranges]
    for m in re.finditer(rb'[\xc0-\xca\xcc\xcd\xdc\xdd]|\xfa\xff|\xfc\xff', data):
        pos = m.start(); op = data[pos]
        if op <= 0xca:
            width, skip, kind = 1, 1, 'branch8'
        elif op in (0xcc, 0xcd):
            width, skip, kind = 2, 1, 'jmp16' if op == 0xcc else 'call16'
        elif op in (0xdc, 0xdd):
            width, skip, kind = 4, 1, 'jmp32' if op == 0xdc else 'call32'
        else:
            width, skip, kind = (2 if op == 0xfa else 4), 2, 'calls'
        if pos+skip+width > len(data):
            continue
        target = (mapping+pos+int.from_bytes(data[pos+skip:pos+skip+width], 'little', signed=True)) & 0xffffffff
        for i, (low, high) in enumerate(ranges):
            if low <= target < high:
                results[i].append(dict(site=hex(mapping+pos), target=hex(target), encoding=kind,
                    source_hex=data[max(0,pos-16):pos+16].hex(),
                    qualification='Raw encoding match; source may be data or misaligned.'))
    return results


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True, type=Path)
    args = p.parse_args(); args.out.mkdir(parents=True, exist_ok=False)
    b = firmware()
    older_path = ROOT/'analysis/preset_startup_final/penf3100.main.bin'
    older = older_path.read_bytes()
    assert sha(older) == '3d5963c6d9385aafc99ff51892ec706bef1c4783a84f586179271a64b8401bfd'
    sections = json.loads((ROOT/'analysis/preset_startup_final/audit.json').read_text())['startup_sections']
    blocks = parse((ROOT/'firmware_files/OLY_E_122_3101_0000_0000.BIN').read_bytes())
    rows = []
    for section in sections:
        low, high = int(section['destination'],16), int(section['end_exclusive'],16)
        data = b[low-BASE:high-BASE]
        count = len(data)-len(data.rstrip(b'\xff'))
        if count < 256:
            continue
        start = high-count
        # Preserve >=64 bytes at both boundaries, then align to 16 bytes.
        inner_low, inner_high = (start+64+15)&~15, (high-64)&~15
        flash_start = int(section['flash_source'],16)+inner_low-low
        row = dict(section=section['id'], padding_start=hex(start), end_exclusive=hex(high),
            raw_bytes=count, proposed_start=hex(inner_low), proposed_end_exclusive=hex(inner_high),
            proposed_bytes=inner_high-inner_low,
            preserved_prefix_bytes=inner_low-start, preserved_suffix_bytes=high-inner_high,
            logical_flash_start=hex(flash_start),
            identical_padding_in_3100=older[start-BASE:high-BASE] == b[start-BASE:high-BASE],
            same_descriptor_in_3100=older[int(section['descriptor'],16)-BASE:int(section['descriptor'],16)-BASE+12] ==
                b[int(section['descriptor'],16)-BASE:int(section['descriptor'],16)-BASE+12],
            literal_reference_candidates=[])
        for alias, address in [('runtime',inner_low), ('runtime_uncached',inner_low+0x40000000),
                               ('logical_flash',flash_start), ('flash_alias',flash_start+0x40000000)]:
            for block in blocks:
                hits = pointer_candidates(block.payload, address, address+inner_high-inner_low)
                row['literal_reference_candidates'].extend(dict(component=hex(block.kind), alias=alias, **hit) for hit in hits)
        rows.append(row)
    ranges = [(int(r['proposed_start'],16), int(r['proposed_end_exclusive'],16)) for r in rows]
    direct = branch_candidates(b, BASE, ranges)
    relocated = branch_candidates(b[0x113c9e0:0x113c9e0+0x1800], 0x47000800, ranges)
    for row, hits, extra in zip(rows, direct, relocated):
        row['relative_transfer_candidates'] = hits+extra
        row['proven_unused'] = False
    # Known startup clear ranges from actual main operands and allocator
    # configuration, not assumptions about the entire flat FF tail.
    reserved = [
        ('small initialized globals',0x61170fe0,0x61171628),
        ('relocated library source',BASE+0x113c9e0,BASE+0x113c9e0+0x1800),
        ('small object pool',0x61173fc0,0x61221fc0),
        ('startup pointer initializers',0x615fc540,0x615fc540+0x20a20),
        ('startup clear 1',0x6168b900,0x616fd314),
        ('startup clear 2',0x61bc2a40,0x61ca8d08),
    ]
    for cpu, config in enumerate((0x600414c4,0x60041650,0x600417dc)):
        arena, size = struct.unpack_from('<II',b,config-BASE+0x2c)
        reserved.append((f'CPU{cpu} kernel object arena',arena,arena+size))
    for row, (low, high) in zip(rows,ranges):
        row['known_reserved_overlaps'] = [name for name,a,z in reserved if low<z and a<high]
        print('section', row['section'], row['proposed_start'],row['proposed_bytes'],
              'literal candidates',len(row['literal_reference_candidates']),
              'relative candidates',len(row['relative_transfer_candidates']),flush=True)
    report = dict(main_sha256=sha(b), older_main_sha256=sha(older), candidates=rows,
        total_proposed_bytes=sum(r['proposed_bytes'] for r in rows),
        known_reserved_ranges=[dict(name=n,start=hex(a),end_exclusive=hex(z)) for n,a,z in reserved],
        preferred_for_COLOR=3, alternate_for_more_space=8,
        preference_reason='Section 3 is the COLOR code/data load itself, avoiding a dependency on another section being ready. Section 8 offers the largest individual loaded suffix, but loads later.',
        limits=['Not a whole-program pointer/range proof. Computed accesses, DMA destinations, undocumented aliases and later runtime states may be missed.',
                'Literal scan covers all four decoded update components and four reviewed address representations, at every byte alignment.',
                'Relative-transfer scan covers all main bytes and the known relocated helper. Raw candidates need instruction/data classification.',
                'No assumptions about immutable ROM, boot signature policy or independent recovery.',
                'Boundary margins protect the existing first/last padding bytes; they are a design precaution, not a proved safety radius.'],
        source_sha256=sha(Path(__file__).read_bytes()))
    (args.out/'audit.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__ == '__main__':
    main()
