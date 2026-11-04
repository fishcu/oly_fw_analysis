#!/usr/bin/env python3
"""Build a firmware patch from a declarative patch definition and a stock file you supply.

A patch directory holds `patch.json` (format `oly-patch/1`), assembly sources,
linker scripts and any authored resources. No firmware is distributed: the tool
reads your own stock update file, checks its exact hash, rebuilds every declared
change from source, and requires each result to match the recorded hashes.

    python3 tools/oly_patch.py patches/hsl/pen-f --stock OLY_E_122_3101_0000_0000.BIN --out generated/pen-f

Outputs (the output directory must be new):

    decoded/<kind>.bin           patched decoded components, e.g. for an emulator (--decoded)
    install/<package file>       update file containing the selected patched components
    restore-stock/<package file> the same components unmodified, from your stock file
    build.json                   hashes, sizes, tool versions and source hashes

A patch whose definition says it has not been tested on a camera produces no
install file unless --write-untested-package is given. This tool never talks to
a camera, and a correct checksum does not show that a change is safe to flash.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from oly_container import parse, replace_payload, reconstruct  # noqa: E402
from oly_compress import expand_image, repack_image  # noqa: E402
from oly_resource import alias_images, liblz4_version  # noqa: E402

SCHEMA = 'oly-patch/1'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def kind_of(text):
    return int(text, 16)


def encode_format3_bitmap(pixels, header, width, height, size):
    """Pack indexed pixels into an existing format-3 OSD bitmap allocation of fixed size."""
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
        encoded.extend(sum(t << (10 * j) for j, t in enumerate(tokens[i:i + 6])).to_bytes(8, 'little'))
    decoded = bytearray()
    for at in range(4, len(encoded), 8):
        word = int.from_bytes(encoded[at:at + 8], 'little')
        require(word >> 60 == 0, 'Nonzero bitmap padding bits')
        for j in range(6):
            token = (word >> (10 * j)) & 1023
            count = (token & 3) + 1
            require(len(decoded) % width + count <= width, 'Bitmap run crosses a row')
            decoded.extend([token >> 2] * count)
    require(len(encoded) == size and bytes(decoded) == pixels, 'Bitmap round trip failed')
    return bytes(encoded)


def executable(explicit, name):
    local = ROOT / 'toolchains/mn103-patch-build' / {'as': 'gas/as-new', 'ld': 'ld/ld-new',
                                                      'objcopy': 'binutils/objcopy'}[name]
    value = explicit or shutil.which('mn10300-elf-' + name)
    if value is None and local.is_file():
        value = str(local)
    require(value is not None, f'Missing MN103 {name}; supply --{name} or install mn10300-elf-{name}')
    return str(Path(value).resolve())


class Component:
    """One decoded payload being patched, with every changed span declared in advance."""

    def __init__(self, kind, block, spec):
        self.kind, self.block = kind, block
        self.base = int(spec['cpu_base'], 16) if 'cpu_base' in spec else 0
        self.spec = spec
        self.compressed = spec.get('image_transform') == 'olycompress'
        require(not self.compressed or sha(block.payload) == spec['stored_before_sha256'],
                f'Unexpected stored component {kind:#x}')
        self.data = bytearray(expand_image(block.payload) if self.compressed else block.payload)
        require(sha(self.data) == spec['before_sha256'], f'Unexpected stock component {kind:#x}')
        self.declared, self.written, self.after = {}, set(), {}

    def offset(self, row):
        if 'address' in row:
            require(self.base, f'{row["name"]}: addresses need a cpu_base for component {self.kind:#x}')
            return int(row['address'], 16) - self.base
        return int(row['offset'], 16)

    def declare(self, row):
        at, size = self.offset(row), row['bytes']
        require(0 <= at < at + size <= len(self.data), f'Invalid range: {row["name"]}')
        require(sha(self.data[at:at + size]) == row['before_sha256'], f'Original bytes differ: {row["name"]}')
        for (name, other), (o_at, o_size) in self.declared.items():
            require(at + size <= o_at or o_at + o_size <= at, f'Overlapping ranges: {row["name"]} and {name}')
        key = (row['name'], at)
        require(key not in self.declared, f'Repeated range: {row["name"]}')
        self.declared[key] = (at, size)
        self.after[key] = row['after_sha256']

    def install(self, name, at, data):
        key = (name, at)
        require(key in self.declared and key not in self.written, f'Unexpected or repeated section: {name} at {at:#x}')
        require(len(data) == self.declared[key][1], f'Section size differs: {name}: {len(data)} != {self.declared[key][1]}')
        require(sha(data) == self.after[key], f'Built bytes differ from the reference: {name}')
        self.data[at:at + len(data)] = data
        self.written.add(key)

    def finish(self):
        missing = set(self.declared) - self.written
        require(not missing, 'Not every declared range was produced: ' + ', '.join(sorted(n for n, _ in missing)))
        require(sha(self.data) == self.spec['after_sha256'], f'Patched component {self.kind:#x} differs from the reference')
        return bytes(self.data)


def build(patch_dir, stock_path, out, tools=None, decoded=False, untested=False):
    patch_dir, out = Path(patch_dir).resolve(), Path(out).resolve()
    require(patch_dir not in out.parents and out != patch_dir, 'Keep generated output outside the patch directory')
    spec = json.loads((patch_dir / 'patch.json').read_text())
    require(spec.get('schema') == SCHEMA, f'{patch_dir}/patch.json is not {SCHEMA}')
    stock = Path(stock_path).read_bytes()
    require(sha(stock) == spec['stock']['sha256'], f'Wrong stock file; {spec["model"]} {spec["firmware"]} requires SHA-256 {spec["stock"]["sha256"]}')
    blocks = parse(stock)
    require(reconstruct(blocks) == stock, 'Stock container does not round-trip')
    by_kind = {}
    for block in blocks:
        require(block.kind not in by_kind, f'Duplicate component kind {block.kind:#x}')
        by_kind[block.kind] = block
    require(not out.exists(), 'Output directory must be new')
    package = spec.get('package')
    tested = spec.get('camera_tested', False)

    comps = {}
    for text, cspec in spec['components'].items():
        kind = kind_of(text)
        require(kind in by_kind, f'Stock file has no component {text}')
        comps[kind] = Component(kind, by_kind[kind], cspec)
    for row in spec.get('ranges', []):
        comps[kind_of(row['component'])].declare(row)

    tools = tools or {}
    toolchain = None
    if spec.get('assembly'):
        toolchain = {name: executable(tools.get(name), name) for name in ('as', 'ld', 'objcopy')}
    out.mkdir(parents=True)

    for group in spec.get('assembly', []):
        comp = comps[kind_of(group['component'])]
        folder = out / 'assembly' / group['name']
        folder.mkdir(parents=True)
        objects = []
        for source in group['sources']:
            obj = folder / (Path(source).stem + '.o')
            subprocess.run([toolchain['as'], '-o', str(obj), str(patch_dir / source)], check=True)
            objects.append(str(obj))
        elf = folder / 'patch.elf'
        subprocess.run([toolchain['ld'], '--no-relax', '-T', str(patch_dir / group['linker']), '-o', str(elf), *objects], check=True)
        for name, address in group['sections'].items():
            target = folder / (name + '.bytes')
            subprocess.run([toolchain['objcopy'], '-O', 'binary', '--only-section=.' + name, str(elf), str(target)], check=True)
            comp.install(name, int(address, 16) - comp.base, target.read_bytes())

    for edit in spec.get('data_edits', []):
        comp = comps[kind_of(edit['component'])]
        comp.install(edit['name'], comp.offset(edit), bytes.fromhex(edit['after']))

    for group in spec.get('resource_aliases', []):
        comp = comps[kind_of(group['component'])]
        require(not comp.compressed, 'Resource aliases need a stored resource component')
        aliases = [(kind_of(target), kind_of(source)) for target, source in group['aliases']]
        comp.install(group['name'], 0, alias_images(bytes(comp.data), aliases))

    for bitmap in spec.get('bitmaps', []):
        comp = comps[kind_of(bitmap['component'])]
        alphabet = {symbol: int(value) for value, symbol in bitmap['pixel_symbols'].items()}
        rows = (patch_dir / bitmap['source']).read_text().splitlines()
        require(len(rows) == bitmap['height'] and all(len(r) == bitmap['width'] for r in rows), 'Artwork dimensions differ')
        pixels = bytes(alphabet[s] for r in rows for s in r)
        require(sha(pixels) == bitmap['pixels_sha256'], 'Artwork pixels differ')
        at = comp.offset(bitmap)
        original = comp.data[at:at + bitmap['bytes']]
        comp.install(bitmap['name'], at, encode_format3_bitmap(pixels, original[:4], bitmap['width'], bitmap['height'], bitmap['bytes']))

    expanded = {kind: comp.finish() for kind, comp in comps.items()}
    # repack "split": a stock match that no longer fits is re-encoded with short literal
    # runs (never longer than the stock stream's longest) instead of one long literal run.
    patched = {kind: repack_image(by_kind[kind].payload, data,
                                  split=comps[kind].spec.get('repack') == 'split',
                                  literal_limit=0 if comps[kind].spec.get('repack') == 'split' else None)
               if comps[kind].compressed else data
               for kind, data in expanded.items()}
    for kind, comp in comps.items():
        if comp.compressed:
            require(sha(patched[kind]) == comp.spec['stored_after_sha256'],
                    f'Repacked component {kind:#x} differs from the reference')
    report = {'schema': SCHEMA, 'name': spec['name'], 'model': spec['model'], 'firmware': spec['firmware'],
              'release': spec.get('release'), 'camera_tested': tested, 'stock_sha256': sha(stock),
              'components': {f'{k:#x}': {'sha256': sha(v), 'expanded_sha256': sha(expanded[k]),
                                        'changed_bytes': sum(a != b for a, b in zip(v, by_kind[k].payload))}
                             for k, v in patched.items()}}

    if decoded:
        (out / 'decoded').mkdir()
        for kind, data in expanded.items():
            (out / 'decoded' / f'{kind:04x}.bin').write_bytes(data)
        report['decoded'] = sorted(f'decoded/{k:04x}.bin' for k in patched)

    if package:
        wanted = [b.kind for b in blocks] if package['components'] == 'all' else [kind_of(t) for t in package['components']]
        require(set(patched) <= set(wanted), 'Every patched component must be packaged')
        chosen = [b for b in blocks if b.kind in wanted]
        require(len(chosen) == len(wanted), 'Package names a component the stock file lacks')
        image = reconstruct([replace_payload(b, patched[b.kind]) if b.kind in patched else b for b in chosen])
        restore = reconstruct(chosen)
        verified = parse(image)
        require([v.payload for v in verified] == [patched.get(b.kind, b.payload) for b in chosen], 'Package round trip failed')
        require(all(v.header == b.header and v.trailer[:28] == b.trailer[:28] for v, b in zip(verified, chosen)), 'Component metadata changed')
        for key, value in (('sha256', sha(image)), ('bytes', len(image)), ('restore_sha256', sha(restore))):
            if key in package:
                require(package[key] == value, f'Package {key} differs from the recorded value')
        report.update(package_sha256=sha(image), package_bytes=len(image), restore_sha256=sha(restore))
        target = out / 'restore-stock' / package['file']
        target.parent.mkdir(parents=True)
        target.write_bytes(restore)
        if tested or untested:
            target = out / 'install' / package['file']
            target.parent.mkdir(parents=True)
            target.write_bytes(image)
            report['install'] = 'install/' + package['file']
        else:
            report['install'] = None
            report['install_withheld'] = 'Not tested on a camera; use --write-untested-package to write it anyway'

    if toolchain:
        report['tool_versions'] = {n: subprocess.check_output([t, '--version'], text=True).splitlines()[0] for n, t in toolchain.items()}
    if spec.get('resource_aliases'):
        report.setdefault('tool_versions', {})['liblz4'] = liblz4_version()
    report['source_sha256'] = {str(p.relative_to(patch_dir)): sha(p.read_bytes()) for p in sorted(patch_dir.rglob('*'))
                               if p.is_file() and '__pycache__' not in p.parts}
    report['camera_access'] = False
    (out / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main(argv=None, default_patch=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    if default_patch is None:
        parser.add_argument('patch', type=Path, help='patch directory containing patch.json')
    parser.add_argument('--stock', type=Path, required=True, help='your stock update file')
    parser.add_argument('--out', type=Path, required=True, help='new output directory')
    parser.add_argument('--as', dest='assembler')
    parser.add_argument('--ld', dest='linker')
    parser.add_argument('--objcopy')
    parser.add_argument('--decoded', action='store_true', help='also write patched decoded components')
    parser.add_argument('--write-untested-package', action='store_true',
                        help='write the install file even though the patch is not camera-tested')
    args = parser.parse_args(argv)
    patch = default_patch or args.patch
    try:
        report = build(patch, args.stock, args.out, {'as': args.assembler, 'ld': args.linker, 'objcopy': args.objcopy},
                       args.decoded, args.write_untested_package)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Build failed: {error}\n')
    print(json.dumps({k: report.get(k) for k in ('name', 'camera_tested', 'package_sha256', 'package_bytes', 'install', 'components')}, indent=2))


if __name__ == '__main__':
    main()
