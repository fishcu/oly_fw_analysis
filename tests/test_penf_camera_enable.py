# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native enable preserves other bits and rejects unreviewed contexts."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from penf_boot_camera_enable import CameraEnablePeer
from penf_probe import ProbeState


class CameraEnableTests(unittest.TestCase):
    def test_native_bit_preservation_and_mapping_cleanup(self):
        for old in (0,0x80000080):
            p=CameraEnablePeer('bulk','next',0)
            p.camera_clock_finished=True;p.enable_old=old
            s=ProbeState(0x602a46c1,0,0,b'x',dict(d0=1))
            s.regs['pc']=0x602a4334
            for _ in range(8):
                r=s.run(p.hooks|{0x602a4339},limit=100)
                self.assertEqual(r['status'],'breakpoint',r)
                if s.regs['pc']==0x602a4339:break
                self.assertTrue(p.handle(s,p.hooks,None))
            self.assertEqual(s.regs['pc'],0x602a4339)
            self.assertEqual(s.regs['d0'],old|1)
            self.assertEqual(p.enable_stage,4)
            with self.assertRaises(ValueError):s.read(0x9b000500,4)

    def test_unreviewed_context_is_rejected(self):
        for finished,stage,mdr in [(False,0,0x602a4339),(True,4,0x602a4339),(True,0,0)]:
            p=CameraEnablePeer('bulk','next',0)
            p.camera_clock_finished=finished;p.enable_stage=stage
            s=ProbeState(0x602a46c1,0,0,b'x',dict(d0=1,mdr=mdr))
            s.regs['pc']=0x602a46c1
            self.assertFalse(p.handle(s,p.hooks,None))
            self.assertEqual(s.steps,0)


if __name__=='__main__':unittest.main()
