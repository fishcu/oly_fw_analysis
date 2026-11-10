"""Freeze a task-context probe's actual sources, inputs, and outputs; never rewrites a snapshot."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]

def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def freeze(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if digest(source) != digest(target):
            raise ValueError(f'Refusing to replace archived input: {target}')
    else:
        shutil.copyfile(source, target)

def record(run, probe):
    run = run.resolve()
    if not run.is_relative_to(ROOT / 'analysis/button-af/readiness'):
        raise ValueError('Run must be inside the research readiness directory')
    name = probe
    while name:
        src = ROOT / 'scripts' / f'{name}.java'
        if not src.exists():
            break
        freeze(src, run / 'source-snapshot' / src.name)
        match = re.search(r'public class \w+ extends (\w+)', src.read_text(encoding='utf-8-sig'))
        name = match.group(1) if match else None
    freeze(Path(__file__), run / 'source-snapshot' / Path(__file__).name)
    for name in ('mn103_base.sinc', 'mn103_mn10300.sla'):
        src = ROOT / 'tooling/ghidra_12.2_PUBLIC/Ghidra/Extensions/MN10300/data/languages' / name
        freeze(src, run / 'input-snapshot' / name)
    freeze(ROOT / 'analysis/button-af/readiness/hook-core1/observations.txt', run / 'input-snapshot/hook-core-observations.txt')
    files = [p for p in run.rglob('*') if p.is_file() and p.name != 'task-context-evidence-manifest.json']
    files.append(ROOT / 'analysis/decoded/00_0100_50000020.decoded.bin')
    manifest = {'probe': probe, 'scope': 'Offline, declared OS/device/context models; no hardware validation or installable image.',
                'sha256': {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(files)}}
    target = run / 'task-context-evidence-manifest.json'
    if target.exists() and json.loads(target.read_text()) != manifest:
        raise ValueError('Refusing to change existing manifest')
    target.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    mismatches = [name for name, expected in manifest['sha256'].items() if digest(ROOT / name) != expected]
    if mismatches:
        raise ValueError(mismatches)
    print(f'Archived and verified {len(files)} inputs/outputs: {target}')

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('run', type=Path)
    ap.add_argument('--probe', required=True)
    args = ap.parse_args()
    record(args.run, args.probe)
