# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native favorite-lens startup validation and RAM-default behavior.

Only the lower storage read is supplied. No saved camera data or flash writes
are involved, and no persistent region is declared spare by these tests.
"""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_probe import ProbeState, CALLER
from penf_boot_favorite_lens import FavoriteLensPeer, FAVORITE_READ


class FavoriteLensBootTests(unittest.TestCase):
    buffer = 0xa1c49380
    size = 2048

    def initialize(self, data):
        s = ProbeState(0x60162c76, 0x80, 28, bytes(1), {})
        s.ram('lens_state', 0x6184dfd0, bytes(128))
        s.write(0x6184dfe0, struct.pack('<III', self.buffer, self.buffer, self.size))
        s.ram('resource_results', 0xa1c58810, b'\xa5'*32)
        s.ram('favorite_buffer', self.buffer, b'\xa5'*self.size)
        r = s.run({0x600720e1}, limit=1000)
        self.assertEqual(r['status'], 'breakpoint', r)
        self.assertEqual((s.regs['a1'], s.regs['a0'], s.regs['d0'], s.regs['d1']),
                         (0x40160000, self.buffer, self.size, 0x101))
        s.write(self.buffer, data)
        s.return_from_model(0)
        r = s.run({CALLER+7}, limit=3000)
        self.assertEqual(r['status'], 'breakpoint', r)
        self.assertEqual(s.regs['sp'], 0x18018000)
        return s

    def test_erased_and_bad_checksum_or_marker_reset_only_ram_fields(self):
        for kind in ('erased', 'checksum', 'marker'):
            with self.subTest(kind=kind):
                data = bytearray(b'\xff'*self.size if kind == 'erased' else bytes(self.size))
                if kind != 'erased':
                    data[334:349] = b'MyFavoriteLens\0'
                    if kind == 'checksum': data[178] = 1
                    else: data[334] = ord('?')
                s = self.initialize(bytes(data))
                self.assertEqual(s.read(self.buffer, 7), b'\0'+b'\xff'*6)
                self.assertEqual(s.read(self.buffer+152, 1), b'\0')
                self.assertEqual(s.read(self.buffer+334, 15), b'MyFavoriteLens\0')
                expected = bytearray(data)
                expected[:7] = b'\0'+b'\xff'*6
                expected[152] = 0
                expected[334:349] = b'MyFavoriteLens\0'
                self.assertEqual(s.read(self.buffer, self.size), bytes(expected))

    def test_valid_empty_favorite_record_is_retained(self):
        data = bytearray(self.size)
        data[334:349] = b'MyFavoriteLens\0'
        s = self.initialize(bytes(data))
        self.assertEqual(s.read(self.buffer, self.size), bytes(data))

    def test_scoped_storage_model_requires_matching_request_and_restores_caller(self):
        for valid in (True, False):
            with self.subTest(valid=valid):
                s = ProbeState(0x600224c2, 0, 0, bytes(1), dict(
                    a0=FAVORITE_READ['source'], a1=self.buffer, d1=self.size))
                s.ram('favorite_buffer', self.buffer, b'\xa5'*self.size)
                r = s.run({0x600224c2}, limit=10)
                self.assertEqual(r['status'], 'breakpoint')
                peer = FavoriteLensPeer('bulk', 'next', 0)
                peer.favorite_active = True
                peer.resource_request = dict(FAVORITE_READ) if valid else None
                self.assertEqual(peer.handle(s, peer.hooks, None), valid)
                if valid:
                    r = s.run({CALLER+7}, limit=10)
                    self.assertEqual(r['status'], 'breakpoint')
                    self.assertEqual(s.regs['pc'], CALLER+7)
                    self.assertEqual(s.regs['d0'], 0)
                    self.assertEqual(s.read(self.buffer, self.size), b'\xff'*self.size)
                else:
                    self.assertEqual(s.read(self.buffer, self.size), b'\xa5'*self.size)


if __name__ == '__main__':
    unittest.main()
