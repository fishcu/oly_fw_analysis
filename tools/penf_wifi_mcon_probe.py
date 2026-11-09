#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Offline PEN-F 3101 Wi-Fi numeric-setting handler contracts.

Runs native query parsing and setting writes against the existing captured
boot fixture. Stops before HTTP response transmission; no sockets, camera
access, peripheral success models or firmware mutations. This is not an
end-to-end Wi-Fi, persistence, live-view or shooting test.
"""
import argparse
import json
from pathlib import Path
import struct

import penf_profile_context_probe as c
from penf_landmarks import MAIN_SHA256
from oly_container import parse

HANDLER, RESPONSE, QUERY = 0x60aa2656, 0x60a9d38b, 0x21070000
INHIBIT = 0x6189a4b0
DIRECTORIES = ((0, 1274, 0x603fa158, 4), (1500, 19, 0x603fb540, 4),
               (3000, 23, 0x603fb5b8, 2), (4000, 22, 0x603fb58c, 2),
               (15000, 263, 0x603fb7ca, 4))


def compact(result):
    return {k: v for k, v in result.items()
            if k not in ('trace_tail', 'stop_registers')}


def set_query(s, mode, value, *, omit_value=False):
    pairs = [('mode', mode)] + ([] if omit_value else [('value', value)])
    assert all(len(x.encode()) < 30 for pair in pairs for x in pair)
    query = struct.pack('<H', len(pairs)) + b''.join(
        k.encode().ljust(30, b'\0') + v.encode().ljust(30, b'\0')
        for k, v in pairs)
    s.ram('synthetic_parsed_CGI_query', QUERY, query, aliases=False)
    result = c.invoke(s, HANDLER, 0, 0,
                      dict(a0=0x21080000, a1=QUERY), stops=(RESPONSE,))
    c.at(s, result, RESPONSE)
    return compact(result)


def snapshot(f, s, key):
    return dict(current_record=c.current_record(f, s, key),
                live=struct.unpack('<i', s.read(c.LIVE+key*4, 4))[0])


def scalar_cases(f):
    s = c.state(f)
    c.selected(s, 2)
    active, banks = s.read(c.ACTIVE, c.STRIDE), s.read(c.BANKS, 9*c.STRIDE)
    # Different sectors/profiles, tones, contrast, WB and EV records. Values
    # are ordinary native values, NOT all Workspace values or slider units.
    cases = [(k, (k % 11)-5) for k in range(931, 967)]
    cases += [(916, -2), (917, 1), (918, 2)]
    cases += [(k, (k % 15)-7) for k in range(967, 976)]
    cases += [(9, 0), (91, 3), (133, -2), (428, 0), (107, 5300),
              (1171, 1), (904, 85)]
    rows = []
    for key, value in cases:
        before = snapshot(f, s, key)
        result = set_query(s, f'{key:04X}', f'{value & 0xffffffff:08X}')
        after = snapshot(f, s, key)
        assert result['result'] == 200
        assert after['current_record'] == value, (key, value, after)
        assert after['live'] == before['live']
        rows.append(dict(id=key, mode_hex=f'{key:04X}', value=value,
                         before=before, after=after, native=result))
    assert active == s.read(c.ACTIVE, c.STRIDE)
    assert banks == s.read(c.BANKS, 9*c.STRIDE)
    return dict(cases=rows, live_values_unchanged=True,
                active_and_saved_banks_unchanged=True)


def controls(f):
    s = c.state(f)
    c.selected(s, 2)
    c.put(s, 943, 0)
    c.put(s, 919, 0)
    rows = []
    for name, mode, value, expected, inhibit, omit, http in (
        ('positive', '03AF', '00000005', 5, False, False, 200),
        ('negative_twos_complement', '03AF', 'FFFFFFFB', -5, False, False, 200),
        ('incorrect_decimal_mode', '943', '5', -5, False, False, 200),
        ('incorrect_signed_decimal_value', '03AF', '-5', 0, False, False, 200),
        ('inhibited', '03AF', '5', 0, True, False, 200),
        ('unknown_mode', 'FFFF', '5', 0, False, False, 200),
        ('missing_value', '03AF', '', 0, False, True, 520),
        # Deliberately invalid UI value, only in emulated RAM. This proves
        # the setter itself does not enforce the stock saturation enum.
        ('no_range_validation_OFFLINE_ONLY', '03AF', '00000063', 99, False, False, 200),
    ):
        s.write(INHIBIT, bytes([inhibit]))
        result = set_query(s, mode, value, omit_value=omit)
        after = snapshot(f, s, 943)
        assert after == dict(current_record=expected, live=0), (name, after)
        assert c.current_record(f, s, 919) == 0
        assert result['result'] == http
        rows.append(dict(case=name, mode=mode, value=value, observed=after,
                         effective_saturation_unchanged=0, native=result))
    # Contrast to the real public edit path. Stop at a known dependency
    # boundary before any missing record/hardware response is invented.
    s = c.state(f)
    c.selected(s, 2)
    before = snapshot(f, s, 943)
    result = c.invoke(s, 0x602b9f33, 0xc0, 16, dict(d0=943, d1=5),
                      stops=(0x60549d65,))
    c.at(s, result, 0x60549d65)
    after = snapshot(f, s, 943)
    assert after == dict(current_record=5, live=5)
    return dict(cases=rows, public_setter_prefix=dict(before=before, after=after,
                native=compact(result), scope='Stops in later dependency processing; not a completed edit'))


def map_audit(f, patched):
    aliases, count = [], 0
    spans = [(0x60aa2349, 0x60aa2718), (0x602f024a, 0x602f0600),
             (0x600751c5, 0x60075238), (0x60aa612b, 0x60aa627b),
             (0x60188bfa, 0x60188c8a)]
    for first, length, table, stride in DIRECTORIES:
        spans.append((table, table+length*stride))
        for i in range(length):
            record = struct.unpack_from('<H', f.image, table-c.BASE+i*stride)[0]
            count += 1
            if record in (0x85c4, 0x85d4):
                aliases.append(dict(id=first+i, record=hex(record)))
    assert not aliases
    report = dict(entries_scanned=count, hsl_bank_record_aliases=aliases,
                  special_6000='Separate 16-bit scalar at a1c58bb0, not part-1 H/L',
                  interpretation='No direct H/L bank-record alias in these mapped ID ranges')
    if patched:
        encoded = patched.read_bytes()
        block = next(b for b in parse(encoded) if b.kind == 0x0100)
        checked = []
        for start, end in spans:
            same = f.image[start-c.BASE:end-c.BASE] == block.payload[start-c.BASE:end-c.BASE]
            assert same, hex(start)
            checked.append(dict(start=hex(start), end_exclusive=hex(end), identical=True))
        report['range7_comparison'] = dict(path=str(patched), sha256=c.sha(encoded),
            decoded_main_sha256=c.sha(block.payload), identical_regions=checked,
            scope='Static equality of relevant handlers/helpers/maps; native execution uses stock main')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--compare-package', type=Path)
    args = parser.parse_args()
    f = c.Fixture()
    assert c.sha(f.image) == MAIN_SHA256
    report = dict(image=str(c.DEFAULT_IMAGE), main_sha256=c.sha(f.image),
                  checkpoint_sha256=c.CHECKPOINT_SHA,
                  scope='Native setter entry through response preparation, synthetic parsed requests; no camera traffic')
    report['map_audit'] = map_audit(f, args.compare_package)
    report['scalar_writes'] = scalar_cases(f)
    report['controls'] = controls(f)
    report['all_assertions_passed'] = True
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2)+'\n')
    print(f'Saved {args.out}; {len(report["scalar_writes"]["cases"])} scalar cases and '
          f'{len(report["controls"]["cases"])} controls passed')


if __name__ == '__main__':
    main()
