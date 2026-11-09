#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Offline COLOR input routing and settings-bank contracts, without a patch.

Fixtures supply a selected GUI state and initialized object pointers. They do
not reproduce the complete physical-input stack or camera persistent storage.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import struct

from penf_emulator import BASE, ENGINE, firmware
from penf_probe import ProbeState, CALLER, BUFFER
from penf_disasm import DEFAULT_IMAGE, DEFAULT_OBJDUMP, window

OBJ = 0x19000000
CONTROLLER = OBJ + 0x1000
ACTUATOR = OBJ + 0x2000
ACTIVE = 0x61b938b8
LIVE = 0x61b924cc
BANKS = 0x61b7bdc8
WORDS = 1274
EVENTS = {
    'up': 0x9004, 'down': 0x9006, 'left': 0x9008, 'right': 0x900a,
    'OK': 0x900c, 'MENU': 0x900e, 'PLAY': 0x9010, 'MOVIE': 0x9012,
    'INFO': 0x9014, 'DELETE': 0x9016,
    'FN': 0x9057, 'FN2': 0x9059, 'FN3': 0x905b,
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def until(s, addresses, limit=100000):
    r = s.run(set(addresses), limit=limit)
    assert r['status'] == 'breakpoint' and s.regs['pc'] in addresses, {
        'status': r['status'], 'pc': hex(s.regs['pc']), 'fault': r.get('fault')}
    return s.regs['pc']


def returned(s):
    assert s.regs['pc'] == CALLER + 7 and s.regs['sp'] == 0x18018000


def fsm_fixture(event):
    obj = bytearray(32)
    obj[:3] = bytes([2, 2, 19])  # machine 2, active editor state 2
    struct.pack_into('<I', obj, 4, 0x60f30a04)
    struct.pack_into('<H', obj, 8, 0xffff)
    s = ProbeState(0x60bcba4d, 0, 0, bytes(32),
                   dict(a0=OBJ, d0=event, d1=0, a1=BUFFER))
    s.ram('selected_editor_FSM_fixture', OBJ, obj, aliases=False)
    return s


def local_route(name, event):
    s = fsm_fixture(event)
    pc = until(s, {CALLER + 7, 0x60cefd3d})
    if pc == CALLER + 7:
        returned(s)
        assert s.regs['d0'] == 3  # event absent from this state machine
    else:
        assert s.regs['d0'] == event
    return dict(name=name, event=hex(event), instructions=s.steps,
                result='local editor handler' if pc == 0x60cefd3d else 'unlisted',
                stop=hex(pc), modeled_functions=[])


def arrow_route(key, event, target, blob):
    s = fsm_fixture(event)
    controller = bytearray(180)
    struct.pack_into('<I', controller, 0, ACTUATOR)
    actuator = bytearray(188)
    struct.pack_into('<I', actuator, 0, 0x60f6eda0)
    struct.pack_into('<H', actuator, 100, key)
    row = 0x60f6df6c + (key - 0x13b2) * 56
    actuator[48:92] = blob[row - BASE + 12:row - BASE + 56]
    s.ram('controller_fixture', CONTROLLER, controller, aliases=False)
    s.ram('actuator_fixture', ACTUATOR, actuator, aliases=False)
    s.ram('current_editor_pointer_fixture', 0x6161b810, struct.pack('<I', CONTROLLER))
    s.ram('no_modal_actuator_override_fixture', 0x61618eb0, bytes(4))
    s.ram('no_repeat_override_fixture', 0x6161ad04, bytes(4))
    until(s, {target})
    assert s.regs['a0'] == ACTUATOR
    return dict(key=hex(key), event=hex(event), target=hex(target),
                instructions=s.steps, modeled_functions=[],
                scope='FSM through local handler/controller/base actuator to COLOR callback')


def global_press(name, event):
    s = ProbeState(0x60d12112, 0xb0, 176, struct.pack('<8I',event,0,0,0,0,0,0,0),
                   dict(a0=BUFFER))
    # Reviewed global filter flags: no event lock, modal capture or deferred
    # operation. These are a scenario, not sampled COLOR editor state.
    s.ram('nonmodal_global_filter_fixture', 0x6161bde8, bytes(36))
    until(s, {CALLER+7})
    returned(s)
    assert s.regs['d0'] == 0
    assert struct.unpack('<I',s.read(BUFFER,4))[0] == event
    return dict(name=name,event=hex(event),instructions=s.steps,consumed=False,
                event_unchanged=True,modeled_functions=[],
                scope='GUI pre-filter only; upstream configurable actions excluded')


def property_identity(property_id):
    s = ProbeState(0x607359ef, 0, 0, bytes(16),
                   dict(a0=OBJ, a1=BUFFER, d0=property_id))
    s.ram('setting_controller_fixture', OBJ, bytes(8), aliases=False)
    until(s, {0x602bad44})
    assert s.regs['d0'] == property_id
    return dict(property_id=property_id,mcon_getter=hex(s.regs['pc']),
                instructions=s.steps,modeled_functions=[])


def bank_selection(blob, mode, selector):
    s = ProbeState(0x602b9ff9, 0xe0, 16, bytes(16),
                   dict(d0=mode, d1=selector, a0=BUFFER))
    source = 0x601eb5ac
    s.ram('native_initialized_dial_mapping', 0x615fd2ec,
          blob[source-BASE:source-BASE+138])
    until(s, {CALLER+7})
    returned(s)
    bank, mode_class, submode, extra = s.read(BUFFER, 4)
    expected = mode-52+(0 if selector == 1 else 4) if 53 <= mode <= 56 else 0
    assert bank == expected
    if mode in (1, 2, 3, 4):
        assert (mode_class, submode, extra) == (mode+2, 0, 0)
    return dict(input_mode=mode, selector=selector, bank=bank,
                mode_class=mode_class, submode=submode, instructions=s.steps,
                modeled_functions=[])


def save_pair(blob, mode):
    s = ProbeState(0x6075fb08, 0x80, 8, bytes(16), dict(d0=15))
    models = []
    banks = []
    source = 0x601eb5ac
    s.ram('native_initialized_dial_mapping', 0x615fd2ec,
          blob[source-BASE:source-BASE+138])
    while True:
        pc = until(s, {CALLER+7, 0x607600be, 0x602f0d0f, 0x602bdaa5})
        if pc == CALLER+7:
            break
        if pc == 0x607600be:
            # Isolate bank routing from public API-number validation.
            value = mode
        elif pc == 0x602f0d0f:
            value = 0  # settings operation not locked
        else:
            banks.append(s.regs['d0'])
            value = 0  # stop at store helper; no persistent write is modeled
        models.append(dict(entry=hex(pc), return_value=value))
        s.return_from_model(value)
    returned(s)
    assert banks == [mode-52, mode-48]
    return dict(mode_fixture=mode, stores=banks, instructions=s.steps,
                models=models, persistent_write_executed=False)


def filter_roundtrip(bank):
    # Exercise native filtering and both bulk-copy directions. The distinct
    # values are witness data, not valid saturation values for an ISP.
    active = [0x77777777] * (WORDS*2)
    live = [0x90000000 | i for i in range(WORDS)]
    s = ProbeState(0x602c5f5d, 0xf0, 44, bytes(16), dict(d0=bank, d1=3, a0=0))
    s.register(0x8050, 'r', 0)
    s.ram('settings_pointers', 0x61896ed4, struct.pack('<3I', BANKS, ACTIVE, LIVE))
    s.ram('bank_storage_fixture', BANKS, bytes(9*WORDS*2*4))
    s.ram('live_fixture', LIVE, struct.pack('<1274I', *live))
    s.ram('active_fixture', ACTIVE, struct.pack('<2548I', *active))
    until(s, {CALLER+7}, limit=10000000)
    returned(s)
    filtered = s.read(ACTIVE, WORDS*2*4)
    ids = range(931, 967)
    assert all(struct.unpack_from('<I', filtered, i*4)[0] == live[i] for i in ids)
    assert s.read(LIVE, WORDS*4) == struct.pack('<1274I', *live)
    filter_steps = s.steps
    # Use separate proper synthetic CALL instructions for subsequent helpers.
    for target in (0x602f067a, 0x602f063e):
        s2 = ProbeState(target, 0xc0, 12, bytes(16), dict(d0=bank))
        s2.ram('settings_pointers', 0x61896ed4, struct.pack('<2I', BANKS, ACTIVE))
        s2.ram('bank_storage_fixture', BANKS, s.read(BANKS, 9*WORDS*2*4))
        s2.ram('active_fixture', ACTIVE,
               filtered if target == 0x602f067a else bytes(len(filtered)))
        s2.register(0x8050, 'r', 0)
        until(s2, {CALLER+7}, limit=1000000)
        returned(s2)
        s = s2
    assert s.read(ACTIVE, len(filtered)) == filtered
    recall = ProbeState(0x602c5e7b, 0xf0, 44, bytes(16),
                        dict(d0=bank, d1=3, a0=0))
    recall.register(0x8050, 'r', 0)
    recall.ram('settings_pointers', 0x61896ed8, struct.pack('<2I', ACTIVE, LIVE))
    recall.ram('active_fixture', ACTIVE, filtered)
    recall.ram('live_fixture', LIVE, bytes(WORDS*4))
    until(recall, {CALLER+7}, limit=10000000)
    returned(recall)
    recalled = recall.read(LIVE, WORDS*4)
    assert all(struct.unpack_from('<I', recalled, i*4)[0] == live[i] for i in ids)
    return dict(bank=bank, filter_instructions=filter_steps, color_values_preserved=36,
                recall_instructions=recall.steps, filtered_recall_preserves_color=True,
                complete_filtered_bank_restored=True, modeled_functions=[],
                persistent_write_executed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    b = firmware()
    checkpoint_path = Path('analysis/sd_mount/stock-final/run/state.json.gz')
    checkpoint_bytes = checkpoint_path.read_bytes()
    checkpoint = json.loads(gzip.decompress(checkpoint_bytes))
    region = next(r for r in checkpoint['regions'] if r['name']=='flash_copy_40569800')
    initialized = bytes.fromhex(region['hex'])
    assert initialized[0x615fd2ec-region['address']:0x615fd2ec-region['address']+138] == \
        b[0x601eb5ac-BASE:0x601eb5ac-BASE+138]
    local = [local_route(n, e) for n, e in EVENTS.items()]
    global_cases = [global_press(n, e) for n, e in EVENTS.items()]
    properties = [property_identity(p) for p in range(931,967)]
    arrows = [arrow_route(key, event, target, b) for key in (0x13b2,0x13b3,0x13b4)
              for event,target in ((0x9004,0x60cb0684),(0x9006,0x60cb08e5),
                                    (0x9008,0x60cb0bbb),(0x900a,0x60cb0feb))]
    banks = [bank_selection(b, mode, selector) for mode in (1,2,3,4,53,54,55,56)
             for selector in (1,2)]
    pairs = [save_pair(b, mode) for mode in (53,54,55,56)]
    roundtrips = [filter_roundtrip(bank) for bank in (1,5)]
    mode_filters=[]
    for offset in range(0, 100*12, 12):
        mode,sub,pointer,count,_ = struct.unpack_from('<HHIHH', b, 0x603c891c-BASE+offset)
        if mode == 0:
            break
        rows=list(struct.iter_unpack('<HBB', b[pointer-BASE:pointer-BASE+count*4]))
        color=[r for r in rows if 931<=r[0]<=966]
        assert sorted(color)==[(i,0,0) for i in range(931,967)]
        mode_filters.append(dict(mode=mode, submode=sub, records=count,
                                 color_count=len(color), color_part=0))
    report = dict(main_sha256=sha(b), tool_sha256=sha(Path(__file__).read_bytes()),
                  engine_sha256=sha(ENGINE.read_bytes()), local_routes=local,
                  initializer_checkpoint=dict(path=str(checkpoint_path),
                      sha256=sha(checkpoint_bytes),source='0x601eb5ac',
                      runtime='0x615fd2ec',matching_bytes=138),
                  global_filter_cases=global_cases, property_identity=properties,
                  arrows=arrows, bank_selections=banks, save_pairs=pairs,
                  bank_roundtrips=roundtrips, mode_filters=mode_filters,
                  limitations=['No physical input pipeline executed.',
                    'No persistent settings file or hardware write executed.',
                    'Unlisted local events do not establish globally unused buttons.',
                    'Save-pair probe models API mode conversion and settings-operation lock.'])
    (args.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    for name,start,end in (
        ('fsm-engine',0x60bcba4d,0x60bcbc44),
        ('gui-message-loop',0x60bb9376,0x60bb93d6),
        ('global-filter',0x60d12112,0x60d1242a),
        ('actuator-dispatch',0x60c73065,0x60c73588),
        ('COLOR-arrow-actions',0x60cb0684,0x60cb1422),
        ('settings-value-getter',0x607359ef,0x60735a11),
        ('settings-value-forwarder',0x6075f551,0x6075f57a),
        ('dial-bank-selection',0x602b9fce,0x602ba047),
        ('paired-save',0x6075fb08,0x6075fb2f),
        ('save-wrappers',0x602ba141,0x602ba168),
        ('saved-myset-wrapper',0x602ba24d,0x602ba273),
        ('bank-filter-recall-save',0x602c5e7b,0x602c6041),
    ):
        (args.out/(name+'.asm')).write_text(window(b,DEFAULT_IMAGE,DEFAULT_OBJDUMP,start,end))
    print(f'{len(local)+len(global_cases)+len(properties)+len(arrows)+len(banks)+len(pairs)+len(roundtrips)} native cases; '
          f'{len(mode_filters)} mode-filter records checked; no patch output.')


if __name__ == '__main__':
    main()
