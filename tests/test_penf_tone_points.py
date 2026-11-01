import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from penf_tone_points import FivePoints,decode,resolve,quantize
from penf_tone_points_probe import build_core,core_cases,migration_cases


class FivePointStateTests(unittest.TestCase):
    def test_neutral_is_exact_identity_at_every_ten_bit_input(self):
        self.assertEqual(FivePoints().apply(tuple(range(1024))),tuple(range(1024)))

    def test_quantization_uses_nearest_with_lower_ties(self):
        self.assertEqual([quantize(x) for x in (8,9,1000,1007,1008,1023)], [0,16,992,992,1023,1023])

    def test_invalid_state_is_not_silently_projected_during_decode(self):
        self.assertIsNone(decode(0xbfffffff))
        self.assertIsNone(decode(0xb000003f))
        self.assertEqual(resolve(0xa5d00000,(8,0,0)),FivePoints())

    def test_native_core_matches_all_samples_and_selected_axis_edits(self):
        with tempfile.TemporaryDirectory(prefix='penf-five-points-') as folder:
            core=build_core(Path(folder)/'core')
            self.assertEqual(len(core_cases(core)),48)
            self.assertEqual(len(migration_cases(core)),44)


if __name__=='__main__':
    unittest.main()
