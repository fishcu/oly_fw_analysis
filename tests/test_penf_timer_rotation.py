# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native timer cadence and ready-list rotation, isolated from boot replay."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_probe import ProbeState, CALLER


class TimerRotationTests(unittest.TestCase):
    def test_every_fifth_cpu0_tick_requests_priority_55_rotation(self):
        for previous in range(5):
            with self.subTest(previous=previous):
                s = ProbeState(0x6006e7f0, 0, 0, bytes(1), {})
                s.ram('rotation_counter', 0x6117101c, struct.pack('<I', previous))
                s.register(0x9890007c, 'w')
                r = s.run({0x60032307}, limit=30)
                self.assertEqual(r['status'], 'breakpoint')
                # Only isolate the kernel tick update; the native counter,
                # branch and rotation-call argument below execute normally.
                s.return_from_model(0)
                r = s.run({CALLER+7, 0x600321ca}, limit=40)
                self.assertEqual(r['status'], 'breakpoint')
                self.assertEqual(s.regs['pc'], 0x600321ca if previous == 4 else CALLER+7)
                self.assertEqual(int.from_bytes(s.read(0x6117101c, 4), 'little'), (previous+1) % 5)
                if previous == 4:
                    self.assertEqual(s.regs['d0'], 55)

    def test_native_ready_queue_rotates_head_to_tail(self):
        context, queues, nodes = 0x20100000, 0x20101000, 0x20102000
        head = queues+55*8
        for count in (0, 1, 3):
            with self.subTest(count=count):
                s = ProbeState(0x6003467e, 0xf0, 16, bytes(1), dict(d0=55))
                s.ram('cpu_index', 0x8050, bytes(4))
                s.ram('kernel_pointer', 0x8ff00004, struct.pack('<I', context))
                s.ram('kernel_context', context, bytes(68))
                s.write(context+64, struct.pack('<I', queues))
                s.ram('ready_queues', queues, b'\xa5'*512)
                s.ram('task_links', nodes, bytes(24))
                chain = [head]+[nodes+8*i for i in range(count)]
                for i, address in enumerate(chain):
                    s.write(address, struct.pack('<II', chain[(i+1) % len(chain)], chain[i-1]))
                untouched = s.read(queues, 55*8)
                r = s.run({CALLER+7}, limit=100)
                self.assertEqual(r['status'], 'breakpoint')
                expected = chain[2:]+chain[1:2] if count else []
                links = [head]+expected
                for i, address in enumerate(links):
                    self.assertEqual(s.read(address, 8), struct.pack('<II', links[(i+1) % len(links)], links[i-1]))
                self.assertEqual(s.read(queues, 55*8), untouched)


if __name__ == '__main__':
    unittest.main()
