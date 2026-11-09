#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native PEN-F profile selection, custom save and recall lifecycle probes.

Uses initialized settings from an earlier emulated boot checkpoint, never a
camera dump. All scenario edits are RAM fixtures. Unknown accesses stop;
there is no peripheral, NV storage, event delivery or ISP model here.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import struct

from penf_color_controls_probe import ACTIVE, BANKS, LIVE, WORDS
from penf_diagnostic_lifetime_probe import parser_state
from penf_disasm import DEFAULT_IMAGE, DEFAULT_OBJDUMP, refs, window
from penf_emulator import BASE, ENGINE, Region, firmware
from penf_probe import CALLER, ProbeState

CHECKPOINT = Path('analysis/application_boot/camera-units-final/run/state.json.gz')
CHECKPOINT_SHA = 'ac8fc90113f00d70fd5a565fe7b25b34ca3613a220e6a8b05b900d931b5d73ad'
STRIDE = WORDS * 8
COLOR = range(931, 967)
WORKING = 0x61b7bac0
GUI_OBJECT = 0x19000000


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Fixture:
    def __init__(self):
        data = CHECKPOINT.read_bytes()
        assert sha(data) == CHECKPOINT_SHA
        self.captured = []
        for row in json.loads(gzip.decompress(data))['regions']:
            if row.get('hex'):
                address = row['address']
                address = int(address, 0) if isinstance(address, str) else address
                self.captured.append((address, bytes.fromhex(row['hex'])))
        self.image = firmware()
        self.records = {}
        # Exact setting-ID -> record-key tables used by 602f037b/602f05cb.
        for first, count, table, stride in (
            (0, 1274, 0x603fa158, 4), (1500, 19, 0x603fb540, 4),
            (3000, 23, 0x603fb5b8, 2), (4000, 22, 0x603fb58c, 2),
            (15000, 263, 0x603fb7ca, 4),
        ):
            for i in range(count):
                key = struct.unpack_from('<H', self.image, table - BASE + i*stride)[0]
                if not key:
                    continue
                descriptor = 0x61c281e4 + (key >> 4)*8
                actual, count_, address = struct.unpack('<HHI', self.read(descriptor, 8))
                assert actual == key and (key & 7) in (1, 2, 4)
                self.records[key] = dict(key=hex(key), descriptor=hex(descriptor),
                                         address=hex(address), size=count_*(key & 7))

    def read(self, address, size):
        for start, data in self.captured:
            if start <= address and address+size <= start+len(data):
                return data[address-start:address-start+size]
        raise ValueError(f'Uncaptured range {address:x}+{size:x}')

    def state(self):
        s = ProbeState(0x602b9f33, 0xc0, 16, bytes(256), {})
        s.register(0x8050, 'r', 0)
        for address, size in (
            (0x615fc540, 133664), (WORKING, 0x20000),
            (0x61c281e0, 0x10004), (0x61884000, 0x164b1),
            (0x61c58bb0, 0x1af0),
            (0x61c8ad54, 4),  # captured diagnostic ring-enable flag, 600429d1
            # Debug call history: pointer 615fd92c, capacity 615fd934=300,
            # followed by ten in-flight slots. Runtime allocation overlaps
            # the flat decoded-image address range and must replace it.
            (0x61246700, (300+10)*16),
        ):
            s.ram(f'captured_{address:x}', address, self.read(address, size))
        # Map only declared record extents, not all surrounding RAM. Defaults
        # already readable in the main image stay read-only. Descriptor and
        # source checks make this a reviewed fixture, not automatic fault fill.
        for row in self.records.values():
            address, size = int(row['address'], 0), row['size']
            try:
                s.read(address, size)
            except ValueError:
                s.ram('captured_record_'+row['key'], address, self.read(address, size))
        s.ram('diagnostic_suppression', 0x6181e3c0, struct.pack('<H', 2))
        parser_state(s)  # exact relocated native libc, zero locale fixture
        return s


def invoke(s, address, mask, frame, regs=None, *, stops=(), limit=15000000, stack_arg=None):
    caller = b'\xdd'+struct.pack('<i', address-CALLER)+bytes((mask, frame))+b'\xcb'
    s.regions = [Region('caller', CALLER, caller, 'rx') if r.name == 'caller' else r
                 for r in s.regions]
    s.regs = dict(pc=CALLER, sp=0x18018000, psw=0, **(regs or {}))
    if stack_arg is not None:
        s.write(0x18018004, struct.pack('<I', stack_arg))
    before = s.steps
    result = s.run(set(stops) | {CALLER+7}, limit=limit)
    return dict(status=result['status'], pc=hex(s.regs['pc']), fault=result.get('fault'),
                instructions=s.steps-before, result=s.regs.get('d0'),
                modeled_functions=[],
                **({'stop_registers': s.regs.copy(),
                    'trace_tail': [{k: v for k, v in t.items() if not k.startswith('extra')}
                                   for t in result.get('trace', [])]}
                   if result['status'] != 'breakpoint' else {}))


def returned(s, result):
    assert result['status'] == 'breakpoint' and s.regs['pc'] == CALLER+7, result
    assert s.regs['sp'] == 0x18018000


def get(s, key):
    result = invoke(s, 0x602f024a, 0, 4, dict(d0=key))
    returned(s, result)
    return s.regs['d0']


def signed_get(s, key):
    value = get(s, key)
    return value if value < 0x80000000 else value-0x100000000


def put(s, key, value):
    """Explicit fixture preparation through native current/live setters."""
    for address, mask, frame in ((0x602f029d, 0xc0, 12), (0x602f0762, 0, 4)):
        returned(s, invoke(s, address, mask, frame, dict(d0=key, d1=value & 0xffffffff)))


def setup_a(s, bank=0):
    for key, value in ((24, 4), (26, 4), (43, 4), (109, 0), (41, bank), (912, 1)):
        put(s, key, value)


def words(s, address, count):
    return struct.unpack(f'<{count}i', s.read(address, count*4))


def bank_word(s, bank, key, value, part=0):
    s.write(BANKS+bank*STRIDE+(part*WORDS+key)*4, struct.pack('<i', value))


def color_values(seed):
    return tuple((i*3+seed) % 11-5 for i in range(36))


def select_and_edit(fixture):
    s = fixture.state()
    setup_a(s)
    banks_before = s.read(BANKS, 9*STRIDE)
    active_before = s.read(ACTIVE, STRIDE)
    # Actual observer installed by 6075efbc..6075efc9. Its whitelist must
    # execute; do not silently infer behavior from an unregistered observer.
    s.write(0x615fd38c, struct.pack('<I', 0x6075fedb))
    edits = []
    expected = color_values(2)
    for key, value in zip(COLOR, expected):
        result = invoke(s, 0x602b9f33, 0xc0, 16, dict(d0=key, d1=value & 0xffffffff))
        returned(s, result)
        assert result['result'] == 0
        assert get(s, key) == value & 0xffffffff
        edits.append(dict(property_id=key, value=value, **result))
    assert words(s, LIVE+931*4, 36) == expected
    s.ram('GUI_property_service_fixture', GUI_OBJECT,
          struct.pack('<II', 0x609a4660, 0), aliases=False)
    s.write(0x61602868, struct.pack('<I', GUI_OBJECT))
    selections = []
    for profile in (1, 2, 3, 1):
        result = invoke(s, 0x602b9f33, 0xc0, 16, dict(d0=912, d1=profile))
        returned(s, result)
        ui = invoke(s, 0x60cf064a, 0, 0)
        returned(s, ui)
        assert ui['result'] == 0x13b1+profile, ui
        assert words(s, LIVE+931*4, 36) == expected
        selections.append(dict(profile=profile, editor_key=hex(ui['result']),
                               setter=result, native_GUI_selector=ui))
    assert s.read(BANKS, 9*STRIDE) == banks_before
    assert s.read(ACTIVE, STRIDE) == active_before
    return dict(edits=edits, selections=selections, all_36_values=expected,
                saved_banks_and_active_unchanged=True,
                scope='Native MCON edit and GUI selector/getter; GUI write gates, redraw and ISP excluded')


def adapter_prefixes(fixture):
    cases = []
    for key, value in ((912, 3), (931, 5), (966, -5)):
        s = fixture.state()
        setup_a(s)
        put(s, key, -2 if key != 912 else 1)
        witness = bytes(range(144))
        s.write(ACTIVE+(WORDS+931)*4, witness)
        banks_before = s.read(BANKS, 9*STRIDE)
        result = invoke(s, 0x6075fbed, 0xe0, 16,
                        dict(d0=key, d1=value & 0xffffffff, a0=GUI_OBJECT),
                        stops=(0x607607a1,))
        assert result['status'] == 'breakpoint' and s.regs['pc'] == 0x607607a1, result
        assert signed_get(s, key) == value
        assert words(s, LIVE+key*4, 1)[0] == value
        assert s.read(ACTIVE+(WORDS+931)*4, 144) == witness
        assert s.read(BANKS, 9*STRIDE) == banks_before
        policies = []
        for policy, expected in ((0x6075ff3a, 1), (0x6075ff76, 0)):
            policy_result = invoke(s, policy, 0, 0, dict(d0=key))
            returned(s, policy_result)
            assert policy_result['result'] == expected
            policies.append(dict(entry=hex(policy), **policy_result))
        cases.append(dict(property_id=key, action='set', value=value, **result,
                          part1_and_saved_banks_unchanged=True,
                          notification_policies=policies,
                          scope='Native application setter prefix, before event delivery; not held-OK path'))
    return cases


def save_pair(fixture, index):
    s = fixture.state()
    setup_a(s)
    expected = color_values(index)
    for key, value in zip(COLOR, expected):
        put(s, key, value)
    put(s, 912, index % 3+1)
    witness = bytes((i+index*17) & 255 for i in range(144))
    s.write(ACTIVE+(WORDS+931)*4, witness)
    before = s.read(BANKS, 9*STRIDE)
    result = invoke(s, 0x6075fb08, 0x80, 8, dict(d0=index))
    returned(s, result)
    banks = (index+1, index+5)
    after = s.read(BANKS, 9*STRIDE)
    for bank in range(9):
        if bank not in banks:
            assert after[bank*STRIDE:(bank+1)*STRIDE] == before[bank*STRIDE:(bank+1)*STRIDE]
            continue
        assert words(s, BANKS+bank*STRIDE+931*4, 36) == expected
        assert words(s, BANKS+bank*STRIDE+912*4, 1)[0] == index % 3+1
        assert s.read(BANKS+bank*STRIDE+(WORDS+931)*4, 144) == witness
    edit = invoke(s, 0x602b9f33, 0xc0, 16, dict(d0=931, d1=(expected[0]+1) & 0xffffffff))
    returned(s, edit)
    assert s.read(BANKS, 9*STRIDE) == after
    return dict(input_index=index, banks=banks, all_36_values=expected, **result,
                current_part1_copied_to_both=True, unrelated_banks_unchanged=True,
                later_live_edit_does_not_resave_banks=True, nonvolatile_write=False)


def transition(fixture, destination, *, source=0, stage='prefix'):
    s = fixture.state()
    setup_a(s, source)
    source_values, dest_values = color_values(2), color_values(6)
    for key, value in zip(COLOR, source_values):
        put(s, key, value)
    for key, value in ((24, 4), (26, 4), (43, 4), (109, 0), (912, 3)):
        bank_word(s, destination, key, value)
    for key, value in zip(COLOR, dest_values):
        bank_word(s, destination, key, value)
    witness = bytes((i+destination*19) & 255 for i in range(144))
    s.write(BANKS+destination*STRIDE+(WORDS+931)*4, witness)
    source_saved_before = s.read(BANKS+source*STRIDE, STRIDE)
    # Public selector-2 route: C1..4 codes 53..56 map to banks 5..8.
    result = invoke(s, 0x602ba07b, 0xc0, 16, dict(d0=destination+48 if destination else 2),
                    stops={'prefix': (0x602f0a2c,), 'commit': (0x602bd7f9,), 'full': ()}[stage])
    if stage != 'full':
        assert result['status'] == 'breakpoint', result
        assert s.regs['pc'] == {'prefix': 0x602f0a2c, 'commit': 0x602bd7f9}[stage], result
    else:
        assert result['status'] == 'memory_fault' and s.regs['pc'] == 0x60031bec, result
        assert result['fault']['address'] == 0x8ff00004
    if stage == 'commit':
        count = s.regs['d2']
        result['changed_property_ids'] = list(struct.unpack(f'<{count}H', s.read(s.regs['a2'], count*2)))
        assert set(COLOR) <= set(result['changed_property_ids'])
    if source == 0:
        assert words(s, BANKS+931*4, 36) == source_values
    else:
        assert s.read(BANKS+source*STRIDE, STRIDE) == source_saved_before
    assert words(s, LIVE+931*4, 36) == dest_values
    assert words(s, LIVE+912*4, 1)[0] == 3
    assert s.read(ACTIVE+(WORDS+931)*4, 144) == witness
    result.update(source_bank=source, destination_bank=destination,
                  source_COLOR_saved_in_bank0=source == 0,
                  source_custom_bank_unchanged=source != 0,
                  destination_COLOR_in_live=True, destination_part1_in_active=True,
                  current_profile=get(s, 912), current_bank=get(s, 41), stage=stage)
    if stage == 'commit':
        assert result['current_profile'] == 3 and result['current_bank'] == destination
        assert tuple(signed_get(s, key) for key in COLOR) == dest_values
        assert s.read(0x6189a4b0, 1) == b'\0'
        result['native_transaction_committed_all_36_COLOR_values'] = True
        result['settings_lock_released'] = True
        result['post_commit_callbacks_and_notifications_pending'] = True
    return result


def static_evidence(fixture, out):
    windows = {
        'bank-public': (0x602b9ff9, 0x602ba299),
        'transition-core': (0x602bd5f0, 0x602bdd92),
        'settings-mapping': (0x602f037b, 0x602f063b),
        'transaction-staging': (0x602f0a2c, 0x602f0d18),
        'property-write': (0x6075fbed, 0x607601b5),
        'GUI-write': (0x607363b3, 0x607365ff),
        'post-change-event': (0x607607a1, 0x60760828),
        'observer-registration': (0x6075efbc, 0x6075efce),
        'temporary-recall-callers': (0x6093ef13, 0x6093ef6d),
        'callback-passes-and-observers': (0x602bbf60, 0x602bc05a),
        'debug-history-start': (0x602e13ea, 0x602e143c),
        'current-task-query': (0x60031be2, 0x60031c26),
        'generic-action-3-not-identified-as-reset': (0x602bace5, 0x602bad1c),
    }
    for name, (start, end) in windows.items():
        (out/(name+'.asm')).write_text(window(fixture.image, DEFAULT_IMAGE, DEFAULT_OBJDUMP, start, end))
    candidates = {}
    for target in (0x602ba07b, 0x602ba0fb, 0x602ba1bd, 0x602bdad8, 0x602bdb0b,
                   0x602f067a, 0x607607a1, 0x606c003e):
        pointers, calls = refs(fixture.image, target)
        candidates[hex(target)] = dict(raw_pointer_candidates=list(map(hex, pointers)),
                                       raw_direct_call_candidates=list(map(hex, calls)))
    return candidates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path('analysis/profile_lifecycle/verified'))
    parser.add_argument('--group', choices=('all', 'edits', 'save', 'transition'), default='all')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    fixture = Fixture()
    report = dict(main_sha256=sha(fixture.image), checkpoint_sha256=CHECKPOINT_SHA,
                  engine_sha256=sha(ENGINE.read_bytes()), script_sha256=sha(Path(__file__).read_bytes()),
                  source_sha256={p: sha(Path('tools', p).read_bytes()) for p in (
                      'penf_probe.py', 'penf_boot_emulator.py', 'penf_emulator.py',
                      'penf_diagnostic_lifetime_probe.py', 'penf_color_controls_probe.py')},
                  group=args.group,
                  assumptions=['CPU0', 'initialized captured settings, explicit A-mode scenario',
                               'zero libc locale', 'diagnostic output disabled',
                               'GUI singleton object fixture for selection only',
                               'real MCON observer installed in edit cases; captured null observers in recall/save'],
                  nonvolatile_write=False, camera_used=False)
    if args.group in ('all', 'edits'):
        report['edits'] = select_and_edit(fixture)
        report['application_edit_prefixes'] = adapter_prefixes(fixture)
        print('Native edits and GUI selection passed', flush=True)
    if args.group in ('all', 'save'):
        report['paired_save'] = []
        for index in range(4):
            report['paired_save'].append(save_pair(fixture, index))
            print(f'Native paired save C{index+1} passed', flush=True)
    if args.group in ('all', 'transition'):
        report['transition_prefix'] = [transition(fixture, bank) for bank in (5, 6)]
        report['transition_committed'] = [transition(fixture, dst, source=src, stage='commit')
                                         for src, dst in ((0, 5), (5, 6), (5, 0))]
        report['transition_full_attempt'] = transition(fixture, 5, stage='full')
        r = report['transition_full_attempt']
        print('Transition stop', r['status'], r['pc'], r['fault'], flush=True)
    report['mapped_record_inventory'] = list(fixture.records.values())
    report['reference_candidates'] = static_evidence(fixture, args.out)
    (args.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(args.out/'report.json')


if __name__ == '__main__':
    main()
