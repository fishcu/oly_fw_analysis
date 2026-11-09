#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Read-only native comparison of OM-5 / E-M1 III electronic rate consumers.

Runs registered setting APIs, typed getters, mode lookup and the bounded
rate-qualification tail. RAM/settings and the tail's calculated threshold
are explicit fixtures. Does not simulate capture or emit modified firmware.
The sole counterfactual substitutes two rate-list entries in emulator memory.
Run from the workspace root with a fresh --out directory.
"""
import argparse
import json
from pathlib import Path
import struct
import tempfile

from oly_container import parse, sha256
from om5_burst_audit import PINS, rate_tables
from penf_disasm import DEFAULT_OBJDUMP, window
from penf_emulator import BASE, ENGINE, Region
from penf_probe import BUFFER, CALLER, ProbeState


CONFIG = {
    'om5': dict(init=0x602deab6, buckets=0x620d9bbc, count=1439,
                schema=0x6050a2a0, delta=0, mapping=0x60514fec,
                public_mapper=0x602f18d1, cache_flag=0xa25ed128, cache=0xa25eac3c,
                bank=0xa2663dc4, selector=0x602c6468, ceiling=0x602c64b3,
                units=0x602c7068, lookup=0x60160889, lookup_table=0x601f0438,
                candidates=0x601ef148, accessors=0x605ce91f,
                pointers=0x605fb918, tail=(0x60160d09, 0x60160cd2, 0x60160d55),
                callback_table=0x6046d62c, callback_count=327),
    'em1iii': dict(init=0x602dc744, buckets=0x62119a40, count=1422,
                   schema=0x604da438, delta=-0x2355, mapping=0x604e4d90,
                   public_mapper=0x602eeff9, cache_flag=0xa262d0d4, cache=0xa262ac3c,
                   bank=0xa26a3dc4, selector=0x602c0d79, ceiling=0x602c0dc4,
                   units=0x602c18fa, lookup=0x60161cfc, lookup_table=0x601f2140,
                   candidates=0x601f0e50, accessors=0x6059191f,
                   pointers=0x605be918, tail=(0x6016217c, 0x60162145, 0x601621c8),
                   callback_table=0x6046aa94, callback_count=324),
}
TYPED = dict(silent_l=0xf142, silent_h=0xf152,
             pro_capture_l=0x5402, pro_capture_h=0x5412)
SP = 0x18018000
WINDOWS = {
    'om5': {
        'schema-initializer': (0x602deab6, 0x602deb37),
        'schema-consumers': (0x602de225, 0x602de56c),
        'schema-stepping': (0x602de6cc, 0x602de955),
        'callback-initializer': (0x602d1c33, 0x602d1c88),
        'public-to-typed': (0x602f18d1, 0x602f1b21),
        'rate-selector': (0x602c6468, 0x602c64d6),
        'capture-rate-branch': (0x602c6f53, 0x602c7097),
        'rate-qualification': (0x60160c01, 0x60160d58),
        'mode-lookup': (0x60160889, 0x6016091e),
        'record-accessors': (0x605ce91f, 0x605ce947),
        'mode-to-record': (0x60159621, 0x60159675),
        'threshold-wrapper': (0x6014b0b9, 0x6014b100),
        'threshold-calculation': (0x6014918b, 0x60149269),
        'threshold-mode-metadata': (0x60169905, 0x60169931),
        'threshold-flag': (0x6014b23d, 0x6014b25a),
    },
    'em1iii': {
        'schema-initializer': (0x602dc744, 0x602dc7c5),
        'schema-consumers': (0x602dbed0, 0x602dc217),
        'schema-stepping': (0x602dc377, 0x602dc600),
        'callback-initializer': (0x602cc498, 0x602cc4ed),
        'public-to-typed': (0x602eeff9, 0x602ef249),
        'rate-selector': (0x602c0d79, 0x602c0de7),
        'capture-rate-branch': (0x602c17e3, 0x602c1929),
        'rate-qualification': (0x60162074, 0x601621cb),
        'mode-lookup': (0x60161cfc, 0x60161d91),
        'record-accessors': (0x6059191f, 0x60591947),
        'mode-to-record': (0x6015aa94, 0x6015aae8),
    },
}


def state(data):
    s = ProbeState(CALLER, 0, 0, bytes(1024), {})
    s.regions = [Region('main', BASE, data, 'rx') if r.name == 'main' else r
                 for r in s.regions]
    return s


def start_call(s, target, mask, frame, registers=None):
    caller = b'\xdd'+struct.pack('<i', target-CALLER)+bytes((mask, frame))+b'\xcb'
    s.regions = [Region('caller', CALLER, caller, 'rx') if r.name == 'caller' else r
                 for r in s.regions]
    s.regs = dict(pc=CALLER, sp=SP, psw=0, **(registers or {}))


def invoke(s, target, mask, frame, registers=None):
    start_call(s, target, mask, frame, registers)
    r = s.run([CALLER+7], limit=200000)
    assert r['status'] == 'breakpoint' and s.regs['pc'] == CALLER+7, r
    return dict(d0=s.regs['d0'], a0=s.regs.get('a0'), instructions=r['completed'])


def registry_cases(data, c, rates):
    s = state(data)
    s.ram('native_registry', c['buckets'], b'\xa5'*(512+c['count']*8))
    init = invoke(s, c['init'], 0xb0, 12)
    rows = []
    for row in rates:
        key, values = row['key'], row['values_tenths_fps']
        lookup = invoke(s, 0x602de6cc+c['delta'], 0, 4, dict(d0=key))
        assert lookup['a0'] == int(row['descriptor'], 16)
        count = invoke(s, 0x602de4bb+c['delta'], 0x80, 8, dict(d0=key))
        assert count['d0'] == len(values)
        cases = []
        # Valid indices only. The stock getter's out-of-range behavior is
        # not a promise that adjacent ROM data is another selectable entry.
        for index, value in enumerate(values):
            enum = invoke(s, 0x602de526+c['delta'], 0x80, 8, dict(d0=key, d1=index))
            reverse = invoke(s, 0x602de37f+c['delta'], 0x80, 8, dict(d0=key, d1=value))
            assert enum['d0'] == value and reverse['d0'] == index
            steps = []
            for function, direction in ((0x602de225, -1), (0x602de260, 1)):
                s.write(BUFFER, struct.pack('<H', value))
                step = invoke(s, function+c['delta'], 0xa0, 24, dict(d0=key, a0=BUFFER))
                assert step['d0'] == values[(index+direction) % len(values)]
                assert s.read(BUFFER, 2) == struct.pack('<H', value)
                steps.append(step)
            conversions = [invoke(s, function+c['delta'], 0xe0, 16,
                                  dict(d0=key, d1=value))
                           for function in (0x602de30f, 0x602de336)]
            assert all(r['d0'] == value for r in conversions)
            cases.append(dict(value=value, index=index, enum=enum, reverse=reverse,
                              previous_next=steps, conversions=conversions))
        # Public value->index returns zero on a miss; zero also names the
        # first valid entry. Do not present it as a boolean validator.
        find600 = invoke(s, 0x602de37f+c['delta'], 0x80, 8, dict(d0=key, d1=600))
        assert find600['d0'] == (values.index(600) if 600 in values else 0)
        rows.append(dict(mode=row['mode'], lookup=lookup, count=count,
                         cases=cases, index_of_600=find600))
    return dict(initialization=init, rows=rows)


def getter_cases(data, c, rates):
    s = state(data)
    s.register(0x8050, 'r', 0)  # explicit CPU0 address-translation fixture
    s.ram('descriptor_bank', c['bank'], bytes(2))
    s.ram('cache_enabled', c['cache_flag'], b'\1')
    s.ram('empty_public_pointer_cache', c['cache'], bytes(1893*4))
    for i, key in enumerate(TYPED.values()):
        s.ram(f'typed_descriptor_{key:x}', c['bank']+4+(key >> 4)*8,
              struct.pack('<HHI', key, 1, BUFFER+i*8))
    cases = []
    for i, row in enumerate(rates):
        mode, key = row['mode'], row['key']
        typed = struct.unpack_from('<HH', data, c['mapping']-BASE+key*4)
        assert typed == (TYPED[mode], 0)
        mapping = invoke(s, c['public_mapper'], 0xf0, 28, dict(d0=key, a0=BUFFER+512))
        assert mapping['d0'] == typed[0]
        assert s.read(BUFFER+512, 4) == struct.pack('<I', BUFFER+i*8)
        for value in (row['values_tenths_fps'][-1], 600):
            # Distinct values in every other cell check actual branch choice.
            for j in range(4):
                s.write(BUFFER+j*8, struct.pack('<H', value if j == i else 41+j))
            result = invoke(s, c['selector'], 0x80, 8,
                            dict(d0=int(mode.endswith('_h')), d1=1,
                                 a0=int(mode.startswith('pro_'))))
            assert result['d0'] == value
            cases.append(dict(mode=mode, public_key=key, typed_key=hex(typed[0]),
                              native_public_mapping=mapping, fixture_value=value, result=result))
    return cases


def lower_cases(data, c):
    s = state(data)
    ceilings = []
    for high, expected in ((0, 180), (1, 600)):
        result = invoke(s, c['ceiling'], 0, 0, dict(d0=high, d1=1))
        assert result['d0'] == expected
        ceilings.append(dict(high=high, result=result))
    conversions = []
    for value, expected in ((150, 15), (200, 20), (300, 30), (600, 60), (180, 0)):
        result = invoke(s, c['units'], 0, 0, dict(d0=value))
        assert result['d0'] == expected
        conversions.append(dict(tenths=value, result=result))

    lookups = []
    for flag in (0, 1):
        for fps, want in zip((60, 30, 20, 15),
                             (54, 55, 56, 57) if flag == 0 else (58, 58, 59, 59)):
            result = invoke(s, c['lookup'], 0xf0, 32, dict(d0=14, d1=fps, a0=flag))
            assert result['d0'] == want
            records = [invoke(s, c['accessors']+offset, 0, 4, dict(d0=want))
                       for offset in (0, 20)]
            ptrs = [struct.unpack_from('<I', data, c['pointers']-BASE+offset+(want-54)*4)[0]
                    for offset in (0, 48)]
            assert [r['a0'] for r in records] == ptrs
            budget = ((struct.unpack_from('<I', data, ptrs[1]-BASE)[0] & 32767)
                      * struct.unpack_from('<H', data, ptrs[0]-BASE+10)[0])
            lookups.append(dict(flag=flag, fps=fps, result=result, records=records,
                                comparison_budget=budget))

    tails = []
    # This threshold is an OUTPUT of the preceding calculation. It is not
    # asserted to be a real shutter time or observed hardware measurement.
    for flag in (0, 1):
        for request in (15, 20, 30, 60):
            for threshold in (0, 4004, 4005, 8008, 8009, 12012, 12013, 16016, 16017):
                s.regs = dict(pc=c['tail'][flag], sp=SP, psw=0, d3=32767)
                for offset, value in ((4, threshold), (8, flag), (16, request)):
                    s.write(SP+offset, struct.pack('<I', value))
                s.write(SP+22, struct.pack('<H', request))
                result = s.run([c['tail'][2]], limit=2000)
                assert result['status'] == 'breakpoint' and s.regs['pc'] == c['tail'][2], result
                candidates = (60, 30, 20, 15) if flag == 0 else (30, 15)
                selected = next((v for v in candidates if threshold <= next(
                    r['comparison_budget'] for r in lookups if r['fps'] == v and r['flag'] == flag)), 0)
                expected = min(selected, request) if selected else 0
                assert s.regs['d0'] == expected, (flag, request, threshold, result)
                tails.append(dict(flag=flag, requested_fps=request, synthetic_threshold=threshold,
                                  returned_fps=expected, instructions=result['completed']))
    return dict(electronic_ceilings=ceilings, unit_conversion=conversions,
                mode_lookup=lookups, qualification_tail=tails)


def compare_data(images):
    rows = []
    def compare(label, a, b, length):
        first, second = images['om5'][a-BASE:a-BASE+length], images['em1iii'][b-BASE:b-BASE+length]
        assert len(first) == length and first == second, label
        rows.append(dict(label=label, om5=hex(a), em1iii=hex(b), length=length,
                         identical=True, sha256=sha256(first)))
    compare('mode_lookup_rows_and_fallback', 0x601f0438, 0x601f2140, 144)
    compare('candidate_lists', 0x601ef148, 0x601f0e50, 32)
    compare('ceiling_function', 0x602c64b3, 0x602c0dc4, 35)
    compare('unit_conversion_function', 0x602c7068, 0x602c18fa, 47)
    for i in range(6):
        addresses = [struct.unpack_from('<I', images[m], CONFIG[m]['pointers']-BASE+i*4)[0]
                     for m in ('om5', 'em1iii')]
        compare(f'rate_record_window_{54+i}', *addresses, 112)
    # These accessors alias modes54..57 to one record and58..59 to another.
    # Compare precisely the 12-byte prefixes consumed by the reviewed tail;
    # do not infer a 156-byte record from a different neighboring pointer list.
    for i in (0, 4):
        addresses = [struct.unpack_from('<I', images[m], CONFIG[m]['pointers']-BASE+48+i*4)[0]
                     for m in ('om5', 'em1iii')]
        compare(f'budget_record_prefix_{i}', *addresses, 12)
    return rows


def threshold_boundary(data):
    """Retain the real missing-runtime-table stop; do not fake its threshold."""
    s = state(data)
    metadata = invoke(s, 0x60169905, 0x80, 16, dict(d0=14))
    s.write(BUFFER+4, struct.pack('<I', 14))
    s.write(BUFFER+20, struct.pack('<I', BUFFER+256))
    s.write(BUFFER+14, struct.pack('<H', 4004))
    s.write(BUFFER+512, struct.pack('<I', metadata['a0']))
    clamp = invoke(s, 0x6014918b, 0x80, 4, dict(a0=BUFFER, a1=BUFFER+512))
    start_call(s, 0x601491b8, 0xf0, 32, dict(a0=BUFFER, a1=BUFFER+512))
    r = s.run([CALLER+7], limit=2000)
    assert r['status'] == 'memory_fault', r
    assert (r['fault']['pc'], r['fault']['address'], r['fault']['access']) == (
        0x601491e3, 0x61e343e4, 'read'), r
    return dict(fixture='zeroed request/work objects; mode14, secondary parameter0, flag0, dimension4004',
                metadata=metadata, clamp=clamp, strict_stop=r,
                limitation='Runtime table not initialized. No calculated threshold or capture success is inferred.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    pins = json.loads(PINS.read_text())
    dependencies = [Path(__file__), PINS, DEFAULT_OBJDUMP, ENGINE]
    dependencies += [Path('tools')/name for name in (
        'om5_burst_audit.py', 'oly_container.py', 'penf_disasm.py',
        'penf_probe.py', 'penf_boot_emulator.py', 'penf_emulator.py')]
    report = dict(scope=__doc__, hardware_tested=False,
                  dependency_hashes={str(p): sha256(p.read_bytes()) for p in dependencies},
                  models={})
    images = {}
    with tempfile.TemporaryDirectory(prefix='om5-consumers-') as temporary:
        for model, c in CONFIG.items():
            pin = pins[model]
            encoded = Path(pin['source']).read_bytes()
            assert sha256(encoded) == pin['source_sha256']
            data = next(b.payload for b in parse(encoded) if b.kind == 0x100)
            assert sha256(data) == pin['main_sha256']
            images[model] = data
            rates = rate_tables(data, model)[2:]
            callback_keys = [struct.unpack_from('<H', data, c['callback_table']-BASE+i*60)[0]
                             for i in range(c['callback_count'])]
            assert all(r['key'] not in callback_keys for r in rates)
            record = dict(source=pin, locations=c, rates=rates,
                          absent_from_reviewed_callback_registry=[r['key'] for r in rates],
                          registry=registry_cases(data, c, rates),
                          typed_getter=getter_cases(data, c, rates), lower=lower_cases(data, c))
            image = Path(temporary)/f'{model}.main.bin'
            image.write_bytes(data)
            record['windows'] = []
            for label, (start, end) in WINDOWS[model].items():
                name = f'{model}-{label}.asm'
                (args.out/name).write_text(window(data, image, DEFAULT_OBJDUMP, start, end))
                record['windows'].append(dict(file=name, start=hex(start), end=hex(end),
                                              sha256=sha256(data[start-BASE:end-BASE])))
            report['models'][model] = record
        report['identical_regions'] = compare_data(images)
        report['om5_threshold_boundary'] = threshold_boundary(images['om5'])
        original = images['om5']
        modified = bytearray(original)
        changed_rates = []
        changes = []
        for row in report['models']['om5']['rates']:
            if row['mode'].endswith('_h'):
                row = dict(row)
                address = int(row['array'], 16)+4
                assert modified[address-BASE:address-BASE+2] == struct.pack('<H', 300)
                struct.pack_into('<H', modified, address-BASE, 600)
                row['values_tenths_fps'] = [150, 200, 600]
                changed_rates.append(row)
                changes.append(dict(address=hex(address), before=300, after=600))
        assert sum(a != b for a, b in zip(original, modified)) == 4
        report['memory_only_counterfactual'] = dict(changes=changes,
            registry=registry_cases(bytes(modified), CONFIG['om5'], changed_rates),
            warning='Changes exist only in emulator input. No modified component or BIN saved.')
    (args.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print('Verified native registry/stepping, typed getters, rate lookup, 144 qualification-tail cases,')
    print('12 identical regions and a four-byte in-memory list counterfactual. No hardware capture or BIN.')


if __name__ == '__main__':
    main()
