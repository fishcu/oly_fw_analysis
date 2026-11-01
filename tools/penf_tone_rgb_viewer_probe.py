#!/usr/bin/env python3
"""DEL dispatch through the exact native tone viewer and parameter publication.

Allocators return exact guarded objects. Camera context properties, status,
notification, timer, log and lower draw-queue services have explicit models.
The factory, constructors, updater, callbacks, helper update, parameter store
and draw wrapper execute their native instructions. No camera I/O.
"""
if not __debug__:
    raise RuntimeError('Tone audit probes require assertions')

import argparse
from dataclasses import replace
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import struct
import tempfile

from penf_emulator import BASE, Region, firmware
from penf_hsl_context_probe import reenter
from penf_osd_bitmaps import BitmapBank
from penf_probe import CALLER
from penf_tone_editor_probe import fixture, actuator, current, mode, ACTUATOR, SERVICE
from penf_tone_graph_candidate import build_graph
from penf_tone_points import FivePoints
from penf_tone_probe import INITIAL_SP, PRESERVED
from penf_tone_transport_probe import call, put32, u32, ACTIVE, BANKS, LIVE, WORDS, set_words
from penf_tone_viewer_probe import getter_adapter, GETTER, GETTER_TABLE, PAGE_NAMES

VIEWER, HELPER, OWNER = 0x19112000, 0x19130000, 0x19140000
STORE, TABLE = 0x19150000, 0x19151000
STATUS, STATUS_VTABLE = 0x19160000, 0x19161000
DRAW, DRAW_VTABLE = 0x19170000, 0x19171000
STATUS_MODE, STATUS_FLAGS, DRAW_SET, DRAW_UNSET = range(0x190b1000, 0x190b1040, 16)
CONTROLLER, EVENT = 0x19110000, 0x19111000
UPDATE, CALLBACKS, HELPER_UPDATE, DRAW_REQUEST = 0x60cf9b6d, (0x60cf9c27, 0x60cfa658), 0x60c922d2, 0x60d147e8
PARAMETERS = {118: (VIEWER+8, 92), 209: (VIEWER+100, 12)}
CONTEXT_PROPERTIES = {26: 0, 28: 0, 44: 0, 683: 0, 762: 0, 906: 111}
OBSERVE = {UPDATE, *CALLBACKS, HELPER_UPDATE, DRAW_REQUEST,
           0x60bba9e5, 0x60bba9fd, 0x60cf9b9a, 0x60cf9bab,
           0x60cf9be6, 0x60cf9c24, 0x60c92738, 0x60d14834}
MODELS = {GETTER, 0x60950a46, 0x60d13bb1, 0x606f5d80, STATUS_MODE,
          STATUS_FLAGS, 0x60d13bbb, 0x60d10726, 0x60d107fe, 0x60d1075c,
          0x60d1392d, 0x60d12a62, 0x60bd6efa, 0x60bd70f4, 0x60bd6765,
          0x60bd6e60, 0x60d12a50, 0x60726f04, DRAW_SET, DRAW_UNSET}
SCOPE = ('Native DEL dispatcher, tone/helper factories and constructors, tone updater, '
         'both callbacks, patched footer, native parameter get/set and no-observer '
         'display store, helper update and draw-request wrapper through ABI return. '
         'Exact allocator objects, context properties, status, logs, timer, GUI '
         'notification and lower draw queue/lock services are modeled. The helper '
         'uses the explicit status-zero path. Queue worker, LCD and camera execution excluded.')


@lru_cache(maxsize=1)
def gui_getter():
    with tempfile.TemporaryDirectory(prefix='penf-native-viewer-getter-') as folder:
        return getter_adapter(Path(folder)/'getter')


class NativeToneViewer:
    def __init__(self, s):
        self.s, self.models, self.observed, self.transfers = s, [], [], []
        s.regions.append(Region('GUI_getter_adapter', GETTER, gui_getter(), 'rx'))
        s.ram('GUI_getter_vtable', GETTER_TABLE, struct.pack('<3I', 0, 0, GETTER), aliases=False)
        put32(s, SERVICE, GETTER_TABLE)
        s.ram('context_owner', OWNER, bytes(180), aliases=False)
        for name, address, size in (('tone_viewer', VIEWER, 120), ('tone_helper', HELPER, 1492)):
            s.regions.append(Region(name+'_before', address-16, b'\xa5'*16, 'r'))
            s.ram(name, address, bytes(size), aliases=False)
            s.regions.append(Region(name+'_after', address+size, b'\x5a'*16, 'r'))
        s.ram('current_viewer_family', 0x61619ebc, bytes(4))
        s.ram('tone_callbacks', 0x6161b8a4, bytes(16))
        s.ram('external_status_service', STATUS, struct.pack('<I', STATUS_VTABLE), aliases=False)
        vtable = bytearray(332)
        struct.pack_into('<I', vtable, 20, STATUS_MODE)
        struct.pack_into('<I', vtable, 328, STATUS_FLAGS)
        s.ram('external_status_vtable', STATUS_VTABLE, vtable, aliases=False)
        s.ram('external_draw_service', DRAW, struct.pack('<I', DRAW_VTABLE), aliases=False)
        vtable = bytearray(36)
        struct.pack_into('<2I', vtable, 28, DRAW_SET, DRAW_UNSET)
        s.ram('external_draw_vtable', DRAW_VTABLE, vtable, aliases=False)
        for address, size in ((0x6161bf90, 2), (0x6161bf06, 2), (0x61618eb0, 4),
                              (0x6161ad04, 4), (0x6161bf84, 4)):
            s.ram(hex(address), address, bytes(size))
        data = firmware()[0x601f95dc-BASE:0x601f95dc-BASE+211*16]
        s.ram('native_descriptor_table', TABLE, data, aliases=False)
        self.destinations = {}
        for key in (0, 37, 80, 118, 209):
            flags, other, address, size = struct.unpack_from('<4I', data, key*16)
            assert (flags, other) == (0, 0)
            self.destinations[key] = (address, size)
            s.ram('parameter'+str(key), address, bytes(size))
        s.ram('native_display_store', STORE, bytes(28), aliases=False)
        s.ram('display_store_global', 0x6160c068, struct.pack('<I', STORE))
        s.ram('display_lock_callbacks', 0x6160c154, bytes(16))
        call(s, 0x60bbaa1b, 0x20, 8, a0=STORE)
        call(s, 0x60bbaa75, 0xf0, 24, a0=STORE, a1=TABLE, d0=211)
        assert struct.unpack('<3I', s.read(STORE+16, 12)) == (STORE+16, STORE+16, 0)
        bank = BitmapBank()
        row = bank.rows[8]
        data = bank.data[row['start']:row['end']]
        s.regions.append(Region('stock_language', 0xa2ce3c00, data, 'r'))
        s.ram('selected_string_slot', 0x6160c2ec, b'\x01', aliases=False)
        s.ram('string_slots', 0x6161886c, struct.pack('<II', 0, struct.unpack_from('<I', data)[0]), aliases=False)
        call(s, 0x60cfa6f5, 0, 0)
        assert struct.unpack('<4I', s.read(0x6161b8a4, 16)) == (0xffffffff, CALLBACKS[0], 0xffffffff, CALLBACKS[1])
        reenter(s, 0x60cf990a, 0, 0, dict(PRESERVED, a0=OWNER))
        self.drive()
        assert s.regs['a0'] == VIEWER and s.regs['sp'] == INITIAL_SP
        assert all(s.regs[k] == v for k, v in PRESERVED.items())
        assert (u32(s, VIEWER), u32(s, VIEWER+4), u32(s, VIEWER+112), u32(s, VIEWER+116)) == (0x60f8bca4, HELPER, OWNER, 0)
        assert (u32(s, HELPER), u32(s, HELPER+1484), u32(s, HELPER+1488)) == (0x60f5c950, OWNER, 1)
        self.constructor = dict(viewer_hex=s.read(VIEWER, 120).hex(),
            helper_sha256=hashlib.sha256(s.read(HELPER, 1492)).hexdigest(),
            models=self.models.copy(), transfers=self.transfers.copy())
        self.invariants = (s.read(VIEWER, 8), s.read(VIEWER+112, 8), s.read(HELPER, 4), s.read(HELPER+1484, 8))
        self.guards()
        self.clear()

    def clear(self):
        self.models, self.observed, self.transfers = [], [], []

    def guards(self):
        s = self.s
        for address, size in ((VIEWER, 120), (HELPER, 1492)):
            assert s.read(address-16, 16) == b'\xa5'*16
            assert s.read(address+size, 16) == b'\x5a'*16
        assert (s.read(VIEWER, 8), s.read(VIEWER+112, 8), s.read(HELPER, 4), s.read(HELPER+1484, 8)) == self.invariants

    def handle(self, pc):
        s = self.s
        if pc == GETTER and s.regs['d0'] not in CONTEXT_PROPERTIES:
            self.observed.append(GETTER)
            step = s.run(set(), limit=1)
            assert step['status'] == 'instruction_limit'
            return
        self.models.append(dict(entry=hex(pc), caller_return=hex(s.regs['mdr']),
            d0=s.regs['d0'], d1=s.regs['d1'], a0=hex(s.regs['a0']), a1=hex(s.regs['a1'])))
        if pc == GETTER:
            key = s.regs['d0']
            put32(s, s.regs['a1'], CONTEXT_PROPERTIES[key])
            s.regs['pc'], s.regs['d0'] = s.regs['mdr'], 0
        elif pc == 0x60950a46:
            size = s.regs['d0']
            assert size in (120, 1492), size
            s.return_from_model(0)
            s.regs['a0'] = {120: VIEWER, 1492: HELPER}[size]
        elif pc in (0x606f5d80, 0x60726f04):
            s.return_from_model(0)
            s.regs['a0'] = STATUS if pc == 0x606f5d80 else DRAW
        elif pc in (STATUS_MODE, STATUS_FLAGS, DRAW_SET, DRAW_UNSET):
            if pc in (DRAW_SET, DRAW_UNSET):
                assert s.regs['d0'] == 4
            s.regs['pc'], s.regs['d0'] = s.regs['mdr'], 0
        elif pc == 0x60d1392d:
            assert (s.regs['d0'], s.regs['d1']) == (18, 1)
            s.return_from_model(0)
        else:
            s.return_from_model(1 if pc == 0x60bd6e60 else 0)

    def drive(self, stops=None, *, allow_fault=False):
        s = self.s
        stops = {CALLER+7} if stops is None else set(stops)
        for _ in range(200):
            result = s.run(MODELS | OBSERVE | stops, limit=100000)
            pc = s.regs['pc']
            if result['status'] != 'breakpoint':
                if allow_fault:
                    return result
                raise AssertionError((result['status'], result.get('fault'), hex(pc)))
            if pc in stops:
                return result
            if pc in MODELS:
                self.handle(pc)
                continue
            self.observed.append(pc)
            if pc in (0x60bba9e5, 0x60bba9fd):
                key, size, pointer = s.regs['d0'], s.regs['d1'], s.regs['a0']
                assert self.destinations[key][1] == size
                self.transfers.append(dict(direction='read' if pc == 0x60bba9e5 else 'write',
                    parameter=key, bytes=size, pointer=hex(pointer), destination=hex(self.destinations[key][0])))
            if pc in (0x60cf9b9a, 0x60cf9bab):
                key = 209 if pc == 0x60cf9b9a else 118
                source, size = self.destinations[key]
                pointer, _ = PARAMETERS[key]
                assert s.read(pointer, size) == s.read(source, size)
            step = s.run(set(), limit=1)
            assert step['status'] == 'instruction_limit'
        raise AssertionError('Native viewer operation did not return')


def state(graph):
    s = fixture(graph.base, replace(graph.editor, image=graph.image))
    mode(s, 54)
    current(s, 1, (0, 0, 0))
    actuator(s, 1, 0)
    viewer = NativeToneViewer(s)
    s.ram('tone_controller', CONTROLLER, struct.pack('<2I', ACTUATOR, VIEWER), aliases=False)
    s.ram('current_controller', 0x6161b810, struct.pack('<I', CONTROLLER))
    s.ram('current_screen', 0x6161b81c, struct.pack('<H', 897))
    s.ram('DEL_event', EVENT, b'\x02\x02', aliases=False)
    return viewer


def press(viewer):
    reenter(viewer.s, 0x60bcba4d, 0, 0, dict(PRESERVED, a0=EVENT, d0=0x9016, d1=0, a1=0))
    return viewer.drive()


def settings_bytes(s):
    return (s.read(ACTIVE, WORDS*8), s.read(BANKS, 9*WORDS*8), s.read(LIVE, WORDS*4))


def fallback_cases(graph):
    viewer = state(graph)
    s = viewer.s
    reports = []
    for reason in ('modal', 'unsupported', 'FSM', 'busy16', 'busy44', 'null_viewer'):
        actuator(s, 1, 0)
        s.write(EVENT, b'\x02\x02')
        put32(s, 0x61618eb0, 0)
        put32(s, CONTROLLER+4, VIEWER)
        if reason == 'modal':
            put32(s, 0x61618eb0, 1)
        elif reason == 'unsupported':
            put32(s, ACTUATOR+188, 0x60f4ccd0)
        elif reason == 'FSM':
            s.write(EVENT, b'\x02\x01')
        elif reason in ('busy16', 'busy44'):
            put32(s, ACTUATOR+int(reason[4:]), 1)
        else:
            put32(s, CONTROLLER+4, 0)
        before = (s.read(VIEWER, 120), settings_bytes(s))
        viewer.clear()
        reenter(s, 0x60bcba4d, 0, 0, dict(PRESERVED, a0=EVENT, d0=0x9016, d1=0x1234, a1=0x4321))
        viewer.drive({0x60bcbbc7})
        assert not viewer.observed and not viewer.models and not viewer.transfers
        assert (s.read(VIEWER, 120), settings_bytes(s)) == before
        assert s.read(ACTUATOR+194, 2) == bytes(2)
        viewer.guards()
        reports.append(dict(reason=reason, native_stock_fallback=hex(s.regs['pc']), no_update_or_publication=True))
    return reports


def joined_cases(graph):
    viewer = state(graph)
    s = viewer.s
    set_words(s, (FivePoints().pack(),)*3)
    before_settings = settings_bytes(s)
    reports = []
    for profile in (1, 2, 3):
        mode(s, 53+profile)
        current(s, profile, (0, 0, 0))
        for page in (0, 1, 2):
            actuator(s, profile, page)
            initial_family = 18 if page == 0 else 129
            put32(s, 0x61619ebc, initial_family)
            for channel in (1, 2, 3, 0):
                viewer.clear()
                put32(s, 0x6161bf84, 9)
                press(viewer)
                assert s.regs['sp'] == INITIAL_SP and s.regs['d0'] == 0
                assert all(s.regs[k] == v for k, v in PRESERVED.items())
                assert struct.unpack('<H', s.read(ACTUATOR+194, 2))[0] == channel*3+page
                assert u32(s, 0x6161bf84) == 0 and u32(s, 0x61619ebc) == 18
                assert settings_bytes(s) == before_settings
                viewer.guards()
                for entry in (UPDATE, *CALLBACKS, HELPER_UPDATE, DRAW_REQUEST, 0x60cf9c24, 0x60c92738, 0x60d14834):
                    assert viewer.observed.count(entry) == 1, (hex(entry), viewer.observed)
                expected_transfers = [('read', 209), ('read', 118), ('write', 118), ('write', 209)]
                assert [(t['direction'], t['parameter']) for t in viewer.transfers] == expected_transfers
                for transfer in viewer.transfers:
                    assert (int(transfer['pointer'], 16), transfer['bytes']) == PARAMETERS[transfer['parameter']]
                for key, (pointer, size) in PARAMETERS.items():
                    destination, _ = viewer.destinations[key]
                    assert s.read(destination, size) == s.read(pointer, size)
                label = s.read(viewer.destinations[118][0]+18, 66).decode('utf-16le').split('\0')[0]
                expected = ('ALL', 'R', 'G', 'B')[channel]+' '+PAGE_NAMES[8][page]+(' S0256 H0768', ' M+0', ' B0000 W1023')[page]+'@A028@ DEL'
                assert label == expected, (label, expected)
                assert s.read(viewer.destinations[118][0]+5, 1) == bytes((2 if page == 1 else 1,))
                notifications = [m for m in viewer.models if m['entry'] == '0x60d1392d']
                assert len(notifications) == int(initial_family != 18 and channel == 1)
                reports.append(dict(profile=profile, page=page, channel=channel, label=label,
                    first_entry_notification=bool(notifications), transfers=viewer.transfers.copy(),
                    native_entries=list(map(hex, viewer.observed)), models=viewer.models.copy()))
    return dict(cycles=reports, native_constructor=viewer.constructor,
        exact_viewer_allocation=120, exact_helper_allocation=1492,
        neutral_channels=True, setting_writes=0, guards_and_owner_unchanged=True,
        stack_and_preserved_registers_restored=True, scope=SCOPE)


def negative_case(graph):
    viewer = state(graph)
    s = viewer.s
    put32(s, 0x61619ebc, 18)
    s.ram('negative_wrong_HSL_update', 0x60f8bca4, struct.pack('<I', 0x60c84901), aliases=False)
    reenter(s, 0x60bcba4d, 0, 0, dict(PRESERVED, a0=EVENT, d0=0x9016, d1=0, a1=0))
    result = viewer.drive(allow_fault=True)
    assert result['status'] == 'memory_fault', result['status']
    assert (result['fault']['address'], result['fault']['access']) == (VIEWER+120, 'write'), result['fault']
    assert u32(s, VIEWER+112) != OWNER
    assert s.read(VIEWER+120, 16) == b'\x5a'*16
    return dict(status=result['status'], fault=result['fault'], viewer_offset=120,
                owner_corrupted=True, canary_write_rejected=True, scope='Same native-constructed fixture with the old HSL method injected into slot zero')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    graph = build_graph(args.out/'candidate')
    report = dict(joined=joined_cases(graph), old_target=negative_case(graph), fallbacks=fallback_cases(graph))
    (args.out/'viewer-audit.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(status='PASS', cycles=len(report['joined']['cycles']),
        old_target=report['old_target'], scope=SCOPE), indent=2))


if __name__ == '__main__':
    main()
