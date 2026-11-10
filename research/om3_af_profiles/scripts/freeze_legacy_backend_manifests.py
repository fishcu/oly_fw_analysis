"""Preserve old evidence indexes when a shared window list gains a new row.

Execution outputs and expected content hashes are unchanged. Original indexes
are retained, and moved references point to byte-identical historical copies.
"""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def migrate(run):
    index = run / 'class-aware-evidence-manifest.json'
    original = index.read_bytes()
    value = json.loads(original)
    moves = []
    for name, expected in list(value['sha256'].items()):
        source = ROOT / name
        if digest(source.read_bytes()) == expected:
            continue
        if name == 'analysis/review/device-dispatch/windows.tsv':
            # The historical list had nine windows; a later request-builder
            # decode appended one independent window to the shared list.
            content = b''.join(source.read_bytes().splitlines(keepends=True)[:9])
        elif source.name == 'class-aware-evidence-manifest.json':
            content = source.with_name('manifest-before-static-snapshot.json').read_bytes()
        else:
            raise ValueError(f'No historical resolution for {name}')
        if digest(content) != expected:
            raise ValueError(f'Historical content does not match expected hash: {name}')
        target = run / 'evidence-snapshot' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != content:
            raise ValueError(f'Conflicting snapshot: {target}')
        target.write_bytes(content)
        new_name = target.relative_to(ROOT).as_posix()
        del value['sha256'][name]
        value['sha256'][new_name] = expected
        moves.append({'original_path': name, 'snapshot_path': new_name, 'unchanged_sha256': expected})
    if not moves:
        return
    backup = run / 'manifest-before-static-snapshot.json'
    if backup.exists():
        raise ValueError('An original manifest backup already exists')
    backup.write_bytes(original)
    updated = (json.dumps(value, indent=2) + '\n').encode('utf-8')
    index.write_bytes(updated)
    audit = {'reason': 'Shared disassembly window list grew after execution; preserve historical bytes instead of following mutable paths.',
             'execution_data_modified': False, 'expected_content_hashes_modified': False,
             'original_manifest_sha256': digest(original), 'updated_manifest_sha256': digest(updated), 'references_moved': moves}
    (run / 'manifest-snapshot-migration.json').write_text(json.dumps(audit, indent=2) + '\n', encoding='utf-8')
    print(run.name, len(moves), 'references frozen; expected hashes unchanged')


if __name__ == '__main__':
    for name in ('missing-device1', 'missing-device2', 'constructor-group-queue10-4'):
        migrate(ROOT / 'analysis/button-af/readiness' / name)
