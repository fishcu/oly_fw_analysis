# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Opaque-directory guards, exact resources and native initialization fallback."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_emulator import BASE, Region, firmware
from penf_probe import ProbeState, CALLER
from penf_resource_storage import opaque_ram, package_read, transfer, LENS_READ


class ResourceStorageTests(unittest.TestCase):
    def test_opaque_slice_blocks_native_reads_in_both_aliases(self):
        for alias in (0, 0x40000000):
            with self.subTest(alias=alias):
                # Real 32-bit load instruction from the resource version getter.
                s = ProbeState(0x602b9205, 0, 0, bytes(1), {})
                s.ram('test_owner', 0x62000000, bytes(range(64)))
                opaque_ram(s, 'test_gap', 0xa2000010, 16)
                self.assertEqual(s.read(0x62000000, 16), bytes(range(16)))
                self.assertEqual(s.read(0xa2000020, 32), bytes(range(32, 64)))
                s.write(0xa2000024, b'abcd')
                self.assertEqual(s.read(0x62000024, 4), b'abcd')
                s.regs.update(pc=0x602b9205, a0=0x62000010+alias)
                r = s.run(set(), limit=1)
                self.assertEqual(r['status'], 'memory_fault')
                self.assertEqual(r['fault']['address'], 0x62000010+alias)
                self.assertEqual(r['fault']['access'], 'read')

    def test_package_header_and_missing_boundaries(self):
        data, kind = package_read(0x46160000, 64)
        self.assertEqual(kind, 0x102)
        self.assertEqual(data[:4], bytes.fromhex('4f451220'))
        self.assertEqual(struct.unpack_from('<II', data, 32), (0x46163000, 0x7a00))
        for address, size in ((0x47560000, 1024), (0x4755fff0, 32), (0x44560000, 4096), (0x46160000, 0)):
            with self.subTest(address=hex(address), size=size):
                with self.assertRaises(ValueError): package_read(address, size)

    def initialize(self, lens_bytes=None):
        s = ProbeState(0x602b8573, 0xf0, 24, bytes(1), {})
        s.ram('resource_state', 0xa1c58600, b'\xa5'*0x400)
        # The real boot owns one large BSS slice; exercise the same partitioning.
        s.ram('resource_directories', 0xa1c9d580, bytes(0x10000))
        blob = firmware(); offset = 0x6115da00-BASE
        s.regions.append(Region('relocated_helpers', 0x47000800, blob[offset:offset+0x1800], 'rx'))
        reads = []
        for _ in range(20):
            r = s.run({0x600720e1, CALLER+7}, limit=100000)
            self.assertEqual(r['status'], 'breakpoint', r)
            if s.regs['pc'] == CALLER+7:
                return s, reads
            source, dest, size = s.regs['a1'], s.regs['a0'], s.regs['d0']
            self.assertEqual(s.regs['d1'], 0x101)
            reads.append((source, dest, size))
            if (source, dest, size) == LENS_READ and lens_bytes is not None:
                s.ram('test_lens_data', dest, lens_bytes)
            else:
                transfer(s, source, dest, size)
            # Isolate only lower storage and synchronization, not the resource
            # initializer, alignment helper, comparison or fallback copy.
            s.return_from_model(0)
        self.fail('Native resource initializer exceeded read bound')

    def test_initializer_completes_without_reading_unknown_directories(self):
        s, reads = self.initialize()
        self.assertEqual(len(reads), 14)
        self.assertEqual(reads[0], (0x47560000, 0xa1c9d580, 1024))
        self.assertEqual(s.read(0xa2d23c00, 1024), s.read(0x603713ac, 1024))
        self.assertEqual(s.read(0xa2d23c00+1017, 7), b'LENSDAT')
        for a in (0x61c9d580, 0xa1c9d580, 0x61ca09a0, 0xa1ca09a0):
            r = next(r for r in s.regions if r.address == a)
            self.assertEqual(r.permissions, 'w')
        self.assertEqual(s.regs['sp'], 0x18018000)

    def test_lens_marker_alone_selects_keep_or_default(self):
        for valid in (True, False):
            with self.subTest(valid=valid):
                data = bytearray(b'\x3c'*1024)
                data[1017:] = b'LENSDAT' if valid else b'LENSDA?'
                s, _ = self.initialize(bytes(data))
                self.assertEqual(s.read(0xa2d23c00, 1024), bytes(data) if valid else s.read(0x603713ac, 1024))


if __name__ == '__main__':
    unittest.main()
