#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Audit stock OM-5/E-M1 III frame records and image-buffer pool lifecycles.

Executes constructor fragments, allocation to exhaustion, address resolution,
release and slot reuse. Image pixels/DRAM are not mapped. Pool controls start
zeroed and lock helpers are modeled as uncontended; no full boot, concurrent
capture, mode reconfiguration or extra physical memory is established.
Read-only original firmware inputs; no modified firmware output.
"""
import argparse
import json
from pathlib import Path
import struct
import tempfile

from oly_container import parse, sha256
from om5_burst_audit import PINS
from om5_rate_consumers_probe import SP, invoke, start_call
from om5_runtime_buffer_probe import CONFIG as RUNTIME, initialized_state, run_to
from penf_disasm import DEFAULT_OBJDUMP, window
from penf_emulator import BASE, ENGINE
from penf_probe import BUFFER, CALLER


CONFIG = {
    'om5': dict(object=0xa25ee060, registry=0x60575c70, pool_count=18,
                initialize=(0x6040cd83, 0x6040cde7),
                metadata_initialize=(0x6040d0c0, 0x6040d0e7),
                allocate=0x6040f78f, release=0x6040f869, address=0x6040dfd3,
                lock=0x6040f557, unlock=0x6040f578,
                records=0x620d0260, handles=32,
                records_initialize=(0x602bc43f, 0x602bc455), find=0x602bcd7b,
                address_bases=(0xb0000000, 0xc4000000), split=7,
                secondary_base=0xae713b40, metadata_base=0xae84bfc0),
    'em1iii': dict(object=0xa262dfc4, registry=0x60545cdc, pool_count=50,
                   initialize=(0x60409eb1, 0x60409f15),
                   metadata_initialize=(0x6040a233, 0x6040a25a),
                   allocate=0x6040c843, release=0x6040c91d, address=0x6040af6d,
                   lock=0x6040c60b, unlock=0x6040c62c,
                   records=0x6210f9d4, handles=64,
                   records_initialize=(0x602b7079, 0x602b708f), find=0x602b784a,
                   address_bases=(0xb0000000, 0x84000000), split=36,
                   secondary_base=0xae34e740, metadata_base=0xae693bc0),
}


def call(s, c, function, mask, frame, registers):
    start_call(s, function, mask, frame, registers)
    locks = []
    for _ in range(12):
        result = s.run([CALLER+7, c['lock'], c['unlock']], limit=30000)
        assert result['status'] == 'breakpoint', result
        pc = s.regs['pc']
        if pc == CALLER+7:
            assert [r['operation'] for r in locks] in ([], ['lock', 'unlock'])
            return dict(d0=s.regs['d0'], locks=locks)
        locks.append(dict(operation='lock' if pc == c['lock'] else 'unlock',
                          id=s.regs['d0']))
        s.return_from_model(0)
    raise AssertionError('Native call did not return')


def pools(data, model, c):
    s = initialized_state(data, RUNTIME[model])
    # Explicit zeroed control-state fixture, not a complete BSS/startup replay.
    # Exact stock constructors then write the pool parameters and method tables.
    s.ram('pool_controls', c['object']-12, bytes(0x4000))
    for start, stop in (c['initialize'], c['metadata_initialize']):
        s.regs = dict(pc=start, sp=SP, psw=0)
        run_to(s, stop)
    rows = []
    for kind, count, stride, label in ((0, c['pool_count'], 32798208, 'large_image'),
                                      (1, c['pool_count'], 53760, 'paired_auxiliary'),
                                      (21, c['handles'], 41984, 'per_frame_metadata')):
        key, obj = struct.unpack_from('<II', data, c['registry']-BASE+kind*8)
        assert key == kind*256
        vtable, flags, base, actual_stride, lock_id, free, id_base, capacity = struct.unpack(
            '<5I3H', s.read(obj, 26))
        assert (flags, actual_stride, free, id_base, capacity) == (0, stride, count, key, count)
        expected_base = c['address_bases'][0] if kind == 0 else c[
            'secondary_base' if kind == 1 else 'metadata_base']
        assert base == expected_base
        split = None
        if kind == 0:
            split = struct.unpack('<HHIH', s.read(obj+304, 10))
            assert split == (32, c['split'], c['address_bases'][1], count-c['split'])
        methods = struct.unpack('<14I', s.read(vtable, 56))
        allocated, lock_calls = [], []
        for index in range(count):
            s.write(BUFFER, b'\xa5'*8)
            result = call(s, c, c['allocate'], 0xf0, 40, dict(a0=obj, a1=BUFFER))
            assert result['d0'] == 0
            slot = struct.unpack('<H', s.read(BUFFER, 2))[0]
            assert slot == key+index+1
            remaining = struct.unpack('<H', s.read(obj+20, 2))[0]
            assert remaining == count-index-1
            address = call(s, c, c['address'], 0xf0, 44, dict(d0=slot))
            if kind == 0 and index >= c['split']:
                expected_address = c['address_bases'][1]+(index-c['split'])*stride
            else:
                expected_address = base+index*stride
            assert address['d0'] == expected_address
            allocated.append(dict(handle=hex(slot), address=hex(address['d0']), remaining=remaining))
            lock_calls.extend(result['locks'])
        before = s.read(obj, 316 if kind == 0 else 476)
        s.write(BUFFER, b'\xa5'*8)
        exhausted = call(s, c, c['allocate'], 0xf0, 40, dict(a0=obj, a1=BUFFER))
        assert exhausted['d0'] == 1 and s.read(BUFFER, 8) == b'\xa5'*8
        assert s.read(obj, len(before)) == before
        # Release a non-edge slot, then verify that the same handle/address recurs.
        released = call(s, c, c['release'], 0xf0, 36,
                        dict(d0=key+3, a0=obj, a1=BUFFER+4))
        assert released['d0'] == 0 and s.read(obj+20, 2) == b'\1\0'
        reused = call(s, c, c['allocate'], 0xf0, 40, dict(a0=obj, a1=BUFFER))
        assert reused['d0'] == 0 and s.read(BUFFER, 2) == struct.pack('<H', key+3)
        assert s.read(obj+20, 2) == b'\0\0'
        address = call(s, c, c['address'], 0xf0, 44, dict(d0=key+3))['d0']
        assert address == int(allocated[2]['address'], 16)
        rows.append(dict(label=label, type=hex(key), object=hex(obj), vtable=hex(vtable),
                         methods=[hex(x) for x in methods], configured_slots=count,
                         slot_stride_bytes=stride, initial_base=hex(base), lock_id=lock_id,
                         split_configuration=split, allocated=allocated,
                         exhaustion_return=exhausted['d0'], exhaustion_preserves_state=True,
                         released_and_reused_handle=hex(key+3), reused_address=hex(address),
                         allocation_lock_calls=lock_calls))
    return rows


def frame_records(data, model, c):
    s = initialized_state(data, RUNTIME[model])
    length = (c['handles']+1)*20
    s.ram('frame_records_and_guard', c['records'], b'\xa5'*(length+16))
    s.regs = dict(pc=c['records_initialize'][0], sp=SP, psw=0)
    run_to(s, c['records_initialize'][1])
    for index in range(c['handles']+1):
        assert s.read(c['records']+20*index, 20) == b'\0\0'+b'\xa5'*18
    cases = []
    for free_id in (1, c['handles'], None):
        for index in range(1, c['handles']+1):
            s.write(c['records']+index*20, struct.pack('<H', 0 if index == free_id else 4))
        result = invoke(s, c['find'], 0x80, 4, dict(d0=0))
        assert result['d0'] == (free_id if free_id else c['handles']+1)
        cases.append(dict(free_id=free_id, result=result))
    assert s.read(c['records']+length, 16) == b'\xa5'*16
    return dict(base=hex(c['records']), stride=20, valid_handles=c['handles'],
                reserved_index_zero=True, bytes_including_index_zero=length,
                next_address=hex(c['records']+length), cases=cases, guard_intact=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    pins = json.loads(PINS.read_text())
    dependencies = [Path(__file__), PINS, ENGINE, DEFAULT_OBJDUMP]+[
        Path('tools')/n for n in ('om5_runtime_buffer_probe.py', 'om5_rate_consumers_probe.py',
        'om5_burst_audit.py', 'oly_container.py', 'penf_disasm.py', 'penf_probe.py',
        'penf_boot_emulator.py', 'penf_emulator.py')]
    report = dict(scope=__doc__, hardware_tested=False,
                  dependency_hashes={str(p): sha256(p.read_bytes()) for p in dependencies}, models={})
    with tempfile.TemporaryDirectory(prefix='om5-image-pools-') as temporary:
        for model, c in CONFIG.items():
            encoded = Path(pins[model]['source']).read_bytes()
            assert sha256(encoded) == pins[model]['source_sha256']
            data = next(b.payload for b in parse(encoded) if b.kind == 0x100)
            assert sha256(data) == pins[model]['main_sha256']
            row = dict(source=pins[model], locations=c, pools=pools(data, model, c),
                       frame_records=frame_records(data, model, c), windows=[])
            image = Path(temporary)/f'{model}.bin'
            image.write_bytes(data)
            windows = dict(pool_initialization=c['initialize'],
                           metadata_initialization=c['metadata_initialize'],
                           record_initialization=c['records_initialize'],
                           record_search=(c['find'], c['find']+35),
                           allocation=(c['allocate'], c['release']),
                           release=(c['release'], c['release']+184),
                           address=(c['address'], c['address']+246))
            if model == 'om5':
                windows.update(frame_acquire=(0x602bc486, 0x602bc639),
                               pair_acquire=(0x602bce18, 0x602bce8d),
                               metadata_acquire=(0x602bcd9e, 0x602bcdde),
                               frame_release=(0x602bc639, 0x602bc6e5),
                               pair_release=(0x602bce8d, 0x602bcef8),
                               metadata_release=(0x602bcdde, 0x602bce18),
                               split_address_method=(0x60410917, 0x60410968),
                               pool_constructor=(0x60410326, 0x60410385),
                               general_pool_constructor=(0x6040f706, 0x6040f751),
                               lock_helpers=(0x6040f526, 0x6040f59c))
            for label, (start, stop) in windows.items():
                name = f'{model}-{label}.asm'
                (args.out/name).write_text(window(data, image, DEFAULT_OBJDUMP, start, stop))
                row['windows'].append(dict(file=name, start=hex(start), stop=hex(stop),
                                          sha256=sha256(data[start-BASE:stop-BASE])))
            report['models'][model] = row
            print(f'{model}: three stock pools exhausted/released/reused; frame record limits passed', flush=True)
    (args.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print('No pixel memory mapped, firmware changed or physical capture performed.')


if __name__ == '__main__':
    main()
