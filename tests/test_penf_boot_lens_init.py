# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native lens reset tail completes without admitting unreviewed MMIO reads."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_boot_lens_init import LensInitPeer
from penf_probe import ProbeState, CALLER


class LensInitTest(unittest.TestCase):
    def fixture(self):
        s = ProbeState(0x6017cb2a, 0, 8, bytes(16), {})
        s.ram('lens_descriptor_slots', 0x6184e340, b'\xa5'*32)
        s.register(0x9bf00000, 'w', 0xa5a5a5a5)
        return s, LensInitPeer('bulk', 'next', 0)

    def test_native_reset_tail_with_strict_scoped_writes(self):
        s, peer = self.fixture()
        for _ in range(20):
            result = s.run(peer.hooks | {CALLER+7}, limit=1000)
            self.assertEqual(result['status'], 'breakpoint')
            if s.regs['pc'] == CALLER+7:
                break
            self.assertTrue(peer.handle(s, peer.hooks | {CALLER+7}, None))
        else:
            self.fail('Native initializer did not return')
        self.assertEqual(s.regs['sp'], 0x18018000)
        self.assertEqual(s.read(0x6184e340, 32), b'\x00'+b'\xa5'*3+bytes(8)+b'\xa5'*4+b'\x01'+b'\xa5'*3+bytes(8)+b'\xa5'*4)
        writes = [e for e in s.events if e.get('name') == 'native lens interface zero write accepted']
        self.assertEqual([e['address'] for e in writes], [hex(a) for a in peer.zero_writes.values()])
        for address in peer.zero_writes.values():
            self.assertFalse(any(r.address <= address < r.address+len(r.data) for r in s.regions))

    def test_nonzero_write_requires_new_review(self):
        s, peer = self.fixture()
        s.regs.update(pc=0x6017cb31, d0=1)
        with self.assertRaises(AssertionError):
            peer.handle(s, peer.hooks, None)
        self.assertFalse(any(r.address == 0x9bf00068 for r in s.regions))

    def test_lens_irq_is_not_silently_simulated(self):
        s, peer = self.fixture()
        s.regs['pc'] = 0x6017cf68
        self.assertFalse(peer.handle(s, peer.hooks, None))
        self.assertEqual(s.steps, 0)


if __name__ == '__main__':
    unittest.main()
