#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Make same-size PEN-F ORF metadata controls without rewriting image data.

These test whether development honors the existing COLOR saturation metadata.
They do NOT enable hue/lightness or invent unsupported HSL tags. Only existing
PictureMode and ColorProfileSettings values are changed, in copied files.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2,
         9: 4, 10: 8, 11: 4, 12: 8, 13: 4}


def digest(data):
    return hashlib.sha256(data).hexdigest()


class ORF:
    def __init__(self, data):
        self.data = data
        if data[:4] not in (b'IIRO', b'IIRS'):
            raise ValueError('requires a little-endian Olympus ORF')
        self.ifd0 = self.ifd(self.u32(4), 0)
        if self.value(self.ifd0[0x110]).rstrip(b'\0 ') != b'PEN-F':
            raise ValueError('requires Model PEN-F')
        exif = self.ifd(self.ints(self.ifd0[0x8769])[0], 0)
        maker = exif[0x927c]
        self.maker_base = maker['offset']
        if self.value(maker)[:12] != b'OLYMPUS\0II\x03\0':
            raise ValueError('unexpected Olympus MakerNote header')
        self.maker = self.ifd(self.maker_base + 12, self.maker_base)
        self.camera = self.ifd(self.maker_base + self.ints(self.maker[0x2020])[0], self.maker_base)
        self.picture = self.camera[0x520]
        self.color = self.camera[0x539]
        if (self.picture['type'], self.picture['count']) != (3, 2):
            raise ValueError('unexpected PictureMode type/count')
        if (self.color['type'], self.color['count']) != (8, 14):
            raise ValueError('unexpected ColorProfileSettings type/count')
        self.color_values = self.ints(self.color)
        if self.color_values[:2] != [-5, 5]:
            raise ValueError('unexpected saturation limits')
        starts, lengths = self.ints(self.ifd0[0x111]), self.ints(self.ifd0[0x117])
        if len(starts) != len(lengths) or not starts:
            raise ValueError('unexpected RAW strip layout')
        self.strips = []
        for offset, length in zip(starts, lengths):
            self.read(offset, length)
            if not length:
                raise ValueError('empty RAW strip')
            self.strips.append((offset, length))
        for entry in (self.picture, self.color):
            a, b = entry['offset'], entry['offset'] + entry['bytes']
            if any(a < start + count and b > start for start, count in self.strips):
                raise ValueError('metadata overlaps RAW strip')

    def read(self, offset, length):
        if offset < 0 or length < 0 or offset + length > len(self.data):
            raise ValueError('offset outside ORF')
        return self.data[offset:offset + length]

    def u32(self, offset):
        return struct.unpack('<I', self.read(offset, 4))[0]

    def ifd(self, offset, base):
        count = struct.unpack('<H', self.read(offset, 2))[0]
        if count > 4096:
            raise ValueError('implausible IFD count')
        self.read(offset, 2 + 12 * count + 4)
        entries = {}
        for i in range(count):
            at = offset + 2 + 12 * i
            tag, kind, number, pointer = struct.unpack('<HHII', self.read(at, 12))
            if kind not in SIZES or tag in entries:
                raise ValueError('unsupported type or duplicate tag')
            size = SIZES[kind] * number
            where = at + 8 if size <= 4 else base + pointer
            self.read(where, size)
            entries[tag] = {'tag': hex(tag), 'type': kind, 'count': number,
                            'entry_offset': at, 'offset': where, 'bytes': size}
        return entries

    def value(self, entry):
        return self.read(entry['offset'], entry['bytes'])

    def ints(self, entry):
        formats = {3: 'H', 4: 'I', 8: 'h', 9: 'i', 13: 'I'}
        if entry['type'] not in formats:
            raise ValueError('expected integer field')
        return list(struct.unpack('<' + formats[entry['type']] * entry['count'], self.value(entry)))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        ap.error('output directory must be new')
    source = args.source.read_bytes()
    layout = ORF(source)
    report = {
        'purpose': 'SATURATION METADATA CONTROLS ONLY; no hue/lightness implementation',
        'source': str(args.source), 'source_sha256': digest(source), 'source_bytes': len(source),
        'source_picture_mode': layout.ints(layout.picture),
        'source_color_profile_settings': layout.color_values,
        'picture_mode_entry': layout.picture, 'color_profile_entry': layout.color,
        'red_sector_index_in_exif': 3, 'red_element_in_14_value_tag': 5,
        'raw_strips': [{'offset': offset, 'bytes': length,
                        'sha256': digest(source[offset:offset+length])} for offset, length in layout.strips],
        'camera_tested': False, 'cases': [],
        'limits': [
            'RAW Data Edit Current is documented to use current camera settings; it may ignore these edits.',
            'Custom1/2 also use stored camera settings in the traced firmware path.',
            'No HSL arrays or unknown processing blocks are modified.',
            'Embedded previews remain byte-identical and therefore do not display the changed recipe.',
            'Other metadata and private blocks may also encode settings; camera acceptance is untested.',
        ],
    }
    args.out.mkdir(parents=True)
    for name, red in [('original', None), ('color1-neutral', 0),
                      ('color1-red-plus5', 5), ('color1-red-minus5', -5)]:
        data = bytearray(source)
        allowed = set()
        if red is not None:
            offset = layout.picture['offset']
            struct.pack_into('<H', data, offset, 9)  # Exif COLOR profile 1
            allowed.update(range(offset, offset + 2))
            values = [-5, 5] + [0] * 12
            values[5] = red
            offset = layout.color['offset']
            struct.pack_into('<14h', data, offset, *values)
            allowed.update(range(offset, offset + 28))
        changes = [i for i, (a, b) in enumerate(zip(source, data)) if a != b]
        if len(data) != len(source) or not set(changes) <= allowed:
            raise ValueError('unintended file changes')
        checked = ORF(bytes(data))
        if checked.strips != layout.strips or any(
                source[o:o+n] != data[o:o+n] for o, n in layout.strips):
            raise ValueError('RAW data was changed')
        folder = args.out / name
        folder.mkdir()
        target = folder / args.source.name
        target.write_bytes(data)
        report['cases'].append({
            'file': str(target.relative_to(args.out)), 'sha256': digest(data),
            'picture_mode': checked.ints(checked.picture),
            'color_profile_settings': checked.ints(checked.color),
            'changed_bytes': [{'offset': hex(i), 'before': source[i], 'after': data[i]} for i in changes],
            'raw_strips_byte_identical': True, 'all_other_bytes_unchanged': True,
        })
    if digest(args.source.read_bytes()) != report['source_sha256']:
        raise ValueError('source changed during operation')
    (args.out / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'output': str(args.out), 'source_unchanged': True,
                      'raw_data_unchanged_in_all_four_copies': True,
                      'hue_lightness_modified': False}, indent=2))


if __name__ == '__main__':
    main()
