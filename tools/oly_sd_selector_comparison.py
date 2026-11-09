#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Offline E-M5 startup-selector comparison and PEN-F thread-factory probes.

Executes bounded stock functions, not a continuous camera boot. Hardware input
snapshots, two settings reads, allocator/current-task APIs and diagnostic output
are explicit models. Task activation is trapped. No update image is generated.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

from penf_emulator import Region, ROOT, ENGINE, firmware
from penf_probe import ProbeState, CALLER
from penf_input_recovery_probe import initialize_pointers
from penf_preset_startup_audit import disassemble
from penf_disasm import DEFAULT_IMAGE, DEFAULT_OBJDUMP
from penf_sd_activation_audit import transfer_candidates


EM5 = ROOT / 'analysis/preset_startup_final/em5_1500.main.bin'
EM5_BASE = 0x7e421020
EM5_HASH = '10e69c8de7028ac48de7481dae61d92aa7a0b926439f24b934143dcc0383f657'
EM5II = ROOT / 'analysis/historical_hacks/em5ii4100/stock-main.bin'
EM5II_HASH = 'ecd9603c4a264a358d91ef110a05f9236055e6369399f7c7de5985b21a2fd96a'
PENF_BASE = 0x60021020
EM5_WINDOWS = {
    'initial_task': (0x7e441eb2, 0x7e441f9e),
    'initial_task_second_stage': (0x7e446b94, 0x7e446cb7),
    'application_startup': (0x7e5e5538, 0x7e5e628c),
    'ok_guard_update': (0x7e5e6c94, 0x7e5e6cb5),
    'key_state': (0x7e5ebb4b, 0x7e5ebc20),
    'key_lookup_and_bit_test': (0x7e5ed26e, 0x7e5ed38d),
    'key_setting_overrides': (0x7e5ec75b, 0x7e5ec7a2),
    'key_argument_hook': (0x7e5ee1d6, 0x7e5ee1d9),
    'wake_reason_getter': (0x7e454ad3, 0x7e454adc),
    'wake_reason_mapping': (0x7e5ed3ca, 0x7e5ed3d7),
    'controller_mode_getter': (0x7e454f65, 0x7e454f6e),
    'sd_initialization': (0x7e622cb9, 0x7e622d3d),
    'sd_platform_helpers': (0x7e62400b, 0x7e624099),
    'normal_branch_stub': (0x7e622d94, 0x7e622d98),
    'debug_ok_command': (0x7e74a599, 0x7e74a5d7),
    'fast_start_worker': (0x7e5e3771, 0x7e5e38b2),
    'fast_start_signal': (0x7e5e38e2, 0x7e5e38f4),
    'fast_start_normal_handler': (0x7e5e39ab, 0x7e5e39d3),
    'fast_start_skip_handler': (0x7e5e3b00, 0x7e5e3b0b),
}
PENF_WINDOWS = {
    'factory_getter': (0x6094fda1, 0x6094fdad),
    'current_task_query': (0x6094fdad, 0x6094fdca),
    'existing_thread_factory': (0x60950973, 0x609509a3),
    'existing_thread_constructor': (0x60950599, 0x609505b0),
    'thread_start_method': (0x60950706, 0x6095072b),
    'current_thread_factory_caller': (0x60951d9b, 0x60951e25),
    'sd_precheck_stub': (0x60b1ce0c, 0x60b1ce10),
    'sd_dispose_stub': (0x60b1d00f, 0x60b1d012),
    'fast_start_dispatcher': (0x601a4e2f, 0x601a50b7),
    'fast_start_signal': (0x601a50e7, 0x601a50f9),
    'fast_start_normal_handler': (0x601a5347, 0x601a5365),
}
EM5II_WINDOWS = {
    'sd_client': (0x60b5e53d, 0x60b5e78f),
    'sd_precheck_stub': (0x60b5e78f, 0x60b5e793),
    'sd_dispose_stub': (0x60b5e992, 0x60b5e995),
    'no_file_fallback': (0x601d50b2, 0x601d50f6),
    'normal_startup_stub_calls': (0x60198562, 0x60198570),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def references(blob, base, target):
    pointers = [base+m.start() for m in re.finditer(re.escape(struct.pack('<I', target)), blob)]
    calls = []
    for m in re.finditer(b'[\xcd\xdd]', blob):
        p = m.start(); size = 2 if blob[p] == 0xcd else 4
        if p+1+size <= len(blob):
            delta = int.from_bytes(blob[p+1:p+1+size], 'little', signed=True)
            if (base+p+delta) & 0xffffffff == target:
                calls.append(base+p)
    return {'exact_pointer_candidates': list(map(hex, pointers)),
            'cd_dd_call_candidates': list(map(hex, calls))}


def em5_state(blob, target, mask=0, frame=4, regs=None):
    s = ProbeState(target, mask, frame, b'x', regs or {})
    s.regions = [Region('em5_main', EM5_BASE, blob, 'rx') if r.name == 'main' else r
                 for r in s.regions]
    return s


def checked_run(s, hooks):
    result = s.run(hooks, limit=20000)
    assert result['status'] == 'breakpoint', result
    return s.regs['pc']


def em5_case(blob, wake, snapshot, controller_mode=0, initial_guard=1):
    # Real key lookup and snapshot comparison, with ordinary setting values.
    s = em5_state(blob, 0x7e5e6c94)
    for name, address, data in [
        ('guard_fixture', 0x602a9b4c, bytes((initial_guard,))),
        ('input_flags_fixture', 0x60501e98, bytes(8)),
        ('key_snapshot_fixture', 0x60501f58, bytes((snapshot,))),
        ('controller_mode_fixture', 0x60416451, bytes((controller_mode,))),
        ('debug_fixture', 0x602a9ea8, b'\0'),
    ]:
        s.ram(name, address, data)
    settings = []
    for _ in range(8):
        pc = checked_run(s, {CALLER+7, 0x7e44ed1c})
        if pc == CALLER+7:
            break
        assert s.regs['d0'] in (8050, 8130), s.regs
        settings.append({'id': s.regs['d0'], 'modeled_value': 0})
        s.return_from_model(0)
    assert s.regs['pc'] == CALLER+7
    assert [x['id'] for x in settings] == [8050, 8130]
    guard = s.read(0x602a9b4c, 1)[0]
    expected_guard = 0 if not (snapshot & 8) and controller_mode != 9 else initial_guard
    assert guard == expected_guard
    guard_steps = s.steps

    # Execute the stock SD init wrapper, including the actual wake lookup and
    # selector. Its flash-interface initialization is modeled to complete.
    s = em5_state(blob, 0x7e622cb9)
    s.ram('guard_from_previous_slice', 0x602a9b4c, bytes((guard,)))
    s.ram('wake_reason_fixture', 0x6041644e, struct.pack('<H', wake))
    s.ram('client_state', 0x60512030, b'\xa5\xa5')
    pc = checked_run(s, {CALLER+7, 0x7e45f873})
    assert pc == 0x7e45f873
    s.return_from_model(0)
    assert checked_run(s, {CALLER+7}) == CALLER+7
    assert s.read(0x60512030, 2) == b'\0\0'
    selection = s.regs['d0']
    translated = struct.unpack_from('<I', blob, 0x7e84efc0-EM5_BASE+4*wake)[0]
    expected = 1 if guard == 0 and translated in (12, 0x01000001, 0x01000002) else 2
    assert selection == expected
    selection_steps = s.steps

    # Actual final branch, after intervening initialization (not executed here).
    # The startup function retains the result in d2. Do not claim those skipped
    # initializers succeed or that other tasks cannot run concurrently.
    s = em5_state(blob, 0x7e5e6206, 0xa0, 12, {'d2': selection})
    logs = {0x7e421650, 0x7e4217a1, 0x7e442b6a}
    starts = []; messages = []
    for _ in range(12):
        pc = checked_run(s, logs | {0x7e4413b0, 0x7e441490})
        if pc == 0x7e441490:
            break
        if pc == 0x7e4413b0:
            starts.append(s.regs['d0'])
        else:
            a = s.regs['a0']
            messages.append(blob[a-EM5_BASE:a-EM5_BASE+100].split(b'\0')[0].decode('ascii'))
        s.return_from_model(0)
    assert s.regs['pc'] == 0x7e441490
    assert starts == ([20] if selection == 1 else [82]), starts
    return dict(wake_reason=wake, translated=hex(translated), snapshot=hex(snapshot),
                controller_mode=controller_mode, initial_guard=initial_guard,
                final_guard=guard, selection=selection, requested_task=starts[0],
                instructions=[guard_steps, selection_steps, s.steps], settings=settings,
                messages=messages, stopped_at='current-task exit; activation trapped')


def penf_current_wrapper(current):
    s = ProbeState(0x60951dcf, 0, 4, b'x', {})
    initialize_pointers(s)
    obj = 0x20001000
    s.ram('modeled_allocated_object', obj, b'\xa5'*28, aliases=False)
    query_count = 0; allocation_count = 0
    for _ in range(8):
        pc = checked_run(s, {0x60951de9, 0x60031be2, 0x60950a6e, 0x600307dd})
        assert pc != 0x600307dd, 'unexpected task activation'
        if pc == 0x60951de9:
            break
        if pc == 0x60031be2:
            query_count += 1
            s.write(s.regs['a0'], struct.pack('<H', current))
            s.return_from_model(0)
        else:
            assert s.regs['d0'] == 28
            allocation_count += 1
            s.return_from_model(0)
            s.regs['a0'] = obj
    assert s.regs['pc'] == 0x60951de9
    assert query_count == allocation_count == 1
    raw = s.read(obj, 28)
    vtable = struct.unpack_from('<I', raw)[0]
    stored_id = struct.unpack_from('<H', raw, 4)[0]
    assert (vtable, stored_id) == (0x60a4f7bc, current)
    assert struct.unpack_from('<2I', raw, 8) == (1, 1)
    assert s.regs['a0'] == obj
    return dict(current_task_fixture=current, wrapped_task=stored_id,
                vtable=hex(vtable), object_bytes=raw.hex(), instructions=s.steps,
                task_activation=False,
                note='ID 95 control presupposes that SD is already the current task'
                if current == 95 else 'no substitution of SD task 95')


def fast_start_case(em5, model, skip):
    if model == 'em5':
        s = em5_state(em5, 0x7e5e3781, frame=32)
        state_address = 0x604f1978
        wait, clear, log, normal = 0x7e441088, 0x7e4410f4, 0x7e5e5037, 0x7e5e3e8f
        bit = 32 if skip else 1
    else:
        s = ProbeState(0x601a4e2f, 0, 64, b'x', {})
        state_address = 0x618642c4
        wait, clear, log, normal = 0x60069138, 0x60069250, 0x60041aa5, 0x601a566e
        bit = 64 if skip else 1
    s.ram('startup_progress_fixture', state_address, bytes(4))
    delivered = False; cleared = []; messages = []; flag_object = None
    for _ in range(10):
        pc = checked_run(s, {wait, clear, log, normal})
        if pc == normal:
            assert not skip
            break
        if pc == wait:
            if delivered:
                assert skip
                break
            delivered = True
            flag_object = s.regs['d0']
            s.write(s.regs['a0'], struct.pack('<I', bit))
        elif pc == clear:
            cleared.append(s.regs['d1'])
        else:
            a = s.regs['a0']
            messages.append(bytes(s.read(a+i, 1)[0] for i in range(80)).split(b'\0')[0].decode('ascii'))
        s.return_from_model(0)
    assert delivered and cleared == [(~bit) & 0xffffffff]
    final = struct.unpack('<I', s.read(state_address, 4))[0]
    assert final == (11 if skip else 0)
    assert s.regs['pc'] == (wait if skip else normal)
    return dict(model=model, supplied_event=hex(bit), flag_object=flag_object,
                progress_before=0, progress_after=final, instructions=s.steps,
                normal_handler_entered=not skip, stop=hex(s.regs['pc']), messages=messages,
                scope='One supplied event; consumer only. Does not demonstrate its producer or physical recovery activation.')


def audit(out, em5, penf, em5ii):
    windows = []; startup_asm = None
    for name, path, base, blob, spans in [
        ('em5', EM5, EM5_BASE, em5, EM5_WINDOWS),
        ('penf', DEFAULT_IMAGE, PENF_BASE, penf, PENF_WINDOWS),
        ('em5ii', EM5II, PENF_BASE, em5ii, EM5II_WINDOWS),
    ]:
        for label, (lo, hi) in spans.items():
            asm = disassemble(path, base, lo, hi)
            lines = [line for line in asm.splitlines() if re.match(r'^[0-9a-f]{8}:', line)]
            last = lines[-1].split('\t')
            assert int(last[0][:-1], 16)+len(last[1].split()) == hi, (label, last)
            assert '\tunknown' not in asm, label
            dest = out / f'{name}.{label}.asm'
            dest.write_text(asm)
            windows.append(dict(image=name, label=label, start=hex(lo), stop=hex(hi),
                                sha256=sha(blob[lo-base:hi-base]), file=dest.name))
            if label == 'application_startup':
                startup_asm = asm
    # Decode aligned instructions to inventory raw task IDs; high bits can name
    # a task on another CPU, so do not index the CPU0 table with those IDs.
    starts = []
    for line in startup_asm.splitlines():
        if '\tcall\t0x7e4413b0,' not in line:
            continue
        address = int(line.split(':')[0], 16); p = address-EM5_BASE
        pre = em5[p-7:p]
        row = {'site': hex(address)}
        if pre[:2] == b'\xfc\xac' and pre[-1] == 0x18:
            const = struct.unpack_from('<I', pre, 2)[0]
            task = struct.unpack_from('<H', em5, const-EM5_BASE)[0]
            row.update(id_constant=hex(const), raw_task_id=hex(task))
            if task < 128:
                row['cpu0_entry'] = hex(struct.unpack_from('<I', em5, 0x7e4e864c-EM5_BASE+task*28+12)[0])
        else:
            row['classification'] = 'review separately; no immediately preceding constant load'
        starts.append(row)
    for site, task in [(0x7e5e5642, 21), (0x7e5e5db2, 18),
                       (0x7e5e621e, 20), (0x7e5e626e, 82)]:
        assert next(r for r in starts if r['site'] == hex(site))['raw_task_id'] == hex(task)
    refs = {'em5': {}, 'penf': {}}
    for label, target in {'startup': 0x7e5e5538, 'guard': 0x602a9b4c,
                          'sd_init': 0x7e622cb9, 'selector': 0x7e62405f}.items():
        refs['em5'][label] = references(em5, EM5_BASE, target)
    for label, target in {'factory_getter': 0x6094fda1,
                          'factory_global': 0x616061dc,
                          'factory_global_uncached_alias': 0xa16061dc,
                          'existing_factory': 0x60950973,
                          'fast_start_signal': 0x601a50e7,
                          'fast_start_flag_id': 0x60041000}.items():
        refs['penf'][label] = references(penf, PENF_BASE, target)
    methods = []
    for site_hex in refs['penf']['factory_getter']['cd_dd_call_candidates']:
        site = int(site_hex, 16)
        asm = disassemble(DEFAULT_IMAGE, PENF_BASE, site, site+40)
        method = re.search(r'\tmov\t\((\d+),a[0-3]\),a[0-3]', asm)
        assert method, site_hex
        offset = int(method[1])
        indirect = next(line for line in asm.splitlines() if '\tcalls\t(a' in line)
        end = int(indirect.split(':')[0], 16)+2
        asm = disassemble(DEFAULT_IMAGE, PENF_BASE, site, end)
        dest = out / f'penf.factory_caller_{site:08x}.asm'
        dest.write_text(asm)
        methods.append(dict(site=site_hex, vtable_offset=offset, file=dest.name,
                            end_exclusive=hex(end), sha256=sha(penf[site-PENF_BASE:end-PENF_BASE])))
    assert len(methods) == 17
    assert [r['site'] for r in methods if r['vtable_offset'] == 36] == ['0x60951ddc']
    transfers = transfer_candidates(penf, PENF_BASE,
        {0x6094fda1, 0xa094fda1, 0x60950973, 0xa0950973})
    assert [t['site'] for t in transfers] == [r['site'] for r in methods]
    assert refs['penf']['factory_global']['exact_pointer_candidates'] == ['0x6094fda3']
    assert not refs['penf']['factory_global_uncached_alias']['exact_pointer_candidates']
    strings = {}
    for name, blob, base in [('em5', em5, EM5_BASE), ('penf', penf, PENF_BASE),
                             ('em5ii', em5ii, PENF_BASE)]:
        strings[name] = {s.decode(): [hex(base+m.start()) for m in re.finditer(re.escape(s), blob)]
                         for s in [b'[usr]firmup', b'gfwup', b'FIRMUP_CLI', b'firmup_client_dispose_end']}
    assert strings['em5']['[usr]firmup'] and not strings['penf']['[usr]firmup']
    # Debug parser's "key", "o" branch emits 02000004 / 02010004.
    for addr, expected in [(2123288053, b'key'), (2123288057, b'o')]:
        assert em5[addr-EM5_BASE:addr-EM5_BASE+len(expected)+1] == expected+b'\0'
    assert em5[0x7e8ec981-EM5_BASE:].startswith(b'app key o -- OK')
    em5ii_ref = {hex(a): references(em5ii, PENF_BASE, a) for a in
                 (0x60b5e53d, 0x60b5e78f, 0x60b5e992, 0x60040d7a)}
    assert em5ii_ref['0x60b5e53d']['exact_pointer_candidates'] == ['0x6003a134']
    assert struct.unpack_from('<4I', em5ii, 0x6003a128-PENF_BASE) == (95, 0, 0, 0x60b5e53d)
    assert em5ii[0x60b5e78f-PENF_BASE:0x60b5e793-PENF_BASE] == b'\0\xde\0\0'
    assert em5ii[0x60b5e992-PENF_BASE:0x60b5e995-PENF_BASE] == b'\xde\0\0'
    assert not strings['em5ii']['[usr]firmup'] and not strings['em5ii']['gfwup']
    producers = [(0x601a6d8c, 128), (0x601a729e, 1), (0x601a750e, 2), (0x601a7e31, 8)]
    assert refs['penf']['fast_start_signal']['cd_dd_call_candidates'] == [hex(a) for a, _ in producers]
    for site, value in producers:
        p = site-PENF_BASE
        encoding = b'\x2c\x80\0' if value == 128 else bytes((0x80, value))
        assert penf[p-len(encoding):p] == encoding
        (out/f'penf.fast_signal_{site:08x}.asm').write_text(
            disassemble(DEFAULT_IMAGE, PENF_BASE, site-len(encoding), site+5))
    return dict(windows=windows, raw_startup_task_requests=starts,
                references=refs, factory_callers=methods, diagnostic_strings=strings,
                expanded_factory_transfers=transfers, em5ii_references=em5ii_ref,
                penf_fast_signal_callers=[dict(site=hex(a), mask=hex(v)) for a, v in producers],
                caveat='Literal/CD/DD candidates and reviewed windows are not a whole-program reachability proof.')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        ap.error('output directory must be new')
    em5 = EM5.read_bytes(); penf = firmware(); em5ii = EM5II.read_bytes()
    assert sha(em5) == EM5_HASH
    assert sha(em5ii) == EM5II_HASH
    args.out.mkdir(parents=True)
    evidence = audit(args.out, em5, penf, em5ii)
    cases = [em5_case(em5, wake, snapshot) for wake in range(10) for snapshot in (0, 8)]
    cases += [em5_case(em5, 1, 0, controller_mode=9),
              em5_case(em5, 1, 8, initial_guard=0),
              em5_case(em5, 1, 0x80), em5_case(em5, 1, 0x88)]
    wrappers = [penf_current_wrapper(task) for task in (1, 47, 0x101d, 95)]
    fast_cases = [fast_start_case(em5, model, skip)
                  for model in ('em5', 'penf') for skip in (False, True)]
    paths = [Path(__file__), ROOT/'tools/penf_update_probe.py',ROOT/'tools/penf_probe.py',
             ROOT/'tools/penf_boot_emulator.py', ROOT/'tools/penf_emulator.py',
             ROOT/'tools/penf_input_recovery_probe.py', ROOT/'tools/penf_preset_startup_audit.py',
             ROOT/'tools/penf_disasm.py', ENGINE, DEFAULT_OBJDUMP]
    paths.append(ROOT/'tools/penf_sd_activation_audit.py')
    result = dict(scope='Bounded native E-M5 stock selector slices and PEN-F current-thread wrapper; not physical or continuous boot',
                  images={'em5': {'path': str(EM5.relative_to(ROOT)), 'sha256': sha(em5), 'base': hex(EM5_BASE)},
                          'penf': {'path': str(DEFAULT_IMAGE), 'sha256': sha(penf), 'base': hex(PENF_BASE)},
                          'em5ii': {'path': str(EM5II.relative_to(ROOT)), 'sha256': sha(em5ii), 'base': hex(PENF_BASE)}},
                  tools={str(p.resolve().relative_to(ROOT)): sha(p.read_bytes()) for p in paths},
                  em5_models=['input snapshot and controller bytes supplied',
                              'guard pre-state supplied; initial-value provenance not established',
                              'settings 8050 and 8130 return zero',
                              'flash-interface initialization 7e45f873 completes',
                              'intervening startup is statically reviewed, not executed',
                              'diagnostics suppressed; task activation and exit trapped'],
                  penf_models=['kernel current-task ID supplied', 'allocator supplies one 28-byte object'],
                  em5_cases=cases, penf_cases=wrappers, fast_start_cases=fast_cases,
                  static=evidence, passed=len(cases)+len(wrappers)+len(fast_cases))
    (args.out/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'passed': result['passed'], 'em5_cases': len(cases),
                      'penf_cases': len(wrappers), 'summary': str(args.out/'summary.json')}))


if __name__ == '__main__':
    main()
