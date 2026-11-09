#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Pinned, offline COLOR preset comparison. Does not modify firmware or a camera.

Checks native per-profile settings reads against the default arrays, exports
aligned disassembly, and cross-checks OM-3 setting names in resource 0106.
This is static analysis, not execution of reset, capture, or the ISP.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import struct

from compare_color_generations import MODELS, ROOT, TABLE_BYTES, TABLE_SHA, export_window


PROFILES = {
    'PEN-F': dict(defaults=0x603c8bb0, saturation=[931, 943, 955],
                  contrast=[916, 917, 918], sharpness=[913, 914, 915],
                  shading=[1111, 1112, 1113], tone=[967, 970, 973]),
    'E-P7': dict(defaults=0x604a8774, saturation=[927, 939, 951, 1655],
                 contrast=[912, 913, 914, 1653], sharpness=[909, 910, 911, 1651],
                 shading=[1667, 1668, 1669, 1670], tone=[963, 966, 969, 1672],
                 dispatch_table=0x60460458, getter=0x602b2237,
                 dispatch=(0x602b7b71, 0x602b7bf2),
                 accessors=(0x602ba4bd, 0x602ba4cc),
                 starts=[0x602b814e, 0x602b823c, 0x602b832a, 0x602b8418],
                 end=0x602b850d),
    'OM-3': dict(defaults=0x605f6d90, saturation=[928, 940, 952, 964],
                 contrast=[908, 909, 910, 911], sharpness=[904, 905, 906, 907],
                 shading=[912, 913, 914, 915], tone=[976, 979, 982, 985],
                 dispatch_table=0x605e0350, getter=0x603f34ec,
                 dispatch=(0x604032a4, 0x60403328),
                 accessors=(0x60405804, 0x60405813),
                 starts=[0x604037f9, 0x6040391a, 0x60403a3b, 0x60403b5c],
                 end=0x60403c86),
}
SATURATION = [
    [0]*12,
    [1, 1, 0, 0, 0, 0, 1, 1, 0, 0, 1, 1],
    [4, 4, 4, 4, 4, 3, 4, 4, 4, 4, 4, 4],
    [-4, 0, 0, 0, -1, -1, -1, 0, 0, 0, 0, -4],
]
TONE = [[0, 0, 0], [3, 0, -3], [4, 0, -4], [-3, 0, 3]]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    objdump = ROOT/'toolchains/binutils-2.45-build/binutils/objdump'
    result = dict(scope='Static source/default/dispatch checks; no hardware execution',
                  script_sha256=sha(Path(__file__).read_bytes()), models={})
    csv_rows = []
    for name, cfg in MODELS.items():
        data = (ROOT/cfg['main']).read_bytes()
        require(sha(data) == cfg['main_sha'], f'{name}: main hash')
        table = data[cfg['table']-cfg['base']:cfg['table']-cfg['base']+TABLE_BYTES]
        require(sha(table) == TABLE_SHA, f'{name}: processing table')
        layout = PROFILES[name]
        read = lambda key, count=1: list(struct.unpack_from(
            '<'+'i'*count, data, layout['defaults']-cfg['base']+key*4))
        record = dict(build=cfg['build'], main=cfg['main'], main_sha256=sha(data),
                      defaults_address=hex(layout['defaults']),
                      color_table_sha256=sha(table), profiles=[], windows=[])
        if name != 'PEN-F':
            for label in ('dispatch', 'accessors'):
                record['windows'].append(export_window(
                    name, label, layout[label], cfg, data, args.out, objdump))
            a, z = layout['accessors']
            # mov default_table,a0; retf; mov count,d0; retf
            require(data[a-cfg['base']:a-cfg['base']+6] ==
                    b'\xfc\xdc'+struct.pack('<I', layout['defaults']),
                    f'{name}: default accessor')
            require(data[a-cfg['base']+6:a-cfg['base']+9] == b'\xde\x00\x00',
                    f'{name}: default accessor return')
        if name == 'E-P7':
            record['windows'].append(export_window(
                name, 'cursor_four_profiles', (0x60de83b7, 0x60de857f),
                cfg, data, args.out, objdump))
        for i, first in enumerate(layout['saturation']):
            ids = dict(saturation=list(range(first, first+12)),
                       tone=list(range(layout['tone'][i], layout['tone'][i]+3)),
                       contrast=layout['contrast'][i], sharpness=layout['sharpness'][i],
                       shading=layout['shading'][i])
            values = dict(saturation=read(first, 12), tone_high_mid_low=read(ids['tone'][0], 3),
                          **{k: read(ids[k])[0] for k in ('contrast', 'sharpness', 'shading')})
            require(values['saturation'] == SATURATION[i], f'{name}: COLOR{i+1} saturation')
            require(values['tone_high_mid_low'] == TONE[i], f'{name}: COLOR{i+1} tone')
            require(all(values[k] == 0 for k in ('contrast', 'sharpness', 'shading')),
                    f'{name}: COLOR{i+1} other defaults')
            p = dict(profile=i+1, ids=ids, defaults=values,
                     saturation_address=hex(layout['defaults']+first*4))
            if name != 'PEN-F':
                start = layout['starts'][i]
                end = layout['starts'][i+1] if i < 3 else layout['end']
                public_mode = [54, 55, 56, 64][i]
                target = struct.unpack_from('<I', data,
                    layout['dispatch_table']-cfg['base']+public_mode*4)[0]
                require(target == start, f'{name}: COLOR{i+1} dispatch')
                window = export_window(name, f'color{i+1}_settings', (start, end),
                                       cfg, data, args.out, objdump)
                assembly = (args.out/window['file']).read_text()
                key_order = [int(x) for x in re.findall(r'\bmov\s+(\d+),a0', assembly)]
                expected = [ids['contrast'], ids['sharpness'], *ids['tone'],
                            ids['shading'], *ids['saturation']]
                require(key_order == expected, f'{name}: COLOR{i+1} native setting IDs')
                calls = re.findall(r'\bcall\s+0x([0-9a-f]+),', assembly)
                require(len(calls) == (18 if i == 3 else 17) and
                        all(int(x, 16) == layout['getter'] for x in calls),
                        f'{name}: COLOR{i+1} getter calls')
                # First three arms jump to the common final getter in arm 4.
                p.update(public_picture_mode=public_mode, native_setting_order=key_order,
                         settings_getter=hex(layout['getter']))
                record['windows'].append(window)
            record['profiles'].append(p)
            for field, keys in ids.items():
                keys = keys if isinstance(keys, list) else [keys]
                for j, key in enumerate(keys):
                    csv_rows.append([name, i+1, field, j, key,
                                     hex(layout['defaults']+key*4), read(key)[0]])
        result['models'][name] = record

    # OM-3 names are a separate fixed-width string array, not the PEN-F 72-byte schema.
    resource_path = ROOT/'analysis/om3_1100/02_0106_458c0020.decoded.bin'
    resource = resource_path.read_bytes()
    names_start = 0x28803f0
    name_at = lambda key: resource[names_start+52*key:names_start+52*(key+1)].split(b'\0')[0].decode('ascii')
    require(name_at(0) == 'MODE_DRIVE' and name_at(111) == 'MODE_COLORTONE', 'OM-3 name anchors')
    names = {}
    for p in result['models']['OM-3']['profiles']:
        i, ids = p['profile'], p['ids']
        expected = {
            ids['contrast']: f'MODE_COLOR_CREATOR_2_CONTRAST_SET{i}',
            ids['sharpness']: f'MODE_COLOR_CREATOR_2_SHARP_SET{i}',
            ids['shading']: f'MODE_COLOR_CREATOR_2_SHADING_SET{i}',
        }
        expected.update({k: f'MODE_COLOR_CREATOR_2_VIVID_SET{i}_{j+1}'
                         for j, k in enumerate(ids['saturation'])})
        expected.update({k: f'MODE_COLOR_CREATOR_2_TONE_CONTROL_{band}_SET{i}'
                         for k, band in zip(ids['tone'], ['HIGH', 'MIDDLE', 'LOW'])})
        for key, label in expected.items():
            require(name_at(key) == label, f'OM-3 setting name {key}')
            names[key] = label
    result['om3_names'] = dict(component=str(resource_path.relative_to(ROOT)),
        component_sha256=sha(resource), string_table_offset=hex(names_start), names=names)
    with (args.out/'profile_defaults.csv').open('w') as f:
        writer = csv.writer(f)
        writer.writerow(['model', 'profile', 'field', 'index', 'setting_id', 'address', 'default'])
        writer.writerows(csv_rows)
    (args.out/'comparison.json').write_text(json.dumps(result, indent=2)+'\n')
    (args.out/'soft_tone_recipe.txt').write_text(
        'E-P7 / OM-3 stock COLOR4 core recipe (firmware 1.1)\n'
        'For manual reproduction in an existing PEN-F COLOR profile. No firmware patch.\n'
        'Saturation, index 0..11 (Yellow first):\n'
        '-4, 0, 0, 0, -1, -1, -1, 0, 0, 0, 0, -4\n'
        'Highlights -3; Midtones 0; Shadows +3\n'
        'Contrast 0; Sharpness 0; Shading 0\n'
        'WB, exposure and noise settings are outside this 18-setting profile group.\n'
        'Identical recipe does not establish identical rendered pixels across cameras.\n')
    print('Verified three main hashes, shared COLOR tables, 11 profile defaults,')
    print('eight native profile branches, and 72 OM-3 field names. No firmware modified.')
    print(args.out/'comparison.json')


if __name__ == '__main__':
    main()
