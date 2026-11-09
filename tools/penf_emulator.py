#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Strict, offline execution of bounded PEN-F MN103 routines using GNU libsim.

Only explicit memory regions exist. An unknown instruction/access stops the
run; there are no device models, host syscalls, or automatic hardware stubs.
"""
import argparse
from bisect import bisect_left
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from penf_landmarks import BASE, MAIN_SHA256

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / 'toolchains/mn103-gnu-build/penf-mn103'
IMAGE = ROOT / 'analysis/penf_3.1/00_0100_403a0020.decoded.bin'
REGISTERS = ['d0', 'd1', 'd2', 'd3', 'a0', 'a1', 'a2', 'a3', 'sp', 'pc',
             'mdr', 'psw', 'lir', 'lar', 'mdrq'] + [f'extra{i}' for i in range(15, 32)]
# Synthetic addresses for isolated function calls, not claimed camera RAM.
BUFFER = 0x10000000
PATTERN = 0x18000000
STACK = 0x18010000
INITIAL_SP = STACK + 0x1000
WRAPPER = 0x18020000

# Retain only the preceding call's immutable buffers. Identity checks avoid both
# rehashing large byte strings as dictionary keys and stale mutable-buffer hashes.
_region_digests = {}


def _region_inputs(regions):
    global _region_digests
    current, records = {}, []
    for r in regions:
        key = id(r.data)
        cached = current.get(key, _region_digests.get(key))
        if cached is not None and cached[0] is r.data:
            digest = cached[1]
        else:
            digest = hashlib.sha256(r.data).hexdigest()
        if type(r.data) is bytes:
            current[key] = (r.data, digest)
        records.append({'name': r.name, 'address': r.address, 'size': len(r.data),
                        'alias_of': r.alias_of, 'permissions': r.permissions, 'sha256': digest})
    _region_digests = current
    return records


@lru_cache(maxsize=1)
def _engine_digest_at(path, identity):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _engine_digest():
    stat = ENGINE.stat()
    return _engine_digest_at(ENGINE, (stat.st_dev, stat.st_ino, stat.st_size,
                                     stat.st_mtime_ns, stat.st_ctime_ns))


@dataclass(frozen=True)
class Region:
    name: str
    address: int
    data: bytes
    permissions: str = 'r'
    capture: bool = False
    alias_of: str | None = None


@lru_cache(maxsize=1)
def firmware():
    data = IMAGE.read_bytes()
    if hashlib.sha256(data).hexdigest() != MAIN_SHA256:
        raise ValueError('Requires the exact stock PEN-F 3101 main image')
    return data


def image_region(name, start, end, permissions='rx'):
    data = firmware()
    if not BASE <= start < end <= BASE + len(data):
        raise ValueError('Image slice outside known mapping')
    return Region(name, start, data[start-BASE:end-BASE], permissions)


def execute(regions, registers, stop_pc, *, limit=10000, trace_limit=0, timeout=30, breakpoints=(), trace_tail=False, changed_captures=False):
    """Run one fresh simulator process. Return registers, fault, trace and captures."""
    if not ENGINE.is_file():
        raise RuntimeError('Build tools/build_mn103_emulator.py before executing firmware')
    if not 0 < limit <= 100_000_000 or not 0 <= trace_limit <= 100_000:
        raise ValueError('Invalid instruction/trace limit')
    if not 0 <= stop_pc <= 0xffffffff or len(regions) > 1024:
        raise ValueError('Invalid stop address/region count')
    values = [0]*32
    for name, value in registers.items():
        if name not in REGISTERS or not 0 <= value <= 0xffffffff:
            raise ValueError(f'Invalid register assignment: {name}={value}')
        values[REGISTERS.index(name)] = value
    breakpoints = list(breakpoints)
    if len(breakpoints)>1024 or any(not 0<=pc<=0xffffffff for pc in breakpoints):
        raise ValueError('Invalid breakpoints')
    payload = bytearray(b'PFMN002\0' + struct.pack('<6I', limit, stop_pc, trace_limit, len(regions), len(breakpoints), int(trace_tail)))
    payload.extend(struct.pack(f'<{len(breakpoints)}I32I', *breakpoints, *values))
    spans = []
    names = {}
    for index, r in enumerate(regions):
        if r.name in names:
            raise ValueError(f'Duplicate region name: {r.name}')
        if not r.data or not 0 <= r.address < r.address+len(r.data) <= 0x100000000:
            raise ValueError(f'Invalid region: {r.name}')
        if not r.permissions or set(r.permissions)-set('rwx'):
            raise ValueError(f'Invalid permissions: {r.name}')
        end = r.address+len(r.data)
        position = bisect_left(spans, (r.address,))
        if ((position and spans[position-1][1] > r.address) or
                (position < len(spans) and spans[position][0] < end)):
            raise ValueError(f'Overlapping region: {r.name}')
        spans.insert(position, (r.address, end))
        mask = sum(bit for char, bit in [('r', 1), ('w', 2), ('x', 4)] if char in r.permissions)
        alias = names.get(r.alias_of, 0xffffffff)
        if r.alias_of is not None:
            if alias == 0xffffffff or regions[alias].data != r.data or regions[alias].address % 8 != r.address % 8:
                raise ValueError(f'Invalid alias: {r.name}')
        capture = (2 if changed_captures else 1) if r.capture else 0
        payload.extend(struct.pack('<5I', r.address, len(r.data), mask, capture, alias))
        if alias == 0xffffffff:
            payload.extend(r.data)
        names[r.name] = index
    if sum(len(r.data) for r in regions) > 256*1024*1024:
        raise ValueError('Memory allocation exceeds harness limit')
    proc = subprocess.run([str(ENGINE)], input=payload, capture_output=True, timeout=timeout)
    if proc.returncode:
        raise RuntimeError(f'Engine failed ({proc.returncode}): {proc.stderr.decode(errors="replace")}')
    try:
        result = json.loads(proc.stdout)
    except ValueError as e:
        raise RuntimeError(f'Invalid engine output: {proc.stdout[:1000]!r}; {proc.stderr[:1000]!r}') from e
    result['registers'] = dict(zip(REGISTERS, result['registers']))
    result['before_last_instruction'] = dict(zip(REGISTERS, result['before_last_instruction']))
    result['trace'] = [dict(zip(REGISTERS, row)) for row in result['trace']]
    for capture in result['memory']:
        capture['name'] = regions[capture['index']].name
    if result['fault']:
        result['fault']['access'] = {0: 'read', 1: 'write', 2: 'execute'}.get(result['fault']['map'], 'unknown') if result['fault']['kind'] == 1 else None
    result['diagnostics'] = proc.stderr.decode(errors='replace')
    result['engine_sha256'] = _engine_digest()
    result['inputs'] = {'registers': registers, 'stop_pc': stop_pc, 'limit': limit,
                        'breakpoints': breakpoints, 'trace_tail': trace_tail, 'changed_captures': changed_captures,
                        'regions': _region_inputs(regions)}
    return result


def call_function(target, end, save_mask, frame_size, inputs, registers, *, trace_limit=0, limit=10000, timeout=30):
    """Exercise a real CALL and firmware return, with a synthetic caller."""
    code = b'\xdd' + struct.pack('<i', target-WRAPPER) + bytes([save_mask, frame_size])
    regions = [Region('caller', WRAPPER, code, 'rx'),
               image_region('function', target, end),
               Region('stack', STACK, bytes(0x1100), 'rw')] + list(inputs)
    regs = {'d2': 0x22334455, 'd3': 0x66778899, 'a2': 0xaabbccdd,
            'a3': 0x11223344, 'sp': INITIAL_SP, 'pc': WRAPPER}
    regs.update(registers)
    result = execute(regions, regs, WRAPPER+len(code), limit=limit, trace_limit=trace_limit, timeout=timeout)
    result['firmware_sha256'] = MAIN_SHA256
    return result


def checksum(data, *, trace_limit=0):
    if not data or len(data) % 4:
        raise ValueError('Checksum input must have positive length divisible by four')
    return call_function(0x60187f3e, 0x60187f4f, 0x80, 4,
                         [Region('data', BUFFER, data)], {'d0': len(data), 'a0': BUFFER},
                         trace_limit=trace_limit, limit=6*(len(data)//4)+32, timeout=120)


def suffix(data, *, trace_limit=0):
    if not data or len(data) > 65535:
        raise ValueError('Suffix input must contain 1..65535 bytes')
    return call_function(0x60b1cfba, 0x60b1d00f, 0xf0, 16,
                         [Region('suffix', BUFFER, data)], {'d0': len(data), 'a0': BUFFER},
                         trace_limit=trace_limit, limit=40*len(data)+32)


def match_name(name, pattern=b'E122????BIN', *, trace_limit=0):
    if len(name) != len(pattern) or not name:
        raise ValueError('Name and pattern must have the same positive length')
    return call_function(0x6059cdb5, 0x6059ce05, 0xa0, 8,
                         [Region('name', BUFFER, name), Region('pattern', PATTERN, pattern),
                          image_region('character_classes', 0x6064e28e, 0x6064e38e, 'r')],
                         {'d0': len(name), 'a0': BUFFER, 'a1': PATTERN},
                         trace_limit=trace_limit, limit=30*len(name)+32)


def color_builder(saturation=None, *, overrides=(), trace_limit=0):
    """Execute the actual coefficient builder, with optional native table edits.

    Overrides are (record, byte_offset, signed_i16), restricted to H/S/L
    offsets 12/14/16. This modifies a simulator input only, never firmware files.
    Array index maps to record (index % 2)*6 + index//2.
    """
    saturation = list(saturation if saturation is not None else [0]*12)
    overrides = list(overrides)
    if len(saturation) != 12 or any(not -128 <= s <= 127 for s in saturation):
        raise ValueError('Supply twelve signed-byte saturation inputs')
    table_address, table_size, output = 0x60622d74, 3028, 0x19000000
    table = bytearray(image_region('table', table_address, table_address+table_size, 'r').data)
    for record, field, value in overrides:
        if not 0 <= record < 12 or field not in (12, 14, 16) or not -32768 <= value <= 32767:
            raise ValueError('Invalid native HSL table override')
        struct.pack_into('<h', table, 28*record+field, value)
    inputs = [Region('color_table', table_address, table),
              Region('saturation', BUFFER, struct.pack('<12b', *saturation)),
              Region('output', output, bytes(5212), 'rw', True),
              image_region('gain_pointers', 0x6062fef8, 0x6062ff28, 'r')]
    pointers = struct.unpack('<12I', inputs[-1].data)
    for pointer in sorted(set(pointers)):
        inputs.append(image_region(f'gain_{pointer:x}', pointer, pointer+4, 'r'))
    result = call_function(0x604f7272, 0x604f746a, 0xf0, 96, inputs,
                           {'a0': table_address, 'a1': BUFFER, 'd1': output,
                            'd0': struct.unpack_from('<H', table, 3024)[0]},
                           trace_limit=trace_limit, limit=5000)
    captured = bytes.fromhex(next(m['hex'] for m in result['memory'] if m['name'] == 'output'))
    result['color'] = {'saturation_inputs': saturation, 'native_overrides': list(overrides),
                       'records': [list(struct.unpack_from('<6I', captured, 676+i*24)) for i in range(12)],
                       'enable_mask': struct.unpack_from('<I', captured, 964)[0],
                       'scope': 'Coefficient builder only; no ISP rendering or camera validation'}
    return result


def boot_prefix(*, trace_limit=100):
    """Run only the known entry prefix, stopping at its first hardware access.

    Incoming stack/PSW are synthetic preconditions; no claim to emulate reset.
    """
    result = execute([image_region('entry_prefix', 0x60021020, 0x600210f9),
                      Region('synthetic_incoming_stack', STACK, bytes(0x1100), 'rw')],
                     {'pc': 0x60021020, 'sp': INITIAL_SP, 'psw': 0},
                     0x600210f9, limit=100, trace_limit=trace_limit)
    result['firmware_sha256'] = MAIN_SHA256
    result['assumptions'] = ['Entry starts at 0x60021020, not hardware reset',
                             'Incoming SP points into explicitly zero-initialized synthetic RAM',
                             'Other registers, including PSW, initially zero',
                             'No controller, interrupt or secondary-CPU behavior is supplied']
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trace', type=int, default=0, help='Record up to N pre-instruction register snapshots')
    p.add_argument('--out', type=Path, help='Save complete JSON result')
    sub = p.add_subparsers(dest='command', required=True)
    check = sub.add_parser('checksum'); src = check.add_mutually_exclusive_group(required=True)
    src.add_argument('--hex'); src.add_argument('--file', type=Path)
    sub.add_parser('suffix').add_argument('text')
    match = sub.add_parser('match'); match.add_argument('name'); match.add_argument('--pattern', default='E122????BIN')
    color = sub.add_parser('color')
    color.add_argument('--saturation', default=','.join(['0']*12), help='Twelve comma-separated signed integers')
    color.add_argument('--override', action='append', default=[], metavar='RECORD:FIELD:VALUE',
                       help='Native table override; FIELD is h, s or l; RECORD is 0..11')
    sub.add_parser('boot-prefix')
    args = p.parse_args()
    if args.command == 'checksum':
        data = bytes.fromhex(args.hex) if args.hex is not None else args.file.read_bytes()
        result = checksum(data, trace_limit=args.trace)
    elif args.command == 'suffix':
        result = suffix(args.text.encode('ascii'), trace_limit=args.trace)
    elif args.command == 'match':
        result = match_name(args.name.encode('ascii'), args.pattern.encode('ascii'), trace_limit=args.trace)
    elif args.command == 'boot-prefix':
        result = boot_prefix(trace_limit=args.trace)
    else:
        overrides = []
        for entry in args.override:
            record, field, value = entry.split(':')
            overrides.append((int(record), {'h': 12, 's': 14, 'l': 16}[field], int(value)))
        result = color_builder([int(v) for v in args.saturation.split(',')], overrides=overrides, trace_limit=args.trace)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'status': result['status'], 'd0': hex(result['registers']['d0']),
                      'pc': hex(result['registers']['pc']), 'instructions': result['completed'],
                      'fault': result['fault']}, indent=2))
    if result['status'] != 'returned':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
