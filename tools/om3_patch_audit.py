#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Independently audit the supplied OM-3 V22 manifest, without executing its code.

Reads stock firmware and JSON only. Reconstructs encoded/decoded release hashes
in memory, exports a decoded main component for disassembly, and never writes
an installable update package. Run from the workspace root.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from oly_container import Block, encode, parse, replace_payload, sha256, sum32


BASE = 0x60021020
STOCK_SHA = '8c133084414533159f587bf46bfb4152714c4074312a47c8d8503e33d605696d'
MANIFEST_SHA = '8f520edb97995c7b5de3b43da725b33bff9a5f1ddb52d31d439a01609369505e'
DEFAULT_MANIFEST = Path('research/om3_patcher_20260929/extracted/OM-3 patcher/patches/om3_pc_remote_v22.json')
DEFAULT_STOCK = Path('firmware_archive/reference/OM-3/1.1/OLY_E_147_1100_0000_0000.BIN')
OBJDUMP = Path('toolchains/binutils-2.45-build/binutils/objdump')


def require(value, message):
    if not value:
        raise ValueError(message)


def spans(offsets):
    result = []
    for offset in offsets:
        if result and offset == result[-1][1]:
            result[-1][1] += 1
        else:
            result.append([offset, offset + 1])
    return [{'start': hex(a), 'end_exclusive': hex(b), 'bytes': b-a} for a, b in result]


def disassemble(image, start, end):
    return subprocess.check_output([
        str(OBJDUMP.resolve()), '-b', 'binary', '-m', 'mn10300', '-D', '-z',
        '--insn-width=16', f'--adjust-vma={BASE:#x}',
        f'--start-address={start:#x}', f'--stop-address={end:#x}', str(image)
    ], text=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument('--stock', type=Path, default=DEFAULT_STOCK)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    require(not args.out.exists(), 'Use a new output directory')
    manifest_bytes = args.manifest.read_bytes()
    require(sha256(manifest_bytes) == MANIFEST_SHA, 'Unexpected manifest')
    manifest = json.loads(manifest_bytes)
    original = args.stock.read_bytes()
    require(sha256(original) == STOCK_SHA == manifest['original_sha256'], 'Unexpected stock')
    blocks = parse(original)
    edits = sorted(manifest['patches'], key=lambda p: int(p['offset'], 16))
    patched = {b.index: bytearray(b.payload) for b in blocks}
    rows, last_end = [], 0
    for patch in edits:
        offset = int(patch['offset'], 16)
        before, after = (bytes.fromhex(patch[k]) for k in ('expected', 'replacement'))
        require(before and len(before) == len(after), 'Invalid edit length')
        require(offset >= last_end, 'Overlapping edits')
        last_end = offset + len(before)
        owners = [b for b in blocks if b.offset+32 <= offset and last_end <= b.offset+32+len(b.payload)]
        require(len(owners) == 1, 'Edit outside one component payload')
        block, = owners
        local = offset-block.offset-32
        require(block.payload[local:local+len(before)] == before, f"Guard mismatch: {patch['name']}")
        patched[block.index][local:local+len(before)] = after
        changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
        row = dict(name=patch['name'], decoded_container_offset=hex(offset),
                   component_index=block.index, component_kind=hex(block.kind),
                   payload_offset=hex(local), bytes_guarded=len(before), bytes_changed=len(changed),
                   expected_all_ff=all(v == 255 for v in before),
                   expected=before.hex(), replacement=after.hex(),
                   changed_ranges=spans([offset+i for i in changed]))
        if block.index == 0:
            row['analysis_address'] = hex(BASE+local)
            if before[0] in (0xcc, 0xcd, 0xdc, 0xdd) and len(before) >= (3 if before[0] in (0xcc, 0xcd) else 5):
                n = 2 if before[0] in (0xcc, 0xcd) else 4
                row['original_initial_relative_target'] = hex(BASE+local+int.from_bytes(before[1:1+n], 'little', signed=True))
            if after[0] in (0xcc, 0xcd, 0xdc, 0xdd) and len(after) >= (3 if after[0] in (0xcc, 0xcd) else 5):
                n = 2 if after[0] in (0xcc, 0xcd) else 4
                row['patched_initial_relative_target'] = hex(BASE+local+int.from_bytes(after[1:1+n], 'little', signed=True))
        rows.append(row)

    encoded_hash, decoded_hash, repaired_decoded_hash = (hashlib.sha256() for _ in range(3))
    components = []
    for block in blocks:
        payload = bytes(patched[block.index])
        rebuilt = replace_payload(block, payload)
        encoded = encode(payload)
        stock_encoded = original[block.offset+32:block.offset+32+len(payload)]
        encoded_changed = sum(a != b for a, b in zip(encoded, stock_encoded)) if payload != block.payload else 0
        trailer_changed = sum(a != b for a, b in zip(rebuilt.trailer, block.trailer))
        for chunk in (block.header, encoded, rebuilt.trailer):
            encoded_hash.update(chunk)
        # The supplied builder leaves ORIGINAL checksum words in decoded output.
        for chunk in (block.header, payload, block.trailer):
            decoded_hash.update(chunk)
        for chunk in (block.header, payload, rebuilt.trailer):
            repaired_decoded_hash.update(chunk)
        require((sum32(rebuilt.header)+sum32(payload)+sum32(rebuilt.trailer)) & 0xffffffff == 0,
                'Independent rebuilt checksum failed')
        require(parse(rebuilt.header+encoded+rebuilt.trailer)[0].payload == payload,
                'Independent final decode failed')
        require(encode(block.payload) == stock_encoded, 'Stock codec roundtrip failed')
        components.append(dict(index=block.index, kind=hex(block.kind),
                               payload_size=len(payload),
                               stock_payload_sha256=sha256(block.payload),
                               patched_payload_sha256=sha256(payload),
                               payload_changed=payload != block.payload,
                               encoded_payload_changed_bytes=encoded_changed,
                               trailer_changed_bytes=trailer_changed,
                               header_identical=block.header == rebuilt.header,
                               trailer_metadata_identical=block.trailer[:28] == rebuilt.trailer[:28],
                               old_checksum=hex(struct.unpack_from('<I', block.trailer, 28)[0]),
                               new_checksum=hex(struct.unpack_from('<I', rebuilt.trailer, 28)[0]),
                               final_checksum_valid=True))
    require(encoded_hash.hexdigest() == manifest['encoded_sha256'], 'Encoded release hash mismatch')
    require(decoded_hash.hexdigest() == manifest['decoded_sha256'], 'Decoded release hash mismatch')

    # Merge adjacent injected ranges into physical regions, preserving FF holes.
    caves = []
    for row in rows:
        if not row['expected_all_ff']:
            continue
        start = int(row['analysis_address'], 16); end = start+row['bytes_guarded']
        if caves and caves[-1]['end'] == start:
            caves[-1]['end'] = end
            caves[-1]['patches'].append(row['name'])
            caves[-1]['changed_bytes'] += row['bytes_changed']
        else:
            caves.append(dict(start=start, end=end, patches=[row['name']], changed_bytes=row['bytes_changed']))
    for cave in caves:
        cave['span_bytes'] = cave['end']-cave['start']
        cave['start'], cave['end_exclusive'] = hex(cave['start']), hex(cave.pop('end'))

    args.out.mkdir(parents=True)
    patched_main = args.out/'patched-main-analysis-only.bin'
    patched_main.write_bytes(patched[0])
    stock_main = Path('analysis/om3_1100/00_0100_50000020.decoded.bin')
    require(stock_main.read_bytes() == blocks[0].payload, 'Canonical decoded main differs')
    asm_dir = args.out/'assembly'; asm_dir.mkdir()
    operands = {'control_uses_existing_tpc_transport', 'vendor_dispatch_table', 'vendor_dispatch_count',
                'device_info_operation_count','device_info_operation_list','control_property_usb_enable_event',
                'control_property_usb_disable_event','native_operation_list','native_operation_count',
                'native_event_list','native_event_count','device_info_event_count','device_info_event_list'}
    for row in rows:
        if row['name'] in operands:
            continue
        start = int(row['analysis_address'], 16); end = start+row['bytes_guarded']
        for suffix, path in [('stock',stock_main),('patched',patched_main)]:
            (asm_dir/f"{row['name']}.{suffix}.asm").write_text(disassemble(path,start,end))
    report = dict(source=str(args.stock), source_sha256=STOCK_SHA,
                  manifest=str(args.manifest), manifest_sha256=MANIFEST_SHA,
                  tool_sha256=sha256(Path(__file__).read_bytes()),
                  main_analysis_base=hex(BASE),
                  offset_convention='Manifest offsets are decoded CONTAINER offsets, including 32-byte component headers.',
                  scope='Independent packaging/hash and static edit audit only; no supplied Python executed, camera accessed, or installable package saved.',
                  patches=rows, components=components, injected_regions=caves,
                  patch_records=len(rows), guarded_bytes=sum(r['bytes_guarded'] for r in rows),
                  decoded_bytes_changed=sum(r['bytes_changed'] for r in rows),
                  injected_bytes_changed=sum(r['bytes_changed'] for r in rows if r['expected_all_ff']),
                  existing_bytes_changed=sum(r['bytes_changed'] for r in rows if not r['expected_all_ff']),
                  encoded_bytes_changed=sum(c['encoded_payload_changed_bytes']+c['trailer_changed_bytes'] for c in components),
                  encoded_sha256=encoded_hash.hexdigest(), encoded_matches_manifest=True,
                  decoded_sha256=decoded_hash.hexdigest(), decoded_matches_manifest=True,
                  decoded_with_repaired_checksums_sha256=repaired_decoded_hash.hexdigest(),
                  decoded_checksum_note='Author decoded output retains stock checksum trailers; encoded update repairs checksums correctly.',
                  disassembly_caveat='Exact edit starts; operand-only records omitted. Cave blobs mix code, data and FF padding; linear decoding alone does not establish reachable instructions.')
    (args.out/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
    cols=['name','decoded_container_offset','analysis_address','bytes_guarded','bytes_changed','expected_all_ff']
    (args.out/'edits.tsv').write_text('\t'.join(cols)+'\n'+'\n'.join('\t'.join(str(r[c]) for c in cols) for r in rows)+'\n')
    print(json.dumps({k:report[k] for k in ['patch_records','guarded_bytes','decoded_bytes_changed','injected_bytes_changed','existing_bytes_changed','encoded_bytes_changed','injected_regions','encoded_matches_manifest','decoded_matches_manifest']},indent=2))


if __name__ == '__main__':
    main()
