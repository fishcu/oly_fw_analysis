#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Pinned, offline preset/startup/flash evidence. Never creates an update file.

This exports decoded source bytes and selected, instruction-aligned disassembly.
It checks static relationships, not hardware execution or recovery safety.
"""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess

from oly_container import parse, sha256
from penf_disasm import DEFAULT_IMAGE, DEFAULT_OBJDUMP
from penf_landmarks import BASE, MAIN_SHA256


PENF_WINDOWS = {
    'main_entry_excerpt': (0x60021020, 0x60021111),
    'startup_init': (0x60041ae3, 0x60041d9a),
    'startup_start': (0x60041d9a, 0x6004204b),
    'section_loader': (0x60042063, 0x6004228a),
    'cross_cpu_submit': (0x600700a8, 0x600701d1),
    'cross_cpu_interrupt_request': (0x6006fcd2, 0x6006fdb4),
    'cross_cpu_receiver_example': (0x6006fdb4, 0x6006fe08),
    'power_init': (0x6007d1c2, 0x6007d371),
    'power_scratch_access': (0x6007d97b, 0x6007d9a5),
    'flash_guard_mode': (0x6013004c, 0x6013005e),
    'flash_guard': (0x6013005e, 0x601301c3),
    'section_flash_io_dispatch': (0x600720e1, 0x600721aa),
    'flash_read_backend': (0x601301c3, 0x6013024b),
    'flash_read_wrapper': (0x600711a1, 0x600711d3),
    'ustart1_section2': (0x601a70cc, 0x601a7144),
    'ustart1_section3_excerpt': (0x601a72ee, 0x601a731c),
    'ustart3_wait_excerpt': (0x601a7644, 0x601a76d0),
    'ustart4_sections4_to8': (0x601a7ed1, 0x601a8019),
    'erase_then_write': (0x60071267, 0x600712c0),
    'erase_wrapper': (0x60022402, 0x600224c2),
    'erase_blocks': (0x60022029, 0x6002209c),
    'nand_status_poll': (0x600220ad, 0x600220f5),
    'controller_status_poll': (0x600220f5, 0x6002213b),
    'program_pages': (0x60021e3e, 0x60021f42),
    'program_alignment_and_error_return': (0x60071d3a, 0x60071edb),
    'update_backend_excerpt': (0x60130365, 0x6013038c),
    'update_backend_return': (0x60130446, 0x60130465),
    'update_block_writer': (0x60b1e119, 0x60b1e178),
    'update_descriptor_accessors_and_parser': (0x60187f64, 0x60187fd2),
    'main_update_request_excerpt': (0x60b1dfb3, 0x60b1dff6),
    'sd_client': (0x60b1cbb5, 0x60b1ce0c),
    'preset_selector': (0x604f6a2e, 0x604f6d67),
    'direct_table_builder': (0x604f6d67, 0x604f6f12),
    'ordinary_builder': (0x604f6f12, 0x604f7272),
    'color_builder': (0x604f7272, 0x604f746a),
    'table_dispatch': (0x604f747f, 0x604f7572),
    'alternate_table_dispatch': (0x604f7572, 0x604f75e5),
    'custom_pointer_request_origin_excerpt': (0x604c3051, 0x604c3090),
    'alternate_request_packer': (0x604c34ee, 0x604c359b),
    'alternate_pipeline': (0x604f860e, 0x604f86a1),
}

SOURCES = {
    'penf3100': ('firmware_archive/stock/OLY_E_122_3100_0000_0000.BIN', BASE,
                 '3d5963c6d9385aafc99ff51892ec706bef1c4783a84f586179271a64b8401bfd'),
    'em5_1500': ('firmware_archive/reference/E-M5/1.5/OLY_E_097_1500_0000_0000.BIN',
                 0x7e421020, '10e69c8de7028ac48de7481dae61d92aa7a0b926439f24b934143dcc0383f657'),
    'em1ii3001': ('e-m1_hack/original_fw/3.0/OLY_E_125_3001_0000_0000.BIN', BASE,
                  '9c0d32363caafd5c77ef1828cf6fdbdee222f1e199719fdafd224862d0670cd7'),
    'em1ii3200': ('e-m1_hack/original_fw/3.2/OLY_E_125_3200_0000_0000.BIN', BASE,
                  '3ed0f000012cc86b9123955730a4d9aaf6be8d8604fc07947093c5d03efa5f11'),
}


def disassemble(path, base, start, stop):
    return subprocess.check_output([
        str(DEFAULT_OBJDUMP.resolve()), '-b', 'binary', '-m', 'mn10300',
        '-D', '-z', '--insn-width=16', f'--adjust-vma={base:#x}',
        f'--start-address={start:#x}', f'--stop-address={stop:#x}', str(path)
    ], text=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', required=True, type=Path)
    args = ap.parse_args()
    if args.out.exists():
        ap.error('output directory must not exist')
    b = DEFAULT_IMAGE.read_bytes()
    assert sha256(b) == MAIN_SHA256
    images = {'penf3101': (DEFAULT_IMAGE, BASE, b)}
    provenance = []
    extra = []
    # Parse all container checksums before creating output.
    for name, (path, base, expected) in SOURCES.items():
        raw = Path(path).read_bytes()
        blocks = parse(raw)
        main_block, = [v for v in blocks if v.kind == 0x100]
        assert sha256(main_block.payload) == expected, name
        images[name] = (args.out / f'{name}.main.bin', base, main_block.payload)
        provenance.append({'name': name, 'container': path, 'container_sha256': sha256(raw),
                           'base': hex(base), 'blocks': [v.metadata() for v in blocks]})
        for v in blocks:
            if (name, v.kind) in [('em5_1500', 0x107), ('em1ii3001', 0x10e)]:
                extra.append((name, v))
    args.out.mkdir(parents=True)
    for name, (path, _, data) in images.items():
        if name != 'penf3101':
            path.write_bytes(data)
    for name, block in extra:
        path = args.out / f'{name}.block{block.kind:04x}.bin'
        path.write_bytes(block.payload)
        images[f'{name}_extra'] = (path, block.address + 32, block.payload)

    windows = []
    assembly = {}

    def emit(image, name, start, stop):
        path, base, data = images[image]
        assert base <= start < stop <= base + len(data)
        asm = disassemble(path, base, start, stop)
        output = args.out / f'{image}.{name}.asm'
        output.write_text(asm)
        assembly[image, name] = asm
        windows.append({'image': image, 'name': name, 'start': hex(start), 'stop': hex(stop),
                        'sha256': sha256(data[start-base:stop-base]), 'file': output.name})

    for name, (start, stop) in PENF_WINDOWS.items():
        emit('penf3101', name, start, stop)
    emit('penf3100', 'ustart3_wait_excerpt', 0x601a7644, 0x601a76d0)
    emit('penf3101', 'ustart1_completion_flag_excerpt', 0x601a74c0, 0x601a755c)
    for image in ['em1ii3001', 'em1ii3200']:
        emit(image, 'sd_client', 0x60cf6125, 0x60cf6329)
        a = 0x6021ac9a if image == 'em1ii3001' else 0x6021ad9a
        emit(image, 'sd_failure_helper', a, a + 0x29)
    emit('em5_1500', 'sd_client', 0x7e622aff, 0x7e622cb9)
    emit('em5_1500', 'sd_failure_helper', 0x7e9d4255, 0x7e9d42a0)
    emit('em5_1500', 'main_entry', 0x7e421020, 0x7e421106)
    emit('em5_1500_extra', 'entry_and_handoff', 0x40060020, 0x40060363)

    def unpack(addr, fmt):
        return struct.unpack_from(fmt, b, addr-BASE)

    defaults = {
        'key1_vivid_associated': [0x6062f6a4, 0x6062f6d8],
        'key2_natural_associated': [0x6062f5d4, 0x6062f608],
        'key2_alternate_42b': [0x6062f63c, 0x6062f670],
        'key3_muted_associated': [0x6062f70c, 0x6062f740],
        'key4_portrait_associated': [0x6062f774, 0x6062f7a8],
    }
    profiles = {}
    all_tables = {0x60622d74, 0x60623948, 0x6061ced4}
    for name, descs in defaults.items():
        rows = []
        for desc in descs:
            v = unpack(desc, '<13I')
            gains = [unpack(p, '<12H') for p in v[1:]]
            assert all(g == (256,) * 12 for g in gains)
            all_tables.add(v[0])
            rows.append({'descriptor': hex(desc), 'source_table': hex(v[0]),
                         'gain_pointers': list(map(hex, v[1:])),
                         'gain_values_by_record': gains})
        profiles[name] = rows
    tables = []
    for address in sorted(all_tables):
        raw = b[address-BASE:address-BASE+3028]
        records = [list(struct.unpack_from('<14h', raw, n*28)) for n in range(12)]
        tables.append({'address': hex(address), 'sha256': sha256(raw),
                       'records_i16': records, 'hsl_native': [r[6:9] for r in records],
                       'control': hex(struct.unpack_from('<H', raw, 3024)[0]),
                       'control_flag': raw[3026]})
    assert [r['source_table'] for r in profiles['key4_portrait_associated']] == [
        r['source_table'] for r in profiles['key2_natural_associated']]

    ends = [0x601cb000, 0x60428000, 0x6069b800, 0x60a50000,
            0x60fdc800, 0x610f2000, 0x61100000, 0x6115b800]
    cores = [0, 0, 1, 1, 1, 1, 2, 1]
    sections = []
    for i, end in enumerate(ends):
        start, flash, destination = unpack(0x60026d7c + 12*i, '<3I')
        assert start == destination
        sections.append({'id': i+1, 'descriptor': hex(0x60026d7c+12*i),
                         'destination': hex(destination), 'end_exclusive': hex(end),
                         'flash_source': hex(flash), 'length': end-start,
                         'requested_cpu': cores[i]})

    # Exact bytes, not a relocation-tolerant similarity claim.
    comparison = []
    older = images['penf3100'][2]
    for name, (start, stop) in PENF_WINDOWS.items():
        x, y = b[start-BASE:stop-BASE], older[start-BASE:stop-BASE]
        comparison.append({'name': name, 'start': hex(start), 'length': len(x),
                           'same_address_identical': x == y,
                           'differing_bytes': sum(i != j for i, j in zip(x, y))})
    for row in tables:
        a = int(row['address'], 16)-BASE
        row['identical_in_3100'] = b[a:a+3028] == older[a:a+3028]

    tasks = []
    for name, addr, wanted in [('penf3101', 0x6003a128, 95),
                               ('em5_1500', 0x7e4e887c, 20),
                               ('em1ii3001', 0x6003969c, 90),
                               ('em1ii3200', 0x6003969c, 90)]:
        _, base, data = images[name]
        v = struct.unpack_from('<7I', data, addr-base)
        assert v[0] == wanted and v[1] == 0
        tasks.append({'image': name, 'descriptor': hex(addr), 'id': v[0],
                      'attributes': v[1], 'entry': hex(v[3]), 'priority': v[4],
                      'stack_size': v[5]})

    def instruction_shape(asm):
        result = []
        for line in asm.splitlines():
            if not re.match(r'^[0-9a-f]+:\s', line):
                continue
            ins = line.split('\t', 2)[-1].strip()
            # Only a structural comparison: strip external call targets and
            # image-address immediates; preserve local branches and other values.
            ins = re.sub(r'^(call\s+)0x[0-9a-f]+', r'\1<target>', ins)
            ins = re.sub(r'(?<![\w])16\d{8}(?=,)', '<image-pointer>', ins)
            result.append(ins)
        return result
    a = assembly['em1ii3001', 'sd_client']
    c = assembly['em1ii3200', 'sd_client']
    shape_equal = instruction_shape(a) == instruction_shape(c)
    assert shape_equal
    assert 'add\t131072,a3' in assembly['penf3101', 'erase_blocks']
    assert 'add\t2048,d0' in assembly['penf3101', 'program_pages']

    report = {
        'main_sha256': MAIN_SHA256, 'hardware_executed': False, 'update_created': False,
        'provenance': provenance, 'windows': windows,
        'ordinary_presets': profiles, 'tables': tables,
        'ordinary_coefficients': 'signed source H/S/L times selected u16 gain, arithmetic >>8; multiplication semantics inferred for udf00 opcodes',
        'ordinary_default_gain': 256,
        'selection_scope': 'Default requests; +0x42f and +0x430 overrides inactive. Names are internal key associations, not a complete menu-to-request trace.',
        'caller_table_pointer_route': {'source_object_offset': 13364,
            'request_offset': 960, 'table_pointer_in_descriptor': 16,
            'dispatch': '0x604f747f', 'builder': '0x604f6d67',
            'upstream_pointer_owner_resolved': False},
        'alternate_route': {'request_flag': 587, 'request_selector': 590,
            'source': '0x60623948', 'control': '0x41 << threshold_index',
            'menu_identity_resolved': False,
            'note': '624-byte packer clears flag +587 and does not set it; a producer for a nonzero value is still missing.'},
        'startup_sections': sections,
        'flash_geometry': {'erase_step_bytes': 131072, 'program_page_bytes': 2048,
            'logical_to_physical_mapper': '0x6002189d',
            'bad_block_handler': '0x600217a6',
            'transactional_rollback_established': False},
        'sd_task_descriptors': tasks,
        'penf_3100_3101_window_comparison': comparison,
        'em1ii_sd_instruction_shape_equal_3001_3200': shape_equal,
        'comparison_limit': 'Instruction-shape equality ignores external call targets and image-pointer immediates; it is not semantic equivalence.',
        'remaining_boundaries': ['Earlier PEN-F reset/BOOT and main-image acceptance',
            'Physical SD-trigger activation and its service dependencies',
            'Complete USB event delivery to component commit',
            'Bad-block-map persistence, power-loss behavior, and every writer dependency residency',
            'Live capture/RAW selection and final pixels for fixed H/L values'],
    }
    (args.out/'audit.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'report': str(args.out/'audit.json'), 'windows': len(windows),
                      'penf_identical_windows': sum(r['same_address_identical'] for r in comparison),
                      'penf_compared_windows': len(comparison), 'tables': len(tables)}, indent=2))


if __name__ == '__main__':
    main()
