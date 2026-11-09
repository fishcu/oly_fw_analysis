#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Boundaries of the private 8040 write hypothesis; native instruction checks."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_boot_after_alex import PostAlexPeer
from penf_probe import ProbeState


class PostAlexTests(unittest.TestCase):
    def state(self, value=8):
        s = ProbeState(0x600706ec, 0, 4, bytes(16), dict(d0=value))
        s.regs['pc'] = 0x600706ec
        return s

    def test_native_write_is_still_a_fault_without_the_model(self):
        s = self.state()
        result = s.run(set(), limit=1)
        self.assertEqual(result['status'], 'memory_fault')
        self.assertEqual(result['fault']['address'], 0x8040)
        self.assertEqual(result['fault']['access'], 'write')

    def test_model_accepts_only_the_reviewed_native_halfword(self):
        s, peer = self.state(), PostAlexPeer(low_memory_word=0)
        self.assertTrue(peer.handle(s, peer.hooks, None))
        region = next(r for r in s.regions if r.address == 0x8040)
        self.assertEqual(region.data, b'\x08\x00')
        self.assertEqual(region.permissions, 'w')
        self.assertTrue(s.is_private(region))
        self.assertEqual(s.regs['pc'], 0x600706ef)

    def test_unreviewed_value_is_rejected_without_mapping_memory(self):
        s, peer = self.state(9), PostAlexPeer(low_memory_word=0)
        with self.assertRaises(AssertionError):
            peer.handle(s, peer.hooks, None)
        self.assertFalse(any(r.address == 0x8040 for r in s.regions))


if __name__ == '__main__':
    unittest.main(verbosity=2)
