#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native COLOR notification/return and state-request construction contracts.

No camera access or firmware changes. The no-state-request case returns on
the original edit stack; the active-state case stops before camera-state
dispatch. Allocation, OS handles, exclusion and timer scheduling are explicit
bounded models. Unknown accesses/instructions still stop native execution.
"""
import argparse
import json
from pathlib import Path
import struct

from penf_color_refresh_probe import (
    CALLER, CHECKPOINT_SHA, DEFAULT_IMAGE, DEFAULT_OBJDUMP, ENGINE,
    Editor, Exclusion, Fixture, POST_CHANGE, UP, VIEWER, VIEW_CALLBACKS,
    at, compact, current_record, drive, full_viewer, invoke, memory_initialize,
    resume, returned, sha, u32, viewer_initialize, window,
)
from penf_color_edit_probe import CONTROLLER, MUTEX_OBJECTS

MANAGER, MEDIATOR, DIRTY = 0x19035000, 0x190c0000, 0x190a00fc
SEQUENCE = 0x23000000
REQUEST = 0x6075d593
LISTENERS = (0x606ba61c, 0x606da12e, 0x606ef6eb, 0x6075c8e0)
ALLOCATORS = {0x60950a6e, 0x60950a78, 0x609520a6}
# (allocator entry, caller return) -> exact reviewed requested size.
ALLOCATIONS = {
    (0x60950a6e, 0x606bb53d): 8,       # timer semaphore wrapper
    (0x60950a6e, 0x609509dc): 8,       # native ITRON semaphore adapter
    (0x60950a6e, 0x609509b6): 16,      # native ITRON mutex adapter
    (0x609520a6, 0x6075ef17): 80,      # general listener vector
    (0x609520a6, 0x6075ef3e): 80,      # 32 grouped listener vectors
    (0x609520a6, 0x6075ef76): 80,      # pending changed IDs
    (0x609520a6, 0x6075ef9c): 80,
    (0x609520a6, 0x6076010a): 80,      # general listener snapshot
    (0x609520a6, 0x606b53e1): 80,      # vector copy replacement
    (0x609520a6, 0x607601de): 80,      # deferred changed-ID snapshot
    (0x609520a6, 0x6076021f): 80,      # replacement pending vector
    (0x609520a6, 0x60760546): 80,      # grouped listener snapshot
    (0x60950a6e, 0x607607fd): 32,      # event404e
    (0x60950a6e, 0x606f142a): 180,     # shared responder
    (0x60950a6e, 0x606f1397): 12,      # reply wrapper
    (0x60950a6e, 0x606f1539): 24,      # RcvParamManager
    (0x60950a78, 0x606f162a): 1024,    # its native collection
    (0x60950a6e, 0x60950993): 28,      # current-thread adapter
    (0x60950a6e, 0x6095090d): 56,      # framework queue
    (0x609520a6, 0x607f38a3): 1600,    # queue's 400-pointer collection
    (0x60950a78, 0x606b4e2d): 8,       # two ComResource semaphore slots
    (0x60950a6e, 0x606b4e63): 8,       # shared-request semaphore wrapper
}
CREATORS = {0x6003059d: (0x6095076d, 'mutex'),
            0x60030635: (0x6094fe2c, 'semaphore'),
            0x600301e1: (0x609503b6, 'flag'),
            0x60030127: (0x6094ff3d, 'queue')}
OBSERVATIONS = set(LISTENERS+VIEW_CALLBACKS) | {
    0x606f11d6, 0x606c003e, 0x606f11e8, 0x6076081d,
    0x60760063, 0x607600e2, 0x60cd04b7, 0x60c84901,
    0x60bba9e5, 0x60bba9fd, 0x60760519,
}


def word(s, address):
    return int.from_bytes(s.read(address, 4), 'little')


class Contracts:
    """Guarded heap plus only the reviewed OS and exclusion boundaries."""
    def __init__(self, s, fill, fail_event=False):
        self.s, self.fill, self.fail_event = s, fill, fail_event
        self.next_address = 0x22000000
        self.heap, self.handles, self.held = {}, {}, set()
        self.events, self.observations, self.timers = [], [], []
        self.private_wait = None

    @property
    def hooks(self):
        return ALLOCATORS | set(CREATORS) | OBSERVATIONS | {
            0x609520b0, 0x606b4d81, 0x606b4d91, 0x606b5072,
            0x606b5062, 0x60086eaa, 0x60031be2, CALLER+7,
        }

    def run(self, initial=None, stop=CALLER+7):
        s = self.s
        hooks = self.hooks | {stop}
        start = s.steps - (initial['instructions'] if initial else 0)
        first_event, first_observation = len(self.events), len(self.observations)
        r = initial or resume(s, hooks)
        for _ in range(350):
            pc = s.regs['pc']
            if r['status'] != 'breakpoint' or pc == stop:
                break
            if pc in OBSERVATIONS:
                item = dict(entry=hex(pc), caller_return=hex(s.regs['mdr']),
                            a0=hex(s.regs['a0']), a1=hex(s.regs['a1']),
                            d0=s.regs['d0'], d1=s.regs['d1'])
                if pc == 0x60760519:
                    item['group'] = s.regs['d3']
                    item['selected'] = s.read(word(s, s.regs['sp']+12), 1)[0]
                self.observations.append(item)
                step = s.run(hooks-{pc}, limit=1)
                assert step['status'] == 'instruction_limit' and step['completed'] == 1
            else:
                self.model()
            r = resume(s, hooks)
        else:
            raise AssertionError('Unexpected repeated boundary')
        return dict(**compact(r), total_instructions=s.steps-start,
                    models=self.events[first_event:],
                    observations=self.observations[first_observation:])

    def model(self):
        s = self.s
        pc, ret, a, d = (s.regs[k] for k in ('pc', 'mdr', 'a0', 'd0'))
        item = dict(entry=hex(pc), caller_return=hex(ret))
        result = 0
        if pc in ALLOCATORS:
            assert ALLOCATIONS[(pc, ret)] == d
            if self.fail_event and ret == 0x607607fd:
                s.regs['a0'] = 0
                item.update(operation='injected allocation failure', bytes=d)
            else:
                ptr = self.next_address
                self.next_address += 0x1000
                assert d < 0x1000
                s.ram('guarded_allocation_'+hex(ptr), ptr, bytes([self.fill])*d, aliases=False)
                self.heap[ptr] = dict(bytes=d, caller=ret)
                s.regs['a0'] = ptr
                item.update(operation='allocation', bytes=d, address=hex(ptr))
        elif pc == 0x609520b0:
            assert ret in (0x606b53c9, 0x606b4978, 0x6076020d)
            allocation = self.heap.pop(a)
            assert allocation['bytes'] == 80
            # Remove the extent: any later use-after-free must fault.
            s.regions = [region for region in s.regions if region.address != a]
            item.update(operation='free', address=hex(a))
        elif pc in CREATORS:
            expected_ret, kind = CREATORS[pc]
            assert ret == expected_ret
            attr = s.read(a, 1)[0]
            if kind == 'mutex':
                assert attr == 2 and s.read(a+2, 2) == bytes(2)
                config = dict(attribute=attr, ceiling=0)
            elif kind == 'semaphore':
                assert (attr, word(s, a+4), word(s, a+8)) == (1, 1, 1)
                config = dict(attribute=attr, initial=1, maximum=1)
            elif kind == 'flag':
                assert attr == 3 and word(s, a+4) == 0
                config = dict(attribute=attr, pattern=0)
            else:
                assert (attr, word(s, a+4), word(s, a+8)) == (0, 400, 0)
                config = dict(attribute=attr, capacity=400, storage=0)
            result = 101+len(self.handles)
            self.handles[result] = kind
            item.update(operation='create OS '+kind, handle=result, config=config)
        elif pc in (0x606b4d81, 0x606b4d91):
            enter = pc == 0x606b4d81
            callers = {
                MANAGER+552: ({0x6075f04a, 0x60760119, 0x6076008a, 0x607601f1, 0x60760551},
                              {0x6075f05e, 0x6076012d, 0x607600bb, 0x6076022a, 0x60760565}),
                MEDIATOR+24: ({0x6075cf5a}, {0x6075cf65}),
                MUTEX_OBJECTS+16: ({0x606f140d}, {0x606f1452}),
                0x618d4888: ({0x606b6595}, {0x606b65a3}),
            }
            registry = word(s, 0x61602474)
            if registry:
                callers[registry+16] = ({0x606f15a1}, {0x606f15f2})
            assert ret in callers[a][0 if enter else 1]
            if enter:
                assert a not in self.held
                self.held.add(a)
            else:
                assert a in self.held
                self.held.remove(a)
            item.update(operation='uncontended mutex enter' if enter else 'mutex leave', address=hex(a))
        elif pc in (0x606b5072, 0x606b5062):
            enter = pc == 0x606b5072
            timer = word(s, 0x61600c1c)
            if ret in (0x606bb56f, 0x606bb5a5):
                assert a == timer
            elif ret == 0x606f129d:
                assert a == word(s, word(s, 0x61600950))
            elif ret == 0x606f1a2d:
                # Native stack-resident semaphore just constructed for reply wait.
                assert a == s.regs['sp']+16
                self.private_wait = a
            else:
                raise AssertionError(hex(ret))
            assert word(s, a) == 0x609524f0
            assert self.handles[int.from_bytes(s.read(word(s, a+4)+4, 2), 'little')] == 'semaphore'
            if enter:
                assert d == 0xffffffff and a not in self.held
                self.held.add(a)
            else:
                assert a in self.held
                self.held.remove(a)
            result = 1  # wrapper's boolean success, not kernel E_OK
            item.update(operation='available semaphore take' if enter else 'semaphore give', address=hex(a))
        elif pc == 0x60086eaa:
            assert (ret, d, s.regs['d1'], a, s.regs['a1']) == (
                0x606bb596, 1, 20, 0x606bb5de, MANAGER+4)
            assert not self.timers
            result = 201
            item.update(operation='schedule timer; do not fire inline', timer=result,
                        delay_units=20, callback=hex(a), argument=hex(s.regs['a1']))
            self.timers.append(item.copy())
        elif pc == 0x60031be2:
            assert ret in (0x6094fdb9, 0x602e1417)
            s.write(a, struct.pack('<H', 64))
            item.update(operation='supplied current task ID', task=64)
        else:
            raise AssertionError(hex(pc))
        item['result'] = result
        self.events.append(item)
        s.return_from_model(result)

    def call(self, address, mask, frame, regs=None, stop=CALLER+7):
        r = invoke(self.s, address, mask, frame, regs,
                   stops=self.hooks | {stop})
        return self.run(r, stop)


def prepare(f, profile, sector, fill, application_state, *, dirty=True, fail_event=False):
    e = Editor(f, profile, sector, -3)
    s = e.s
    initialization = memory_initialize(e, fill)
    display = viewer_initialize(e)
    u32(s, CONTROLLER+4, VIEWER)
    models = Contracts(s, fill, fail_event)
    s.ram('native_settings_manager_destination', MANAGER, bytes([fill])*616, aliases=False)
    manager = models.call(0x6075eed9, 0xf0, 20, dict(a0=MANAGER))
    returned(s, manager)
    assert word(s, MANAGER) == 0x609b6558
    for offset in (24, *range(40, 552, 16), 560, 576):
        assert (word(s, MANAGER+offset+4), word(s, MANAGER+offset+8)) == (0, 20)
    registrations = []
    for callback in LISTENERS:
        r = models.call(0x6075f036, 0xb0, 16, dict(a0=MANAGER, a1=callback))
        returned(s, r)
        registrations.append(r)
    assert word(s, MANAGER+28) == 4
    assert struct.unpack('<4I', s.read(word(s, MANAGER+36), 16)) == LISTENERS
    # Only this member of the previously unmapped ShootArchitecture witness
    # is needed by the native general callback. Other fields still fault.
    if dirty:
        s.ram('shoot_settings_dirty_word', DIRTY, bytes([fill])*4, aliases=False)
    # State producer remains outside scope: only the getter's two fields exist.
    s.ram('supplied_application_state', MEDIATOR+4, struct.pack('<I', application_state), aliases=False)
    s.ram('mediator_mutex_witness', MEDIATOR+24,
          struct.pack('<2I', 0x609524c0, 0xdeadffff), aliases=False)
    u32(s, 0x61602c44, MEDIATOR)
    # Reviewed native framework static-object destinations, not automatic
    # fault filling. Native constructors run if the active branch uses them.
    for address, size in ((0x618ea770, 12), (0x618ea278, 72), (0x618ea73c, 24)):
        s.ram('framework_'+hex(address), address, bytes([fill])*size)
    u32(s, 0x618ea770, 0)
    # Native TRA history checks one of these eight diagnostic flags.
    s.ram('captured_debug_output_flags', 0x618d4c74, f.read(0x618d4c74, 8))
    before = full_viewer(e)
    return e, models, dict(memory=initialization, display=display,
                          manager=manager, registrations=registrations,
                          display_before=before)


def sequence_cache(e, c):
    """Isolated native predicate: only its declared cache and captured gate."""
    s, f = e.s, e.f
    s.ram('sequence_property_cache', SEQUENCE+162, b'\xa5'*24, aliases=False)
    s.ram('native_setting_read_mutex', 0x618d4888, bytes([c.fill])*8)
    mutex = c.call(0x606b4d2c, 0x30, 12, dict(a0=0x618d4888))
    returned(s, mutex)
    assert word(s, 0x618d4888) == 0x609524c0
    gate = f.read(0x61604864, 2)
    assert gate == bytes(2)
    # Feature-dependent side effects of60831074 are excluded by this explicit
    # captured gate. This is not proof of its value on every running camera.
    assert s.read(0x61604864, 2) == gate
    cold = c.call(0x608189b7, 0xa0, 12, dict(a0=SEQUENCE))
    returned(s, cold)
    assert s.regs['d0'] == 1
    warm = c.call(0x608189b7, 0xa0, 12, dict(a0=SEQUENCE))
    returned(s, warm)
    assert s.regs['d0'] == 0 and not c.held
    return dict(mutex_constructor=mutex, cold=cold, warm=warm, cache=s.read(SEQUENCE+162, 24).hex(),
                captured_feature_gate=gate.hex())


def edit_prefix(e):
    route, guards = e.input(UP), e.guards()
    r = drive(e.s, Exclusion())
    at(e.s, r, POST_CHANGE)
    return dict(route=route, guards=guards, refresh=r)


def completion(f, profile, sector, fill, fail_event=False):
    state = 0x10001 if fail_event else 0
    e, c, preparation = prepare(f, profile, sector, fill, state, fail_event=fail_event)
    s = e.s
    cache_before = sequence_cache(e, c)
    prefix = edit_prefix(e)
    r = c.run()
    returned(s, r)
    assert not c.held
    observed = [x['entry'] for x in r['observations']]
    assert all(observed.count(hex(cb)) == 1 for cb in LISTENERS+VIEW_CALLBACKS)
    assert observed.index('0x607600e2') < observed.index('0x60cd04b7') < observed.index('0x60c84901')
    assert current_record(f, s, e.key) == -2 and word(s, DIRTY) == 1
    wheel = s.read(0x619bd870, 96)
    assert wheel == s.read(VIEWER+36, 96) and list(wheel[1:3]) == [3, 3]
    before = bytes.fromhex(preparation['display_before']['wheel_hex'])
    assert [i for i, (a, b) in enumerate(zip(before, wheel)) if a != b] == [2]
    assert word(s, MANAGER+564) == 1
    assert word(s, word(s, MANAGER+572)) == e.key
    assert len(c.timers) == 1 and s.read(MANAGER+12, 2) == struct.pack('<H', 201)
    error = [x['d0'] for x in r['observations'] if x['entry'] == '0x6076081d']
    assert error == ([0xf0000016] if fail_event else [])
    assert ('0x606f11d6' in observed) is False
    # Separate predicate call AFTER the original edit has returned.
    unchanged = c.call(0x608189b7, 0xa0, 12, dict(a0=SEQUENCE))
    returned(s, unchanged)
    assert s.regs['d0'] == 0 and s.read(SEQUENCE+162, 24).hex() == cache_before['cache']
    # A stale picture-mode cache is a positive control, not a fake user mode.
    original = s.read(SEQUENCE+164, 2)
    s.write(SEQUENCE+164, struct.pack('<H', int.from_bytes(original, 'little') ^ 1))
    stale = c.call(0x608189b7, 0xa0, 12, dict(a0=SEQUENCE))
    returned(s, stale)
    assert s.regs['d0'] == 1 and s.read(SEQUENCE+164, 2) == original
    # Timer expiry is a separate, explicitly scheduled invocation. Stop at
    # the real work-queue submission boundary; do not replace its delivery.
    expiry = invoke(s, 0x606bb5de, 0, 0, dict(a0=MANAGER+4), stops=(0x6008593a,))
    at(s, expiry, 0x6008593a)
    assert (s.regs['a0'], s.regs['a1']) == (0x6075fecb, 0)
    assert s.read(MANAGER+12, 2) == bytes(2)
    # Test the submitted worker separately. Group lists remain empty; this
    # covers classification/list clearing, not real GUI subscriber delivery.
    deferred = c.call(0x6075fecb, 0, 0)
    returned(s, deferred)
    assert word(s, MANAGER+564) == 0 and not c.held
    groups = [x['group'] for x in deferred['observations']
              if x['entry'] == '0x60760519' and x['selected']]
    assert groups == [0]
    assert s.read(0x619bd870, 96) == wheel
    return dict(profile=profile, sector=sector, fill=hex(fill), supplied_state=hex(state),
                allocation_failure_control=fail_event, preparation=preparation,
                prefix=prefix, uninterrupted_edit_return=r, dirty_word=word(s, DIRTY),
                sequence_cache_before=cache_before, sequence_predicate_after_edit=unchanged,
                stale_sequence_cache_positive_control=stale,
                wheel_hex=wheel.hex(), timer_submission_boundary=compact(expiry),
                separately_invoked_deferred_worker=deferred, notification_groups=groups)


def active_request(f, fill):
    e, c, preparation = prepare(f, 1, 1, fill, 0x10001)
    s = e.s
    prefix = edit_prefix(e)
    result = c.run(stop=REQUEST)
    at(s, result, REQUEST)
    assert s.regs['mdr'] == 0x606f1a3f
    event = s.regs['a0']
    assert word(s, event) == 0x60967240 and s.read(event+4, 2) == b'\x4e\x40'
    wrapper = word(s, event+28)
    responder = word(s, 0x61602470)
    assert c.heap[event]['bytes'] == 32 and c.heap[wrapper]['bytes'] == 12
    assert c.heap[responder]['bytes'] == 180
    assert word(s, responder) == 0x609b4fd4
    assert (word(s, responder+128), word(s, responder+132)) == (0x404e, 0xf0000001)
    assert word(s, responder+120) == c.private_wait
    assert len(c.held) == 2 and c.private_wait in c.held
    assert word(s, MANAGER+564) == 0 and not c.timers
    assert all(x['entry'] != '0x60cd04b7' for x in result['observations'])
    assert s.read(0x619bd870, 96).hex() == preparation['display_before']['wheel_hex']
    return dict(fill=hex(fill), supplied_state='0x10001', preparation=preparation,
                prefix=prefix, request_submission_boundary=result,
                event=hex(event), event_hex=s.read(event, 32).hex(),
                wrapper=hex(wrapper), wrapper_hex=s.read(wrapper, 12).hex(),
                responder=hex(responder), responder_hex=s.read(responder, 180).hex(),
                held_semaphores=list(map(hex, sorted(c.held))),
                request_dispatched=False, response_supplied=False)


def strict_dirty_control(f):
    e, c, _ = prepare(f, 1, 1, 0xa5, 0, dirty=False)
    edit_prefix(e)
    r = c.run()
    assert r['status'] == 'memory_fault' and r['pc'] == '0x606dd6c3'
    assert r['fault']['address'] == DIRTY and r['fault']['access'] == 'write'
    return r


SPANS = {
    'sequence-check-wrapper': (0x607e11a2, 0x607e11b0),
    'sequence-parameter-cache': (0x608187ac, 0x608188fe),
    'sequence-change-predicate': (0x608189b7, 0x608189dd),
    'sequence-extra-cache': (0x6082dd29, 0x6082dd49),
    'sequence-feature-gated-effects': (0x60831074, 0x608310e1),
    'still-change-sequence': (0x608038b2, 0x60803a71),
    'post-edit-state-gate': (0x607607a1, 0x60760828),
    'receiver-creation': (0x606f1117, 0x606f11e8),
    'receiver-lazy-objects': (0x606f1362, 0x606f145e),
    'responder-construction': (0x606f183f, 0x606f18a7),
    'responder-state-machine': (0x6075da43, 0x6075dd11),
    'reply-wrapper': (0x606f2724, 0x606f287c),
    'parameter-receiver-registry': (0x606f14bd, 0x606f1598),
    'native-mutex-constructor': (0x6095074c, 0x60950793),
    'native-semaphore-constructor': (0x6094fe12, 0x6094fe4a),
    'native-flag-constructor': (0x6095039d, 0x609503d4),
    'native-queue-constructor': (0x6094ff0e, 0x6094ff5d),
    'native-main-framework-thread': (0x6095181e, 0x6095187a),
    'settings-manager': (0x6075eed9, 0x6075f09c),
    'notification-and-classification': (0x60760063, 0x6076062d),
    'timer-and-registered-setting-callback': (0x6075fecb, 0x6075ff13),
    'timer-wrapper': (0x606bb519, 0x606bb5f7),
    'general-listener-shoot': (0x606da12e, 0x606da142),
    'dirty-word-setter': (0x606dd6c3, 0x606dd6c9),
    'receiver-send-and-wait': (0x606f11e8, 0x606f1334),
    'reply-wait-and-state-dispatch': (0x606f19c2, 0x606f1ac0),
    'state-transition-factory-send': (0x6075d513, 0x6075d5ef),
    'state-factory-adapter': (0x60934a59, 0x60934b80),
    'still-handler-404e-branch': (0x60808c9e, 0x60808cff),
    'still-handler-specialization-404e-branch': (0x60929d14, 0x60929d72),
    'still-settings-request-action': (0x608042d1, 0x6080434f),
    'response-register': (0x60931c41, 0x60931c59),
    'response-complete': (0x60931e5f, 0x60931ecf),
    'response-unit-final': (0x6093212d, 0x609321ab),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    f = Fixture()
    report = dict(camera_used=False, firmware_modified=False, main_sha256=sha(f.image),
                  checkpoint_sha256=CHECKPOINT_SHA, cases=[], active_request_cases=[])
    for fill in (0, 0xa5):
        for profile, sector in ((1, 1), (2, 6), (3, 12)):
            report['cases'].append(completion(f, profile, sector, fill))
            print(f'COLOR{profile}, fill {fill:#x}: native edit return, four listeners, viewer and deferred worker passed', flush=True)
        report['active_request_cases'].append(active_request(f, fill))
        print(f'Active-state receiver, fill {fill:#x}: constructed natively; strict stop before state dispatch', flush=True)
    report['allocation_failure_control'] = completion(f, 1, 1, 0xa5, fail_event=True)
    report['unmapped_dirty_field_control'] = strict_dirty_control(f)
    report['limits'] = [
        'Selected editor fixture, not connected camera boot or physical input',
        'Application state supplied; no claim that state0 is normal COLOR editing',
        'Active event404e not delivered; request/reply and camera-state provenance remain open',
        'Four general listeners identified by direct-call scan, not proof of exhaustive runtime subscriptions',
        'Grouped observers empty; timer worker separately invoked after real submission boundary',
        'Sequence predicate tested separately with warmed cache and captured feature gate61604864=0',
        'Synthetic bounded heap/OS handles, task64, uncontended locks and deferred timer models',
        'Display parameter store has no drawing observers; no physical LCD, ISP, persistence or capture',
    ]
    sources = [Path(__file__), Path('tools/penf_color_refresh_probe.py'),
               Path('tools/penf_color_edit_probe.py'), Path('tools/penf_probe.py'),
               Path('tools/penf_boot_emulator.py'), Path('tools/penf_emulator.py'),
               Path('tools/penf_profile_context_probe.py'), Path('tools/penf_profile_followup_probe.py'),
               Path('tools/penf_profile_lifecycle_probe.py'), Path('tools/penf_recovery_isolation_probe.py')]
    report['source_sha256'] = {str(p): sha(p.read_bytes()) for p in sources}
    report['engine_sha256'] = sha(ENGINE.read_bytes())
    directory = args.out/'disassembly'
    directory.mkdir()
    for name, (start, end) in SPANS.items():
        (directory/(name+'.asm')).write_text(window(f.image, DEFAULT_IMAGE, DEFAULT_OBJDUMP, start, end))
    (args.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print('All notification contracts and negative controls passed.', flush=True)


if __name__ == '__main__':
    main()
