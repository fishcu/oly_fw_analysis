#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native COLOR compound selection and registered recall contracts.

The boot checkpoint predates three MCON registries. Initialize all three,
then use native public-value conversion for compound settings. Additional
captured RAM extents are bounded and reviewed; no peripheral success models.
"""
import argparse
import json
from pathlib import Path
import struct

from penf_profile_followup_probe import (
    ACTIVE, BANKS, BASE, BUFFER, CALLER, CHECKPOINT_SHA, COLOR, DEFAULT_IMAGE,
    DEFAULT_OBJDUMP, ENGINE, Fixture, LIVE, OUTPUT, STRIDE, WORDS, WORKING,
    at, bank_word, color_values, get, invoke, put, returned, sha,
    state as prior_state, window, words,
)

SCHEMA_INIT = 0x602c6c37
REVIEWED_RAM = ((0x61c69314, 12), (0x61c6bca0, 6), (0x61c874f0, 52),
                (0x618d271c, 4), (0x61b9dafc, 24), (0x61c28154, 112))


def state(f):
    s = prior_state(f)
    # Three recording diagnostic enable/selector pairs, recording-mode state,
    # one file-counter record, and a TAKE_EXPOSE debug mask. Captured zeroes are
    # not a card-present model. The last two ranges hold initialized settings
    # store/default pointers and four exact 28-byte object descriptors.
    for address, size in REVIEWED_RAM:
        s.ram(f'captured_reviewed_{address:x}', address, f.read(address, size))
    returned(s, invoke(s, SCHEMA_INIT, 0xb0, 12))
    return s


def public_get(s, key):
    r = invoke(s, 0x602bad3f, 0, 0, dict(d0=key))
    returned(s, r)
    return r['result']


def fixture_public_set(s, key, value):
    # Actual conversion + storage, deliberately without callbacks/dependencies.
    # This is fixture preparation, not the tested user-edit route.
    returned(s, invoke(s, 0x602bae0f, 0xe0, 16,
                       dict(d0=key, d1=value & 0xffffffff)))


def selected(s, profile):
    fixture_public_set(s, 111, 53+profile)
    fixture_public_set(s, 910, 53+profile)
    for key, value in ((906, 910), (1083, 910), (44, 0), (109, 0)):
        put(s, key, value)
    # Picture-mode availability flags are still zero in the partial-boot
    # capture. Make COLOR1/2/3 explicitly available in this scenario.
    for key in (1048, 1049, 1050):
        put(s, key, 1)
    for key, value in zip(COLOR, color_values(2)):
        put(s, key, value)
    assert get(s, 111) == 11 and get(s, 912) == profile
    assert get(s, 910) == 11 and get(s, 1086) == profile
    assert public_get(s, 111) == public_get(s, 910) == 53+profile


def resume(s, stops, limit=20000000):
    before = s.steps
    r = s.run(set(stops), limit=limit)
    return dict(status=r['status'], pc=hex(s.regs['pc']), fault=r.get('fault'),
                instructions=s.steps-before, modeled_functions=[])


def current_record(f, s, key):
    """Read the pinned directory's scalar without disturbing a stopped stack."""
    record, index = struct.unpack_from('<HH', f.image, 0x603fa158-BASE+4*key)
    row = f.records[record]
    width = record & 7
    return int.from_bytes(s.read(int(row['address'], 0)+index*width, width),
                          'little', signed=bool(record & 8))


def native_block(s, start, end, regs, stack_words=()):
    # Explicit interior-block contract, not a whole-function invocation.
    s.regs = dict(pc=start, sp=0x18018000, psw=0, **regs)
    for offset, value in stack_words:
        s.write(s.regs['sp']+offset, struct.pack('<I', value))
    r = resume(s, (end,))
    at(s, r, end)
    return r


def image_snapshot(f, s, expected):
    """Join exact copy blocks to the complete request packer and HSL selector.

    The large capture object's allocation/event ingress is not emulated.
    Two interior blocks receive the register/stack contracts shown by their
    enclosing functions. Subsequent packer and HSL selector execute in full.
    """
    capture, job, request, context, coefficients = (
        0x21000000, 0x21010000, 0x21020000, 0x21021000, 0x21022000)
    s.ram('synthetic_capture_parameters', capture, bytes(22080), aliases=False)
    s.ram('synthetic_picture_job', job, bytes(14000), aliases=False)
    s.ram('synthetic_picture_request', request, bytes(1132), aliases=False)
    s.ram('synthetic_HSL_context', context, bytes(192), aliases=False)
    s.ram('synthetic_coefficients', coefficients, bytes(5632), aliases=False)
    s.write(BUFFER, struct.pack('<I', capture))
    before = tuple(current_record(f, s, k) for k in range(919, 931))
    assert before == tuple(expected)
    first = native_block(s, 0x60253b36, 0x60253c7f, dict(d2=capture))
    assert s.read(capture+18595, 1) == b'\x0b'
    assert struct.unpack('<12h', s.read(capture+18600, 24)) == tuple(expected)
    # A later profile change must not alter an already copied parameter block.
    for key in range(919, 931):
        put(s, key, 5)
    s.write(job+12, b'\x00\x00\x0b\x00')  # supplied group/type/mode fields
    second = native_block(s, 0x6052056e, 0x605205f9, dict(d3=BUFFER),
                          ((4, job+36),))
    assert struct.unpack('<12b', s.read(job+36+5684, 12)) == tuple(expected)
    packed = invoke(s, 0x604c3051, 0xf0, 28, dict(a0=job, a1=request, d0=0))
    returned(s, packed)
    assert s.read(request+8, 4) == b'\x00\x00\x0b\x00'
    assert struct.unpack('<12b', s.read(request+1076, 12)) == tuple(expected)
    s.write(context+4, struct.pack('<4I', request, 0, coefficients, coefficients+5212))
    s.write(context+56, struct.pack('<I', 0xffffffff))
    s.write(context+100, struct.pack('<I', 0xffffffff))
    built = invoke(s, 0x604f747f, 0xf0, 20, dict(a0=context))
    returned(s, built)
    assert struct.unpack('<I', s.read(coefficients+0x3c4, 4))[0] == 0x0fff
    records = [list(struct.unpack('<6I', s.read(coefficients+0x2a4+i*24, 24)))
               for i in range(12)]
    gain_pointers = struct.unpack_from('<12I', f.image, 0x6062fef8-BASE)
    observed = []
    for sector, value in enumerate(expected):
        record = (sector % 2)*6+sector//2
        source = 0x60622d74+record*28-BASE
        amplitude = struct.unpack_from('<h', f.image, source+14)[0]
        gain = struct.unpack_from('<H', f.image, gain_pointers[record]-BASE+2*(value < 0))[0]
        numerator = ((amplitude*gain) >> 8)*value
        calculated = (1 if numerator >= 0 else -1)*(abs(numerator)//5)
        observed_S = struct.unpack('<h', s.read(coefficients+0x2a4+record*24+20, 2))[0]
        assert observed_S == calculated
        assert s.read(coefficients+0x2a4+record*24+18, 2) == f.image[source+12:source+14]
        assert s.read(coefficients+0x2a4+record*24+22, 2) == f.image[source+16:source+18]
        observed.append(dict(sector=sector, table_record=record, input=value, coefficient=observed_S))
    return dict(effective_values=before, capture_copy_block=first,
                word_to_byte_copy_block=second, request_packer=packed,
                HSL_selector=built, records=records, saturation_coefficients=observed,
                later_current_values_changed=True, snapshot_values_preserved=True,
                scope='Explicit interior copy contracts plus complete request packer/selector; no outer job scheduler or ISP')


def registration(f):
    s = prior_state(f)
    assert s.read(0x618872c0, 128*4) == bytes(128*4)
    before, after = {}, {}
    for key in (111, 906, 910, 912, 1086, 931):
        r = invoke(s, 0x602c67c5, 0, 4, dict(d0=key))
        returned(s, r)
        before[key] = r['result']
        assert r['result'] == 0
    initialization = invoke(s, SCHEMA_INIT, 0xb0, 12)
    returned(s, initialization)
    for key, expected in ((111, 1), (906, 2), (910, 1), (912, 2), (1086, 0), (931, 2)):
        r = invoke(s, 0x602c67c5, 0, 4, dict(d0=key))
        returned(s, r)
        after[key] = r['result']
        assert r['result'] == expected
    return dict(before=before, after=after, initialization=initialization,
                descriptor_table='0x603dffcc', descriptor_count=968,
                descriptor_stride=20, hash='0x618872c0')


def selection(f):
    cases = []
    for target in (1, 2, 3):
        s = state(f)
        selected(s, target % 3+1)
        r = invoke(s, 0x602b9f33, 0xc0, 16, dict(d0=910, d1=53+target),
                   stops=(0x602c50be,))
        at(s, r, 0x602c50be)
        assert (s.regs['d0'], s.regs['d1']) == (0, 53+target)
        # Inspect public values only after the native prefix is complete;
        # these calls replace the stack, so do not resume this scenario later.
        assert public_get(s, 111) == public_get(s, 910) == 53+target
        assert get(s, 912) == get(s, 1086) == target
        assert get(s, 111) == get(s, 910) == 11
        cases.append(dict(target=target, effective_public_mode=53+target,
                          raw_picture_mode=11, **r))
    # Negative/sensitivity control: writing just the editor's scalar profile
    # changes how compound 111 decodes, but has no registered refresh itself.
    s = state(f)
    selected(s, 1)
    r = invoke(s, 0x602b9f33, 0xc0, 16, dict(d0=912, d1=2), stops=(0x602c50be,))
    returned(s, r)
    assert public_get(s, 111) == 55 and public_get(s, 910) == 54
    return dict(compound_switches=cases,
                scalar_only_control=dict(**r, effective_public_mode=55,
                                         COLOR_source_public_mode=54,
                                         refresh_reached=False))


def availability(f):
    cases = []
    for enabled in (False, True):
        s = state(f)
        selected(s, 3)
        put(s, 1050, int(enabled))
        returned(s, invoke(s, 0x602f0a2c, 0xf0, 20))
        returned(s, invoke(s, 0x602f0b12, 0, 4))
        r = invoke(s, 0x602c2f42, 0, 4)
        returned(s, r)
        expected = 3 if enabled else 1
        actual = words(s, 0x61896ee0+1086*4, 1)[0]
        assert actual == expected
        cases.append(dict(COLOR3_enabled=enabled, applied_staged_profile=actual, **r))
    return dict(availability_ids=[1048, 1049, 1050],
                callback_descriptor_id=346, staged_callback='0x602c2f42', cases=cases)


def persistence(f):
    s = state(f)
    selected(s, 3)
    initial = s.read(WORKING, 0x20000)
    s.ram('Mode_backing_RAM_fixture', 0x61ef2c00, initial)
    witnesses = []
    for bank in range(9):
        address = BANKS+bank*STRIDE+(WORDS+931)*4
        value = bytes((bank*19+i) & 255 for i in range(144))
        s.write(address, value)
        witnesses.append((address, value))
    active_address = ACTIVE+(WORDS+931)*4
    active_value = bytes((241+i) & 255 for i in range(144))
    s.write(active_address, active_value)
    witnesses.append((active_address, active_value))
    put(s, 931, -4)
    prepared = invoke(s, 0x600733d8, 0xf0, 24, dict(a0=0xa1c281a8),
                      stops=(0x600720e1,))
    at(s, prepared, 0x600720e1)
    assert (s.regs['d0'], s.regs['d1'], s.regs['a0'], s.regs['a1']) == (
        0x20000, 0, WORKING, 0xa1ef2c00)
    envelope = s.read(WORKING, 0x20000)
    assert sum(struct.unpack('<65536H', envelope)) & 65535 == 0
    assert s.read(0x61ef2c00, 0x20000) == initial
    # Separate load experiment: transfer the prepared bytes to RAM explicitly.
    # Never resume the programming wrapper or substitute successful storage IO.
    s.write(0x61ef2c00, envelope)
    s.write(WORKING, bytes([0xa5])*0x20000)
    loaded = invoke(s, 0x6007333e, 0xb0, 20, dict(a0=0xa1c281a8))
    returned(s, loaded)
    assert loaded['result'] == 0
    assert s.read(WORKING, 0x20000) == envelope
    assert all(s.read(address, len(value)) == value for address, value in witnesses)
    assert words(s, LIVE+931*4, 1)[0] == -4
    assert current_record(f, s, 931) == -4
    # Native wait helper used by the shutdown wrappers: status zero is an
    # immediate return, not a retry or deferred programming invocation.
    outer_wait = invoke(s, 0x607609d4, 0xf0, 60,
                        dict(d0=0, d1=0xffffffff, a0=0x602f0d18))
    assert outer_wait['status'] == 'memory_fault', outer_wait
    assert outer_wait['pc'] == '0x60086c0b'
    # Its object constructor requires kernel context even for zero status.
    # Isolate the complete inner wait function to test only its status policy.
    wait = invoke(s, 0x607609f3, 0xf0, 36,
                  dict(d0=0, d1=0xffffffff, a0=BUFFER, a1=0x602f0d18))
    returned(s, wait)
    assert wait['result'] == 0
    return dict(write_preparation=prepared, separate_RAM_reload=loaded,
                outer_wait_strict_stop=outer_wait, inner_zero_status_wait=wait,
                saved_banks_preserved=9,
                active_candidate_preserved=True, current_and_live_preserved=True,
                entire_128KiB_envelope_preserved=True,
                scope='Native prepare and separate RAM load; no programming, physical persistence or full shutdown')


def shutdown_store(f):
    s = state(f)
    selected(s, 3)
    base, size = 0x61b6bac0, 0x10000
    blob = bytearray(f.read(base, size))
    replaced = []
    # Expand three previously mapped records to their declared type-36 store,
    # retaining every current overlay. This is one identified 64-KiB object.
    for region in s.regions:
        if 'w' not in region.permissions:
            continue
        address = region.address
        if 0xa0000000 <= address < 0xc0000000:
            address -= 0x40000000
        if base <= address and address+len(region.data) <= base+size:
            blob[address-base:address-base+len(region.data)] = s.read(region.address, len(region.data))
            replaced.append(region.name)
    s.regions = [r for r in s.regions if r.name not in replaced]
    s.ram('captured_type36_working', base, blob)
    s.ram('type36_backing_RAM', 0x61f12c00, blob)
    initial_mode = s.read(WORKING, 0x20000)
    s.ram('Mode_backing_RAM', 0x61ef2c00, initial_mode)
    witness = bytes(range(144))
    s.write(ACTIVE+(WORDS+931)*4, witness)
    s.write(BUFFER, struct.pack('<6H', 1, 0, 0, 1, 1, 0))
    # Native character logger supports suppression through these two controls.
    # It still executes its native return-status getter; no logger is stubbed.
    s.ram('captured_logger_status', 0x61c552c8, f.read(0x61c552c8, 1))
    s.write(0x615fc816, struct.pack('<2H', 1, 0))
    r = invoke(s, 0x6007561f, 0xa0, 16, dict(a0=BUFFER),
               stops=(0x600720e1,), limit=4000000)
    at(s, r, 0x600720e1)
    assert (s.regs['d0'], s.regs['d1'], s.regs['a0'], s.regs['a1']) == (
        0x20000, 0, WORKING, 0xa1ef2c00)
    assert s.read(0x61f12c00, size) == blob
    assert s.read(0x61ef2c00, 0x20000) == initial_mode
    assert s.read(ACTIVE+(WORDS+931)*4, 144) == witness
    # Recover the actual firmware name of the static caller route.
    name_lookup = invoke(s, 0x606bc2c2, 0x80, 4, dict(d0=0x10102))
    returned(s, name_lookup)
    name = s.read_c_string(s.regs['a0']).decode('ascii')
    assert name == 'CameraCommon::shutDown'
    return dict(store_dispatch=r, request=[1, 0, 0, 1, 1, 0],
                type36_unchanged=True, candidate_active_change_reaches_Mode_program_wrapper=True,
                backing_RAM_unchanged=True, logger_controls=[1, 0],
                replaced_type36_regions=replaced, caller_name=name,
                caller_name_lookup=name_lookup,
                scope='Native storage dispatcher; application shutdown chain reviewed statically, not executed end to end')


def processing(f):
    packed, dispatch, refreshed = [], [], []
    for context in (0, 1):
        for profile in (1, 2, 3):
            s = state(f)
            selected(s, profile)
            if context:
                returned(s, invoke(s, 0x602f0a2c, 0xf0, 20))
                returned(s, invoke(s, 0x602f0b12, 0, 4))
                for key in COLOR:
                    put(s, key, 5)
            expected = color_values(2)[12*(profile-1):12*profile]
            r = invoke(s, 0x602c414a, 0xf0, 168,
                       dict(d0=context, d1=53+profile, a0=OUTPUT))
            returned(s, r)
            assert words(s, OUTPUT+80, 12) == expected
            packed.append(dict(context=context, profile=profile, values=expected, **r))
            if context:
                r = invoke(s, 0x602c50be, 0x80, 160, dict(d0=1, d1=53+profile))
                returned(s, r)
                actual = []
                for key in range(919, 931):
                    q = invoke(s, 0x602f0786, 0, 0, dict(d0=key))
                    returned(s, q)
                    v = q['result']
                    actual.append(v if v < 0x80000000 else v-0x100000000)
                assert tuple(actual) == expected
                refreshed.append(dict(profile=profile, derived_staged_S=actual, **r))
    for active in (1, 2, 3):
        for edited in (1, 2, 3):
            s = state(f)
            selected(s, active)
            s.write(0x615fd38c, struct.pack('<I', 0x6075fedb))
            key = 931+12*(edited-1)
            r = invoke(s, 0x602b9f33, 0xc0, 16, dict(d0=key, d1=5),
                       stops=(0x602c50be,))
            if active == edited:
                at(s, r, 0x602c50be)
                assert (s.regs['d0'], s.regs['d1']) == (0, 53+active)
            else:
                returned(s, r)
            assert get(s, key) == 5
            dispatch.append(dict(active=active, edited=edited, refresh=active == edited, **r))
    s = state(f)
    selected(s, 1)
    strict = invoke(s, 0x602b9f33, 0xc0, 16, dict(d0=931, d1=5))
    assert strict['status'] == 'memory_fault', strict
    return dict(packed=packed, dispatch=dispatch, staged_refresh=refreshed,
                strict_current_edit=strict)


def capture_prefix(f):
    s = state(f)
    selected(s, 3)
    capture = 0x21000000
    s.ram('synthetic_registered_capture', capture, bytes(22080), aliases=False)
    s.ram('captured_base_capture_parameters', 0x618bb6b8, f.read(0x618bb6b8, 22080))
    # Native slot accessor checks index 1..40 and allocated bit 4, then returns
    # slot+12. Allocation itself is supplied, not proved by this prefix.
    s.ram('synthetic_capture_slot_1', 0x618689b8+20,
          struct.pack('<5I', 4, 0, 0, capture, 0))
    records = []
    for key, address, size in ((0xc2da, 0x61ae9390, 2),
                               (0xc2ca, 0x61ae9388, 2),
                               (0xc0d1, 0x61ae92b4, 1)):
        actual, count, pointer = struct.unpack('<HHI', f.read(0x61c281e4+(key >> 4)*8, 8))
        assert (actual, pointer, count*(key & 7)) == (key, address, size)
        s.ram(f'captured_capture_record_{key:x}', address, f.read(address, size))
        records.append(dict(key=hex(key), address=hex(address), bytes=size))
    r = invoke(s, 0x6025350c, 0xb0, 16, dict(d0=1), limit=2000000)
    assert r['status'] == 'memory_fault' and r['pc'] == '0x605de5d5', r
    assert r['fault']['address'] == 0x618d2678
    return dict(strict_prefix=r, extra_captured_records=records,
                capture_size=22080, allocated_slot_supplied=True,
                COLOR_copy_reached=False, scope='Whole capture-population entry; stops on exposure state before COLOR copy')


def exposure_owner(f):
    s = state(f)
    selected(s, 3)
    descriptor = struct.unpack_from('<7I', f.image, 0x6003a438-BASE)
    assert descriptor == (123, 0, 0, 0x605d8230, 25, 0x600, 0)
    s.ram('TAKE_EXPOSE_state_pointer', 0x618d2668, f.read(0x618d2668, 4))
    s.ram('captured_exposure_flags', 0x61c89e91, f.read(0x61c89e91, 2))
    # Keep the task's long-lived frame separate from the probe caller stack.
    s.ram('TAKE_EXPOSE_separate_stack', 0x21030000, bytes(0x1000), aliases=False)
    s.regs = dict(pc=0x605d8230, sp=0x21030ff0, psw=0)
    prefix = resume(s, (0x605d827f,), limit=1000)
    at(s, prefix, 0x605d827f)
    pointer = struct.unpack('<I', s.read(0x618d2668, 4))[0]
    assert pointer == s.regs['sp']+20 == 0x21030fac
    assert s.read(pointer, 5) == bytes(5)
    # Stop before queue receive. This does not launch or schedule task123.
    calculate = invoke(s, 0x605dd526, 0x80, 8, limit=100000)
    assert calculate['status'] == 'memory_fault' and calculate['pc'] == '0x60037fae', calculate
    assert calculate['fault']['address'] == 0x61835820
    assert calculate['stop_registers']['d3'] == 26
    assert s.read(pointer, 5) == bytes(5)
    return dict(task_id=123, descriptor='0x6003a438', task_entry='0x605d8230',
                state_pointer='0x618d2668', native_initialized_stack_state=hex(pointer),
                initialized_bytes=5, prefix=prefix, calculate_continuation=calculate,
                semaphore_id=26, scope='Task initialization prefix and separate calculate entry; no task activation, queue delivery or exposure result')


def paired_saves(f):
    cases = []
    for index in range(4):
        s = state(f)
        profile = index % 3+1
        selected(s, profile)
        values = color_values(2)
        witness = bytes((index*17+i) & 255 for i in range(144))
        s.write(ACTIVE+(WORDS+931)*4, witness)
        before = s.read(BANKS, STRIDE*9)
        r = invoke(s, 0x6075fb08, 0x80, 8, dict(d0=index))
        returned(s, r)
        banks = (index+1, index+5)
        after = s.read(BANKS, STRIDE*9)
        for bank in range(9):
            if bank not in banks:
                assert after[bank*STRIDE:(bank+1)*STRIDE] == before[bank*STRIDE:(bank+1)*STRIDE]
            else:
                assert words(s, BANKS+bank*STRIDE+931*4, 36) == values
                assert words(s, BANKS+bank*STRIDE+912*4, 1)[0] == profile
                assert words(s, BANKS+bank*STRIDE+1086*4, 1)[0] == profile
                assert s.read(BANKS+bank*STRIDE+(WORDS+931)*4, 144) == witness
        # A registered inactive-profile edit returns without a processing
        # notification and must not silently re-save either custom bank.
        key = 943 if profile == 1 else 931
        edit = invoke(s, 0x602b9f33, 0xc0, 16, dict(d0=key, d1=5))
        returned(s, edit)
        assert get(s, key) == 5
        assert s.read(BANKS, STRIDE*9) == after
        cases.append(dict(input_index=index, banks=banks, save=r,
                          inactive_edit=edit, candidate_copied_to_pair=True,
                          unrelated_banks_preserved=True, later_edit_does_not_resave=True))
    return cases


def destination_fixture(s, destination):
    destination_values = color_values(6)
    for key, value in ((24, 4), (26, 4), (43, 4), (109, 0), (912, 3),
                       (111, 11), (1083, 910), (906, 910), (910, 11), (1086, 3),
                       (1048, 1), (1049, 1), (1050, 1)):
        bank_word(s, destination, key, value)
    for key, value in zip(COLOR, destination_values):
        bank_word(s, destination, key, value)
    witness = bytes((i+19*destination) & 255 for i in range(144))
    s.write(BANKS+destination*STRIDE+(WORDS+931)*4, witness)
    return destination_values, witness


def recall(f, source, destination):
    s = state(f)
    selected(s, 1)
    put(s, 41, source)
    destination_values, witness = destination_fixture(s, destination)
    source_before = s.read(BANKS+source*STRIDE, STRIDE)
    r = invoke(s, 0x602ba07b, 0xc0, 16,
               dict(d0=destination+48 if destination else 2),
               stops=(0x602bd7f9,), limit=20000000)
    at(s, r, 0x602bd7f9)
    changed = struct.unpack(f'<{s.regs["d2"]}H', s.read(s.regs['a2'], s.regs['d2']*2))
    assert s.read(ACTIVE+(WORDS+931)*4, 144) == witness
    assert words(s, LIVE+931*4, 36) == destination_values
    assert tuple(current_record(f, s, k) for k in COLOR) == destination_values
    expected_effective = destination_values[24:36]
    assert tuple(current_record(f, s, k) for k in range(919, 931)) == expected_effective
    assert s.read(0x6189a4b0, 1) == b'\0'
    if source:
        assert s.read(BANKS+source*STRIDE, STRIDE) == source_before
    else:
        assert words(s, BANKS+931*4, 36) == color_values(2)
    # Resume original stack, preserving the evidence from the commit boundary.
    continuation = resume(s, (CALLER+7,))
    snapshot = image_snapshot(f, s, expected_effective)
    return dict(source=source, destination=destination, commit=r,
                changed_ids=changed, candidate_part1_preserved=True,
                all_36_S_committed=True, settings_lock_released=True,
                leaving_custom_preserves_saved_source=bool(source),
                post_commit_continuation=continuation, image_snapshot=snapshot)


def temporary_recall(f):
    cases = []
    for name, entry, frame, destination in (
            ('MyMode', 0x602ba1bd, 20, 1),
            ('ShortcutMyset', 0x602ba0fb, 16, 5)):
        s = state(f)
        selected(s, 1)
        values, witness = destination_fixture(s, destination)
        r = invoke(s, entry, 0xc0, frame, dict(d0=53),
                   stops=(0x602bce20,), limit=20000000)
        if name == 'MyMode':
            # Before the shared staging/commit: restoring ID86 requests a
            # exposure action whose initialized task state is absent here.
            assert r['status'] == 'memory_fault' and r['pc'] == '0x605dd54b', r
            assert r['fault']['address'] == 0x618d2668
            assert s.read(ACTIVE+(WORDS+931)*4, 144) == witness
            cases.append(dict(route=name, destination=destination, strict_prefix=r,
                              candidate_loaded_into_active=True, RAM_commit_reached=False))
            continue
        at(s, r, 0x602bce20)
        assert s.read(ACTIVE+(WORDS+931)*4, 144) == witness
        assert tuple(current_record(f, s, k) for k in COLOR) == values
        assert tuple(current_record(f, s, k) for k in range(919, 931)) == values[24:36]
        assert s.read(0x6189a4b0, 1) == b'\0'
        continuation = resume(s, (CALLER+7,))
        cases.append(dict(route=name, destination=destination, commit=r,
                          candidate_part1_preserved=True, all_36_S_committed=True,
                          settings_lock_released=True,
                          post_commit_continuation=continuation,
                          current_bank_at_stop=current_record(f, s, 41),
                          temporary_indicator_at_stop=current_record(f, s, 569)))
    return cases


def evidence(f, out):
    spans = {
        'application-registration': (0x602ba469, 0x602ba4f0),
        'compound-public-value': (0x602bad3f, 0x602bae66),
        'schema-registration': (0x602c6c37, 0x602c6cd0),
        'availability-key': (0x602c0af6, 0x602c0b2a),
        'availability-callback': (0x602c2d63, 0x602c2f4f),
        'COLOR-availability-fallback': (0x602c3072, 0x602c30f6),
        'staged-refresh-callback': (0x602c320c, 0x602c3226),
        'precommit-callback-loop': (0x602bbf60, 0x602bbf8a),
        'dial-and-temporary-public-recall': (0x602ba07b, 0x602ba24d),
        'temporary-staging-commit': (0x602bcd16, 0x602bce30),
        'dial-staging-commit': (0x602bd5f0, 0x602bd82a),
        'capture-slot-accessor': (0x60249c22, 0x60249c68),
        'capture-base-copy': (0x6054c52b, 0x6054c53e),
        'capture-population': (0x6025350c, 0x60253dd3),
        'capture-to-job-conversion': (0x6052010f, 0x605206a7),
        'alternate-capture-COLOR-copy': (0x6055761d, 0x605577c5),
        'request-packing': (0x604c3051, 0x604c3260),
        'HSL-selection': (0x604f7272, 0x604f7572),
        'store-load-and-prepare': (0x6007333e, 0x60073571),
        'store-dispatch': (0x6007561f, 0x6007582c),
        'store-application-wrapper': (0x602f0d18, 0x602f0e04),
        'shutdown-store-sequence': (0x606efb9e, 0x606efd27),
        'shutdown-outer-sequence': (0x606efd27, 0x606f0376),
        'shutdown-named-interface': (0x606f6263, 0x606f62ce),
        'wait-status-policy': (0x607609d4, 0x60760a87),
        'character-logger-policy': (0x600230a7, 0x6002311f),
        'temporary-recall-exposure-boundary': (0x605dd526, 0x605dd60d),
        'exposure-task-state-owner': (0x605d8230, 0x605d84a0),
        'exposure-state-reset': (0x605d76b6, 0x605d7807),
        'exposure-capture-getters': (0x605de5c2, 0x605de5e8),
    }
    directory = out/'disassembly'
    directory.mkdir()
    inventory = []
    for name, (start, end) in spans.items():
        (directory/(name+'.asm')).write_text(window(f.image, DEFAULT_IMAGE, DEFAULT_OBJDUMP, start, end))
        inventory.append(dict(name=name, start=hex(start), end_exclusive=hex(end),
                              native_bytes_sha256=sha(f.image[start-BASE:end-BASE])))
    return inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path('analysis/profile_context/verified'))
    parser.add_argument('--group', choices=('all', 'selection', 'processing', 'recall', 'persistence'), default='all')
    args = parser.parse_args()
    if args.out.exists():
        parser.error('Use a fresh output directory to preserve previous evidence')
    args.out.mkdir(parents=True)
    f = Fixture()
    report = dict(main_sha256=sha(f.image), checkpoint_sha256=CHECKPOINT_SHA,
                  engine_sha256=sha(ENGINE.read_bytes()),
                  source_sha256={str(p): sha(p.read_bytes()) for p in (
                      Path(__file__), Path('tools/penf_profile_followup_probe.py'),
                      Path('tools/penf_profile_lifecycle_probe.py'), Path('tools/penf_probe.py'),
                      Path('tools/penf_emulator.py'), Path('tools/penf_boot_emulator.py'),
                      Path('tools/penf_disasm.py'), Path('tools/penf_diagnostic_lifetime_probe.py'),
                      Path('tools/penf_color_controls_probe.py'))},
                  assumptions=['CPU0 and captured diagnostic task 47',
                               'three native MCON registries initialized',
                               'native conversion/storage without callbacks for scenario preparation',
                               'explicit A-mode COLOR fixture',
                               'COLOR availability flags 1048/1049/1050 explicitly enabled except negative control',
                               'bounded captured file counters, no media-presence claim'],
                  reviewed_captured_RAM=[dict(address=hex(a), size=n) for a, n in REVIEWED_RAM],
                  camera_used=False, nonvolatile_write=False)
    report['registration'] = registration(f)
    if args.group in ('all', 'selection'):
        report['selection'] = selection(f)
        report['availability'] = availability(f)
        print('Compound selection passed', flush=True)
    if args.group in ('all', 'processing'):
        report['processing'] = processing(f)
        report['capture_outer'] = capture_prefix(f)
        report['exposure_owner'] = exposure_owner(f)
        print('Schema-aware processing passed', flush=True)
    if args.group in ('all', 'recall'):
        report['recall'] = []
        for source, destination in ((0, 5), (5, 6), (5, 0)):
            report['recall'].append(recall(f, source, destination))
            print(f'Registered recall {source}->{destination} committed', flush=True)
        report['temporary_recall'] = temporary_recall(f)
        print('Temporary recall RAM commits passed', flush=True)
    if args.group in ('all', 'persistence'):
        report['persistence'] = persistence(f)
        report['paired_saves'] = paired_saves(f)
        report['shutdown_store'] = shutdown_store(f)
        print('Mode envelope preparation and RAM reload passed', flush=True)
    report['code_windows'] = evidence(f, args.out)
    (args.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(args.out/'report.json')


if __name__ == '__main__':
    main()
