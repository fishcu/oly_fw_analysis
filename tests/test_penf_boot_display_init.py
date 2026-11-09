# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native display-state initialization, change reporting and mapping bounds."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_boot_display_init import DisplayStatePeer
from penf_probe import ProbeState, CALLER, RESULT


class DisplayStateTests(unittest.TestCase):
    def test_native_initializer_fills_entire_poisoned_extent(self):
        s = ProbeState(0x60042664, 0, 0, bytes(16), {})
        peer = DisplayStatePeer('bulk', 'next', 0)
        s.run({0x60042664}, limit=100)
        s.regs['mdr'] = 0x60315f9d  # Exact reviewed call site; stop before its return.
        self.assertTrue(peer.handle(s, peer.hooks, None))
        r = s.run({0x60042681}, limit=100)
        self.assertEqual(r['status'], 'breakpoint')
        self.assertEqual(s.read(0x8ff001a4, 12), bytes.fromhex('703000000000000000000000'))
        region = next(r for r in s.regions if r.name == 'display_shared_state')
        self.assertEqual((region.permissions, len(region.data)), ('rw', 12))
        with self.assertRaises(ValueError):
            s.read(0x8ff001b0, 1)

    def test_other_caller_is_not_admitted(self):
        s = ProbeState(0x60042664, 0, 0, bytes(16), {})
        s.regs.update(pc=0x60042664, mdr=CALLER+7)
        peer = DisplayStatePeer('bulk', 'next', 0)
        self.assertFalse(peer.handle(s, peer.hooks, None))

    def test_existing_mapping_requires_review(self):
        s = ProbeState(0x60042664, 0, 0, bytes(16), {})
        s.regs.update(pc=0x60042664, mdr=0x60315f9d)
        s.ram('existing', 0x8ff001a8, b'\xa5'*4)
        peer = DisplayStatePeer('bulk', 'next', 0)
        self.assertFalse(peer.handle(s, peer.hooks, None))
        self.assertEqual(s.read(0x8ff001a8, 4), b'\xa5'*4)

    def test_native_change_reader_updates_previous_and_reports_changes_once(self):
        cases = ((0x3070, 0, 0x3070), (0x3070, 0x3070, 0),
                 (4000, 0x3070, 4000), (0x12343070, 0x3070, 0x12340000))
        for current, previous, expected in cases:
            s = ProbeState(0x6004268d, 0, 0, bytes(16), dict(a0=RESULT))
            s.ram('display_shared_state', 0x8ff001a4,
                  current.to_bytes(4, 'little')+previous.to_bytes(4, 'little')+b'\xa5'*4)
            r = s.run({CALLER+7}, limit=100)
            self.assertEqual(r['status'], 'breakpoint')
            self.assertEqual(s.regs['pc'], CALLER+7)
            self.assertEqual(int.from_bytes(s.read(RESULT, 4), 'little'), expected)
            self.assertEqual(int.from_bytes(s.read(0x8ff001a8, 4), 'little'), current)
            self.assertEqual(s.read(0x8ff001ac, 4), b'\xa5'*4)


if __name__ == '__main__':
    unittest.main()
