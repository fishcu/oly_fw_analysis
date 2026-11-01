import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import penf_tone_graph_probe as graph


class ToneGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='penf-tone-graph-')
        cls.candidate = graph.build_graph(Path(cls.temporary.name) / 'candidate')

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_native_graph_matches_reference_and_effective_endpoint_geometry(self):
        graph.paint_cases(self.candidate)

    def test_native_child_filter_is_profile_page_and_receiver_specific(self):
        graph.filter_cases(self.candidate)

    def test_unsupported_display_and_unloaded_sections_preserve_stock_path(self):
        graph.paint_fallback_cases(self.candidate)

    def test_endpoint_refresh_invalidates_the_entire_receiver(self):
        graph.update_cases(self.candidate)

    def test_relocated_editor_and_image_pipeline_still_join_native_paths(self):
        graph.composed_cases(self.candidate,Path(self.temporary.name))

    def test_unmodeled_text_allocator_stops_at_the_real_pool_boundary(self):
        result = graph.paint(graph.fixture(self.candidate, word=graph.packed(64, 960)),
                             self.candidate, model_text=False)
        self.assertFalse(result['complete_return'])
        self.assertEqual(result['allocator_stop']['address'], 0x61a8e884)


if __name__ == '__main__':
    unittest.main()
