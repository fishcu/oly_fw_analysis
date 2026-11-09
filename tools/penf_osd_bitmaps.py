#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Extract bounded PEN-F 3101 bitmap assets without modifying firmware.

Supports the inferred format-3 byte-palette RLE stream, with six 10-bit
tokens per 64-bit group. Preview grayscale visualizes palette indices;
it does not reproduce the native palette or transparency. Extra bank 69's
runtime mapping remains inferred, not a native resource-loader replay.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct

from PIL import Image

from penf_code_space_reference_audit import resource_rows
from penf_osd_symbols import SOURCE, EXPECTED_SHA, BANK_BASE, BANK_OFFSET, BANK_SIZE


def decode_format3(data, width, height):
    """Return palette indices; reject truncation, overruns and nonzero padding."""
    if len(data) < 4 or data[3] != 3:
        raise ValueError('Unsupported stream header')
    encoded_height = (data[0] | ((data[1] & 3) << 8)) + 1
    encoded_width = ((data[1] >> 4) | ((data[2] & 63) << 4)) + 1
    if (width, height) != (encoded_width, encoded_height):
        raise ValueError('Descriptor/header dimensions disagree')
    pixels = bytearray()
    tokens = 0
    while len(pixels) < width * height:
        group, slot = divmod(tokens, 6)
        offset = 4 + 8 * group
        if offset + (10 * (slot + 1) + 7) // 8 > len(data):
            raise ValueError(f'Truncated stream after {len(pixels)}/{width * height} pixels')
        word = int.from_bytes(data[offset:offset + 8], 'little')
        if word >> 60:
            raise ValueError('Nonzero group padding')
        token = (word >> (10 * slot)) & 1023
        run = (token & 3) + 1
        if len(pixels) + run > width * height:
            raise ValueError('Run crosses declared image end')
        pixels.extend(bytes([token >> 2]) * run)
        tokens += 1
    if word >> (10 * (slot + 1)) or any(data[offset + 8:]):
        raise ValueError('Nonzero trailing padding')
    return bytes(pixels)


class BitmapBank:
    def __init__(self):
        self.data = SOURCE.read_bytes()
        if hashlib.sha256(self.data).hexdigest() != EXPECTED_SHA:
            raise ValueError('Requires the exact decoded PEN-F 3101 OSD component')
        self.rows = {row['index']: row for row in
                     resource_rows(self.data, 0, 0x41800020, len(self.data))}
        assert self.rows[0] == dict(index=0, start=BANK_OFFSET, end=BANK_OFFSET + BANK_SIZE)
        self.table, = struct.unpack('<I', self.read(BANK_BASE + 16, 4))
        symbol_table, = struct.unpack('<I', self.read(BANK_BASE, 4))
        assert self.table == 0xa26abfac and symbol_table == 0xa26b0890
        # Candidate extent ends where the independently verified symbol table starts.
        self.count = (symbol_table - self.table) // 4
        assert self.count == 4665

    def read(self, pointer, size):
        index, base = (0, BANK_BASE) if pointer < 0xa26e6c00 else (69, 0xa26e6c00)
        row = self.rows[index]
        offset = row['start'] + pointer - base
        if size <= 0 or not row['start'] <= offset < offset + size <= row['end']:
            raise ValueError(f'Resource {index} bounds exceeded at {pointer:#x}+{size}')
        return self.data[offset:offset + size]

    def descriptor(self, index):
        if not 1 <= index < self.count:
            raise ValueError('Bitmap ID outside candidate table extent')
        pointer, = struct.unpack('<I', self.read(self.table + 4 * index, 4))
        fields = struct.unpack('<6H3I', self.read(pointer, 24))
        fmt, width, height, field6, u1, u2, size, payload, flags = fields
        return dict(id=index, descriptor=pointer, format=fmt, width=width,
                    height=height, format_field6=field6, unknown_fields=[u1, u2],
                    encoded_bytes=size, payload=payload, flags=flags)

    def decode(self, descriptor):
        if (descriptor['format'], descriptor['format_field6']) != (14, 8):
            raise ValueError('Only descriptor format14/field6=8 is supported')
        data = self.read(descriptor['payload'], descriptor['encoded_bytes'])
        return decode_format3(data, descriptor['width'], descriptor['height'])


def preview(pixels, width, height):
    """Normalize indices for shape inspection only; preserve raw indices separately."""
    largest = max(pixels, default=0) or 1
    return Image.frombytes('L', (width, height), bytes(round(v * 255 / largest) for v in pixels))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--ids', type=int, nargs='+', default=[4222, 2447, 1132, 1125])
    ap.add_argument('--audit', action='store_true', help='Check every candidate format-3 bitmap; report unsupported/failing assets')
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    bank = BitmapBank()
    selected = []
    for index in args.ids:
        row = bank.descriptor(index)
        pixels = bank.decode(row)
        width, height = row['width'], row['height']
        raw = Image.frombytes('L', (width, height), pixels)
        raw.save(args.out / f'indices-{index}.png')
        preview(pixels, width, height).resize((width * 4, height * 4),
            Image.Resampling.NEAREST).save(args.out / f'decoded-{index}.png')
        row.update(palette_indices=sorted(set(pixels)),
                   payload_sha256=hashlib.sha256(bank.read(row['payload'], row['encoded_bytes'])).hexdigest(),
                   gap_before_descriptor=row['descriptor'] - row['payload'] - row['encoded_bytes'])
        selected.append(row)
    report = dict(source=str(SOURCE), source_sha256=EXPECTED_SHA,
                  tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  bitmap_table=hex(bank.table), candidate_table_entries=bank.count,
                  selected=selected,
                  limitations=['Inferred compression; no native rasterizer execution.',
                               'Grayscale previews are not the native palette/transparency.',
                               'Extra resource69 runtime mapping is inferred.',
                               'No display or firmware changes.'])
    if args.audit:
        formats, headers = Counter(), Counter()
        passed, failures = 0, []
        for index in range(1, bank.count):
            row = bank.descriptor(index)
            key = (row['format'], row['format_field6'])
            formats[str(key)] += 1
            if key != (14, 8):
                continue
            header = bank.read(row['payload'], 4)[3]
            headers[str(header)] += 1
            if header != 3:
                continue
            try:
                bank.decode(row)
                passed += 1
            except ValueError as error:
                failures.append(dict(id=index, error=str(error)))
        report['audit'] = dict(formats=formats, stream_headers=headers,
                               format3_passed=passed, failures=failures)
    (args.out / 'bitmap-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(selected=args.ids, audit=report.get('audit'), output=str(args.out))))


if __name__ == '__main__':
    main()
