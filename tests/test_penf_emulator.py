#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Execute actual PEN-F routines and test strict GNU simulator boundaries."""
import hashlib
import json
from pathlib import Path
import random
import signal
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from penf_emulator import (Region, execute, checksum, suffix, match_name, firmware,
                           INITIAL_SP, ROOT, ENGINE)
from oly_container import sum32

OBSERVATIONS = []


class EmulatorTests(unittest.TestCase):
    def observe(self, name, r):
        OBSERVATIONS.append({'case': name, 'status': r['status'], 'completed': r['completed'],
                             'd0': r['registers']['d0'], 'pc': r['registers']['pc'], 'fault': r['fault']})
        return r

    def returned(self, name, r, expected):
        self.observe(name, r)
        self.assertEqual(r['status'], 'returned', r)
        self.assertEqual(r['registers']['d0'], expected)
        self.assertEqual(r['registers']['sp'], INITIAL_SP)
        for reg, value in [('d2', 0x22334455), ('d3', 0x66778899),
                           ('a2', 0xaabbccdd), ('a3', 0x11223344)]:
            self.assertEqual(r['registers'][reg], value, reg)

    def test_checksum_vectors_and_random(self):
        vectors = [bytes(4), bytes.fromhex('ffffffff'), struct.pack('<3I', 1, 0xffffffff, 2),
                   bytes(range(256)), firmware()[:4096], firmware()[-4096:]]
        rng = random.Random(0x50454e46)
        vectors += [rng.randbytes(4*rng.randint(1, 1024)) for _ in range(100)]
        for i, data in enumerate(vectors):
            with self.subTest(vector=i):
                r = checksum(data)
                self.returned(f'checksum_{i}', r, sum32(data))
                self.assertEqual(r['completed'], 6*(len(data)//4)+6)

    def test_checksum_mutation_changes_result(self):
        data = bytearray(firmware()[:4096])
        first = checksum(data)
        data[120] ^= 1
        second = checksum(data)
        self.returned('checksum_mutation', second, sum32(data))
        self.assertNotEqual(first['registers']['d0'], second['registers']['d0'])

    def test_checksum_entire_main_payload(self):
        data = firmware()
        self.returned('checksum_full_main', checksum(data), sum32(data))

    def test_suffix_matches_independent_hex_parser(self):
        rng = random.Random(122)
        vectors = ['0000', '9999', 'FFFF', 'abcd', 'aBcD', '3101', '12345678']
        vectors += [f'{rng.randrange(65536):04x}' for _ in range(50)]
        for text in vectors:
            with self.subTest(text=text):
                self.returned('suffix_'+text, suffix(text.encode()), int(text, 16))

    def test_filename_matcher(self):
        vectors = [(b'E1229999BIN', b'E122????BIN', 0),
                   (b'E1223101BIN', b'E122????BIN', 0),
                   (b'E122ABcdBIN', b'E122????BIN', 0),
                   (b'E122!!!!BIN', b'E122????BIN', 0),
                   (b'G1229999BIN', b'E122????BIN', 1),
                   (b'E1239999BIN', b'E122????BIN', 1),
                   (b'E1229999bin', b'E122????BIN', 1),
                   (b'E1229\0\0\0BIN', b'E122????BIN', 1),
                   (b'0', b'#', 0), (b'9', b'#', 0), (b'A', b'#', 1),
                   (b'X', b'X', 0), (b'Y', b'X', 1)]
        for name, pattern, expected in vectors:
            with self.subTest(name=name, pattern=pattern):
                self.returned('match_'+name.hex()+'_'+pattern.hex(), match_name(name, pattern), expected)

    def mini(self, name, code, regs=None, extra=(), *, stop=None, limit=20):
        pc = 0x60000000
        r = execute([Region('code', pc, code, 'rx'), *extra],
                    {'pc': pc, 'sp': 0x12345678, **(regs or {})},
                    stop if stop is not None else pc+len(code), limit=limit, trace_limit=20)
        return self.observe(name, r)

    def test_unknown_instruction_stops_without_exception_frame(self):
        r = self.mini('unknown_instruction', bytes.fromhex('f7ff000000000000'))
        self.assertEqual(r['status'], 'instruction_fault')
        self.assertEqual(r['signal'], signal.SIGILL)
        self.assertEqual(r['completed'], 0)
        self.assertEqual(r['registers']['sp'], 0x12345678)
        self.assertEqual(r['registers']['pc'], 0x60000000)

    def test_syscall_and_trap_stop(self):
        for code in ['f0c0', 'f0fe', 'ff']:
            r = self.mini('trap_'+code, bytes.fromhex(code))
            self.assertEqual(r['status'], 'instruction_fault')
            self.assertEqual(r['completed'], 0)
            self.assertEqual(r['registers']['sp'], 0x12345678)

    def test_unmapped_reads_and_writes(self):
        for address in [0x8000, 0x98e00060, 0x40000000]:
            for opcode, access in [('70', 'read'), ('60', 'write')]:
                r = self.mini(f'unmapped_{access}_{address:x}', bytes.fromhex(opcode), {'a0': address})
                self.assertEqual(r['status'], 'memory_fault')
                self.assertEqual(r['fault']['address'], address)
                self.assertEqual(r['fault']['access'], access)
                self.assertEqual(r['registers']['pc'], 0x60000000)
                self.assertEqual(r['completed'], 0)

    def test_unmapped_fetch(self):
        r = self.observe('unmapped_fetch', execute([], {'pc': 0x40000000}, 0, limit=1))
        self.assertEqual(r['status'], 'memory_fault')
        self.assertEqual(r['fault']['access'], 'execute')

    def test_read_only_and_non_executable_permissions(self):
        r = self.mini('read_only_write', b'\x60', {'a0': 0x1000},
                      [Region('read_only', 0x1000, b'ABCD', 'r', True)])
        self.assertEqual(r['status'], 'memory_fault')
        self.assertEqual(r['memory'][0]['hex'], b'ABCD'.hex())
        r = self.observe('non_executable_fetch', execute([Region('data', 0x1000, b'\xcb', 'rw')],
                                                       {'pc': 0x1000}, 0x1001))
        self.assertEqual(r['status'], 'memory_fault')
        self.assertEqual(r['fault']['access'], 'execute')

    def test_mapping_boundary(self):
        r = self.mini('past_buffer_end', b'\x70', {'a0': 0x1004}, [Region('buffer', 0x1000, bytes(4))])
        self.assertEqual(r['status'], 'memory_fault')
        self.assertEqual(r['fault']['address'], 0x1004)
        r = self.mini('truncated_instruction', b'\xfc')
        self.assertEqual(r['status'], 'memory_fault')
        self.assertEqual(r['fault']['access'], 'execute')

    def test_bounded_loop(self):
        r = self.mini('instruction_limit', b'\xca\x00', limit=12)
        self.assertEqual(r['status'], 'instruction_limit')
        self.assertEqual(r['completed'], 12)
        self.assertEqual(len(r['trace']), 12)

    def test_memory_write_capture(self):
        r = self.mini('write_capture', b'\x60', {'a0': 0x1000, 'd0': 0x12345678},
                      [Region('output', 0x1000, bytes(4), 'rw', True)])
        self.assertEqual(r['status'], 'returned')
        self.assertEqual(r['memory'][0]['hex'], '78563412')

    def test_mulq_candidate_semantics(self):
        # This validates GNU semantics against arithmetic, not TruePic silicon.
        for a, b in [(-7000, 7), (0, 99), (0x7fffffff, 3), (-2147483648, -1), (-3, -7)]:
            r = self.mini(f'mulq_{a}_{b}', bytes.fromhex('f604'),
                          {'d0': a & 0xffffffff, 'd1': b & 0xffffffff, 'psw': 15})
            product = (a*b) & 0xffffffffffffffff
            self.assertEqual(r['status'], 'returned')
            self.assertEqual(r['registers']['d0'], product & 0xffffffff)
            self.assertEqual(r['registers']['mdrq'], product >> 32)
            low = product & 0xffffffff
            self.assertEqual(r['registers']['psw'] & 15, (1 if low == 0 else 0) | (2 if low & 0x80000000 else 0))


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(EmulatorTests))
    out = ROOT / 'analysis/emulation/validation.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({'passed': result.wasSuccessful(), 'tests_run': result.testsRun,
                               'executions_recorded': len(OBSERVATIONS),
                               'engine_sha256': hashlib.sha256(ENGINE.read_bytes()).hexdigest(),
                               'observations': OBSERVATIONS}, indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
