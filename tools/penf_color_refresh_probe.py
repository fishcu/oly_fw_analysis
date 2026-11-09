#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native current-context COLOR refresh and bounded viewer continuation.

No camera I/O, patched image, or generic peripheral-success hook. The original
strict edit stop is retained. Recording-memory constructors run natively;
only reviewed exclusion primitives have an explicit uncontended model.
"""
import argparse
import json
from pathlib import Path
import struct

from penf_color_edit_probe import (
    CALLER, CHECKPOINT_SHA, COLOR, DEFAULT_IMAGE, DEFAULT_OBJDUMP,
    ENGINE, Editor, Fixture, REFRESH, UP, VIEWER, at, compact, current_record,
    image_snapshot, invoke, resume, returned, sha, signed, u32, window,
)
from penf_recovery_isolation_probe import without_ranges

POOL = 0x61c69320
HOLE = (0x6069b2b0, 0x6069b7c0)
POST_CHANGE = 0x607607a1
INT_ENTER, INT_LEAVE = 0x60086c0b, 0x60086c54
HW_ENTER, HW_LEAVE = 0x60070bc0, 0x60070cb1
SEM_ENTER, SEM_LEAVE = 0x60069606, 0x600696f9
MODELS = {INT_ENTER, INT_LEAVE, HW_ENTER, HW_LEAVE, SEM_ENTER, SEM_LEAVE}
OBSERVE = {REFRESH, 0x602bc3e3, 0x6030981f, 0x60549311,
           0x60549048, 0x6054907b, 0x60538017}
DISPLAY_STORE = 0x190b0000
DISPLAY_ROWS = ((179, 0x619bd870, 96), (209, 0x619c0b30, 12))
EDIT_CONTEXT_ROW = (176, 0x619bd18c, 1556)
VIEW_CALLBACKS = (0x60c849b3, 0x60c84bcd, 0x60c84cf0, 0x60c8504f)
REFRESH_KEYS = [8, 7, 59, 307, 130, 131, 105, 1213, 362, 394, 395, 396,
                424, 425, 593, 594, 666, 667, 397, 876,
                *range(919, 931), 994, 998, 984, 384, 698, 383]


def memory_initialize(e, fill):
    """Use the previously audited section-3 destination bounds, not fault fill."""
    s, f = e.s, e.f
    # This six-byte captured extent belongs to the larger native manager.
    # Remove exactly it and its alias before replacing the owning extent.
    removed = [r for r in s.regions if r.address in (0x61c6bca0, 0xa1c6bca0)]
    assert len(removed) == 2 and all(len(r.data) == 6 for r in removed)
    s.regions = [r for r in s.regions if r not in removed]
    s.regions = without_ranges(s.regions, [HOLE])
    s.ram('native_section3_objects', POOL, bytes([fill])*0x30c0)
    s.ram('native_internal_objects', 0x8ff001b4, bytes([fill])*0x240, aliases=False)
    constructors = invoke(s, 0x6006da8c, 0xa0, 12, dict(d0=3))
    returned(s, constructors)
    # Also initialize the manager's non-constructor state, including the
    # three halfwords at a1c6bca0 and four packed software-lock bytes.
    manager = invoke(s, 0x60548891, 0, 4)
    returned(s, manager)
    assert s.read(0xa1c6bca0, 6) == bytes(6)
    assert s.read(0xa1c6c38c, 4) == bytes(4)
    # rec_mem.c's separate mode byte and one pointer. This is a reviewed
    # captured *empty* scenario, not a claim about every running camera.
    data = f.read(0x61c6867c, 8)
    assert data == bytes(8)
    s.ram('captured_empty_rec_mem_state', 0x61c6867c, data)
    return dict(initial_fill=hex(fill), constructors=compact(constructors),
                manager=compact(manager), pool_before=s.read(POOL, 68).hex(),
                inaccessible_code_range=list(map(hex, HOLE)),
                captured_empty_rec_mem_state=data.hex())


class Exclusion:
    """Only the reviewed rec_mem/memory-manager critical sections may pass."""
    def __init__(self, semaphore=True):
        self.phase = 0
        self.semaphore_held = False
        self.semaphore_enabled = semaphore
        self.events = []

    @property
    def hooks(self):
        return MODELS if self.semaphore_enabled else MODELS-{SEM_ENTER, SEM_LEAVE}

    def handle(self, s):
        pc, ret, arg = s.regs['pc'], s.regs['mdr'], s.regs['d0']
        result = 0
        if pc == INT_ENTER:
            assert (ret, arg, self.phase) == (0x60549dd4, 0, 0)
            self.phase = 1
            result = 0x2400  # opaque saved-state witness, checked on restoration
        elif pc == HW_ENTER:
            assert (ret, arg, s.regs['d1'], self.phase) == (0x60549de3, 0x1e18001e, 0, 1)
            self.phase = 2
            result = 30
        elif pc == HW_LEAVE:
            assert (ret, arg, self.phase) == (0x60549e11, 0x1e18001e, 2)
            self.phase = 3
        elif pc == INT_LEAVE:
            assert (ret, arg, self.phase) == (0x60549e19, 0x2400, 3)
            self.phase = 0
        elif pc == SEM_ENTER:
            assert (ret, arg, s.regs['d1']) == (0x6053974d, 99, 0xffffffff)
            assert self.phase == 0 and not self.semaphore_held
            self.semaphore_held = True
        elif pc == SEM_LEAVE:
            assert (ret, arg) == (0x60539757, 99)
            assert self.phase == 0 and self.semaphore_held
            self.semaphore_held = False
        else:
            raise AssertionError(hex(pc))
        self.events.append(dict(entry=hex(pc), caller_return=hex(ret),
                                argument=hex(arg), result=hex(result)))
        s.return_from_model(result)

    def balanced(self):
        assert self.phase == 0 and not self.semaphore_held


def drive(s, exclusion, end=POST_CHANGE):
    start = s.steps
    observations = []
    hooks = exclusion.hooks | OBSERVE | {end}
    for _ in range(300):
        r = resume(s, hooks)
        pc = s.regs['pc']
        if r['status'] != 'breakpoint' or pc == end:
            break
        if pc in exclusion.hooks:
            exclusion.handle(s)
        else:
            item = dict(entry=hex(pc), caller_return=hex(s.regs['mdr']),
                        d0=s.regs['d0'], d1=s.regs['d1'])
            if pc == 0x602bc3e3:
                item.update(property=s.regs['a0'], value=signed(s.regs['a1']))
            observations.append(item)
            # Observe a real entry without replacing any instruction/call.
            step = s.run(hooks-{pc}, limit=1)
            assert step['status'] == 'instruction_limit' and step['completed'] == 1
    else:
        raise AssertionError('Unexpected repeated boundary')
    exclusion.balanced()
    return dict(**compact(r), total_instructions=s.steps-start,
                observations=observations, exclusion_calls=exclusion.events)


def strict_controls(f):
    e = Editor(f, 1, 1, -3)
    e.input(UP); e.guards()
    original = resume(e.s, (CALLER+7,))
    assert original['status'] == 'memory_fault' and original['pc'] == '0x60549d65'
    assert original['fault']['address'] == 0xa1c6c38e
    e = Editor(f, 1, 1, -3)
    initialization = memory_initialize(e, 0xa5)
    e.input(UP); e.guards()
    semaphore = drive(e.s, Exclusion(semaphore=False))
    assert semaphore['status'] == 'memory_fault' and semaphore['pc'] == '0x60037fae'
    assert semaphore['fault']['address'] == 0x61835820
    return dict(original_fixture=compact(original),
                initialized_without_semaphore_model=semaphore,
                initialization=initialization)


def viewer_initialize(e):
    s, f = e.s, e.f
    # Native GUI initialization registers the 211 descriptors at 6160b31c.
    # Supply the viewer's destinations plus the generic child's edit-context
    # payload, read at 60c80965 and conditionally written at 60c809cf before
    # the property setter. Do not conflate that block with the COLOR wheel.
    for key, address, size in DISPLAY_ROWS+(EDIT_CONTEXT_ROW,):
        descriptor = struct.unpack('<4I', s.read(0x6160b31c+key*16, 16))
        assert descriptor == (0, 0, address, size)
        s.ram(f'captured_display_{key}', address, f.read(address, size))
    # Record c321: one byte, read by the native display-state query.
    descriptor = struct.unpack('<HHI', s.read(0x61c281e4+(0xc321 >> 4)*8, 8))
    assert descriptor == (0xc321, 1, 0x61ae93b8)
    s.ram('captured_display_state_record', 0x61ae93b8, f.read(0x61ae93b8, 1))
    # Native status-indicator callback queries cached input state 02021906.
    # Same reviewed key-state structure as the earlier input investigation.
    s.ram('captured_input_state', 0x61c57fd8, f.read(0x61c57fd8, 0x500))
    s.ram('native_display_store_object', DISPLAY_STORE, bytes(28), aliases=False)
    results = []
    for fun, mask, frame, regs in (
        (0x60c848ed, 0, 4, dict(a1=VIEWER)),
        (0x60bbaa1b, 0x20, 8, dict(a0=DISPLAY_STORE)),
        (0x60bbaa75, 0xf0, 24, dict(a0=DISPLAY_STORE, a1=0x6160b31c, d0=211)),
    ):
        r = invoke(s, fun, mask, frame, regs)
        returned(s, r)
        results.append(dict(entry=hex(fun), **compact(r)))
    assert r['result'] == 1
    assert struct.unpack('<5I', s.read(VIEWER+4, 20)) == VIEW_CALLBACKS+(0,)
    # Empty observer list is constructor state, not the full drawing engine.
    assert struct.unpack('<3I', s.read(DISPLAY_STORE+16, 12)) == (
        DISPLAY_STORE+16, DISPLAY_STORE+16, 0)
    assert s.read(0x6160c154, 16) == bytes(16)  # no display mutex/lifecycle callbacks
    u32(s, 0x6160c068, DISPLAY_STORE)
    u32(s, 0x61619ebc, 129)  # this test updates an already selected editor
    return dict(native_initialization=results, descriptor_table='0x6160b31c',
                descriptor_count=211, destinations=DISPLAY_ROWS+(EDIT_CONTEXT_ROW,),
                scope='Already selected screen; native display store with no drawing observers')


def full_viewer(e):
    s = e.s
    hooks = set(VIEW_CALLBACKS) | {0x60bba9e5, 0x60bba9fd, CALLER+7}
    start = s.steps
    r = invoke(s, 0x60c84901, 0, 0, dict(a0=VIEWER), stops=hooks)
    seen, transfers = [], []
    for _ in range(20):
        if r['status'] != 'breakpoint' or s.regs['pc'] == CALLER+7:
            break
        pc = s.regs['pc']
        if pc in VIEW_CALLBACKS:
            seen.append(hex(pc))
        else:
            assert (s.regs['d0'], s.regs['d1'], s.regs['a0']) in (
                (179, 96, VIEWER+36), (209, 12, VIEWER+132))
            transfers.append(dict(direction='read' if pc == 0x60bba9e5 else 'write',
                                  parameter=s.regs['d0'], bytes=s.regs['d1']))
        step = s.run(hooks-{pc}, limit=1)
        assert step['status'] == 'instruction_limit' and step['completed'] == 1
        r = resume(s, hooks)
    returned(s, r)
    assert seen == list(map(hex, VIEW_CALLBACKS))
    assert [t['direction'] for t in transfers] == ['read', 'read', 'write', 'write']
    wheel = s.read(0x619bd870, 96)
    status = s.read(0x619c0b30, 12)
    assert wheel == s.read(VIEWER+36, 96) and status == s.read(VIEWER+132, 12)
    value = current_record(e.f, s, e.key)
    assert list(wheel[1:3]) == [3 if value < 0 else 2 if value > 0 else 1, abs(value)+1]
    assert wheel[88:92] == b'\x01\0\0\0'
    return dict(**compact(r), total_instructions=s.steps-start, callbacks=seen,
                transfers=transfers, wheel_hex=wheel.hex(), status_hex=status.hex(),
                selected_value=value, separate_invocation=True,
                scope='Complete native viewer and RAM parameter copies; no LCD or drawing observers')


def post_change_gate(e, value, connected=False):
    """Sensitivity test ending at native receiver creation, BEFORE dispatch.

    The state producer is outside this test. Map only the fields the reached
    mediator getter reads. All other fields remain inaccessible; this is not
    a constructor substitute for a usable application mediator.
    """
    s = e.s
    mediator, event = 0x190c0000, 0x190c1000
    s.ram('supplied_mediator_state', mediator+4, struct.pack('<I', value), aliases=False)
    s.ram('mediator_mutex_witness', mediator+24,
          struct.pack('<2I', 0x609524c0, 0xdeadffff), aliases=False)
    u32(s, 0x61602c44, mediator)
    enter, leave, allocate, receiver = 0x606b4d81, 0x606b4d91, 0x60950a6e, 0x606f11d6
    hooks = {enter, leave, allocate, receiver, CALLER+7}
    start = s.steps
    if connected:
        assert s.regs['pc'] == POST_CHANGE
        r = resume(s, hooks)
    else:
        r = invoke(s, POST_CHANGE, 0x30, 48, dict(a0=0, d0=e.key), stops=hooks)
    held, allocated, models = False, False, []
    for _ in range(6):
        if r['status'] != 'breakpoint' or s.regs['pc'] in (receiver, CALLER+7):
            break
        pc = s.regs['pc']
        if pc == enter:
            assert s.regs['a0'] == mediator+24 and not held
            held = True
            s.return_from_model(0)
        elif pc == leave:
            assert s.regs['a0'] == mediator+24 and held
            held = False
            s.return_from_model(0)
        else:
            assert pc == allocate and not allocated
            assert s.regs['d0'] == 32 and s.regs['mdr'] == 0x607607fd
            s.ram('native_state_event_destination', event, b'\xa5'*32, aliases=False)
            s.regs['a0'] = event
            s.return_from_model(0)
            allocated = True
        models.append(dict(entry=hex(pc), operation='32-byte allocation' if pc == allocate else 'uncontended mediator lock'))
        r = resume(s, hooks)
    assert not held
    passes = 0x10000 < value <= 0x1ffff
    if passes:
        at(s, r, receiver)
        assert allocated and s.regs['mdr'] == 0x6076080b
        assert s.read(event, 32) == b'\xa5'*32  # constructor is AFTER this dependency
    else:
        returned(s, r)
        assert not allocated
    return dict(**compact(r), total_instructions=s.steps-start,
                supplied_application_state=hex(value), receiver_requested=passes,
                connected_from_edit=connected, modeled_operations=models,
                event_allocation_bytes=32 if passes else 0,
                scope='Native state test; state supplied, receiver creation/event construction/delivery pending')


def evidence(f, out):
    spans = {
        'pool-constructor': (0x60547d3e, 0x60547ed8),
        'manager-initialize': (0x60548891, 0x605488ae),
        'mode-state-initialize': (0x605492f7, 0x605493df),
        'pool-reservation-selection': (0x60549048, 0x60549089),
        'pool-reservation-bits': (0x6054a837, 0x6054a8b8),
        'software-locks': (0x60549d3e, 0x60549e1c),
        'recording-notify-api': (0x6030981f, 0x60309850),
        'recording-memory-policy': (0x60537d56, 0x605380cb),
        'current-refresh': (0x602c50be, 0x602c52ff),
        'post-edit-state-event': (0x607607a1, 0x60760828),
        'state-event-constructor': (0x606c003e, 0x606c0069),
        'receiver-creation': (0x606f1117, 0x606f145e),
        'immediate-and-deferred-observers': (0x60760063, 0x6076062d),
        'settings-manager-constructor': (0x6075eed9, 0x6075efce),
        'viewer-update': (0x60c848ed, 0x60c849b3),
        'viewer-callbacks': (0x60c849b3, 0x60c850e1),
        'display-store': (0x60bba9e5, 0x60bbac3d),
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
    report = dict(camera_used=False, firmware_modified=False,
                  main_sha256=sha(f.image), checkpoint_sha256=CHECKPOINT_SHA,
                  engine_sha256=sha(ENGINE.read_bytes()),
                  strict_controls=strict_controls(f), cases=[])
    report['application_state_gate_controls'] = [
        post_change_gate(Editor(f, 1, 1, -3), value)
        for value in (0, 0x10000, 0x10001, 0x1ffff, 0x20000)]
    for fill in (0, 0xa5):
        for profile, sector in ((1, 1), (2, 6), (3, 12)):
            e = Editor(f, profile, sector, -3)
            initialization = memory_initialize(e, fill)
            display_initialization = viewer_initialize(e)
            display_before = full_viewer(e)
            before = [current_record(f, e.s, k) for k in COLOR]
            route, guards = e.input(UP), e.guards()
            result = drive(e.s, Exclusion())
            at(e.s, result, POST_CHANGE)
            assert e.s.regs['d0'] == e.key
            derived = [x for x in result['observations'] if 'property' in x]
            assert [x['property'] for x in derived] == REFRESH_KEYS
            assert all((x['d0'], x['d1']) == (0, 2) for x in derived)
            after = [current_record(f, e.s, k) for k in COLOR]
            assert [i for i, pair in enumerate(zip(before, after)) if pair[0] != pair[1]] == [e.key-931]
            assert after[e.key-931] == -2
            expected = after[(profile-1)*12:profile*12]
            actual = [current_record(f, e.s, k) for k in range(919, 931)]
            assert actual == expected
            assert e.s.read(0xa1c6c38c, 4) == bytes(4)
            assert e.s.read(POOL+64, 4) == struct.pack('<I', 0x00ff0000)
            assert e.s.read(0xa1c6bca0, 6) == b'\x01\0\0\0\0\0'
            case = dict(profile=profile, sector=sector, initial_fill=hex(fill),
                        initialization=initialization, route=route, guards=guards,
                        current_refresh=result, effective_values=actual,
                        current_refresh_completed=True,
                        display_initialization=display_initialization,
                        display_before=display_before,
                        pool_after=e.s.read(POOL, 68).hex(),
                        memory_mode_state=e.s.read(0xa1c6bca0, 6).hex())
            case['post_change_event_boundary'] = post_change_gate(e, 0x10001, connected=True)
            # Independent invocation after stopping the outer edit at its next
            # dependency. This checks refresh with already reserved memory.
            warm = invoke(e.s, REFRESH, 0x80, 160, dict(d0=0, d1=53+profile),
                          stops=(REFRESH,))
            at(e.s, warm, REFRESH)
            case['repeat_current_refresh'] = drive(e.s, Exclusion(), CALLER+7)
            returned(e.s, case['repeat_current_refresh'])
            assert [current_record(f, e.s, k) for k in range(919, 931)] == expected
            case['display_after'] = full_viewer(e)
            before_bytes = bytes.fromhex(display_before['wheel_hex'])
            after_bytes = bytes.fromhex(case['display_after']['wheel_hex'])
            case['wheel_changed_offsets'] = [i for i, pair in enumerate(zip(before_bytes, after_bytes))
                                            if pair[0] != pair[1]]
            assert case['wheel_changed_offsets'] == [2]
            assert display_before['status_hex'] == case['display_after']['status_hex']
            # The actual current refresh supplies these parameters. No staged
            # refresh or staged-to-current commit is inserted this time.
            case['separate_capture_contract'] = image_snapshot(f, e.s, expected)
            report['cases'].append(case)
            print(f'COLOR{profile}, fill {fill:#x}: refresh, repeat, complete viewer and snapshot passed', flush=True)
    report['limits'] = [
        'Selected editor fixture; physical input, entry and scheduler excluded',
        'Native section-3 constructors plus manager initialization; not connected boot',
        'Empty recording auxiliary pool; native memory decisions, explicit uncontended locks',
        'Outer edit reaches receiver creation for event 404e with supplied application-state witness; delivery unmodeled',
        'Repeated refresh, complete viewer and capture-copy contracts are separate invocations',
        'Viewer has native descriptor registration and an empty drawing-observer list',
        'No image payload buffer, ISP execution, physical display or persistence tested',
    ]
    report['source_sha256'] = {str(p): sha(p.read_bytes()) for p in (
        Path(__file__), Path('tools/penf_color_edit_probe.py'),
        Path('tools/penf_profile_context_probe.py'), Path('tools/penf_profile_followup_probe.py'),
        Path('tools/penf_profile_lifecycle_probe.py'), Path('tools/penf_probe.py'),
        Path('tools/penf_boot_emulator.py'), Path('tools/penf_recovery_isolation_probe.py'))}
    evidence(f, args.out)
    (args.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
