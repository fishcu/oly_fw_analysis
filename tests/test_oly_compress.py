"""Bounded LZ4 repacking checks independent of any firmware file."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from oly_compress import MAGIC, _encode, expand_image, max_literal_run, repack_image, spans


class OlyCompressTest(unittest.TestCase):
    def test_edit_match_source_and_output(self):
        raw = b'abcd' * 32 + b'efgh' * 32
        packed = bytes(_encode(b'abcd', 4, 124) + _encode(b'efgh', 4, 124) + _encode(b''))
        original = bytearray(b'\xff' * len(raw))
        original[:16] = MAGIC
        struct.pack_into('<II', original, 16, len(packed), len(raw))
        original[24:32] = bytes(8)
        original[32:32 + len(packed)] = packed
        original = bytes(original)
        self.assertEqual(expand_image(original), raw)
        self.assertEqual(repack_image(original, raw), original)

        target = bytearray(raw)
        target[0] = ord('z')       # changes the original match's source
        target[63] = ord('y')      # changes its output only
        result = repack_image(original, target)
        self.assertEqual(expand_image(result), target)
        self.assertEqual(len(result), len(original))
        self.assertLess(spans(result)[0][1] + 32, len(raw))

    def test_split_keeps_literal_runs_short(self):
        raw = b'code' * 8 + b'\xff' * 4000
        packed = bytes(_encode(b'code', 4, 28) + _encode(b'\xff', 1, 3994) + _encode(b'\xff' * 5))
        original = bytearray(b'\xff' * len(raw))
        original[:16] = MAGIC
        struct.pack_into('<II', original, 16, len(packed), len(raw))
        original[24:32] = bytes(8)
        original[32:32 + len(packed)] = packed
        original = bytes(original)
        self.assertEqual(expand_image(original), raw)
        target = bytearray(raw)
        target[2000:2040] = bytes(range(40))   # new code inside the padding
        with self.assertRaises(ValueError):   # one long literal run no longer fits the span
            repack_image(original, target)
        split = repack_image(original, target, split=True, literal_limit=64)
        self.assertEqual(expand_image(split), bytes(target))
        p, packed_len, size = spans(split)[0]
        self.assertLessEqual(max_literal_run(split[p + 32:p + 32 + packed_len], size), 41)

if __name__ == '__main__':
    unittest.main()
