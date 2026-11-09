# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Exercise real diagnostic availability reads and the native no-input branch."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_boot_console_idle import ConsoleIdlePeer
from penf_probe import ProbeState, CALLER, RESULT


class ConsoleIdleTests(unittest.TestCase):
    def fixture(self, target=0x6006d24f):
        s = ProbeState(target, 0, 0, bytes(16), {})
        s.ram('diagnostic_selection', 0x8ff0007c, b'\0\1', aliases=False)
        return s, ConsoleIdlePeer('bulk', 'next', 0)

    def test_read_faults_without_model(self):
        s, _ = self.fixture()
        result = s.run({CALLER+7}, limit=1000)
        self.assertEqual(result['status'], 'memory_fault')
        self.assertEqual(result['fault']['address'], 0x9870000c)

    def test_native_zero_read_then_return(self):
        for target in (0x6006d24f, 0x6006d22c):
            s, peer = self.fixture(target)
            result = s.run(peer.hooks | {CALLER+7}, limit=1000)
            self.assertEqual(result['status'], 'breakpoint')
            self.assertTrue(peer.handle(s, peer.hooks | {CALLER+7}, None))
            result = s.run({CALLER+7}, limit=1000)
            self.assertEqual(result['status'], 'breakpoint')
            self.assertEqual(s.regs['pc'], CALLER+7)
            self.assertEqual(s.regs['d0'], 0)
            self.assertEqual(s.regs['sp'], 0x18018000)
            self.assertFalse(any(r.address == 0x9870000c for r in s.regions))

    def test_empty_shell_branch_for_both_console_modes(self):
        for mode, boundary in ((1, 0x6006fbeb), (3, 0x6006fc10)):
            s, _ = self.fixture(0x6006fbf0)
            s.write(0x8ff0007d, bytes((mode,)))
            s.regs['d0'] = 0
            result = s.run({0x6003172b}, limit=1000)
            self.assertEqual(result['status'], 'breakpoint')
            self.assertEqual(s.regs['d0'], 50)
            s.return_from_model(0)  # Isolated test only; full boot executes RTOS wait.
            result = s.run({0x6006fbeb, 0x6006fc05, 0x6006fc10}, limit=1000)
            self.assertEqual(result['status'], 'breakpoint')
            self.assertEqual(s.regs['pc'], boundary)

    def test_native_line_reader_waits_without_reading_fifo(self):
        s = ProbeState(0x6006fb2e, 0xe0, 16, bytes(16), dict(a0=RESULT))
        s.ram('diagnostic_selection', 0x8ff0007c, b'\0\3', aliases=False)
        peer = ConsoleIdlePeer('bulk', 'next', 0)
        result = s.run(peer.hooks | {0x6003172b}, limit=1000)
        self.assertEqual(result['status'], 'breakpoint')
        self.assertTrue(peer.handle(s, peer.hooks, None))
        result = s.run({0x6003172b}, limit=1000)
        self.assertEqual(result['status'], 'breakpoint')
        self.assertEqual(s.regs['d0'], 50)
        s.return_from_model(0)
        result = s.run({0x6006fb30, 0x6006fb43}, limit=1000)
        self.assertEqual(result['status'], 'breakpoint')
        self.assertEqual(s.regs['pc'], 0x6006fb30)
        self.assertEqual(s.read(RESULT, 16), bytes(16))

    def test_other_port_requires_review(self):
        s, peer = self.fixture()
        s.regs.update(pc=0x6006d25e, a0=0x9840000c)
        with self.assertRaises(AssertionError):
            peer.handle(s, peer.hooks, None)

    def test_existing_boot_write_shadow_is_restored(self):
        s, peer = self.fixture()
        s.register(0x9870000c, 'w', 0xdeadbeef)
        old = next(r for r in s.regions if r.address == 0x9870000c)
        result = s.run(peer.hooks | {CALLER+7}, limit=1000)
        self.assertEqual(result['status'], 'breakpoint')
        self.assertTrue(peer.handle(s, peer.hooks, None))
        self.assertEqual(s.regs['d0'], 0)
        self.assertEqual(next(r for r in s.regions if r.address == 0x9870000c), old)

    def test_unreviewed_readable_mapping_stops(self):
        s, peer = self.fixture()
        s.register(0x9870000c, 'r', 1)
        s.regs.update(pc=0x6006d25e, a0=0x9870000c)
        self.assertFalse(peer.handle(s, peer.hooks, None))
        self.assertEqual(s.steps, 0)


if __name__ == '__main__':
    unittest.main()
