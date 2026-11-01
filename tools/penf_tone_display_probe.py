#!/usr/bin/env python3
"""Execute native PEN-F graph rectangle requests in an explicit synthetic fixture.

This is a drawing prerequisite, not a camera paint hook or installable patch.
Only raster submission at 606e15cc is modeled; unknown native accesses stop.
"""
if not __debug__:
    raise RuntimeError('Native display evidence requires assertions. Run without -O.')

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from penf_diagnostic_lifetime_probe import parser_state
from penf_emulator import BASE, ROOT, Region, firmware
from penf_probe import CALLER, ProbeState
from penf_profile_context_probe import resume
from penf_profile_lifecycle_probe import invoke, returned

CODE, CONTEXT, BACKEND = 0x19000000, 0x19500000, 0x19501000
DESCRIPTOR, CLIP, COMMANDS, SURFACE = 0x19502000, 0x19502100, 0x19503000, 0x19510000
RASTER = 0x606e15cc
GRAPH = (348, 107, 609, 372)
CONTEXT_BYTES = 684
PRESERVED = dict(d2=0x2dd22dd2, d3=0x3dd33dd3, a2=0x2aa22aa2, a3=0x3aa33aa3)

# This command painter has no receiver state, firmware placement, or stock
# traversal contract. Its input is a fixture descriptor, not a native UI job.
PAINTER = r'''
.text
.global _start
_start:
 movm [d2,d3,a2,a3],(sp)
 add -716,sp
 movhu (a1),d0
 cmp 1,d0
 bne done
 mov (4,a1),d3
 cmp 0,d3
 beq done
 mov (8,a1),a2
 mov (12,a1),d2
 mov sp,a3
 add 32,a3
 mov a3,a1
 mov 171,d1
copy_context:
 mov (a0),d0
 mov d0,(a1)
 inc4 a0
 inc4 a1
 add -1,d1
 bne copy_context
 mov a3,a0
 mov d2,a1
 call native_clip,[a2,a3],20
 mov a3,a0
 mov -1,d0
 call native_pen,[d2,d3,a2,a3],16
next_rectangle:
 mov a3,a0
 mov (a2),a1
 mov -2,d0
 mov -1,d1
 call native_brush,[d2,d3,a2],16
 mov a3,a0
 mov a2,a1
 inc4 a1
 call native_rectangle,[d2,a2,a3],52
 add 12,a2
 add -1,d3
 bne next_rectangle
done:
 clr d0
 add 716,sp
 ret [d2,d3,a2,a3],16
'''


def assemble(out):
    tc = ROOT / 'toolchains/tone-binutils-build'
    out.mkdir(parents=True, exist_ok=True)
    source, obj, elf, binary = [out / ('fixture.' + ext) for ext in ('s', 'o', 'elf', 'bin')]
    source.write_text(PAINTER)
    for args in ([tc/'gas/as-new', '-o', obj, source],
                 [tc/'ld/ld-new', '-Ttext', hex(CODE), '-e', '_start',
                  '--defsym=native_clip=0x60bc9f95', '--defsym=native_pen=0x60bca2b4',
                  '--defsym=native_brush=0x60bca074', '--defsym=native_rectangle=0x60bc69b8',
                  '-o', elf, obj],
                 [tc/'binutils/objcopy', '-O', 'binary', elf, binary]):
        subprocess.run(list(map(str, args)), check=True, capture_output=True)
    return binary.read_bytes()


def fixture(code, commands, *, layer=1, clip=(0, 0, 639, 479), backend=0, selector=0):
    if not 1 <= layer <= 3 or not 0 <= backend <= 2 or selector not in (0, 1):
        raise ValueError('Fixture layer/backend/selector outside qualified bounds')
    if len(commands) > 1024:
        raise ValueError('At most 1024 fixture rectangles')
    s = ProbeState(CODE, 0, 0, bytes(16), {})
    parser_state(s)
    s.regions.append(Region('synthetic_command_painter', CODE, code, 'rx'))
    context = bytearray(CONTEXT_BYTES)
    for offset in (4, 24):
        struct.pack_into('<4h', context, offset, 0, 0, 639, 479)
    struct.pack_into('<I', context, 72, BACKEND)
    s.ram('explicit_drawing_context', CONTEXT, context, aliases=False)
    backend_data = bytearray(160)
    struct.pack_into('<3H', backend_data, 0, backend, 640, 480)
    struct.pack_into('<I', backend_data, 92, 0x60bcc0e8)
    s.ram('explicit_native_rectangle_backend', BACKEND, backend_data, aliases=False)
    s.ram('fixture_descriptor', DESCRIPTOR,
          struct.pack('<4I', layer, len(commands), COMMANDS, CLIP), aliases=False)
    s.ram('fixture_clip', CLIP, struct.pack('<4h', *clip), aliases=False)
    data = b''.join(struct.pack('<I4h', color, *rect) for color, rect in commands)
    s.ram('fixture_commands', COMMANDS, data or bytes(12), aliases=False)
    s.ram('opaque_raster_surface_tokens', SURFACE, bytes(6*16), aliases=False)
    s.ram('explicit_gui_globals', 0x6160c000, bytes(0x500), aliases=False)
    s.write(0x6160c40c, bytes([selector]))
    s.ram('native_logging_disabled', 0x6161bdd4, bytes(8), aliases=False)
    s.ram('explicit_surface_table', 0x61a8e308,
          struct.pack('<6I', *(SURFACE+i*16 for i in range(6))), aliases=False)
    return s


def paint(s):
    original = s.read(CONTEXT, CONTEXT_BYTES)
    backend = s.read(BACKEND, 160)
    start = s.steps
    draws = []
    r = invoke(s, CODE, 0, 0, dict(a0=CONTEXT, a1=DESCRIPTOR, **PRESERVED), stops=(RASTER,))
    while s.regs['pc'] != CALLER+7:
        if r['status'] != 'breakpoint' or s.regs['pc'] != RASTER:
            raise RuntimeError(json.dumps(r))
        raw = s.read(s.regs['a0'], 28)
        surface, device = struct.unpack_from('<II', raw)
        x, y, width, height = struct.unpack_from('<4h', raw, 8)
        draws.append(dict(entry=hex(RASTER), surface=hex(surface), device_layer=device,
                          x=x, y=y, width=width, height=height,
                          palette_index=raw[20], color_halfword=struct.unpack_from('<H', raw, 18)[0],
                          mode=struct.unpack_from('<I', raw, 24)[0], request_hex=raw.hex()))
        s.return_from_model(0)
        r = resume(s, (RASTER, CALLER+7), limit=2000000)
    returned(s, r)
    assert s.read(CONTEXT, CONTEXT_BYTES) == original
    assert s.read(BACKEND, 160) == backend
    assert s.regs['sp'] == 0x18018000
    assert all(s.regs[key] == value for key, value in PRESERVED.items())
    return dict(returned=True, stack_restored=True, caller_context_unchanged=True,
                backend_unchanged=True, callee_saved_registers_unchanged=True,
                instructions=s.steps-start, draws=draws,
                modeled_functions=['606e15cc raster submission only'])


def validate_input(data):
    lut, markers = data['lut'], data['marker_indices']
    if (not isinstance(lut, list) or len(lut) != 256 or
            any(type(v) is not int or not 0 <= v <= 1023 for v in lut)):
        raise ValueError('LUT must contain 256 integer samples in 0..1023')
    if (not isinstance(markers, list) or len(markers) != 5 or
            any(type(i) is not int for i in markers) or markers[0] != 0 or
            markers[-1] != 255 or any(a >= b for a, b in zip(markers, markers[1:]))):
        raise ValueError('Five strictly ordered marker indices must span 0..255')
    return lut, markers


def graph_commands(data, rect=GRAPH):
    lut, markers = validate_input(data)
    left, top, right, bottom = rect
    if not (0 <= left < right < 640 and 0 <= top < bottom < 480):
        raise ValueError('Graph rectangle must fit the explicit 640x480 fixture')
    def point(i):
        return (left + (i*(right-left)+127)//255,
                bottom - (lut[i]*(bottom-top)+511)//1023)
    commands = [(0, rect)]
    for i in range(1, 4):
        x = left + i*(right-left)//4
        y = top + i*(bottom-top)//4
        commands += [(3, (x, top, x, bottom)), (3, (left, y, right, y))]
    for i in range(256):
        x, y = point(i)
        old_x, old_y = point(max(0, i-1))
        first_x = x if i == 0 else min(x, old_x+1)
        commands.append((5, (first_x, min(y, old_y), x, max(y, old_y))))
    points = [dict(index=i, value=lut[i], x=point(i)[0], y=point(i)[1]) for i in markers]
    for p in points:
        x, y = p['x'], p['y']
        commands += [(4, (x-3, y, x+3, y)), (4, (x, y-3, x, y+3))]
    return commands, points


def svg(draws):
    colors = {0: '#202020', 3: '#606060', 4: '#ffcd60', 5: '#eeeeee'}
    rows = ['<svg xmlns="http://www.w3.org/2000/svg" width="640" height="500" viewBox="0 0 640 500">',
            '<rect width="640" height="500" fill="#101010"/>',
            '<text x="12" y="24" fill="white" font-family="sans-serif" font-size="14">PROTOTYPE: recorded native requests, illustrative palette</text>',
            '<text x="12" y="48" fill="white" font-family="sans-serif" font-size="12">Synthetic fixture. No body capture or production anchor contract.</text>']
    for d in draws:
        rows.append(f'<rect x="{d["x"]}" y="{d["y"]}" width="{d["width"]}" height="{d["height"]}" fill="{colors.get(d["palette_index"], "#ff00ff")}"/>')
    return '\n'.join(rows + ['</svg>']) + '\n'


def render_png(draws, path):
    from PIL import Image, ImageDraw
    preview = Image.new('RGB', (640, 500), '#101010')
    draw = ImageDraw.Draw(preview)
    draw.text((12, 12), 'PROTOTYPE: native requests, illustrative palette', fill='white')
    draw.text((12, 32), 'Synthetic fixture. No body capture or production anchor contract.', fill='white')
    colors = {0: '#202020', 3: '#606060', 4: '#ffcd60', 5: '#eeeeee'}
    for d in draws:
        draw.rectangle((d['x'], d['y'], d['x']+d['width']-1, d['y']+d['height']-1),
                       fill=colors.get(d['palette_index'], '#ff00ff'))
    preview.save(path)


def tone_paint_dispatch():
    receiver, job = 0x19600000, 0x19601000
    s = ProbeState(0x60bbe8b6, 0, 0, bytes(16), dict(a0=receiver, a1=job))
    obj = struct.pack('<I', 0x60ec4cac)
    s.ram('explicit_tone_receiver', receiver, obj, aliases=False)
    s.ram('explicit_native_paint_job', job, struct.pack('<3I', 0, 1, CONTEXT), aliases=False)
    result = s.run({0x60bbe8d4}, limit=1000)
    assert result['status'] == 'breakpoint' and s.regs['pc'] == 0x60bbe8d4
    assert (s.regs['a0'], s.regs['a1']) == (receiver, job)
    table = struct.unpack_from('<III', firmware(), 0x60ec4cac-BASE+440)
    assert table[1:] == (0x60bf7aec, 0x60bbe8d4)
    assert struct.unpack_from('<I', firmware(), 0x60ec4cac-BASE+160)[0] == 0x60bbe8b6
    return dict(entry='0x60bbe8b6', native_instructions=s.steps,
                receiver_preserved=True, job_preserved=True,
                stopped_at='0x60bbe8d4', stopped_before='Unqualified background and child traversal',
                complete_paint_returned=False, modeled_functions=[])


def run(out, data):
    code = assemble(out/'native-fixture')
    clipping = paint(fixture(code, [(5, (0, 0, 100, 100)), (5, (200, 200, 210, 210))],
                             clip=(10, 20, 30, 40)))
    expected = dict(x=10, y=20, width=21, height=21, palette_index=5, device_layer=1)
    assert len(clipping['draws']) == 1
    assert all(clipping['draws'][0][k] == v for k, v in expected.items())
    rejected = [dict(layer=layer, **paint(fixture(code, [(5, GRAPH)], layer=layer))) for layer in (2, 3)]
    assert all(not row['draws'] for row in rejected)
    layers = []
    for backend in range(3):
        for selector in range(2):
            row = paint(fixture(code, [(7, (10, 20, 10, 20))], backend=backend, selector=selector))
            d = row['draws'][0]
            assert (d['device_layer'], d['surface']) == ((1, 2, 0)[backend], hex(SURFACE+(2*backend+selector)*16))
            layers.append(dict(backend=backend, selector=selector, **row))
    commands, points = graph_commands(data)
    comparison = None
    if 'source_lut' in data:
        _, original_points = graph_commands(dict(lut=data['source_lut'], marker_indices=data['marker_indices']))
        comparison = dict(source_marker_points=original_points,
                          inner_markers_unchanged=original_points[1:4] == points[1:4],
                          endpoint_x_unchanged=all(original_points[i]['x'] == points[i]['x'] for i in (0, 4)))
    graph = paint(fixture(code, commands, clip=GRAPH))
    expected = []
    for color, (left, top, right, bottom) in commands:
        left, top = max(left, GRAPH[0]), max(top, GRAPH[1])
        right, bottom = min(right, GRAPH[2]), min(bottom, GRAPH[3])
        if left <= right and top <= bottom:
            expected.append((left, top, right-left+1, bottom-top+1, color))
    actual = [(d['x'], d['y'], d['width'], d['height'], d['palette_index']) for d in graph['draws']]
    assert actual == expected
    graph['all_requests_match_clipped_commands'] = True
    report = dict(label='Prototype native drawing fixture; no body integration',
                  main_sha256=hashlib.sha256(firmware()).hexdigest(),
                  painter_sha256=hashlib.sha256(code).hexdigest(), painter_bytes=len(code),
                  painter_address=hex(CODE), context_bytes=CONTEXT_BYTES,
                  graph_rectangle=GRAPH, marker_points=points, source_comparison=comparison, clipping=clipping,
                  native_paint_dispatch=tone_paint_dispatch(),
                  rejected_layers=rejected, backend_mapping=layers, graph=graph,
                  input_fixture=data,
                  tone_paint_hook=dict(vtable='0x60ec4cac', slot=160, pointer='0x60ec4d4c',
                                       stock_entry='0x60bbe8b6', stock_dispatch='0x60bbe8bb',
                                       background_slot=448, background='0x60bbe8d4',
                                       children_slot=444, children='0x60bf7aec',
                                       evidence='Decoded stock vtable and instruction references only; full traversal not executed'),
                  limits=['Only raster submission is modeled. No hardware/display/compositor is modeled.',
                          'Synthetic command painter is not a native receiver callback and does not execute stock traversal.',
                          'Supplied markers are display prototype inputs, not photographic ISP anchors.',
                          'Palette indices are recorded exactly; SVG colors are illustrative.',
                          'No firmware placement, object extension, flash, full boot, or camera access.'])
    (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    (out/'prototype.svg').write_text(svg(graph['draws']))
    print(json.dumps(dict(report=str(out/'report.json'), graph_draws=len(graph['draws']),
                          painter_bytes=len(code), native_instructions=graph['instructions'],
                          clipping=True, layer_gate=True, caller_context_unchanged=True)))
    return report


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--fixture', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    data = json.loads(args.fixture.read_text())
    validate_input(data)
    run(args.out, data)
