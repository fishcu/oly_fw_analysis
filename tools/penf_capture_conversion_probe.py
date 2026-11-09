#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Complete native capture-to-processing conversion and COLOR copy lifetime.

Uses the stock descriptor +124 capture pointer, stock table initialization,
complete converter, request packer and coefficient selector. Pixel-buffer
metadata and outer job header remain explicit fixtures. No ISP submission,
physical exposure, new H/L storage or firmware modification.
"""
import argparse
import json
from pathlib import Path
import struct
import sys

from penf_image_ownership_probe import (
    Harness, Fixture, word, invoke, returned, CAPTURE_BYTES, BASE, CALLER,
    CHECKPOINT_SHA, DEFAULT_IMAGE, DEFAULT_OBJDUMP, ENGINE, sha, window,
)

DESCRIPTOR = 0x27000000
GEOMETRY = (0, 0, 5184, 3888)


def populate(h, index, address):
    r = h.populate(index)
    # The partial-boot/default-exposure capture has zero geometry here.
    # Supply an explicit full-frame crop fixture, rather than letting the
    # converter's divisions run with zero denominators. Its real producer
    # is outside this bounded capture-population function.
    assert h.s.read(address+21942, 8) == bytes(8)
    h.s.write(address+21942, struct.pack('<4H', *GEOMETRY))
    return dict(native_population=r, supplied_capture_geometry=list(GEOMETRY),
                offset=21942, producer_not_replayed=True)


def prepare(h):
    s, f = h.s, h.f
    s.ram('captured_iseq_debug_policy', 0x618b5108, f.read(0x618b5108, 4))
    s.ram('native_iseq_history', 0x61c67324, bytes([h.fill])*1208)
    log = invoke(s, 0x6051886e, 0, 4); returned(s, log)
    s.ram('native_conversion_configuration', 0x61c67be8, bytes([h.fill])*26)
    s.ram('native_conversion_configuration_copy', 0x618b5144, bytes([h.fill])*10)
    config = invoke(s, 0x60522730, 0x80, 4); returned(s, config)

    # Three groups of fourteen record pairs supply the 3x112-byte table.
    # The following 32 bytes are written by the same native initializer.
    # Map only declared record extents absent from the existing fixture.
    keys = set(struct.unpack_from('<84H', f.image, 0x6033025e-BASE))
    keys |= {0xcd82, 0x8042, 0x8052, 0x8062}
    records = []
    for key in sorted(keys):
        actual, count, ptr = struct.unpack('<HHI', f.read(0x61c281e4+(key >> 4)*8, 8))
        size = count*(key & 7)
        assert actual == key and (key & 7) in (1, 2, 4)
        try:
            s.read(ptr, size)
        except ValueError:
            s.ram('conversion_record_'+hex(key), ptr, f.read(ptr, size))
            records.append(dict(key=hex(key), address=hex(ptr), bytes=size))
    s.ram('native_conversion_table', 0xa1c5854c, bytes([h.fill])*368)
    table = invoke(s, 0x6023463e, 0xf0, 32); returned(s, table)
    s.ram('outer_descriptor376', DESCRIPTOR, bytes(376), aliases=False)
    return dict(history=log, configuration=config, table_initializer=table,
                table_sha256=sha(s.read(0xa1c5854c, 368)), additional_records=records)


def convert(h, index, expected, ordinal):
    s = h.s
    base = 0x28000000+ordinal*0x10000
    job = base
    # The enclosing job (including optional pointer fields after +6068) is
    # an explicit empty fixture. Poison only the converter-owned output.
    s.ram('complete_job_'+str(ordinal), job, bytes(14000), aliases=False)
    s.write(job+36, bytes([h.fill])*6032)
    # Both stock callers zero 376 bytes, set descriptor+8=5 and write the
    # capture pointer at +124. Pixel-buffer fields are omitted in this
    # bounded fixture: the native COLOR path does not dereference them.
    s.write(DESCRIPTOR, bytes(376))
    access = invoke(s, 0x60521f80, 0xe0, 16, dict(d0=index, a0=DESCRIPTOR+124))
    returned(s, access)
    capture = word(s, DESCRIPTOR+124)
    assert capture != 0
    s.write(DESCRIPTOR+8, b'\x05')
    # The enclosing processing-job header is still supplied. Its mode byte
    # comes from the actual native capture, rather than a literal COLOR ID.
    s.write(job, bytes(36))
    s.write(job+14, s.read(capture+18595, 1))
    before = s.read(capture, CAPTURE_BYTES)
    r = invoke(s, 0x6052010f, 0xf0, 48, dict(a0=job+36, a1=DESCRIPTOR, d0=0))
    returned(s, r)
    assert r['result'] == 0
    assert s.read(capture, CAPTURE_BYTES) == before
    assert struct.unpack('<4H', s.read(capture+21942, 8)) == GEOMETRY
    assert struct.unpack('<4H', s.read(job+36+5808, 8)) == (0, 5183, 0, 3887)
    assert struct.unpack('<12b', s.read(job+36+5684, 12)) == tuple(expected)
    return job, dict(slot=index, capture=hex(capture), job=hex(job), accessor=access,
                     full_converter=r, values=expected,
                     parameter_sha256=sha(s.read(job+36, 6032)))


def pack(h, job, expected):
    s, f = h.s, h.f
    request, context, output = job+0x4000, job+0x5000, job+0x6000
    for name, address, size in (('request', request, 1132), ('context', context, 192),
                                ('coefficients', output, 5632)):
        s.ram(name+'_'+hex(job), address, bytes(size), aliases=False)
    packed = invoke(s, 0x604c3051, 0xf0, 28, dict(a0=job, a1=request, d0=0))
    returned(s, packed)
    assert struct.unpack('<12b', s.read(request+1076, 12)) == tuple(expected)
    s.write(context+4, struct.pack('<4I', request, 0, output, output+5212))
    s.write(context+56, struct.pack('<I', 0xffffffff))
    s.write(context+100, struct.pack('<I', 0xffffffff))
    built = invoke(s, 0x604f747f, 0xf0, 20, dict(a0=context)); returned(s, built)
    assert word(s, output+0x3c4) == 0xfff
    pointers = struct.unpack_from('<12I', f.image, 0x6062fef8-BASE)
    coefficients = []
    for sector, value in enumerate(expected):
        record = (sector % 2)*6+sector//2
        source = 0x60622d74+record*28-BASE
        amplitude = struct.unpack_from('<h', f.image, source+14)[0]
        gain = struct.unpack_from('<H', f.image, pointers[record]-BASE+2*(value < 0))[0]
        numerator = ((amplitude*gain) >> 8)*value
        expected_s = (1 if numerator >= 0 else -1)*(abs(numerator)//5)
        actual = struct.unpack('<3h', s.read(output+0x2a4+record*24+18, 6))
        assert actual == (0, expected_s, 0)
        coefficients.append(dict(sector=sector, H=actual[0], S=actual[1], L=actual[2]))
    return dict(packer=packed, HSL_selector=built, coefficients=coefficients,
                coefficient_sha256=sha(s.read(output+0x2a4, 292)), neutral_HL_stock=True)


def lifetime(f, profile, fill):
    h = Harness(f, profile, fill); s = h.s
    h.refresh(profile)
    preparation = prepare(h)
    before = h.values()
    ia, a, allocation_a = h.allocate(); population_a = populate(h, ia, a)
    sector = (1, 6, 12)[profile-1]-1
    edit = h.edit(931+12*(profile-1)+sector, 5 if before[sector] != 5 else -5)
    after = h.values()
    assert after != before and h.capture_values(a) == before
    ib, b, allocation_b = h.allocate(); population_b = populate(h, ib, b)
    assert a != b and h.capture_values(b) == after
    ja, converted_a = convert(h, ia, before, 0)
    jb, converted_b = convert(h, ib, after, 1)
    held_a, held_b = s.read(ja, 14000), s.read(jb, 14000)
    switch = h.edit(910, 53+(profile % 3+1))
    next_values = h.values()
    released = h.release(ia)
    ic, c, allocation_c = h.allocate()
    assert (ic, c) == (ia, a)
    assert h.capture_values(c) == before  # release does not erase storage
    population_c = populate(h, ic, c)
    assert h.capture_values(c) == next_values
    jc, converted_c = convert(h, ic, next_values, 2)
    assert s.read(ja, 14000) == held_a and s.read(jb, 14000) == held_b
    # Crucially, pack A only AFTER its source slot has been released and
    # overwritten. The full converter has already made the owned value copy.
    packed_a, packed_b, packed_c = (pack(h, j, v) for j, v in
                                   ((ja, before), (jb, after), (jc, next_values)))
    assert h.capture_values(b) == after
    h.release(ib); h.release(ic)
    return dict(kind='complete_conversion_lifetime', profile=profile, fill=hex(fill),
                preparation=preparation, allocations=[allocation_a, allocation_b, allocation_c],
                populations=[population_a, population_b, population_c],
                edit=edit, profile_switch=switch, release_A=released,
                conversions=[converted_a, converted_b, converted_c],
                packed_after_source_reuse=[packed_a, packed_b, packed_c],
                converted_jobs_survive_source_reuse=True)


def missing_capture(f, fill):
    h = Harness(f, 1, fill); s = h.s
    h.refresh(1); prepare(h)
    index, _, _ = h.allocate(); h.populate(index); h.release(index)
    access = invoke(s, 0x60521f80, 0xe0, 16, dict(d0=index, a0=DESCRIPTOR+124))
    returned(s, access)
    assert word(s, DESCRIPTOR+124) == 0 and access['result'] != 0
    output = 0x28000000
    s.ram('invalid_conversion_destination', output, bytes([fill])*6032, aliases=False)
    r = invoke(s, 0x6052010f, 0xf0, 48, dict(a0=output, a1=DESCRIPTOR, d0=0))
    assert (r['status'], r['pc'], r['fault']['address']) == ('memory_fault', '0x60521914', 0x1314)
    return dict(kind='released_capture_rejected_then_null_fault', fill=hex(fill), accessor=access,
                deliberately_ignored_accessor_error=True,
                execution={k: v for k, v in r.items() if k not in ('trace_tail', 'stop_registers')})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--quick', action='store_true')
    args = parser.parse_args(); args.out.mkdir(parents=True, exist_ok=False)
    f = Fixture(); cases = []
    for fill in ((0xa5,) if args.quick else (0, 0xa5)):
        for profile in ((1,) if args.quick else (1, 2, 3)):
            cases.append(lifetime(f, profile, fill))
            print(f'COLOR{profile}, fill {fill:#x}: full converter and delayed packing passed', flush=True)
        cases.append(missing_capture(f, fill))
        print(f'Fill {fill:#x}: released-capture error and strict null control passed', flush=True)
    spans = {
        'first-caller-descriptor': (0x6051c5cc, 0x6051c7a3),
        'second-caller-descriptor': (0x6051d310, 0x6051d4ef),
        'capture-accessor': (0x60521f80, 0x60521fc2),
        'complete-converter': (0x6052010f, 0x605206a7),
        'conversion-table-selector': (0x602335fd, 0x60233615),
        'conversion-table-initializer': (0x6023463e, 0x60234777),
    }
    folder = args.out/'disassembly'; folder.mkdir()
    for name, (lo, hi) in spans.items():
        (folder/(name+'.asm')).write_text(window(f.image, DEFAULT_IMAGE, DEFAULT_OBJDUMP, lo, hi))
    root = Path.cwd(); sources = {Path(__file__).resolve()}
    for module in list(sys.modules.values()):
        file = getattr(module, '__file__', None)
        if file and Path(file).resolve().is_relative_to(root/'tools'):
            sources.add(Path(file).resolve())
    report = dict(main_sha256=sha(f.image), checkpoint_sha256=CHECKPOINT_SHA,
        engine_sha256=sha(ENGINE.read_bytes()),
        source_sha256={str(p.relative_to(root)): sha(p.read_bytes()) for p in sorted(sources)},
        cases=cases, spans={k: list(map(hex, v)) for k, v in spans.items()},
        limits=[
            'Full native converter with descriptor+124 derived by slot accessor; callers supplying that field are statically traced, not replayed in full.',
            'Zeroed outer descriptor, type5, job argument0 and supplied enclosing job header; pixel-buffer metadata is absent. Not a complete physical processing job.',
            'Captured base/default-exposure scenario and exact captured records; hardware and physical scheduling remain outside the probe.',
            'After native population, geometry+21942 receives an explicit0,0,5184,3888 fixture. Its actual producer is not replayed; converter geometry output is checked.',
            'Native settings/pool operations inherit explicitly modeled uncontended kernel exclusion.',
            'Value-copy lifetime for COLOR; not an ownership proof for every other processing-job pointer.',
            'Host chooses release order after conversion. Actual submission/completion/release timing is not established by this test.',
            'Stock neutral H/L coefficients only; no new H/L array, spare storage or added code qualified.',
            'The negative control deliberately ignores an accessor error that stock callers check; it is not a demonstrated camera crash.',
        ])
    (args.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f'{len(cases)} complete-conversion cases passed.', flush=True)


if __name__ == '__main__':
    main()
