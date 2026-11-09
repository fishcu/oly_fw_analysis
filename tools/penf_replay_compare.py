#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Compare complete replay bytes, allowing only explicitly changed source pins.

Streaming comparison avoids loading two multi-million-record traces into RAM.
Gzip headers/compression are excluded; decompressed JSON otherwise must match.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path


def compare_gzip(left, right, substitutions=()):
    substitutions = [(a.encode(), b.encode()) for a, b in substitutions]
    if any(len(a) != len(b) for a, b in substitutions):
        raise ValueError('Only equal-length source-pin substitutions are supported')
    margin = max((len(a) for a, b in substitutions), default=1)-1
    counts = [0]*len(substitutions)
    digest = hashlib.sha256()
    offset, pending = 0, b''
    with gzip.open(left, 'rb') as before, gzip.open(right, 'rb') as after:
        while True:
            chunk = before.read(1024*1024)
            data = pending+chunk
            # Keep a possible partial match across reads. Replace only matches
            # beginning before the cut; their suffix may extend into pending.
            cut = max(0, len(data)-margin) if chunk else len(data)
            for index, (old, new) in enumerate(substitutions):
                start = 0
                while True:
                    found = data.find(old, start)
                    if found < 0 or found >= cut:
                        break
                    data = data[:found]+new+data[found+len(old):]
                    counts[index] += 1
                    start = found+len(new)
            part, pending = data[:cut], data[cut:]
            other = after.read(len(part))
            if part != other:
                mismatch = next((i for i, (a, b) in enumerate(zip(part, other)) if a != b),
                                min(len(part), len(other)))
                raise AssertionError(f'{left.name}: decompressed mismatch at byte {offset+mismatch}')
            digest.update(part)
            offset += len(part)
            if not chunk:
                assert not after.read(1), 'Second replay has extra data'
                break
    assert counts == [1]*len(substitutions), ('Source pins must each occur exactly once', counts)
    return dict(bytes=offset, normalized_sha256=digest.hexdigest(), source_pin_replacements=sum(counts))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=Path)
    parser.add_argument('after', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    before = json.loads((args.before/'summary.json').read_text())
    after = json.loads((args.after/'summary.json').read_text())
    old_sources, new_sources = before.pop('source_sha256'), after.pop('source_sha256')
    assert before == after, 'Summary differs beyond source hashes'
    assert old_sources.keys() == new_sources.keys(), 'Source inventory changed'
    changed = {name:dict(before=digest, after=new_sources[name]) for name, digest in old_sources.items()
               if digest != new_sources[name]}
    substitutions = [(json.dumps(name)+': '+json.dumps(values['before']),
                      json.dumps(name)+': '+json.dumps(values['after'])) for name, values in changed.items()]
    result = dict(before=str(args.before), after=str(args.after), changed_sources=changed,
                  summary_equal_except_source_hashes=True,
                  trace=compare_gzip(args.before/'trace.json.gz', args.after/'trace.json.gz', substitutions),
                  snapshot=compare_gzip(args.before/'state.json.gz', args.after/'state.json.gz'))
    args.out.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
