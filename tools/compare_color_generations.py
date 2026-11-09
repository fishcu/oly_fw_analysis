#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Offline, exact-build PEN-F / E-P7 / OM-3 COLOR comparison.

Validates supplied stock files, exports disassembly,
and checks table, gain, call-site, and builder-code correspondences. No device
access, network requests, firmware patches, or claims of bootability.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from oly_container import encode, parse, sha256

ROOT = Path(__file__).resolve().parents[1]
TABLE_BYTES = 3028
TABLE_SHA = 'a33d64bdb78ac41ba24ccbff820380f563211a095ac08a12a7c37a51b5c00531'
MODELS = {
    'PEN-F': dict(
        build='3101', public_version='3.1', base=0x60021020,
        main='analysis/penf_3.1/00_0100_403a0020.decoded.bin',
        main_sha='a2eb1d1f1afe47cce148e9aae0a04dfb82547d9de9437d342e012341140913f4',
        table=0x60622d74, gains=0x6062fef8, builder=(0x604f7272, 0x604f746a),
        selector=(0x604f747f, 0x604f7572), writer=(0x604b5006, 0x604b51de),
        saturation_request_offset=1076, records_offset=676, control_offset=964,
        mmio_bases=[0x9e001800, 0x9e005800], mmio_records_offset=728,
        mmio_control_offset=1016, writer_condition='source control word != 0'),
    'E-P7': dict(
        build='1100', public_version='1.1', base=0x60020020,
        main='analysis/ep7_1100/00_0100_406a0020.decoded.bin',
        main_sha='5dd9af164b4590c7e82f6905c919b3cc450bb58f2d5742ab2a0e3a4eb2e26190',
        source='research/ep7_om3/ep7_catalog/OLY_E_142_1100_0000_0000.BIN',
        source_sha='9d1610124ad98f6edae4540182205f06c9c703d9033ef0c4f19847193f95eaeb',
        model_id='1420', expected_kinds=[0x100, 0x101, 0x106, 0x10e, 0x102],
        table=0x6051de2c, gains=0x60531810, builder=(0x603b0068, 0x603b0247),
        selector=(0x603b0252, 0x603b0345), writer=(0x6034667e, 0x6034677b),
        entry_jump_offset=0xb6, init_offset=0xd9,
        table_instruction=0x603b02d3, builder_call=0x603b02d9,
        saturation_request_offset=1816, records_offset=688, control_offset=976,
        mmio_bases=[0x9f001000, 0x9f805000], mmio_records_offset=752,
        mmio_control_offset=1040, writer_condition='source control word != 0',
        dispatch_windows=[(0x60345f81, 0x60345f94), (0x60345fa0, 0x60345fb6)]),
    'OM-3': dict(
        build='1100', public_version='1.1', base=0x60021020,
        main='analysis/om3_1100/00_0100_50000020.decoded.bin',
        main_sha='5e8d376e9111a44ac0352f26030d7c1b17026d42c45f3600cfa02a0e8c5b7d59',
        source='research/ep7_om3/om3_download/OLY_E_147_1100_0000_0000.BIN',
        source_sha='8c133084414533159f587bf46bfb4152714c4074312a47c8d8503e33d605696d',
        model_id='1470', expected_kinds=[0x100, 0x101, 0x106, 0x10e, 0x102, 0x107],
        table=0x606ba608, gains=0x606d413c, builder=(0x60518381, 0x60518560),
        selector=(0x60518573, 0x6051869e), writer=(0x604a3e73, 0x604a4041),
        entry_jump_offset=0x82, init_offset=0xa5,
        table_instruction=0x6051860a, builder_call=0x60518615,
        saturation_request_offset=1739, records_offset=836, control_offset=1124,
        mmio_bases=[0x9c201000, 0x9c205000], mmio_records_offset=964,
        mmio_control_offset=1252, writer_condition='source word 0 bit 0x01000000 clear',
        dispatch_windows=[(0x604a35cf, 0x604a35e2), (0x604a3817, 0x604a382a)]),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def dump_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def validate_stock(name, cfg, table):
    source = ROOT / cfg['source']
    raw = source.read_bytes()
    require(sha256(raw) == cfg['source_sha'], f'{name}: unexpected stock hash')
    blocks = parse(raw)  # Validates every decoded additive checksum and wrapper.
    require([b.kind for b in blocks] == cfg['expected_kinds'], f'{name}: block kinds')
    require(sha256(blocks[0].payload) == cfg['main_sha'], f'{name}: main block')
    digest = hashlib.sha256()
    for block in blocks:
        encoded = encode(block.payload)
        start = block.offset + 32
        require(encoded == raw[start:start + len(encoded)], f'{name}: roundtrip')
        digest.update(block.header)
        digest.update(encoded)
        digest.update(block.trailer)
    require(digest.hexdigest() == cfg['source_sha'], f'{name}: reconstructed hash')
    occurrences = [b.payload.count(table) for b in blocks]
    require(occurrences == [1] + [0] * (len(blocks) - 1), f'{name}: table occurrences')
    return dict(model=name, model_id=cfg['model_id'], public_version=cfg['public_version'],
        file_build=cfg['build'], original_filename=source.name,
        source=str(source.relative_to(ROOT)), bytes=len(raw), sha256=cfg['source_sha'],
        all_block_checksums_valid=True, exact_payload_roundtrip=True,
        roundtrip_sha256=digest.hexdigest(), table_occurrences_per_block=occurrences,
        blocks=[b.metadata() for b in blocks], camera_accessed=False,
        caveat='File integrity only; no inference about modified-image acceptance or recovery.')



def export_window(name, label, bounds, cfg, data, out, objdump):
    start, stop = bounds
    require(cfg['base'] <= start < stop <= cfg['base'] + len(data), 'window bounds')
    filename = f'{name.lower().replace("-", "")}_{label}.asm'
    command = [str(objdump), '-b', 'binary', '-m', 'mn10300', '-D', '-z',
               '--insn-width=16', f"--adjust-vma={cfg['base']:#x}",
               f'--start-address={start:#x}', f'--stop-address={stop:#x}',
               str(ROOT / cfg['main'])]
    (out / filename).write_text(subprocess.check_output(command, text=True))
    return dict(file=filename, start=hex(start), stop_exclusive=hex(stop),
                bytes=stop-start, sha256=sha256(data[start-cfg['base']:stop-cfg['base']]))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True, help='new evidence directory')
    ap.add_argument('--objdump', type=Path,
                    default=ROOT / 'toolchains/binutils-2.45-build/binutils/objdump')
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    results, builders, reference_gains = {}, {}, None
    for name, cfg in MODELS.items():
        data = (ROOT / cfg['main']).read_bytes()
        require(sha256(data) == cfg['main_sha'], f'{name}: decoded main hash')
        base = cfg['base']
        offset = cfg['table'] - base
        table = data[offset:offset + TABLE_BYTES]
        require(sha256(table) == TABLE_SHA and data.count(table) == 1, f'{name}: COLOR table')
        pointers = struct.unpack_from('<12I', data, cfg['gains'] - base)
        require(all(base <= p <= base + len(data) - 4 for p in pointers), f'{name}: gains bounds')
        gains = [struct.unpack_from('<HH', data, p-base) for p in pointers]
        if reference_gains is None:
            reference_gains = gains
            (args.out / 'shared_color_table.decoded.bin').write_bytes(table)
        require(gains == reference_gains, f'{name}: gain values differ')
        start, stop = cfg['builder']
        builders[name] = data[start-base:stop-base]
        row = dict(build=cfg['build'], public_version=cfg['public_version'],
                   source_main=cfg['main'], source_main_sha256=cfg['main_sha'],
                   analysis_base=hex(base), table_address=hex(cfg['table']),
                   table_offset=hex(offset), table_sha256=TABLE_SHA,
                   gains_pointer_table=hex(cfg['gains']),
                   gain_pointers=[hex(p) for p in pointers], gains_nonnegative_negative=gains)
        for field in ('saturation_request_offset', 'records_offset', 'control_offset',
                      'mmio_records_offset', 'mmio_control_offset', 'writer_condition'):
            row[field] = cfg[field]
        row['mmio_bases'] = [hex(v) for v in cfg['mmio_bases']]
        require(cfg['control_offset'] - cfg['records_offset'] == 288, '12 x 24-byte records')
        require(cfg['mmio_control_offset'] - cfg['mmio_records_offset'] == 288, 'register span')
        windows = {label: cfg[label] for label in ('builder', 'selector', 'writer')}
        if 'source' in cfg:
            row['stock'] = validate_stock(name, cfg, table)
            jump = cfg['entry_jump_offset']
            require(data[jump:jump+2] == b'\xfc\xdc' and data[jump+6:jump+8] == b'\xf0\xf4',
                    f'{name}: absolute entry jump')
            target = struct.unpack_from('<I', data, jump+2)[0]
            require(target - cfg['init_offset'] == base, f'{name}: runtime mapping')
            require(data[cfg['init_offset']] == 0xcf, f'{name}: initialization prologue')
            row['entry_mapping_evidence'] = dict(jump_file_offset=hex(jump),
                target=hex(target), init_file_offset=hex(cfg['init_offset']),
                derived_base=hex(target-cfg['init_offset']))
            literal = cfg['table_instruction'] - base
            require(data[literal:literal+6] == b'\xfc\xdc' + struct.pack('<I', cfg['table']),
                    f'{name}: real table instruction')
            call = cfg['builder_call'] - base
            require(data[call] == 0xcd and cfg['builder_call'] + struct.unpack_from('<h', data, call+1)[0] == start,
                    f'{name}: selector-to-builder call')
            row['table_load_instruction'] = hex(cfg['table_instruction'])
            row['builder_call_instruction'] = hex(cfg['builder_call'])
            windows['entry'] = (base, base + cfg['init_offset'])
            windows.update({f'writer_dispatch_{i}': bounds for i, bounds in enumerate(cfg['dispatch_windows'])})
        row['windows'] = {label: export_window(name, label, bounds, cfg, data, args.out,
                                              args.objdump.resolve()) for label, bounds in windows.items()}
        results[name] = row

    # Only these independently identified address/structure operands may differ.
    spans = [(0x8, 2, 'records offset'), (0x4d, 4, 'gain pointer-table address'),
             (0x172, 2, 'control offset')]
    spans += [(p, 2, 'LUT pointer output-field offset') for p in
              (0x17e, 0x188, 0x192, 0x19c, 0x1a6, 0x1b2, 0x1bc, 0x1c6, 0x1d0, 0x1da)]
    ep, om = builders['E-P7'], builders['OM-3']
    require(len(ep) == len(om) == 479, 'builder lengths')
    changes = [i for i, (a, b) in enumerate(zip(ep, om)) if a != b]
    allowed = {i for start, length, _ in spans for i in range(start, start+length)}
    require(len(changes) == 27 and set(changes) <= allowed, 'unexpected builder-code changes')
    masked_ep, masked_om = bytearray(ep), bytearray(om)
    operands = []
    for start, length, meaning in spans:
        operands.append(dict(offset=hex(start), bytes=length, meaning=meaning,
            ep7=int.from_bytes(ep[start:start+length], 'little'),
            om3=int.from_bytes(om[start:start+length], 'little')))
        masked_ep[start:start+length] = masked_om[start:start+length] = bytes(length)
    require(masked_ep == masked_om, 'masked builder comparison')
    with (args.out / 'sector_gains.csv').open('w', newline='') as output:
        writer = csv.writer(output)
        writer.writerow(['table_record', 'UI_array_index', 'nonnegative_gain', 'negative_gain',
                         'source_hue_i16', 'source_sat_amplitude_i16', 'source_lightness_i16'])
        for record, gains in enumerate(reference_gains):
            writer.writerow([record, 2*(record % 6) + record//6, *gains,
                             *struct.unpack_from('<hhh', table, record*28+12)])
    report = dict(scope='Offline stock-file and static-code comparison; no camera execution.',
        shared_color_table_bytes=TABLE_BYTES, shared_color_table_sha256=TABLE_SHA,
        all_tables_and_gains_equal=True, models=results,
        ep7_om3_builder_comparison=dict(bytes=479, differing_bytes=27,
            differing_offsets=[hex(i) for i in changes], operand_changes=operands,
            equal_after_masking_only_listed_operands=True, masked_sha256=sha256(masked_ep)),
        limitations=[
            'No camera execution or pixel-output equality test.',
            'Saturation arithmetic interpretation retains the prior MN103 multiply-opcode caveat.',
            'H/L fields are forwarded; no H/L UI arrays or universal allowed ranges established.',
            'OM-3 register-copy enable-bit lifecycle is not fully traced.',
            'Newer firmware acceptance, boot integrity, and recovery are not mapped by this audit.'])
    dump_json(args.out / 'comparison.json', report)
    print(json.dumps(dict(report=str(args.out / 'comparison.json'),
        shared_table_sha256=TABLE_SHA, validated_stock_blocks=11,
        exported_windows=sum(len(r['windows']) for r in results.values()),
        builder_bytes=479, differing_bytes=27), indent=2))


if __name__ == '__main__':
    main()
