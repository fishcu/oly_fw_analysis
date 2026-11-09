#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native bulk setup/cleanup and strict peer boundaries; no device access."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_alex_bulk_model import AlexBulkPeer, BLOCKS
from penf_emulator import BASE, Region, firmware
from penf_probe import ProbeState, CALLER, RESULT


class AlexBulkTests(unittest.TestCase):
    def bulk_state(self, stage, low_memory_word=0):
        address, size = BLOCKS[stage]
        s = ProbeState(0x6007cf6e, 0xf0, 48, bytes(16),
                       dict(d0=size, a0=address+0x40000000))
        s.regions.append(Region('bulk_source_alias', address+0x40000000,
                                firmware()[address-BASE:address-BASE+size], 'r'))
        s.register(0x9b80128c, 'w')
        s.ram('board_revision', 0x8ff00188, b'\0', aliases=False)
        pin_address = struct.unpack_from('<I', firmware(), 0x60025cec-BASE+97*4)[0]
        s.register(pin_address, 'w')
        peer = AlexBulkPeer(low_memory_word=low_memory_word)
        peer.stage = stage
        return s, peer

    def test_native_three_block_descriptors_and_cleanup(self):
        for stage, checksum in enumerate((0xc15f2584, 0x84af24b0, 0xa4c3f383)):
            with self.subTest(stage=stage):
                s, peer = self.bulk_state(stage)
                # Isolated fixture: clocks and pin configuration are boundaries.
                # The separate main-entry run executes these native services.
                services = {0x6008ee45, 0x6007d1b0, 0x60083f42}
                hooks = peer.hooks | services | {CALLER+7}
                for _ in range(100):
                    result = s.run(hooks, limit=10000)
                    self.assertEqual(result['status'], 'breakpoint', result.get('fault'))
                    pc = s.regs['pc']
                    if pc == CALLER+7:
                        break
                    if pc in services:
                        s.return_from_model(0)
                    else:
                        self.assertTrue(peer.handle(s, hooks, None))
                self.assertEqual(s.regs['pc'], CALLER+7)
                self.assertEqual(s.regs['sp'], 0x18018000)
                self.assertEqual(len(peer.uploads), 1)
                upload = peer.uploads[0]
                self.assertEqual(upload['sum_be32'], checksum)
                self.assertEqual(upload['bytes'], BLOCKS[stage][1])
                self.assertTrue(upload['completed'])
                self.assertFalse(any(r.address < 8 for r in s.regions))

    def test_unreviewed_source_is_rejected(self):
        s, peer = self.bulk_state(0)
        s.regs.update(pc=0x6007cf6e, a0=0xa0042c04)
        with self.assertRaises(AssertionError):
            peer.handle(s, peer.hooks, None)
        self.assertEqual(peer.uploads, [])

    def test_low_memory_descriptor_is_a_real_native_dereference(self):
        pin_address = struct.unpack_from('<I', firmware(), 0x60025cec-BASE+97*4)[0]
        for word in (None, 0, 1, 0xffffffff):
            with self.subTest(word=word):
                s = ProbeState(0x60083f5d, 0, 4, bytes(16), dict(d0=97, a0=0))
                s.ram('board_revision', 0x8ff00188, b'\0', aliases=False)
                s.register(pin_address, 'w')
                if word is not None:
                    s.ram('explicit_low_memory', 0, struct.pack('<II', word, 0), aliases=False)
                result = s.run({CALLER+7}, limit=1000)
                if word is None:
                    self.assertEqual(result['status'], 'memory_fault')
                    self.assertEqual(result['fault']['address'], 0)
                    self.assertEqual(result['fault']['access'], 'read')
                else:
                    self.assertEqual(s.regs['pc'], CALLER+7)
                    self.assertEqual(s.read(0, 4), struct.pack('<I', word & 1))
                    self.assertEqual(s.read(pin_address, 4), struct.pack('<I', word & 1))

    def test_checksum_response_requires_a_completed_upload(self):
        s, peer = self.bulk_state(0)
        peer.phase = 3
        peer.uploads = [dict(stage=0, completed=False, sum_be32=0xc15f2584)]
        with self.assertRaises(AssertionError):
            peer.command_reply(s, bytes.fromhex('66000000a0'))

    def test_nonzero_low_memory_callback_is_an_actual_indirect_call(self):
        pin_address = struct.unpack_from('<I', firmware(), 0x60025cec-BASE+97*4)[0]
        callback = 0x18040000
        marker = 0x13579bdf
        # Synthetic callback: mov marker,d0; mov d0,(a0); rets.
        code = bytes.fromhex('fccc')+struct.pack('<I', marker)+bytes.fromhex('60f0fc')
        for argument_mapped in (False, True):
            with self.subTest(argument_mapped=argument_mapped):
                s = ProbeState(0x60083f5d, 0, 4, bytes(16), dict(d0=97, a0=0))
                s.ram('board_revision', 0x8ff00188, b'\0', aliases=False)
                s.register(pin_address, 'w')
                low = struct.pack('<II', 0xffffffff, callback)
                if argument_mapped:
                    low += struct.pack('<I', RESULT)
                s.ram('explicit_low_memory', 0, low, aliases=False)
                s.regions.append(Region('synthetic_callback', callback, code, 'rx'))
                result = s.run({CALLER+7}, limit=1000)
                self.assertEqual(s.read(0, 4), struct.pack('<I', 1))
                self.assertEqual(s.read(pin_address, 4), struct.pack('<I', 1))
                self.assertEqual(s.read(4, 4), struct.pack('<I', callback))
                if argument_mapped:
                    self.assertEqual(result['status'], 'breakpoint')
                    self.assertEqual(s.regs['pc'], CALLER+7)
                    self.assertEqual(s.regs['sp'], 0x18018000)
                    self.assertEqual(s.read(RESULT, 4), struct.pack('<I', marker))
                    self.assertEqual(s.read(8, 4), struct.pack('<I', RESULT))
                else:
                    self.assertEqual(result['status'], 'memory_fault')
                    self.assertEqual(result['fault']['pc'], 0x600846a6)
                    self.assertEqual(result['fault']['address'], 8)
                    self.assertEqual(result['fault']['access'], 'read')
                    self.assertEqual(s.read(RESULT, 4), bytes(4))

    def test_native_poll_stays_waiting_without_completion(self):
        s, peer = self.bulk_state(0)
        s.register(0x9bf00044, 'w')
        # Enter at SETLB so the native loop target is established normally.
        s.regs.update(pc=0x6007d119, a2=0x9bf00044)
        result = s.run({0x6007d11a}, limit=5)
        self.assertEqual(result['status'], 'breakpoint')
        self.assertTrue(peer.observed_read(s, peer.hooks, 0x9bf00044, 0))
        result = s.run({0x6007d11a, 0x6007d121}, limit=10)
        self.assertEqual(s.regs['pc'], 0x6007d11a)
        self.assertEqual(result['status'], 'breakpoint')
        self.assertEqual(next(r for r in s.regions if r.address == 0x9bf00044).permissions, 'w')
        self.assertEqual(peer.uploads, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
