import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import penf_tone_viewer_probe as viewer


class ToneViewerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='penf-tone-viewer-')
        folder = Path(cls.temporary.name)
        cls.graph = viewer.build_graph(folder/'candidate')
        cls.getter = viewer.getter_adapter(folder/'getter')

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_native_data_tables_align_every_halfword_and_word(self):
        rows=viewer.data_alignment_cases(self.graph)
        self.assertEqual(len(rows),16)
        self.assertTrue(all(row['aligned'] for row in rows), rows)

    def test_color_middle_queries_preserve_native_control_descriptors(self):
        self.assertEqual(len(viewer.middle_cases(self.graph, self.getter)), 18)

    def test_color_pair_compaction_preserves_queries_logging_and_native_join(self):
        self.assertEqual(len(viewer.pair_cases(self.graph,self.getter)),20)

    def test_all_pages_publish_canonical_values_and_next_info_destination(self):
        self.assertEqual(len(viewer.footer_cases(self.graph,self.getter)),18)

    def test_footer_preserves_other_modes_unloaded_state_and_first_publication_flag(self):
        self.assertEqual(len(viewer.footer_fallback_cases(self.graph,self.getter)),19)

    def test_other_modes_preserve_the_native_middle_continuation(self):
        self.assertEqual(len(viewer.fallback_cases(self.graph, self.getter)), 8)

    def test_literal_hint_uses_native_formatter_and_fits_native_english_japanese_layout(self):
        self.assertEqual(len(viewer.formatter_cases()), 6)
        self.assertEqual(len(viewer.layout_cases()), 6)


if __name__ == '__main__':
    unittest.main()
