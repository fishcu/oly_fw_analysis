# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native settings-bank copies: exact extents, direction and caller bounds."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_probe import ProbeState, CALLER
from penf_emulator import Region


class ParameterBankTests(unittest.TestCase):
    bank_base = 0x61b7bdc8
    active = 0x61b938b8
    words = 2548
    size = words*4
    count = 9

    def fixture(self, target, bank):
        state = ProbeState(target, 0xc0, 12, bytes(16), dict(d0=bank))
        state.register(0x8050, 'r', 0)
        state.ram('bank_pointer', 0x61896ed4, struct.pack('<I', self.bank_base))
        state.ram('active_pointer', 0x61896ed8, struct.pack('<I', self.active))
        banks = b''.join(struct.pack('<I', 0x80000000 | (b << 16) | i)
                         for b in range(self.count) for i in range(self.words))
        active = b''.join(struct.pack('<I', 0xfedc0000 | i) for i in range(self.words))
        state.ram('bank_storage', self.bank_base, banks)
        state.ram('active_storage', self.active, active)
        for index, address in enumerate((self.bank_base-4, self.bank_base+len(banks),
                                         self.active-4, self.active+self.size)):
            state.regions.append(Region(f'read_only_guard_{index}', address, b'\x3c'*4, 'r'))
        return state, banks, active

    def test_native_copy_both_directions_and_preserves_other_banks(self):
        for target in (0x602f063e, 0x602f067a):
            for bank in (0, 5, 8):
                with self.subTest(target=hex(target), bank=bank):
                    state, banks, active = self.fixture(target, bank)
                    edges = {a: state.read(a, 4) for a in (
                        self.bank_base-4, self.bank_base+len(banks),
                        self.active-4, self.active+self.size)}
                    result = state.run({CALLER+7}, limit=250000)
                    self.assertEqual(result['status'], 'breakpoint')
                    offset = bank*self.size
                    if target == 0x602f063e:
                        expected_banks = banks
                        expected_active = banks[offset:offset+self.size]
                    else:
                        expected_banks = banks[:offset]+active+banks[offset+self.size:]
                        expected_active = active
                    self.assertEqual(state.read(self.bank_base, len(banks)), expected_banks)
                    self.assertEqual(state.read(self.active, self.size), expected_active)
                    for address, value in edges.items():
                        self.assertEqual(state.read(address, 4), value)
                    self.assertEqual(state.regs['sp'], 0x18018000)

    def test_store_helper_itself_does_not_enforce_nine_bank_bound(self):
        state, banks, active = self.fixture(0x602f067a, 9)
        result = state.run({CALLER+7}, limit=1000)
        self.assertEqual(result['status'], 'memory_fault')
        self.assertEqual(result['fault']['address'], self.bank_base+len(banks))
        self.assertEqual(state.read(self.bank_base, len(banks)), banks)
        self.assertEqual(state.read(self.active, self.size), active)


if __name__ == '__main__':
    unittest.main()
