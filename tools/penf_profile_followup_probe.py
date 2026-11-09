#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""COLOR processing/display dispatch and settings-store lifetime contracts.

All execution is offline. Captured boot RAM is a partial initialization, not
camera state. Register property callbacks and validators natively before edit
dispatch tests. Never emulate an ISP or nonvolatile write as successful.
"""
import argparse
import json
from pathlib import Path
import struct

from penf_profile_lifecycle_probe import (
    ACTIVE, BANKS, CHECKPOINT_SHA, COLOR, ENGINE, Fixture, LIVE, STRIDE,
    WORDS, WORKING, bank_word, color_values, get, invoke, put, returned,
    setup_a, sha, words,
)
from penf_disasm import BASE, DEFAULT_IMAGE, DEFAULT_OBJDUMP, refs, window
from penf_probe import BUFFER, CALLER

OUTPUT = 0x20001000
DRAW_INFO = 0x618d4bc0
REGISTRATIONS = ((0x602bb8f1, 0xb0, 12), (0x602bd565, 0xb0, 12))


def state(fixture, registered=True):
    s = fixture.state()
    # The native debug-history query needs CPU0's captured current task (47).
    # This is a diagnostic calling-context fixture, not a GUI scheduler model.
    for address, size in ((0x8ff00004, 12), (0x6183581c, 2),
                          (0x6183580c, 4), (0x61823860, 2)):
        s.ram(f'captured_task_query_{address:x}', address, fixture.read(address, size),
              aliases=address < 0x80000000)
    setup_a(s)
    s.ram('output_fixture', OUTPUT, bytes(256), aliases=False)
    if registered:
        for entry, mask, frame in REGISTRATIONS:
            returned(s, invoke(s, entry, mask, frame))
    return s


def at(s, result, address):
    assert result['status'] == 'breakpoint' and s.regs['pc'] == address, result


def selected_fixture(s, profile):
    # ID111 is supplied explicitly. Its production from the dial, public
    # picture-mode values and UI profile selection is not proved by this test.
    put(s, 912, profile)
    put(s, 111, 53+profile)
    for key, value in zip(COLOR, color_values(2)):
        put(s, key, value)


def registration(fixture):
    s = state(fixture, registered=False)
    before = []
    for key in (111, 931, 943, 966):
        r = invoke(s, 0x602bb946, 0, 0, dict(d0=key))
        returned(s, r)
        assert s.regs['a0'] == 0
        before.append(dict(id=key, descriptor=0))
    assert s.read(0x61884dec, 256) == bytes(256)
    assert s.read(0x61885d50, 128) == bytes(128)
    initialized = []
    for entry, mask, frame in REGISTRATIONS:
        r = invoke(s, entry, mask, frame)
        returned(s, r)
        initialized.append(dict(entry=hex(entry), **r))
    after = []
    for key, expected in ((111, 0x602bff81), (931, 0x602c1067),
                          (943, 0x602c1080), (966, 0x602c1099)):
        r = invoke(s, 0x602bb946, 0, 0, dict(d0=key))
        returned(s, r)
        address = s.regs['a0']
        row = struct.unpack('<15I', s.read(address, 60))
        assert row[0] == key and row[6] == expected
        after.append(dict(id=key, descriptor=hex(address),
                          current_callback=hex(row[6]), staged_callback=hex(row[12])))
    r = invoke(s, 0x602bd53b, 0, 0, dict(d0=111))
    returned(s, r)
    assert s.regs['a0'] == 0x603a16d8
    return dict(captured_lookup_before=before, registration=initialized,
                registered_lookup=after, validator111='0x603a16d8',
                correction='Earlier checkpoint-only probes had empty callback AND validator hash tables')


def processing(fixture):
    packed, dispatch = [], []
    for context in (0, 1):
        for profile in (1, 2, 3):
            s = state(fixture)
            selected_fixture(s, profile)
            if context:
                returned(s, invoke(s, 0x602f0a2c, 0xf0, 20))
                returned(s, invoke(s, 0x602f0b12, 0, 4))
                # Distinguish staged values from a fresh read of current ones.
                for key in COLOR:
                    put(s, key, 5)
            r = invoke(s, 0x602c414a, 0xf0, 168,
                       dict(d0=context, d1=53+profile, a0=OUTPUT))
            returned(s, r)
            expected = color_values(2)[(profile-1)*12:profile*12]
            assert words(s, OUTPUT+80, 12) == expected
            packed.append(dict(context=context, profile=profile, values=expected,
                               current_changed_after_snapshot=bool(context), **r))
    for active_profile in (1, 2, 3):
        for edited_profile in (1, 2, 3):
            s = state(fixture)
            selected_fixture(s, active_profile)
            s.write(0x615fd38c, struct.pack('<I', 0x6075fedb))
            key = 931+(edited_profile-1)*12
            r = invoke(s, 0x602b9f33, 0xc0, 16, dict(d0=key, d1=5),
                       stops=(0x602c50be,))
            refresh = active_profile == edited_profile
            if refresh:
                at(s, r, 0x602c50be)
                assert (s.regs['d0'], s.regs['d1']) == (0, 53+active_profile)
            else:
                returned(s, r)
            assert get(s, key) == 5
            dispatch.append(dict(active_profile=active_profile, edited_profile=edited_profile,
                                 property_id=key, processing_refresh_reached=refresh, **r))
    # Strict continuation of one active edit, including downstream callbacks.
    s = state(fixture)
    selected_fixture(s, 1)
    strict = invoke(s, 0x602b9f33, 0xc0, 16, dict(d0=931, d1=5))
    assert strict['status'] == 'memory_fault', strict
    assert strict['pc'] == '0x60547a00' and strict['fault']['address'] == 0xa1c6931c
    return dict(packing=packed, active_inactive_dispatch=dispatch,
                strict_active_edit=strict,
                scope='Supplied effective profile ID111; no completed display, capture or ISP submission')


def display(fixture):
    cases = []
    for profile, cursor in ((1, 1), (2, 6), (3, 12)):
        s = state(fixture)
        selected_fixture(s, profile)
        put(s, (1095, 1100, 1101)[profile-1], cursor)
        s.ram('captured_COLOR_draw_info', DRAW_INFO, fixture.read(DRAW_INFO, 12))
        s.write(BUFFER, struct.pack('<H', 5)+bytes(22))
        r = invoke(s, 0x6081b780, 0, 0, dict(a0=0x19000000, a1=BUFFER),
                   stops=(0x60300b3d,))
        at(s, r, 0x60300b3d)
        assert s.regs['d0'] == 5
        payload = s.read(s.regs['a0'], 13)
        expected = color_values(2)[(profile-1)*12:profile*12]
        assert struct.unpack('<12b', payload[:12]) == expected and payload[12] == cursor
        s.write(BUFFER, payload)
        converted = invoke(s, 0x602fc370, 0xf0, 28, dict(a0=OUTPUT, a1=BUFFER))
        returned(s, converted)
        assert converted['result'] == 0
        output = s.read(OUTPUT, 13)
        assert tuple(output[:12]) == tuple(v+5 for v in expected)
        assert output[12] == cursor-1
        cases.append(dict(profile=profile, input_cursor=cursor, draw_prefix=r,
                          input_payload=list(struct.unpack('<12bB', payload)),
                          converter=converted, display_payload=list(output)))
    return cases


RESET_LISTS = (
    ('25-ID current reset', 0x602c5a86, 0x603ca598, 25),
    ('478-ID current reset', 0x602c5ab6, 0x603cb010, 478),
    ('1315-ID staged reset', 0x602c5ad8, 0x603ca5ca, 1315),
)


def resets(fixture):
    cases = []
    witness = bytes(range(144))
    defaults = fixture.image[0x603c8bb0-BASE:0x603c8bb0-BASE+WORDS*4]
    for name, entry, table, count in RESET_LISTS:
        s = state(fixture)
        selected_fixture(s, 3)
        s.write(ACTIVE+(WORDS+931)*4, witness)
        saved = s.read(BANKS, STRIDE*9)
        ids = struct.unpack_from(f'<{count}H', fixture.image, table-BASE)
        r = invoke(s, entry, 0, 4)
        returned(s, r)
        changed = entry == 0x602c5ad8
        expected = defaults[931*4:967*4] if changed else witness
        assert s.read(ACTIVE+(WORDS+931)*4, 144) == expected
        assert s.read(BANKS, STRIDE*9) == saved
        assert (set(COLOR) <= set(ids)) == changed
        cases.append(dict(name=name, entry=hex(entry), list=hex(table), count=count,
                          COLOR_ids=[i for i in ids if i in COLOR],
                          replaces_candidate_bytes=changed,
                          saved_banks_unchanged=True, **r))
    return cases


def recall_prefixes(fixture):
    cases = []
    for name, entry, frame, destination in (
            ('MyMode', 0x602ba1bd, 20, 1),
            ('ShortcutMyset', 0x602ba0fb, 16, 5),
            ('DialMyset', 0x602ba07b, 16, 5)):
        s = state(fixture)
        selected_fixture(s, 1)
        for key, value in ((24, 4), (26, 4), (43, 4), (109, 0), (912, 3)):
            bank_word(s, destination, key, value)
        values = color_values(6)
        for key, value in zip(COLOR, values):
            bank_word(s, destination, key, value)
        witness = bytes((i+19*destination) & 255 for i in range(144))
        s.write(BANKS+destination*STRIDE+(WORDS+931)*4, witness)
        # Before filtering/staging: MyMode has an earlier special restore of
        # ID86 requiring the default-record directory, so stop at 602bcd16.
        stop = 0x602bcd16 if name != 'DialMyset' else 0x602f0a2c
        r = invoke(s, entry, 0xc0, frame, dict(d0=53), stops=(stop,))
        at(s, r, stop)
        assert s.read(ACTIVE+(WORDS+931)*4, 144) == witness
        assert words(s, ACTIVE+931*4, 36) == values
        cases.append(dict(route=name, destination=destination, **r,
                          candidate_bytes_loaded_into_active=True,
                          application_completion=False))
    # Continue the last prefix with its native call stack and initialized
    # dispatch tables. Do not re-enter while the settings lock is already held.
    before = s.steps
    run = s.run({CALLER+7}, limit=15000000)
    r = dict(status=run['status'], pc=hex(s.regs['pc']), fault=run.get('fault'),
             instructions=s.steps-before, modeled_functions=[])
    assert r['status'] == 'memory_fault', r
    cases.append(dict(route='DialMyset continuation with initialized tables', **r,
                      note='Resumes original native call stack; strict boundary only'))
    return cases


def store(fixture):
    cases = []
    for changed in (False, True):
        s = state(fixture)
        # Real initialized type-54 Mode object. Its sole backing pointer is
        # a1ef2c00; supply a matching RAM comparison image, not physical flash.
        s.ram('captured_Mode_object', 0x61c281a8, fixture.read(0x61c281a8, 28))
        obj = 0xa1c281a8
        initial = s.read(WORKING, 0x20000)
        s.ram('Mode_backing_RAM_fixture', 0x61ef2c00, initial)
        offset = BANKS+STRIDE+(WORDS+931)*4
        witness = bytes(range(144))
        if changed:
            s.write(offset, witness)
        r = invoke(s, 0x600733d8, 0xf0, 24, dict(a0=obj), stops=(0x600720e1,))
        if changed:
            at(s, r, 0x600720e1)
            assert (s.regs['d0'], s.regs['d1'], s.regs['a0'], s.regs['a1']) == (
                0x20000, 0, WORKING, 0xa1ef2c00)
            envelope = s.read(WORKING, 0x20000)
            assert s.read(offset, 144) == witness
            assert sum(struct.unpack('<65536H', envelope)) & 65535 == 0
            assert struct.unpack_from('<I', envelope, 4)[0] == (
                struct.unpack_from('<I', initial, 4)[0]+1) & 0xffffffff
            validator = invoke(s, 0x600734e3, 0xf0, 20,
                               dict(d0=0x20000, d1=0x54, a0=WORKING))
            returned(s, validator)
            assert validator['result'] == 0
        else:
            returned(s, r)
            assert r['result'] == 0 and s.read(WORKING, 0x20000) == initial
            validator = None
        assert s.read(0x61ef2c00, 0x20000) == initial
        cases.append(dict(changed=changed, native_store_prefix=r,
                          checksum_validation=validator,
                          backing_RAM_unchanged=True, programming_executed=False,
                          candidate_Myset1_bytes_trigger_full_store=changed))
    return cases


def evidence(fixture, out):
    windows = {
        'property-registration': (0x602bb8f1, 0x602bb970),
        'validator-registration': (0x602bd53b, 0x602bd5ba),
        'property-write-and-callback': (0x602bb63a, 0x602bb6a9),
        'COLOR-current-callbacks': (0x602c1067, 0x602c10b2),
        'COLOR-staged-callbacks': (0x602c59bd, 0x602c5a1d),
        'effective-profile-builder': (0x602c414a, 0x602c52ff),
        'draw-payload': (0x6081b780, 0x6081bcb7),
        'draw-converter': (0x602fc370, 0x602fc619),
        'reset-lists-and-loops': (0x602c5a86, 0x602c5d4a),
        'temporary-recall': (0x602ba0fb, 0x602ba24d),
        'temporary-recall-inner': (0x602bcd16, 0x602bce30),
        'temporary-bank-load': (0x602bda17, 0x602bdaa5),
        'store-check-and-write': (0x600732cc, 0x60073443),
        'store-wrapper': (0x602f0d18, 0x602f0dee),
        'store-selector': (0x6007561f, 0x6007582c),
        'application-store-sequence': (0x606efb9e, 0x606efc7f),
        'notification-deferred': (0x607601b5, 0x6076062d),
        'notification-registration': (0x6075f036, 0x6075f0c9),
        'notification-immediate': (0x60760063, 0x607601b5),
    }
    for name, (start, end) in windows.items():
        (out/(name+'.asm')).write_text(window(fixture.image, DEFAULT_IMAGE, DEFAULT_OBJDUMP, start, end))
    candidates = {}
    for target in (0x602bb8f1, 0x602bd565, 0x602c50be, 0x602f0d1d, 0x602f0d88,
                   0x606efbef, 0x606efb9e, 0x6075f036, 0x6075f061):
        pointers, calls = refs(fixture.image, target)
        candidates[hex(target)] = dict(raw_pointer_candidates=list(map(hex, pointers)),
                                       raw_call_candidates=list(map(hex, calls)))
    return candidates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path('analysis/profile_followup/verified'))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    fixture = Fixture()
    report = dict(main_sha256=sha(fixture.image), checkpoint_sha256=CHECKPOINT_SHA,
                  source_sha256={str(p): sha(p.read_bytes()) for p in (
                      Path(__file__), Path('tools/penf_profile_lifecycle_probe.py'),
                      Path('tools/penf_probe.py'), Path('tools/penf_boot_emulator.py'),
                      Path('tools/penf_emulator.py'), Path('tools/penf_diagnostic_lifetime_probe.py'),
                      Path('tools/penf_disasm.py'), ENGINE)},
                  camera_used=False, firmware_modified=False, flash_write=False,
                  assumptions=['CPU0 captured task47 for diagnostic query, no scheduling',
                               'A-mode RAM scenario; explicit effective profile111=54/55/56',
                               'native property/validator registration before dispatch tests',
                               'synthetic drawing command and Mode backing RAM'])
    for name, function in (('registration', registration), ('processing', processing),
                           ('display', display), ('resets', resets),
                           ('recall_prefixes', recall_prefixes), ('store', store)):
        report[name] = function(fixture)
        print(name, 'passed', flush=True)
    report['reference_candidates'] = evidence(fixture, args.out)
    report['all_assertions_passed'] = True
    (args.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(args.out/'report.json')


if __name__ == '__main__':
    main()
