# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native threshold edges and tightly scoped A-mode ADC model."""
import sys
from pathlib import Path
import struct
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from penf_boot_mode_dial import ModeDialPeer
from penf_probe import ProbeState, CALLER


class ModeDialAdcTests(unittest.TestCase):
    def test_native_a_threshold_edges(self):
        for sample, bits in ((391, 0x80), (392, 0x100), (415, 0x100),
                             (437, 0x100), (438, 0x200), (900, 0)):
            with self.subTest(sample=sample):
                s = ProbeState(0x6019b892, 0xe0, 12, b'x', dict(d0=sample))
                s.ram('threshold_pointer', 0x6185041c, struct.pack('<I', 0x601c3c10))
                r = s.run({CALLER+7}, limit=1000)
                self.assertEqual(r['status'], 'breakpoint')
                self.assertEqual(s.regs['d0'], bits)

    def test_sample_mapping_removed_after_native_read(self):
        p = ModeDialPeer('bulk', 'next', 0)
        s = ProbeState(p.mode_adc_pc, 0, 4, b'x', dict(d0=0x80))
        self.assertEqual(s.run({p.mode_adc_pc}, limit=10)['status'], 'breakpoint')
        self.assertTrue(p.handle(s, p.hooks, None))
        self.assertEqual(s.regs['d1'], 415)
        self.assertFalse(any(r.address == p.mode_adc_register for r in s.regions))
        with self.assertRaises(ValueError):
            s.read(p.mode_adc_register, 4)

    def test_unreviewed_context_and_overlap_stop(self):
        for bad_cpu, overlap in ((True, False), (False, True)):
            p = ModeDialPeer('bulk', 'next', 0)
            s = ProbeState(p.mode_adc_pc, 0, 4, b'x', dict(d0=0x80))
            s.regs['pc'] = p.mode_adc_pc
            s.cpu = int(bad_cpu)
            if overlap:
                s.register(p.mode_adc_register, 'w', 123)
            self.assertFalse(p.handle(s, p.hooks, None))
            self.assertEqual(s.steps, 0)


if __name__ == '__main__':
    unittest.main()
