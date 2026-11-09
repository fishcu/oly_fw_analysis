# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Isolated service-3 routing; full boot must still execute the kernel flag set."""
import struct
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_probe import ProbeState, CALLER
import penf_boot_section_completion as driver
import test_penf_semaphore_release as release_tests


class SectionCompletionProtocolTests(unittest.TestCase):
    def completion_fixture(self):
        s, old, _, worker = release_tests.SemaphoreReleaseTests().fixture()
        m = driver.SectionCompletionInterrupts(10)
        m.__dict__.update(old.__dict__)
        # Guard fixture for the second worker; native deletion is a replay result.
        m.release_phase = 'release'
        m.remote_returns = [1, 0, 1]
        s.write(m.request_address, struct.pack('<13I', *m.completion_words))
        s.write(0x6182abe0, struct.pack('<I', 1))
        s.write(0x6182dddc, bytes(4))
        return s, m

    def test_completion_waits_for_release_worker_and_restores_sender(self):
        s, m = self.completion_fixture()
        sender = dict(s.regs)
        m.send_request(s, {0x6006c62f})
        self.assertEqual((m.completion_phase, s.cpu), ('cleanup', 0))
        self.assertEqual(s.read(0x99200308, 4), bytes(4))
        s.regs = dict(m.remote_frames[0]['registers'])
        s.task_snapshot = lambda cpu: []
        m.release_cleanup_entered = True
        m.finish_release_cleanup(s)
        self.assertEqual((s.cpu, s.regs), (1, sender))
        self.assertEqual(m.remote_returns, [1, 0, 1, 0])
        m.send_request(s, {0x6006c62f})
        self.assertEqual((m.completion_phase, s.cpu), ('sent', 0))
        self.assertEqual(m.request_words, m.completion_words)
        self.assertEqual(s.read(0x99200308, 4), struct.pack('<I', 1))

    def test_wrong_flag_or_unreleased_semaphore_stops_without_native_write(self):
        for address, value in ((0x6182abe0, 0), (0x6182dddc, 4), (0xa1bed9cc, 183)):
            with self.subTest(address=address):
                s, m = self.completion_fixture()
                s.write(address, struct.pack('<I', value))
                before = s.cpu, dict(s.regs), list(s.regions)
                with self.assertRaises(ValueError): m.send_request(s, {0x6006c62f})
                self.assertEqual((s.cpu, s.regs, s.regions), before)
                self.assertEqual(m.completion_phase, 'pending')

    def test_driver_preserves_inherited_class_contract_and_restores_bindings(self):
        old_peer, old_irq = driver.release.SemaphoreReleasePeer, driver.release.SemaphoreReleaseInterrupts
        reports = []
        def inner_main():
            cls = driver.release.SemaphoreReleaseInterrupts
            self.assertEqual(cls.boundaries, old_irq.boundaries)
            cls(10)
            reports.append(driver.boot.boot_experiment()[0])
        def experiment(): return {'source_sha256':{}}, object()
        with patch.object(driver.release, 'main', inner_main), patch.object(driver.boot, 'boot_experiment', experiment):
            driver.main()
            self.assertIs(driver.boot.boot_experiment, experiment)
        self.assertEqual(reports[0]['section_completion_scenario']['phase'], 'pending')
        self.assertIs(driver.release.SemaphoreReleasePeer, old_peer)
        self.assertIs(driver.release.SemaphoreReleaseInterrupts, old_irq)

    def test_section3_completion_routes_to_native_flag_set(self):
        address = 0xa1bed9b8
        record = (3, 0, 0, 1, 1, 182, 4, 0, 0, 0, 182, 0x101c, 3)
        for result in (0, 0xffffffd6):
            with self.subTest(result=result):
                s = ProbeState(0x6006c483, 0xb0, 24, bytes(1), dict(a0=address))
                s.ram('cpu1_request', address, struct.pack('<13I', *record))
                s.register(0x99300308, 'rw')
                r = s.run({0x600366eb}, limit=100)
                self.assertEqual((r['status'], s.regs['pc']), ('breakpoint', 0x600366eb))
                self.assertEqual((s.regs['d0'], s.regs['d1']), (182, 4))
                s.return_from_model(result)  # Deliberately isolated kernel operation.
                r = s.run({CALLER+7}, limit=100)
                self.assertEqual((r['status'], s.regs['pc']), ('breakpoint', CALLER+7))
                self.assertEqual(s.read(address+8, 4), struct.pack('<I', result))
                self.assertEqual(s.read(address+48, 4), struct.pack('<I', 5))
                self.assertEqual(s.read(0x99300308, 4), struct.pack('<I', 2))


if __name__ == '__main__':
    unittest.main()
