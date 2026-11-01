#!/usr/bin/env python3
"""Execute composed native endpoint publication, snapshots and job transport offline."""
if not __debug__:
    raise RuntimeError('Tone audit probes require assertions')

import argparse
from dataclasses import replace
import json
from pathlib import Path
import struct

from penf_emulator import BASE, ENGINE, Region
from penf_probe import CALLER, ProbeState
from penf_diagnostic_lifetime_probe import helpers
from penf_hsl_context_probe import reenter
from penf_recovery_isolation_probe import without_ranges
from penf_tone_candidate import build_candidate
from penf_tone_integration_probe import (JOB, OUTPUT, CONTEXT, LUT, prepare, packed,
                                         stock_signal, upload_result)
from penf_tone_endpoints import ToneEndpoints, endpoint_oracle
from penf_tone_probe import (INITIAL_SP, PRESERVED, GUARD, identity_lut, _finish,
                             _check_guards, sha)

ACTIVE, BANKS, LIVE, WORDS = 0x61b938b8, 0x61b7bdc8, 0x61b924cc, 1274
LARGE, COMPACT, HL_ROWS = 0xadafa3c0, 0xa1c6cab8, 0xa069b590
REFERENCE_REGS = dict(d0=0x01234567, d1=0x89abcdef, **PRESERVED,
                      a0=0x23456789, a1=0xabcdef01,
                      mdr=0x91827364, lir=0x10203040, lar=0x50607080)
HL_PACKED = bytes((i % 8) | ((7 - i % 8) << 4) for i in range(36))
SOURCE_WORDS = (packed(50, 950), packed(80, 920), packed(100, 900))


def u32(s, address):
    return struct.unpack('<I', s.read(address, 4))[0]


def put32(s, address, value):
    s.write(address, struct.pack('<I', value))


def stopped(s, result, address):
    assert result['status'] == 'breakpoint' and s.regs['pc'] == address, (
        result['status'], result.get('fault'), hex(s.regs['pc']))
    return dict(instructions=result['completed'], stop=hex(address), modeled_functions=[])


def call(s, entry, mask=0, frame=4, **registers):
    reenter(s, entry, mask, frame, dict(REFERENCE_REGS, **registers))
    result = s.run({CALLER + 7}, limit=500000)
    report = stopped(s, result, CALLER + 7)
    assert s.regs['sp'] == INITIAL_SP
    return report


def block(s, entry, stop, **registers):
    s.regs = dict(REFERENCE_REGS, **registers, pc=entry, sp=INITIAL_SP, psw=0x80000000)
    result = s.run({stop}, limit=500000)
    report = stopped(s, result, stop)
    assert s.regs['sp'] == INITIAL_SP
    return report


def setup(candidate, *, reference=False, loaded=True, processing=False, raw=(0, 0, 0, 0, 0), record=0, **processing_options):
    if processing:
        s = prepare(identity_lut(), raw, record=record, **processing_options)
    else:
        s = ProbeState(CALLER + 7, 0, 0, bytes(16), {})
        s.ram('job', JOB - 32, GUARD + b'\xa7' * 14948 + GUARD, aliases=False)
    image = candidate.reference if reference else candidate.image
    s.regions = [replace(r, data=image) if r.name == 'main' else r for r in s.regions]
    s.ram('loaded_sections', 0x61c58404, struct.pack('<I', 0x84 if loaded else 4))
    s.ram('hl_source', candidate.symbols['hl_profile_source'], HL_PACKED)
    s.ram('tone_source', candidate.symbols['tone_source'], struct.pack('<3I', *SOURCE_WORDS))
    s.ram('hl_rows', HL_ROWS, bytes(540))
    if loaded:
        s.ram('tone_rows', candidate.symbols['tone_rows'], b'\xc7' * 180)
    else:
        s.regions = without_ranges(s.regions, [(0x6115b060, 0x6115b7c0)])
    s.write(INITIAL_SP - 0x1000, GUARD)
    return s


def owner(s, slot, profile, *, alias=False, mode=11):
    compact = slot >= 40
    address = COMPACT + (slot - 40) * 632 if compact else LARGE + slot * 41984
    start = 378 if compact else 18588
    data = bytearray(b'\x31' * (4 if compact else 40))
    data[381 - start if compact else 18625 - start] = profile
    if not compact:
        data[18595 - start] = mode
    s.ram(f'owner_{slot}', address + start, data)
    return address - 0x40000000 if alias else address


def acquisition(s, address, compact=False):
    if compact:
        raw_record = 0x1a080020
        s.ram('compact_raw', raw_record, b'\x7d' * 124, aliases=False)
        put32(s, INITIAL_SP + 4, raw_record)
        report = block(s, 0x605576ec, 0x605576f2, a3=address + 382)
        assert s.read(raw_record, 124) == b'\x7d' * 122 + b'\0\x7d'
    else:
        report = block(s, 0x60253c7f, 0x60253c85, d2=address)
        assert s.regs['d0'] == 63401
    return report


def to_job(s, address, route):
    if route == 'preview':
        pointer = 0x1a090020
        s.ram('owner_pointer', pointer, struct.pack('<I', address), aliases=False)
        put32(s, INITIAL_SP + 4, JOB + 36)
        return block(s, 0x605205f9, 0x605205ff, a0=pointer)
    if route == 'recording':
        put32(s, INITIAL_SP + 24, address)
        put32(s, INITIAL_SP + 20, JOB + 36)
        return block(s, 0x605323f8, 0x605323fe)
    raise ValueError(route)


def settings(s):
    s.register(0x8050, 'r', 0)
    s.ram('settings_pointer', 0x61896ed4, struct.pack('<3I', BANKS, ACTIVE, LIVE))
    s.ram('banks', BANKS, bytes(9 * WORDS * 8))
    s.ram('active', ACTIVE, bytes(WORDS * 8))
    s.ram('live', LIVE, bytes(WORDS * 4))


def set_words(s, words):
    for setting, word in zip((967, 970, 973), words):
        call(s, 0x602f0710, 0x80, 8, d0=setting, d1=1, a0=word)


def publication(candidate):
    s = setup(candidate, loaded=False)
    settings(s)
    reports = []
    for bank in range(9):
        words = tuple(packed(bank * 10 + p, 1023 - bank * 10 - p) for p in range(3))
        set_words(s, words)
        stored = call(s, 0x602f067a, 0xc0, 12, d0=bank)
        set_words(s, (0xffffffff,) * 3)
        loaded = call(s, 0x602f063e, 0xc0, 12, d0=bank)
        published = call(s, candidate.symbols['hl_publish'])
        assert s.read(candidate.symbols['tone_source'], 12) == struct.pack('<3I', *words)
        reports.append(dict(bank=bank, words=list(words), store=stored, load=loaded, publish=published))
    for words in ((0, 0xffffffff, 0x12345678), (packed(0, 1023),) * 3):
        set_words(s, words)
        call(s, candidate.symbols['hl_publish'])
        assert s.read(candidate.symbols['tone_source'], 12) == struct.pack('<3I', *words)
    return dict(banks=reports, publication_without_section8=True,
                invalid_words_copied_opaquely=True)


def owner_matrix(candidate):
    s = setup(candidate)
    reports = []
    for slot in range(45):
        profile = slot % 3 + 1
        address = owner(s, slot, profile, alias=bool(slot % 2))
        before = s.read(candidate.symbols['tone_rows'], 180)
        acquired = acquisition(s, address, slot >= 40)
        row = candidate.symbols['tone_rows'] + 4 * slot
        assert u32(s, row) == SOURCE_WORDS[profile - 1]
        expected = bytearray(before)
        struct.pack_into('<I', expected, slot * 4, SOURCE_WORDS[profile - 1])
        assert s.read(candidate.symbols['tone_rows'], 180) == bytes(expected)
        # The later source is deliberately different: a job must use its owner's snapshot.
        source = s.read(candidate.symbols['tone_source'], 12)
        s.write(candidate.symbols['tone_source'], bytes(12))
        copied = call(s, candidate.symbols['hl_owner_to_job'], a0=address, a2=JOB + 14920)
        assert u32(s, JOB + 14944) == SOURCE_WORDS[profile - 1]
        source_hl = HL_PACKED[(profile - 1) * 12:profile * 12]
        assert s.read(JOB + 14920, 24) == bytes(v & 15 for v in source_hl) + bytes(v >> 4 for v in source_hl)
        s.write(candidate.symbols['tone_source'], source)
        reports.append(dict(slot=slot, owner=hex(address), profile=profile,
                            acquisition=acquired, job_helper=copied))
    for profile in (0, 4, 255):
        for slot in (0, 40):
            address = owner(s, slot, profile)
            acquisition(s, address, slot >= 40)
            assert u32(s, candidate.symbols['tone_rows'] + slot * 4) == 0
    for address in (LARGE - 1, LARGE + 1, LARGE + 40 * 41984,
                    COMPACT - 1, COMPACT + 1, COMPACT + 5 * 632, 0, 0x2dafa3c0):
        before = s.read(candidate.symbols['tone_rows'], 180)
        call(s, candidate.symbols['hl_source_to_owner'], a0=address)
        assert s.read(candidate.symbols['tone_rows'], 180) == before
        call(s, candidate.symbols['hl_owner_to_job'], a0=address, a2=JOB + 14920)
        assert u32(s, JOB + 14944) == 0
    _check_guards(s, JOB, 14948)
    return dict(owners=reports, neutral_profiles=6, rejected_owners=8)


def hooks(candidate):
    reports = []
    for route in ('preview', 'recording'):
        states = []
        for reference in (True, False):
            s = setup(candidate, reference=reference)
            address = owner(s, 0, 2)
            acquisition(s, address)
            acquired_regs = dict(s.regs)
            expected = SOURCE_WORDS[1]
            s.write(candidate.symbols['tone_source'], bytes(12))
            report = to_job(s, address, route)
            assert u32(s, JOB + 14944) == (0xa7a7a7a7 if reference else expected)
            states.append((s, acquired_regs))
        old, new = states
        assert old[1] == new[1]
        assert old[0].regs == new[0].regs
        assert old[0].read(JOB, 14944) == new[0].read(JOB, 14944)
        _check_guards(new[0], JOB, 14948)
        reports.append(dict(route=route, native_registers_equal=True, **report))
    return reports


def compact_postcall(candidate):
    reports = []
    for status in (0, 1, 0xffffffff):
        for reference in (True, False):
            s = setup(candidate, reference=reference)
            address = owner(s, 42, 3)
            acquisition(s, address, True)
            put32(s, INITIAL_SP + 12, address)
            put32(s, INITIAL_SP + 1868, JOB)
            report = block(s, candidate.symbols['hl_after_compact_call'], 0x6055a291, d0=status)
            expected = SOURCE_WORDS[2] if status == 0 and not reference else 0xa7a7a7a7
            assert u32(s, JOB + 14944) == expected
            if reference:
                previous = dict(s.regs), s.read(JOB, 14944)
            else:
                assert previous == (s.regs, s.read(JOB, 14944))
        reports.append(dict(status=status, native_registers_equal=True, **report))
    return dict(scope='actual post-call hook continuation; displaced compact setter not modeled or executed', cases=reports)


def raw_acquisition(candidate):
    reports = []
    for mode in (11, 1, 2):
        for loaded in (True, False):
            states = []
            for reference in (True, False):
                s = setup(candidate, reference=reference, loaded=loaded)
                address = owner(s, 3, 2, mode=mode)
                pointer = 0x1a090020
                s.ram('raw_owner_pointer', pointer, struct.pack('<I', address), aliases=False)
                report = block(s, 0x60af2f56, 0x60af2f5c, a2=pointer)
                if loaded and not reference:
                    assert u32(s, candidate.symbols['tone_rows'] + 12) == (SOURCE_WORDS[1] if mode == 11 else 0)
                states.append(s)
            assert states[0].regs == states[1].regs
            assert states[0].read(HL_ROWS, 540) == states[1].read(HL_ROWS, 540)
            reports.append(dict(mode=mode, section8_loaded=loaded, **report))
    return reports


def constructor(candidate):
    s = setup(candidate)
    report = block(s, 0x604c1c0a, 0x604c1c12)
    assert s.regs['d0'] == 14948
    helpers(s)
    zero = block(s, 0x604c1d19, 0x604c1d28, a3=JOB)
    assert s.read(JOB, 14908) == b'\xa7' * 14908
    assert s.read(JOB + 14908, 40) == bytes(40)
    _check_guards(s, JOB, 14948)
    return dict(allocation_request=14948, allocation_prefix=report,
                zero_start=14908, zero_bytes=40, native_zero=zero,
                limitation='full constructor unavailable without saved boot/heap checkpoint; allocator not modeled')


def pipeline(candidate, *, loaded=True, raw=(0, 0, 4, -2, -3), record=0, route='recording'):
    s = setup(candidate, loaded=loaded, processing=True, raw=raw, record=record)
    settings(s)
    set_words(s, SOURCE_WORDS)
    call(s, candidate.symbols['hl_publish'])
    address = owner(s, record % 40, record % 3 + 1)
    acquisition(s, address)
    call(s, candidate.symbols['hl_publish'])
    to_job(s, address, route)
    word = SOURCE_WORDS[record % 3] if loaded else 0
    assert u32(s, JOB + 14944) == word
    helpers(s)
    reenter(s, 0x604f8543, 0xf0, 40, dict(PRESERVED, a0=CONTEXT))
    s.write(INITIAL_SP + 64, GUARD)
    report = _finish(s, s.run({CALLER + 7}, limit=300000))
    output = s.read(OUTPUT, 5212)
    pointer = struct.unpack_from('<I', output, 4656)[0]
    actual = struct.unpack('<256H', s.read(pointer, 512))
    # Native reference is separately executed, never replaced by a host spline.
    stock = setup(candidate, reference=True, processing=True, raw=raw, record=record)
    helpers(stock)
    reenter(stock, 0x604f8543, 0xf0, 40, dict(PRESERVED, a0=CONTEXT))
    _finish(stock, stock.run({CALLER + 7}, limit=300000))
    old_pointer = u32(stock, OUTPUT + 4656)
    old = struct.unpack('<256H', stock.read(old_pointer, 512))
    if loaded:
        _, (lo, hi) = stock_signal(identity_lut(), raw)
        black, white = word & 1023, word >> 10 & 1023
        expected = endpoint_oracle(old, ToneEndpoints(min(black, old[lo]), max(white, old[hi]), lo, hi))
        assert actual == expected and actual[lo:hi + 1] == old[lo:hi + 1]
    else:
        assert output == stock.read(OUTPUT, 5212)
    assert s.regs['d0'] == stock.regs['d0']
    _check_guards(s, JOB, 14948)
    _check_guards(s, OUTPUT, 5212)
    assert s.read(LUT, 512) == struct.pack('<256H', *identity_lut())
    uploaded = upload_result(dict(state=s, lut=actual), record % 2)
    return dict(record=record, route=route, section8_loaded=loaded, word=word,
                endpoints=list(actual[::255]), builder=report, upload=uploaded)



def entry_compatibility(candidate):
    cases = [dict(endpoint_word=word) for word in (0, 0xffffffff, packed(0, 1023))]
    cases += [dict(endpoint_word=packed(70, 950), **kw) for kw in
              (dict(callback=0), dict(parent=JOB + 4), dict(mode_prefix=1),
               dict(record_offset=1849), dict(bypass=True),
               dict(custom=False, selection_stop=True), dict(null_lut=True))]
    reports = []
    for options in cases:
        states = []
        for reference in (True, False):
            s = setup(candidate, reference=reference, processing=True,
                      raw=(0, 0, 0, 0, 0) if options.get('null_lut') else (0, 0, 4, -2, -3), **options)
            helpers(s)
            outer = bool(options.get('bypass'))
            reenter(s, 0x604f8543 if outer else 0x604f7c76, 0xf0, 40 if outer else 28, dict(PRESERVED, a0=CONTEXT))
            report = _finish(s, s.run({CALLER + 7}, limit=300000))
            states.append((s.read(OUTPUT, 5212), s.read(CONTEXT, 192), s.regs['d0']))
        assert states[0] == states[1], options
        reports.append(dict(options=options, exact_native_result=True, checks=report))
    return reports



def acquisition_abi(candidate):
    reports = []
    for slot in (0, 40):
        states = []
        for reference in (True, False):
            s = setup(candidate, reference=reference)
            address = owner(s, slot, 3)
            report = acquisition(s, address, slot >= 40)
            states.append((dict(s.regs), s.read(HL_ROWS, 540)))
        assert states[0] == states[1]
        reports.append(dict(slot=slot, native_registers_equal=True, **report))
    return reports


def alternative_path(candidate):
    reports = []
    for selected in (False, True):
        states = []
        for reference in (True, False):
            s = setup(candidate, reference=reference, processing=True,
                      endpoint_word=packed(70, 950))
            if selected:
                s.write(JOB + 12228 + 576, struct.pack('<H', 257))
            reenter(s, 0x604f7d22, 0x20, 8, dict(PRESERVED, a0=CONTEXT))
            report = _finish(s, s.run({CALLER + 7}, limit=300000))
            output = s.read(OUTPUT, 5212)
            states.append((output, s.regs['d0']))
        assert states[0] == states[1]
        reports.append(dict(selected_table=selected, pointer=hex(struct.unpack_from('<I', output, 4656)[0]),
                            exact_native_result=True, checks=report))
    return reports


def audit(candidate):
    return dict(publication=publication(candidate), owners=owner_matrix(candidate),
                hooks=hooks(candidate), acquisition_abi=acquisition_abi(candidate),
                compatibility=entry_compatibility(candidate), alternative_path=alternative_path(candidate),
                compact=compact_postcall(candidate),
                raw=raw_acquisition(candidate), constructor=constructor(candidate),
                pipeline=[pipeline(candidate, record=i, route='preview' if i % 2 else 'recording') for i in range(16)] +
                         [pipeline(candidate, loaded=False, raw=raw) for raw in ((0, 0, 0, 0, 0), (0, 0, 4, -2, -3))],
                engine_sha256=sha(ENGINE.read_bytes()),
                limits=['Synthetic RAM and single-thread execution; no camera or flash access.',
                        'Full constructor and compact setter unavailable: bounded native blocks are explicit.',
                        'UI/default/reset routing and nonvolatile commit are not yet integrated.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    args = parser.parse_args()
    candidate = build_candidate(args.out / 'candidate')
    result = audit(candidate)
    (args.out / 'audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(owners=len(result['owners']['owners']), banks=9,
                         pipelines=len(result['pipeline']), constructor=result['constructor']), indent=2))


if __name__ == '__main__':
    main()
