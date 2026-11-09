#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Rebuild the specified PEN-F HSL release from exact stock and assembly source.

No network or camera access. The default build requires byte equality with the
published release, including the Value bitmap and both component checksums.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from oly_container import parse, replace_payload, reconstruct


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encode_bitmap(pixels, header, width, height, size):
    """Pack authored indexed pixels into the existing format-3 allocation."""
    require(len(pixels) == width * height, 'Bitmap dimensions differ')
    runs = []
    for y in range(height):
        x = 0
        while x < width:
            value, length = pixels[y * width + x], 1
            while length < 4 and x + length < width and pixels[y * width + x + length] == value:
                length += 1
            runs.append((value, length))
            x += length
    target = (size - 4) // 8 * 6
    missing = target - len(runs)
    require(missing >= 0, 'Bitmap exceeds slot capacity')
    tokens = []
    for value, length in runs:
        while length > 1 and missing:
            tokens.append(value << 2)
            length -= 1
            missing -= 1
        tokens.append((value << 2) | (length - 1))
    require(missing == 0 and len(tokens) == target, 'Bitmap cannot fill the slot')
    encoded = bytearray(header)
    for i in range(0, len(tokens), 6):
        encoded.extend(sum(t << (10 * j) for j, t in enumerate(tokens[i:i+6])).to_bytes(8, 'little'))
    # Independent decode checks the stream, including scanline boundaries.
    decoded = bytearray()
    for at in range(4, len(encoded), 8):
        word = int.from_bytes(encoded[at:at+8], 'little')
        require(word >> 60 == 0, 'Nonzero bitmap padding bits')
        for j in range(6):
            token = (word >> (10 * j)) & 1023
            count = (token & 3) + 1
            require(len(decoded) % width + count <= width, 'Bitmap run crosses a row')
            decoded.extend([token >> 2] * count)
    require(len(encoded) == size and bytes(decoded) == pixels, 'Bitmap round trip failed')
    return bytes(encoded)


def executable(explicit, name, local):
    value = explicit or shutil.which('mn10300-elf-' + name)
    if value is None and local.is_file():
        value = str(local)
    require(value is not None, f'Missing MN103 {name}; supply --{name} or install mn10300-elf-{name}')
    return str(Path(value).resolve())


def build(args):
    args.out = args.out.resolve()
    require(HERE not in args.out.parents and args.out != HERE, 'Keep generated output outside the patch source directory')
    spec = json.loads((HERE / 'patch.json').read_text())
    stock = args.stock.read_bytes()
    require(sha(stock) == spec['stock_sha256'], 'Wrong stock firmware hash; requires full PEN-F 3101 container')
    blocks = parse(stock)
    require(len(blocks) == 4 and [b.kind for b in blocks[:2]] == [0x100, 0x101], 'Unexpected component order')
    require(not args.out.exists(), 'Output directory must be new')
    toolchain = ROOT / 'toolchains/mn103-patch-build'
    assembler = executable(args.assembler, 'as', toolchain / 'gas/as-new')
    linker = executable(args.linker, 'ld', toolchain / 'ld/ld-new')
    objcopy = executable(args.objcopy, 'objcopy', toolchain / 'binutils/objcopy')
    args.out.mkdir(parents=True)
    base = int(spec['cpu_base'], 16)
    main = bytearray(blocks[0].payload)
    ranges = sorted(spec['main_ranges'], key=lambda x: int(x['address'], 16))
    for i, row in enumerate(ranges):
        at, size = int(row['address'], 16) - base, row['bytes']
        require(0 <= at < at + size <= len(main), f'Invalid range: {row["name"]}')
        require(sha(main[at:at+size]) == row['before_sha256'], f'Original bytes differ: {row["name"]}')
        if i:
            prior = ranges[i-1]
            require(int(prior['address'], 16) + prior['bytes'] <= at + base, 'Overlapping patch ranges')
    expected = {(x['name'], int(x['address'], 16)): x for x in ranges}
    written = set()

    def install(name, address, data):
        key = name, address
        require(key in expected and key not in written, f'Unexpected or repeated section: {key}')
        row = expected[key]
        require(len(data) == row['bytes'], f'Section size differs: {name}: {len(data)} != {row["bytes"]}')
        require(sha(data) == row['after_sha256'], f'Compiled bytes differ from reference: {name}')
        main[address-base:address-base+len(data)] = data
        written.add(key)

    for group in spec['groups']:
        folder = args.out / 'assembly' / group['name']
        folder.mkdir(parents=True)
        objects = []
        for source in group['sources']:
            obj = folder / (Path(source).stem + '.o')
            subprocess.run([assembler, '-o', str(obj), str(HERE / source)], check=True)
            objects.append(str(obj))
        elf = folder / 'patch.elf'
        subprocess.run([linker, '--no-relax', '-T', str(HERE / group['linker']), '-o', str(elf), *objects], check=True)
        for name, address in group['sections'].items():
            output = folder / (name + '.bytes')
            subprocess.run([objcopy, '-O', 'binary', '--only-section=.' + name, str(elf), str(output)], check=True)
            install(name, int(address, 16), output.read_bytes())
    for edit in spec['data_edits']:
        install(edit['name'], int(edit['address'], 16), bytes.fromhex(edit['after']))
    require(written == set(expected), 'Not every declared patch range was produced')
    require(sha(main) == spec['main_sha256'], 'Decoded main differs from reference')

    bitmap = spec['value_bitmap']
    alphabet = {symbol: int(value) for value, symbol in bitmap['pixel_symbols'].items()}
    rows = (HERE / bitmap['source']).read_text().splitlines()
    require(len(rows) == bitmap['height'] and all(len(row) == bitmap['width'] for row in rows), 'Artwork dimensions differ')
    pixels = bytes(alphabet[symbol] for row in rows for symbol in row)
    require(sha(pixels) == bitmap['pixels_sha256'], 'Artwork pixels differ')
    osd = bytearray(blocks[1].payload)
    at, size = int(bitmap['offset'], 16), bitmap['size']
    original = osd[at:at+size]
    require(sha(original) == bitmap['stock_sha256'], 'Original bitmap differs')
    encoded = encode_bitmap(pixels, original[:4], bitmap['width'], bitmap['height'], size)
    require(sha(encoded) == bitmap['encoded_sha256'], 'Encoded artwork differs')
    osd[at:at+size] = encoded
    require(sha(osd) == spec['osd_sha256'], 'Decoded OSD differs from reference')

    package = reconstruct([replace_payload(blocks[0], main), replace_payload(blocks[1], osd)])
    restore = reconstruct(blocks[:2])
    require(len(package) == spec['package_bytes'] and sha(package) == spec['package_sha256'], 'Package differs from released BIN')
    require(sha(restore) == spec['stock_restore_sha256'], 'Restore package differs')
    verified = parse(package)
    require(verified[0].payload == main and verified[1].payload == osd, 'Container round trip failed')
    require(all(a.header == b.header and a.trailer[:28] == b.trailer[:28] for a, b in zip(verified, blocks)), 'Component metadata changed')
    for path, data in [('install/DCOLYMP/E1229999.BIN', package), ('restore-stock/DCOLYMP/E1229999.BIN', restore)]:
        target = args.out / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    report = {'release': spec['release'], 'stock_sha256': sha(stock), 'package_sha256': sha(package),
              'restore_sha256': sha(restore), 'main_sha256': sha(main), 'osd_sha256': sha(osd),
              'package_bytes': len(package), 'patch_ranges': len(ranges),
              'main_changed_bytes': sum(a != b for a, b in zip(main, blocks[0].payload)),
              'osd_changed_bytes': sum(a != b for a, b in zip(osd, blocks[1].payload)),
              'exact_release_match': True,
              'tool_versions': {name: subprocess.check_output([tool, '--version'], text=True).splitlines()[0]
                                for name, tool in [('as', assembler), ('ld', linker), ('objcopy', objcopy)]},
              'source_sha256': {str(p.relative_to(HERE)): sha(p.read_bytes()) for p in sorted(HERE.rglob('*'))
                                if p.is_file() and '__pycache__' not in p.parts},
              'camera_access': False}
    (args.out / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('exact_release_match', 'package_sha256', 'package_bytes', 'main_changed_bytes', 'osd_changed_bytes')}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stock', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--as', dest='assembler')
    parser.add_argument('--ld', dest='linker')
    parser.add_argument('--objcopy')
    args = parser.parse_args()
    try:
        build(args)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Build failed: {error}\n')


if __name__ == '__main__':
    main()
