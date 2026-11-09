#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Extract PEN-F 3101 inline text symbols; optionally verify native lookup.

Read-only firmware analysis. The four-level raster decoder is inferred from
the assets, with exact pixel counts and zero padding checked for all symbols.
Preview intensities are a visualization, not a verified display palette.
Native probes use synthetic font objects and stop before rasterization.
"""
import argparse
import hashlib
import html
import json
from pathlib import Path
import struct

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'analysis/penf_3.1/01_0101_41800020.decoded.bin'
EXPECTED_SHA = 'e06330df45867f192e708254c996f93f622793583dd52a938ac7414e8cbc076e'
BANK_OFFSET, BANK_SIZE, BANK_BASE = 0x7e0, 0x730a00, 0xa1fa6c00
COUNT = 0x131


def digest(data):
    return hashlib.sha256(data).hexdigest()


def decode_symbol(bank, index):
    if not 0 <= index < COUNT:
        raise ValueError('Symbol index outside A000–A130')
    table, = struct.unpack_from('<I', bank)
    descriptor, = struct.unpack_from('<I', bank, table - BANK_BASE + 4 * index)
    offset = descriptor - BANK_BASE
    assert 0 <= offset <= len(bank) - 8
    width, height, pointer = struct.unpack_from('<HHI', bank, offset)
    start = pointer - BANK_BASE
    assert 0 <= start < offset
    encoded = bank[start:offset]
    encoded_height = (encoded[0] | ((encoded[1] & 3) << 8)) + 1
    encoded_width = ((encoded[1] >> 4) | ((encoded[2] & 63) << 4)) + 1
    assert (encoded_width, encoded_height) == (width, height)
    assert encoded[3] == 1, 'Only the observed symbol format is supported'
    pixels, cursor = [], 0
    while len(pixels) < width * height:
        value = (encoded[4 + cursor // 2] >> (4 * (cursor % 2))) & 15
        pixels.extend([value >> 2] * ((value & 3) + 1))
        cursor += 1
    assert len(pixels) == width * height, 'Run crosses the declared image end'
    assert int.from_bytes(encoded[4:], 'little') >> (4 * cursor) == 0
    image = Image.new('L', (width, height))
    image.putdata([level * 85 for level in pixels])
    row = dict(code=f'{0xa000 + index:04X}', token=f'@{0xa000 + index:04X}@',
               width=width, height=height, descriptor=hex(descriptor),
               data_pointer=hex(pointer), component_offset=hex(BANK_OFFSET + start),
               encoded_interval_bytes=len(encoded), decoded_pixels=len(pixels),
               run_nibbles=cursor, zero_padding=True, encoded_sha256=digest(encoded))
    return row, image


def native_checks(bank, symbols):
    from penf_emulator import ENGINE, Region, firmware
    from penf_probe import ProbeState, CALLER, BUFFER

    def stop(state, address):
        result = state.run({address}, limit=10000)
        assert result['status'] == 'breakpoint' and state.regs['pc'] == address, {
            'status': result['status'], 'pc': hex(state.regs['pc']), 'fault': result.get('fault')}

    lookups = []
    # Every descriptor plus both native rejection boundaries of the reserved range.
    for code in [*range(0xa000, 0xa131), 0xa131, 0xa1ff]:
        state = ProbeState(0x60bce153, 0xf0, 44, bytes(16),
                           dict(a0=code, d0=15, d1=32))
        state.regions.append(Region('stock_osd_bank', BANK_BASE, bank, 'r'))
        state.ram('current_font_bank_fixture', 0x61a8e328,
                  struct.pack('<I', BANK_BASE), aliases=False)
        stop(state, CALLER + 7)
        expected = int(symbols[code - 0xa000]['descriptor'], 16) if code < 0xa131 else 0
        assert state.regs['a0'] == expected and state.regs['sp'] == 0x18018000
        lookups.append(dict(code=hex(code), result=hex(expected), instructions=state.steps))

    parsers = []
    for token in ('@A047@', '@a047@', '@A025@', '@A072@'):
        state = ProbeState(0x60bcf529, 0xf0, 52,
                           (token + 'X\0').encode('utf-16le'),
                           dict(a0=0x19000000, a1=0x19000100))
        font = bytearray(32)
        struct.pack_into('<I', font, 4, 0x19000200)
        fixtures = (
            ('font', 0x19000000, font),
            ('glyph_request', 0x19000100, struct.pack('<I', BUFFER) + bytes(28)),
            ('font_child', 0x19000200, struct.pack('<HH', 0, 32)),
            ('font_styles', 0x19000300, struct.pack('<H', 15) + bytes(16)),
            ('font_styles_pointer', 0x61a8e6b0, struct.pack('<I', 0x19000300)),
            ('literal_flag', 0x61a8e6d0, bytes(2)),
            ('hex_state', 0x6160c510, bytes(4)),
        )
        for name, address, data in fixtures:
            state.ram(name + '_fixture', address, data, aliases=False)
        stop(state, 0x60bce013)
        font_id, size, code = struct.unpack('<3H', state.read(state.regs['a0'], 6))
        next_pointer, = struct.unpack('<I', state.read(0x19000104, 4))
        assert (font_id, size, code) == (15, 32, int(token[1:-1], 16))
        assert next_pointer == BUFFER + 2 * len(token)
        parsers.append(dict(token=token, code=hex(code), consumed_utf16_units=len(token),
                            instructions=state.steps, stopped_before='0x60bce013'))
    return dict(lookup_cases=lookups, parser_cases=parsers,
                main_sha256=digest(firmware()), engine_sha256=digest(ENGINE.read_bytes()),
                modeled_functions=[], hardware_accesses=0,
                scope='Synthetic font fixtures; native markup parsing and descriptor lookup only; no display draw')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--verify-native', action='store_true')
    args = ap.parse_args()
    source = SOURCE.read_bytes()
    assert digest(source) == EXPECTED_SHA
    # English resource 8, independently addressed inside this pinned payload.
    english_offset, english_base = 0x4201cc00 - 0x41800020, 0xa2ce3c00
    english = source[english_offset:english_offset + 153088]
    strings, = struct.unpack_from('<I', english)
    label, = struct.unpack_from('<I', english, strings - english_base + 4 * 990)
    expected_label = 'Delete@A047@'.encode('utf-16le') + b'\0\0'
    assert english[label - english_base:label - english_base + len(expected_label)] == expected_label
    bank = source[BANK_OFFSET:BANK_OFFSET + BANK_SIZE]
    out = args.out
    (out / 'symbols').mkdir(parents=True, exist_ok=True)
    rows, images = [], []
    for index in range(COUNT):
        row, image = decode_symbol(bank, index)
        row['image'] = f'symbols/{row["code"]}.png'
        image.save(out / row['image'])
        rows.append(row)
        images.append(image)

    # A legible close-up of the real extracted pixels, not generated artwork.
    image = images[0x47]
    image.resize((image.width * 8, image.height * 8), Image.Resampling.NEAREST).save(out / 'trash-enlarged.png')
    sheet = Image.new('RGB', (1440, ((COUNT + 11) // 12) * 84), '#20252b')
    draw = ImageDraw.Draw(sheet)
    for index, (row, image) in enumerate(zip(rows, images)):
        x, y = (index % 12) * 120, (index // 12) * 84
        preview = image.copy()
        preview.thumbnail((112, 52), Image.Resampling.NEAREST)
        sheet.paste(preview, (x + 4, y + 25))
        draw.text((x + 4, y + 5), row['token'], fill='white')
    sheet.save(out / 'contact-sheet.png')

    cards = ''.join(f'<figure><img src="{r["image"]}" width="{r["width"] * 2}" '
                    f'height="{r["height"] * 2}"><figcaption>{html.escape(r["token"])} '
                    f'· {r["width"]}×{r["height"]}</figcaption></figure>' for r in rows)
    page = '''<!doctype html><meta charset="utf-8"><title>PEN-F stock UI symbols</title>
<style>body{background:#172029;color:#eef3f6;font:16px system-ui;max-width:1450px;margin:32px auto;padding:0 20px}
img{image-rendering:pixelated;background:black}a{color:#96d3ff}.grid{display:flex;flex-wrap:wrap}
figure{margin:6px;padding:12px;background:#25333f;min-width:120px}figcaption{font:13px monospace;margin-top:8px}
.hero{display:flex;align-items:center;gap:24px;flex-wrap:wrap}p{max-width:900px;line-height:1.5}</style>
<h1>PEN-F stock UI symbols</h1><div class="hero"><img src="trash-enlarged.png" width="352" height="256">
<p><b>Trash can: <code>@A047@</code></b><br>44 × 32 source pixels; enlarged 8×.
The stock English label is <code>Delete@A047@</code>.<br>
Proposed use: a button hint beside the current HSL axis. This is an extraction, not a patched camera screenshot.</p></div>
<p>All 305 shared text symbols were decoded from the unchanged 3101 OSD resource bank.
Each raster exactly matches its declared dimensions and has only zero alignment padding.
Four intensity levels are shown as grayscale; actual display colors and compositing are not reproduced here.
The native lookup distinguishes these character codes from general bitmap IDs.</p>
<p><a href="report.json">Evidence and native probe results</a> · <a href="contact-sheet.png">Contact sheet</a></p>
<div class="grid">''' + cards + '</div>'
    (out / 'index.html').write_text(page)
    report = dict(source=str(SOURCE.relative_to(ROOT)), source_sha256=digest(source),
                  tool_sha256=digest(Path(__file__).read_bytes()), bank_base=hex(BANK_BASE),
                  bank_offset=hex(BANK_OFFSET), bank_size=BANK_SIZE,
                  symbol_range='A000–A130', symbol_count=len(rows),
                  decoder='Format 1: low nibble first; low 2 bits + 1 = run length, high 2 bits = level',
                  decoder_evidence='Inferred layout; exact dimensions, pixel count and zero padding for all 305 symbols',
                  trash=dict(code='A047', english_string_id=990, stock_text='Delete@A047@'),
                  limitations=['Raster palette/compositing not verified on hardware',
                               'COLOR paint callback not yet joined to this text path',
                               'Delete button handling remains a separate mapping task'],
                  symbols=rows)
    if args.verify_native:
        report['native'] = native_checks(bank, rows)
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(symbols=len(rows), trash=rows[0x47],
                          native_verified=args.verify_native, output=str(out))))


if __name__ == '__main__':
    main()
