#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Documented MAC transfer semantics and the camera's context self-test.

Reference: Panasonic MN103001G/F01K manual pp. 3-6, 3-8, 3-9.
Undefined N/Z and hardware flag-pipeline timing are not assertions here.
"""
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from penf_emulator import Region, execute, call_function, image_region


class MacContextTests(unittest.TestCase):
    def test_putcx_all_register_pairs(self):
        for m in range(4):
            for n in range(4):
                for overflow in (0, 8):
                    regs = {f'd{i}': 0x12345678*(i+1) for i in range(4)}
                    regs.update(pc=0x10000, psw=0xf07 | overflow)
                    r = execute([Region('code',0x10000,bytes((0xf5,0x10+4*m+n)),'rx')], regs, 0x10002)
                    self.assertEqual(r['status'], 'returned')
                    self.assertEqual(r['registers']['extra15'], regs[f'd{m}'])
                    self.assertEqual(r['registers']['extra16'], regs[f'd{n}'])
                    self.assertEqual(r['registers']['extra17'], bool(overflow))
                    self.assertEqual(r['registers']['psw'], regs['psw'])

    def test_getcx_data_and_defined_flags(self):
        for high in (True, False):
            for m in range(4):  # Source selector is ignored according to manual.
                for n in range(4):
                    for value in (0, 0x12345678, 0x80000000, 0xffffffff):
                        for overflow in (0, 1):
                            regs = {'pc':0x10000, 'psw':0xf0f,
                                    'extra15': value if high else 0x98765432,
                                    'extra16': value if not high else 0x98765432,
                                    'extra17': overflow}
                            code=bytes((0xf6,(0xc0 if high else 0xd0)+4*m+n))
                            r=execute([Region('code',0x10000,code,'rx')],regs,0x10002)
                            self.assertEqual(r['status'],'returned')
                            self.assertEqual(r['registers'][f'd{n}'],value)
                            self.assertEqual(r['registers']['psw'] & 0xc, overflow*8)
                            self.assertEqual(r['registers']['psw'] & ~0xf, 0xf00)

    def test_firmware_kernel_context_selftest(self):
        for overflow in (0,1):
            r=call_function(0x6003383b,0x60033920,0,0,
                [image_region('context_transfer',0x600300f7,0x60030127)],
                {'psw':0x700|overflow*8, 'extra15':0x12345678,
                 'extra16':0x9abcdef0, 'extra17':overflow, 'mdrq':0xcafe1234}, limit=1000)
            self.assertEqual(r['status'],'returned',r)
            for name,value in (('extra15',0x12345678),('extra16',0x9abcdef0),
                               ('extra17',overflow),('mdrq',0xcafe1234)):
                self.assertEqual(r['registers'][name],value)
            self.assertEqual(r['registers']['psw'] & 0xf00,0x700)

    def test_other_unknown_extension_still_stops(self):
        r=execute([Region('code',0x10000,bytes.fromhex('f520'),'rx')],{'pc':0x10000},0x10002)
        self.assertEqual(r['status'],'instruction_fault')
        self.assertEqual(r['completed'],0)

if __name__ == '__main__':
    unittest.main(verbosity=2)
