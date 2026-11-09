#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Read-only OM-5 / E-M1 II / E-M1 III / E-M5 III burst comparison.

Pins archived stock containers, extracts six rate descriptors per camera and
executes only a bounded queue-limit arithmetic fragment on two models. Does
not patch firmware, model sensor timing, allocate camera buffers or access USB.
Run from the workspace root with a fresh --out directory.
"""
import argparse
import json
from pathlib import Path
import struct
import tempfile

from oly_container import parse, sha256
from penf_disasm import DEFAULT_OBJDUMP, window
from penf_emulator import BASE, ENGINE, Region
from penf_probe import BUFFER, ProbeState


PINS = Path('research/om5_burst/source-pins.json')
MODES = ('mechanical_l', 'mechanical_h', 'silent_l', 'silent_h',
         'pro_capture_l', 'pro_capture_h')
# Descriptor starts, not pointers into machine instructions.
DESCRIPTORS = {
    'om5': [0x6050c3d4, 0x6050c3e8, 0x6050e2ec, 0x6050e300,
            0x6050f73c, 0x6050f750],
    'em1iii': [0x604dc594, 0x604dc5a8, 0x604de4ac, 0x604de4c0,
               0x604df8fc, 0x604df910],
    'em1ii': [0x604f03d0, 0x604f03e4, 0x604f22d4, 0x604f22e8,
              0x604f374c, 0x604f3760],
    'em5iii': [0x604d6c44, 0x604d6c58, 0x604d8b0c, 0x604d8b20,
               0x604d9f34, 0x604d9f48],
}
FAST = [list(range(10, 101, 10)), list(range(100, 151, 10)),
        list(range(10, 101, 10))+[150, 180], [150, 200, 300, 600],
        [100, 150, 180], [150, 200, 300, 600]]
SLOW = [list(range(10, 61, 10)), list(range(50, 101, 10)),
        list(range(10, 101, 10)), [150, 200, 300], [100], [150, 200, 300]]
WINDOWS = {
    'om5': {
        'buffer-configuration-branches': (0x602b8c95, 0x602b8d00),
        'buffer-trim-and-enqueue': (0x602b8da7, 0x602b8e86),
        'typed-parameter-wrapper': (0x602bc39b, 0x602bc3d2),
        'parameter-getter': (0x6005fa8d, 0x6005faaf),
        'parameter-descriptor-lookup': (0x6005ea40, 0x6005eaa3),
        'typed-parameter-read': (0x60060131, 0x60060179),
        'buffer-diagnostics': (0x602b9152, 0x602b91a2),
    },
    'em1iii': {
        'buffer-configuration': (0x602b39f6, 0x602b3a9b),
        'buffer-trim-and-enqueue': (0x602b3b3e, 0x602b3c1d),
        'buffer-diagnostics': (0x602b3ee9, 0x602b3f39),
    },
}
CLAMP = {
    'om5': (0x602b8dc3, 0x602b8df3, 0x620cfe02),
    'em1iii': (0x602b3b5a, 0x602b3b8a, 0x6210f376),
}


def cstring(data):
    return data.split(b'\0')[0].decode('ascii')


def rate_tables(data, model):
    rows = []
    expected = FAST if model in ('em1ii', 'em1iii') else SLOW
    for mode, address, want in zip(MODES, DESCRIPTORS[model], expected):
        key, flags, pointer, zero, size, stride, tail = struct.unpack_from(
            '<HHIIHHI', data, address-BASE)
        assert (flags, zero, stride, tail) == (128, 0, 2, 0x500)
        assert BASE <= pointer < pointer+size <= BASE+len(data)
        values = list(struct.unpack_from('<'+'H'*(size//2), data, pointer-BASE))
        assert values == want, (model, mode, values)
        rows.append(dict(mode=mode, descriptor=hex(address), key=key,
                         array=hex(pointer), bytes=size, values_tenths_fps=values,
                         fps=[v/10 for v in values],
                         following_8_bytes=data[pointer-BASE+size:pointer-BASE+size+8].hex()))
    return rows


def resource_evidence(data, model, tables):
    # Newer models store the names as a distinct array. This is not the older
    # 72-byte settings-backup schema. Do not interpret the rest speculatively.
    if model in ('om5', 'em1iii'):
        start = {'om5': 0x1c403f0, 'em1iii': 0x20403f0}[model]
        name = lambda key: cstring(data[start+key*52:start+(key+1)*52])
        assert name(0) == 'MODE_DRIVE' and name(111) == 'MODE_COLORTONE'
        names = {row['key']: name(row['key']) for row in tables}
        first = tables[-2]['key']-1
        names.update({key: name(key) for key in range(first, first+9)})
        assert names[tables[-1]['key']] == 'MODE_ZERO_TIME_LAG_SPEED_HIGH'
        return dict(kind='fixed_width_names', start=hex(start), names=names)

    start = {'em1ii': 0x1e803e0, 'em5iii': 0x1ec03e0}[model]
    raw = data[start:]
    count, offset, nenum, enum_offset, nflags, flag_offset, unknown = struct.unpack_from('<7I', raw)
    assert offset == 32 and count in (1337, 1301)
    rows = []
    for i in range(count):
        p = offset+72*i
        key, kind = struct.unpack_from('<HB', raw, p)
        name = cstring(raw[p+4:p+56])
        if not ('CONTINUE_TAKE_SPEED' in name or 'ZERO_TIME_LAG' in name):
            continue
        enum_start, enum_count = struct.unpack_from('<IH', raw, p+56)
        values = []
        if kind == 1:
            for j in range(enum_count):
                q = enum_offset+enum_start+j*56
                values.append(dict(value=struct.unpack_from('<i', raw, q)[0],
                                   name=cstring(raw[q+4:q+56])))
        rows.append(dict(id=key, kind=kind, name=name, values=values))
    h = next(r for r in rows if r['name'] == 'MODE_ZERO_TIME_LAG_SPEED_HIGH')
    assert [r['value'] for r in h['values']] == [150, 200, 300, 600]
    return dict(kind='serialized_settings_schema', start=hex(start), rows=rows,
                caution='Schema enum membership does not establish current camera availability; E-M5 III is a counterexample.')


def clamp_cases(data, model):
    start, stop, limit_address = CLAMP[model]
    results = []
    # Queue count and helper return are synthetic register inputs. The caller
    # object field +18 and configured limit are also explicit synthetic data.
    # Stop BEFORE queue access. No queue implementation or allocation is modeled.
    for queued, extra, configured, object_limit in (
            (0, 0, 14, 99), (2, 1, 14, 99), (40, 1, 14, 99),
            (40, 1, 35, 99), (40, 1, 35, 18), (40, 1, 35, 0),
            (40, 1, 0, 99), (35, 1, 35, 36)):
        package = bytearray(32)
        struct.pack_into('<H', package, 18, object_limit)
        s = ProbeState(start, 0, 0, package, dict(d0=queued, d2=extra, a2=BUFFER))
        s.regions = [Region('comparison_main', BASE, data, 'rx') if r.name == 'main' else r
                     for r in s.regions]
        s.ram('configured_buffering_limit', limit_address,
              struct.pack('<H', configured))
        result = s.run([stop], limit=100)
        assert result['status'] == 'breakpoint' and s.regs['pc'] == stop, result
        expected = min(queued+extra, configured+1, object_limit)
        assert s.regs['d2'] == expected, (model, s.regs, expected)
        results.append(dict(queued=queued, helper_return=extra,
                            configured_limit=configured, object_field_18=object_limit,
                            target=s.regs['d2'], instructions=s.steps,
                            stop=hex(stop), trace=result.get('trace')))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    pins = json.loads(PINS.read_text())
    report = dict(scope='Static rate descriptors and bounded native arithmetic only',
                  hardware_timing_tested=False, models={},
                  source_hashes={str(p): sha256(p.read_bytes()) for p in (
                      Path(__file__), PINS, Path('tools/oly_container.py'),
                      Path('tools/penf_disasm.py'), Path('tools/penf_probe.py'),
                      Path('tools/penf_boot_emulator.py'), Path('tools/penf_emulator.py'),
                      DEFAULT_OBJDUMP, ENGINE)})
    with tempfile.TemporaryDirectory(prefix='om5-burst-audit-') as temp:
        for model, pin in pins.items():
            encoded = Path(pin['source']).read_bytes()
            assert sha256(encoded) == pin['source_sha256'], model
            blocks = parse(encoded)  # Rejects malformed components and bad checksums.
            main_block = next(b for b in blocks if b.kind == 0x100)
            common = next(b for b in blocks if b.kind == 0x106)
            data = main_block.payload
            assert sha256(data) == pin['main_sha256'], model
            rows = rate_tables(data, model)
            image = Path(temp)/f'{model}.main.bin'
            image.write_bytes(data)
            record = dict(source=pin, components=[b.metadata() for b in blocks],
                          rates=rows, resource=resource_evidence(common.payload, model, rows))
            record['windows'] = []
            for label, (start, end) in WINDOWS.get(model, {}).items():
                filename = f'{model}-{label}.asm'
                (args.out/filename).write_text(window(data, image, DEFAULT_OBJDUMP, start, end))
                record['windows'].append(dict(file=filename, start=hex(start), end=hex(end),
                    bytes_sha256=sha256(data[start-BASE:end-BASE])))
            if model in CLAMP:
                record['native_clamp'] = clamp_cases(data, model)
            report['models'][model] = record
    (args.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print('Verified 24 rate descriptors, four resource comparisons and 16 native clamp cases.')
    print('No firmware patched or camera accessed. Sensor timing and available buffers remain untested.')


if __name__ == '__main__':
    main()
