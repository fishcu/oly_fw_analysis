from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from penf_emulator import ENGINE, IMAGE
from penf_tone_probe import NativeToneParameters, baseline_report


class NativeToneParameterTests(unittest.TestCase):
    def test_optimized_cli_and_imports_fail_before_audit_claims(self):
        root = Path(__file__).resolve().parents[1]
        modules = {
            'penf_tone_probe': ('native_tone, native_gate', []),
            'penf_tone_endpoints': ('native_endpoints',
                ['--black', '50', '--white', '950', '--shadow-index', '64', '--highlight-index', '192']),
        }
        with tempfile.TemporaryDirectory(prefix='penf-tone-optimized-') as folder:
            for module, (helpers, arguments) in modules.items():
                out = Path(folder) / module
                commands = {
                    'cli': [sys.executable, '-O', str(root / 'tools' / (module + '.py')),
                            '--out', str(out), *arguments],
                    'import': [sys.executable, '-O', '-c',
                        f'import sys; sys.path.insert(0, {str(root / "tools")!r}); '
                        f'from {module} import {helpers}; print("audit_claim_reached")'],
                }
                for kind, command in commands.items():
                    with self.subTest(module=module, kind=kind):
                        result = subprocess.run(command, capture_output=True, text=True,
                                                timeout=30)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn('optimized Python execution is unsupported', result.stderr)
                        self.assertEqual(result.stdout, '')
                        self.assertFalse(out.exists())

    def test_exact_signed16_input_shape(self):
        self.assertEqual(NativeToneParameters((-32768, -7, 0, 7, 32767)).pack(),
                         bytes.fromhex('0080f9ff00000700ff7f'))
        for slots in ((0,) * 4, (0,) * 6, (0, 0, 0, 0, 32768),
                      (0, 0, 0, 0, -32769), (0, 0, 0, 0, True), [0] * 5):
            with self.subTest(slots=slots), self.assertRaises(ValueError):
                NativeToneParameters(slots)


@unittest.skipUnless(IMAGE.is_file() and ENGINE.is_file(),
                     'Exact PEN-F 3101 firmware and built GNU strict engine required')
class NativeToneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = baseline_report()

    def test_known_identity_and_forced_neutral_outputs(self):
        self.assertEqual(self.report['identity_sha256'],
                         '8ef45d7de8746b48e7b04fe690d045885cde1c1e62d03fefd3304f50281a538a')
        neutral = self.report['cases'][0]
        self.assertFalse(neutral['gate_active'])
        self.assertEqual(neutral['stock_lut'], self.report['identity_lut'])
        self.assertEqual(neutral['coefficients_hex'], '00' * 16)
        self.assertEqual(neutral['lut_sha256'],
                         '1d3a4cf6980ceffd36027a9b8feef1c4401a97bcf4f75958de6ef3b1f5860e87')
        self.assertEqual(self.report['forced_neutral_overlay_changes'], [
            dict(index=i, base=x, forced_overlay=y) for i, x, y in (
                (43, 173, 172), (44, 177, 176), (45, 181, 180),
                (126, 505, 506), (127, 509, 510),
                (213, 855, 854), (214, 859, 858), (215, 863, 862))])

    def test_each_opaque_slot_changes_interior_but_keeps_endpoints(self):
        cases = self.report['cases']
        self.assertEqual(len(cases), 11)
        for slot in range(5):
            for index, value in enumerate((-7, 7)):
                case = cases[1 + slot * 2 + index]
                expected = [0] * 5
                expected[slot] = value
                with self.subTest(slot=slot, value=value):
                    self.assertEqual(case['slots'], expected)
                    self.assertTrue(case['gate_active'])
                    self.assertEqual(len(case['lut']), 256)
                    self.assertEqual((case['lut'][0], case['lut'][-1]), (0, 1023))
                    self.assertNotEqual(case['lut_sha256'], cases[0]['lut_sha256'])
                    self.assertTrue(all(0 <= x <= 1023 for x in case['lut']))

    def test_mixed_last_three_slot_extremes_keep_endpoints(self):
        mixed = self.report['mixed_cases']
        self.assertEqual(len(mixed), 27)
        self.assertEqual(len({tuple(case['slots']) for case in mixed}), 27)
        for case in mixed:
            self.assertEqual(case['slots'][:2], [0, 0])
            self.assertEqual((case['lut'][0], case['lut'][-1]), (0, 1023))
            self.assertTrue(all(0 <= x <= 1023 for x in case['lut']))

    def test_native_boundaries_remain_intact_without_models(self):
        for case in self.report['cases'] + self.report['mixed_cases']:
            for stage in [case['gate_stage'], *case['stages']]:
                with self.subTest(slots=case['slots'], entry=stage['entry']):
                    for key in ('returned', 'stack_restored', 'preserved_registers',
                                'stack_canaries', 'buffer_canaries', 'inputs_immutable'):
                        self.assertTrue(stage[key], key)
                    self.assertEqual(stage['modeled_functions'], [])
        self.assertEqual(self.report['firmware_sha256'],
                         'a2eb1d1f1afe47cce148e9aae0a04dfb82547d9de9437d342e012341140913f4')
        self.assertEqual(len(self.report['engine_sha256']), 64)


if __name__ == '__main__':
    unittest.main(verbosity=2)
