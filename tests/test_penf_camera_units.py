# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native unit setup and exact clock-write instruction checks."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from penf_boot_camera_units import CameraUnitsPeer
from penf_probe import ProbeState


class CameraUnitTests(unittest.TestCase):
    def test_native_config_copy_and_callbacks(self):
        destinations=[(0x61869dbc,0x18c,84),(0x61869f48,48,40),
            (0x61870e8c,48,40),(0x61870f84,128,96),(0x618715dc,112,92)]
        expected=[[(8,2,0x6025da26),(9,2,0x6025db46),(10,2,0x6025dbf5)],
            [(17,2,0x6025e918)],[(15,2,0x60296b0f)],
            [(11,2,0x60298c19),(12,2,0x60298cc5),(13,2,0x60298d71),(14,2,0x60298ed8)],
            [(16,2,0x6029e1da)]]
        for i,(entry,source,caller,ret,ops) in enumerate(CameraUnitsPeer.units):
            p=CameraUnitsPeer('bulk','next',0);p.gates_active=True;p.unit_index=i
            s=ProbeState(entry,0x20 if i in (0,4) else 0,8 if i in (0,4) else 4,b'x',{})
            s.regs['pc']=caller-5
            dest,size,copied=destinations[i]
            s.ram('native_configuration',dest,b'\xa5'*size)
            data=bytes((i*31+n)&255 for n in range(copied))
            if source is None:
                source=s.regs['sp']+4
                s.write(source,data)
            else:s.ram('explicit_configuration_fixture',source,data)
            s.regs['a0']=source
            before=s.read(source,copied);registrations=[]
            for _ in range(30):
                r=s.run(p.hooks|{caller,0x60086c9c,0x4700159a},limit=2000)
                self.assertEqual(r['status'],'breakpoint',r)
                if s.regs['pc']==caller:break
                if s.regs['pc']==0x4700159a:
                    self.assertEqual((s.regs['a0'],s.regs['d0'],s.regs['d1']),(dest,0,size))
                    s.write(dest,bytes(size));s.return_from_model(0)
                elif s.regs['pc']==0x60086c9c:
                    registrations.append(tuple(s.regs[k] for k in ('d0','d1','a0')))
                    s.return_from_model(0)
                else:self.assertTrue(p.handle(s,p.hooks,None))
            self.assertEqual(s.regs['pc'],caller)
            self.assertEqual(s.read(dest,copied),before)
            self.assertEqual(registrations,expected[i])
            self.assertEqual(p.unit_index,i+1)
            self.assertIsNone(p.unit_stage)
            self.assertFalse(any(r.address in {a for _,a,_ in ops} for r in s.regions))

    def test_every_scoped_clock_write_is_native_store(self):
        for pc,value in CameraUnitsPeer.config_writes.items():
            p=CameraUnitsPeer('bulk','next',0);p.gates_active=True
            s=ProbeState(pc,0,0,b'x',dict(d0=value));s.regs['pc']=pc
            self.assertTrue(p.handle(s,p.hooks,None))
            self.assertEqual(s.regs['pc'],pc+6)
            self.assertEqual(s.steps,1)
            self.assertFalse(any(r.address==0x98800128 for r in s.regions))

    def test_unit_write_without_entry_rejected(self):
        p=CameraUnitsPeer('bulk','next',0);p.gates_active=True
        s=ProbeState(0x6025d9b9,0,0,b'x',dict(d0=0));s.regs['pc']=0x6025d9b9
        self.assertFalse(p.handle(s,p.hooks,None));self.assertEqual(s.steps,0)

    def test_existing_clock_sink_keeps_permissions(self):
        p=CameraUnitsPeer('bulk','next',0);p.gates_active=True
        s=ProbeState(0x602b7b20,0,0,b'x',dict(d0=4));s.regs['pc']=0x602b7b20
        s.register(0x98800128,'w',0)
        self.assertTrue(p.handle(s,p.hooks,None))
        r=next(r for r in s.regions if r.address==0x98800128)
        self.assertEqual(r.permissions,'w');self.assertEqual(int.from_bytes(r.data,'little'),4)


if __name__=='__main__':unittest.main()
