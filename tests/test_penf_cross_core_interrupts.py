# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Scoped request, halt-wakeup frame, acknowledgement and cross-core isolation."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_boot_emulator import BootState
from penf_emulator import REGISTERS, Region
from penf_cross_core_interrupts import CrossCoreInterrupts
from penf_boot_cross_core import CrossCorePeer


class CrossCoreInterruptTests(unittest.TestCase):
    def fixture(self):
        s = BootState()
        s.regs = {k: 0 for k in REGISTERS}
        s.regs.update(pc=0x600701c9, sp=0x61773b80, psw=0x80000f00, d0=71)
        s.ram('cpu1_task_stack', 0x617fdb40, b'\xa5'*2048)
        s.ram('cpu1_running_state', 0x61bdd74c, b'\x01\x00')
        s.regions.append(Region('local_interrupt_source', 0x8a00, b'\x54\x00', 'r'))
        s.write(0x8008, struct.pack('<H', 0x68))
        s.write(0x801c, struct.pack('<I', 0x60030070))
        s.private_memory[1] = {r.name: r.data for r in s.regions if s.is_private(r)}
        s.cpu_regs[1] = {k: 0 for k in REGISTERS}
        s.cpu_regs[1].update(pc=0x600706ef, sp=0x617fe318, psw=0x80000f0a, d0=8, mdr=0x600706e0)
        s.blocked[1] = 'hypothetical private 8040 idle'
        s.write(0x993001e0, struct.pack('<I', 4))
        s.register(0x99300308, 'rw', 8)
        m = CrossCoreInterrupts(10)
        m.cross_requested = True
        m.pending.add((1, 120))
        m.resume = {'cpu0_interrupted_task': 'must survive CPU1 delivery'}
        m.active[0] = (58, 0x99200214)
        return s, m

    def test_wake_clear_native_rti_and_cpu0_state_preservation(self):
        s, m = self.fixture(); cpu0 = dict(s.regs); cpu1 = dict(s.cpu_regs[1]); pending0 = dict(m.resume)
        m.wake_cpu1(s)
        self.assertEqual(s.cpu, 1)
        self.assertEqual(s.cpu_regs[0], cpu0)
        self.assertEqual(m.resume, pending0)
        self.assertEqual(m.active[0], (58, 0x99200214))
        self.assertEqual(s.regs['pc'], 0x60030068)
        self.assertEqual(s.read(cpu1['sp']-4, 4), struct.pack('<I', cpu1['pc']))
        self.assertEqual(s.read(0x8a00, 2), b'\x48\x00')
        s.regs.update(pc=0x6006c90c, d0=8)
        self.assertTrue(m.acknowledge(s, {0x6006c90c}))
        self.assertEqual(s.read(0x99300308, 4), bytes(4))
        self.assertEqual(s.read(0x99300208, 4), bytes(4))
        self.assertNotIn((1, 120), m.pending)
        # Isolated frame test, not execution of the full native handler.
        for k in m.register_keys:
            if k != 'sp': s.regs[k] = cpu1[k]
        s.regs['pc'] = 0x6003952d
        r = s.run({cpu1['pc']}, limit=5)
        self.assertEqual(r['status'], 'breakpoint', r)
        m.returned(s)
        self.assertTrue(m.cross_returned)
        self.assertIsNone(m.cross_resume)
        self.assertEqual(m.resume, pending0)
        s.switch_core(0)
        self.assertEqual(s.regs, cpu0)
        self.assertEqual(s.read(0x8a00, 2), b'\x54\x00')

    def test_wake_guards_reject_without_changing_either_core(self):
        for case in ('sender', 'site', 'blocked', 'task', 'stack', 'mask', 'priority', 'status', 'pending', 'budget', 'repeated'):
            with self.subTest(case=case):
                s, m = self.fixture()
                if case == 'sender': s.regs['pc'] += 1
                if case == 'site': s.cpu_regs[1]['pc'] += 1
                if case == 'blocked': s.blocked.clear()
                if case == 'task': s.write(0x61bdd74c, b'\x02\x00')
                if case == 'stack': s.cpu_regs[1]['sp'] = 0x61820c00
                if case == 'mask': s.cpu_regs[1]['psw'] = 0xa00
                if case == 'priority': s.write(0x993001e0, struct.pack('<I', 3))
                if case == 'status': s.write(0x99300308, bytes(4))
                if case == 'pending': m.pending.clear()
                if case == 'budget': m.delivered = m.budget
                if case == 'repeated': m.cross_injected = True
                before, peer, regions = dict(s.regs), dict(s.cpu_regs[1]), list(s.regions)
                with self.assertRaises(ValueError): m.wake_cpu1(s)
                self.assertEqual(s.cpu, 0)
                self.assertEqual(s.regs, before)
                self.assertEqual(s.cpu_regs[1], peer)
                self.assertEqual(s.regions, regions)

    def test_native_request_requires_exact_queue_and_corrupt_return_rejects(self):
        s, m = self.fixture()
        m.cross_requested = False; m.pending.clear()
        s.ram('section_selector', 0xa1c583fc, struct.pack('<I', 3))
        s.ram('task_slot', 0xa1c274e0, struct.pack('<II', 0x600421e1, 0))
        s.ram('irq_slot', 0xa1c26cc8, struct.pack('<II', 0x600701ff, 0))
        s.ram('ring_indices', 0xa1c26fc8, b'\x01\x00')
        s.regs.update(pc=0x6006fda5, a0=0x99300308, d0=8)
        s.write(0xa1c583fc, struct.pack('<I', 4))
        with self.assertRaises(ValueError): m.request(s, {0x6006fda5})
        self.assertFalse(m.cross_requested)
        s.write(0xa1c583fc, struct.pack('<I', 3))
        self.assertTrue(m.request(s, {0x6006fda5}))
        self.assertEqual(s.regs['pc'], 0x6006fda6)
        self.assertIn((1, 120), m.pending)
        s.regs['pc'] = 0x600701c9
        m.wake_cpu1(s)
        s.regs = dict(m.cross_resume)
        with self.assertRaisesRegex(ValueError, 'before acknowledging'): m.returned(s)
        m.cross_acknowledged = True
        s.regs['a3'] ^= 1
        with self.assertRaisesRegex(ValueError, 'changed registers'): m.returned(s)

    def test_sender_resumption_does_not_deliver_a_second_interrupt(self):
        s, m = self.fixture()
        m.cross_injected = True
        m.cross_resume = dict(s.cpu_regs[1])
        peer = CrossCorePeer('bulk', 'next', 0)
        self.assertTrue(peer.handle(s, peer.hooks, m))
        self.assertEqual(s.cpu, 0)
        self.assertEqual(s.regs['pc'], 0x600701ca)
        self.assertEqual(s.regs['d0'], 0)  # Native instruction at sender return.
        self.assertEqual(m.delivered, 0)

    def test_new_observations_preserve_inherited_alex_landmarks(self):
        s, m = self.fixture()
        s.regs.update(pc=0x600272d8, d0=0x1234)
        peer = CrossCorePeer('bulk', 'next', 0)
        self.assertTrue(peer.handle(s, peer.hooks, m))
        self.assertEqual(s.regs['pc'], 0x600272de)
        self.assertEqual(s.read(0x8ff00070, 4), struct.pack('<I', 0x1234))
        self.assertTrue(any(e.get('name') == 'CPU1 stores Alex result' for e in s.events))


if __name__ == '__main__':
    unittest.main()
