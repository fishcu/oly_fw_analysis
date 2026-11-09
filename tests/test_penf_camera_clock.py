# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native clock initializer and rejection of unreviewed MMIO contexts."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from penf_boot_camera_clock import CameraClockPeer
from penf_probe import ProbeState

class CameraClockTests(unittest.TestCase):
    def test_native_initializer_from_real_caller(self):
        p=CameraClockPeer('bulk','next',0)
        s=ProbeState(0x602b74d8,0,4,b'x',{})
        s.regs['pc']=0x6025b939 # Execute the actual call, preserving native return/frame.
        s.ram('refcounts',0x6188448c,b'\xa5'*19)
        for _ in range(20):
            r=s.run(p.hooks|{0x6025b940},limit=20000)
            self.assertEqual(r['status'],'breakpoint')
            if s.regs['pc']==0x6025b940:break
            self.assertTrue(p.handle(s,p.hooks,None))
        self.assertEqual(s.regs['pc'],0x6025b940)
        self.assertTrue(p.camera_clock_finished)
        self.assertEqual(p.camera_clock_operation,8)
        self.assertEqual(s.read(0x6188448c,19),b'\0\0\1'+bytes(16))
        self.assertEqual(s.regs['sp'],0x18018000)
        for address in {x[1] for x in p.clock_operations}:
            with self.assertRaises(ValueError):s.read(address,4)

    def test_register_operations_require_active_correct_context(self):
        for active,operation,mdr in [(False,0,0x6008f904),(True,1,0x6008f904),(True,0,0)]:
            p=CameraClockPeer('bulk','next',0)
            p.camera_clock_active=active;p.camera_clock_operation=operation
            s=ProbeState(0x6008f2b5,0,0,b'x',dict(a0=0x98800050,mdr=mdr))
            s.regs['pc']=0x6008f2b5
            self.assertFalse(p.handle(s,p.hooks,None))
            self.assertEqual(s.steps,0)

if __name__=='__main__':unittest.main()
