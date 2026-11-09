#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native compact COLOR refresh, five-slot selection and state exclusion.

Explicit initial ring state and captured runtime controls; native pointer
registration, refresh and copying. Kernel/hardware exclusion is modeled only
at reviewed call sites. Selection stops at the take-info builder. No physical
frame completion, scheduler replay, firmware patch or new storage claim.
"""
import argparse
import json
from pathlib import Path
import struct
import sys

from penf_image_ownership_probe import (
    Harness, Fixture, invoke, returned, resume, at, BASE, CALLER,
    CHECKPOINT_SHA, DEFAULT_IMAGE, DEFAULT_OBJDUMP, ENGINE, sha, window,
)

RING, INDICES, SNAPSHOT = 0xa1c6cab8, 0xa1c6ca64, 0x61bc9d6c
TABLES = ((0x606465e8, 0x61bca018, 30), (0x606466d8, 0x61bca090, 2),
          (0x606466e8, 0x61bca098, 4), (0x60646708, 0x61bca0a8, 3),
          (0x60646720, 0x61bca0b4, 29), (0x60646808, 0x61bca128, 3))


def half(s, address):
    return int.from_bytes(s.read(address, 2), 'little')


def prepare(h):
    s, f = h.s, h.f
    tables = []
    for table, pointers, count in TABLES:
        records = []
        for i in range(count):
            key, kind, _, offset = struct.unpack_from('<HBBI', f.image, table-BASE+i*8)
            actual, n, ptr = struct.unpack('<HHI', f.read(0x61c281e4+(key >> 4)*8, 8))
            size = n*(key & 7)
            assert actual == key and (key & 7) in (1, 2, 4)
            try:
                s.read(ptr, size)
            except ValueError:
                s.ram('compact_declared_'+hex(key), ptr, f.read(ptr, size))
            records.append(dict(key=hex(key), kind=kind, offset=offset, address=hex(ptr), bytes=size))
        s.ram('compact_pointer_array_'+hex(pointers), pointers, bytes([h.fill])*count*4)
        r = invoke(s, 0x60568e0f, 0xf0, 24, dict(d0=count, a0=table, a1=pointers))
        returned(s, r)
        tables.append(dict(table=hex(table), registration=r, records=records))
    # These are supplied ring states, not a claim to replay ring startup.
    s.ram('explicit_compact_ring', RING, bytes(632*5))
    s.ram('explicit_compact_indices', INDICES, bytes(10))
    s.ram('native_compact_snapshot', SNAPSHOT, bytes([h.fill])*632)
    for ptr, size in ((0x61bca1c8, 4), (0x61c6fff4, 4), (0x61c70014, 3)):
        data = f.read(ptr, size)
        assert data == bytes(size)
        s.ram('captured_compact_control_'+hex(ptr), ptr, data)
    # 60557494's derived control store through 60567727: native code writes
    # this byte; the test does not suppress this side effect of full refresh.
    s.ram('native_compact_derived_control', 0xa1c6fc20, bytes([h.fill]))
    s.ram('compact_diagnostic_mask_off', 0xa1c6c7e8, bytes(4))
    request = bytearray(306); request[240] = 1
    s.ram('explicit_selection_request', 0x29000000, request, aliases=False)
    return tables


class StateExclusion:
    hooks = {0x60039214, 0x600316cb, 0x600317b3, 0x60086c0b,
             0x60086c54, 0x60070bc0, 0x60070cb1, 0x60557305, 0x6055726d}

    def __init__(self, s):
        self.s, self.phase, self.events = s, 0, []

    def set(self, index, value):
        result = self.call(0x6055619b, 0xc0, 12, dict(d0=index, d1=value),
                           [(0x60557305, index, value)])
        assert half(self.s, RING+632*index+612) == value
        if value == 2:
            assert half(self.s, INDICES+4) == index
        return dict(index=index, value=value, **result)

    def call(self, target, mask, frame, regs, stores):
        s = self.s; events = []
        remaining = list(stores)
        r = invoke(s, target, mask, frame, regs, stops=self.hooks)
        for _ in range(40):
            pc = s.regs['pc']
            assert r['status'] == 'breakpoint', r
            if pc == CALLER+7:
                returned(s, r); assert self.phase == 0 and not remaining
                return dict(execution=r, models=events)
            ret, arg, result = s.regs['mdr'], s.regs['d0'], 0
            if pc in (0x60557305, 0x6055726d):
                assert self.phase == 3 and remaining
                assert (pc, arg, s.regs['d1']) == remaining.pop(0)
                events.append(dict(operation='native state/handle store inside exclusion',
                                   callback=hex(pc), index=arg, value=s.regs['d1']))
                step = s.run(self.hooks-{pc}, limit=1)
                assert step['status'] == 'instruction_limit'
            else:
                expected = {
                    0x60039214: (0x605562af, 0, 0, 0, 'ordinary task context'),
                    0x600316cb: (0x605562bd, 0, 1, 0, 'dispatch disable'),
                    0x60086c0b: (0x605562d4, 1, 2, 0x2400, 'interrupt state save'),
                    0x60070bc0: (0x605562e6, 2, 3, 18, 'hardware lock acquire'),
                    0x60070cb1: (0x605562f7, 3, 4, 0, 'hardware lock release'),
                    0x60086c54: (0x60556300, 4, 5, 0, 'interrupt state restore'),
                    0x600317b3: (0x6055630d, 5, 0, 0, 'dispatch enable'),
                }
                caller, phase, next_phase, result, name = expected[pc]
                assert (ret, self.phase) == (caller, phase)
                if pc == 0x60086c0b: assert arg == 2
                if pc == 0x60070bc0: assert (arg, s.regs['d1']) == (0x121a0012, 255)
                if pc == 0x60070cb1: assert arg == 18
                if pc == 0x60086c54: assert arg == 0x2400
                self.phase = next_phase
                events.append(dict(operation=name, entry=hex(pc), caller_return=hex(ret), result=result))
                s.return_from_model(result)
            r = resume(s, self.hooks|{CALLER+7})
        raise AssertionError('unexpected repeated boundary')


def refresh(h):
    s = h.s
    r = invoke(s, 0x60557319, 0x30, 16); returned(s, r)
    index = half(s, INDICES+4)
    assert struct.unpack('<12h', s.read(RING+632*index+382, 24)) == h.values()
    assert s.read(0xa1c6fc20, 1) == b'\0'
    return r


def select(s, expected=None, limit=15000000):
    r = invoke(s, 0x60554c7c, 0xf0, 40, dict(a0=0x29000000, a1=0),
               stops=(0x60557bcf,), limit=limit)
    if expected is None:
        assert r['status'] == 'instruction_limit', r
        assert 0x60554cff <= s.regs['pc'] <= 0x60554d20
        return dict(execution=r, all_busy_does_not_reach_builder=True)
    at(s, r, 0x60557bcf)
    assert half(s, INDICES+2) == expected
    assert half(s, s.regs['a1']+4) == expected
    return dict(execution=r, selected=expected, stop='before take-info builder; no claimed submission')


def lifetime(f, profile, fill):
    h = Harness(f, profile, fill); s = h.s
    h.refresh(profile); tables = prepare(h); exclusion = StateExclusion(s)
    first_state = exclusion.set(0, 2)
    first_refresh = refresh(h); before = h.values()
    first = s.read(RING, 632)
    snapshot = invoke(s, 0x605553bf, 0, 0); returned(s, snapshot)
    assert s.read(SNAPSHOT, 632) == first
    pin = invoke(s, 0x605561d5, 0, 0, dict(d0=0)); returned(s, pin)
    assert s.read(INDICES, 1) == b'\x01' and half(s, INDICES+6) == 0
    edit = h.edit(910, 53+(profile % 3+1)); after = h.values()
    selection = select(s, 1)
    queued = exclusion.set(1, 1)
    assert half(s, INDICES+4) == 0  # state1 does not switch the current index
    second_state = exclusion.set(1, 2)
    second_refresh = refresh(h)
    assert s.read(RING, 632) == first and s.read(SNAPSHOT, 632) == first
    assert before != after
    # Release through the native state setter. The caller deciding when it
    # is safe to release is still a host contract in this bounded test.
    release = exclusion.set(0, 0)
    unpin = invoke(s, 0x605561b9, 0, 0, dict(d0=0)); returned(s, unpin)
    assert s.read(INDICES, 1) == b'\0'
    # Supply preceding index4 to exercise native wrap-around and reuse0.
    s.write(INDICES+2, struct.pack('<H', 4))
    reuse = select(s, 0)
    reuse_state = exclusion.set(0, 2)
    reuse_refresh = refresh(h)
    assert struct.unpack('<12h', s.read(RING+382, 24)) == after
    assert s.read(SNAPSHOT, 632) == first
    return dict(kind='compact_lifetime', profile=profile, fill=hex(fill), registration=tables,
                old_values=before, new_values=after, state_operations=[first_state, queued, second_state, release, reuse_state],
                full_refreshes=[first_refresh, second_refresh, reuse_refresh], selections=[selection, reuse],
                snapshot_copy=snapshot, pin=pin, unpin=unpin, profile_switch=edit,
                old_slot_survives_new_refresh=True, saved_copy_survives_ring_reuse=True,
                snapshot_sha256=sha(first), explicit_wrap_fixture_previous_index=4)


def controls(f, fill):
    h = Harness(f, 1, fill); s = h.s; h.refresh(1); prepare(h)
    exclusion = StateExclusion(s)
    for i in range(5): exclusion.set(i, 1)
    busy = select(s, None, limit=2000)
    exclusion.set(3, 0)
    skips = select(s, 3)
    # Pinning is advisory here: inconsistent state0 + pinned/current index
    # only logs !search_frame and still reaches the builder with that slot.
    exclusion.set(0, 2)
    returned(s, invoke(s, 0x605561d5, 0, 0, dict(d0=0)))
    exclusion.set(0, 0)
    s.write(INDICES+2, struct.pack('<H', 4))
    pinned = select(s, 0)
    # Native release notification searches backwards from a slot hint for
    # the matching type0700 handle, then clears its handle AND state. The
    # upstream resource-release result remains a separate static boundary.
    for i in range(5):
        exclusion.set(i, 1)
        s.write(RING+632*i+24, struct.pack('<H', 0x701+i))
    before = s.read(RING, 632*5)
    matched = exclusion.call(0x60556899, 0xf0, 32, dict(d0=4, d1=0x703, a0=0x700),
                             [(0x6055726d, 2, 0), (0x60557305, 2, 0)])
    expected = bytearray(before)
    expected[632*2+24:632*2+26] = bytes(2)
    expected[632*2+612:632*2+614] = bytes(2)
    assert s.read(RING, 632*5) == expected
    unmatched = exclusion.call(0x60556899, 0xf0, 32, dict(d0=4, d1=0x799, a0=0x700), [])
    assert s.read(RING, 632*5) == expected
    return dict(kind='compact_selection_controls', fill=hex(fill), all_busy=busy,
                skips_states_1_and_2=skips, inconsistent_pin_does_not_reserve=pinned,
                matching_handle_release=matched, unmatched_handle_no_change=unmatched,
                limitation='Supplied states; no claim that camera creates the inconsistent pinned scenario.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True); p.add_argument('--quick', action='store_true')
    args = p.parse_args(); args.out.mkdir(parents=True, exist_ok=False)
    f = Fixture(); cases = []
    for fill in ((0xa5,) if args.quick else (0, 0xa5)):
        for profile in ((1,) if args.quick else (1, 2, 3)):
            cases.append(lifetime(f, profile, fill))
            print(f'COLOR{profile}, fill {fill:#x}: compact full refresh, ring and snapshot passed', flush=True)
        cases.append(controls(f, fill))
        print(f'Fill {fill:#x}: busy-loop and advisory-pin controls passed', flush=True)
    spans = {
        'selector': (0x60554c7c, 0x60554d80), 'copy-and-accessors': (0x605553bf, 0x60555448),
        'state-and-pins': (0x60556177, 0x6055620b), 'state-exclusion': (0x60556293, 0x6055631a),
        'state-store-and-full-refresh': (0x60557305, 0x60557378),
        'capture-event-refresh': (0x60575a18, 0x60575a99),
        'start-state-producer': (0x60558490, 0x60558500),
        'release-handle-search': (0x60556899, 0x605569a1),
        'release-handle-and-state-stores': (0x6055726d, 0x60557319),
        'release-caller-result-gate': (0x60554f30, 0x60554f7c),
        'resource-release-wrapper': (0x6056bfcf, 0x6056c08b),
        'pool-release-dispatch': (0x605489a5, 0x60548a92),
        'pool-release-inner': (0x6054a097, 0x6054a14f),
        'pool0700-reference-decrement': (0x6054a4b0, 0x6054a4e1),
        'event-worker': (0x60574c5a, 0x60574d42),
        'full-refresh-helpers': (0x605573f0, 0x6055761d),
        'derived-control-store': (0x60567727, 0x60567730),
        'dispatch-disable': (0x600316cb, 0x6003172b), 'dispatch-enable': (0x600317b3, 0x60031822),
        'hardware-lock': (0x60070bc0, 0x60070cda),
    }
    folder = args.out/'disassembly'; folder.mkdir()
    for name, (lo, hi) in spans.items():
        (folder/(name+'.asm')).write_text(window(f.image, DEFAULT_IMAGE, DEFAULT_OBJDUMP, lo, hi))
    root = Path.cwd(); sources = {Path(__file__).resolve()}
    for module in list(sys.modules.values()):
        file = getattr(module, '__file__', None)
        if file and Path(file).resolve().is_relative_to(root/'tools'):
            sources.add(Path(file).resolve())
    report = dict(main_sha256=sha(f.image), checkpoint_sha256=CHECKPOINT_SHA,
        engine_sha256=sha(ENGINE.read_bytes()),
        source_sha256={str(p.relative_to(root)): sha(p.read_bytes()) for p in sorted(sources)},
        spans={k: list(map(hex, v)) for k, v in spans.items()}, cases=cases,
        limits=[
            'Explicit initial zero ring/indices; pointer tables initialized natively, exact captured zero runtime controls.',
            'Complete 60557319 refresh and complete632-byte snapshot copy, not a physical frame or ISP completion.',
            'Selection runs from function entry and stops before60557bcf take-info builder; pending/active states are exercised by separate native setter calls.',
            'Full type0700 release-notification search clears only a matching supplied handle. Resource release and remaining-reference result before that notification are statically traced, not executed here.',
            'Only reviewed successful, uncontended task/interrupt/hardware exclusion is modeled; not a scheduler or multicore proof.',
            'The protected callback writes state+612. Current-index publication and full COLOR refresh occur after exclusion is released.',
            'Pin getters/flags do not enforce reservation independently of state1/2; inconsistent-state control is not a demonstrated camera bug.',
            'Snapshot at61bc9d6c is a reusable global copy, not an indefinitely owned per-image allocation; actual refresh/consumer timing remains open.',
            'No new H/L transport storage, firmware changes or recovery claim.',
        ])
    (args.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f'{len(cases)} compact ownership cases passed.', flush=True)


if __name__ == '__main__':
    main()
