#!/usr/bin/env python3
"""Reproduce the PEN-F electronic aperture-ring patch, with optional HSL.

Requires an exact, separately obtained stock container and GNU MN103 tools.
The standalone build is main-only; the HSL combination includes main and OSD.
No network or camera access.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from oly_container import parse, reconstruct, replace_payload

MODELS = ('pen-f', 'pen-f-hsl')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_spec(model):
    require(model in MODELS, 'Unsupported camera model')
    folder = HERE/model
    spec = json.loads((folder/'patch.json').read_text())
    for name, digest in spec['source_sha256'].items():
        require(sha((folder/name).read_bytes()) == digest, 'Source differs from tested patch: '+name)
    for name, digest in spec.get('extra_source_sha256', {}).items():
        require(sha((ROOT/name).read_bytes()) == digest, 'Referenced HSL source differs: '+name)
    return spec


def stock_blocks(data, spec):
    require(sha(data) == spec['stock_container_sha256'], 'Wrong full stock container SHA-256')
    blocks = parse(data)
    require(len(blocks) == spec['component_count'] and blocks[0].kind == 0x100,
            'Unexpected stock component layout')
    require(sha(blocks[0].payload) == spec['original_main_sha256'], 'Wrong decoded main SHA-256')
    require(reconstruct(blocks) == data, 'Stock container failed exact round trip')
    return blocks


def apply_sections(original, base, ranges, sections):
    """Apply only complete, nonoverlapping, original- and compiled-hash guards."""
    names = [row['name'] for row in ranges]
    require(len(names) == len(set(names)) and set(names) == set(sections),
            'Missing, repeated or unexpected patch section')
    result = bytearray(original)
    previous_end = 0
    for row in sorted(ranges, key=lambda r: int(r['address'], 16)):
        offset, size = int(row['address'], 16)-base, row['bytes']
        require(size > 0 and 0 <= offset < offset+size <= len(original), 'Patch range outside main')
        require(offset >= previous_end, 'Overlapping patch sections')
        previous_end = offset+size
        before, after = original[offset:offset+size], sections[row['name']]
        require(sha(before) == row['before_sha256'], 'Original bytes differ: '+row['name'])
        require(len(after) == size and sha(after) == row['after_sha256'],
                'Compiled bytes differ from tested patch: '+row['name'])
        result[offset:offset+size] = after
    return bytes(result)


def packages(blocks, main, spec, osd=None):
    require(sha(main) == spec['patched_main_sha256'], 'Decoded main differs from tested patch')
    changed = [replace_payload(blocks[0], main)]
    if 'hsl_release' in spec:
        require(osd is not None and sha(osd) == spec['hsl_osd_sha256'], 'Exact HSL OSD is required')
        changed.append(replace_payload(blocks[1], osd))
    else:
        require(osd is None, 'Standalone aperture patch must replace only main')
    install = reconstruct(changed)
    restore = reconstruct(blocks[:len(changed)])
    require(len(install) == len(restore) == spec['package_bytes'], 'Main write extent changed')
    require(sha(install) == spec['install_sha256'], 'Encoded install differs from tested BIN')
    require(sha(restore) == spec['restore_sha256'], 'Encoded restore differs from stock main')
    for data, expected in ((install, changed), (restore, blocks[:len(changed)])):
        decoded = parse(data)
        require(len(decoded) == len(expected) and all(a.payload == b.payload for a, b in zip(decoded, expected)),
                'Package round trip failed')
        require(all(a.header == b.header and a.trailer[:28] == b.trailer[:28]
                    for a, b in zip(decoded, blocks)), 'Original update metadata changed')
    return install, restore


def range_intersections(left, right):
    return [dict(left=a['name'], right=b['name'], start=hex(max(int(a['address'], 16), int(b['address'], 16))),
                 end_exclusive=hex(min(int(a['address'], 16)+a['bytes'], int(b['address'], 16)+b['bytes'])))
            for a in left for b in right
            if max(int(a['address'], 16), int(b['address'], 16)) <
               min(int(a['address'], 16)+a['bytes'], int(b['address'], 16)+b['bytes'])]


def compose_hsl(args, spec, blocks, assembler, linker, objcopy):
    """Rebuild exact HSL, reclaim only its ORF group, preserve every other edit."""
    source = ROOT/'patches/hsl/pen-f'
    hsl_spec = json.loads((source/'patch.json').read_text())
    require(hsl_spec['release'] == spec['hsl_release'] and
            hsl_spec['stock_sha256'] == spec['stock_container_sha256'], 'HSL reference differs')
    reference = args.out.resolve()/'hsl-reference'
    subprocess.run([sys.executable, str(source/'build.py'), '--stock', str(args.stock.resolve()),
                    '--out', str(reference), '--as', assembler, '--ld', linker, '--objcopy', objcopy], check=True)
    raw = (reference/'install/DCOLYMP'/spec['sd_filename']).read_bytes()
    require(sha(raw) == spec['hsl_install_sha256'], 'HSL baseline package differs')
    hsl = parse(raw)
    require(sha(hsl[0].payload) == spec['hsl_original_main_sha256'] and
            sha(hsl[1].payload) == spec['hsl_osd_sha256'], 'HSL payloads differ')
    group = next(g for g in hsl_spec['groups'] if 'native_orf_hook' in g['sections'])
    keys = {(n, a) for n, a in group['sections'].items()}
    require(keys == {(r['name'], r['address']) for r in spec['hsl_relocated_sections']},
            'Relocated ORF group differs')
    main = bytearray(hsl[0].payload)
    preserved = []
    for row in hsl_spec['main_ranges']:
        if (row['name'], row['address']) not in keys:
            preserved.append(row)
            continue
        at = int(row['address'], 16)-int(spec['cpu_base'], 16)
        require(sha(main[at:at+row['bytes']]) == row['after_sha256'], 'HSL ORF bytes differ')
        main[at:at+row['bytes']] = blocks[0].payload[at:at+row['bytes']]
    require(not range_intersections(spec['ranges'], preserved), 'Composition overlaps a retained HSL range')
    return bytes(main), hsl[1].payload, raw, preserved


def executable(explicit, name, local):
    value = explicit or shutil.which('mn10300-elf-'+name)
    if value is None and local.is_file():
        value = str(local)
    require(value is not None, 'Missing MN103 '+name+'; supply --'+name)
    return str(Path(value).resolve())


def build(args):
    spec = load_spec(args.model)
    out = args.out.resolve()
    require(HERE != out and HERE not in out.parents, 'Keep output outside the patch source directory')
    require(not out.exists(), 'Output directory must be new')
    blocks = stock_blocks(args.stock.read_bytes(), spec)
    tc = ROOT/'toolchains/mn103-patch-build'
    assembler = executable(args.assembler, 'as', tc/'gas/as-new')
    linker = executable(args.linker, 'ld', tc/'ld/ld-new')
    objcopy = executable(args.objcopy, 'objcopy', tc/'binutils/objcopy')
    original = blocks[0].payload
    osd, hsl_restore, preserved = None, None, []
    if 'hsl_release' in spec:
        original, osd, hsl_restore, preserved = compose_hsl(args, spec, blocks, assembler, linker, objcopy)
    # Preserve the exact source that this build actually assembles.
    source = out/'source'
    source.mkdir(parents=True)
    for name in (*spec['source_sha256'], 'patch.json'):
        shutil.copy2(HERE/args.model/name, source/name)
    for name in spec.get('extra_source_sha256', {}):
        target = source/Path(name).name
        require(not target.exists(), 'Repeated assembly source basename')
        shutil.copy2(ROOT/name, target)
    objects, elf = [], out/'ring.elf'
    for path in sorted(source.iterdir()):
        if path.suffix not in ('.s', '.S'):
            continue
        obj = out/(path.stem+'.o')
        subprocess.run([assembler, str(path), '-o', str(obj)], check=True)
        objects.append(str(obj))
    subprocess.run([linker, '--no-relax', '-T', str(source/'layout.ld'), *objects, '-o', str(elf)], check=True)
    sections = {}
    for row in spec['ranges']:
        name = row['name']
        target = out/(name+'.bin')
        subprocess.run([objcopy, '-O', 'binary', '--only-section=.'+name, str(elf), str(target)], check=True)
        sections[name] = target.read_bytes()
    main = apply_sections(original, int(spec['cpu_base'], 16), spec['ranges'], sections)
    for row in preserved:
        at = int(row['address'], 16)-int(spec['cpu_base'], 16)
        require(sha(main[at:at+row['bytes']]) == row['after_sha256'], 'Retained HSL edit changed')
    install, restore = packages(blocks, main, spec, osd)
    (out/'decoded-main.bin').write_bytes(main)
    files = []
    payloads = [('install', install), ('restore-stock', restore)]
    if hsl_restore is not None:
        payloads.append(('restore-hsl', hsl_restore))
    for folder, data in payloads:
        path = out/folder/'DCOLYMP'/spec['sd_filename']
        path.parent.mkdir(parents=True)
        with path.open('xb') as f:
            f.write(data)
        files.append(dict(path=str(path.relative_to(out)), bytes=len(data), sha256=sha(data)))
    report = dict(model=spec['model'], version=spec['version'], build=spec['build'],
        reference_patch=spec['reference_patch'], stock_container_sha256=spec['stock_container_sha256'],
        original_main_sha256=spec['original_main_sha256'], patched_main_sha256=sha(main),
        files=files, ranges=spec['ranges'], included_components=['0x100']+(['0x101'] if osd is not None else []),
        omitted_unchanged_components=[hex(b.kind) for b in blocks[2 if osd is not None else 1:]],
        main_changed_bytes=sum(a != b for a, b in zip(main, blocks[0].payload)),
        exact_reference_bytes_reproduced=True, original_metadata_preserved=True,
        camera_report=spec['camera_report'],
        hsl_non_orf_ranges_preserved=True if preserved else None,
        source_sha256={str(p.relative_to(HERE)): sha(p.read_bytes()) for p in
            [HERE/'build.py', HERE/args.model/'patch.json', *[HERE/args.model/n for n in spec['source_sha256']]]},
        extra_source_sha256=spec.get('extra_source_sha256', {}),
        tool_versions={name: subprocess.check_output([tool, '--version'], text=True).splitlines()[0]
            for name, tool in (('as', assembler), ('ld', linker), ('objcopy', objcopy))},
        camera_access=False,
        scope='Exact source/stock/compiled/package hash checks. Contributor camera observations '
              'are documented separately from this offline build. No camera is accessed; '
              'update recovery, measured exposure accuracy and universal lens support are not inferred.')
    (out/'build.json').write_text(json.dumps(report, indent=2)+'\n')
    (out/'SHA256SUMS').write_text(''.join(f"{x['sha256']}  {x['path']}\n" for x in files))
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', choices=MODELS, required=True)
    p.add_argument('--stock', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--as', dest='assembler')
    p.add_argument('--ld', dest='linker')
    p.add_argument('--objcopy')
    args = p.parse_args()
    try:
        r = build(args)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        p.exit(1, f'Build failed: {error}\n')
    print(json.dumps({k: r[k] for k in ('model', 'reference_patch', 'patched_main_sha256',
                                        'files', 'exact_reference_bytes_reproduced')}, indent=2))


if __name__ == '__main__':
    main()
