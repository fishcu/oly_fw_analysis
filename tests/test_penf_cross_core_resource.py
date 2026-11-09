# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native CPU1 request dispatch; IRQ entry/wakeup and kernel queues are isolated."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_probe import ProbeState, CALLER


class CrossCoreResourceTests(unittest.TestCase):
    def test_irq120_body_drains_cpu0_ring_and_posts_task_message(self):
        for pending, read_index in ((False, 0), (True, 0), (True, 31)):
            with self.subTest(pending=pending, read_index=read_index):
                s = ProbeState(0x6006c840, 0, 0, bytes(1), {})
                s.register(0x99300308, 'rw', 8 if pending else 0)
                s.register(0x9930030c, 'w')
                s.ram('cpu0_to_cpu1_ring', 0xa1c26cc8, bytes(0x308))
                write_index = (read_index+1) % 32 if pending else read_index
                s.write(0xa1c26fc8, bytes((write_index, read_index)))
                s.write(0xa1c26cc8+8*read_index, struct.pack('<II', 0x600701ff, 5))
                s.ram('cpu1_dispatch_queue_id', 0xa1c276e4, struct.pack('<I', 17))
                r = s.run({CALLER+7, 0x6006c912}, limit=100)
                self.assertEqual(r['status'], 'breakpoint', r)
                if pending:
                    self.assertEqual(s.regs['pc'], 0x6006c912)
                    self.assertEqual(s.read(0x9930030c, 4), struct.pack('<I', 8))
                    # Model only the write-one-to-clear effect after the native write.
                    s.write(0x99300308, bytes(4))
                    r = s.run({0x600320ca}, limit=100)
                    self.assertEqual(r['status'], 'breakpoint', r)
                    self.assertEqual((s.regs['d0'], s.regs['d1']), (17, 5))
                    # Native dispatch runs; kernel message delivery is isolated here.
                    s.return_from_model(0)
                    r = s.run({CALLER+7}, limit=150)
                    self.assertEqual(r['status'], 'breakpoint', r)
                self.assertEqual(s.regs['pc'], CALLER+7)
                self.assertEqual(s.regs['sp'], 0x18018000)
                self.assertEqual(s.read(0xa1c26fc9, 1), bytes((write_index,)))

    def test_cpu1_dispatch_task_selects_source_and_reaches_loader(self):
        for source, table in ((0, 0xa1c274e0), (2, 0xa1c275e0)):
            with self.subTest(source=source):
                s = ProbeState(0x600702de, 0, 0, bytes(1), {})
                s.ram('cpu1_task_dispatch', 0xa1c274e0, bytes(0x208))
                s.write(table+8*5, struct.pack('<II', 0x600421e1, 0x12345678))
                r = s.run({0x60069ef2}, limit=30)
                self.assertEqual(r['status'], 'breakpoint', r)
                self.assertEqual((s.regs['d0'], s.regs['d1'], s.regs['a0']), (0, 33, 0))
                s.return_from_model(17)  # Isolated kernel queue creation.
                r = s.run({0x6003782e}, limit=100)
                self.assertEqual(r['status'], 'breakpoint', r)
                self.assertEqual((s.regs['d0'], s.regs['d1']), (17, 0xffffffff))
                s.write(s.regs['a0'], struct.pack('<I', source << 16 | 5))
                s.return_from_model(0)  # Isolated kernel receive.
                r = s.run({0x600421e1}, limit=100)
                self.assertEqual(r['status'], 'breakpoint', r)
                self.assertEqual(s.regs['pc'], 0x600421e1)
                self.assertEqual(s.regs['a0'], 0x12345678)


if __name__ == '__main__':
    unittest.main()
