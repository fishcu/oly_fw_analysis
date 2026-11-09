#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Bounded PEN-F grain configuration probes; no pixels, camera I/O or BIN export.

Original MN103 instructions configure synthetic requests and write to captured
MMIO. One explicitly labelled counterfactual changes a selector comparison in
host memory only. It is not a proposed complete firmware patch.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import struct

from penf_emulator import BASE, ROOT, ENGINE, firmware
from penf_probe import ProbeState, CALLER, RESULT
from penf_hsl_context_probe import finished, reenter
from penf_disasm import window, DEFAULT_IMAGE, DEFAULT_OBJDUMP
from penf_repack_preflight import sha

C, Q, O, M = 0x19000000, 0x19001000, 0x19003000, 0x19007000
ICM = 0x17a8
GAINS = {0x901: [0, 110, 300, 600], 0x902: [0, 50, 75, 100]}


def fixture(target, mask, frame, mode, stage, level=3, image=None):
    context = bytearray(192)
    struct.pack_into('<3I', context, 4, Q, O, O + 0x20c)
    struct.pack_into('<I', context, 48, mode)
    struct.pack_into('<I', context, 56, 0xffffffff)
    request = bytearray(1132)
    struct.pack_into('<HH', request, 10, mode, stage)
    struct.pack_into('<H', request, 28, 0x200)
    request[0x440] = level
    # Minimal source descriptor: its first sample supplies the 0x901 seed.
    # This is not an image or a recovered real capture descriptor.
    struct.pack_into('<I', request, 212, M)
    s = ProbeState(target, mask, frame, bytes(16), dict(a0=C))
    if image is not None:
        s.regions = [replace(r, data=image) if r.name == 'main' else r
                     for r in s.regions]
    s.ram('context', C, context, aliases=False)
    s.ram('request', Q, request, aliases=False)
    s.ram('configuration', O, bytes(8192), aliases=False)
    s.ram('seed_sample', M, struct.pack('<H', 0x1234), aliases=False)
    s.ram('alternative_seed_counter', 0xa1c63108, bytes(4))
    return s, bytes(request)


def complete(s):
    result = s.run({CALLER + 7}, limit=20000)
    finished(s, result)


def configure(mode, stage, level, image=None):
    s, request = fixture(0x604ea2ba, 0xf0, 20, mode, stage, level, image)
    complete(s)
    assert s.read(Q, len(request)) == request
    block = s.read(O + ICM, 164)
    row = dict(mode=mode, stage=hex(stage), level=level,
               counterfactual=image is not None, instructions=s.steps,
               gain=struct.unpack_from('<I', block, 112)[0],
               seed=hex(struct.unpack_from('<I', block, 148)[0]),
               words=[hex(x) for x in struct.unpack('<41I', block)],
               sha256=sha(block), request_unchanged=True)
    return s, block, row


def upload(s, block, bank):
    address = (0x9e000800, 0x9e004800)[bank]
    hardware_flag = (0x200, 0x400000)[bank]
    s.write(O, struct.pack('<I', hardware_flag))
    s.ram(f'icm_mmio_{bank}', address, b'\xa5' * 0x100, aliases=False)
    before = s.steps
    # Execute the original register dispatcher as well as its ICM writer.
    reenter(s, 0x604b4933, 0xf0, 24, dict(a0=C))
    complete(s)
    actual = s.read(address, 0x100)
    expected = bytearray(b'\xa5' * 0x100)
    expected[12:16] = block[:4]
    expected[0x38:0xd8] = block[4:164]
    assert actual == expected
    assert actual[0xa4:0xa8] == block[112:116]
    return dict(bank=bank, base=hex(address), instructions=s.steps-before,
                hardware_flag=hex(hardware_flag), native_dispatch=True,
                gain_register=hex(address+0xa4),
                gain=struct.unpack_from('<I', actual, 0xa4)[0],
                exact_register_copy=True, sha256=sha(actual))


def tone(mode, stage):
    s, _ = fixture(0x604f75e5, 0xf0, 24, mode, stage)
    s.regs.update(a0=Q, a1=RESULT)
    complete(s)
    address = s.regs['a0']
    return dict(mode=mode, stage=hex(stage), pointer=hex(address),
                sha256=sha(s.read(address, 512)), instructions=s.steps)


def chroma(mode, stage):
    s, _ = fixture(0x604f83f1, 0xb0, 20, mode, stage)
    complete(s)
    value = struct.unpack('<I', s.read(O+0x20c+0x4c, 4))[0]
    assert value == (0 if mode == 11 else 0x808001)
    return dict(mode=mode, stage=hex(stage), control=hex(value),
                instructions=s.steps)


def pipeline(mode, alternate, format_bits):
    context = bytearray(0x4000)
    struct.pack_into('<I', context, 12192, mode)
    context[12204] = alternate
    struct.pack_into('<H', context, 20, format_bits)
    s = ProbeState(0x604c542d, 0xf0, 36, bytes(16), dict(a0=C))
    s.ram('pipeline_context', C, context, aliases=False)
    complete(s)
    count = struct.unpack('<H', s.read(C+12198, 2))[0]
    assert 0 < count <= 20
    entries = [list(map(hex, struct.unpack('<3I', s.read(C+11868+12*i, 12))))
               for i in range(count)]
    if mode == 12 and format_bits == 0:
        expected = ([['0x604c4c84', '0x604c8471', '0x0']] if alternate else
                    [['0x604c81db', '0x0', '0x0'], ['0x604c82eb', '0x0', '0x0']])
    else:
        expected = [['0x604c4c84', '0x0', '0x0']]
    assert entries == expected
    return dict(mode=mode, alternate=alternate, format_bits=hex(format_bits),
                count=count, entries=entries, instructions=s.steps)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', required=True, type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    stock = firmware()
    workspace = ROOT/'analysis/color_grain/measurements.json'
    measured = json.loads(workspace.read_text())
    lut = stock[0x60610742-BASE:0x60610942-BASE]
    assert sha(lut) == measured['mask_lut_sha256']
    assert stock.count(lut) == 1
    gains = struct.pack('<3H', 110, 300, 600)
    assert stock[0x605fc452-BASE:0x605fc458-BASE] == gains
    assert stock.count(gains) == 1

    # Isolate ONLY the ICM selector. This changes its accepted key from MONO
    # to COLOR, not all pipeline gates. Never save this image to a file.
    modified = bytearray(stock)
    at = 0x604fb880-BASE
    assert modified[at:at+2] == b'\xa0\x0c'
    modified[at+1] = 11
    modified = bytes(modified)
    cases, uploads = [], []
    for stage in (0x901, 0x902):
        for level in (0, 1, 2, 3, 4, 255):
            s, native, row = configure(12, stage, level)
            assert row['gain'] == (GAINS[stage][level] if level <= 3 else 0)
            cases.append(row)
            for bank in (0, 1):
                uploads.append(dict(stage=hex(stage), level=level,
                                    **upload(s, native, bank)))
            _, normal, row = configure(11, stage, level)
            cases.append(row)
            _, enabled, row = configure(11, stage, level, modified)
            assert enabled == native and enabled != normal
            row['equals_stock_mono_configuration'] = True
            cases.append(row)
    tones = [tone(mode, stage) for mode in (11, 12) for stage in (0, 0x900, 0x901)]
    assert [r['pointer'] == '0x60610742' for r in tones] == [False]*4+[True,False]
    chromas = [chroma(mode, stage) for mode in (11, 12) for stage in (0, 0x900, 0x901)]
    pipelines = [pipeline(mode, alternate, bits) for mode in (11, 12)
                 for alternate in (0, 1) for bits in (0, 0x10, 0x100)]
    report = dict(source_sha256=sha(stock), engine_sha256=sha(ENGINE.read_bytes()),
        probe_sha256=sha(Path(__file__).read_bytes()),
        workspace_measurement_sha256=sha(workspace.read_bytes()),
        mask_lut_address='0x60610742', mask_lut_sha256=sha(lut),
        mask_lut_exact_match=True, gain_table_address='0x605fc452',
        counterfactual=dict(address='0x604fb881', old=12, new=11,
            scope='ICM selector only; host memory; NOT a complete patch; no BIN saved'),
        configurations=cases, register_uploads=uploads, tone_selection=tones,
        chroma_control=chromas, pipeline_selection=pipelines,
        limits='Synthetic independent stage calls. Native register writes captured as '
               'memory. No pixel engine, image-buffer execution, complete capture, '
               'interrupt timing, live view or camera recovery validation.')
    (args.out/'audit.json').write_text(json.dumps(report, indent=2)+'\n')
    windows = {
        'icm-selector': (0x604fb7b8, 0x604fba1e),
        'icm-builder': (0x604ea2ba, 0x604eac40),
        'icm-register-writer': (0x604b5644, 0x604b5662),
        'register-dispatch': (0x604b4933, 0x604b4b14),
        'mask-selector': (0x604f75e5, 0x604f7b58),
        'chroma-controls': (0x604f82c2, 0x604f8461),
        'pipeline-selector': (0x604c542d, 0x604c630e),
        'mask-grain-allocation': (0x604c81db, 0x604c8482),
    }
    for name, (start, stop) in windows.items():
        (args.out/(name+'.asm')).write_text(window(stock, DEFAULT_IMAGE,
                                                  DEFAULT_OBJDUMP, start, stop))
    print(json.dumps(dict(configurations=len(cases), uploads=len(uploads),
        tone_cases=len(tones), chroma_cases=len(chromas), pipelines=len(pipelines),
        mask_exact=True, out=str(args.out))))


if __name__ == '__main__':
    main()
