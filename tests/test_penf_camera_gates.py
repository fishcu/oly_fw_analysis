# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native gate helpers retain/clear only requested bits under scoped models."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from penf_boot_camera_gates import CameraGatesPeer
from penf_probe import ProbeState


class CameraGateTests(unittest.TestCase):
    def test_native_enable_clear_sequence(self):
        for initial in (0,0x80000000):
            p=CameraGatesPeer('bulk','next',0);p.gates_active=True;p.gate_value=initial
            value=initial
            for caller,kind,mask in [(0x602b77c6,'enable',1),(0x602b7b17,'enable',8),
                    (0x602b7b63,'enable',64),(0x602b7bce,'clear',8),(0x602b7c1d,'clear',64)]:
                s=ProbeState(caller,0,0,b'x',dict(d0=mask));s.regs['pc']=caller
                for _ in range(20):
                    r=s.run(p.hooks|{caller+7,0x602b7f6c,0x602b7fc6},limit=100)
                    self.assertEqual(r['status'],'breakpoint',r)
                    if s.regs['pc']==caller+7:break
                    if s.regs['pc'] in (0x602b7f6c,0x602b7fc6):s.return_from_model(0)
                    else:self.assertTrue(p.handle(s,p.hooks,None))
                self.assertEqual(s.regs['pc'],caller+7)
                self.assertIsNone(p.gate_request)
                value=(value|mask) if kind=='enable' else (value&~mask)
                self.assertEqual(p.gate_value,value)
                self.assertFalse(any(r.address in (0x9b000500,0x9b000504) for r in s.regions))

    def test_wrong_caller_or_mask_rejected(self):
        for caller,mask in [(0x602b77cd,8),(0x12345678,1)]:
            p=CameraGatesPeer('bulk','next',0);p.gates_active=True
            s=ProbeState(0x602a432a,0,0,b'x',dict(d0=mask,mdr=caller));s.regs['pc']=0x602a432a
            self.assertFalse(p.handle(s,p.hooks,None));self.assertEqual(s.steps,0)

    def test_dynamic_resource_hook_still_delegated(self):
        p=CameraGatesPeer('bulk','next',0)
        p.hooks.add(0x600224c2)
        s=ProbeState(0x600224c2,0,0,b'x',{});s.regs['pc']=0x600224c2
        with patch.object(CameraGatesPeer.__mro__[1],'handle',return_value=True) as parent:
            self.assertTrue(p.handle(s,p.hooks,None))
            parent.assert_called_once_with(s,p.hooks,None)
        self.assertEqual(s.steps,0)


if __name__=='__main__':unittest.main()
