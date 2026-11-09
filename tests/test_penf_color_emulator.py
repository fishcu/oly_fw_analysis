#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Cross-check actual MN103 color-builder execution with earlier DLL probes."""
import csv
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from penf_emulator import color_builder, boot_prefix, ROOT, ENGINE, INITIAL_SP

OBSERVATIONS = []


class ColorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = json.loads((ROOT / 'tests/fixtures/color-builder-reference.json').read_text())
        cls.saturation_reference = {(row['input_index'], row['input_value']): row
                                    for row in cls.reference['saturation']}
        cls.neutral = color_builder()
        assert cls.neutral['status'] == 'returned'
        cls.neutral_memory = bytes.fromhex(cls.neutral['memory'][0]['hex'])

    def check_return(self, result):
        self.assertEqual(result['status'], 'returned', result['fault'])
        self.assertEqual(result['registers']['sp'], INITIAL_SP)
        for reg, value in [('d2', 0x22334455), ('d3', 0x66778899),
                           ('a2', 0xaabbccdd), ('a3', 0x11223344)]:
            self.assertEqual(result['registers'][reg], value, reg)

    def test_full_workspace_parameter_grid(self):
        for case in self.reference['observations']:
            array, index, record, value = (case[k] for k in ('array', 'index', 'record', 'input'))
            with self.subTest(array=array, index=index, value=value):
                if array == 1:
                    inputs = [0]*12; inputs[index] = value
                    result = color_builder(inputs)
                    expected = int(self.saturation_reference[index, value]['camera_static_prediction'])
                    offset = 676 + 24*record + 20
                else:
                    expected = case['observed_i16']
                    result = color_builder(overrides=[(record, case['field_offset'], expected)])
                    offset = 676 + 24*record + (18 if array == 0 else 22)
                self.check_return(result)
                actual = bytes.fromhex(result['memory'][0]['hex'])
                observed = struct.unpack_from('<h', actual, offset)[0]
                self.assertEqual(observed, expected)
                restored = actual[:offset] + self.neutral_memory[offset:offset+2] + actual[offset+2:]
                self.assertEqual(restored, self.neutral_memory, 'Unexpected additional output change')
                OBSERVATIONS.append({'array': array, 'index': index, 'record': record, 'input': value,
                                     'mn103_observed': observed, 'workspace_observed': case['observed_i16'],
                                     'expected': expected, 'instructions': result['completed']})

    def test_combined_hsl_inputs(self):
        inputs = [7, -7, 5, -5, 3, -3, 1, -1, 0, 2, -2, 6]
        overrides = [(record, field, value) for record in range(12)
                     for field, value in [(12, (record-6)*1000), (16, (record-6)*25)]]
        result = color_builder(inputs, overrides=overrides)
        self.check_return(result)
        actual = bytes.fromhex(result['memory'][0]['hex'])
        for index, value in enumerate(inputs):
            record = (index % 2)*6 + index//2
            h = struct.unpack_from('<h', actual, 676+record*24+18)[0]
            s = struct.unpack_from('<h', actual, 676+record*24+20)[0]
            lightness = struct.unpack_from('<h', actual, 676+record*24+22)[0]
            self.assertEqual(h, (record-6)*1000)
            self.assertEqual(s, int(self.saturation_reference[index, value]['camera_static_prediction']))
            self.assertEqual(lightness, (record-6)*25)

    def test_entry_stops_at_first_controller_read(self):
        result = boot_prefix()
        self.assertEqual(result['status'], 'memory_fault')
        self.assertEqual(result['registers']['pc'], 0x600210ef)
        self.assertEqual(result['fault']['address'], 0x98e00060)
        self.assertEqual(result['fault']['access'], 'read')
        self.assertEqual(result['completed'], 6)
        self.assertEqual([row['pc'] for row in result['trace']],
                         [0x60021020, 0x60021024, 0x60021025, 0x60021026,
                          0x60021029, 0x600210e9, 0x600210ef])


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ColorTests))
    saturation = [o for o in OBSERVATIONS if o['array'] == 1]
    out = ROOT / 'analysis/emulation/color-validation.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({'passed': result.wasSuccessful(), 'tests_run': result.testsRun,
                               'parameter_cases': len(OBSERVATIONS),
                               'saturation_rounding_differences': sum(o['mn103_observed'] != o['workspace_observed'] for o in saturation),
                               'max_saturation_difference': max((abs(o['mn103_observed']-o['workspace_observed']) for o in saturation), default=0),
                               'engine_sha256': hashlib.sha256(ENGINE.read_bytes()).hexdigest(),
                               'scope': 'Actual camera coefficient-builder code under GNU CPU semantics; supplied tables/inputs; no pixels or camera access',
                               'observations': OBSERVATIONS}, indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
