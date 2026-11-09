#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Scoped allocation and native initializer checks, without device access."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_boot_application import ApplicationPeer
from penf_probe import ProbeState, CALLER


class ApplicationTests(unittest.TestCase):
    def fixture(self, address=0x6123a640):
        s = ProbeState(0x6016d5b4, 0, 4, bytes(16), dict(a0=address))
        s.ram('record_control', 0x6184e04c, b'\xa5'*12)
        s.ram('allocation_bitmap', 0xa1c556b4, struct.pack('<II', 1 << 4, 0))
        return s, ApplicationPeer(low_memory_word=0)

    def test_scoped_mapping_then_native_initialization(self):
        s, peer = self.fixture()
        hooks = peer.hooks | {CALLER+7}
        for _ in range(8):
            result = s.run(hooks, limit=30000)
            self.assertEqual(result['status'], 'breakpoint', result.get('fault'))
            if s.regs['pc'] == CALLER+7:
                break
            self.assertTrue(peer.handle(s, hooks, None))
        self.assertEqual(s.regs['pc'], CALLER+7)
        self.assertEqual(s.regs['sp'], 0x18018000)
        expected = (bytes.fromhex('3f3f3f00')+bytes(16))*819
        self.assertEqual(s.read(0x6123a640, 16380), expected)
        self.assertEqual(s.read(0xa123a640, 16380), expected)
        regions = [r for r in s.regions if r.name.startswith('startup_record_allocation')]
        self.assertEqual(len(regions), 2)
        self.assertTrue(all(len(r.data) == 16380 and r.permissions == 'rw' for r in regions))
        self.assertTrue(any(e.get('name') == 'native startup record buffer initialized' for e in s.events))

    def test_unreviewed_pointer_is_not_mapped(self):
        s, peer = self.fixture(0x6123a644)
        s.regs['pc'] = 0x6016d5b4
        with self.assertRaises(AssertionError):
            peer.handle(s, peer.hooks, None)
        self.assertIsNone(peer.record_allocation)
        self.assertFalse(any(r.name.startswith('startup_record_allocation') for r in s.regions))

    def test_free_requires_a_new_lifetime_review(self):
        s, peer = self.fixture()
        s.regs['pc'] = 0x600233fc
        peer.record_allocation = (0x6123a640, 16380)
        self.assertFalse(peer.handle(s, peer.hooks, None))
        self.assertEqual(s.steps, 0)
        self.assertEqual(s.events[-1]['kind'], 'unresolved')


if __name__ == '__main__':
    unittest.main(verbosity=2)
