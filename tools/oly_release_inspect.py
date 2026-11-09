#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Inspect azqeurio's pinned release as data; never execute its Windows program.

Reads only profiles.json from the PyInstaller archive. Reports patch locations
and hashes without redistributing patch bytes. No network, camera or BIN output.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import struct
import zlib

EXE_SHA256 = '994927d6ccfe31cf6b944ac509186e10f51bf739082e2799104d04460a316435'
RELEASE = 'https://github.com/azqeurio/om-c-firmware/releases/tag/dbv0.3.2'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def profiles_from_exe(path):
    data = path.read_bytes()
    require(sha(data) == EXE_SHA256, 'Requires the pinned db.firmware.0.3.2.exe')
    magic = b'MEI\x0c\x0b\x0a\x0b\x0e'
    cookie = data.rfind(magic)
    require(cookie >= 0 and cookie + 88 <= len(data), 'Missing CArchive cookie')
    _, size, toc_offset, toc_size, version, _ = struct.unpack_from('!8sIIII64s', data, cookie)
    start = cookie + 88 - size
    pos, end = start + toc_offset, start + toc_offset + toc_size
    require(0 <= start <= pos < end <= cookie and version == 312, 'Invalid CArchive layout')
    found = []
    while pos < end:
        length, offset, packed, unpacked, compressed, kind = struct.unpack_from('!iIIIBc', data, pos)
        require(length >= 19 and pos + length <= end, 'Invalid CArchive entry')
        name = data[pos + 18:pos + length].split(b'\0')[0].decode('utf-8')
        if name == 'profiles.json':
            require(kind == b'b' and compressed in (0, 1), 'Unexpected profiles member type')
            require(0 <= offset <= offset + packed <= toc_offset, 'Member outside package')
            raw = data[start + offset:start + offset + packed]
            raw = zlib.decompress(raw) if compressed else raw
            require(len(raw) == unpacked, 'Member length mismatch')
            found.append(json.loads(raw))
        pos += length
    require(len(found) == 1, 'Expected exactly one profiles.json')
    return found[0]


def ring_feature(profile):
    return next(f for f in profile['features'] if f['id'] == 'ring-native')


def patch_records(profile):
    records = []
    for p in ring_feature(profile)['patches']:
        old, new = (base64.b64decode(p[k], validate=True) for k in ('old', 'new'))
        require(len(old) == len(new), 'Length-changing patch')
        address = profile['runtime_base'] + p['offset'] if p['block'] == 0 else None
        record = dict(label=p['label'], block=p['block'], offset=p['offset'],
                      address=hex(address) if address is not None else None,
                      bytes=len(new), changed=sum(a != b for a, b in zip(old, new)),
                      old_sha256=sha(old), new_sha256=sha(new))
        if address is not None and new[:1] == b'\xdc':
            record['jump_target'] = hex(address + struct.unpack_from('<i', new, 1)[0])
        records.append(record)
    return records


def patched_main(profile, stock):
    """Analysis buffer only. Does not encode or write an update container."""
    result = bytearray(stock)
    spans = []
    for p in ring_feature(profile)['patches']:
        require(p['block'] == 0, 'Feature unexpectedly changes another component')
        old, new = (base64.b64decode(p[k], validate=True) for k in ('old', 'new'))
        a, z = p['offset'], p['offset'] + len(old)
        require(0 <= a < z <= len(stock) and len(old) == len(new), 'Invalid patch bounds')
        require(all(z <= x or y <= a for x, y in spans), 'Overlapping patch spans')
        require(stock[a:z] == old, f"Stock bytes differ at {p['label']}")
        result[a:z] = new
        spans.append((a, z))
    return bytes(result)


def inventory(profiles):
    result = []
    for p in profiles:
        f = ring_feature(p)
        sites = patch_records(p)
        result.append(dict(model=p['body'], version=p['version'], id=p['id'],
                           source_sha256=p['source_sha256'], source_file=p['dlfile'],
                           feature_ids=[x['id'] for x in p['features']],
                           ring_implementation=f.get('implementation'),
                           ring_payload_sha256=f.get('payload_sha256'),
                           ring_patch_records=len(sites),
                           ring_changed_records=sum(s['changed'] > 0 for s in sites),
                           ring_changed_bytes=sum(s['changed'] for s in sites)))
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('release_exe', type=Path)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    profiles = profiles_from_exe(args.release_exe)
    penf = next(p for p in profiles if p['id'] == 'penf-3.1')
    result = dict(release=RELEASE, asset_sha256=EXE_SHA256, models=inventory(profiles),
                  penf_sites=patch_records(penf),
                  method='Read JSON only; program not executed; no camera access')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f'{len(profiles)} profiles; PEN-F: {sum(s["changed"] for s in result["penf_sites"])} changed main bytes')


if __name__ == '__main__':
    main()
