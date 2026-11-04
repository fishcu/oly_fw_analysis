#!/usr/bin/env python3
"""Build PEN-F HSL + Live ND (Frame Off/2f/4f/8f) + AF Limiter from exact stock.

First rebuilds the HSL alpha-20261017 package with patches/hsl/pen-f/build.py,
then assembles the helpers here and applies every range in patch.json to the
HSL main. No network or camera access. The build must match the recorded
hashes byte for byte, including the camera-tested package.
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
HSL_BUILDER = ROOT / 'patches/hsl/pen-f/build.py'
sys.path.insert(0, str(ROOT / 'tools'))
from oly_container import parse, replace_payload, reconstruct  # noqa: E402


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def executable(explicit, name, local):
    value = explicit or shutil.which('mn10300-elf-' + name)
    if value is None and local.is_file():
        value = str(local)
    require(value is not None, f'Missing MN103 {name}; supply --{name} or install mn10300-elf-{name}')
    return str(Path(value).resolve())


def build(args):
    args.out = args.out.resolve()
    require(HERE not in args.out.parents and args.out != HERE, 'Keep generated output outside the patch source directory')
    require(not args.out.exists(), 'Output directory must be new')
    spec = json.loads((HERE / 'patch.json').read_text())
    require(sha(args.stock.read_bytes()) == spec['stock_sha256'],
            'Wrong stock firmware hash; requires full PEN-F 3101 container')
    toolchain = ROOT / 'toolchains/mn103-patch-build'
    assembler = executable(args.assembler, 'as', toolchain / 'gas/as-new')
    linker = executable(args.linker, 'ld', toolchain / 'ld/ld-new')
    objcopy = executable(args.objcopy, 'objcopy', toolchain / 'binutils/objcopy')
    args.out.mkdir(parents=True)

    # 1. The HSL release this patch is layered on, rebuilt and checked by its own
    #    builder through its command line.
    base_dir = args.out / 'base-hsl'
    subprocess.run([sys.executable, str(HSL_BUILDER), '--stock', str(args.stock.resolve()),
                    '--out', str(base_dir), '--as', assembler, '--ld', linker, '--objcopy', objcopy],
                   check=True)
    base = (base_dir / 'install/DCOLYMP/E1229999.BIN').read_bytes()
    require(sha(base) == spec['base_package_sha256'], 'HSL base package differs')
    blocks = parse(base)
    require([b.kind for b in blocks] == [0x100, 0x101], 'Unexpected HSL component order')
    main = bytearray(blocks[0].payload)
    require(sha(main) == spec['base_main_sha256'], 'HSL base main differs')

    # 2. Check every original range against the HSL main.
    cpu = int(spec['cpu_base'], 16)
    ranges = sorted(spec['main_ranges'], key=lambda x: int(x['address'], 16))
    for i, row in enumerate(ranges):
        at, size = int(row['address'], 16) - cpu, row['bytes']
        require(0 <= at < at + size <= len(main), f'Invalid range: {row["name"]}')
        require(sha(main[at:at+size]) == row['before_sha256'], f'Original bytes differ: {row["name"]}')
        if i:
            prior = ranges[i-1]
            require(int(prior['address'], 16) + prior['bytes'] <= at + cpu, 'Overlapping patch ranges')
    expected = {(x['name'], int(x['address'], 16)): x for x in ranges}
    written = set()

    def install(name, address, data):
        key = name, address
        require(key in expected and key not in written, f'Unexpected or repeated section: {key}')
        row = expected[key]
        require(len(data) == row['bytes'], f'Section size differs: {name}: {len(data)} != {row["bytes"]}')
        require(sha(data) == row['after_sha256'], f'Compiled bytes differ from reference: {name}')
        main[address-cpu:address-cpu+len(data)] = data
        written.add(key)

    # 3. Assemble the helpers; stock call targets are defined in each layout.ld.
    for group in spec['groups']:
        folder = args.out / 'assembly' / group['name']
        folder.mkdir(parents=True)
        objects = []
        for source in group['sources']:
            obj = folder / (Path(source).stem + '.o')
            subprocess.run([assembler, '-o', str(obj), str(HERE / source)], check=True)
            objects.append(str(obj))
        elf = folder / 'patch.elf'
        subprocess.run([linker, '--no-relax', '-e', '0', '-T', str(HERE / group['linker']),
                        '-o', str(elf), *objects], check=True)
        for name, address in group['sections'].items():
            output = folder / (name + '.bytes')
            subprocess.run([objcopy, '-O', 'binary', '--only-section=.' + name, str(elf), str(output)], check=True)
            install(name, int(address, 16), output.read_bytes())
    for edit in spec['data_edits']:
        install(edit['name'], int(edit['address'], 16), bytes.fromhex(edit['after']))
    require(written == set(expected), 'Not every declared patch range was produced')
    require(sha(main) == spec['main_sha256'], 'Decoded main differs from reference')

    # 4. Re-encode; the OSD component is HSL's, unchanged.
    package = reconstruct([replace_payload(blocks[0], main), blocks[1]])
    require(len(package) == spec['package_bytes'] and sha(package) == spec['package_sha256'],
            'Package differs from the tested build')
    verified = parse(package)
    require(verified[0].payload == main and verified[1].payload == blocks[1].payload, 'Container round trip failed')
    require(sha(verified[1].payload) == spec['osd_sha256'], 'OSD differs from HSL')
    require(all(a.header == b.header and a.trailer[:28] == b.trailer[:28] for a, b in zip(verified, blocks)),
            'Component metadata changed')
    restore = (base_dir / 'restore-stock/DCOLYMP/E1229999.BIN').read_bytes()
    require(sha(restore) == spec['stock_restore_sha256'], 'Restore package differs')
    for path, data in [('install/DCOLYMP/E1229999.BIN', package), ('restore-stock/DCOLYMP/E1229999.BIN', restore)]:
        target = args.out / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    report = {'release': spec['release'], 'base_release': spec['base_release'],
              'stock_sha256': spec['stock_sha256'], 'package_sha256': sha(package),
              'restore_sha256': sha(restore), 'main_sha256': sha(main), 'package_bytes': len(package),
              'patch_ranges': len(ranges),
              'main_changed_bytes_vs_hsl': sum(a != b for a, b in zip(main, blocks[0].payload)),
              'exact_tested_build_match': True,
              'tool_versions': {name: subprocess.check_output([tool, '--version'], text=True).splitlines()[0]
                                for name, tool in [('as', assembler), ('ld', linker), ('objcopy', objcopy)]},
              'source_sha256': {str(p.relative_to(HERE)): sha(p.read_bytes()) for p in sorted(HERE.rglob('*'))
                                if p.is_file() and '__pycache__' not in p.parts},
              'camera_access': False}
    (args.out / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('exact_tested_build_match', 'package_sha256', 'package_bytes',
                                             'main_changed_bytes_vs_hsl')}, indent=2))


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
