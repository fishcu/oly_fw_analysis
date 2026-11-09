#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Bounded native probes for a highlight-protected PEN-F vignette.

No camera access or firmware export. Produces analysis data, not a patch.
Buffer service, dimensions and job submission are explicit fixture models;
native descriptor bookkeeping, callbacks, tone selection and uploads execute.
MMIO captures bytes only and does not simulate hardware pixel arithmetic.
"""
import argparse
from itertools import product
import json
import math
from pathlib import Path
import struct

from penf_emulator import BASE, ENGINE, Region, firmware
from penf_probe import ProbeState, CALLER
from penf_diagnostic_lifetime_probe import helpers
from penf_hsl_context_probe import (
    build, finished, reenter, LOCKS, CACHE, FLAGS, CONTEXT, REQUEST, OUTPUT,
)
from penf_repack_preflight import sha

JOB, REQUEST_FIXTURE = 0x19000000, 0x19010000
SLOTS, STRIDE = 6068, 88
SIZE_QUERY, SERVICE, SUBMIT = 0x604c4474, 0x604b31a2, 0x604d5f4d
MASK, COMBINE = 0x604c81db, 0x604c82eb
TABLE, OVERRIDE = 0x19080000, 0x19081000


def word(s, at):
    return struct.unpack('<I', s.read(at, 4))[0]


def descriptor(data):
    return dict(pointer=hex(struct.unpack_from('<I', data)[0]),
                format=hex(struct.unpack_from('<H', data, 8)[0]),
                pitch=struct.unpack_from('<H', data, 10)[0],
                dimensions=list(struct.unpack_from('<2H', data, 12)))


class AllocationProbe:
    def __init__(self, dimensions, failure=None, occupied=0):
        self.dimensions, self.failure = dimensions, failure
        self.calls, self.submissions, self.live = [], [], {}
        self.s = ProbeState(MASK, 0, 0, bytes(16), dict(a0=JOB))
        data = bytearray(0x4000)
        # Sentinel source descriptor: destination allocation must not overwrite it.
        data[36:100] = bytes(range(64))
        for i in range(occupied):
            struct.pack_into('<I', data, SLOTS+STRIDE*i+64, 0x30000000+i*0x1000)
            struct.pack_into('<I', data, SLOTS+STRIDE*i+76, 0x5000+i)
        self.source = bytes(data[36:100])
        self.s.ram('job', JOB, data, aliases=False)
        self.s.ram('request', REQUEST_FIXTURE, bytes(1132), aliases=False)
        self.s.regions.append(Region('cpu0', 0x8050, bytes(4), 'r'))
        helpers(self.s)

    def run(self, target, mask=0, frame=0, registers=None):
        s = self.s
        reenter(s, target, mask, frame, registers or dict(a0=JOB))
        start = s.steps
        for _ in range(12):
            result = s.run({CALLER+7, SIZE_QUERY, SERVICE, SUBMIT}, limit=50000)
            pc = s.regs['pc']
            if result['status'] != 'breakpoint' or pc == CALLER+7:
                break
            if pc == SIZE_QUERY:
                assert s.regs['a0'] == JOB+4
                for ptr, value in zip((s.regs['a1'], s.regs['d0']), self.dimensions):
                    s.write(ptr, struct.pack('<H', value))
                self.calls.append(dict(model='size query', dimensions=self.dimensions))
                s.return_from_model(0 if self.failure == 'size' else 1)
            elif pc == SERVICE:
                assert s.regs['a0'] == JOB+4
                operation, slot = s.regs['d0'], s.regs['a1']
                assert (slot-JOB-SLOTS) % STRIDE == 0
                assert 0 <= (slot-JOB-SLOTS)//STRIDE < 64
                if operation == 18:
                    size, tag = word(s, slot+72), word(s, slot+76)
                    pointer = 0 if self.failure == 'allocate' else 0x30000000+len(self.calls)*0x4000000
                    if pointer:
                        self.live[slot] = pointer
                    s.write(slot+64, struct.pack('<I', pointer))
                    self.calls.append(dict(model='allocate', slot=hex(slot), bytes=size,
                                           tag=hex(tag), pointer=hex(pointer)))
                    s.return_from_model(int(bool(pointer)))
                elif operation == 19:
                    assert self.live.pop(slot) == word(s, slot+64)
                    self.calls.append(dict(model='release', slot=hex(slot)))
                    s.return_from_model(1)
                else:
                    raise AssertionError(('unmodeled service', operation))
            else:
                assert s.regs['a0'] == JOB
                # Native call allocated 16 bytes; these were caller stack +4,+8.
                wrapper = word(s, s.regs['sp']+20)
                callback = word(s, s.regs['sp']+24)
                compact = s.read(word(s, wrapper), 56)
                self.submissions.append(dict(callback=hex(callback),
                    descriptor=descriptor(compact), descriptor_hex=compact.hex(),
                    wrapper_flags=list(s.read(wrapper+4, 2)),
                    d0=s.regs['d0'], d1=s.regs['d1']))
                # Synthetic completion token; no image or callback executes here.
                s.write(s.regs['a1'], struct.pack('<I', 0x12340000+len(self.submissions)))
                s.return_from_model(0)
        finished(s, result)
        assert s.read(JOB+36, 64) == self.source
        return dict(result=hex(s.regs['d0']), instructions=s.steps-start,
                    original_descriptor_unchanged=True)

    def callback(self, index, kind=0):
        s = self.s
        data = bytearray(1132)
        data[16] = kind
        s.write(REQUEST_FIXTURE, data)
        callback = int(self.submissions[index]['callback'], 16)
        row = self.run(callback, registers=dict(a0=JOB, a1=REQUEST_FIXTURE))
        row.update(kind=kind, stage=hex(struct.unpack('<H', s.read(REQUEST_FIXTURE+12, 2))[0]))
        if callback == 0x604c8428 and kind == 0:
            slot = next(at for at in self.live if word(s, at+76) == 0x10a0)
            assert s.read(REQUEST_FIXTURE+404, 64) == s.read(slot, 64)
            row['mask_descriptor_exact'] = True
        else:
            assert s.read(REQUEST_FIXTURE+404, 64) == bytes(64)
        return row


def allocation_cases():
    rows = []
    for dims in ((5184, 3888), (1280, 720)):
        p = AllocationProbe(dims, occupied=2)
        mask = p.run(MASK)
        assert mask['result'] == '0x0' and len(p.submissions) == 1
        callbacks = [p.callback(0, kind) for kind in (0, 3)]
        combine = p.run(COMBINE)
        assert combine['result'] == '0x0' and len(p.submissions) == 2
        callbacks += [p.callback(1, kind) for kind in (0, 3)]
        allocations = [r for r in p.calls if r['model'] == 'allocate']
        assert [r['bytes'] for r in allocations] == [
            dims[0]*((dims[1]+63)&~63), 2*dims[1]*((dims[0]+31)&~31)]
        assert [r['tag'] for r in allocations] == ['0x10a0', '0x1000']
        # Exercise the release API explicitly; this does not prove its scheduling.
        for slot in list(p.live):
            p.run(0x604be8a2, 0x30, 12,
                  dict(a0=JOB, d0=(slot-JOB-SLOTS)//STRIDE))
            assert p.s.read(slot, 84) == bytes(84)
        assert not p.live
        rows.append(dict(dimensions=dims, mask=mask, combine=combine,
                         callbacks=callbacks, modeled=p.calls, submissions=p.submissions,
                         explicit_release_api_passed=True))
    failures = []
    for name, options, entry, expected in (
        ('size unavailable', dict(failure='size'), MASK, 0x9ec1),
        ('allocation unavailable', dict(failure='allocate'), MASK, 0x9ec3),
        ('all 64 slots occupied', dict(occupied=64), MASK, 0x9ec3),
        ('no preceding mask', {}, COMBINE, 0x9ece),
    ):
        p = AllocationProbe((5184, 3888), **options)
        row = p.run(entry)
        assert int(row['result'], 16) == expected and not p.submissions
        failures.append(dict(case=name, **row, no_job_submitted=True))
    return dict(success=rows, failures=failures,
        limits='Only outer stage builders and callbacks; dimension query, allocation '
               'service and submission modeled. No scheduler or pixel job executed. '
               'Explicit release API test does not prove automatic cleanup or lifetime. '
               'Descriptor formats 0x03a4/0x0302 are recorded, not decoded as pixel layouts.')


def rational_table(midpoint=0.8):
    k = (midpoint/(1-midpoint))**2
    def h(y):
        return y*y/(y*y+k*(1-y)**2)
    # Desktop tone interpolation uses knots at 0,4,...,1020; clamp last 4 codes.
    knots = [round(1023*h(4*i/1023)) for i in range(256)]
    interpolated = []
    for y in range(1024):
        i, fraction = divmod(y, 4)
        value = knots[i] if i == 255 else knots[i]+((fraction*(knots[i+1]-knots[i])+2)>>2)
        interpolated.append(value)
    errors = [abs(v/1023-h(y/1023)) for y,v in enumerate(interpolated)]
    assert knots[0] == 0 and knots[-1] == 1023
    assert all(a <= b for a,b in zip(knots, knots[1:]))
    return struct.pack('<256H', *knots), dict(midpoint=midpoint, k=k,
        entries=256, element='little-endian u16', output_range=[0, 1023],
        input_knots='0,4,...,1020 of 10-bit Y; last knot holds through 1023',
        max_normalized_error=max(errors), max_error_in_8bit_levels=max(errors)*255,
        domain='Already tone-mapped Y. Not a drop-in replacement for grain mask RAW tone.',
        interpolation='Desktop tone model; camera interpolation not pixel-verified')


def tone_cases(table):
    rows = []
    for mode in (11, 12):
        for bank in (0, 1):
            _, _, s, _ = build(firmware(), mode=mode)
            before = s.read(REQUEST, 1132)
            request = bytearray(before)
            struct.pack_into('<H', request, 12, 0x900)
            struct.pack_into('<I', request, 948, 0)
            struct.pack_into('<I', request, 960, OVERRIDE)
            s.write(REQUEST, request)
            s.ram('custom_tone', TABLE, table, aliases=False)
            s.ram('tone_override', OVERRIDE, struct.pack('<3I', 0, 0, TABLE), aliases=False)
            reenter(s, 0x604f7c76, 0xf0, 28, dict(a0=CONTEXT))
            finished(s, s.run({CALLER+7}, limit=20000))
            assert word(s, OUTPUT+0x1230) == TABLE
            assert s.read(REQUEST, 1132) == request
            coeff, lut = ((0x9e001800,0x9e00a400),(0x9e005800,0x9e00cc00))[bank]
            s.write(CONTEXT+52, struct.pack('<I', 17))
            s.write(CONTEXT+189, bytes([bank]))
            s.ram('flags', FLAGS, struct.pack('<2I', 8 if bank == 0 else 0x10000, 0), aliases=False)
            s.ram('cache', CACHE, bytes(8))
            s.ram('coeff_mmio', coeff, b'\xa5'*0x500, aliases=False)
            s.ram('lut_mmio', lut, b'\xa5'*0x2800, aliases=False)
            reenter(s, 0x604b4933, 0xf0, 24, dict(a0=CONTEXT))
            modeled = []
            for _ in range(8):
                result = s.run({CALLER+7, *LOCKS}, limit=200000)
                if result['status'] != 'breakpoint' or s.regs['pc'] == CALLER+7:
                    break
                assert s.regs['pc'] in LOCKS and s.regs['d0'] == 4
                modeled.append(LOCKS[s.regs['pc']])
                s.return_from_model(0)
            finished(s, result)
            expected = struct.pack('<256I', *struct.unpack('<256H', table))
            assert s.read(lut, 1024) == expected
            assert s.read(TABLE, 512) == table
            assert s.read(REQUEST, 1132) == request
            rows.append(dict(mode=mode, stage='0x900', bank=bank,
                request_override_offset='0x3c0', override_table_pointer_offset=8,
                table_pointer=hex(TABLE), destination=hex(lut), exact_upload=True,
                table_and_request_unchanged=True, instructions=s.steps, modeled=modeled))
    return rows


def blend_data():
    """Keep stock black/white ICM blocks; change spatial input for mask building.

    These are data for planning a new job sequence, not a claim that the stock
    job already takes these inputs. No unverified register fields are changed.
    """
    from penf_grain_probe import fixture, complete, upload, Q, O, ICM
    blocks, rows = {}, []
    for name, level in (('stock-black', -5), ('stock-white', 5)):
        s, _ = fixture(0x604ea2ba, 0xf0, 20, 11, 0)
        s.write(Q+0x441, struct.pack('b', level))
        s.write(Q+0x444, struct.pack('<H', 0x0c00))
        complete(s)
        block = s.read(O+ICM, 164)
        blocks[name+'.icm-u32le'] = block
        for bank in (0, 1):
            row = upload(s, block, bank)
            row['config_112_register'] = row.pop('gain_register')
            row['config_112_word'] = row.pop('gain')
            rows.append(dict(name=name, **row))
    stock = firmware()
    radial = struct.unpack_from('<64h', stock, 0x605fc340-BASE)
    assert all(0 <= x <= 1024 for x in radial)
    inverted = [1024-x for x in radial]
    blocks['inverse-radial-curve.i16le'] = struct.pack('<64h', *inverted)
    return blocks, dict(register_uploads=rows,
        stock_radial_address='0x605fc340', inverse_radial=list(inverted),
        proposed_sequence=[
            'Make h(Y) from finished Y in a separate mask buffer; input route unresolved.',
            'Stock white blend: source A=h(Y), retained weight=1-g, target=white; output G.',
            'Stock black blend: source A=original color, retained weight=G; output final image.',
        ],
        identity='h*(1-g)+g = g+(1-g)*h',
        limits='Stock register bytes and their uploads verified. New source routing, '
               'full-frame mask format, radial interpolation/rounding, and scheduling '
               'are not established. Inverting a radial LUT is only a data candidate; '
               'its complete mask generation is not executed here.')


def strength_data():
    from penf_shading_probe import amount, probe, coordinate_probe, TABLE as LEVEL_TABLE
    selection_path = Path('analysis/shading/selected-tuning.json')
    selection = json.loads(selection_path.read_text())
    values = [6,12,18,24,30]
    assert selection['levels'] == values and selection['midpoint'] == 0.8
    assert selection['protection'] == selection['power'] == 1
    amounts = [amount(v) for v in values]
    assert amounts == [412,567,721,876,1024]
    words = [round(math.sqrt(1024*a)) for a in amounts]
    stock = firmware()
    changed = bytearray(stock)
    struct.pack_into('<5H', changed, LEVEL_TABLE-BASE, *words)
    changed = bytes(changed)
    cases = [probe(changed, words, lev, kind)
             for kind in (0, 3) for lev in (*range(-5,0), *range(1,6))]
    coordinates = [coordinate_probe(1048576//w, 4096, 4096) for w in words]
    return struct.pack('<5H', *words), dict(selection_sha256=sha(selection_path.read_bytes()),
        workspace_values=[-v for v in values], workspace_amounts=amounts,
        camera_coordinate_words=words, table_address=hex(LEVEL_TABLE),
        implied_workspace_amounts=[1024*(1024/(1048576//w))**2 for w in words],
        native_request_cases=cases, native_coordinate_cases=coordinates,
        limits='First-order coordinate match, not an exact camera/desktop pixel match. '
               'In-memory table counterfactual only; no firmware image saved.')


def pipeline_cases(grain_levels=(0,), modes=(11, 12)):
    """Select native jobs with explicit grain levels, independently of MONO key.

    Job +36 contains the processing parameters; grain +0x1641 therefore lives
    at job +0x1665, beside shading +0x1666. Mode keys are supplied fixtures,
    not inferred from the grain setting or a live camera's front dial.
    """
    rows = []
    for mode, grain in product(modes, grain_levels):
        for alternate in (0, 1):
            for enabled in (False, True):
                for level in (-5, 5):
                    context = bytearray(0x4000)
                    struct.pack_into('<I', context, 12192, mode)
                    struct.pack_into('<I', context, 16, 0x80000 if enabled else 0)
                    context[12204] = alternate
                    context[0x1665] = grain
                    context[0x1666] = level & 255
                    s = ProbeState(0x604c542d, 0xf0, 36, bytes(16), dict(a0=JOB))
                    s.ram('job', JOB, context, aliases=False)
                    finished(s, s.run({CALLER+7}, limit=20000))
                    count = struct.unpack('<H', s.read(JOB+12198, 2))[0]
                    entries = [list(struct.unpack('<3I', s.read(JOB+11868+12*i, 12)))
                               for i in range(count)]
                    shade = any(0x604c9168 in e or e[0] in (0x604c970c, 0x604c971e)
                                for e in entries)
                    assert shade == enabled
                    if mode == 11:
                        assert entries == [[0x604c4c84, 0x604c9168 if enabled else 0, 0]]
                    if mode == 12 and not alternate:
                        assert entries == [[MASK,0,0], [COMBINE,0,0]]+(
                            [[0x604c971e,0,0]] if enabled else [])
                    rows.append(dict(mode=mode, grain_level=grain,
                        alternate=alternate, shade_flag=enabled,
                        level=level, instructions=s.steps,
                        entries=[list(map(hex,e)) for e in entries], modeled=[]))
    return dict(cases=rows,
        flag='job+16 bit 0x80000; signed level alone does not schedule shading',
        limits='Synthetic job selector inputs; does not prove live-view routing or pixel order '
               'inside the primary processing pass. Upstream flag derivation not traced here.')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        ap.error('Output directory must be new')
    table, table_info = rational_table()
    allocation = allocation_cases()
    tones = tone_cases(table)
    blends, blend_info = blend_data()
    strength, strength_info = strength_data()
    pipelines = pipeline_cases()
    args.out.mkdir(parents=True)
    (args.out/'posttone-protection-m0800.u16le').write_bytes(table)
    (args.out/'candidate-strengths.u16le').write_bytes(strength)
    for name, data in blends.items():
        (args.out/name).write_bytes(data)
    report = dict(firmware_sha256=sha(firmware()), engine_sha256=sha(ENGINE.read_bytes()),
        probe_sha256=sha(Path(__file__).read_bytes()),
        helper_sha256={name:sha((Path(__file__).parent/name).read_bytes()) for name in (
            'penf_grain_probe.py', 'penf_shading_probe.py', 'penf_hsl_context_probe.py',
            'penf_probe.py', 'penf_diagnostic_lifetime_probe.py')},
        protection_table=dict(**table_info, sha256=sha(table)),
        allocation=allocation, tone_override_and_upload=tones,
        combiner_data=blend_info, strength_candidate=strength_info,
        pipeline_selection=pipelines,
        data_files_sha256={p.name:sha(p.read_bytes()) for p in sorted(args.out.iterdir())},
        limits='No patched firmware, hardware pixel execution, complete capture or live-view '
               'validation. Table requires a suitable post-tone Y input route before use.')
    (args.out/'audit.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(out=str(args.out), native_allocation_cases=len(allocation['success']),
        negative_cases=len(allocation['failures']), tone_uploads=len(tones), table_bytes=len(table))))


if __name__ == '__main__':
    main()
