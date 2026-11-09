# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Release guards and native request/reply writes; connected replay proves cleanup."""
import struct
import unittest
from unittest.mock import patch

import test_penf_remote_semaphore_interrupts as existing
import penf_boot_semaphore_release as driver
from penf_semaphore_release_interrupts import SemaphoreReleaseInterrupts


class SemaphoreReleaseTests(unittest.TestCase):
    def fixture(self):
        helper = existing.RemoteSemaphoreInterruptTests()
        s, first = helper.fixture()
        m = SemaphoreReleaseInterrupts(10)
        m.__dict__.update(first.__dict__)
        m.send_request(s, {0x6006c62f})
        s.regs.update(pc=0x6006c756, d0=1)
        m.acknowledge_remote(s, {0x6006c756})
        s.write(m.request_address+48, struct.pack('<I', 5))
        s.regs.update(pc=0x6006c577, d0=2, a2=m.request_address+12, sp=0x6171f6d0)
        m.send_reply(s, {0x6006c577})
        s.regs.update(pc=0x6006c88e, d0=2)
        m.acknowledge_remote(s, {0x6006c88e})
        helper.native_frame_return(s, m, 1)
        s.write(m.request_address, struct.pack('<13I', *m.release_words))
        s.write(0x6182abe0, bytes(4))
        s.regs.update(pc=0x6006c62f, d0=1, a3=m.request_address)
        worker = dict(id=141, state=1, entry='0x6006bf73', priority=15,
                      stack='0x6171f2f4', stack_bytes=1024, tcb='0x61826704')
        s.task_snapshot = lambda cpu: [worker]  # Guard fixture, not native task deletion.
        return s, m, helper, worker

    def prepare_release(self):
        s, m, helper, worker = self.fixture()
        sender = dict(s.regs)
        self.assertTrue(m.send_request(s, {0x6006c62f}))
        self.assertEqual((s.cpu, s.regs['pc']), (0, 0x6006c57d))
        self.assertEqual(s.read(0x99200308, 4), bytes(4))
        self.assertEqual(m.remote_returns, [1])
        # Only the connected replay executes deletion and restores this frame.
        s.regs = dict(m.remote_frames[0]['registers'])
        s.task_snapshot = lambda cpu: []
        m.cleanup_entered = True
        m.finish_cleanup(s)
        self.assertEqual((s.cpu, s.regs), (1, sender))
        self.assertEqual(m.remote_returns, [1, 0])
        self.assertEqual(m.remote_frames, {})
        return s, m, helper

    def test_release_reuses_protocol_without_losing_older_contexts(self):
        s, m, helper = self.prepare_release()
        startup, initial = m.resume, m.cross_resume
        m.send_request(s, {0x6006c62f})
        self.assertEqual(m.release_phase, 'release')
        self.assertEqual(s.read(0x99200308, 4), struct.pack('<I', 1))
        s.regs.update(pc=0x6006c756, d0=1)
        m.acknowledge_remote(s, {0x6006c756})
        s.write(m.request_address+48, struct.pack('<I', 5))
        s.regs.update(pc=0x6006c577, d0=2, a2=m.request_address+12)
        m.send_reply(s, {0x6006c577})
        s.regs.update(pc=0x6006c88e, d0=2)
        m.acknowledge_remote(s, {0x6006c88e})
        helper.native_frame_return(s, m, 1)
        self.assertEqual(m.remote_returns, [1, 0, 1])
        self.assertIs(m.resume, startup)
        self.assertIs(m.cross_resume, initial)

    def test_defer_rejects_unreviewed_context_before_switch_or_write(self):
        for case in ('record', 'worker_pc', 'worker_stack', 'worker_state', 'semaphore', 'ack'):
            with self.subTest(case=case):
                s, m, _, worker = self.fixture()
                if case == 'record': s.write(m.request_address, struct.pack('<I', 6))
                if case == 'worker_pc': s.cpu_regs[0]['pc'] += 1
                if case == 'worker_stack': s.cpu_regs[0]['sp'] = 0
                if case == 'worker_state': worker['state'] = 2
                if case == 'semaphore': s.write(0x6182abe0, struct.pack('<I', 1))
                if case == 'ack': m.remote_frames[0]['acknowledged'] = False
                before = (s.cpu, dict(s.regs), list(s.regions))
                with self.assertRaises(ValueError): m.send_request(s, {0x6006c62f})
                self.assertEqual((s.cpu, s.regs, s.regions), before)
                self.assertEqual(m.release_phase, 'acquire')

    def test_release_cannot_overwrite_an_outstanding_return(self):
        s, m, _ = self.prepare_release()
        m.remote_frames[0] = {'still_pending':True}
        before = (s.cpu, dict(s.regs), list(s.regions))
        with self.assertRaisesRegex(ValueError, 'pending'): m.send_request(s, {0x6006c62f})
        self.assertEqual((s.cpu, s.regs, s.regions), before)

    def test_driver_retains_class_interface_and_restores_original_bindings(self):
        old_peer, old_irq = driver.remote.RemoteSemaphorePeer, driver.remote.RemoteSemaphoreInterrupts
        reports = []

        def inner_main():
            cls = driver.remote.RemoteSemaphoreInterrupts
            self.assertEqual(cls.boundaries, old_irq.boundaries)
            cls(10)
            reports.append(driver.boot.boot_experiment()[0])

        def experiment():
            return {'source_sha256':{}}, object()

        with patch.object(driver.remote, 'main', inner_main), patch.object(driver.boot, 'boot_experiment', experiment):
            driver.main()
            self.assertIs(driver.boot.boot_experiment, experiment)
        self.assertEqual(reports[0]['semaphore_release_scenario']['phase'], 'acquire')
        self.assertIs(driver.remote.RemoteSemaphorePeer, old_peer)
        self.assertIs(driver.remote.RemoteSemaphoreInterrupts, old_irq)


if __name__ == '__main__':
    unittest.main()
