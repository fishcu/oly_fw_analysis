# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Isolated native bc_ssc input branches; no actual transfer is simulated."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_probe import ProbeState, BUFFER
from penf_emulator import BASE, firmware


class BcsscHandshakeTests(unittest.TestCase):
    def test_gpio97_error_or_gpio83_handshake(self):
        blob = firmware()
        for pin97, pin83 in ((1, 1), (0, 1), (0, 0)):
            with self.subTest(pin97=pin97, pin83=pin83):
                record = bytearray(65)
                struct.pack_into('<II', record, 4, BUFFER+64, 1)
                record[64] = 0x55  # Synthetic command byte for native log only.
                s = ProbeState(0x60194165, 0x30, 12, bytes(record), dict(a0=BUFFER))
                s.ram('bc_ssc_test_state', 0x6184fe00, bytes(512))
                s.write(0x6184feac, struct.pack('<I', 1000))
                s.ram('board_variant', 0x8ff00188, bytes(1))
                for pin, level in ((97, pin97), (83, pin83)):
                    a = int.from_bytes(blob[0x60025cec-BASE+pin*4:0x60025cec-BASE+pin*4+4], 'little')
                    s.register(a, 'r', level << 4)
                r = s.run({0x60080530, 0x601974c5}, limit=300)
                self.assertEqual(r['status'], 'breakpoint')
                if pin97:
                    self.assertEqual(s.regs['pc'], 0x60080530)
                    self.assertEqual((s.regs['d0'], s.regs['a0'], s.regs['a1']),
                                     (0x8221, 0x601946ec, BUFFER))
                    continue
                self.assertEqual(s.regs['pc'], 0x601974c5)
                self.assertEqual((s.regs['d0'], s.regs['a0'], s.regs['a1']),
                                 (1000, 0x60194211, BUFFER))
                # Only this isolated branch test substitutes timer allocation.
                # Connected replay executes the real allocator and timer setup.
                s.return_from_model(7)
                r = s.run({0x60083faf, 0x601941e9}, limit=150)
                self.assertEqual(r['status'], 'breakpoint')
                self.assertEqual(int.from_bytes(s.read(0x6184febc, 2), 'little'), 7)
                if pin83:
                    self.assertEqual(s.regs['pc'], 0x60083faf)
                    self.assertEqual((s.regs['d0'], s.regs['a0']), (83, 0x601c2a1c))
                    self.assertEqual(s.read(0x6184feb4, 8), struct.pack('<II', BUFFER, 0x601941e9))
                else:
                    self.assertEqual(s.regs['pc'], 0x601941e9)
                    self.assertEqual(s.regs['a0'], BUFFER)


if __name__ == '__main__':
    unittest.main()
