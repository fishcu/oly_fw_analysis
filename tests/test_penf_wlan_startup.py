# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Review the new small-allocation boundary; do not extend connected boot."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_probe import ProbeState, CALLER
from penf_emulator import BASE, Region, firmware


class WlanStartupTests(unittest.TestCase):
    address = 0xa12225c0

    def test_native_small_allocator_selects_slot_eight(self):
        # Body after the indirect-entry stack adjustment; native return frame.
        state = ProbeState(0x60023685, 0, 4, bytes(16), {})
        state.ram('allocation_cursor', 0xa1c554c8, struct.pack('<I', 7))
        state.ram('small_physical_bitmap', 0xa1c5569c, bytes(24))
        result = state.run({CALLER+7}, limit=2000)
        self.assertEqual(result['status'], 'breakpoint')
        self.assertEqual(state.regs['a0'], self.address)
        self.assertEqual(state.read(0xa1c554c8, 4), struct.pack('<I', 8))
        self.assertEqual(state.read(0xa1c5569c, 24), struct.pack('<I', 1 << 8)+bytes(20))

    def test_first_clear_is_four_bytes_not_the_full_nine_byte_request(self):
        state = ProbeState(0x602f5c52, 0, 0, bytes(16), dict(a0=self.address, a2=self.address))
        blob = firmware(); offset = 0x6115da00-BASE
        state.regions.append(Region('relocated_helpers', 0x47000800, blob[offset:offset+0x1800], 'rx'))
        state.ram('nine_byte_allocation', self.address, b'\xa5'*9)
        result = state.run({0x602f5c5c}, limit=1000)
        self.assertEqual(result['status'], 'breakpoint')
        self.assertEqual(state.read(self.address, 9), bytes(4)+b'\xa5'*5)

    def test_setting_writer_uses_descriptor_length_without_string_termination(self):
        for key, descriptor, length, destination in (
                (58081, 0xa1c2f354, 9, 0x61b96398),
                (56977, 0xa1c2f12c, 64, 0x61b962dc)):
            with self.subTest(key=key):
                state = ProbeState(0x60075435, 0xf0, 20, bytes(16), dict(d0=key, a1=self.address))
                state.ram('descriptor_table_selector', 0xa1c281e0, bytes(2))
                state.ram('selected_descriptor', descriptor, struct.pack('<HHI', key, length, destination))
                state.ram('nine_byte_source', self.address, b'12345678\xa5')
                state.ram('destination', destination, bytes(length))
                result = state.run({CALLER+7}, limit=2000)
                if length == 9:
                    self.assertEqual(result['status'], 'breakpoint')
                    self.assertEqual(state.read(destination, 9), b'12345678\xa5')
                else:
                    self.assertEqual(result['status'], 'memory_fault')
                    self.assertEqual(result['fault']['address'], self.address+9)
                    self.assertEqual(result['fault']['access'], 'read')


if __name__ == '__main__':
    unittest.main()
