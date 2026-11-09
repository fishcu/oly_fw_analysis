# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Execute the startup input-registration wrapper with its retained marker.

Fixtures reproduce the two RAM words observed before USTART3. They do not
claim the physical meaning or producer of every possible retained event.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_probe import ProbeState, CALLER


class StartupInputGateTests(unittest.TestCase):
    def run_case(self, marker, destination):
        s = ProbeState(0x601c9334, 0, 4, bytes(16), dict(d0=destination))
        s.ram('retained_startup_marker', 0xa1c57fd4, marker.to_bytes(4, 'little'))
        s.ram('input_delivery_destination', 0xa1c58028, bytes(4))
        result = s.run({CALLER+7, 0x600424dc}, limit=1000)
        self.assertEqual(result['status'], 'breakpoint')
        self.assertEqual(s.regs['pc'], CALLER+7, 'Unexpected application event delivery')
        self.assertEqual(s.regs['sp'], 0x18018000)
        self.assertEqual(int.from_bytes(s.read(0xa1c58028, 4), 'little'), destination)
        return int.from_bytes(s.read(0xa1c57fd4, 4), 'little')

    def test_observed_marker_cleared_without_application_delivery(self):
        self.assertEqual(self.run_case(0x01000000, 6), 0)

    def test_no_marker_needs_no_dispatch(self):
        self.assertEqual(self.run_case(0, 6), 0)

    def test_an_ordinary_ok_event_is_not_replayed_by_this_setter(self):
        self.assertEqual(self.run_case(0x02000004, 6), 0x02000004)

    def test_zero_destination_still_clears_the_special_marker(self):
        self.assertEqual(self.run_case(0x01000000, 0), 0)


if __name__ == '__main__':
    unittest.main()
