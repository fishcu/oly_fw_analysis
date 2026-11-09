# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Instruction-scoped strobe writes must not enable later MMIO access."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from penf_boot_strobe_sequence import StrobeSequencePeer
from penf_probe import ProbeState

class StrobeSequenceTests(unittest.TestCase):
    def test_native_writes_in_order_and_no_lingering_mapping(self):
        peer=StrobeSequencePeer('bulk','next',0)
        for pc,(address,value,ret) in peer.control_writes.items():
            s=ProbeState(pc,0,0,b'x',dict(d0=value,mdr=ret))
            s.regs['pc']=pc
            self.assertTrue(peer.handle(s,peer.hooks,None))
            self.assertEqual(s.steps,1)
            self.assertFalse(any(r.address==address for r in s.regions))
            with self.assertRaises(ValueError):s.read(address,4)
        self.assertEqual(peer.sequence_writes_seen,list(peer.control_writes))

    def test_unreviewed_value_order_core_and_caller_stop(self):
        for pc,cpu,value,ret in [(0x60147bdc,0,1,0x602daac1),
                (0x602ccf27,0,1,0x602daac8),(0x60147bdc,1,2,0x602daac1),
                (0x60147bdc,0,2,0)]:
            p=StrobeSequencePeer('bulk','next',0)
            s=ProbeState(pc,0,0,b'x',dict(d0=value,mdr=ret))
            s.regs['pc']=pc;s.cpu=cpu
            self.assertFalse(p.handle(s,p.hooks,None))
            self.assertEqual(s.steps,0)

if __name__=='__main__': unittest.main()
