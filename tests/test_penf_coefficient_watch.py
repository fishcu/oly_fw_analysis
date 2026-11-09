# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native CPU access controls for the exact Red lightness field."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from penf_coefficient_watch import RED_LIGHTNESS,guard_red_coefficient
from penf_probe import ProbeState
from penf_emulator import BASE,firmware


class RedWatchTests(unittest.TestCase):
    def fixture(self,value):
        s=ProbeState(0x602b9205,0,0,b'x',{})
        base=RED_LIGHTNESS-8
        s.ram('explicit_loaded_table_fixture',base,firmware()[base-BASE:base-BASE+24])
        before=s.read(base,24)
        guard_red_coefficient(s,value)
        self.assertEqual(s.read(base,8),before[:8])
        self.assertEqual(s.read(RED_LIGHTNESS+2,14),before[10:])
        return s

    def test_either_alias_and_overlapping_word_read_stop(self):
        for value in (0,250):
            for alias in (0,0x40000000):
                for offset in (-2,0):
                    with self.subTest(value=value,alias=alias,offset=offset):
                        s=self.fixture(value)
                        self.assertEqual(s.read(RED_LIGHTNESS+alias,2),value.to_bytes(2,'little'))
                        s.regs.update(pc=0x602b9205,a0=RED_LIGHTNESS+alias+offset)
                        result=s.run(set(),limit=1)
                        self.assertEqual(result['status'],'memory_fault')
                        self.assertEqual(result['fault']['access'],'read')

    def test_neighbor_read_and_alias_writes_survive(self):
        s=self.fixture(250)
        s.regs.update(pc=0x602b9205,a0=RED_LIGHTNESS-8)
        self.assertEqual(s.run(set(),limit=1)['status'],'instruction_limit')
        s.write(RED_LIGHTNESS+0x40000000,b'\x12\x34')
        self.assertEqual(s.read(RED_LIGHTNESS,2),b'\x12\x34')

    def test_flat_image_or_changed_original_rejected(self):
        s=ProbeState(0x602b9205,0,0,b'x',{})
        with self.assertRaises(ValueError):guard_red_coefficient(s)
        s.ram('changed_fixture',RED_LIGHTNESS,b'\x01\0')
        with self.assertRaises(ValueError):guard_red_coefficient(s)


if __name__=='__main__':unittest.main()
