#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Regenerate an indexed disassembly window from an explicitly supplied image."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--entry', required=True, help='Original analysis/.../*.asm path from inventory')
    p.add_argument('--image', type=Path, required=True, help='Exact decoded input you supply')
    p.add_argument('--objdump', type=Path, required=True)
    p.add_argument('--base', type=lambda x: int(x, 0), required=True,
                   help='CPU mapping base, not container address')
    p.add_argument('--machine', default='mn10300')
    p.add_argument('--segment', type=int, help='Zero-based contiguous segment if a listing combines windows')
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    items = json.loads((ROOT / 'provenance/disassembly-windows.json').read_text())
    matches = [x for x in items if x['path'] == a.entry or a.entry in x.get('aliases', [])]
    if len(matches) != 1:
        p.error('Inventory path must match exactly one window')
    item = matches[0]
    if 'start' not in item or 'stop_exclusive' not in item:
        p.error('No reliable instruction boundaries; consult the original probe source')
    digest = hashlib.sha256(a.image.read_bytes()).hexdigest()
    known = item.get('input_images', [])
    if len({x['sha256'] for x in known}) > 1:
        p.error('This listing combines different inputs; use its original probe/disassembly source')
    if known and digest not in {x['sha256'] for x in known}:
        p.error('Input SHA-256 differs from every known image for this window')
    segments = item.get('segments', [{'start': item['start'], 'stop_exclusive': item['stop_exclusive']}])
    if len(segments) > 1 and a.segment is None:
        p.error(f'Listing contains {len(segments)} separate windows; select one using --segment')
    index = a.segment if a.segment is not None else 0
    if not 0 <= index < len(segments):
        p.error('Segment outside inventory bounds')
    start, stop = int(segments[index]['start'], 0), int(segments[index]['stop_exclusive'], 0)
    if not a.base <= start < stop <= a.base + a.image.stat().st_size:
        p.error('Window outside supplied image mapping')
    if a.out.exists():
        p.error('Output already exists; choose a fresh path')
    cmd = [str(a.objdump.resolve()), '-b', 'binary', '-m', a.machine, '-D', '-z',
           '--insn-width=16', f'--adjust-vma={a.base:#x}',
           f'--start-address={start:#x}', f'--stop-address={stop:#x}', str(a.image.resolve())]
    result = subprocess.run(cmd, check=True, capture_output=True)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(result.stdout)
    print(json.dumps({'entry': a.entry, 'input_sha256': digest,
                      'known_input_verified': bool(known), 'output': str(a.out),
                      'output_sha256': hashlib.sha256(result.stdout).hexdigest(),
                      'note': 'Raw objdump output; annotations/tool versions can change the text hash.'}, indent=2))


if __name__ == '__main__':
    main()
