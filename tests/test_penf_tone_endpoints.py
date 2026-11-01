from itertools import product
from pathlib import Path
import random
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from penf_emulator import ENGINE, IMAGE
from penf_tone_endpoints import (TOOLCHAIN, ToneEndpoints, build_kernel,
                                 endpoint_oracle, native_endpoints)
from penf_tone_probe import NativeToneParameters, identity_lut, native_tone


class EndpointBoundaryTests(unittest.TestCase):
    def test_invalid_luts_and_endpoint_contracts_are_rejected(self):
        curve = tuple(i * 4 for i in range(255)) + (1023,)
        valid = ToneEndpoints(50, 950, 64, 192)
        invalid_curves = [curve[:-1], (1,) + curve[1:], curve[:-1] + (1022,),
                          curve[:10] + (100,) + curve[11:],
                          curve[:10] + (-1,) + curve[11:],
                          curve[:10] + (True,) + curve[11:]]
        for bad in invalid_curves:
            with self.subTest(curve=bad[:12]), self.assertRaises(ValueError):
                endpoint_oracle(bad, valid)
        for bad in (ToneEndpoints(-1, 950, 64, 192), ToneEndpoints(257, 950, 64, 192),
                    ToneEndpoints(50, 767, 64, 192), ToneEndpoints(50, 1024, 64, 192),
                    ToneEndpoints(50, 950, -1, 192), ToneEndpoints(50, 950, 64, 256),
                    ToneEndpoints(50, 950, 192, 64), ToneEndpoints(50, 950, 64, 64),
                    ToneEndpoints(True, 950, 64, 192), ToneEndpoints(50, 950, 64.0, 192)):
            with self.subTest(endpoints=bad), self.assertRaises(ValueError):
                endpoint_oracle(curve, bad)

    def test_degenerate_anchor_heights_require_neutral_endpoint(self):
        curve = (0,) * 128 + (1023,) * 128
        self.assertEqual(endpoint_oracle(curve, ToneEndpoints(0, 1023, 64, 192)), curve)
        for endpoints in (ToneEndpoints(1, 1023, 64, 192), ToneEndpoints(0, 1022, 64, 192)):
            with self.assertRaises(ValueError):
                endpoint_oracle(curve, endpoints)


DEPENDENCIES = (IMAGE.is_file() and ENGINE.is_file()
                and (TOOLCHAIN / 'gas/as-new').is_file()
                and (TOOLCHAIN / 'ld/ld-new').is_file()
                and (TOOLCHAIN / 'binutils/objcopy').is_file()
                and (TOOLCHAIN / 'binutils/objdump').is_file())


@unittest.skipUnless(DEPENDENCIES, 'Exact stock firmware, strict GNU engine, and tone binutils required')
class NativeEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='penf-tone-test-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.kernel = build_kernel(Path(cls.temp.name) / 'kernel')
        cls.identity = identity_lut()

    def check_native(self, curve, endpoints):
        before = tuple(curve)
        actual, report = native_endpoints(curve, endpoints, self.kernel)
        self.assertEqual(actual, endpoint_oracle(curve, endpoints))
        self.assertEqual(tuple(curve), before)
        self.assertEqual(actual[endpoints.shadow_index:endpoints.highlight_index + 1],
                         tuple(curve[endpoints.shadow_index:endpoints.highlight_index + 1]))
        self.assertTrue(report['preserved_registers'])
        self.assertTrue(report['stack_canaries'])
        self.assertTrue(report['buffer_canaries'])
        return actual

    def test_identity_and_endpoint_extremes_at_explicit_synthetic_anchors(self):
        for shadow, highlight in ((32, 208), (64, 192), (0, 255), (1, 254)):
            cs, height = self.identity[shadow], self.identity[highlight]
            for black, white in product(sorted({0, cs // 2, cs}),
                                        sorted({height, (height + 1023) // 2, 1023})):
                endpoints = ToneEndpoints(black, white, shadow, highlight)
                with self.subTest(endpoints=endpoints):
                    actual = self.check_native(self.identity, endpoints)
                    if black == 0 and white == 1023:
                        self.assertEqual(actual, self.identity)

    def test_plateaus_and_degenerate_anchors(self):
        curves = [(0,) * 128 + (1023,) * 128,
                  (0,) + (511,) * 254 + (1023,),
                  (0,) * 255 + (1023,), (0,) + (1023,) * 255]
        for curve in curves:
            for black, white in ((0, 1023), (curve[64], curve[192])):
                with self.subTest(curve=curve[:3], black=black, white=white):
                    self.check_native(curve, ToneEndpoints(black, white, 64, 192))

    def test_half_up_rounding_in_both_tails(self):
        curve = (0, 1, 2) + (2,) * 250 + (1021, 1022, 1023)
        actual = self.check_native(curve, ToneEndpoints(1, 1022, 2, 253))
        self.assertEqual(actual[:3], (1, 2, 2))
        self.assertEqual(actual[-3:], (1021, 1022, 1022))

    def test_seeded_monotone_tables(self):
        rng = random.Random(0x50454e46)
        for case in range(16):
            curve = (0, *sorted(rng.randrange(1024) for _ in range(254)), 1023)
            shadow = rng.randrange(1, 128)
            highlight = rng.randrange(128, 255)
            endpoints = ToneEndpoints(rng.randrange(curve[shadow] + 1),
                                      rng.randrange(curve[highlight], 1024), shadow, highlight)
            with self.subTest(case=case, endpoints=endpoints):
                self.check_native(curve, endpoints)

    def test_mixed_stock_native_curves(self):
        for slots in product((-7, 0, 7), repeat=3):
            raw = NativeToneParameters((0, 0, *slots))
            curve = self.identity if slots == (0, 0, 0) else native_tone(raw).lut
            self.assertTrue(all(a <= b for a, b in zip(curve, curve[1:])), slots)
            cs, height = curve[64], curve[192]
            endpoints = ToneEndpoints(cs // 2, (height + 1023) // 2, 64, 192)
            with self.subTest(slots=slots):
                self.check_native(curve, endpoints)

    def test_native_boundary_rejects_before_kernel_access(self):
        with self.assertRaises(ValueError):
            native_endpoints(self.identity, ToneEndpoints(1023, 0, 64, 192), None)


if __name__ == '__main__':
    unittest.main(verbosity=2)
