#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Read-only checks of cmdada's E-M10 I 1.4 source against stock firmware.

Reads patch constants with Python's AST, without importing the contributor's
patcher. Produces facts and hashes, never a modified firmware image.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import struct

from oly_container import parse, reconstruct

STOCK_SHA256 = '84d81b2dbd80ea2e94ec70e35acbba0e3193ccee8b51db14976fd0d9c4e3590c'
BASE = 0x7D991020
TABLE = 0x7D9988E8


def digest(data):
    return hashlib.sha256(data).hexdigest()


def literal(node):
    """Only literal addresses/hex strings and the patcher's little-endian form."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, str)):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return literal(node.left) + literal(node.right)
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == 'le' and len(node.args) == 1 and not node.keywords):
        return struct.pack('<I', literal(node.args[0])).hex(' ')
    raise ValueError('not a supported literal expression')


def audit(firmware, upstream):
    encoded = firmware.read_bytes()
    if digest(encoded) != STOCK_SHA256:
        raise ValueError('requires exact E-M10 I 1.4 stock container')
    blocks = parse(encoded)
    main = blocks[0].payload
    source = upstream / 'tools/patch.py'
    tree = ast.parse(source.read_text())
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    guards = []
    # Inspect only existing-code guards in the plugin function. Three injected
    # blobs have build-dependent lengths and are deliberately not evaluated.
    for node in ast.walk(funcs['plugins']):
        if not isinstance(node, ast.Tuple) or len(node.elts) != 3:
            continue
        try:
            address, expected = literal(node.elts[0]), literal(node.elts[1])
        except ValueError:
            continue
        if not isinstance(address, int) or not isinstance(expected, str):
            continue
        preimage = bytes.fromhex(expected)
        actual = main[address - BASE:address - BASE + len(preimage)]
        guards.append({'address': hex(address), 'bytes': len(preimage),
                       'matches_stock': actual == preimage})
    if len(guards) != 22 or not all(g['matches_stock'] for g in guards):
        raise ValueError(f'expected 22 matching plugin hook guards, got {guards}')
    sections = []
    for i in range(6):
        end, start, flash, destination = struct.unpack_from('<4I', main, TABLE - BASE + 16 * i)
        sections.append({'index': i, 'end': hex(end), 'start': hex(start),
                         'logical_source': hex(flash), 'destination': hex(destination),
                         'bytes': end - start})
    before = main[TABLE - BASE:TABLE - BASE + 4]
    after = struct.pack('<I', 0x7DD00000)
    if before != struct.pack('<I', 0x7DC9D800):
        raise ValueError('section end differs')
    padding = []
    for name, low, high in [('loader', 0x7DC9D803, 0x7DD00000),
                            ('plugin_arena', 0x7E600000, 0x7E6A0000)]:
        data = main[low - BASE:high - BASE]
        padding.append({'name': name, 'start': hex(low), 'end': hex(high),
                        'bytes': len(data), 'all_ff': all(x == 255 for x in data),
                        'sha256': digest(data)})
    movie = main[0x7DE7225B - BASE:0x7DE7225B - BASE + 3]
    if movie != bytes.fromhex('2c cc 06') or not all(p['all_ff'] for p in padding):
        raise ValueError('movie operand or candidate padding differs')
    important = ['README.md', 'notes/system.md', 'notes/plugins.md', 'tools/patch.py',
                 'plugins/loader/loader.c', 'plugins/loader/fw.S', 'plugins/loader/loader.ld',
                 'plugins/sdk/em10.h', 'plugins/sysdump/sysdump.c', 'tools/emp.py',
                 'emu/main.c', 'emu/hle.c', 'emu/emu.h', 'emu/mem.c']
    return {
        'format': 'em10-source-audit-v1', 'tool_sha256': digest(Path(__file__).read_bytes()),
        'firmware_sha256': digest(encoded),
        'roundtrip_identical': reconstruct(blocks) == encoded,
        'components': [b.metadata() for b in blocks],
        'section_table': sections, 'plugin_hook_guards': guards,
        'load_padding': {'changed_bytes': sum(a != b for a, b in zip(before, after)),
                         'additional_copy_bytes': 0x7DD00000 - 0x7DC9D800},
        'candidate_padding': padding,
        'movie_duration': {'instruction': hex(0x7DE7225B), 'stock_seconds': 1740,
                           'proposed_seconds': 32767, 'continuous_recording_verified': False},
        'upstream_source_hashes': {name: digest((upstream / name).read_bytes()) for name in important},
        'scope': 'Static stock/source checks only. No loader build, device I/O or reset-path proof.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firmware', type=Path, required=True)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('output already exists')
    result = audit(args.firmware, args.upstream)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(f"Verified {len(result['plugin_hook_guards'])} hook guards, six descriptors and container roundtrip.")


if __name__ == '__main__':
    main()
