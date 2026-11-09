# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Scope and native GPIO-reader checks for deferred bc_ssc startup work."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_probe import ProbeState
from penf_boot_startup_gpio import StartupGpioPeer


class StartupGpioTests(unittest.TestCase):
    def fixture(self, output):
        s = ProbeState(0x60194165, 0x30, 12, bytes(1), dict(d0=97))
        # Isolate the real CALL instruction, reader and return. No bc_ssc
        # transaction or kernel interrupt handler is represented by this test.
        s.regs.update(pc=0x6019419f, sp=0x18018000)
        s.ram('board_variant', 0x8ff00188, bytes(1))
        s.register(0x9b800b84, 'w', output)
        return s, StartupGpioPeer('bulk', 'next', 0)

    def test_native_reader_observes_output_and_shadow_is_restored(self):
        for output in (0, 1, 0x20, 0x21):
            with self.subTest(output=output):
                s, p = self.fixture(output)
                self.assertTrue(p.handle(s, p.hooks, None))
                r = s.run({0x601941a6}, limit=100)
                self.assertEqual(r['status'], 'breakpoint')
                self.assertEqual(s.regs['d0'], output & 1)
                self.assertTrue(p.handle(s, p.hooks, None))
                region = next(r for r in s.regions if r.address == 0x9b800b84)
                self.assertEqual((region.permissions, int.from_bytes(region.data, 'little')), ('w', output))
                self.assertIsNone(p.gpio97_sample)

    def test_unexpected_context_and_unpaired_return_reject(self):
        for case in ('cpu', 'pin', 'permissions', 'return'):
            with self.subTest(case=case):
                s, p = self.fixture(0)
                if case == 'cpu': s.cpu = 1
                if case == 'pin': s.regs['d0'] = 98
                if case == 'permissions': s.register(0x9b800b84, 'rw', 0)
                if case == 'return': s.regs['pc'] = 0x601941a6
                before = list(s.regions)
                with self.assertRaises(ValueError): p.handle(s, p.hooks, None)
                self.assertEqual(s.regions, before)


if __name__ == '__main__':
    unittest.main()
