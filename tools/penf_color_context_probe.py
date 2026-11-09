#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Offline COLOR task ownership and native request/reply context contracts.

Task 64's real entry wrapper runs the framework pump. The GUI worker has a
separate native creation/entry path. Dynamic GUI IDs, OS services and selected
shooting state remain explicit fixtures; this is not a connected boot replay.
"""
import argparse
import json
from pathlib import Path
import struct

from penf_color_request_probe import (
    CHECKPOINT_SHA, DEFAULT_IMAGE, DEFAULT_OBJDUMP, EMPTY_WAIT, ENGINE,
    Fixture, MAIN_THREAD, RequestContracts, at, continue_case, prepare,
    request_fixture, returned, sha, u32, window, word,
)
from penf_color_controls_probe import fsm_fixture, until
from penf_disasm import BASE
from penf_probe import BUFFER, CALLER, ProbeState
from penf_profile_context_probe import invoke

GUI_OBJECT = 0x190d0000


class ContextContracts(RequestContracts):
    """Current-task queries reflect the active, explicitly scheduled stack."""
    foreground_task = 48

    def model(self):
        s = self.s
        if s.regs['pc'] != 0x60031be2:
            return super().model()
        assert s.regs['mdr'] in (0x6094fdb9, 0x602e1417)
        # The second stack is the dispatcher, whose task-table ID is 64.
        # Foreground IDs after initialization are arbitrary GUI witnesses.
        task = 64 if 0x18110000 <= s.regs['sp'] < 0x18120000 else self.foreground_task
        s.write(s.regs['a0'], struct.pack('<H', task))
        self.events.append(dict(entry='0x60031be2', caller_return=hex(s.regs['mdr']),
                                operation='explicit active-task query', task=task))
        s.return_from_model(0)


def bound_task(s):
    adapter = word(s, MAIN_THREAD+52)
    assert word(s, adapter) == 0x60a4f7bc
    return int.from_bytes(s.read(adapter+4, 2), 'little')


def initialize(f, profile, sector, fill, creator=48):
    e, base, details = prepare(f, profile, sector, fill, 0x10001)
    c = ContextContracts(base)
    c.foreground_task = creator
    init = c.call(0x6094f09e, 0xa0, 12, dict(d0=1))
    returned(e.s, init)
    assert e.s.regs['a0'] == MAIN_THREAD and bound_task(e.s) == creator
    details['native_framework_initialization'] = dict(creator_task=creator, execution=init)
    return e, c, details


def binding_case(f, fill, creator):
    e, c, preparation = initialize(f, 1, 1, fill, creator)
    # Task 64 uses the already-created singleton. It must not silently rebind
    # the adapter to itself or create another queue.
    c.foreground_task = 64
    before = dict(c.heap)
    run = c.call(0x606b486e, 0x20, 8, stop=EMPTY_WAIT)
    at(e.s, run, EMPTY_WAIT)
    assert bound_task(e.s) == creator and c.heap == before
    assert not any(x.get('operation') == 'explicit active-task query' for x in run['models'])
    assert not c.framework_lock
    return dict(kind='precreated_framework_then_task64', fill=hex(fill), creator=creator,
                preparation=preparation, task64_to_empty_wait=run,
                bound_task_after=bound_task(e.s), adapter_not_rebound=True)


def exchange_case(f, profile, sector, fill, gui_task):
    prepared = initialize(f, profile, sector, fill)
    prepared[1].foreground_task = gui_task
    e, c, details = request_fixture(f, profile, sector, fill, 'new',
                                    prepared=prepared, reactive_context=0)
    assert bound_task(e.s) == 48
    result = continue_case(e, c, details, timeout=profile == 1,
                           pump_entry=(0x606b486e, 0x20, 8))
    assert bound_task(e.s) == 48
    queries = [x for x in c.events if x.get('operation') == 'explicit active-task query']
    assert queries[0]['task'] == 48
    assert any(x['task'] == gui_task for x in queries)
    result.update(kind='distinct_GUI_and_dispatcher_request_exchange',
                  explicit_gui_task=gui_task, dispatcher_task=64, adapter_task=48,
                  native_null_context_default=True, task_queries=queries)
    return result


def gui_creation():
    # Start after the GUI message-system initializer. Its state is not needed
    # to inspect the task descriptor; do not replace it with fake success.
    s = ProbeState(0x60bb8d55, 0xb0, 40, b'x', dict(a2=GUI_OBJECT))
    s.ram('GUI_task_holder', GUI_OBJECT, b'\xa5'*8, aliases=False)
    until(s, {0x606f92fc})
    descriptor = struct.unpack('<4I', s.read(s.regs['d1'], 16))
    assert descriptor == (0x60c72e76, 1, 8704, 0)
    assert s.regs['d0'] == 0
    assert s.read(s.regs['a1'], 9) == b'GUI_TASK\0'
    assert s.read(GUI_OBJECT, 8) == b'\xa5'*8
    return dict(kind='native_GUI_creation_descriptor', stop=hex(s.regs['pc']),
                entry=hex(descriptor[0]), descriptor_words=list(map(hex, descriptor)),
                name='GUI_TASK', native_instructions=s.steps,
                scope='Interior creation prefix; stops before task creation API. No allocated GUI ID asserted.')


def gui_entry():
    s = ProbeState(0x60c72e76, 0, 0, b'x', {})
    until(s, {0x60d10620})
    assert s.regs['mdr'] == 0x60c72e88
    s.return_from_model(0)  # Only the reviewed GUI-start diagnostic.
    until(s, {0x60bb914e})
    return dict(kind='native_GUI_entry_to_WinMain', stop=hex(s.regs['pc']),
                native_instructions=s.steps, omitted=['60d10620 GUI-start diagnostic'])


def gui_dispatch(event, missing_fsm=False):
    s = fsm_fixture(event)
    # Interior GUI-loop contract: use its real prefilter and call site. The
    # already-selected editor FSM and received message are explicit inputs.
    s.regs.update(pc=0x60bb9376, sp=0x18018000, a3=BUFFER)
    s.write(BUFFER, struct.pack('<8I', event, 0, 0, BUFFER+24, 0, 0, 0, 0))
    s.write(s.regs['sp']+396, s.read(BUFFER, 28))
    s.ram('nonmodal_GUI_filter', 0x6161bde8, bytes(36))
    if not missing_fsm:
        s.ram('GUI_selected_FSM', 0x6160c04c, struct.pack('<I', 0x19000000))
    r = s.run({0x60cefd3d, 0x60bb939c}, limit=5000)
    if missing_fsm:
        assert r['status'] == 'memory_fault' and s.regs['pc'] == 0x60bb938f, r
        assert r['fault']['address'] == 0x6160c04c
    else:
        expected = 0x60bb939c if event == 0x9016 else 0x60cefd3d
        assert r['status'] == 'breakpoint' and s.regs['pc'] == expected, r
        if expected == 0x60cefd3d:
            assert s.regs['d0'] == event
        else:
            assert s.regs['d0'] == 3  # unlisted in selected editor
    return dict(kind='native_GUI_loop_to_COLOR_action', event=hex(event),
                missing_fsm=missing_fsm, stop=hex(s.regs['pc']), status=r['status'],
                fault=r.get('fault'), native_instructions=s.steps, modeled_functions=[])


def initialization_event_case(fill, present):
    s = ProbeState(0x609377b3, 0, 4, b'x', dict(a0=GUI_OBJECT))
    s.ram('native_init_event_destination', GUI_OBJECT, bytes([fill])*28, aliases=False)
    until(s, {CALLER+7})
    assert word(s, GUI_OBJECT) == 0x60a49bac
    assert int.from_bytes(s.read(GUI_OBJECT+4, 2), 'little') == 11562
    component = GUI_OBJECT+0x1000
    s.ram('only_component_current_event', component+104,
          struct.pack('<I', GUI_OBJECT if present else 0), aliases=False)
    gate = invoke(s, 0x609280b4, 0xa0, 12, dict(a0=component), stops=(0x6092809b,))
    expected = 0x6092809b if present else CALLER+7
    at(s, gate, expected)
    continuation = None
    if present:
        # The next transition genuinely needs the old substate. Do not turn
        # this boundary into state14 by inserting a guessed zero.
        r = s.run({CALLER+7}, limit=5000)
        assert r['status'] == 'memory_fault' and s.regs['pc'] == 0x60928052, r
        assert r['fault']['address'] == component+556
        continuation = dict(status=r['status'], pc=hex(s.regs['pc']), fault=r['fault'])
    else:
        assert s.regs['d0'] == 0
    return dict(kind='native_init_success_event_gate', fill=hex(fill), present=present,
                gate=gate, strict_transition_boundary=continuation,
                native_instructions=s.steps, modeled_functions=[])


WINDOWS = {
    'ustart4-init-before-task64': (0x601a7ed1, 0x601a7f57),
    'framework-boot-initializer': (0x606b4800, 0x606b4869),
    'framework-init-main-singleton': (0x60951fdf, 0x60952027),
    'task64-entry': (0x606b4869, 0x606b4892),
    'framework-run-wrapper': (0x60952058, 0x60952098),
    'main-singleton-and-run': (0x6094f07b, 0x6094f15a),
    'thread-context-constructor': (0x60951d9b, 0x60951e25),
    'task-adapter-constructor': (0x60950599, 0x609505b0),
    'reactive-null-context': (0x60950eee, 0x60950f2a),
    'GUI-creation': (0x60bb8d4b, 0x60bb8d9b),
    'GUI-start-callsite': (0x60ba1eb0, 0x60ba1f3c),
    'GUI-entry': (0x60c72e76, 0x60c72e92),
    'GUI-loop-and-FSM': (0x60bb914e, 0x60bb93d6),
    'FSM-constructor': (0x60bcb9d6, 0x60bcba41),
    'NEW-init-success-event': (0x609280b4, 0x6092810a),
    'NEW-active-transition': (0x6092809b, 0x609280b4),
    'NEW-active-entry': (0x60928730, 0x60928767),
    'NEW-state14-entry': (0x6092a013, 0x6092a028),
    'NEW-init-exit-boundary': (0x6092804d, 0x6092806e),
    'init-event-constructor': (0x609377b3, 0x609377db),
    'shooting-factory-allocation': (0x609274a3, 0x609274e6),
    'shooting-factory-selected-child': (0x60927609, 0x60927610),
    'shooting-factory-caller': (0x6094b484, 0x6094b4aa),
    'selected-leaf-getter': (0x60934649, 0x60934672),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', required=True, type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    f = Fixture()
    assert sha(f.image) == 'a2eb1d1f1afe47cce148e9aae0a04dfb82547d9de9437d342e012341140913f4'
    cases = [gui_creation(), gui_entry()]
    cases += [gui_dispatch(event) for event in (0x9004, 0x9006, 0x9016)]
    cases.append(gui_dispatch(0x9004, missing_fsm=True))
    cases += [initialization_event_case(fill, present)
              for fill in (0, 0xa5) for present in (False, True)]
    for fill in (0, 0xa5):
        for creator in (48, 64, 200):
            cases.append(binding_case(f, fill, creator))
            print(f'Native precreated context {creator}, task64 pump, fill {fill:#x}: passed', flush=True)
        for profile, sector in ((1, 1), (2, 6), (3, 12)):
            gui_task = 200+profile
            cases.append(exchange_case(f, profile, sector, fill, gui_task))
            print(f'COLOR{profile}: explicit GUI {gui_task}, dispatcher64, fill {fill:#x}: passed', flush=True)
    directory = args.out/'disassembly'
    directory.mkdir()
    windows = {}
    for name, (lo, hi) in WINDOWS.items():
        (directory/(name+'.asm')).write_text(window(f.image, DEFAULT_IMAGE, DEFAULT_OBJDUMP, lo, hi))
        windows[name] = dict(start=hex(lo), end=hex(hi), sha256=sha(f.image[lo-BASE:hi-BASE]))
    sources = [Path(__file__)] + [Path('tools')/name for name in (
        'penf_color_request_probe.py', 'penf_color_notification_probe.py',
        'penf_color_refresh_probe.py', 'penf_color_edit_probe.py',
        'penf_color_controls_probe.py', 'penf_profile_context_probe.py',
        'penf_profile_followup_probe.py', 'penf_profile_lifecycle_probe.py',
        'penf_probe.py', 'penf_boot_emulator.py', 'penf_emulator.py',
        'penf_recovery_isolation_probe.py', 'penf_disasm.py')]
    report = dict(main_sha256=sha(f.image), checkpoint_sha256=CHECKPOINT_SHA,
                  engine_sha256=sha(ENGINE.read_bytes()),
                  source_sha256={str(p): sha(p.read_bytes()) for p in sources},
                  cases=cases, windows=windows,
                  limits=[
                      'Native paths are bounded contracts, not an uninterrupted startup or RTOS scheduler replay.',
                      'GUI creation, worker entry, loop dispatch and reply exchange are separately tested joins.',
                      'GUI IDs 201-203 are explicit witnesses; real dynamic task IDs remain unknown.',
                      'OS FIFO, flags, handles, heap, mutual exclusion and scheduling remain models.',
                      'Selected factory/root, state10001, state14, sequence/cache and child gates retain prior fixture assumptions.',
                      'Native init-event11562 check reaches transition6092809b; missing old substate+556 faults. Producer and full state14 transition remain open.',
                      'No physical display, ISP, capture, persistence, recovery guarantee or firmware modification.',
                  ])
    (args.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f'{len(cases)} context contracts and controls passed.', flush=True)


if __name__ == '__main__':
    main()
