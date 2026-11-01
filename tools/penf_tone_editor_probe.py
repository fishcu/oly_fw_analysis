#!/usr/bin/env python3
"""Bounded native tone-editor request, control-reference and page contracts."""
if not __debug__:
    raise RuntimeError('Tone audit probes require assertions')

import argparse
from dataclasses import replace
import json
from pathlib import Path
import struct

from penf_emulator import BASE, ROOT, Region, firmware
from penf_probe import CALLER
from penf_hsl_context_probe import reenter
from penf_recovery_isolation_probe import without_ranges
from penf_diagnostic_lifetime_probe import parser_state
from penf_tone_candidate import build_candidate
from penf_tone_editor_candidate import build_editor
from penf_tone_integration_probe import packed, stock_signal, run_builder, build_adapter
from penf_tone_probe import identity_lut, PRESERVED, INITIAL_SP
from penf_tone_transport_probe import setup, settings, set_words, call, stopped, u32, put32, ACTIVE, WORDS

CODE, ACTUATOR, SERVICE, MANAGER, CURVE = (0x19080000, 0x19100000, 0x19101000,
                                           0x19102000, 0x19103000)
RECORDS = 0x19104000



def fixture(candidate, editor):
    s = setup(replace(candidate, image=editor.image))
    settings(s)
    s.write(0x61c58404, b'\xa4')
    for name, address, size in (('schema_hash', 0x618872c0, 128 * 4),
            ('schema_nodes', 0x618874c0, 968 * 8), ('callback_hash', 0x61884dec, 64 * 4),
            ('callback_nodes', 0x61884eec, 460 * 8)):
        s.ram(name, address, bytes(size))
    for entry in (0x602c6c37, 0x602bb8f1):
        call(s, entry, 0xb0, 12)
    s.ram('current_record_cache_flag', 0x61c5a69c, b'\x01')
    s.ram('current_record_pointer_cache', 0x61c58bb4, bytes(WORDS * 4))
    s.ram('current_records', RECORDS, bytes(0x400), aliases=False)
    for key in range(967, 976):
        put32(s, 0x61c58bb4 + key * 4, RECORDS + ((key - 967) % 3) * 0x100)
    s.ram('native_compound_ring', 0x618848e8, bytes(20 * 64 + 1))
    parser_state(s)
    s.ram('mode_records', RECORDS + 0x1000, bytes(5), aliases=False)
    for index, key in enumerate((111, 1144, 1084, 912, 977)):
        put32(s, 0x61c58bb4 + key * 4, RECORDS + 0x1000 + index)
    s.ram('property_service', SERVICE, struct.pack('<2I', 0x609a4660, MANAGER), aliases=False)
    s.ram('property_service_pointer', 0x61602868, struct.pack('<I', SERVICE))
    s.ram('curve', CURVE, bytes(512), aliases=False)
    return s


def mode(s, public):
    image = firmware()
    values = struct.unpack_from('<57I', image, 0x603cd014 - BASE)
    index = values.index(public)
    components = struct.unpack_from('<16i', image, 0x603d5a78 - BASE + index * 64)[:5]
    s.write(RECORDS + 0x1000, bytes(components))


def current(s, profile, controls):
    for component, value in enumerate(controls):
        s.write(RECORDS + component * 0x100 + profile - 1, struct.pack('<b', value))


def actuator(s, profile=1, page=0):
    data = bytearray(208)
    high = 967 + 3 * (profile - 1)
    struct.pack_into('<I', data, 0, 0x60f4d350)
    for offset, value in ((160, high + 2), (164, high + 2), (168, high),
                          (180, high + 2), (184, high)):
        struct.pack_into('<I', data, offset, high + 1 if page == 1 else value)
    struct.pack_into('<I', data, 188, 0x60f4cd08 + 56 * (profile - 1))
    struct.pack_into('<HH', data, 192, 2, page)
    s.ram('actuator', ACTUATOR, data, aliases=False)
    return data


def manager_cases(candidate, editor):
    results = []
    for profile in (1, 2, 3):
        s = fixture(candidate, editor)
        initial = (packed(1, 1000), packed(2, 999), packed(3, 998))
        set_words(s, initial)
        high, word = 967 + 3 * (profile - 1), packed(64, 960)
        before = s.read(ACTIVE, WORDS * 8)
        s.regs = dict(PRESERVED, pc=0x60736556, sp=INITIAL_SP, psw=0,
                      a0=0, a1=0, a2=1, a3=SERVICE, d0=0, d1=0, d2=high)
        put32(s,INITIAL_SP+24,0); put32(s,INITIAL_SP+36,word)
        s.write(INITIAL_SP+40,struct.pack('<H',high))
        stop = (0x602c1067, 0x602c1080, 0x602c1099)[profile - 1]
        report = stopped(s, s.run({stop}, limit=100000), stop)
        expected = bytearray(before)
        struct.pack_into('<I', expected, (WORDS + high) * 4, word)
        assert s.read(ACTIVE, WORDS * 8) == expected
        words = list(initial); words[profile - 1] = word
        assert s.read(candidate.symbols['tone_source'], 12) == struct.pack('<3I', *words)
        assert s.regs['d2'] == high and s.regs['a2'] == MANAGER
        results.append(dict(profile=profile, full_word=hex(word), **report))
    for high, word, loaded in ((967, 7, True), (970, 0xfffffff9, True),
                               (968, packed(1, 1022), True), (967, 7, False)):
        s = fixture(candidate, editor)
        if not loaded:
            s.write(0x61c58404, b'\x04')
        before = s.read(ACTIVE, WORDS * 8)
        reenter(s, editor.symbols['tone_manager_gate'], 0xe0, 16,
                dict(PRESERVED, a0=MANAGER, d0=high, d1=word))
        stopped(s, s.run({0x6075fbed}, limit=10000), 0x6075fbed)
        assert (s.regs['a0'], s.regs['d0'], s.regs['d1']) == (MANAGER, high, word)
        assert s.read(ACTIVE, WORDS * 8) == before
    return dict(commit_prefixes=results, native_fallbacks=4,
                scope='Actual part1 write/publication through native per-profile callback entry; completion excluded')


def reference_cases(candidate, editor, adapter):
    s = fixture(candidate, editor)
    reports = []
    for profile, controls in ((1, (0, 0, 0)), (1, (-7, -7, -7)), (2, (7, 7, 7)),
                              (2, (4, -2, -3)), (3, (-7, 7, -7)), (3, (7, -7, 7))):
        current(s, profile, controls)
        report = call(s, editor.symbols['tone_reference'], 0xf0, 16,
                      d0=967 + 3 * (profile - 1), a0=CURVE)
        raw = (0, 0, *controls)
        expected = run_builder(adapter, identity_lut(), raw, native=True)['lut']
        actual = struct.unpack('<256H', s.read(CURVE, 512))
        assert actual == expected
        bounds = stock_signal(identity_lut(), raw)[1]
        assert s.regs['d0'] == bounds[0] | bounds[1] << 8
        assert s.regs['d1'] == expected[bounds[0]] | expected[bounds[1]] << 10
        reports.append(dict(profile=profile, controls=controls, bounds=bounds,
                            inner_heights=[expected[bounds[0]], expected[bounds[1]]], **report))
    return reports


def step_cases(candidate, editor):
    s = fixture(candidate, editor)
    total = 0
    for black, white in ((0, 1023), (64, 960), (1023, 0), (119, 901)):
        for shadow, highlight in ((120, 900), (0, 1023), (400, 401)):
            for axis in (0, 1):
                for delta in (-16, 16):
                    call(s, editor.symbols['tone_step'], 0xf0, 16, d0=packed(black, white),
                         d1=delta & 0xffffffff, a0=axis, a1=shadow | highlight << 10)
                    expected = [min(black, shadow), max(white, highlight)]
                    expected[axis] = (max(0, min(shadow, expected[0] + delta)) if axis == 0 else
                                      max(highlight, min(1023, expected[1] + delta)))
                    assert s.regs['d0'] == packed(*expected), (black, white, shadow, highlight, axis, delta)
                    total += 1
    return dict(cases=total, preserves_exact_clipped_height=True)


def binding_cases(candidate, editor):
    s = fixture(candidate, editor)
    for profile in (1, 2, 3):
        for page in (0, 1, 2):
            before = actuator(s, profile, page)
            mode(s,53+profile)
            call(s, editor.symbols['tone_bind'], 0xf0, 28, a0=ACTUATOR)
            expected = bytearray(before)
            high = 967 + 3 * (profile - 1)
            for offset, value in ((160, high + 2), (164, high + 2), (168, high),
                                  (180, high + 2), (184, high)):
                struct.pack_into('<I', expected, offset, high + 1 if page == 1 else value)
            assert s.read(ACTUATOR, 208) == expected
    return dict(cases=9, page2_uses_pair_fields=True, no_table_stride_change=True)



def input_cases(candidate, editor):
    s = fixture(candidate, editor)
    callbacks = ((0x60c871e3, 0, 1, 16), (0x60c87245, 0, 1, -16),
                 (0x60c872a9, 0, 0, -16), (0x60c8730d, 0, 0, 16),
                 (0x60c8736f, 1, 0, -16), (0x60c8736f, -1, 0, 16),
                 (0x60c873ec, 1, 1, 16), (0x60c873ec, -1, 1, -16))
    reports = []
    for profile in (1, 2, 3):
        mode(s, 53 + profile)
        current(s, profile, (4, -2, -3))
        high = 967 + 3 * (profile - 1)
        set_words(s, (packed(32, 991),) * 3)
        call(s, editor.symbols['tone_reference'], 0xf0, 16, d0=high, a0=CURVE)
        bounds = s.regs['d1']
        shadow, highlight = bounds & 1023, bounds >> 10
        for page in (0, 1, 2):
            for entry, delta, axis, change in callbacks:
                before = actuator(s, profile, page)
                reenter(s, entry, 0, 0, dict(PRESERVED, a0=ACTUATOR, d1=delta & 0xffffffff))
                report = stopped(s, s.run({0x607363b3}, limit=200000), 0x607363b3)
                if page == 2:
                    values = [min(32, shadow), max(991, highlight)]
                    values[axis] = (max(0, min(shadow, values[0] + change)) if axis == 0 else
                                    max(highlight, min(1023, values[1] + change)))
                    expected = (SERVICE, high, 0, packed(*values))
                else:
                    prop = high + 1 if page == 1 else high + (2 if axis == 0 else 0)
                    expected = (SERVICE, prop, 1 if change > 0 else 2, 0)
                actual = tuple(s.regs[r] for r in ('a0', 'd0', 'd1', 'a1'))
                assert actual == expected, (profile, page, hex(entry), actual, expected)
                assert s.read(ACTUATOR, 208) == before
                reports.append(dict(profile=profile, page=page, entry=hex(entry),
                                    payload=hex(s.regs['a1']), **report))
    return dict(callbacks=reports, scope='Real callbacks to unchanged GUI setter, including public-mode and current-control getters; unchanged service completion excluded')


def page_cases(candidate, editor):
    s = fixture(candidate, editor)
    reports = []
    for profile in (1, 2, 3):
        for page in (0, 1, 2):
            mode(s,53+profile)
            actuator(s, profile, page)
            put32(s, INITIAL_SP + 4, ACTUATOR)
            put32(s, INITIAL_SP + 20, 53 + profile)
            s.regs = dict(PRESERVED, pc=0x60c87670, sp=INITIAL_SP, d0=0, d1=0,
                          a0=0, a1=0, a3=0, psw=0)
            report = stopped(s, s.run({0x60c879c8}, limit=10000), 0x60c879c8)
            newpage = (page + 1) % 3
            assert struct.unpack('<H', s.read(ACTUATOR + 194, 2))[0] == newpage
            high = 967 + 3 * (profile - 1)
            assert u32(s, ACTUATOR + 164) == (high + 1 if newpage == 1 else high + 2)
            assert u32(s, ACTUATOR + 168) == (high + 1 if newpage == 1 else high)
            reports.append(dict(profile=profile, before=page, after=newpage, **report))
    return dict(cycles=reports, scope='Native INFO join through bound page, stopped at unchanged axis eligibility entry')


def reset_cases(candidate, editor):
    s = fixture(candidate, editor)
    reports = []
    for profile in (1, 2, 3):
        actuator(s, profile, 2)
        put32(s, INITIAL_SP + 4, ACTUATOR)
        put32(s, INITIAL_SP + 20, 53 + profile)
        s.regs = dict(PRESERVED, pc=0x60c875e4, sp=INITIAL_SP, d0=0, d1=0,
                      a0=0, a1=0, a3=0, psw=0)
        report = stopped(s, s.run({0x607363b3}, limit=10000), 0x607363b3)
        assert tuple(s.regs[r] for r in ('a0', 'd0', 'd1', 'a1')) == (
            SERVICE, 967 + 3 * (profile - 1), 0, packed(0, 1023))
        reports.append(dict(profile=profile, **report))
    return reports



def unavailable_cases(candidate, editor):
    s = fixture(candidate, editor)
    reports = []
    original_regions = list(s.regions)
    for mask in (4, 0x24, 0x84):
        s.regions = list(original_regions)
        s.write(0x61c58404, bytes((mask,)))
        absent = []
        if not mask & 0x20:
            absent.append((0x610f1ea0, 0x610f1fc0))
        if not mask & 0x80:
            absent.append((0x6115b060, 0x6115b7c0))
        absent += [(lo+0x40000000,hi+0x40000000) for lo,hi in absent]
        s.regions = [r for r in s.regions if not any(lo <= r.address and r.address+len(r.data) <= hi for lo,hi in absent)]
        s.regions = without_ranges(s.regions, absent)
        if not mask & 0x80:
            for key in (967, 970, 973):
                before = s.read(ACTIVE, WORDS * 8)
                call(s, editor.symbols['tone_manager_gate'], 0xe0, 16,
                     a0=MANAGER, d0=key, d1=packed(64, 960))
                assert s.regs['d0'] == 0 and s.read(ACTIVE, WORDS * 8) == before
        for entry, delta in ((0x60c871e3, 0), (0x60c8736f, 1)):
            for page in (0, 2):
                before = actuator(s, 1, page)
                reenter(s, entry, 0, 0, dict(PRESERVED, a0=ACTUATOR, d1=delta))
                target = 0x607363b3 if page == 0 else 0x60c87a02
                report = stopped(s, s.run({target, 0x607363b3}, limit=20000), target)
                assert s.read(ACTUATOR, 208) == before
                if page == 2:
                    assert s.regs['a0'] == ACTUATOR
                    expected_sp = INITIAL_SP - (20 if entry == 0x60c871e3 else 24) - 16
                    assert s.regs['sp'] == expected_sp, (hex(s.regs['sp']),hex(expected_sp))
                reports.append(dict(mask=mask, entry=hex(entry), page=page, **report))
        actuator(s, 1, 2)
        put32(s, INITIAL_SP+4, ACTUATOR)
        s.regs = dict(PRESERVED, pc=0x60c875e4, sp=INITIAL_SP, d0=0, d1=0,
                      a0=0, a1=0, a3=0, psw=0)
        stopped(s, s.run({0x60c878dd},limit=1000),0x60c878dd)
    return dict(inputs=reports, tagged_requests_rejected_when_section8_absent=True,
                absent_code_unmapped=True, endpoint_page_does_not_edit_inner_controls=True)


def stock_info_cases(candidate, editor):
    s = fixture(candidate, editor)
    low = (897,969,972,975,1004,1007,1010)
    scenarios = []
    for value in low:
        scenarios += [(value,value-2,value),(value,value-1,value)]
        scenarios += [(value-1,value-1,first) for first in (*low,0xffffffff)]
    scenarios += [(v,v,897) for v in (0,86,324,325,2000,0xffffffff,0x103c8,0x103c9)]
    table = ACTUATOR + 0x800
    s.ram('stock_binding_table_fixture',table,bytes(4),aliases=False)
    for left,right,first in scenarios:
        data = bytearray(208)
        struct.pack_into('<3I',data,180,left,right,table)
        struct.pack_into('<HH',data,192,2,7)
        s.ram('actuator',ACTUATOR,data,aliases=False)
        put32(s,table,first);put32(s,INITIAL_SP+4,ACTUATOR)
        s.regs = dict(PRESERVED,pc=0x60c87670,sp=INITIAL_SP,psw=0,d0=0,d1=0,
                      a0=0,a1=0,a3=0x12345678)
        expected = 1 if left in low and right==left-2 else (0 if left+1 in low and first in low else 7)
        target = 0x60c877f1 if expected==7 else editor.symbols['tone_bind_gate']
        stopped(s,s.run({target},limit=2000),target)
        struct.pack_into('<H',data,194,expected)
        assert s.read(ACTUATOR,208)==data
        assert s.regs['a3']==0x12345678
    return dict(cases=len(scenarios), stock_classification_and_page_mutation_equal=True)


def publication_cases(candidate, editor):
    s = fixture(candidate, editor)
    store,table,destination = ACTUATOR+0x10000,ACTUATOR+0x11000,0x619b5f80
    s.ram('display_store',store,bytes(28),aliases=False)
    s.ram('native_descriptor_table',table,firmware()[0x601f95dc-BASE:0x601f95dc-BASE+211*16],aliases=False)
    s.ram('display_store_global',0x6160c068,struct.pack('<I',store))
    s.ram('display_lock_callbacks',0x6160c154,bytes(16))
    payload=bytes(range(92))
    s.ram('parameter118',destination,payload)
    call(s,0x60bbaa1b,0x20,8,a0=store)
    call(s,0x60bbaa75,0xf0,24,a0=store,a1=table,d0=211)
    reports=[]
    for page in (0,1,2):
        actuator(s,1,page);put32(s,INITIAL_SP+4,ACTUATOR)
        s.regs=dict(PRESERVED,pc=editor.symbols['tone_info_publish'],sp=INITIAL_SP,
                    psw=0,d0=0,d1=0,a0=0,a1=0,a3=0)
        report=stopped(s,s.run({0x60c878e3},limit=20000),0x60c878e3)
        expected=bytearray(payload);expected[5]=page+1
        assert s.read(destination,92)==expected
        assert s.regs['a3']==0
        reports.append(dict(page=page,published_page_byte=page+1,**report))
    return dict(pages=reports, scope='New INFO publication suffix after unchanged eligibility, actual native92-byte get/set and no-observer store; queue delivery excluded')



def stale_cases(candidate, editor):
    s = fixture(candidate,editor)
    before_active=s.read(ACTIVE,WORDS*8)
    for profile in (1,2,3):
        for public in (1,54+(profile%3),57,59):
            mode(s,public)
            actuator(s,profile,2)
            reenter(s,0x60c871e3,0,0,dict(PRESERVED,a0=ACTUATOR,d1=0))
            stopped(s,s.run({0x60c87a02,0x607363b3},limit=20000),0x60c87a02)
            assert s.read(ACTUATOR+194,2)==bytes(2)
            actuator(s,profile,2)
            call(s,editor.symbols['tone_bind'],0xf0,28,a0=ACTUATOR)
            assert s.read(ACTUATOR+194,2)==bytes(2)
            actuator(s,profile,2)
            put32(s,INITIAL_SP+4,ACTUATOR);put32(s,INITIAL_SP+20,public)
            s.regs=dict(PRESERVED,pc=0x60c875e4,sp=INITIAL_SP,psw=0,d0=0,d1=0,a0=0,a1=0,a3=0)
            stopped(s,s.run({0x60c878dd,0x607363b3},limit=20000),0x60c878dd)
            assert s.read(ACTUATOR+194,2)==bytes(2)
            assert s.read(ACTIVE,WORDS*8)==before_active
    return dict(cases=12, stale_input_binding_and_reset_clear_endpoint_page=True, no_setting_changes=True)



def other_family_cases(candidate, editor):
    reports = []
    callbacks = ((0x60c871e3, 0), (0x60c87245, 0), (0x60c872a9, 0),
                 (0x60c8730d, 0), (0x60c8736f, -1), (0x60c8736f, 1),
                 (0x60c873ec, -1), (0x60c873ec, 1))
    def family(state):
        actuator(state, 1, 2)
        put32(state, ACTUATOR+188, 0x60f4c330)
        state.write(ACTUATOR+192, struct.pack('<HH', 4, 2))
        for offset in (160,164,168,180,184):
            put32(state, ACTUATOR+offset, 896)
    for mask in (0xa4, 4, 0x24, 0x84):
        original = fixture(candidate, replace(editor, image=candidate.reference))
        patched = fixture(candidate, editor)
        for state in (original, patched):
            state.write(0x61c58404, bytes((mask,)))
            absent = []
            if not mask & 0x20:
                absent.append((0x610f1ea0, 0x610f1fc0))
            if not mask & 0x80:
                absent.append((0x6115b060, 0x6115b7c0))
            absent += [(lo+0x40000000,hi+0x40000000) for lo,hi in absent]
            state.regions = [r for r in state.regions if not any(lo <= r.address and r.address+len(r.data) <= hi for lo,hi in absent)]
            state.regions = without_ranges(state.regions, absent)
            family(state)
            reenter(state, 0x60c878ec, 0xf0, 28, dict(PRESERVED,a0=ACTUATOR))
            stopped(state,state.run({0x607355e9},limit=10000),0x607355e9)
        expected = original.read(ACTUATOR, 208)
        assert patched.read(ACTUATOR, 208) == expected
        assert struct.unpack('<H', expected[194:196])[0] == 2
        assert u32(patched, ACTUATOR+180) == 896
        for entry, direction in callbacks:
            captured = []
            for state in (original, patched):
                reenter(state, entry, 0, 0, dict(PRESERVED, a0=ACTUATOR, d1=direction & 0xffffffff))
                stopped(state, state.run({0x607363b3,0x60c87a02}, limit=20000),0x607363b3)
                captured.append(tuple(state.regs[k] for k in ('a0','d0','d1','a1','sp')))
                assert state.read(ACTUATOR,208) == expected
            assert captured[0][:-1] == captured[1][:-1], (mask,entry,captured)
            assert captured[1][-1] == captured[0][-1]-4, (mask,entry,captured)
        captured = []
        for state in (original,patched):
            put32(state,INITIAL_SP+4,ACTUATOR)
            state.regs=dict(PRESERVED,pc=0x60c875e4,sp=INITIAL_SP,psw=0,d0=0,d1=0,a0=0,a1=0,a3=0)
            stopped(state,state.run({0x60c875ec,0x60c878dd},limit=2000),0x60c875ec)
            captured.append(tuple(state.regs[k] for k in ('a0','d0','d2','sp')))
            assert state.read(ACTUATOR,208) == expected
        assert captured[0] == captured[1], (mask,captured)
        reports.append(dict(mask=mask,page=2,bound_property=896,input_prefixes=8,
                            native_reset_prefix_equal=True,receiver_unchanged=True))
    return dict(four_page_table='0x60f4c330',cases=reports,
                scope='Binder prefix through unchanged GUI service getter entry; actual input requests and reset replay prefix',
                missing_late_code_unmapped=True,modeled_functions=[])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    candidate = build_candidate(args.out / 'candidate')
    editor = build_editor(args.out / 'editor', candidate)
    adapter = build_adapter(args.out / 'adapter')
    result = dict(editor_bytes=sum(map(len, editor.chunks.values())), placement='bounded composed offline main image; not installable container',
                  manager=manager_cases(candidate, editor), reference=reference_cases(candidate, editor, adapter),
                  steps=step_cases(candidate, editor), bindings=binding_cases(candidate, editor),
                  inputs=input_cases(candidate, editor), pages=page_cases(candidate, editor),
                  reset=reset_cases(candidate, editor), unavailable=unavailable_cases(candidate, editor),
                  stock_info=stock_info_cases(candidate, editor), publication=publication_cases(candidate, editor), stale=stale_cases(candidate,editor), other_family=other_family_cases(candidate,editor))
    (args.out / 'audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(editor_bytes=sum(map(len, editor.chunks.values())), verified=list(result)[2:])))


if __name__ == '__main__':
    main()
