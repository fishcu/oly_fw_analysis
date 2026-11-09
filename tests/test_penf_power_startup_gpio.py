# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native selector and GPIO-completion evidence for queued power startup.

These are isolated firmware probes, not physical power or timer simulation.
The GPIO write executes before its native synchronous callback is observed.
"""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_emulator import BASE, firmware
from penf_probe import ProbeState, CALLER, BUFFER


class PowerStartupGpioTests(unittest.TestCase):
    def test_native_selector_mapping_and_missing_selector(self):
        for selector, channel in ((7, 0), (8, 1), (9, 2), (28, 3), (16, 4), (32, 5), (255, 6)):
            with self.subTest(selector=selector):
                s = ProbeState(0x60088000, 0xc0, 12, bytes(16), dict(d0=selector))
                r = s.run({CALLER+7}, limit=200)
                self.assertEqual(r['status'], 'breakpoint')
                self.assertEqual(s.regs['d0'], channel)

    def test_startup_gpio_writes_invoke_completion_without_hardware_irq(self):
        blob = firmware()
        for revision in range(4):
            for pin, address in ((163, 0x9b800f74), (173, 0x9b80108c), (174, 0x9b8010a8)):
                with self.subTest(revision=revision, pin=pin):
                    offset = 0x60025cec-BASE+4*pin
                    self.assertEqual(int.from_bytes(blob[offset:offset+4], 'little'), address)
                    descriptor = struct.pack('<III', 1, 0x600885da, 0)
                    s = ProbeState(0x60083f5d, 0, 4, descriptor, dict(d0=pin, a0=BUFFER))
                    s.ram('board_revision', 0x8ff00188, bytes([revision]))
                    s.register(address, 'w')
                    r = s.run({0x600885da}, limit=150)
                    self.assertEqual(r['status'], 'breakpoint')
                    self.assertEqual(s.read(address, 4), b'\x01\0\0\0')
                    self.assertEqual(s.regs['a0'], 0)
                    # Isolate only the context query. Do not force the flag
                    # wait or invoke the final power-ready callback.
                    r = s.run({0x60039214}, limit=20)
                    self.assertEqual(r['status'], 'breakpoint')
                    s.return_from_model(0)
                    r = s.run({0x6006906e}, limit=30)
                    self.assertEqual(r['status'], 'breakpoint')
                    self.assertEqual((s.regs['d0'], s.regs['d1']), (117, 1))


if __name__ == '__main__':
    unittest.main()
