# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Execute the finite per-bank settings filter reached after nine-bank setup."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_probe import ProbeState, CALLER
from penf_emulator import BASE, firmware


class ParameterFilterTests(unittest.TestCase):
    def test_native_filter_finishes_for_both_bank_classes(self):
        blob = firmware()
        def native_bytes(address, size):
            return blob[address-BASE:address-BASE+size]

        # Select the first native descriptor (mode 3, secondary selector 0).
        pointer = int.from_bytes(native_bytes(0x603c8920, 4), 'little')
        count = int.from_bytes(native_bytes(0x603c8924, 2), 'little')
        rows = list(struct.iter_unpack('<HBB', native_bytes(pointer, count*4)))
        first_part = {}
        for index, part, _ in rows:
            first_part.setdefault(index, part)
        for bank, ids_address, length in ((1, 0x603cb3dc, 856), (5, 0x603cba8c, 855)):
            with self.subTest(bank=bank):
                state = ProbeState(0x602c5f5d, 0xf0, 44, bytes(16), dict(d0=bank, d1=3, a0=0))
                state.register(0x8050, 'r', 0)
                state.ram('active_pointer', 0x61896ed8, struct.pack('<I', 0x61b938b8))
                state.ram('source_pointer', 0x61896edc, struct.pack('<I', 0x61b924cc))
                original = [0x77777777]*2548
                source = [0x90000000 | i for i in range(1274)]
                packed_source = struct.pack('<1274I', *source)
                state.ram('active_array', 0x61b938b8, struct.pack('<2548I', *original))
                state.ram('source_array', 0x61b924cc, packed_source)
                ids = struct.unpack('<'+'H'*length, native_bytes(ids_address, length*2))
                expected = original.copy()
                for index in ids:
                    expected[first_part.get(index, 0)*1274+index] = source[index]
                result = state.run({CALLER+7}, limit=10000000)
                self.assertEqual(result['status'], 'breakpoint')
                # Exceeding the old budget is expected, not nontermination.
                self.assertGreater(result['completed'], 2000000)
                self.assertEqual(state.read(0x61b938b8, 2548*4), struct.pack('<2548I', *expected))
                self.assertEqual(state.read(0x61b924cc, 1274*4), packed_source)
                self.assertEqual(state.regs['sp'], 0x18018000)


if __name__ == '__main__':
    unittest.main()
