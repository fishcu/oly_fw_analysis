# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Performance changes must preserve faults, aliases and evidence bytes."""
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import penf_emulator as emulator
from penf_boot_emulator import write_gzip_json
from penf_replay_compare import compare_gzip


class PerformanceEquivalenceTests(unittest.TestCase):
    def test_digest_cache_only_reuses_identical_immutable_bytes(self):
        emulator._region_digests = {}
        frozen, mutable = bytes(8192), bytearray(8192)
        regions = [emulator.Region('constant', 0x1000, frozen),
                   emulator.Region('mutable', 0x10000, mutable)]
        first = emulator._region_inputs(regions)
        mutable[0] = 1
        real_sha256 = hashlib.sha256
        with patch.object(emulator.hashlib, 'sha256', wraps=real_sha256) as sha:
            second = emulator._region_inputs(regions)
            self.assertEqual(sha.call_count, 1)
        self.assertEqual(first[0], second[0])
        self.assertNotEqual(first[1]['sha256'], second[1]['sha256'])
        self.assertEqual(second[1]['sha256'], real_sha256(mutable).hexdigest())
        emulator._region_inputs([])
        self.assertEqual(emulator._region_digests, {})

    def test_engine_digest_invalidates_replaced_same_size_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'engine'
            path.write_bytes(b'old')
            with patch.object(emulator, 'ENGINE', path):
                first = emulator._engine_digest()
                replacement = path.with_suffix('.new')
                replacement.write_bytes(b'new')
                replacement.replace(path)
                second = emulator._engine_digest()
            self.assertEqual(first, hashlib.sha256(b'old').hexdigest())
            self.assertEqual(second, hashlib.sha256(b'new').hexdigest())

    def test_batched_json_preserves_exact_decompressed_bytes(self):
        payload = {'events':[{'name':'yellow / \u00e9', 'data':[None, True, False, -7, 2.5]}, {}, []],
                   'empty':[], 'source_sha256':{'a':'b'}, 'snapshot':'00'*10000}
        old = io.StringIO()
        json.dump(payload, old)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'result.json.gz'
            write_gzip_json(path, payload)
            self.assertEqual(gzip.decompress(path.read_bytes()), old.getvalue().encode())

    def test_streaming_comparison_checks_boundary_and_unallowed_change(self):
        old = b'"tools/example.py": "'+b'a'*64+b'"'
        new = b'"tools/example.py": "'+b'b'*64+b'"'
        before = b' '*((1 << 20)-7)+old+b' final memory bytes'
        after = before.replace(old, new)
        with tempfile.TemporaryDirectory() as directory:
            left, right = Path(directory)/'before.gz', Path(directory)/'after.gz'
            left.write_bytes(gzip.compress(before))
            right.write_bytes(gzip.compress(after))
            result = compare_gzip(left, right, [(old.decode(), new.decode())])
            self.assertEqual(result['bytes'], len(after))
            self.assertEqual(result['normalized_sha256'], hashlib.sha256(after).hexdigest())
            right.write_bytes(gzip.compress(after[:-1]+b'X'))
            with self.assertRaises(AssertionError):
                compare_gzip(left, right, [(old.decode(), new.decode())])


if __name__ == '__main__':
    unittest.main()
