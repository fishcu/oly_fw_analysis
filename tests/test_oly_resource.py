"""Resource aliasing uses stock image pointers and leaves the other records alone."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from oly_compress import MAGIC, _encode, _sequences
from oly_resource import alias_images, _liblz4


class ResourceAliasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            _liblz4()
        except ValueError as error:
            raise unittest.SkipTest(str(error)) from error

    def setUp(self):
        self.raw = bytearray(256)
        struct.pack_into('<II', self.raw, 0, 0x1008, 0x1010)
        struct.pack_into('<II', self.raw, 16, 0x0ffc, 0x2000)
        packed = _encode(self.raw)
        self.payload = bytearray(b'\xff' * 2528)
        struct.pack_into('<4I', self.payload, 0, 2016, 512, 0, 0)
        self.payload[2016:2032] = MAGIC
        struct.pack_into('<II', self.payload, 2032, len(packed), len(self.raw))
        self.payload[2040:2048] = bytes(8)
        self.payload[2048:2048 + len(packed)] = packed

    def decoded_record(self, payload):
        packed, raw = struct.unpack_from('<II', payload, 2032)
        return _sequences(payload[2048:2048 + packed], raw)[0]

    def test_alias_changes_one_pointer_and_preserves_component_size(self):
        changed = alias_images(bytes(self.payload), [(0, 1)])
        self.assertEqual(len(changed), len(self.payload))
        self.assertEqual(changed[:2016], self.payload[:2016])
        expected = bytearray(self.raw)
        struct.pack_into('<I', expected, 16, 0x2000)
        self.assertEqual(self.decoded_record(changed), expected)

    def test_rejects_duplicate_and_missing_source(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            alias_images(bytes(self.payload), [(0, 1), (0, 1)])
        with self.assertRaisesRegex(ValueError, 'Invalid resource alias'):
            alias_images(bytes(self.payload), [(0, 0)])


if __name__ == '__main__':
    unittest.main()
