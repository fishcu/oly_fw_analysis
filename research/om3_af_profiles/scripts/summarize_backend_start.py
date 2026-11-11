"""Summarize the observation-only backend-start probe; no camera access."""
from pathlib import Path
import argparse
from collections import Counter
import hashlib
import json
import re
import struct

ROOT = Path(__file__).resolve().parents[1]

def summarize(run):
    path = run / 'backend-start-observations.txt'
    lines = path.read_text(encoding='utf-8').splitlines()
    counts = Counter(line.split(' ', 1)[0] for line in lines)
    snapshots = []
    for line in lines:
        if not line.startswith('SNAPSHOT obj=') or ' data=' not in line:
            continue
        prefix, raw = line.split(' data=', 1)
        data = bytes.fromhex(raw)
        record = {'description': prefix, 'words': {}}
        for offset in (0x94, 0x98, 0xa8, 0xb0, 0xb4, 0xfc, 0x100, 0x108, 0x164, 0x168):
            if offset + 4 <= len(data):
                record['words'][f'+0x{offset:x}'] = f'{struct.unpack_from("<I", data, offset)[0]:08x}'
        snapshots.append(record)
    result = {'observation_only': True, 'outcome': (run / 'backend-start-outcome.txt').read_text(encoding='utf-8').strip(),
              'line_counts': dict(counts), 'snapshots': snapshots,
              'type_key_observations': [s for s in lines if s.startswith('SNAPSHOT key269')],
              'scope': 'One stock-reset connection with inherited explicit models and silent SCPU; deliberately stops before original buttons.'}
    (run / 'backend-start-summary.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    files = [p for p in run.iterdir() if p.is_file() and p.suffix in ('.txt', '.json', '.log') and p.name != 'evidence-manifest.json']
    sources = [ROOT/'scripts'/name for name in ('OM3BackendStartTrace.java','OM3CaptureAfTaskProof.java',
               'OM3CaptureResetProof.java','OM3CaptureTimeoutProof.java','OM3CaptureLinkProof.java',
               'OM3CaptureKernelModelProof.java','OM3FullShooting.java','summarize_backend_start.py')]
    sources += [ROOT/'tooling/ghidra_12.2_PUBLIC/Ghidra/Extensions/MN10300/data/languages'/name
                for name in ('mn103_base.sinc','mn103_mn10300.sla')]
    sources += [ROOT/'analysis/decoded/00_0100_50000020.decoded.bin']
    hashes = {str(p.relative_to(ROOT)).replace('\\','/'): hashlib.sha256(p.read_bytes()).hexdigest() for p in files+sources}
    (run/'evidence-manifest.json').write_text(json.dumps({'scope': result['scope'], 'sha256': hashes}, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    summarize(parser.parse_args().run.resolve())
