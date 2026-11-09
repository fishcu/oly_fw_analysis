# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Exact API-log allocation admission, native clear and lifetime guards."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_boot_api_log import ApiLogPeer
from penf_emulator import BASE, Region, firmware
from penf_probe import ProbeState


class ApiLogModelTests(unittest.TestCase):
    def fixture(self):
        peer = ApiLogPeer('bulk', 'next', 0)
        s = ProbeState(0x602dfca8, 0, 0, bytes(16), dict(a0=peer.api_log_address))
        s.ram('api_log_pointer', 0x615fd92c, b'\xa5'*4)
        s.ram('allocation_cursor', 0xa1c554c8, struct.pack('<I', 7))
        s.ram('cpu0_bitmap', 0xa1c556b4, (0x92).to_bytes(8, 'little'))
        blob = firmware(); offset = 0x6115da00-BASE
        s.regions.append(Region('relocated_helpers', 0x47000800, blob[offset:offset+0x1800], 'rx'))
        s.run({0x602dfca8}, limit=10)
        return s, peer

    def test_mapping_is_exact_and_native_clear_fills_it(self):
        s, peer = self.fixture()
        before = s.read(peer.api_log_address-4, 4)
        after = s.read(peer.api_log_address+peer.api_log_size, 4)
        self.assertTrue(peer.handle(s, peer.hooks, None))
        r = next(r for r in s.regions if r.name == 'api_log_allocation')
        self.assertEqual((r.address, len(r.data), r.permissions), (peer.api_log_address, 16380, 'rw'))
        self.assertEqual(r.data, b'\xa5'*16380)
        result = s.run({0x602dfcb9}, limit=20000)
        self.assertEqual(result['status'], 'breakpoint')
        self.assertTrue(peer.handle(s, peer.hooks, None))
        self.assertEqual(s.read(peer.api_log_address, 16380), bytes(16380))
        self.assertEqual(s.read(peer.api_log_address+0x40000000, 16380), bytes(16380))
        self.assertEqual(s.read(peer.api_log_address-4, 4), before)
        self.assertEqual(s.read(peer.api_log_address+16380, 4), after)

    def test_bad_allocation_state_and_overlap_stop(self):
        for change in ('pointer', 'cpu', 'cursor', 'bitmap', 'repeat', 'overlap'):
            with self.subTest(change=change):
                s, peer = self.fixture()
                if change == 'pointer': s.regs['a0'] += 4
                elif change == 'cpu': s.cpu = 1
                elif change == 'cursor': s.write(0xa1c554c8, struct.pack('<I', 6))
                elif change == 'bitmap': s.write(0xa1c556b4, bytes(8))
                elif change == 'repeat': peer.api_log_mapped = True
                else: s.ram('other_owner', peer.api_log_address+4, b'\xa5'*4)
                steps = s.steps
                self.assertFalse(peer.handle(s, peer.hooks, None))
                self.assertEqual(s.steps, steps)

    def test_free_in_either_alias_stops_before_native_release(self):
        for alias in (0, 0x40000000):
            s, peer = self.fixture()
            self.assertTrue(peer.handle(s, peer.hooks, None))
            s.regs.update(pc=0x600233fc, a0=peer.api_log_address+alias)
            steps = s.steps
            self.assertFalse(peer.handle(s, peer.hooks, None))
            self.assertEqual(s.steps, steps)

    def test_ancestor_hooks_are_not_shadowed(self):
        s, peer = self.fixture()
        s.ram('alex_result', 0x8ff00070, bytes(4))
        s.regs.update(pc=0x600272d8, d0=7)
        self.assertTrue(peer.handle(s, peer.hooks, None))
        self.assertEqual(s.read(0x8ff00070, 4), struct.pack('<I', 7))


if __name__ == '__main__':
    unittest.main()
