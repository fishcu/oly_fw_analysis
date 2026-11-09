#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Check isolation and fail-closed behavior in the cooperative boot harness."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from penf_boot_emulator import BootState, HOOK_RETURN


class BootModelTests(unittest.TestCase):
    def test_enabling_register_writes_preserves_them_across_checkpoints(self):
        s=BootState()
        self.assertFalse(next(r for r in s.regions if r.address==0x98e00058).capture)
        s.register(0x98e00058,'w')
        self.assertTrue(next(r for r in s.regions if r.address==0x98e00058).capture)
        # Execute the real controller bank write, then a fresh engine segment.
        s.regs.update(pc=0x6007d941,d1=0x20ff)
        first=s.run({0x6007d947})
        self.assertEqual(first['status'],'breakpoint')
        self.assertEqual(s.read(0x98e00058,4),struct.pack('<I',0x20ff))
        s.regs['pc']=0x60021024 # native nop
        s.run(set(),limit=1)
        self.assertEqual(s.read(0x98e00058,4),struct.pack('<I',0x20ff))

    def test_core_switch_preserves_private_state_and_shares_globals(self):
        s = BootState()
        s.write(0x47000000, b'CORE')
        s.write(0x8ff00000, struct.pack('<I', 1))
        s.regs['d2'] = 1234
        s.notify_core(1)
        s.switch_core(1)
        self.assertEqual(s.regs['pc'], 0x60027035)
        self.assertEqual(s.read(0x8050, 4), struct.pack('<I', 1))
        self.assertEqual(s.read(0x8958, 2), b'\x10\x00')
        self.assertEqual(s.read(0x47000000, 4), b'\xa5'*4)
        self.assertEqual(s.read(0x8ff00000, 4), struct.pack('<I', 1))
        s.write(0x47000000, b'PEER')
        s.write(0x8ff00000, struct.pack('<I', 3))
        s.switch_core(0)
        self.assertEqual(s.read(0x47000000, 4), b'CORE')
        self.assertEqual(s.read(0x8ff00000, 4), struct.pack('<I', 3))
        self.assertEqual(s.read(0x8958, 2), b'\0\0')
        self.assertEqual(s.regs['d2'], 1234)
        s.switch_core(1)
        self.assertEqual(s.read(0x47000000, 4), b'PEER')

    def test_aliases_share_harness_writes_but_unknown_memory_is_absent(self):
        s = BootState()
        s.write(0xa181e340, b'ABCD')
        self.assertEqual(s.read(0x6181e340, 4), b'ABCD')
        s.write(0x6181e340, b'EFGH')
        self.assertEqual(s.read(0xa181e340, 4), b'EFGH')
        with self.assertRaises(ValueError):
            s.read(0x98e000a4, 4)  # No automatic controller reply.
        with self.assertRaises(ValueError):
            s.ram('overlap', 0x6181e33f, bytes(16))

    def test_wait_does_not_invent_ready_peers(self):
        s = BootState()
        self.assertTrue(s.schedule_wait('first'))
        self.assertEqual(s.cpu, 1)
        self.assertTrue(s.schedule_wait('second'))
        self.assertEqual(s.cpu, 2)
        self.assertFalse(s.schedule_wait('third'))
        s.notify_core(0)
        self.assertTrue(s.schedule_wait('third'))
        self.assertEqual(s.cpu, 0)
        self.assertEqual(s.read(0x8958, 2), b'\x10\0')

    def test_model_return_requires_call_to_current_boundary(self):
        s = BootState()
        # Native call at 60041ae9 targets the diagnostic sink.
        s.regs.update(pc=0x60023e05, mdr=0x60041af0)
        s.return_from_model(7)
        self.assertEqual(s.read(HOOK_RETURN, 3), bytes.fromhex('df0004'))
        self.assertEqual(s.regs['d0'], 7)
        s.regs.update(pc=0x600213ed, mdr=0x60041af0)
        with self.assertRaises(ValueError):
            s.return_from_model()


if __name__ == '__main__':
    unittest.main(verbosity=2)
