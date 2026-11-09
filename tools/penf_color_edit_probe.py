#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Bounded native COLOR edit contracts; no firmware or camera writes.

Join the selected editor FSM to its real property controls and setting API.
Preserve the strict asynchronous-refresh stop. Viewer and capture checks are
separate invocations, not a claim that the event loop or camera boot completes.
"""
import argparse
import json
from pathlib import Path
import struct

from penf_profile_context_probe import (
    BASE, BUFFER, CALLER, CHECKPOINT_SHA, COLOR, DEFAULT_IMAGE, DEFAULT_OBJDUMP,
    ENGINE, Fixture, at, current_record, image_snapshot, invoke, put, resume,
    returned, selected, sha, state, window,
)

FSM, CONTROLLER, PARENT, VIEWER = (0x19000000 + i*0x1000 for i in range(4))
PROPERTY, LOGGER, MODE, DEBUG = (0x19030000 + i*0x1000 for i in range(4))
COMMON, BACKGROUND = 0x19036000, 0x19038000
SATURATION, CURSOR, ARRAYS, HISTORY = 0x19040000, 0x19041000, 0x19050000, 0x19070000
MUTEX_TABLE, MUTEX_OBJECTS = 0x19090000, 0x19091000
UP, DOWN = 0x9004, 0x9006
SETTER, MCON, REFRESH = 0x607363b3, 0x602badc5, 0x602c50be
MUTEX_ENTER, MUTEX_LEAVE = 0x606b4d81, 0x606b4d91


def compact(r):
    return {k: v for k, v in r.items() if k not in ('trace_tail', 'stop_registers')}


def u32(s, address, value):
    s.write(address, struct.pack('<I', value & 0xffffffff))


def signed(value):
    return value if value < 0x80000000 else value-0x100000000


class Editor:
    """Explicit selected-editor fixture; only the tested sector is allocated."""
    def __init__(self, f, profile, sector, value):
        assert 1 <= profile <= 3 and 1 <= sector <= 12 and -5 <= value <= 5
        self.f, self.profile, self.sector = f, profile, sector
        self.key = 931 + (profile-1)*12 + sector-1
        self.cursor_key = (1095, 1100, 1101)[profile-1]
        self.s = s = state(f)
        selected(s, profile)
        put(s, self.key, value)
        put(s, self.cursor_key, sector)
        put(s, 1101+profile, sector)  # remembered single-sector cursor
        self.allocations = []
        self.next_allocation = ARRAYS
        for name, address, data in (
            ('property_service', PROPERTY, struct.pack('<2I', 0x609a4660, 0)),
            ('logger_default_threshold', LOGGER, struct.pack('<7I', 0x609524bc, 0, 0, 0, 0, 0, 4)),
            ('mode_check_service', MODE, struct.pack('<I', 0x60982438)),
            # Native 606b94f1's no-timestamp history layout: 1365 x 3 words.
            ('debug_history_object', DEBUG, struct.pack('<9I', 0, 0, 0, 3, 1365, 0, HISTORY, 0, 0)),
            ('debug_history_ring', HISTORY, bytes(1365*12)),
            ('common_service', COMMON, struct.pack('<2I', 0x609821a0, 0)),
            ('background_service', BACKGROUND, struct.pack('<I', 0x609a33e8)),
        ):
            s.ram(name, address, data, aliases=False)
        for global_, pointer in (
            (0x61602868, PROPERTY), (0x61600944, LOGGER), (0x616026a4, MODE),
            (0x61600bc0, DEBUG), (0x61602694, COMMON), (0x616027b0, BACKGROUND),
            # The exact reached methods do not dereference these backend
            # objects. Leave them UNMAPPED to detect any expanded contract.
            (0x61602da4, 0x19035000), (0x616023a0, 0x19039000),
            (0x616023b4, 0x190a0000),
        ):
            u32(s, global_, pointer)
        for address, size in ((0x618dab64, 14), (0x618d4bc0, 10), (0x618d4890, 16)):
            s.ram(f'reviewed_captured_{address:x}', address, f.read(address, size))
        # These paths are explicitly single-sector, without a modal override.
        for address in (0x61618eb0, 0x6161acfc, 0x6161ad00, 0x6161ad04):
            u32(s, address, 0)
        self.constructors = [self.construct(SATURATION, self.key, 11),
                             self.construct(CURSOR, self.cursor_key, 13)]
        count, index = struct.unpack('<2H', s.read(SATURATION+88, 4))
        eligibility, values = struct.unpack('<2I', s.read(SATURATION+96, 8))
        assert count == 11 and index == 5-value
        assert struct.unpack('<11i', s.read(values, 44)) == tuple(range(5, -6, -1))
        assert s.read(eligibility, 22) == bytes(22)
        assert struct.unpack('<I', s.read(SATURATION+104, 4))[0] == 1
        parent = bytearray(188)
        struct.pack_into('<I', parent, 0, 0x60f6eda0)
        struct.pack_into('<H', parent, 100, 0x13b1+profile)
        row = 0x60f6df6c+(profile-1)*56
        parent[48:92] = f.image[row-BASE+12:row-BASE+56]
        struct.pack_into('<H', parent, 120, 13)
        # Wrong-sector access faults, rather than silently using a duplicate.
        struct.pack_into('<13I', parent, 124, CURSOR, *([0x1b000000]*12))
        struct.pack_into('<I', parent, 124+4*sector, SATURATION)
        s.ram('selected_COLOR_parent', PARENT, parent, aliases=False)
        controller = bytearray(180)
        struct.pack_into('<I', controller, 0, PARENT)
        s.ram('selected_controller', CONTROLLER, controller, aliases=False)
        u32(s, 0x6161b810, CONTROLLER)
        fsm = bytearray(32)
        fsm[:3] = bytes((2, 2, 19))
        struct.pack_into('<I', fsm, 4, 0x60f30a04)
        struct.pack_into('<H', fsm, 8, 0xffff)
        s.ram('selected_editor_FSM', FSM, fsm, aliases=False)
        viewer = bytearray(156)
        struct.pack_into('<I', viewer, 0, 0x60f49f98)
        struct.pack_into('<I', viewer, 28, CURSOR)
        s.ram('viewer_callback_destination', VIEWER, viewer, aliases=False)

    def construct(self, address, key, count):
        s = self.s
        s.ram(f'constructor_destination_{key}', address, bytes(140), aliases=False)
        start = s.steps
        first = len(self.allocations)
        r = invoke(s, 0x60c7f039, 0xb0, 16, dict(a0=address, d0=key), stops=(0x60950a50,))
        while r['status'] == 'breakpoint' and s.regs['pc'] == 0x60950a50:
            n = s.regs['d0']
            expected = (count*2, count*4)[len(self.allocations)-first]
            assert n == expected
            pointer = self.next_allocation
            self.next_allocation += 0x1000
            s.ram(f'allocated_property_array_{pointer:x}', pointer, bytes(n), aliases=False)
            self.allocations.append(dict(entry='0x60950a50', bytes=n, destination=hex(pointer)))
            s.regs['a0'] = pointer
            s.return_from_model()
            r = resume(s, (CALLER+7, 0x60950a50))
        returned(s, r)
        assert len(self.allocations)-first == 2
        return dict(property=key, instructions=s.steps-start, allocations=self.allocations[first:])

    def input(self, event):
        s, f = self.s, self.f
        before = [current_record(f, s, k) for k in COLOR]
        value = current_record(f, s, self.key)
        expected = max(-5, min(5, value+(1 if event == UP else -1)))
        r = invoke(s, 0x60bcba4d, 0, 0,
                   dict(a0=FSM, a1=BUFFER, d0=event, d1=0), stops=(SETTER,))
        at(s, r, SETTER)
        assert (s.regs['a0'], s.regs['d0'], s.regs['d1'], signed(s.regs['a1'])) == (
            PROPERTY, self.key, 0, expected)
        assert [current_record(f, s, k) for k in COLOR] == before
        assert struct.unpack('<H', s.read(SATURATION+90, 2))[0] == 5-expected
        return dict(profile=self.profile, sector=self.sector, property=self.key,
                    event=hex(event), before=value, requested=expected,
                    stored_values_unchanged_before_commit=True,
                    wrong_sector_pointers_unmapped=True, **compact(r))

    def dial(self, delta):
        """One saturation-dial notch, or a zero-count negative control."""
        assert delta in (-1, 0, 1)
        s, f = self.s, self.f
        before = [current_record(f, s, k) for k in COLOR]
        value = current_record(f, s, self.key)
        # Supply the upstream count through its native setter, not by
        # replacing the getter or COLOR wheel callback.
        prepared = invoke(s, 0x60d157ef, 0, 0, dict(d0=delta & 0xffffffff))
        returned(s, prepared)
        r = invoke(s, 0x60bcba4d, 0, 0,
                   dict(a0=FSM, a1=BUFFER, d0=0x9032, d1=0), stops=(SETTER,))
        expected = max(-5, min(5, value-delta))
        if delta:
            at(s, r, SETTER)
            assert (s.regs['d0'], s.regs['d1'], signed(s.regs['a1'])) == (self.key, 0, expected)
        else:
            returned(s, r)
        assert [current_record(f, s, k) for k in COLOR] == before
        assert struct.unpack('<H', s.read(SATURATION+90, 2))[0] == 5-expected
        return dict(profile=self.profile, sector=self.sector, event='0x9032',
                    supplied_dial_count=delta, before=value, requested=expected,
                    commit_reached=bool(delta), stored_values_unchanged=True,
                    count_setter=compact(prepared), **compact(r))

    def guards(self, busy=False):
        """Continue the same native stack with an explicit mutex-only model."""
        s = self.s
        s.ram('ComResource_pointer_table', MUTEX_TABLE,
              struct.pack('<12I', *[MUTEX_OBJECTS+i*8 for i in range(12)]), aliases=False)
        s.ram('ComResource_objects', MUTEX_OBJECTS,
              b''.join(struct.pack('<2I', 0x609524c0, 0xdead0000+i) for i in range(12)), aliases=False)
        u32(s, 0x6160094c, MUTEX_TABLE)
        if busy:
            u32(s, 0x618d4890, 2)  # shared take-status bit; guards must reject
        stops = (MUTEX_ENTER, MUTEX_LEAVE, MCON, 0x606b4aa6)
        start = s.steps
        r = resume(s, stops)
        models, held = [], []
        while r['status'] == 'breakpoint' and s.regs['pc'] in stops[:2]:
            pc, pointer = s.regs['pc'], s.regs['a0']
            assert pointer == MUTEX_OBJECTS+5*8  # only shared take-status lock
            if pc == MUTEX_ENTER:
                assert not held
                held.append(pointer)
            else:
                assert held.pop() == pointer
            models.append(dict(entry=hex(pc), resource=5, return_value=0))
            s.return_from_model(0)
            r = resume(s, stops)
        assert not held
        at(s, r, 0x606b4aa6 if busy else MCON)
        if busy:
            assert (s.regs['d0'], s.regs['d1'], s.regs['a0'], s.regs['a1']) == (0, 9, 1, 1)
        else:
            assert s.regs['d0'] == self.key
        result = compact(r)
        result['modeled_functions'] = models
        return dict(**result, total_instructions=s.steps-start,
                    modeled_mutex_calls=models, busy_control=busy,
                    scope='Native GUI guards; uncontended shared-state mutex only')

    def viewer(self):
        s, f = self.s, self.f
        r = invoke(s, 0x60c84bcd, 0, 0, dict(a0=VIEWER))
        returned(s, r)
        value = current_record(f, s, self.key)
        expected = []
        for table in (0x60f49ea8, 0x60f49f00):
            entries = dict(struct.unpack_from('<iI', f.image, table-BASE+i*8) for i in range(11))
            expected.append(entries[value])
        actual = list(s.read(VIEWER+37, 2))
        assert actual == expected
        assert s.read(VIEWER+124, 4) == b'\x01\x00\x00\x00'
        return dict(value=value, display_codes=actual, **compact(r),
                    scope='Separately invoked native viewer callback; not repaint or event-loop completion')


def staged_snapshot(e):
    """Explicit alternate context, NOT resuming the blocked current refresh."""
    s, f = e.s, e.f
    expected = [current_record(f, s, k) for k in range(931+12*(e.profile-1), 943+12*(e.profile-1))]
    stages = []
    for address, mask, frame, regs in (
        (0x602f0a2c, 0xf0, 20, {}), (0x602f0b12, 0, 4, {}),
        (REFRESH, 0x80, 160, dict(d0=1, d1=53+e.profile)),
        (0x602f0b80, 0xf0, 36, dict(a0=BUFFER)), (0x602f0c58, 0, 4, {}),
    ):
        r = invoke(s, address, mask, frame, regs)
        returned(s, r)
        stages.append(dict(entry=hex(address), **compact(r)))
    assert [current_record(f, s, k) for k in range(919, 931)] == expected
    snapshot = image_snapshot(f, s, expected)
    return dict(stages=stages, snapshot=snapshot,
                scope='Separate native staged refresh/commit, then existing explicit capture-copy contracts; excludes current-context notifications')


def evidence(f, out):
    spans = {
        'child-constructor': (0x60c7f039, 0x60c7f300),
        'child-up-down': (0x60c80745, 0x60c80825),
        'child-commit': (0x60c80911, 0x60c80b1e),
        'COLOR-commit-override': (0x60c836cd, 0x60c8381a),
        'COLOR-up': (0x60cb0684, 0x60cb07d8),
        'COLOR-down': (0x60cb08e5, 0x60cb0a27),
        'controller-update': (0x60cd03cc, 0x60cd04de),
        'saturation-dial': (0x60cb1422, 0x60cb1475),
        'sector-dial': (0x60cb166f, 0x60cb16bc),
        'dial-count-storage': (0x60d157ef, 0x60d15802),
        'upstream-dial-filter': (0x60d126cc, 0x60d127be),
        'GUI-property-guards': (0x607363b3, 0x607365ff),
        'setting-manager': (0x6075fbed, 0x6075fc62),
        'selected-saturation-viewer': (0x60c84bcd, 0x60c84cf0),
        'history-layout': (0x606b94f1, 0x606b951b),
        'history-index': (0x606b99c6, 0x606b99f6),
    }
    directory = out/'disassembly'
    directory.mkdir()
    for name, (start, end) in spans.items():
        (directory/(name+'.asm')).write_text(window(f.image, DEFAULT_IMAGE, DEFAULT_OBJDUMP, start, end))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('Use a fresh output directory')
    args.out.mkdir(parents=True)
    f = Fixture()
    report = dict(main_sha256=sha(f.image), checkpoint_sha256=CHECKPOINT_SHA,
                  engine_sha256=sha(ENGINE.read_bytes()), camera_used=False,
                  firmware_modified=False, input_routes=[], dial_routes=[], connected_prefixes=[])
    for profile in (1, 2, 3):
        for sector in range(1, 13):
            e = Editor(f, profile, sector, 0)
            report['input_routes'].append(e.input(UP))
        for value, event in ((5, UP), (-5, DOWN), (5, DOWN), (-5, UP)):
            e = Editor(f, profile, 3, value)
            report['input_routes'].append(e.input(event))
        for delta in (-1, 1, 0):
            e = Editor(f, profile, 3, 0)
            report['dial_routes'].append(e.dial(delta))
        # Interior value, distinct sector per profile, actual storage/callback.
        e = Editor(f, profile, (1, 6, 12)[profile-1], -3)
        before_display = e.viewer()
        route = e.input(UP)
        guards = e.guards()
        r = resume(e.s, (REFRESH,))
        at(e.s, r, REFRESH)
        assert (e.s.regs['d0'], e.s.regs['d1']) == (0, 53+profile)
        assert current_record(f, e.s, e.key) == -2
        to_refresh = compact(r)
        strict = resume(e.s, (CALLER+7,))
        assert strict['status'] == 'memory_fault' and strict['pc'] == '0x60549d65', strict
        assert strict['fault']['address'] == 0xa1c6c38e
        after_display = e.viewer()
        report['connected_prefixes'].append(dict(
            route=route, guards=guards, storage_to_refresh=to_refresh,
            strict_current_refresh=compact(strict), before_display=before_display,
            after_display=after_display, separate_processing_contract=staged_snapshot(e),
            constructor_runs=e.constructors,
        ))
        print(f'COLOR {profile}: routes, limits, stored edit, viewer and separate snapshot passed', flush=True)
    e = Editor(f, 1, 1, -3)
    e.input(UP)
    report['busy_control'] = e.guards(busy=True)
    assert current_record(f, e.s, e.key) == -3
    report['busy_control']['stored_value_unchanged'] = True
    report['assumptions'] = [
        'A-mode selected editor fixture; physical buttons and entry are excluded',
        'Three native MCON registries and exact captured setting-record extents',
        'Native child constructors with four bounded synthetic array allocations',
        'Native API vtables; constructor-equivalent no-timestamp debug history',
        'Unmapped opaque backend witnesses: any object-field access must stop',
        'Only resource-5 mutex enter/leave modeled for the GUI guard continuation',
        'Current-context notification failure retained; viewer and staged capture checked separately',
    ]
    report['source_sha256'] = {str(p): sha(p.read_bytes()) for p in (
        Path(__file__), Path('tools/penf_profile_context_probe.py'),
        Path('tools/penf_profile_followup_probe.py'), Path('tools/penf_profile_lifecycle_probe.py'),
        Path('tools/penf_color_controls_probe.py'), Path('tools/penf_probe.py'),
        Path('tools/penf_emulator.py'), Path('tools/penf_diagnostic_lifetime_probe.py'),
        Path('tools/penf_disasm.py'),
    )}
    evidence(f, args.out)
    (args.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(args.out/'report.json')


if __name__ == '__main__':
    main()
