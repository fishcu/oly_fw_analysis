#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Read-only shading investigation; bounded native calls, no flashable output.

The counterfactual changes five table words in host memory only. Synthetic
requests exercise both native callback branches, not a camera or pixel ISP.
"""
import argparse
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import struct

from penf_emulator import BASE, ENGINE, firmware
from penf_probe import ProbeState, CALLER
from penf_hsl_context_probe import finished
from penf_disasm import window, refs, DEFAULT_IMAGE, DEFAULT_OBJDUMP

TABLE = 0x605fc45e
PROFILE = 0x605fc340
ENTRY = 0x604c9168
C, Q, M = 0x19000000, 0x19010000, 0x19020000
STOCK = [928, 952, 976, 1000, 1024]


def amount(v):
    """Workspace export formula, spec/31; not a camera-pixel equivalence claim."""
    v = abs(v)
    assert 1 <= v <= 30
    return STOCK[v - 26] if v >= 26 else int(928 - (26-v) * (928 / 36.0))


def probe(image, table, level, kind):
    job = bytearray(0x4000)
    job[0x1666] = level & 255
    struct.pack_into('<I', job, 0x35b0, M)
    request = bytearray(1200)
    request[16] = kind
    # This indirect callback contains its own movm/sub-sp prologue, so the
    # synthetic call must not save/allocate the same frame a second time.
    s = ProbeState(ENTRY, 0, 0, bytes(16), dict(a0=C, a1=Q))
    s.regions = [replace(r, data=image) if r.name == 'main' else r for r in s.regions]
    s.ram('job', C, job, aliases=False)
    s.ram('request', Q, request, aliases=False)
    descriptor = bytes(range(100))
    s.ram('descriptor', M, descriptor, aliases=False)
    result = s.run({CALLER+7}, limit=10000)
    finished(s, result)
    expected = bytearray(request)
    active = 1 <= abs(level) <= 5
    reciprocal = 1048576 // table[abs(level)-1] if active else 1024
    flag_off, scale_off, level_off, desc_off = (
        (1092, 1096, 1089, 404) if kind == 0 else (576, 600, 581, 148))
    expected[desc_off:desc_off+64] = descriptor[12:76]
    expected[level_off] = level & 255
    struct.pack_into('<H', expected, flag_off, 0x0c00 if active else 0)
    struct.pack_into('<H', expected, scale_off, reciprocal)
    assert s.read(Q, 1200) == expected
    assert s.read(C, len(job)) == job
    return dict(level=level, request_kind=kind, active=active,
                reciprocal=reciprocal, instructions=s.steps, returned=True,
                full_request_matches=True, job_unchanged=True,
                modeled_functions=[])


def coordinate_probe(reciprocal, x, y):
    """Execute only the identified 0x0c00 coordinate-scale block, not its caller."""
    s = ProbeState(ENTRY, 0, 0, bytes(16), dict(a0=x, a1=y))
    s.regs['pc'] = 0x604ad741
    sp = s.regs['sp']
    s.write(sp+36, struct.pack('<H', reciprocal))
    r = s.run({0x604ad760}, limit=100)
    assert r['status'] == 'breakpoint' and s.regs['pc'] == 0x604ad760
    assert s.regs['sp'] == sp
    expected = [(v << 10)//reciprocal for v in (x,y)]
    assert [s.regs['a0'], s.regs['a1']] == expected
    return dict(reciprocal=reciprocal, input_steps=[x,y], output_steps=expected,
                instructions=s.steps, scope='native basic block only')


def blend_probes():
    """Native shading ICM setup/uploads; no image processing is simulated.

    Reuse the grain probe's explicit engine/request fixtures because both
    effects use this builder. Stage is neutral; processing code 0x0c00 selects
    shading through request-kind-specific fields. Only nonzero valid levels
    belong to this active-pass experiment.
    """
    from penf_grain_probe import fixture, complete, upload, Q as request_at, O, ICM

    cases, by_sign = [], {}
    for kind in (0, 3):
        for level in (*range(-5, 0), *range(1, 6)):
            s, _ = fixture(0x604ea2ba, 0xf0, 20, 11, 0)
            s.write(request_at+16, bytes([kind]))
            level_off, code_off = (0x441, 0x444) if kind == 0 else (0x245, 0x240)
            s.write(request_at+level_off, struct.pack('b', level))
            s.write(request_at+code_off, struct.pack('<H', 0x0c00))
            before = s.read(request_at, 1132)
            complete(s)
            assert s.read(request_at, 1132) == before
            block = s.read(O+ICM, 164)
            words = struct.unpack('<41I', block)
            assert words[1] == 0x0eee0012
            assert words[24] == (0x00808000 if level < 0 else 0x008080ff)
            assert words[39] == 3
            sign = -1 if level < 0 else 1
            assert block == by_sign.setdefault(sign, block)
            setup_steps = s.steps
            uploads = []
            for bank in (0, 1):
                row = upload(s, block, bank)
                # The shared uploader's grain field is not a grain gain here.
                row['configuration_112_register'] = row.pop('gain_register')
                row['configuration_112_word'] = row.pop('gain')
                uploads.append(row)
            cases.append(dict(request_kind=kind, level=level,
                              configuration_instructions=setup_steps,
                              words=[hex(w) for w in words],
                              request_unchanged=True, uploads=uploads))
    changed = [i for i, (a,b) in enumerate(zip(by_sign[-1], by_sign[1])) if a != b]
    assert changed == [96]
    return dict(cases=cases, sign_difference_byte_offsets=changed,
                same_block_within_each_sign=True,
                limits='Synthetic COLOR requests; original selector, builder and '
                       'register dispatcher executed. MMIO is captured, not an ISP '
                       'pixel model. No hardware highlight-protection capability '
                       'or real job-buffer routing is established.')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    stock = firmware()
    assert list(struct.unpack_from('<5H', stock, TABLE-BASE)) == STOCK
    assert stock.count(struct.pack('<5H', *STOCK)) == 1
    # Camera scales BOTH coordinates of an existing radial mask. Workspace's
    # amount scales radius squared. This is a first-order geometry match only;
    # hardware resampling/rounding and the 128x128 camera mask remain distinct.
    candidate = [round(math.sqrt(1024*amount(i*i))) for i in range(1, 6)]
    changed = bytearray(stock)
    struct.pack_into('<5H', changed, TABLE-BASE, *candidate)
    changed = bytes(changed)
    levels = [-128, -6, *range(-5, 6), 6, 127]
    cases = {name: [probe(image, table, lev, kind)
                    for kind in (0, 3) for lev in levels]
             for name, image, table in [('stock', stock, STOCK),
                                        ('square_slider_coordinate_match', changed, candidate)]}
    coordinate_cases = [coordinate_probe(1048576//a, x, y)
                        for a in STOCK+candidate for x,y in ((4096,4096),(100,133))]
    sha = lambda b: hashlib.sha256(b).hexdigest()
    report = dict(
        main_sha256=sha(stock), engine_sha256=sha(ENGINE.read_bytes()),
        script_sha256=sha(Path(__file__).read_bytes()),
        table_address=hex(TABLE), table_offset=hex(TABLE-BASE), stock_table=STOCK,
        table_pointer_candidates=[[hex(x) for x in g] for g in refs(stock, TABLE)],
        profile_address=hex(PROFILE), profile=list(struct.unpack_from('<64h', stock, PROFILE-BASE)),
        workspace=[dict(camera_level=c, imported_slider=2*(c+10),
                        imported_export_amount=amount(2*(c+10)),
                        same_coefficient_export_slider=25+c,
                        native_amount=STOCK[c-1],
                        inferred_radial_amount=1024*(1024/(1048576//STOCK[c-1]))**2)
                       for c in range(1, 6)],
        counterfactual=dict(export_values=[1, 4, 9, 16, 25], table=candidate,
                            table_span_bytes=10,
                            changed_bytes=sum(a != b for a,b in zip(stock, changed)),
                            saved_firmware=False), cases=cases,
        coordinate_cases=coordinate_cases, blend=blend_probes(),
        limits='Only callback request construction is executed. No pixel ISP, '
               'live-view coverage, metadata export or recovery is established. '
               'Equal camera/Workspace table words do not prove equal pixels.')
    (args.out/'audit.json').write_text(json.dumps(report, indent=2)+'\n')
    for name, start, end in [
        ('camera-level', ENTRY, 0x604c922e),
        ('radial-builder', 0x604aa00c, 0x604aa2a4),
        ('display-level', 0x602fc73a, 0x602fc80e),
        ('scaler-value', 0x604ec8d1, 0x604ec97b),
        ('coordinate-scaling', 0x604ad69f, 0x604ad7ab),
    ]:
        (args.out/(name+'.asm')).write_text(window(stock, DEFAULT_IMAGE, DEFAULT_OBJDUMP, start, end))
    print(json.dumps(dict(cases=sum(map(len, cases.values())), candidate=candidate,
                          out=str(args.out))))


if __name__ == '__main__':
    main()
