#!/usr/bin/env python3
"""Compare relocated HSL CMIO helpers and check the section-8 entry guard.

Numeric buffers, owner pointer and loaded flags are synthetic fixtures. Native
helpers, copy arithmetic and cached/uncached conversion execute unchanged.
The metadata-transfer function is a stop boundary, not a successful stub.
No camera, SD update, RAW file or image-processing hardware is exercised.
"""
import argparse
import json
from pathlib import Path
import struct

from aperture_ring_probe import RingState, patch, engine, SP
from oly_container import parse
from penf_orf_native_cmio import coefficients

CALLER, DEST, OLD, NEW = 0x18000000, 0x62000000, 0x24000000, 0x24001000
SAVED = dict(d2=0x12345678, d3=0x89abcdef, a2=0x13572468, a3=0x24681357)


def call(state, entry, mask, frame, regs, stops=()):
    state.ram('call_site', CALLER, b'\xdd'+struct.pack('<i', entry-CALLER)+bytes((mask, frame))+b'\xcb',
              aliases=False, executable=True)
    state.regs = dict(SAVED, pc=CALLER, sp=SP, psw=0, **regs)
    initial = dict(state.regs)
    result = state.run(set(stops) | {CALLER+7}, limit=20000)
    patch.require(result['status'] == 'breakpoint', dict(status=result['status'], fault=result.get('fault')))
    if not stops:
        patch.require(state.regs['pc'] == CALLER+7 and state.regs['sp'] == SP, 'Native return/stack differs')
        patch.require(all(state.regs[k] == initial[k] for k in SAVED), 'Saved register differs')
    return initial


def experiment(build):
    build = Path(build)
    spec = patch.load_spec('pen-f-hsl')
    image = (build/'decoded-main.bin').read_bytes()
    patch.require(patch.sha(image) == spec['patched_main_sha256'], 'Combined main differs')
    raw = (build/'hsl-reference/install/DCOLYMP'/spec['sd_filename']).read_bytes()
    patch.require(patch.sha(raw) == spec['hsl_install_sha256'], 'HSL reference differs')
    baseline = parse(raw)[0].payload
    symbols = {k: int(v, 16) for k, v in spec['native_symbols'].items()}
    rows = []
    for flags in (0, 0x7f, 0x80, 0xff):
        s = RingState(image, spec)
        s.ram('loaded_sections', int(spec['guard_loaded_address'], 16), struct.pack('<I', flags))
        inputs = dict(d0=0x55aa, d1=0xaa55, a0=0x24002000, a1=0x24003000)
        initial = call(s, symbols['cmio_export_guard'], 0x20, 8, inputs,
                       {symbols['cmio_capture_export'], symbols['native_cmio_copy']})
        target = symbols['cmio_capture_export'] if flags & spec['guard_loaded_mask'] else symbols['native_cmio_copy']
        patch.require(s.regs['pc'] == target and s.regs['sp'] == SP-8, 'Guard target/frame differs')
        patch.require(all(s.regs[k] == initial[k] for k in (*SAVED, *inputs)), 'Guard changed live arguments')
        rows.append(dict(case='section readiness guard', flags=hex(flags), target=hex(target),
                         native_steps=s.steps, argument_registers_preserved=True, callee_executed=False))
    s = RingState(image, spec)
    s.ram('loaded_sections', int(spec['guard_loaded_address'], 16), struct.pack('<I', 0x80))
    s.write(SP+20, struct.pack('<I', 0x24004000))
    call(s, symbols['cmio_export_guard'], 0x20, 8, dict(a0=0x24002000), {symbols['native_cmio_copy']})
    patch.require(s.regs['pc'] == symbols['native_cmio_copy'] and s.regs['a0'] == 0x24002000,
                  'Relocated export did not reach original transfer boundary')
    rows.append(dict(case='relocated metadata prefix', native_steps=s.steps,
                     transfer_function_executed=False, successful_transfer_stub=False))

    for h, sat, light in (([0]*12, [0]*12, [0]*12), ([-7]*12, [7]*12, [7]*12),
                          ([i % 15-7 for i in range(12)], [7-i for i in range(12)], [i-6 for i in range(12)])):
        outputs = []
        for data, entry in ((baseline, 0x601caed0), (image, symbols['cmio_capture_weights'])):
            s = RingState(data, spec)
            s.ram('coefficients', DEST, b'\xa5'*72)
            s.ram('saturation', OLD, struct.pack('<12h', *sat), aliases=False)
            s.ram('hue_lightness', NEW, bytes((a & 15) | ((b & 15) << 4) for a, b in zip(h, light)), aliases=False)
            call(s, entry, 0xf0, 36, dict(a0=DEST, a1=NEW, d0=OLD))
            outputs.append(s.read(DEST, 72))
        patch.require(outputs[0] == outputs[1] == coefficients(h, sat, light), 'CMIO coefficients differ')
        rows.append(dict(case='native captured HSL coefficients', hue=h, saturation=sat, lightness=light,
                         bytes=72, baseline_and_relocated_equal=True, reference_formula_equal=True))

    for size in (0, 1, 15, 32):
        old, new = bytes((i*17) & 255 for i in range(32)), bytes((i*29+3) & 255 for i in range(32))
        initial = bytes((i*7+5) & 255 for i in range(size+1))
        expected, carry = bytearray(initial), 0x5a
        for i in range(size):
            delta = old[i] ^ new[i]
            expected[i] ^= carry ^ delta
            carry = delta
        outputs = []
        for data, entry in ((baseline, 0x601caa50), (image, symbols['cmio_delta_stream'])):
            s = RingState(data, spec)
            s.ram('encoded_output', DEST, initial)
            s.ram('old_plain', OLD, old, aliases=False)
            s.ram('new_plain', NEW, new, aliases=False)
            call(s, entry, 0xf0, 20, dict(a0=DEST, a1=OLD, a2=NEW, d0=size, d1=0x5a))
            outputs.append((s.read(DEST, len(initial)), s.regs['d0']))
        patch.require(outputs[0] == outputs[1] == (bytes(expected), carry), 'CMIO stream differs')
        rows.append(dict(case='native encoded delta stream', bytes=size,
                         baseline_and_relocated_equal=True, boundary_canary_preserved=True))

    for size in (0, 1, 31):
        old, new = bytes(range(32)), bytes(reversed(range(32)))
        initial = bytes((i*11+9) & 255 for i in range(size+2))
        expected = bytearray(initial)
        for i in range(size):
            delta = old[i] ^ new[i]
            expected[i] ^= delta
            expected[i+1] ^= delta
        outputs = []
        for data, entry in ((baseline, 0x601caaca), (image, symbols['cmio_patch_table'])):
            s = RingState(data, spec)
            s.ram('encoded_table', DEST, initial)
            s.ram('old_plain', OLD, old, aliases=False)
            s.ram('new_plain', NEW, new, aliases=False)
            call(s, entry, 0xf0, 60, dict(a0=DEST, a1=OLD, a2=NEW, d0=size))
            outputs.append((s.read(DEST, len(initial)), s.regs['d0']))
        patch.require(outputs[0] == outputs[1] == (bytes(expected), 0), 'CMIO direct table patch differs')
        rows.append(dict(case='native direct CMIO table replacement', bytes=size,
                         baseline_and_relocated_equal=True, original_uncached_conversion_executed=True,
                         boundary_canary_preserved=True))
    return dict(scope=__doc__, patched_main_sha256=patch.sha(image), hsl_main_sha256=patch.sha(baseline),
        engine_sha256=patch.sha(engine.ENGINE.read_bytes()), cases=rows, hardware_models=[],
        source_sha256={p.name: patch.sha(p.read_bytes()) for p in (Path(__file__), Path(__file__).with_name('aperture_ring_probe.py'))},
        hardware_validated=False, camera_access=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--engine', type=Path)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    if args.engine:
        engine.ENGINE = args.engine.resolve()
    report = experiment(args.build)
    with args.out.open('x') as f:
        json.dump(report, f, indent=2)
        f.write('\n')
    print(len(report['cases']), 'native HSL relocation/guard cases passed')
