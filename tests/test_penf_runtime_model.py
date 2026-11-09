# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Check interrupt guardrails and frame compatibility with the native RTI."""
import struct
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from penf_boot_emulator import BootState
from penf_runtime_model import RuntimeInterrupts
from penf_emulator import execute, Region


class RuntimeTests(unittest.TestCase):
    def idle(self):
        s=BootState()
        s.regs.update(pc=0x6003718b,psw=0xf0a,sp=0x61821df0)
        s.write(0x8014,struct.pack('<H',0x68))
        s.write(0x801c,struct.pack('<I',0x60030070))
        s.write(0x99200000+58*4,struct.pack('<I',0x20))
        return s

    def test_native_rti_accepts_modeled_exception_frame(self):
        s=self.idle();before=dict(s.regs)
        irq=RuntimeInterrupts(1);irq.inject(s,58)
        self.assertEqual(s.regs['pc'],0x60030068)
        self.assertEqual(s.regs['psw'],0x50a)
        self.assertEqual(s.read(before['sp']-8,2),struct.pack('<H',before['psw']))
        self.assertEqual(s.read(before['sp']-4,4),struct.pack('<I',before['pc']))
        self.assertEqual(s.read(0x99200214,4),struct.pack('<I',59*4))
        s.regs['pc']=0x6003952d  # Real firmware RTI, isolate frame semantics.
        r=execute(s.regions,s.regs,before['pc'],limit=2)
        self.assertEqual(r['status'],'returned')
        for key in ('sp','psw','pc'):self.assertEqual(r['registers'][key],before[key])

    def test_masked_or_nonidle_irq_is_rejected_before_mutation(self):
        for key,value in [('pc',0x60021020),('psw',0x700),('psw',0xd00)]:
            s=self.idle();s.regs[key]=value;before=dict(s.regs)
            with self.assertRaises(ValueError): RuntimeInterrupts(1).inject(s,58)
            self.assertEqual(s.regs,before)

    def test_context_word_is_per_core_and_transfer_is_explicit(self):
        s=self.idle();irq=RuntimeInterrupts(1)
        for cpu,value in ((0,0x12345678),(1,0x87654321)):
            if s.cpu!=cpu:s.switch_core(cpu)
            s.regs.update(pc=0x60030120,d0=value,psw=0x50a)
            irq.handle(s,irq.hooks)
        s.switch_core(0);s.regs.update(pc=0x60030106,d0=0)
        irq.handle(s,irq.hooks)
        self.assertEqual(s.regs['d0'],0x12345678)
        self.assertEqual(s.regs['psw'],0x50a)
        self.assertEqual(s.steps,0)  # Modeled instructions are not native counts.
        self.assertEqual(s.events[-1]['kind'],'model')


if __name__=='__main__':unittest.main(verbosity=2)
