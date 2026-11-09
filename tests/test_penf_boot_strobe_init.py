# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native strobe setup, preserved hardware bits, and completion boundaries."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_boot_strobe_init import StrobeInitPeer
from penf_probe import ProbeState, CALLER


class StrobeInitTests(unittest.TestCase):
    def test_inherited_alex_landmark_still_executes_native_store(self):
        s = ProbeState(0x600272d8, 0, 0, bytes(16), dict(d0=0x1234))
        s.ram('alex_result', 0x8ff00070, b'\xa5'*4)
        s.run({0x600272d8}, limit=10)
        peer = StrobeInitPeer('bulk', 'next', 0)
        self.assertTrue(peer.handle(s, peer.hooks, None))
        self.assertEqual(s.read(0x8ff00070, 4), (0x1234).to_bytes(4, 'little'))
        self.assertTrue(any(e.get('name') == 'CPU1 stores Alex result' for e in s.events))

    def fixture(self):
        s = ProbeState(0x602d3b5b, 0, 4, bytes(16), {})
        s.ram('strobe_descriptors', 0x61889898, bytes(0xd0))
        s.ram('strobe_request_pointer', 0x6188933c, bytes(8))
        peer = StrobeInitPeer('bulk', 'next', 0)
        # Isolate descriptor/configuration code. Clock/lock setup is exercised
        # by the full boot replay, not fabricated in this native unit probe.
        r = s.run({0x602cc70d}, limit=200)
        self.assertEqual(r['status'], 'breakpoint')
        s.return_from_model(0)
        r = s.run({0x602cc75f}, limit=200)
        self.assertEqual(r['status'], 'breakpoint')
        return s, peer

    def test_without_configuration_model_native_read_faults(self):
        s, _ = self.fixture()
        r = s.run({CALLER+7}, limit=500)
        self.assertEqual(r['status'], 'memory_fault')
        self.assertEqual(r['fault']['address'], 0x9b900044)

    def test_native_config_returns_without_completion_or_callback(self):
        s, peer = self.fixture()
        self.assertTrue(peer.handle(s, peer.hooks, None))
        r = s.run({0x602d3c48}, limit=1000)
        self.assertEqual(r['status'], 'breakpoint')
        self.assertEqual(s.read(0x6188933c, 4), (0x6188994c).to_bytes(4, 'little'))
        self.assertEqual(s.read(0x61889958, 4), bytes(4))
        expected_nonzero = {0x08: 0x111, 0x10: 0x1000, 0x14: 1, 0x6c: 7}
        for offset in peer.config_offsets:
            self.assertEqual(peer.reg(s, 0x9b900000+offset), expected_nonzero.get(offset, 0))
        self.assertTrue(peer.handle(s, peer.hooks, None))
        self.assertEqual(s.regs['pc'], CALLER+7)
        self.assertFalse(any(r.name.startswith('scoped_strobe_') for r in s.regions))
        with self.assertRaises(ValueError):
            s.read(0x9b900044, 4)

    def test_unknown_preserved_bits_do_not_change_native_control_flow(self):
        counts = []
        for seed in (0, 0xffffffff):
            s, peer = self.fixture()
            self.assertTrue(peer.handle(s, peer.hooks, None))
            masks = {0x44: 0x10000, 0x48: 0x10000, 0x4c: 0x10000,
                     0x28: 1, 0x50: 0x70000}
            for offset in masks:
                s.write(0x9b900000+offset, seed.to_bytes(4, 'little'))
            r = s.run({0x602d3c48}, limit=1000)
            self.assertEqual(r['status'], 'breakpoint')
            counts.append(r['completed'])
            for offset, mask in masks.items():
                self.assertEqual(peer.reg(s, 0x9b900000+offset), seed & mask)
        self.assertEqual(counts[0], counts[1])

    def test_changed_descriptor_and_repeated_configuration_stop(self):
        for change in ('caller', 'descriptor', 'repeat', 'mapping'):
            s, peer = self.fixture()
            if change == 'caller':
                s.regs['mdr'] = CALLER+7
            elif change == 'descriptor':
                s.write(0x61889954, (0x61889898).to_bytes(4, 'little'))
            elif change == 'repeat':
                peer.strobe_config_seen = True
            else:
                s.register(0x9b900044, 'rw')
            steps = s.steps
            self.assertFalse(peer.handle(s, peer.hooks, None))
            self.assertEqual(s.steps, steps)

    def test_interrupt_and_transaction_entries_remain_boundaries(self):
        s, peer = self.fixture()
        for pc in peer.boundaries:
            s.regs['pc'] = pc
            steps = s.steps
            self.assertFalse(peer.handle(s, peer.hooks, None))
            self.assertEqual(s.steps, steps)

    def test_reset_sinks_accept_only_zero_and_do_not_leave_mappings(self):
        s, peer = self.fixture()
        for pc, address in peer.reset_writes.items():
            s.regs.update(pc=pc, d0=1)
            self.assertFalse(peer.handle(s, peer.hooks, None))
            s.regs.update(pc=pc, d0=0)
            self.assertTrue(peer.handle(s, peer.hooks, None))
            self.assertEqual(s.regs['pc'], pc+6)
            with self.assertRaises(ValueError):
                s.read(address, 4)


if __name__ == '__main__':
    unittest.main()
