#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native settings schema/export/reset/envelope probes; no camera or patch.

The RAM fixtures model initialized arrays. The envelope load reads a supplied
RAM backing buffer, not physical flash. Unknown accesses/instructions stop.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import struct

from oly_container import parse
from penf_emulator import BASE, ENGINE, firmware
from penf_probe import ProbeState, CALLER, BUFFER, RESULT
from penf_diagnostic_lifetime_probe import parser_state
from penf_color_controls_probe import ACTIVE, LIVE, BANKS, WORDS, until, returned
from penf_code_space_reference_audit import containing_asset
from penf_disasm import DEFAULT_IMAGE, DEFAULT_OBJDUMP, window, refs

PACKAGE = Path('firmware_files/OLY_E_122_3101_0000_0000.BIN')
PACKAGE_SHA = '77398610b379f80238117f31a6d5bbf65d608b49ec563666c64d84367e969f2c'
CHECKPOINT = Path('analysis/application_boot/camera-units-final/run/state.json.gz')
COLOR = range(931, 967)
STRIDE = WORDS*8
OUTPUT, SCRATCH, BACKING = 0x19000000, 0x19100000, 0x69200000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def resource():
    raw = PACKAGE.read_bytes()
    assert sha(raw) == PACKAGE_SHA
    block = next(x for x in parse(raw) if x.kind == 0x106)
    row, path = containing_asset(block, 20710368)
    assert path == [6, 0] and row['end']-row['start'] == 272896
    return block.payload[row['start']:row['end']], dict(
        package=str(PACKAGE), package_sha256=sha(raw), component='0106',
        resource_path=path, logical_address=hex(block.address+32+row['start']),
        component_payload_offset=row['start'])


def schema(raw):
    n, offset, enums, enum_offset, flags, flag_offset, unknown = struct.unpack_from('<7I', raw)
    assert (n, enums, flags) == (1116, 3301, 1792)
    flagmap = dict((key, flag) for key, flag, _ in
                   struct.iter_unpack('<HBB', raw[flag_offset:flag_offset+flags*4]))
    rows = []
    for i in range(n):
        start = offset+72*i
        key, kind = struct.unpack_from('<HB', raw, start)
        name = raw[start+4:start+56].split(b'\0')[0].decode('ascii')
        enum_start, enum_count = struct.unpack_from('<IH', raw, start+56)
        values = []
        if kind == 1:
            for j in range(enum_count):
                a = enum_offset+enum_start+j*56
                value = struct.unpack_from('<i', raw, a)[0]
                label = raw[a+4:a+56].split(b'\0')[0].decode('ascii')
                values.append(dict(value=value, label=label))
        rows.append(dict(id=key, kind=kind, name=name, backup_flag=flagmap.get(key),
                         values=values))
    for row in rows:
        if row['id'] in COLOR:
            assert row['backup_flag'] == 1
            assert [v['value'] for v in row['values']] == list(range(-5, 6))
    return dict(resource_sha256=sha(raw), header=list(struct.unpack_from('<7I', raw)),
                parameters=rows)


def fixture(raw, target, mask, frame, registers, part1=0xface0000):
    b = firmware()
    s = ProbeState(target, mask, frame, bytes(256), registers)
    s.register(0x8050, 'r', 0)
    s.ram('bank_pointers_fixture', 0x61896ed4, struct.pack('<3I', BANKS, ACTIVE, LIVE))
    defaults = b[0x603c8bb0-BASE:0x603c8bb0-BASE+WORDS*4]
    bank = defaults+struct.pack('<1274I', *[part1 | i for i in range(WORDS)])
    s.ram('banks_fixture', BANKS, bank*9)
    s.ram('active_fixture', ACTIVE, bank)
    s.ram('live_fixture', LIVE, defaults)
    s.ram('native_initialized_runtime', 0x615fc540,
          b[0x601ea800-BASE:0x601ea800-BASE+133664])
    s.write(0x615fd4e0, struct.pack('<I', SCRATCH))
    s.ram('myset_schema_resource', 0xad92cd00, raw)
    s.ram('scratch_fixture', SCRATCH, bytes(2048), aliases=False)
    s.ram('export_output', OUTPUT, bytes(65536), aliases=False)
    parser_state(s)
    return s


def export(raw, bank, witness, saturation=None):
    s = fixture(raw, 0x602c1950, 0xf0, 80,
                dict(d0=1 << (bank-1), d1=2, a0=BUFFER, a1=RESULT), witness)
    s.write(BUFFER, struct.pack('<II', OUTPUT, 65536))
    s.write(0x18018004, bytes(4))
    if saturation is not None:
        s.write(BANKS+bank*STRIDE+931*4, struct.pack('<i', saturation))
    until(s, {CALLER+7}, limit=35000000)
    returned(s)
    assert s.regs['d0'] == 0
    n = struct.unpack('<I', s.read(RESULT, 4))[0]
    output = s.read(OUTPUT, n)
    assert len([l for l in output.splitlines() if b'MODE_COLOR_CREATOR_2_VIVID_SET' in l]) == 36
    return output, dict(bank=bank, witness=hex(witness), saturation_override=saturation,
                       instructions=s.steps, bytes=n, sha256=sha(output), modeled_functions=[])


def parse_line(raw, line, expected):
    data = line.encode('ascii')+b'\r\n'
    s = fixture(raw, 0x602c215a, 0xf0, 60,
                dict(d0=len(data), a0=BUFFER, a1=RESULT, d1=RESULT+4))
    s.write(BUFFER, data+b'\0')
    s.write(RESULT, b'\xcc'*8)
    until(s, {CALLER+7}, limit=3000000)
    returned(s)
    if expected is None:
        assert s.regs['d0'] == 1 and s.read(RESULT, 8) == b'\xcc'*8
    else:
        assert s.regs['d0'] == 0
        assert (struct.unpack('<H', s.read(RESULT, 2))[0],
                struct.unpack('<i', s.read(RESULT+4, 4))[0]) == expected
    return dict(line=line, returned=s.regs['d0'], expected=expected,
                instructions=s.steps, modeled_functions=[])


def reset(raw):
    s = fixture(raw, 0x602c6125, 0xf0, 20, {})
    before = s.read(ACTIVE, STRIDE)
    until(s, {CALLER+7}, limit=3000000)
    returned(s)
    defaults = firmware()[0x603c8bb0-BASE:0x603c8bb0-BASE+WORDS*4]
    values = []
    for key in COLOR:
        expected = defaults[key*4:key*4+4]
        assert s.read(ACTIVE+(WORDS+key)*4, 4) == expected
        values.append(struct.unpack('<i', expected)[0])
    assert any(values)
    return dict(entry='0x602c6125', instructions=s.steps, part1_color_defaults=values,
                before_sha256=sha(before), after_sha256=sha(s.read(ACTIVE, STRIDE)),
                modeled_functions=[])


def restore_commit(raw, bank):
    """Run native trailer save; model the two outer mode/flag services only."""
    s = fixture(raw, 0x602c27da, 0xc0, 12, dict(d0=bank))
    active = s.read(ACTIVE, STRIDE)
    s.write(LIVE+931*4, struct.pack('<i', -5))
    modeled = []
    while True:
        pc = until(s, {CALLER+7, 0x602f024a, 0x602f0832}, limit=10000000)
        if pc == CALLER+7:
            break
        if pc == 0x602f024a:
            assert s.regs['d0'] in (26, 109)
            value = {26: 4, 109: 0}[s.regs['d0']]  # A/submode 0
            modeled.append(dict(entry=hex(pc), id=s.regs['d0'], supplied=value))
            s.return_from_model(value)
        else:
            assert (s.regs['d0'], s.regs['d1']) == (1499+bank, 1)
            modeled.append(dict(entry=hex(pc), id=s.regs['d0'], value=1))
            s.return_from_model(0)
    returned(s)
    saved = s.read(BANKS+bank*STRIDE, STRIDE)
    assert struct.unpack_from('<i', saved, 931*4)[0] == -5
    for key in COLOR:
        off = (WORDS+key)*4
        assert saved[off:off+4] == active[off:off+4]
    return dict(bank=bank, instructions=s.steps, mode=4, submode=0,
                part0_color_id931=-5, destination_part1_color_preserved=True,
                modeled_functions=modeled,
                scope='Restore trailer only, supplied live edits and loaded active bank; not full restore')


def checkpoint_bytes(address, size):
    data = json.loads(gzip.decompress(CHECKPOINT.read_bytes()))
    for row in data['regions']:
        start = int(row['address'], 0) if isinstance(row['address'], str) else row['address']
        if row.get('hex') and start <= address and address+size <= start+row['size']:
            return bytes.fromhex(row['hex'])[address-start:address-start+size]
    raise ValueError(f'Checkpoint range not found: {address:x}+{size:x}')


def storage_inventory():
    b = firmware()
    filters = []
    for i in range(54):
        mode, submode, ptr, count, _ = struct.unpack_from('<HHIHH', b, 0x603c891c-BASE+i*12)
        rows = list(struct.iter_unpack('<HBB', b[ptr-BASE:ptr-BASE+count*4]))
        assert sorted(r for r in rows if r[0] in COLOR) == [(k, 0, 0) for k in COLOR]
        filters.append(dict(mode=mode, submode=submode, second_part_ids=[k for k, part, _ in rows if part == 1],
                            all_COLOR_in_part0=True))
    records = []
    for key, default_address, elements, pointer in (
        (0x85d4, 0x6010cd00, 22950, BANKS),
        (0x8b54, 0x60123558, 1275, LIVE),
        (0x8b64, 0x60124948, 2550, ACTIVE),
    ):
        assert struct.unpack_from('<HH', b, default_address-BASE) == (key, elements)
        desc_address = 0x61c281e4+(key >> 4)*8
        assert struct.unpack('<HHI', checkpoint_bytes(desc_address, 8)) == (key, elements, pointer)
        records.append(dict(key=hex(key), default_address=hex(default_address),
                            descriptor=hex(desc_address), elements=elements, pointer=hex(pointer)))
    candidates = {}
    for address in (0x602f06b6, 0x602f06e7, 0x602f0710):
        pointers, calls = refs(b, address)
        candidates[hex(address)] = dict(raw_pointer_candidates=list(map(hex, pointers)),
                                        raw_direct_call_candidates=list(map(hex, calls)))
    return dict(filters=filters, records=records, references=candidates,
                limit='Raw references are candidates, not an exhaustive computed-access analysis.')


def envelope():
    working, length = 0x61b7bac0, 0x20000
    blob = bytearray(checkpoint_bytes(working, length))
    offset = BANKS+STRIDE+(WORDS+931)*4-working
    witness = bytes(range(144))
    blob[offset:offset+144] = witness
    assert struct.unpack_from('<H', blob)[0] == 0x54
    s = ProbeState(0x60073540, 0x20, 8, bytes(16), dict(d0=length, a0=BACKING))
    s.ram('envelope_fixture', BACKING, blob)
    until(s, {CALLER+7}, limit=1000000)
    returned(s)
    checked = s.read(BACKING, length)
    assert sum(struct.unpack('<65536H', checked)) & 65535 == 0
    cases = []
    for corrupt in (False, True):
        content = bytearray(checked)
        if corrupt:
            content[offset] ^= 1
        # Invalid selectors in the outer loader cause a speculative object-table
        # read before its error check. Test rejection at the validator itself;
        # do not silently map an oversized synthetic object to hide that access.
        entry = 0x600734e3 if corrupt else 0x6007333e
        regs = dict(a0=BACKING, d0=length, d1=0x54) if corrupt else dict(a0=BUFFER)
        s = ProbeState(entry, 0xf0 if corrupt else 0xb0, 20, bytes(32), regs)
        s.register(0x8050, 'r', 0)
        # Native diagnostic logger's documented suppress bit; no function stub.
        s.ram('diagnostic_suppression', 0x6181e3c0, struct.pack('<H', 2))
        s.ram('backing_buffer_fixture', BACKING, content)
        s.ram('working_buffer_fixture', working, bytes([0xa5])*length)
        s.write(BUFFER, struct.pack('<7I', 0x54, BACKING, 0, 0x6010c444, working, length, 1))
        until(s, {CALLER+7}, limit=2000000)
        returned(s)
        assert s.regs['d0'] == int(corrupt)
        if corrupt:
            assert s.read(working, length) == bytes([0xa5])*length
        else:
            assert s.read(working, length) == checked
        cases.append(dict(corrupt=corrupt, entry=hex(entry), returned=s.regs['d0'], instructions=s.steps,
                          modeled_functions=[], witness_preserved=not corrupt))
    return dict(source_checkpoint=str(CHECKPOINT), checkpoint_sha256=sha(CHECKPOINT.read_bytes()),
                bytes=length, source_modified_at=offset, witness_bytes=144,
                checksum=struct.unpack_from('<H', checked, 2)[0], cases=cases,
                scope='Native checksum plus backing-buffer validate/load; no physical persistence')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    raw, provenance = resource()
    schemas = schema(raw)
    inventory = storage_inventory()
    (a.out/'schema.json').write_text(json.dumps(dict(**provenance, **schemas), indent=2)+'\n')
    print('Resource recovered and schema checked.', flush=True)
    reset_case = reset(raw)
    envelope_case = envelope()
    print('Native reset and checksum/backing-buffer cases passed.', flush=True)
    commit_cases = [restore_commit(raw, bank) for bank in (1, 5)]
    rows = [r for r in schemas['parameters'] if r['id'] in COLOR]
    parser_cases = [parse_line(raw, f"2,{r['name']},MODE_STEP_P5", (r['id'], 5)) for r in rows]
    parser_cases += [parse_line(raw, f"2,{rows[0]['name']},{value}", None)
                     for value in ('MODE_STEP_P7', 'MODE_STEP_M7', '7', '-7')]
    print('Restore trailer and 40 native line-parser cases passed.', flush=True)
    outputs, exports = [], []
    for bank, marker, saturation in ((1, 0xface0000, None), (1, 0xbeef0000, None),
                                     (1, 0xface0000, 5), (5, 0xface0000, None)):
        out, case = export(raw, bank, marker, saturation)
        outputs.append(out)
        exports.append(case)
        print(f'Native export bank {bank}, marker {marker:x}, saturation {saturation}: {len(out)} bytes.', flush=True)
    assert outputs[0] == outputs[1]
    expected = outputs[0].replace(b'2,MODE_COLOR_CREATOR_2_VIVID_SET1_1,MODE_STEP_0\r\n',
                                  b'2,MODE_COLOR_CREATOR_2_VIVID_SET1_1,MODE_STEP_P5\r\n')
    assert outputs[2] == expected and outputs[2] != outputs[0]
    (a.out/'synthetic-bank1-export.txt').write_bytes(outputs[0])
    report = dict(main_sha256=sha(firmware()), engine_sha256=sha(ENGINE.read_bytes()),
                  tool_sha256=sha(Path(__file__).read_bytes()), resource=provenance,
                  inventory=inventory, reset=reset_case, envelope=envelope_case, restore_trailer=commit_cases,
                  line_parser=parser_cases, exports=exports,
                  part1_only_changes_leave_export_identical=True,
                  part0_sensitivity_control=True,
                  limitations=['Synthetic RAM fixtures, not a camera test.',
                    'No nonvolatile write, power cycle, full restore or physical USB session.',
                    'No proof of all indirect/direct computed consumers or paired-bank lifetime.',
                    'The exported text is synthetic test output, not a camera settings file.'])
    (a.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    for name, start, end in (
        ('custom-bank-export', 0x602c1950, 0x602c1aab),
        ('restore', 0x602c1d6b, 0x602c2300),
        ('restore-trailer', 0x602c27da, 0x602c2865),
        ('custom-default-reset', 0x602c6125, 0x602c615c),
        ('mode-filtered-copies', 0x602c5d4a, 0x602c615c),
        ('custom-bank-mode-readers', 0x602bd611, 0x602bd731),
        ('custom-bank-mode-readers-2', 0x602bda17, 0x602bdaa5),
        ('store-envelope', 0x60073172, 0x60073630),
    ):
        (a.out/(name+'.asm')).write_text(window(firmware(), DEFAULT_IMAGE, DEFAULT_OBJDUMP, start, end))
    print('All checks passed. No firmware, camera settings or flash output generated.')


if __name__ == '__main__':
    main()
