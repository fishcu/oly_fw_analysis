# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native camera configuration copies callbacks and registers scoped IRQs."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from penf_boot_camera_registers import CameraRegistersPeer
from penf_probe import ProbeState


class CameraRegisterTests(unittest.TestCase):
    def test_native_config_copy_and_interrupt_registration(self):
        p=CameraRegistersPeer('bulk','next',0);p.enable_stage=4
        s=ProbeState(0x602a448d,0x20,8,b'x',dict(a0=0x6036b4e0))
        s.regs['pc']=0x602a31f1
        s.ram('controller_configuration',0x61883f5c,b'\xa5'*0x138)
        registrations=[]
        stops=p.hooks|{0x602a31f6,0x60086c9c}
        for _ in range(30):
            r=s.run(stops,limit=1000)
            self.assertEqual(r['status'],'breakpoint',r)
            if s.regs['pc']==0x602a31f6:break
            if s.regs['pc']==0x60086c9c:
                registrations.append((s.regs['d0'],s.regs['d1'],s.regs['a0']))
                s.return_from_model(0)
            else:self.assertTrue(p.handle(s,p.hooks,None))
        self.assertEqual(s.regs['pc'],0x602a31f6)
        self.assertEqual(registrations,[(4,2,0x602a6243),(5,2,0x602a6277),(6,2,0x602a62ab)])
        self.assertEqual(s.read(0x61883f60,69*4),s.read(0x6036b4e0,69*4))
        self.assertEqual(p.register_stage,15)
        self.assertTrue(p.register_initializer_returned)
        for _,a,_,_ in p.operations[:15]:
            with self.assertRaises(ValueError):s.read(a,4)

    def test_unreviewed_value_or_sequence_rejected(self):
        for active,stage,value in [(False,2,0x781f80),(True,0,0x781f80),(True,2,1)]:
            p=CameraRegistersPeer('bulk','next',0)
            p.register_active=active;p.register_stage=stage
            s=ProbeState(0x602a4501,0,0,b'x',dict(d0=value))
            s.regs['pc']=0x602a4501
            self.assertFalse(p.handle(s,p.hooks,None))
            self.assertEqual(s.steps,0)

    def test_existing_clock_write_sink_remains_unreadable(self):
        p=CameraRegistersPeer('bulk','next',0)
        p.register_active=True;p.register_stage=18;p.register_initializer_returned=True
        s=ProbeState(0x602b7848,0,0,b'x',dict(d0=0x10000000))
        s.regs['pc']=0x602b7848
        s.register(0x988000e4,'w',0)
        self.assertTrue(p.handle(s,p.hooks,None))
        region=next(r for r in s.regions if r.address==0x988000e4)
        self.assertEqual(region.permissions,'w')
        self.assertEqual(int.from_bytes(region.data,'little'),0x10000000)
        self.assertEqual(p.register_stage,19)


if __name__=='__main__':unittest.main()
