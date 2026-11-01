import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))

from penf_tone_candidate import build_candidate
from penf_tone_transport_probe import (acquisition_abi, alternative_path, constructor, compact_postcall, entry_compatibility,
                                       hooks, owner_matrix, pipeline, publication, raw_acquisition, source_normalization)


class NativeToneTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='penf-tone-transport-')
        cls.candidate = build_candidate(Path(cls.temporary.name) / 'candidate')

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_bank_publication_before_late_section_load(self):
        result = publication(self.candidate)
        self.assertEqual(len(result['banks']), 9)
        self.assertTrue(result['publication_without_section8'])

    def test_each_owner_retains_its_acquired_endpoint(self):
        result = owner_matrix(self.candidate)
        self.assertEqual(len(result['owners']), 45)
        self.assertEqual(result['rejected_owners'], 8)

    def test_first_color_acquisition_normalizes_invalid_state_only(self):
        self.assertEqual(len(source_normalization(self.candidate)),30)

    def test_job_hooks_preserve_native_context(self):
        self.assertEqual(len(acquisition_abi(self.candidate)), 2)
        self.assertEqual(len(hooks(self.candidate)), 2)
        result = compact_postcall(self.candidate)
        self.assertEqual([r['status'] for r in result['cases']], [0, 1, 0xffffffff])

    def test_raw_reuse_clears_noncolor_endpoint(self):
        self.assertEqual(len(raw_acquisition(self.candidate)), 6)

    def test_constructor_clears_entire_trailer(self):
        result = constructor(self.candidate)
        self.assertEqual(result['allocation_request'], 14960)
        self.assertEqual(result['zero_start'] + result['zero_bytes'], 14960)

    def test_real_entry_preserves_stock_neutral_and_bypass_results(self):
        self.assertEqual(len(entry_compatibility(self.candidate)), 10)

    def test_alternative_tone_path_remains_stock(self):
        self.assertEqual(len(alternative_path(self.candidate)), 2)

    def test_published_snapshot_reaches_native_upload(self):
        result = pipeline(self.candidate, record=15)
        self.assertEqual(result['upload']['bank'], 1)
        self.assertEqual(result['upload']['endpoints'], result['endpoints'])

    def test_absent_late_section_runs_stock_with_zero_job_word(self):
        result = pipeline(self.candidate, loaded=False)
        self.assertEqual(result['word'], 0)
        self.assertEqual(result['endpoints'], [0, 1023])


if __name__ == '__main__':
    unittest.main()
