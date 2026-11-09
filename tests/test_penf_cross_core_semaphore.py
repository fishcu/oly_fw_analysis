# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native remote-semaphore protocol; IRQ entry and kernel services isolated."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_probe import ProbeState, CALLER

REQUEST = 0xa1bed9b8
RECORD = (8, 0xffffffff, 0, 1, 1, 116, 0xffffffff, 0, 0, 0, 116, 0x101c, 3)


class CrossCoreSemaphoreTests(unittest.TestCase):
    def test_cpu0_request_irq_signals_service_task(self):
        s = ProbeState(0x6006c73f, 0, 0, bytes(1), {})
        s.register(0x99200308, 'rw', 1)
        s.register(0x9920030c, 'w')
        s.ram('cpu0_service_flag', 0x60041088, struct.pack('<H', 217))
        r = s.run({0x60039115}, limit=100)
        self.assertEqual(r['status'], 'breakpoint', r)
        self.assertEqual((s.regs['d0'], s.regs['d1']), (217, 0x80000000))
        self.assertEqual(s.read(0x9920030c, 4), struct.pack('<I', 1))
        s.write(0x99200308, bytes(4))  # Isolated W1C after the native write.
        s.return_from_model(0)  # Kernel flag delivery is tested in continuous replay later.
        r = s.run({CALLER+7}, limit=100)
        self.assertEqual(r['status'], 'breakpoint', r)
        self.assertEqual(s.regs['sp'], 0x18018000)

    def test_cpu0_service_scanner_requests_native_worker(self):
        s = ProbeState(0x6006c379, 0xf0, 68, bytes(1), {})
        s.register(0x8050, 'r', 0)
        s.ram('cpu1_requests', REQUEST, bytes(31*52))
        s.ram('cpu2_requests', 0xa1bee004, bytes(31*52))
        s.write(REQUEST, struct.pack('<13I', *RECORD))
        r = s.run({0x600306d3}, limit=100)
        self.assertEqual(r['status'], 'breakpoint', r)
        desc = s.read(s.regs['a0'], 24)
        self.assertEqual(desc[0], 2)
        self.assertEqual(struct.unpack_from('<IIH', desc, 4), (0, 0x6006bf73, 15))
        self.assertEqual(struct.unpack_from('<II', desc, 16), (1024, 0))
        self.assertEqual(s.read(REQUEST+48, 4), struct.pack('<I', 4))
        s.return_from_model(150)  # Isolated task creation; not an executed worker.
        r = s.run({CALLER+7, 0x600306d3}, limit=2000)
        self.assertEqual((r['status'], s.regs['pc']), ('breakpoint', CALLER+7))
        self.assertEqual(s.regs['sp'], 0x18018000)

    def test_remote_wait_result_and_reply_irq(self):
        for result in (0, 0xffffffce):
            with self.subTest(result=result):
                s = ProbeState(0x6006c483, 0xb0, 24, bytes(1), dict(a0=REQUEST))
                s.ram('cpu1_requests', REQUEST, bytes(31*52))
                s.write(REQUEST, struct.pack('<13I', *RECORD))
                s.register(0x99300308, 'rw')
                r = s.run({0x60037f9c}, limit=100)
                self.assertEqual(r['status'], 'breakpoint', r)
                self.assertEqual((s.regs['d0'], s.regs['d1']), (116, 0xffffffff))
                s.return_from_model(result)  # Native semaphore operation isolated.
                r = s.run({CALLER+7}, limit=100)
                self.assertEqual(r['status'], 'breakpoint', r)
                self.assertEqual(s.read(REQUEST+8, 4), struct.pack('<I', result))
                self.assertEqual(s.read(REQUEST+48, 4), struct.pack('<I', 5))
                self.assertEqual(s.read(0x99300308, 4), struct.pack('<I', 2))
                # Fresh function-entry probe: the CPU1 completion handler.
                t = ProbeState(0x6006c840, 0, 0, bytes(1), {})
                t.ram('cpu1_requests', REQUEST, s.read(REQUEST, 31*52))
                t.ram('cpu1_service_flag', 0x60041312, struct.pack('<H', 4115))
                t.register(0x99300308, 'rw', 2)
                t.register(0x9930030c, 'w')
                r = t.run({0x60039115}, limit=100)
                self.assertEqual(r['status'], 'breakpoint', r)
                self.assertEqual(t.read(REQUEST+48, 4), struct.pack('<I', 6))
                self.assertEqual((t.regs['d0'], t.regs['d1']), (4115, 1))
                self.assertEqual(t.read(0x9930030c, 4), struct.pack('<I', 2))
                t.write(0x99300308, bytes(4))
                t.return_from_model(0)
                r = t.run({CALLER+7}, limit=500)
                self.assertEqual(r['status'], 'breakpoint', r)
                self.assertEqual(t.regs['sp'], 0x18018000)


if __name__ == '__main__':
    unittest.main()
