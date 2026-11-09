#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native FIFO operations and strict boundaries of the optional serial model."""
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from penf_boot_emulator import BootState
from penf_alex_model import AlexPeer,STARTUP


class AlexModelTests(unittest.TestCase):
    def test_actual_tx_store_and_rx_load_use_fifo_without_writing_completion(self):
        state=BootState()
        peer=AlexPeer('startup')
        peer.command=STARTUP[0]
        state.register(0x98300018,'w')
        state.register(0x98300008,'w')
        state.ram('test_destination',0x18040000,bytes(4),aliases=False)
        state.ram('test_rx_pointer',0x18040010,struct.pack('<I',0x18040000),aliases=False)
        state.ram('test_completion',0x61c389e4,bytes(4))
        state.regs.update(pc=0x6008b1f5,a2=0x98300018,d2=0xf5)
        self.assertTrue(peer.handle(state,peer.hooks,None))
        self.assertEqual(state.read(0x98300018,4),struct.pack('<I',0xf5))
        state.regs.update(pc=0x6008b547,a3=0x98300008,a1=0x18040010)
        self.assertTrue(peer.handle(state,peer.hooks,None))
        self.assertEqual(state.regs['d0'],0x20)
        self.assertEqual(state.read(0x18040000,1),b'\0')
        self.assertEqual(state.regs['pc'],0x6008b548)
        # The next native instructions copy the received byte to RAM.
        result=state.run(set(),limit=2)
        self.assertEqual(result['completed'],2)
        self.assertEqual(state.read(0x18040000,1),b'\x20')
        self.assertEqual(state.read(0xa1c389e4,1),b'\0')
        self.assertEqual(peer.fifo,[])
        self.assertEqual(next(r for r in state.regions if r.address==0x98300008).permissions,'w')

    def test_corrupt_reply_changes_only_peer_input(self):
        state=BootState()
        peer=AlexPeer('bad-first-reply')
        peer.command=STARTUP[0]
        state.register(0x98300018,'w')
        state.regs.update(pc=0x6008b1f5,a2=0x98300018,d2=0xf5)
        self.assertTrue(peer.handle(state,peer.hooks,None))
        self.assertEqual(peer.fifo,[0x21])
        self.assertEqual(peer.command[1],bytes.fromhex('20f5000000'))

    def test_other_channel_remains_unknown(self):
        state=BootState()
        peer=AlexPeer('startup')
        peer.command=STARTUP[0]
        state.regs.update(pc=0x6008b1f5,a2=0x98200018,d2=0xf5)
        self.assertFalse(peer.handle(state,peer.hooks,None))
        self.assertEqual(state.steps,0)
        self.assertEqual(peer.fifo,[])
        self.assertEqual(state.events[-1]['kind'],'unresolved')


if __name__=='__main__':unittest.main(verbosity=2)
