#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Offline packaging/acceptance preflight. Saves JSON only, never update images.

Real main components are assembled only in memory. Native updater writes are
trapped. Fixtures are explicit and do not establish physical boot/recovery.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from oly_container import Block, parse, reconstruct, replace_payload, sum32
from penf_emulator import BASE, ROOT, firmware
from penf_input_recovery_probe import sd_client, sd_service
from penf_probe import BUFFER
from penf_update_probe import update_probe, synthetic_block

STOCK = ROOT / 'firmware_files/OLY_E_122_3101_0000_0000.BIN'
STOCK_SHA = '77398610b379f80238117f31a6d5bbf65d608b49ec563666c64d84367e969f2c'
FIELD = 0x60622d84 - BASE


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(out, name, report):
    (out / (name + '.json')).write_text(json.dumps(report, indent=2) + '\n')


def build_candidate():
    stock = STOCK.read_bytes()
    assert sha(stock) == STOCK_SHA
    blocks = parse(stock)
    assert len(blocks) == 4 and reconstruct(blocks) == stock
    main = blocks[0]
    assert main.kind == 0x100 and main.address == 0x403a0000
    assert main.payload == firmware() and main.payload[FIELD:FIELD+2] == b'\0\0'
    assert struct.unpack_from('<H', main.header, 16)[0] == 0x3101
    payload = bytearray(main.payload)
    struct.pack_into('<h', payload, FIELD, 300)
    candidate = replace_payload(main, payload)
    package = reconstruct([candidate])
    original = reconstruct([main])
    # Independent construction using only the four previously established
    # encoded-file bytes; detects mistakes in transform, checksum or offsets.
    exact = bytearray(original)
    expected = {0x601d84: (0xff, 0xfe), 0x601d86: (0xff, 0xd3),
                0x145fffc: (0x2e, 0x02), 0x145fffd: (0x81, 0x80)}
    for offset, (before, after) in expected.items():
        assert exact[offset] == before
        exact[offset] = after
    assert package == exact
    parsed = parse(package)
    assert len(parsed) == 1 and parsed[0].payload == payload
    full = reconstruct([candidate] + blocks[1:])
    assert len(full) == len(stock) and full[len(package):] == stock[len(package):]
    assert parse(full)[0] == candidate
    report = dict(stock_sha256=sha(stock), stock_roundtrip_identical=True,
        stock_main_sha256=sha(original), candidate_main_sha256=sha(package),
        candidate_full_container_sha256=sha(full), main_bytes=len(package),
        full_container_bytes=len(full), header_unchanged=candidate.header == main.header,
        trailer_metadata_unchanged=candidate.trailer[:28] == main.trailer[:28],
        version_hex='3101', kind_hex='0100', logical_destination=hex(main.address),
        erase_units_128KiB=len(package)//131072,
        encoded_changes=[dict(offset=hex(k), before=hex(v[0]), after=hex(v[1]))
                         for k, v in expected.items()],
        changed_decoded_field_offset=hex(FIELD), native_lightness=300,
        checksum_before=main.trailer[-4:].hex(), checksum_after=candidate.trailer[-4:].hex(),
        unchanged_other_components=[dict(kind=hex(b.kind), bytes=len(b.payload)+64)
                                    for b in blocks[1:]],
        output_policy='JSON only. Candidate packages exist in process memory, not as saved update files.')
    return main, candidate, original, package, report


def check_update(out, name, package, mode, expected_decoded=None, reject=None):
    print('Running ' + name, flush=True)
    report, state = update_probe(package, mode=mode)
    save(out, name, report)  # Retain failures for diagnosis before asserting.
    assert report['returned'], (name, report['pc'], report['events'][-1])
    assert report['result'] == (0 if reject is None else reject), (name, report['result'])
    if reject is not None or mode == 2:
        assert report['write_requests'] == []
    else:
        assert len(report['write_requests']) == 1
        write = report['write_requests'][0]
        assert write['destination'] == '0x803a0000'
        assert write['bytes'] == len(package)
        assert write['input_sha256'] == sha(expected_decoded)
    print(f"  returned {report['result']:#x}; {len(report['write_requests'])} trapped writes; "
          f"{report['instructions']:,} instructions", flush=True)
    return report, state


def version_matrix(out):
    # Small nonfunctional main-component fixtures isolate header version policy.
    base = parse(synthetic_block(kind=0x100, address=0x403a0000))[0]
    rows = []
    for version in (0x0000, 0x0100, 0x3100, 0x3101, 0x3102, 0x9999, 0xffff):
        h = bytearray(base.header)
        struct.pack_into('<H', h, 16, version)
        b = replace_payload(Block(0, 0, bytes(h), base.payload, bytes(h)), base.payload)
        encoded = reconstruct([b])
        decoded = b.header + b.payload + b.trailer
        for mode in (0, 2, 1):
            p = decoded if mode == 1 else encoded
            r, s = update_probe(p, mode)
            row = dict(version=hex(version), mode=mode, returned=r['returned'],
                       result=r['result'], instructions=r['instructions'],
                       writes=len(r['write_requests']))
            rows.append(row)
            assert r['returned'] and r['result'] == 0, row
            assert len(r['write_requests']) == (0 if mode == 2 else 1)
    save(out, 'version-matrix', dict(scope='Native shared updater only; synthetic small main blocks; '
         'running code is stock PEN-F 3101. No Workspace catalog or physical activation.', cases=rows))
    print(f'  {len(rows)} header-version cases passed', flush=True)
    return rows


def sd_chain(out, package):
    r, s = sd_client(package)
    save(out, 'sd-client', r)
    assert r['request'] and r['request']['data_sha256'] == sha(package)
    for active in (False, True):
        report, state = sd_service(package, r['request'], active_task=active)
        save(out, 'sd-service-' + str(int(active)), report)
        dispatch = report['dispatch']
        assert dispatch and dispatch['mode'] == 0 and dispatch['bytes'] == len(package)
        assert dispatch['data_sha256'] == sha(package)
    print('  Native SD client and both service branches forwarded the main-only package', flush=True)


def historical_headers(out):
    paths = [ROOT / 'e-m1_hack/original_fw/3.0/OLY_E_125_3001_0000_0000.BIN',
             ROOT / 'e-m1_hack/hacked_fw/3.0/e1259999.bin']
    blobs = [p.read_bytes() for p in paths]
    blocks = [parse(b) for b in blobs]
    assert len(blocks[0]) == len(blocks[1]) == 5
    rows = []
    for original, hacked in zip(*blocks):
        assert original.header == hacked.header
        assert original.trailer[:28] == hacked.trailer[:28]
        rows.append(dict(kind=hex(original.kind), header_identical=True,
            version=hex(struct.unpack_from('<H', original.header, 16)[0]),
            payload_identical=original.payload == hacked.payload))
    save(out, 'em1ii-precedent', dict(files=[dict(path=str(p.relative_to(ROOT)), sha256=sha(b))
                                          for p, b in zip(paths, blobs)], blocks=rows))
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    main, candidate, original, package, report = build_candidate()
    save(args.out, 'packaging', report)
    historical_headers(args.out)
    version_matrix(args.out)
    sd_chain(args.out, package)
    decoded = candidate.header + candidate.payload + candidate.trailer
    assert sum32(decoded) == 0
    check_update(args.out, 'main-only-SD', package, 0, decoded)
    _, state = check_update(args.out, 'main-only-USB-check', package, 2)
    native_decoded = state.read(BUFFER, len(package))
    assert native_decoded == decoded
    check_update(args.out, 'main-only-USB-commit', native_decoded, 1, decoded)
    # The restored image carries the same 3101 version. This is an acceptance
    # check, not proof that its updater remains reachable on a damaged camera.
    stock_decoded = main.header + main.payload + main.trailer
    check_update(args.out, 'stock-main-SD-restore-acceptance', original, 0, stock_decoded)
    bad = package[:-4] + main.trailer[-4:]
    check_update(args.out, 'main-only-stale-checksum-SD', bad, 0, reject=0x3211)
    report['all_assertions_passed'] = True
    report['sources_sha256'] = {str(path.relative_to(ROOT)): sha(path.read_bytes()) for path in
        (Path(__file__).resolve(), ROOT/'tools/penf_input_recovery_probe.py',
         ROOT/'tools/penf_update_probe.py',ROOT/'tools/penf_probe.py', ROOT/'tools/oly_container.py')}
    save(args.out, 'summary', report)
    print('All preflight checks passed. Only JSON reports saved.', flush=True)


if __name__ == '__main__':
    main()
