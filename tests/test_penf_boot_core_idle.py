#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native write, core parking and bounded timer eligibility checks."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_boot_core_idle import CoreIdlePeer, CoreIdleInterrupts
from penf_probe import ProbeState


class CoreIdleTests(unittest.TestCase):
    def state(self, cpu):
        pc = 0x600706ec if cpu == 1 else 0x60070b72
        s = ProbeState(pc, 0, 4, bytes(16), dict(d0=8))
        s.cpu = cpu
        s.regs['pc'] = pc
        s.cpu_regs = {0:dict(pc=0x6003718b, psw=0, sp=0x18018000)}
        s.private_memory = {}
        s.blocked = {3-cpu:'unrelated waiting core'}
        s.register(0x8050, 'rw', cpu)
        return s

    def test_native_write_parks_only_its_core_and_notification_releases_it(self):
        for cpu, after in ((1, 0x600706ef), (2, 0x60070b75)):
            with self.subTest(cpu=cpu):
                s, peer = self.state(cpu), CoreIdlePeer(low_memory_word=0)
                self.assertTrue(peer.handle(s, peer.hooks, None))
                self.assertEqual(s.cpu, 0)
                self.assertEqual(s.regs['pc'], 0x6003718b)
                self.assertEqual(s.cpu_regs[cpu]['pc'], after)
                self.assertIn(cpu, s.blocked)
                self.assertFalse(any(r.address == 0x8040 for r in s.regions))
                s.notify_core(cpu)
                self.assertNotIn(cpu, s.blocked)
                s.switch_core(cpu)
                self.assertEqual(s.regs['pc'], after)

    def test_no_timer_injected_at_unreviewed_core_idle_site(self):
        s = self.state(2)
        s.cpu_regs[0]['pc'] = 0x600706ef
        irq = CoreIdleInterrupts(10)
        self.assertFalse(irq.timer(s))
        self.assertEqual(irq.delivered, 0)
        self.assertEqual(s.cpu, 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
