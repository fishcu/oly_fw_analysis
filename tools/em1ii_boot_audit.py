#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Offline E-M1 II startup/SD comparison, with bounded native client probes.

Pins six locally archived stock images. No device access, patch generation,
whole-boot emulation or claim of physical OK-to-updater reachability.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import struct
import tempfile

from oly_container import parse, sha256
from oly_sd_selector_comparison import references
from penf_disasm import DEFAULT_OBJDUMP, window
from penf_emulator import BASE, ENGINE, Region
from penf_probe import BUFFER, CALLER, ProbeState
from penf_sd_activation_audit import transfer_candidates


ARCHIVE = 'research/xdel_olympus_20260924/extracted/original/em1mk2'
SOURCES = {
    '3001': ('e-m1_hack/original_fw/3.0/OLY_E_125_3001_0000_0000.BIN',
             '9c0d32363caafd5c77ef1828cf6fdbdee222f1e199719fdafd224862d0670cd7'),
    '3200': ('e-m1_hack/original_fw/3.2/OLY_E_125_3200_0000_0000.BIN',
             '3ed0f000012cc86b9123955730a4d9aaf6be8d8604fc07947093c5d03efa5f11'),
    '3400': (f'{ARCHIVE}/OLY_E_125_3400_0000_0000.BIN',
             'f9218b57bdad23457a64ef90c80c1cb6f4ab43996e858f3d131ea6fb25c11b9d'),
    '3500': (f'{ARCHIVE}/OLY_E_125_3500_0000_0000.BIN',
             '69142c01ade59c83eed7dbf9e64d4de4a5ee041c8154903d58181443bb21b569'),
    '3600': (f'{ARCHIVE}/OLY_E_125_3600_0000_0000.BIN',
             'f462e042fa6743c639e594a11f95cbe07955c9022cfdca8b0a6f64c5697e11b2'),
    '3700': (f'{ARCHIVE}/OLY_E_125_3700_0000_0000.BIN',
             '0a41fb8e1105751f7817e5664f2edf2a1bdf399f070e91b4e3c84e6943113803'),
}
WINDOWS_3200 = {
    'main_entry': (0x60021020, 0x600210f9),
    'c_startup': (0x600210f9, 0x600213bc),
    'kernel_entry': (0x600326a0, 0x600327f1),
    'kernel_auto_start': (0x60032874, 0x600328c4),
    'initial_task': (0x600521da, 0x60052333),
    'initial_application': (0x60041e47, 0x600420f2),
    'ustart_l': (0x600420f2, 0x600422a8),
    'ustart_l1': (0x600422a8, 0x60042307),
    'ustart_l2': (0x60042307, 0x6004258c),
    'application_startup': (0x6004258c, 0x60042b02),
    'section_status_and_copy': (0x60042b02, 0x60042c1b),
    'section_wait_and_constructors': (0x60042c1b, 0x60042c8a),
    'start_wrapper': (0x600518bb, 0x600518ff),
    'delay_and_exit': (0x60051a36, 0x60051a9e),
    'fast_worker': (0x601a7e34, 0x601a812f),
    'fast_signal': (0x601a8168, 0x601a817a),
    'fast_signal_128': (0x601a9eb2, 0x601a9eba),
    'fast_signal_2': (0x601aa382, 0x601aa389),
    'fast_signal_8': (0x601aad43, 0x601aad4a),
    'fast_other_producers': (0x601a8296, 0x601a82f2),
    'normal_update_service_start': (0x601ab5f3, 0x601ab61c),
    'sd_no_file': (0x6021ad9a, 0x6021adc3),
    'controller_command': (0x600226fd, 0x60022735),
    'sd_controller_wrapper': (0x60cf7b59, 0x60cf7b64),
    'version_trailer_load': (0x600423e2, 0x60042403),
    'version_publication': (0x601aaafe, 0x601aab2b),
    'sd_client': (0x60cf6125, 0x60cf6329),
    'sd_search': (0x60cf6329, 0x60cf6481),
    'sd_candidate': (0x60cf6481, 0x60cf64ce),
    'sd_read_and_suffix': (0x60cf64ce, 0x60cf65b3),
    'debug_task_start': (0x600578a3, 0x600578d0),
    'explicit_start_1048': (0x601ab47e, 0x601ab495),
    'explicit_start_1031': (0x601ab745, 0x601ab74f),
}


def words(b, address, count=1):
    return struct.unpack_from('<' + 'I' * count, b, address - BASE)


def string(b, address):
    assert BASE <= address < BASE + len(b)
    return b[address-BASE:address-BASE+200].split(b'\0')[0].decode('ascii')


def target(b, address):
    offset = address - BASE
    assert b[offset] in (0xcd, 0xdd), hex(address)
    n = 2 if b[offset] == 0xcd else 4
    return (address + int.from_bytes(b[offset+1:offset+1+n], 'little', signed=True)) & 0xffffffff


def configuration(b, main):
    descriptor = words(b, 0x6003969c, 7)
    assert descriptor[:3] == (90, 0, 0) and descriptor[4:] == (45, 2048, 0)
    entry = descriptor[3]
    assert b[entry-BASE:entry-BASE+8] == bytes.fromhex('cff0fafe64ff9f00')
    precheck = target(b, entry+0x11)
    assert b[precheck-BASE:precheck-BASE+4] == bytes.fromhex('00de0000')
    table, = words(b, entry+0xb1)
    directory, = words(b, entry+0xc6)
    assert string(b, directory) == 'DCOLYMP    '
    # Read the actual common initializer source/destination operands. Main's
    # container flash mapping and runtime mapping differ by a constant here.
    assert b[0x600211d9-BASE:0x600211db-BASE] == b'\xfc\xdc'
    flash, = words(b, 0x600211db)
    destination, = words(b, 0x600211e1)
    source = BASE + flash - (main.address + 32)
    end, = words(b, 0x60021171)
    assert destination & 0x40000000 == 0
    cached = destination - 0x40000000
    arrays = []
    records = []
    for i in range(11):
        addr = table+20*i
        kind, option, pointers, count, image_type = words(b, addr, 5)
        initializer = source+pointers-cached
        assert source <= initializer < initializer+4*count <= end
        data = b[initializer-BASE:initializer-BASE+4*count]
        patterns = [string(b, p) for p in struct.unpack('<'+'I'*count, data)]
        arrays.append((pointers, data))
        records.append(dict(address=hex(addr), drive=kind, option=option,
                            patterns=patterns, image_type=image_type,
                            runtime_array=hex(pointers), initializer=hex(initializer)))
    assert records[0]['patterns'] == ['S125????BIN']
    assert records[-1]['patterns'] == ['E125????BIN', 'G125????BIN', 'H125????BIN', 'W125????BIN']
    find_wrapper = target(b, entry+0xd7)
    find_one = target(b, find_wrapper+0x2d)
    callback, = words(b, find_one+0x3c)
    suffix = target(b, callback+0x1c)
    return dict(entry=entry, precheck=precheck, table=table, directory=directory,
                records=records, arrays=arrays, initializer_source=source,
                initializer_destination=destination, initializer_end=end,
                find_wrapper=find_wrapper, find_one=find_one, callback=callback,
                suffix=suffix, controller=target(b, entry+0x2c),
                init=target(b, entry+0x41), mount=target(b, entry+0x67),
                no_file=target(b, entry+0x5c))


def state(b, entry, mask=0, frame=0, data=b'x', registers=None):
    s = ProbeState(entry, mask, frame, data, registers or {})
    s.regions = [Region('em1ii_main', BASE, b, 'rx') if r.name == 'main' else r
                 for r in s.regions]
    return s


def run(s, hooks, limit=20000):
    result = s.run(hooks, limit=limit)
    assert result['status'] == 'breakpoint', (hex(s.regs['pc']), result['status'], result.get('fault'))
    return s.regs['pc']


def suffix_case(b, config, text):
    s = state(b, config['suffix'], 0xf0, 16, text.encode(), {'d0': 4, 'a0': BUFFER})
    run(s, {CALLER+7})
    expected = int(text, 16)
    assert s.regs['d0'] == expected
    return dict(text=text, value=hex(expected), instructions=s.steps)


def candidate_case(b, config, suffix, previous, attributes):
    context, obj, name, slot, method = (0x20100100, 0x20100200, 0x20100300, 0x20100400, 0x18040000)
    s = state(b, config['callback'], registers={'a0': slot, 'a1': obj})
    s.ram('synthetic_file_and_selection', 0x20100000, bytes(0x500), aliases=False)
    # This method is reached via CALLS, so use its native RETS convention.
    s.regions.append(Region('synthetic_cluster_method', method, b'\x80\x4d\xf0\xfc', 'rx'))
    s.write(slot, struct.pack('<I', context))
    s.write(obj, struct.pack('<3I', 0, name, method))
    s.write(name, ('E125'+suffix+'BIN\0').encode())
    s.write(context+28, struct.pack('<4I', 900, 901, previous, 902))
    attr_api = target(b, config['callback']+9)
    size_api = target(b, config['callback']+0x34)
    cookie_api = target(b, config['callback']+0x3f)
    calls = []
    for _ in range(8):
        pc = run(s, {attr_api, size_api, cookie_api, method, CALLER+7})
        if pc == CALLER+7:
            break
        calls.append(hex(pc))
        assert s.regs['a0'] == obj
        if pc == method:
            assert s.run(set(), limit=1)['status'] == 'instruction_limit'
            continue
        s.return_from_model({attr_api: attributes, method: 77, size_api: 12345, cookie_api: 88}[pc])
    assert s.regs['pc'] == CALLER+7
    selected = not (attributes & 0x1e) and int(suffix, 16) > previous
    result = struct.unpack('<4I', s.read(context+28, 16))
    expected = (12345, 77, int(suffix, 16), 88) if selected else (900, 901, previous, 902)
    assert result == expected, result
    assert len(calls) == (4 if selected else 1)
    return dict(suffix=suffix, previous=hex(previous), attributes=hex(attributes),
                selected=selected, result=list(result), modeled_file_methods=calls,
                instructions=s.steps)


def no_file_case(b, config, absent_code):
    s = state(b, config['entry'])
    for index, (pointer, data) in enumerate(config['arrays']):
        s.ram(f'pattern_array_{index}', pointer, data, aliases=False)
    logs = {0x60022f61, 0x60023157}
    hooks = logs | {0x60022dfe, config['controller'], config['init'], config['mount'],
                    config['find_one'], 0x60051a36, 0x60051a52}
    patterns = []; commands = []; messages = []
    for _ in range(120):
        pc = run(s, hooks)
        if pc == 0x60051a52:
            break
        if pc == config['find_one']:
            context = s.regs['a0']
            directory, pattern = struct.unpack('<2I', s.read(context+4, 8))
            assert s.read_c_string(directory) == b'DCOLYMP    '
            patterns.append(s.read_c_string(pattern).decode())
            s.return_from_model(absent_code)
            continue
        if pc == config['controller']:
            commands.append(s.regs['d0'])
        if pc in logs:
            messages.append(s.read_c_string(s.regs['a0']).decode())
        s.return_from_model(0)
    assert s.regs['pc'] == 0x60051a52
    assert patterns == [p for record in config['records'] for p in record['patterns']]
    assert commands == [0, 10]
    # Native task-exit wrapper, with only current-task query/log modeled.
    assert run(s, {0x600317be}) == 0x600317be
    s.write(s.regs['a0'], struct.pack('<H', 90))
    s.return_from_model(0)
    assert run(s, {0x60053625}) == 0x60053625
    s.return_from_model(0)
    assert run(s, {0x60031688}) == 0x60031688
    return dict(absent_code=hex(absent_code), patterns=patterns, controller_arguments=commands,
                stopped_at='native current-task termination API 60031688',
                messages=messages, instructions=s.steps,
                models=['fixed counter; diagnostics suppressed', 'filesystem initialization/mount succeed',
                        'directory lookup returns specified not-found result',
                        'controller call acknowledged; no hardware semantics assumed',
                        'delay returns; current-task query reports task 90'],
                file_or_flash_write=False)


def completion_case(b, flags):
    # Isolated tail of USR_FAST, not a scheduled worker or a fabricated producer.
    s = state(b, 0x601a80d2)
    run(s, {0x601a80d2})
    s.write(s.regs['sp']+8, struct.pack('<I', flags))
    s.ram('progress_fixture', 0x62767ad4, struct.pack('<I', 7))
    clears = []
    for _ in range(4):
        pc = run(s, {0x601a80fe, 0x60041e09, 0x60051250})
        if pc == 0x601a80fe:
            break
        if pc == 0x60051250:
            clears.append([s.regs['d0'], hex(s.regs['d1'])])
        s.return_from_model(0)
    progress, = struct.unpack('<I', s.read(0xa2767ad4, 4))
    assert progress == (11 if flags & 0x40 else 7)
    assert clears == ([[135, '0xffffffbf']] if flags & 0x40 else [])
    return dict(injected_event=hex(flags), progress=progress, modeled_flag_clears=clears,
                instructions=s.steps, producer_established=False)


def autostart_case(b, task_id):
    # Runtime TCB fixture carries the stock descriptor's ID/attribute/argument.
    # No scheduler, task construction or actual task execution is synthesized.
    record = words(b, 0x60038ce0+28*(task_id-1), 7)
    tcb, slot = 0x20100000, 0x20100100
    s = state(b, 0x60032898, registers={'a2': slot})
    s.ram('tcb_fixture', tcb, bytes(92), aliases=False)
    s.ram('tcb_pointer', slot, struct.pack('<I', tcb), aliases=False)
    s.write(tcb+16, struct.pack('<H', task_id))
    s.write(tcb+68, struct.pack('<2I', record[1], record[2]))
    pc = run(s, {0x600328b9, 0x600322f0})
    activated = pc == 0x600322f0
    assert activated == bool(record[1] & 2)
    if activated:
        assert s.regs['a0'] == tcb and s.regs['d0'] == record[2]
    return dict(task_id=task_id, stock_attribute=record[1], requests_activation=activated,
                instructions=s.steps, stopped_at=hex(pc))


def version_case(b, trailer):
    s = state(b, 0x601aab15)
    s.ram('loaded_trailer_fixture', 0x6146de00, trailer, aliases=False)
    run(s, {0x6005e780})
    expected, = struct.unpack_from('<I', trailer, 16)
    assert (s.regs['d0'], s.regs['d1'], s.regs['a0'], s.regs['a1']) == (0xc082, 0, 0, expected)
    return dict(setting='0xc082', published_version_word=hex(expected), instructions=s.steps,
                assumption='trailer already copied; stops before settings writer', ui_formatter_traced=False)


def start_candidates(b, entry):
    result = []
    for raw in references(b, BASE, entry)['cd_dd_call_candidates']:
        address = int(raw, 16); p = address-BASE; source = None
        row = dict(call=raw, preceding_bytes=b[p-16:p].hex())
        for back in (7, 13):
            if b[p-back:p-back+2] == b'\xfc\xac' and b[p-1] == 0x18:
                source, = struct.unpack_from('<I', b, p-back+2)
                break
        if source is not None and BASE <= source < BASE+len(b)-1:
            value, = struct.unpack_from('<H', b, source-BASE)
            row.update(kind='image_halfword', source=hex(source), raw_id=value)
        elif b[p-3] == 0x2c:
            value, = struct.unpack_from('<H', b, p-2)
            row.update(kind='immediate16', raw_id=value)
        else:
            row.update(kind='unclassified_argument')
        assert row.get('raw_id', -1) & 0xfff != 90
        result.append(row)
    return dict(counts=dict(Counter(r['kind'] for r in result)), calls=result,
                caveat='Raw CD/DD candidates with local argument idioms; not whole-program reachability.')


def export(b, path, out, name, lo, hi):
    asm = window(b, path, DEFAULT_OBJDUMP, lo, hi)
    instructions = [line for line in asm.splitlines() if re.match(r'^[0-9a-f]{8}:', line)]
    last = instructions[-1].split('\t')
    assert int(last[0][:-1], 16)+len(last[1].split()) == hi, (name, last)
    assert '\tunknown\t' not in asm, name
    (out / f'{name}.asm').write_text(asm)
    return dict(start=hex(lo), end=hex(hi), sha256=sha256(b[lo-BASE:hi-BASE]), file=f'{name}.asm')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', required=True, type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    report = dict(scope=__doc__, images={}, probes={}, disassembly={},
                  engine_sha256=sha256(ENGINE.read_bytes()), tool_sha256=sha256(Path(__file__).read_bytes()))
    reference = Path('analysis/preset_startup_final/em1ii3200.main.bin').read_bytes()
    assert sha256(reference) == SOURCES['3200'][1]
    with tempfile.TemporaryDirectory(prefix='em1ii-boot-') as scratch:
        for build, (filename, expected_hash) in SOURCES.items():
            container = Path(filename).read_bytes()
            blocks = parse(container)
            main_block, = [v for v in blocks if v.kind == 0x100]
            b = main_block.payload
            assert sha256(b) == expected_hash
            c = configuration(b, main_block)
            serializable = {k: v for k, v in c.items() if k != 'arrays'}
            serializable = {k: hex(v) if isinstance(v, int) else v for k, v in serializable.items()}
            report['images'][build] = dict(container=filename, container_sha256=sha256(container),
                blocks=[v.metadata() for v in blocks], configuration=serializable,
                precheck_references=references(b, BASE, c['precheck']),
                sd_entry_references=references(b, BASE, c['entry']),
                sd_id_references=references(b, BASE, 0x60040ca4),
                sd_candidate_same_bytes_as_3200=b[c['callback']-BASE:c['callback']-BASE+77] ==
                    reference[0x60cf6481-BASE:0x60cf64ce-BASE],
                suffix_same_bytes_as_3200=b[c['suffix']-BASE:c['suffix']-BASE+85] ==
                    reference[0x60cf655b-BASE:0x60cf65b0-BASE],
                debug_string_counts={text: b.count(text.encode()) for text in ('gfwup', '[usr]firmup')},
                literal_entry_search=[dict(kind=hex(block.kind), hits={hex(address):
                    [hex(m.start()) for m in re.finditer(re.escape(struct.pack('<I', address)), block.payload)]
                    for address in (BASE, 0xa0021020, 0x600210f9, 0xa00210f9)}) for block in blocks])
            s = state(b, c['precheck']); run(s, {CALLER+7}); assert s.regs['d0'] == 0
            cases = dict(precheck=dict(result=0, instructions=s.steps),
                suffix=[suffix_case(b, c, t) for t in ('0000','0001','3001','3200','3700','9999','FFFF','aBcD')],
                candidates=[candidate_case(b, c, t, previous, attr) for t, previous, attr in
                            [('9999', 0, 0), ('3001', 0x3200, 0), ('3200', 0x3200, 0),
                             ('3700', 0x3200, 0), ('FFFF', 0x9999, 0), ('0000', 0, 0),
                             ('9999', 0, 0x10), ('9999', 0, 0x20), ('9999', 0, 0x02),
                             ('9999', 0, 0x01)]],
                no_file=[no_file_case(b, c, code) for code in (0xe00, 0xe0c)])
            report['probes'][build] = cases
            if build == '3200':
                report['completion_probes_3200'] = [completion_case(b, flag) for flag in (0, 0x40)]
                report['autostart_probes_3200'] = [autostart_case(b, task_id) for task_id in (1, 90)]
                report['version_probe_3200'] = version_case(b, main_block.trailer)
                report['start_candidate_audit_3200'] = {hex(entry): start_candidates(b, entry)
                    for entry in (0x600518bb, 0x60030727)}
                report['main_transfer_candidates_3200'] = transfer_candidates(b, BASE,
                    {BASE, 0x600210f9, c['entry']})
                report['fast_signal_references_3200'] = references(b, BASE, 0x601a8168)
                report['fast_flag_references_3200'] = references(b, BASE, 0x60040f1c)
                report['section_descriptors_3200'] = [list(map(hex, words(b, 0x60027450+12*i, 3))) for i in range(9)]
                report['tasks_3200'] = {str(i): list(map(hex, words(b, 0x60038ce0+28*(i-1), 7)))
                    for i in (1, 18, 43, 44, 45, 46, 47, 62, 63, 90, 96)}
                report['peer_loader_tasks_3200'] = {hex(a): list(map(hex, words(b, a, 7)))
                    for a in (0x6003c980, 0x6003d828)}
                report['version_trailer_3200'] = dict(flash_address=hex(main_block.address+32+len(b)),
                    native_read_destination='0x6146de00', metadata_word=hex(struct.unpack_from('<I',main_block.trailer,16)[0]),
                    publisher='601aab18 reads trailer+16; 601aab24 passes to setting writer with ID c082',
                    ui_formatter_traced=False)
                extra, = [v for v in blocks if v.kind == 0x10e]
                report['extra_component_3200'] = dict(sha256=sha256(extra.payload),
                    strings=[dict(offset=hex(m.start()), text=m.group().decode())
                        for m in re.finditer(rb'[ -~]{5,}', extra.payload)
                        if any(t in m.group().lower() for t in (b'task_drive', b'luke_main', b'firmup', b'dcolymp', b'e125', b'boot'))],
                    classification='Executable drive/controller material; not identified as an independent boot/recovery loader.')
            if build in ('3200', '3700'):
                path = Path(scratch)/f'em1ii{build}.main.bin'; path.write_bytes(b)
                windows = WINDOWS_3200 if build == '3200' else {
                    'main_entry': (BASE, 0x600210f9),
                    'sd_client': (c['entry'], c['find_wrapper']),
                    'sd_precheck': (c['precheck'], c['precheck']+4),
                    'sd_candidate': (c['callback'], c['callback']+77),
                    'sd_suffix': (c['suffix'], c['suffix']+85),
                    'sd_no_file': (c['no_file'], c['no_file']+0x29),
                }
                for name, (lo, hi) in windows.items():
                    key = f'{build}.{name}'
                    report['disassembly'][key] = export(b, path, args.out, key, lo, hi)
    report['probe_cases'] = sum(1 + len(v['suffix']) + len(v['candidates']) + len(v['no_file'])
                               for v in report['probes'].values()) + len(report['completion_probes_3200']) + 3
    (args.out/'audit.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(images=list(report['images']), native_cases=report['probe_cases'],
                         windows=len(report['disassembly']), report=str(args.out/'audit.json')), indent=2))


if __name__ == '__main__':
    main()
