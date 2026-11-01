import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('penf_tone_build', ROOT/'patches/tone/pen-f/build.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)
REFERENCE = json.loads((ROOT/'tests/fixtures/tone-builder-reference.json').read_text())


class ToneBuildTests(unittest.TestCase):
    def test_altered_stock_is_rejected_before_output_creation(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            stock = folder/'wrong.bin'; stock.write_bytes(b'not pinned stock')
            out = folder/'out'
            with self.assertRaisesRegex(ValueError, 'Wrong stock firmware hash'):
                build.build(SimpleNamespace(stock=stock, out=out))
            self.assertFalse(out.exists())

    def test_optimized_python_cannot_disable_build_guards(self):
        process = subprocess.run([sys.executable, '-O', str(ROOT/'patches/tone/pen-f/build.py'),
                                  '--help'], capture_output=True, text=True)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn('requires assertions', process.stderr)

    def test_manifest_rejects_overlap_tampering_and_unlisted_changes(self):
        before, after = bytes(32), b'\0\1\2\0\3'+bytes(27)
        rows = build.changed_ranges(before, after)
        self.assertEqual(len(rows), 2)
        build.validate_ranges(before, after, rows)
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            build.validate_ranges(before, after, [rows[0], rows[0], rows[1]])
        with self.assertRaisesRegex(ValueError, 'Before hash'):
            build.validate_ranges(before, after, [dict(rows[0], before_sha256='wrong'), rows[1]])
        with self.assertRaisesRegex(ValueError, 'After hash'):
            build.validate_ranges(before, after, [dict(rows[0], after_sha256='wrong'), rows[1]])
        with self.assertRaisesRegex(ValueError, 'every changed byte'):
            build.validate_ranges(before, after, rows[:1])

    @unittest.skipUnless(os.environ.get('PENF_STOCK_CONTAINER'),
                         'Set PENF_STOCK_CONTAINER to the exact full PEN-F 3101 container')
    def test_complete_candidate_rebuild_and_container_integrity(self):
        stock = Path(os.environ['PENF_STOCK_CONTAINER'])
        with tempfile.TemporaryDirectory(prefix='penf-tone-package-') as folder:
            out = Path(folder)/'out'
            with patch.object(build.candidate, 'firmware', side_effect=AssertionError('decoded fixture read')):
                report = build.build(SimpleNamespace(stock=stock, out=out))
            for key in ('stock_sha256','pinned_hsl_package_sha256','package_sha256',
                        'package_bytes','main_sha256','osd_sha256'):
                self.assertEqual(report[key], REFERENCE[key], key)
            altered = bytearray(stock.read_bytes()); altered[100] ^= 1
            bad_stock = Path(folder)/'altered-stock.bin'; bad_stock.write_bytes(altered)
            bad_out = Path(folder)/'rejected'
            with self.assertRaisesRegex(ValueError, 'Wrong stock firmware hash'):
                build.build(SimpleNamespace(stock=bad_stock, out=bad_out))
            self.assertFalse(bad_out.exists())
            data = (out/'install/DCOLYMP/E1229999.BIN').read_bytes()
            blocks = build.parse(data)
            original = build.parse(stock.read_bytes())
            baseline = build.parse((out/'hsl-reference/install/DCOLYMP/E1229999.BIN').read_bytes())
            self.assertEqual(build.reconstruct(blocks), data)
            self.assertEqual(blocks[0].payload, (out/'candidate/main.bin').read_bytes())
            self.assertEqual(blocks[1].payload, baseline[1].payload)
            self.assertNotEqual(blocks[1].payload, original[1].payload)
            for block, old in zip(blocks, original):
                self.assertEqual(block.header, old.header)
                self.assertEqual(block.trailer[:28], old.trailer[:28])
            build.validate_ranges(baseline[0].payload, blocks[0].payload, report['nonoverlapping_main_ranges'])
            damaged = bytearray(data); damaged[100] ^= 1
            with self.assertRaisesRegex(ValueError, 'checksum'):
                build.parse(damaged)


if __name__ == '__main__':
    unittest.main()
