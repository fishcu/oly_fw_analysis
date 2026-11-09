# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Offline format checks; no camera or firmware fixture is required."""
import struct
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from oly_container import decode, encode, parse, reconstruct, sum32


def fixture():
    header = bytearray(32)
    header[:4] = b"OE\x12\x20"
    struct.pack_into("<IIHHH", header, 8, 0x403A0000, 256, 0x3101, 0, 0x100)
    payload = bytes(range(256))
    trailer = bytearray(header)
    struct.pack_into("<I", trailer, 28, -(2 * sum32(header) + sum32(payload)) & 0xFFFFFFFF)
    return bytes(header) + encode(payload) + bytes(trailer)


class ContainerTests(unittest.TestCase):
    def test_documented_permutation(self):
        # Independently spelled out from the CHDK example, including inversion.
        self.assertEqual(decode(b"0123456789abcdef"),
                         bytes(c ^ 255 for c in b"13026475ba98decf"))

    def test_full_byte_domain_roundtrip(self):
        original = bytes(range(256))
        self.assertEqual(decode(encode(original)), original)
        self.assertEqual(encode(decode(original)), original)

    def test_container_roundtrip(self):
        source = fixture()
        blocks = parse(source)
        self.assertEqual(blocks[0].address, 0x403A0000)
        self.assertEqual(blocks[0].payload, bytes(range(256)))
        self.assertEqual(reconstruct(blocks), source)

    def test_reject_corrupted_payload(self):
        bad = bytearray(fixture())
        bad[50] ^= 1
        with self.assertRaisesRegex(ValueError, "checksum"):
            parse(bad)

    def test_reject_header_trailer_mismatch(self):
        bad = bytearray(fixture())
        bad[16] ^= 1
        with self.assertRaisesRegex(ValueError, "header/trailer"):
            parse(bad)

    def test_reject_truncation_and_trailing_bytes(self):
        source = fixture()
        for cut in (0, 1, 31, 32, 63, len(source) - 1):
            with self.subTest(cut=cut), self.assertRaises(ValueError):
                parse(source[:cut])
        with self.assertRaises(ValueError):
            parse(source + b"extra")

    def test_reject_unaligned_size(self):
        bad = bytearray(fixture())
        struct.pack_into("<I", bad, 12, 255)
        with self.assertRaisesRegex(ValueError, "size"):
            parse(bad)

    def test_reject_unsupported_formats(self):
        for signature in (b"OM", b"ZZ"):
            bad = bytearray(fixture())
            bad[:2] = signature
            with self.subTest(signature=signature), self.assertRaisesRegex(ValueError, "signature"):
                parse(bad)

    def test_reject_mixed_models(self):
        other = bytearray(fixture())
        other[2] ^= 1
        with self.assertRaisesRegex(ValueError, "model"):
            parse(fixture() + other)


if __name__ == "__main__":
    unittest.main()
