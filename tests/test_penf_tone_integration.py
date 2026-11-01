import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))

from penf_tone_integration_probe import (JOB, build_adapter, check_case, identity_lut,
                                         packed, run_builder, signal_case, upload_result)


class NativeToneIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='penf-tone-integration-')
        cls.adapter = build_adapter(Path(cls.temporary.name) / 'assembly')

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_missing_upper_crossing_is_rejected(self):
        case = signal_case(self.adapter, tuple([0] * 256), (0, 0, 0, 0, 0))
        self.assertIsNone(case['bounds'])

    def test_upper_crossing_at_last_sample_is_valid(self):
        curve = tuple([0] * 255 + [1023])
        case = signal_case(self.adapter, curve, (0, 0, 0, 0, 0))
        self.assertEqual(case['bounds'], (250, 255))

    def test_endpoint_only_ordinary_native_route(self):
        case = check_case(self.adapter, identity_lut(), (0, 0, 0, 0, 0), 70, 950, outer=True)
        self.assertEqual(case['endpoints'], [70, 950])

    def test_inner_height_clamps_endpoint_independently(self):
        case = check_case(self.adapter, identity_lut(), (0, 0, 4, -2, -3), 1023, 950)
        self.assertLess(case['endpoints'][0], 1023)
        self.assertEqual(case['endpoints'][1], 950)

    def test_unsupported_source_retains_native_pointer(self):
        curve = tuple([700] * 256)
        stock = run_builder(self.adapter, curve, (0, 0, 0, 0, 0), native=True)
        actual = run_builder(self.adapter, curve, (0, 0, 0, 0, 0), endpoint_word=packed(70, 950))
        self.assertEqual(actual['output'], stock['output'])
        self.assertEqual(actual['d0'], stock['d0'])

    def test_ordinary_bypass_retains_native_output(self):
        options = dict(outer=True, bypass=True, endpoint_word=packed(70, 950))
        stock = run_builder(self.adapter, identity_lut(), (0, 0, 4, -2, -3), native=True, **options)
        actual = run_builder(self.adapter, identity_lut(), (0, 0, 4, -2, -3), **options)
        self.assertEqual(actual['output'], stock['output'])
        self.assertEqual(actual['context'], stock['context'])

    def test_wrong_parent_retains_native_output(self):
        options = dict(parent=JOB + 4, endpoint_word=packed(70, 950))
        stock = run_builder(self.adapter, identity_lut(), (0, 0, 0, 0, 0), native=True, **options)
        actual = run_builder(self.adapter, identity_lut(), (0, 0, 0, 0, 0), **options)
        self.assertEqual(actual['output'], stock['output'])

    def test_warm_cache_uploads_endpoint_curve(self):
        actual = run_builder(self.adapter, identity_lut(), (0, 0, 4, -2, -3),
                             endpoint_word=packed(50, 950), outer=True)
        uploaded = upload_result(actual, 1)
        self.assertEqual(uploaded['bank'], 1)
        self.assertEqual(uploaded['dirty'], 0)
        self.assertEqual(uploaded['endpoints'], list(actual['lut'][::255]))


if __name__ == '__main__':
    unittest.main()
