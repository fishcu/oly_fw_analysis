# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native USF initializer coverage and strict model boundaries."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_boot_usf_init import UsfInitPeer
from penf_probe import ProbeState, CALLER


class UsfInitTests(unittest.TestCase):
    def fixture(self):
        s = ProbeState(0x6009069f, 0, 0, bytes(16), {})
        s.ram('usf_descriptor', 0x616fd2d0, b'\xa5'*24)
        return s, UsfInitPeer('bulk', 'next', 0)

    def test_initializer_faults_without_model(self):
        s, _ = self.fixture()
        result = s.run({CALLER+7}, limit=100)
        self.assertEqual(result['status'], 'memory_fault')
        self.assertEqual(result['fault']['address'], 0x9b800008)

    def test_initializer_executes_and_preserves_unwritten_descriptor_fields(self):
        s, peer = self.fixture()
        hooks = peer.hooks | {CALLER+7}
        writes = []
        while True:
            result = s.run(hooks, limit=100)
            self.assertEqual(result['status'], 'breakpoint')
            if s.regs['pc'] == CALLER+7:
                break
            writes.append(s.regs['pc'])
            self.assertTrue(peer.handle(s, hooks, None))
        self.assertEqual(writes, list(peer.init_writes))
        expected = bytearray(b'\xa5'*24)
        expected[4:6] = b'\x28\0'
        expected[16:20] = (0x616fd2e4).to_bytes(4, 'little')
        self.assertEqual(s.read(0x616fd2d0, 24), expected)
        self.assertEqual(s.regs['sp'], 0x18018000)
        self.assertFalse(any(r.address in peer.init_writes.values() for r in s.regions))

    def test_unreviewed_write_value_stops(self):
        s, peer = self.fixture()
        s.regs.update(pc=0x600906a1, d0=2)
        self.assertFalse(peer.handle(s, peer.hooks, None))
        self.assertEqual(s.steps, 0)

    def test_existing_mapping_requires_review(self):
        s, peer = self.fixture()
        s.register(0x9b800008, 'w', 0)
        s.regs.update(pc=0x600906a1, d0=1)
        self.assertFalse(peer.handle(s, peer.hooks, None))
        self.assertEqual(s.steps, 0)

    def test_requests_and_callback_stop_before_execution(self):
        for pc in UsfInitPeer.usf_boundaries:
            s, peer = self.fixture()
            s.regs['pc'] = pc
            self.assertFalse(peer.handle(s, peer.hooks, None))
            self.assertEqual(s.steps, 0)


if __name__ == '__main__':
    unittest.main()
