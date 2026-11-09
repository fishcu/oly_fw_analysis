# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Instruction-scoped controller reads and native retained-media consumer."""
import struct
import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_probe import ProbeState, CALLER
from penf_boot_retained_state import RetainedStatePeer
from penf_alex_bulk_model import AlexBulkPeer


class RetainedStateTests(unittest.TestCase):
    def test_inherited_alex_read_still_executes_and_restores_shadow(self):
        s = ProbeState(0x6007d06e, 0, 0, b'x', dict(a2=0x9bf00044))
        s.cpu = 1
        s.register(0x9bf00044, 'w', 0x1234)
        p = RetainedStatePeer('bulk', 'next', 0)
        self.assertEqual(s.run({0x6007d06e}, limit=10)['status'], 'breakpoint')
        self.assertTrue(p.handle(s, p.hooks, None))
        self.assertEqual(s.regs['d0'], 0)
        self.assertEqual(s.read(0x9bf00044, 4), struct.pack('<I', 0x1234))
        self.assertEqual(p.landmarks, AlexBulkPeer.landmarks)
        self.assertEqual(next(r.permissions for r in s.regions if r.address == 0x9bf00044), 'w')

    def fixture(self):
        s = ProbeState(0x601a88cf, 0xc0, 20, b'x', {})
        s.cpu = 0
        s.ram('translated_reason', 0xa1c57fd0, struct.pack('<I', 0x1000001))
        s.ram('previous_off', 0x616fc934, bytes(1))
        s.ram('early_snapshot', 0x6181e340, bytes(4))
        s.ram('skip_marker', 0x618656b6, bytes(2))
        for i in range(5):
            s.register(0x98e00058+4*i, 'rw', 0xffff if i == 2 else 0)
        s.register(0x98e00000, 'w', 0)
        p = RetainedStatePeer.__new__(RetainedStatePeer)
        p.retained_active = False
        p.retained_finished = False
        p.retained_reads = []
        return s, p

    def test_native_consumer_read_clear_and_register_scope(self):
        s, p = self.fixture()
        hooks = {0x601a88cf, CALLER+7} | set(p.retained_register_reads)
        self.assertEqual(s.run(hooks, limit=10)['status'], 'breakpoint')
        self.assertTrue(p.handle(s, hooks, None))
        for _ in range(5):
            result = s.run(hooks, limit=500)
            self.assertEqual(result['status'], 'breakpoint')
            pc = s.regs['pc']
            if pc == CALLER+7:
                break
            if pc == 0x601a8932:
                # Production input getter leaves configuration shadows write-only.
                s.regions = [replace(r, permissions='w') if r.address == 0x98e00060
                             else r for r in s.regions]
            self.assertTrue(p.handle(s, hooks, None))
        self.assertEqual(s.regs['pc'], CALLER+7)
        self.assertEqual((s.regs['d0'], s.regs['sp']), (0, 0x18018000))
        self.assertEqual(p.retained_reads, list(p.retained_register_reads))
        self.assertEqual(s.read(0x98e00000, 4), bytes(4))
        self.assertEqual(s.read(0x98e00060, 4), struct.pack('<I', 0xffff))
        for address in (0x98e00000, 0x98e00060):
            self.assertEqual(next(r.permissions for r in s.regions if r.address == address), 'w')
        self.assertFalse(any(r.address == 0x98e00054 for r in s.regions))

    def test_wrong_order_core_pointer_and_control_are_rejected(self):
        for variation in ('order', 'core', 'pointer', 'control'):
            with self.subTest(variation=variation):
                s, p = self.fixture()
                p.retained_active = True
                p.retained_reads = [0x601a8932]
                s.regs.update(pc=0x6007d89a, a0=0x98e00000)
                if variation == 'order': p.retained_reads = []
                if variation == 'core': s.cpu = 1
                if variation == 'pointer': s.regs['a0'] += 4
                if variation == 'control': s.write(0x98e00000, struct.pack('<I', 0x10000))
                before = list(s.regions), dict(s.regs), list(p.retained_reads)
                with self.assertRaises(ValueError): p.sample(s, set())
                self.assertEqual((s.regions, s.regs, p.retained_reads), before)


if __name__ == '__main__':
    unittest.main()
