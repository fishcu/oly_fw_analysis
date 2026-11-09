#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Execute stock PEN-F sharpness configuration and capture its register uploads.

Synthetic requests, original CPU instructions, write-capture MMIO. Does not
emulate ISP pixels, contact a camera, modify firmware, or produce a flash image.
"""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import struct

from penf_emulator import BASE, ENGINE, firmware
from penf_probe import ProbeState, CALLER
from penf_hsl_context_probe import finished, reenter
from penf_disasm import window, DEFAULT_IMAGE, DEFAULT_OBJDUMP

MAIN_SHA = 'a2eb1d1f1afe47cce148e9aae0a04dfb82547d9de9437d342e012341140913f4'
C, Q, O = 0x19000000, 0x19001000, 0x19003000
YC = O + 0x20c


def sha(data):
    return hashlib.sha256(data).hexdigest()


def complete(s):
    finished(s, s.run({CALLER + 7}, limit=20000))


def configure(mode, sharpness, sv, stage, image=None):
    context = bytearray(192)
    struct.pack_into('<3I', context, 4, Q, O, YC)
    struct.pack_into('<I', context, 48, mode)
    struct.pack_into('<I', context, 56, 0xffffffff)
    request = bytearray(1132)
    struct.pack_into('<HH', request, 10, mode, stage)
    struct.pack_into('<H', request, 28, 0x200)
    struct.pack_into('<H', request, 0x40e, sv)
    struct.pack_into('<b', request, 0x422, sharpness)
    s = ProbeState(0x604f3ba1, 0xf0, 24, bytes(16), dict(a0=C))
    if image is not None:
        s.regions = [replace(r, data=image) if r.name == 'main' else r
                     for r in s.regions]
    s.ram('context', C, context, aliases=False)
    s.ram('request', Q, request, aliases=False)
    s.ram('configuration', O, bytes(8192), aliases=False)
    complete(s)
    assert s.read(Q, len(request)) == request
    block = s.read(YC, 0x500)
    return s, block, dict(mode_key=mode, sharpness=sharpness, sv_raw=sv,
        stage=hex(stage), instructions=s.steps, request_unchanged=True,
        control_bytes=list(block[12:15]),
        adjacent_u16=list(struct.unpack_from('<2H', block, 16)),
        configuration_sha256=sha(block))


def upload(s, block, bank):
    # Direct original writer; bank choice is supplied here, not a full ISP job.
    address = [0x9e001800, 0x9e005800][bank]
    s.ram(f'yc_registers_{bank}', address, b'\xa5' * 0x1000, aliases=False)
    before = s.steps
    reenter(s, 0x604b5006, 0xf0, 24, dict(a0=address, a1=YC))
    complete(s)
    registers = s.read(address, 0x1000)
    assert registers[0x34:0xbc] == block[:136]
    assert registers[0x40:0x48] == block[0xc:0x14]
    assert s.read(YC, len(block)) == block
    return dict(bank=bank, base=hex(address), instructions=s.steps-before,
        native_writer=True, native_dispatch=False, exact_initial_34_words=True,
        control_register=hex(address+0x40),
        control_word=hex(struct.unpack_from('<I', registers, 0x40)[0]),
        adjacent_register=hex(address+0x44),
        adjacent_word=hex(struct.unpack_from('<I', registers, 0x44)[0]))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--check-zero-gain', action='store_true',
                    help='Also test a table-entry counterfactual in host memory only')
    ap.add_argument('--check-coring', action='store_true',
                    help='Test constant coring curves in host memory, never emit a BIN')
    args = ap.parse_args()
    data = firmware()
    assert sha(data) == MAIN_SHA
    args.out.mkdir(parents=True, exist_ok=False)
    cases = []
    for mode in (1, 2, 3, 4, 11, 12):
        for sv in (1280, 2560, 3840):
            for sharpness in range(-2, 3):
                s, block, row = configure(mode, sharpness, sv, 0)
                row['uploads'] = [upload(s, block, bank) for bank in (0, 1)]
                cases.append(row)
    # Explicit processing-stage suppression, not a simulated boot condition.
    suppressed = []
    for stage in (0x9000, 0xa000):
        s, block, row = configure(11, 0, 1280, stage)
        assert block[12:20] == bytes(8)
        suppressed.append(row)
    zero_experiment = None
    if args.check_zero_gain:
        # Index 3 is selected by COLOR's baseline 5 plus user sharpness -2
        # in this fixture. This is not a globally exclusive COLOR setting.
        address = 0x60619ae4
        offset = address - BASE
        assert data[offset:offset+2] == b'\xa0\x00'
        altered = bytearray(data)
        altered[offset] = 0
        altered = bytes(altered)
        zero_cases = []
        for sv in (1280, 2560, 3840):
            for sharpness in range(-2, 3):
                _, stock, _ = configure(11, sharpness, sv, 0)
                s, changed, row = configure(11, sharpness, sv, 0, altered)
                if sharpness == -2:
                    expected = bytearray(stock)
                    expected[14] = 0
                    assert changed == expected and stock[14] != 0
                else:
                    assert changed == stock
                row['only_expected_gain_change'] = True
                row['uploads'] = [upload(s, changed, bank) for bank in (0,1)]
                zero_cases.append(row)
        zero_experiment = dict(address=hex(address), before='a0', after='00',
            changed_decoded_bytes=1, cases=zero_cases,
            scope='Main altered in host memory only, never saved. Shared table '
                  'entry; may affect other modes/settings. This proves zero '
                  'reaches the register, not that all JPEG sharpening is off.')
    coring_experiments = []
    if args.check_coring:
        address = 0x606199a6
        offset = address - BASE
        original = data[offset:offset+12]
        assert original == bytes([7,7,8,8,9,12,14,18,23,35,45,60])
        for value in (0,32):
            altered = bytearray(data)
            altered[offset:offset+12] = bytes([value])*12
            altered = bytes(altered)
            rows = []
            for mode in (2,11):
                for sv in (1280,1966,2560):
                    for sharpness in (-2,0):
                        _, stock, _ = configure(mode,sharpness,sv,0)
                        s, changed, row = configure(mode,sharpness,sv,0,altered)
                        expected = bytearray(stock)
                        expected[13] = value
                        assert changed == expected
                        row['only_expected_coring_change'] = True
                        row['uploads'] = [upload(s,changed,bank) for bank in (0,1)]
                        rows.append(row)
            coring_experiments.append(dict(address=hex(address),
                original=list(original), constant=value, changed_decoded_bytes=12,
                cases=rows, scope='Shared default curve only; other selector branches '
                'may use different curves. Register writes verified, ISP pixels not modeled.'))
    report = dict(main_sha256=sha(data), engine_sha256=sha(ENGINE.read_bytes()),
        probe_sha256=sha(Path(__file__).read_bytes()),
        default_baseline=list(data[0x60619ad2-BASE:0x60619ad8-BASE]),
        alternate_baseline=list(data[0x60619ad8-BASE:0x60619ade-BASE]),
        strength_lut=list(struct.unpack_from('<11H', data, 0x60619ade-BASE)),
        cases=cases, suppressed_stage_cases=suppressed,
        zero_gain_experiment=zero_experiment,
        coring_experiments=coring_experiments,
        limits='Synthetic engine context, zero unspecified request fields; '
               'Sv values are raw test inputs, not calibrated ISO labels. '
               'The original writer is called directly at both known banks. '
               'No full capture, ISP pixel execution, boot or recovery test. '
               'Equal control words do not prove equal final JPEGs.')
    (args.out/'audit.json').write_text(json.dumps(report, indent=2)+'\n')
    for name, bounds in {
        'request-packer': (0x604c3051, 0x604c3300),
        'sharpness-selector': (0x604f3405, 0x604f3ba1),
        'sharpness-builder': (0x604f3ba1, 0x604f3e5d),
        'register-writer': (0x604b5006, 0x604b5250),
        'register-dispatch': (0x604b4933, 0x604b4b14),
    }.items():
        (args.out/(name+'.asm')).write_text(window(data, DEFAULT_IMAGE,
            DEFAULT_OBJDUMP, *bounds))
    print(json.dumps(dict(configurations=len(cases), register_uploads=2*len(cases),
                          suppressed_stages=len(suppressed), out=str(args.out))))


if __name__ == '__main__':
    main()
