# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Review the next boot boundary: allocated API log storage, not a device."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_emulator import BASE, Region, firmware
from penf_probe import ProbeState, CALLER


class ApiLogStartupTests(unittest.TestCase):
    address = 0x61246700
    size = 16380

    def test_native_allocator_selects_slot_seven_from_prior_boot_bitmap(self):
        s = ProbeState(0x600236bb, 0, 0, bytes(16), {})
        s.register(0x8050, 'r', 0)
        s.ram('allocation_cursor', 0xa1c554c8, struct.pack('<I', 6))
        s.ram('cpu0_bitmap', 0xa1c556b4, (0x12).to_bytes(8, 'little'))
        r = s.run({CALLER+7}, limit=2000)
        self.assertEqual(r['status'], 'breakpoint')
        self.assertEqual(s.regs['a0'], self.address)
        self.assertEqual(s.read(0xa1c554c8, 4), struct.pack('<I', 7))
        self.assertEqual(s.read(0xa1c556b4, 8), (0x92).to_bytes(8, 'little'))

    def fixture(self, writable):
        # Execute the real post-allocation store and memset call. This slice
        # starts after allocation; stop before settings access at 602dfcb9.
        s = ProbeState(0x602dfca8, 0, 0, bytes(16), dict(a0=self.address))
        s.ram('api_log_pointer', 0x615fd92c, b'\xa5'*4)
        blob = firmware()
        # Native relocation source at 6002126a..60021281; no host memset.
        offset = 0x6115da00-BASE
        s.regions.append(Region('relocated_helpers', 0x47000800, blob[offset:offset+0x1800], 'rx'))
        if writable:
            s.ram('api_log_payload', self.address, b'\xa5'*self.size)
        return s

    def test_missing_payload_mapping_reproduces_connected_fault(self):
        s = self.fixture(False)
        r = s.run({0x602dfcb9}, limit=20000)
        self.assertEqual(r['status'], 'memory_fault')
        self.assertEqual(r['fault']['pc'], 0x470015b8)
        self.assertEqual(r['fault']['address'], self.address)

    def test_native_clear_fills_only_requested_payload(self):
        s = self.fixture(True)
        before = s.read(self.address-4, 4)
        after = s.read(self.address+self.size, 4)
        r = s.run({0x602dfcb9}, limit=20000)
        self.assertEqual(r['status'], 'breakpoint')
        self.assertEqual(s.read(self.address, self.size), bytes(self.size))
        self.assertEqual(s.read(0x615fd92c, 4), struct.pack('<I', self.address))
        self.assertEqual(s.read(self.address-4, 4), before)
        self.assertEqual(s.read(self.address+self.size, 4), after)
        self.assertEqual(s.regs['sp'], 0x18018000)


if __name__ == '__main__':
    unittest.main()
