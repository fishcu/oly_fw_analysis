#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Read-only OM-5/E-M1 III rate initialization and Pro Capture queue audit.

Runs stock startup fragments, full rate qualification, queue construction and
overflow handling. Storage delivery, heap allocation/free and diagnostic output
are explicit contracts; sensor operation and actual image buffers are unmodeled.
No modified firmware is produced. Run from the workspace root with fresh --out.
"""
import argparse
import json
from pathlib import Path
import struct
import tempfile

from oly_container import parse, sha256
from om5_burst_audit import PINS
from om5_rate_consumers_probe import CONFIG as SETTINGS, SP, invoke, start_call, state
from penf_disasm import DEFAULT_OBJDUMP, window
from penf_emulator import BASE, ENGINE, Region
from penf_probe import BUFFER, CALLER


CONFIG = {
    'om5': dict(source=0x60257800, end=0x602883f4, destination=0x61e32ac0,
                variables=0x62023fc0, flash=0x409b6800, read=0x60022451,
                helpers=0x616a3000, helper_flash=0x41e02000,
                pointers=0x61e34374, qualify=0x60160c01,
                alloc=0x60136d0a, free=0x60136f6f,
                queue_start=0x602b816d, queue_stop=0x602b818f,
                queue_global=0x620cfd48, capacity=32, push=0x60237c84,
                diagnostic=0x60062d71, queue_api=0x60237c42,
                setup=0x602b8c63, setup_stops=(0x602b8cf2, 0x602b8cb0),
                pre_limit=0x620cfe02, state_base=0x620cfde0,
                metadata=0x60169905, clamp=0x6014918b, calculate=0x601491b8),
    'em1iii': dict(source=0x60252800, end=0x602859a0, destination=0x61e72ac0,
                   variables=0x6205f6c0, flash=0x40a31800, read=0x60022454,
                   helpers=0x61649000, helper_flash=0x41e28000,
                   pointers=0x61e744a0, qualify=0x60162074,
                   alloc=0x6013813e, free=0x601383a3,
                   queue_start=0x602b2f00, queue_stop=0x602b2f22,
                   queue_global=0x6210f23c, capacity=64, push=0x60238fa0,
                   diagnostic=0x60064abf, queue_api=0x60238f5e),
}


def run_to(s, stop, limit=200000):
    result = s.run([stop], limit=limit)
    assert result['status'] == 'breakpoint' and s.regs['pc'] == stop, result
    return result['completed']


def startup(data, c, payload_address):
    """Execute argument setup and the CPU copy, stopping at storage calls."""
    s = state(data)
    s.ram('startup_variables', c['variables'], b'\xa5'*20)
    s.regs = dict(pc=0x600211ab, sp=SP, psw=0)
    run_to(s, 0x600211e7)
    assert struct.unpack('<I', s.read(c['variables']+4, 4))[0] == c['end']
    s.regs = dict(pc=0x600211fe, sp=SP, psw=0)
    run_to(s, c['read'])
    args = {r: s.regs[r] for r in ('d0', 'a0', 'a1')}
    assert args == dict(d0=c['end']-c['source'], a0=c['flash'],
                        a1=c['destination']+0x40000000)
    assert c['flash']-payload_address == c['source']-BASE
    # Model successful logical-storage delivery of exact stock initialized data.
    initializer = data[c['source']-BASE:c['end']-BASE]
    s.ram('stock_initialized_data', c['destination'], initializer)
    pointers = list(struct.unpack('<30I', s.read(c['pointers'], 120)))
    assert pointers[-2:] == pointers[24:26] and all(pointers[-2:])

    s.regs = dict(pc=0x60021272, sp=SP, psw=0)
    run_to(s, c['read'])
    assert (s.regs['d0'], s.regs['a0'], s.regs['a1']) == (
        6144, c['helper_flash'], c['helpers']+0x40000000)
    assert c['helper_flash']-payload_address == c['helpers']-BASE
    library = data[c['helpers']-BASE:c['helpers']-BASE+6144]
    s.ram('delivered_library', c['helpers'], library)
    s.ram('internal_library_destination', 0x47000800, b'\xa5'*6144, aliases=False)
    s.regs = dict(pc=0x60021297, sp=SP, psw=0)
    copy_steps = run_to(s, 0x600212af)
    assert s.read(0x47000800, 6144) == library
    return dict(storage_arguments=args, initializer_sha256=sha256(initializer),
                pointer_source=hex(c['source']+c['pointers']-c['destination']),
                pointers=[hex(p) for p in pointers],
                helper_sha256=sha256(library), native_copy_instructions=copy_steps,
                contract='Exact stock storage delivery modeled; storage driver not executed.')


def initialized_state(data, c):
    s = state(data)
    s.ram('stock_initialized_data', c['destination'], data[c['source']-BASE:c['end']-BASE])
    s.regions.append(Region('stock_internal_library', 0x47000800,
                            data[c['helpers']-BASE:c['helpers']-BASE+6144], 'rx'))
    return s


def qualification(data, c):
    cases = []
    for flag in (0, 1):
        for parameter, expected in ((0, 0), (1024, 15), (1280, 30),
                                    (1536, 60), (2048, 60), (2560, 60)):
            s = initialized_state(data, c)
            start_call(s, c['qualify'], 0xf0, 40, dict(d0=60, d1=parameter, a0=flag))
            allocations, freed = [], []
            for _ in range(10):
                result = s.run([CALLER+7, c['alloc'], c['free']], limit=20000)
                assert result['status'] == 'breakpoint', result
                pc = s.regs['pc']
                if pc == CALLER+7:
                    break
                if pc == c['alloc']:
                    assert not freed, 'Allocation after free invalidates the preserved-bytes contract'
                    address, size = 0x19000000+len(allocations)*4096, s.regs['d0']
                    assert 0 < size < 4096
                    allocations.append(dict(address=address, size=size))
                    s.ram(f'heap_{address:x}', address, b'\xa5'*size, aliases=False)
                    s.return_from_model(0)
                    s.regs['a0'] = address
                else:
                    freed.append(s.regs['a0'])
                    # Explicitly preserve freed bytes: native code reads a flag
                    # afterwards. No allocation occurs after the first free here.
                    s.return_from_model(0)
            else:
                raise AssertionError('Qualification did not return')
            assert [a['size'] for a in allocations] == [208, 92, 192]
            assert sorted(freed) == [a['address'] for a in allocations]
            want = min(expected, 30) if flag else expected
            assert s.regs['d0'] == want
            cases.append(dict(flag=flag, parameter=parameter, requested_fps=60,
                              returned_fps=want, instructions=s.steps,
                              allocations=allocations, frees=freed))
    return cases


def queue(data, c):
    s = initialized_state(data, c)
    base, capacity = c['queue_global'], c['capacity']
    backing, guard = base+24, base+24+capacity*4
    s.ram('queue_and_guard', base, b'\xa5'*(24+capacity*4+16))
    s.regs = dict(pc=c['queue_start'], sp=SP, psw=0)
    init_steps = run_to(s, c['queue_stop'])
    control = struct.unpack('<IHHIHHH', s.read(base+4, 18))
    assert control == (190, capacity, 4, backing, 0, 0, 0)
    assert s.read(base, 4) == struct.pack('<I', base+4)
    # The next stock instruction writes real state immediately after backing.
    run_to(s, c['queue_stop']+8)
    assert s.read(guard, 4) == struct.pack('<I', 7)
    s.write(guard, b'\xa5'*16)
    instructions = 0
    for i in range(capacity):
        result = invoke(s, c['push'], 0, 8, dict(a0=base+4, d0=0x1000+i))
        assert result['d0'] == 4
        instructions += result['instructions']
    expected = struct.pack('<'+'I'*capacity, *range(0x1000, 0x1000+capacity))
    assert s.read(backing, capacity*4) == expected
    assert struct.unpack('<HHH', s.read(base+16, 6)) == (capacity, 0, 0)
    before = s.read(base, guard-base+16)
    start_call(s, c['push'], 0, 8, dict(a0=base+4, d0=0xdeadbeef))
    run_to(s, c['diagnostic'])
    assert s.read(base, guard-base+16) == before
    s.return_from_model(0)  # Only suppress diagnostic output on the full branch.
    run_to(s, CALLER+7)
    assert s.regs['d0'] == 0 and s.read(base, guard-base+16) == before
    assert s.read(guard, 16) == b'\xa5'*16
    return dict(capacity=capacity, element_bytes=4, backing=hex(backing),
                following_state=hex(guard), initialization_instructions=init_steps,
                fill_instructions=instructions, inserted_values=list(range(0x1000, 0x1000+capacity)),
                overflow_return=0, unchanged_on_overflow=True, guard_intact=True,
                caveat='Frame-handle queue only, not physical image-buffer capacity.')


def pre_parameters(data, model):
    """Join named public settings to typed IDs; exercise OM-5 pre-limit loading."""
    c = SETTINGS[model]
    s = state(data)
    s.register(0x8050, 'r', 0)  # Explicit CPU0 translation contract.
    s.ram('descriptor_bank', c['bank'], bytes(2))
    s.ram('cache_enabled', c['cache_flag'], b'\1')
    s.ram('empty_public_pointer_cache', c['cache'], bytes(1893*4))
    mappings = []
    for i, key in enumerate((0x5421, 0x5432, 0x5441, 0x5452, 0x5462, 0x5472)):
        public = 1152+i-(model == 'em1iii')
        assert struct.unpack_from('<HH', data, c['mapping']-BASE+public*4) == (key, 0)
        s.ram(f'descriptor_{key:x}', c['bank']+4+(key >> 4)*8,
              struct.pack('<HHI', key, 1, BUFFER+i*8))
        result = invoke(s, c['public_mapper'], 0xf0, 28, dict(d0=public, a0=BUFFER+512))
        assert result['d0'] == key
        assert s.read(BUFFER+512, 4) == struct.pack('<I', BUFFER+i*8)
        mappings.append(dict(public_id=public, typed_id=hex(key), value_pointer=hex(BUFFER+i*8)))
    cases = []
    if model == 'om5':
        c = CONFIG[model]
        s.ram('capture_state', c['state_base'], b'\xa5'*40)
        for mode in (1, 2):
            for value in (14, 16, 20, 35):
                s.write(BUFFER+32, struct.pack('<H', value if mode == 1 else 7))
                s.write(BUFFER+40, struct.pack('<H', value if mode == 2 else 9))
                start_call(s, c['setup'], 0x80, 8, dict(d0=mode, a0=BUFFER+128))
                steps = run_to(s, c['setup_stops'][mode-1])
                result = struct.unpack('<H', s.read(c['pre_limit'], 2))[0]
                assert result == value
                cases.append(dict(mode=mode, fixture_value=value, stored_pre_limit=result,
                                  instructions=steps))
    return dict(mappings=mappings, load_cases=cases,
                caveat='Synthetic parameter storage; no menu setter, persistence or physical pre-buffer test.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    pins = json.loads(PINS.read_text())
    dependencies = [Path(__file__), PINS, DEFAULT_OBJDUMP, ENGINE]+[
        Path('tools')/name for name in ('om5_rate_consumers_probe.py', 'om5_burst_audit.py',
        'oly_container.py', 'penf_disasm.py', 'penf_probe.py', 'penf_boot_emulator.py', 'penf_emulator.py')]
    report = dict(scope=__doc__, hardware_tested=False,
                  dependency_hashes={str(p): sha256(p.read_bytes()) for p in dependencies},
                  heap_contract='Successful allocation; free preserves bytes until return. '
                  'The native routine reads a freed flag, so allocator behavior is an explicit assumption.',
                  models={})
    table_pairs = {}
    with tempfile.TemporaryDirectory(prefix='om5-runtime-') as temporary:
        for model, c in CONFIG.items():
            pin = pins[model]
            encoded = Path(pin['source']).read_bytes()
            assert sha256(encoded) == pin['source_sha256']
            block = next(b for b in parse(encoded) if b.kind == 0x100)
            data = block.payload
            assert sha256(data) == pin['main_sha256']
            record = dict(source=pin, locations=c, startup=startup(data, c, block.address+32),
                          qualification=qualification(data, c), queue=queue(data, c),
                          parameters=pre_parameters(data, model))
            ptrs = [int(p, 16) for p in record['startup']['pointers'][-2:]]
            # 377 eight-byte rows: signed parameter range [-1536,4480], step16.
            if model == 'om5':
                s = state(data)
                meta = invoke(s, c['metadata'], 0x80, 16, dict(d0=14))['a0']
                assert struct.unpack('<hh', s.read(meta+64, 4)) == (4480, -1536)
            table_pairs[model] = [data[p-BASE:p-BASE+377*8] for p in ptrs]
            record['mode14_tables'] = [dict(address=hex(p), bytes=377*8, sha256=sha256(t))
                                      for p, t in zip(ptrs, table_pairs[model])]
            image = Path(temporary)/f'{model}.main.bin'
            image.write_bytes(data)
            windows = dict(startup=(0x600211ab, 0x600212af),
                           qualification=(c['qualify'], c['qualify']+343),
                           queue_initialization=(c['queue_start'], c['queue_stop']+8),
                           queue_api=(c['queue_api'], c['queue_api']+182))
            if model == 'om5':
                windows.update(pre_limit_load=(c['setup'], 0x602b8d04),
                               threshold=(c['clamp'], 0x60149269),
                               queue_owner_handler=(0x602b86d9, 0x602b8704))
            record['windows'] = []
            for label, (start, end) in windows.items():
                name = f'{model}-{label}.asm'
                (args.out/name).write_text(window(data, image, DEFAULT_OBJDUMP, start, end))
                record['windows'].append(dict(file=name, start=hex(start), end=hex(end),
                                              sha256=sha256(data[start-BASE:end-BASE])))
            report['models'][model] = record
            print(f'{model}: startup, 12 full qualification cases, {c["capacity"]}-entry queue passed', flush=True)
    assert table_pairs['om5'] == table_pairs['em1iii']
    assert report['models']['om5']['qualification'] == report['models']['em1iii']['qualification']
    report['mode14_tables_identical'] = True
    report['qualification_results_identical'] = True
    (args.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print('Verified 24 full qualification cases, two stock queues, 12 parameter mappings and 8 pre-limit loads.')


if __name__ == '__main__':
    main()
