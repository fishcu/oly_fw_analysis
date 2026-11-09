# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Remote IRQ frame/guard tests; complete native handlers remain replay evidence."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_boot_emulator import BootState
from penf_emulator import REGISTERS, Region
from penf_remote_semaphore_interrupts import RemoteSemaphoreInterrupts


class RemoteSemaphoreInterruptTests(unittest.TestCase):
    def fixture(self):
        s = BootState()
        s.regs = dict.fromkeys(REGISTERS, 0)
        s.regs.update(pc=0x600701c9, sp=0x61773b80, psw=0x80000f01, d0=71)
        s.write(0x6182385c, b'\x01\x00')
        s.ram('cpu1_dispatch_stack', 0x617f0038, b'\xa5'*1024)
        s.ram('cpu1_dispatch_state', 0x61bde37c, b'\x01\x00')
        s.ram('request', RemoteSemaphoreInterrupts.request_address,
              struct.pack('<13I', *RemoteSemaphoreInterrupts.request_words))
        s.regions.append(Region('local_interrupt_source', 0x8a00, b'\x54\x00', 'r'))
        s.write(0x8008, struct.pack('<H', 0x68))
        s.write(0x801c, struct.pack('<I', 0x60030070))
        s.private_memory[1] = {r.name:r.data for r in s.regions if s.is_private(r)}
        s.cpu_regs[1] = dict.fromkeys(REGISTERS, 0)
        s.cpu_regs[1].update(pc=0x6006c62f, sp=0x617f03ac, psw=0x80000f01,
                              a3=RemoteSemaphoreInterrupts.request_address, d0=1)
        for base in (0x99200000, 0x99300000):
            s.write(base+120*4, struct.pack('<I', 4))
        s.register(0x99300308, 'rw')
        s.switch_core(1)
        m = RemoteSemaphoreInterrupts(10)
        m.cross_acknowledged = True
        m.resume = {'earlier_cpu0_startup_context': 123}
        m.cross_resume = {'earlier_cpu1_initial_task_context': 456}
        m.active = {0:(58, 0x99200214), 1:(120, 0x99300208)}
        return s, m

    def native_frame_return(self, s, m, cpu):
        saved = m.remote_frames[cpu]['registers']
        for key in m.register_keys:
            if key != 'sp': s.regs[key] = saved[key]
        s.regs.update(pc=0x6003952d, sp=saved['sp']-8)
        r = s.run({saved['pc']}, limit=5)
        self.assertEqual(r['status'], 'breakpoint', r)
        m.remote_returned(s)

    def test_native_request_ack_and_frame_preserve_other_returns(self):
        s, m = self.fixture(); startup, initial = m.resume, m.cross_resume
        cpu0 = dict(s.cpu_regs[0])
        self.assertTrue(m.send_request(s, {0x6006c62f}))
        self.assertEqual(s.cpu, 0)
        self.assertEqual(s.cpu_regs[1]['pc'], 0x6006c635)
        self.assertEqual(s.regs['pc'], 0x60030068)
        self.assertEqual(s.read(cpu0['sp']-4, 4), struct.pack('<I', cpu0['pc']))
        s.regs.update(pc=0x6006c756, d0=1)
        self.assertTrue(m.acknowledge_remote(s, {0x6006c756}))
        self.assertEqual(s.read(0x99200308, 4), bytes(4))
        self.native_frame_return(s, m, 0)
        self.assertEqual(s.regs['sp'], cpu0['sp'])
        self.assertEqual(m.active[0], (58, 0x99200214))
        self.assertIs(m.resume, startup)
        self.assertIs(m.cross_resume, initial)
        self.assertEqual(m.remote_returns, [0])

    def test_native_reply_ack_and_frame_leave_cpu0_suspension_intact(self):
        s, m = self.fixture()
        m.send_request(s, {0x6006c62f})
        s.regs.update(pc=0x6006c756, d0=1)
        m.acknowledge_remote(s, {0x6006c756})
        frame0 = m.remote_frames[0]
        s.write(m.request_address+48, struct.pack('<I', 5))
        s.write(m.request_address+8, struct.pack('<I', 0xffffffce))
        s.regs.update(pc=0x6006c577, d0=2, a2=m.request_address+12)
        self.assertTrue(m.send_reply(s, {0x6006c577}))
        self.assertEqual(s.cpu, 1)
        self.assertEqual(s.cpu_regs[0]['pc'], 0x6006c57d)
        self.assertEqual(m.record(s)[2], 0xffffffce)
        s.regs.update(pc=0x6006c88e, d0=2)
        self.assertTrue(m.acknowledge_remote(s, {0x6006c88e}))
        self.native_frame_return(s, m, 1)
        self.assertIs(m.remote_frames[0], frame0)
        self.assertEqual(m.remote_returns, [1])
        self.assertEqual(m.pending, set())

    def test_request_guard_rejects_before_write_or_core_switch(self):
        for case in ('record', 'task', 'pc', 'stack', 'mask', 'priority', 'blocked', 'budget', 'repeat', 'handoff'):
            with self.subTest(case=case):
                s, m = self.fixture()
                if case == 'record': s.write(m.request_address, struct.pack('<I', 7))
                if case == 'task': s.write(0x6182385c, b'\x02\x00')
                if case == 'pc': s.cpu_regs[0]['pc'] += 1
                if case == 'stack': s.cpu_regs[0]['sp'] = 0x61820c00
                if case == 'mask': s.cpu_regs[0]['psw'] = 0xa00
                if case == 'priority': s.write(0x992001e0, struct.pack('<I', 3))
                if case == 'blocked': s.blocked[0] = 'unreviewed wait'
                if case == 'budget': m.delivered = m.budget
                if case == 'repeat': m.remote_sent = True
                if case == 'handoff': m.cross_acknowledged = False
                before, peer, regions = dict(s.regs), dict(s.cpu_regs[0]), list(s.regions)
                with self.assertRaises(ValueError): m.send_request(s, {0x6006c62f})
                self.assertEqual((s.cpu, s.regs, s.cpu_regs[0], s.regions), (1, before, peer, regions))

    def test_return_requires_acknowledgement_and_intact_registers(self):
        s, m = self.fixture(); m.send_request(s, {0x6006c62f})
        saved = m.remote_frames[0]['registers']
        s.regs = dict(saved)
        with self.assertRaisesRegex(ValueError, 'before acknowledgement'): m.remote_returned(s)
        m.remote_frames[0]['acknowledged'] = True
        s.regs['a0'] ^= 1
        with self.assertRaisesRegex(ValueError, 'changed registers'): m.remote_returned(s)


if __name__ == '__main__':
    unittest.main()
