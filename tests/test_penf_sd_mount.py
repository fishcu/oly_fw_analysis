# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Request-buffer lifetime boundaries in the SD mount continuation."""
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from penf_boot_sd_mount import SDMountPeer
from penf_probe import ProbeState,CALLER


class TransportLifetimeTests(unittest.TestCase):
    def returned_free(self,allocated=False):
        address=0xa1222380;slot=5
        s=ProbeState(0x6002352a,0,4,b'x',{})
        s.run({0x6002352a},limit=1)
        s.ram('sd_transport_packet_5',address,b'\x91'*16)
        s.ram('explicit_pool_bitmap',0xa1c5569c,struct.pack('<I',(1<<slot) if allocated else 0))
        p=SDMountPeer('bulk','next',0)
        p.transport_buffers=[address]
        p.packet_free=(address,s.regs['sp'],0xa1c5569c,1<<slot,slot)
        return s,p,address

    def test_released_packet_denies_native_access_through_both_aliases(self):
        for delta in (0,-0x40000000):
            with self.subTest(delta=delta):
                s,p,address=self.returned_free()
                self.assertTrue(p.handle(s,p.hooks,None))
                self.assertEqual(s.regs['pc'],CALLER+7)
                self.assertEqual(p.transport_buffers,[])
                s.regs.update(pc=0x602b9205,a0=address+delta)
                r=s.run(set(),limit=1)
                self.assertEqual(r['status'],'memory_fault')
                self.assertEqual(r['fault']['access'],'read')

    def test_clear_bit_and_return_stack_required(self):
        for wrong_sp in (False,True):
            s,p,address=self.returned_free(allocated=not wrong_sp)
            if wrong_sp:s.regs['sp']-=4
            self.assertFalse(p.handle(s,p.hooks,None))
            self.assertEqual(s.read(address,16),b'\x91'*16)


if __name__=='__main__':unittest.main()
