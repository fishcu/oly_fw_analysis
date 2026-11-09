# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Regression checks for the shared native probe boundary and diagnostic model."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from penf_probe import BUFFER, CALLER, ProbeState


class ProbeTests(unittest.TestCase):
    def test_diagnostic_stops_at_terminator_at_end_of_mapped_region(self):
        target = 0x6002304a
        state = ProbeState(target, 0xf0, 16, b'A\0', dict(a0=BUFFER, d0=7))
        result = state.run({target}, limit=100)
        self.assertEqual(result['status'], 'breakpoint')
        state.diagnostic()
        self.assertEqual(state.events[-1]['message'], 'A')
        self.assertEqual(state.events[-1]['value'], 7)
        result = state.run({CALLER + 7}, limit=100)
        self.assertEqual(result['status'], 'breakpoint')
        self.assertEqual(state.regs['pc'], CALLER + 7)

    def test_missing_terminator_does_not_hide_unmapped_memory(self):
        state = ProbeState(0x6002304a, 0xf0, 16, b'A', {})
        with self.assertRaises(ValueError):
            state.read_c_string(BUFFER)
        self.assertEqual(state.read_c_string(BUFFER, limit=1), b'A')

    def test_unknown_entry_still_stops_on_native_memory_fault(self):
        state = ProbeState(0x19000000, 0xf0, 16, b'\0', {})
        result = state.run(set(), limit=100)
        self.assertEqual(result['status'], 'memory_fault')
        self.assertEqual(result['fault']['address'], 0x19000000)


if __name__ == '__main__':
    unittest.main(verbosity=2)
