#!/usr/bin/env python3
"""Check the bounded stock WB preparation route before changing capture timing.

This is a static, hash-pinned audit. It does not establish task scheduling,
capture completion, or behaviour on a camera.
"""
import argparse
import hashlib
import json
from pathlib import Path

BASE = 0x60021020
STOCK_SHA256 = '5e8d376e9111a44ac0352f26030d7c1b17026d42c45f3600cfa02a0e8c5b7d59'

# Exact instruction bytes from the stock OM-3 1100 image. Each call is followed
# by its target in the report; comparing the bytes guards against stale tracing.
SITES = {
    'ui_setter_entry': (0x60aea1de, '938782', None),
    'ui_setter_settings_call': (0x60aea1f3, 'dd275f90ff0004', 0x603f011a),
    'stock_commit_entry': (0x603f1ea1, 'f1e6831f8c', None),
    'queued_preparation_call': (0x603e37e2, 'cd2256f02c', 0x603e8e04),
    'other_preparation_call': (0x603e6325, 'cddf2af02c', 0x603e8e04),
    'kelvin_snapshot_store': (0x603e8e9d, 'fc720a930000', None),
    'formatter_entry_call': (0x603e8f44, 'dd38bc06000004', 0x60454b7c),
    'formatter_sync_call': (0x60454b7c, 'cd171cf0ac', 0x60456793),
    'formatter_return': (0x60454b81, 'df0004', None),
    'live_ab_read': (0x60457c44, 'fcccf9840000', None),
    'live_gm_read': (0x60457c5d, 'fccc79960000', None),
}


def audit(data):
    digest = hashlib.sha256(data).hexdigest()
    if digest != STOCK_SHA256:
        raise ValueError(f'expected stock decoded OM-3 1100 main, got {digest}')
    for label, (address, expected_hex, _) in SITES.items():
        expected = bytes.fromhex(expected_hex)
        actual = data[address - BASE:address - BASE + len(expected)]
        if actual != expected:
            raise ValueError(f'{label} changed at {address:08x}')
    return {
        'image_sha256': digest,
        'sites': {label: {'address': f'{address:08x}',
                          **({'direct_target': f'{target:08x}'} if target else {})}
                  for label, (address, _, target) in SITES.items()},
        'bounded_result': 'Kelvin store and live tint reads are in one synchronous call chain; the existing commit hook is downstream of the UI setter',
        'unverified': ['preemption and settings lock', 'all capture entry routes',
                       'outstanding burst count', 'completion task/context',
                       'RAW/development lifetime', 'physical camera behaviour'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('decoded_main', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.decoded_main.read_bytes()), indent=2))


if __name__ == '__main__':
    main()
