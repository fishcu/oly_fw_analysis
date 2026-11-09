# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native command-0 reply parsing; transport, free and GPIO services isolated."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_probe import ProbeState, CALLER


class ControllerReplyTests(unittest.TestCase):
    def test_reply_value_error_gate_and_readiness_side_effect(self):
        cases = (
            (b'\x00\x00\x00', 0, 0, 0, 0),
            (b'\xff\xff\xff', 0, 0, 0, 0xffff),
            (b'\xe1\x23\xa4', 0, 0, 0, 0x1234),
            (b'\x01\x23\x04', 0, 1, 0, 0x1234),
            (b'\x01\x23\x04', 0, 1, 0x60193c20, 0x1234),
            (b'\x01\x23\x04', 0x8221, 1, 0x60193c20, 0xbeef),
        )
        for reply, status, enabled, callback, expected in cases:
            with self.subTest(reply=reply.hex(), status=status, enabled=enabled, callback=callback):
                request, descriptor, rx, tx = 0x18040000, 0x18040100, 0x18040200, 0x18040300
                s = ProbeState(0x60192f0e, 0, 0, bytes(1),
                    dict(a0=request, a1=descriptor, d0=status))
                s.ram('request', request, bytes(36))
                s.write(request+16, struct.pack('<H', 0xbeef))
                s.ram('transfer_descriptor', descriptor, struct.pack('<IIII', 0, tx, 0, rx))
                s.ram('reply', rx, reply)
                s.ram('controller_state', 0x6184fcc0, bytes(0x20))
                s.write(0x6184fcc0, struct.pack('<I', callback))
                s.write(0x6184fcd1, bytes((enabled,)))
                freed, gpio_calls = [], []
                for _ in range(4):
                    r = s.run({CALLER+7, 0x601936fe, 0x60083fe5}, limit=150)
                    self.assertEqual(r['status'], 'breakpoint', r)
                    if s.regs['pc'] == CALLER+7:
                        break
                    if s.regs['pc'] == 0x601936fe:
                        freed.append(s.regs['a0'])
                    else:
                        gpio_calls.append((s.regs['d0'], s.regs['a0']))
                    s.return_from_model(0)
                self.assertEqual(s.regs['pc'], CALLER+7)
                self.assertEqual(s.regs['sp'], 0x18018000)
                self.assertEqual(s.read(request+16, 2), struct.pack('<H', expected))
                self.assertEqual(s.read(0x6184fcd0, 1), bytes((int(status == 0),)))
                self.assertEqual(freed, [tx, rx])
                self.assertEqual(gpio_calls, [(96, callback)] if status == 0 and enabled and callback else [])


if __name__ == '__main__':
    unittest.main()
