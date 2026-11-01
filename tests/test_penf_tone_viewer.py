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

    def test_color_middle_queries_preserve_controls_and_name_the_endpoint_page(self):
        self.assertEqual(len(viewer.middle_cases(self.graph, self.getter)), 18)

    def test_other_modes_preserve_the_native_middle_continuation(self):
        self.assertEqual(len(viewer.fallback_cases(self.graph, self.getter)), 8)

    def test_literal_hint_uses_native_formatter_and_fits_native_english_japanese_layout(self):
        self.assertEqual(len(viewer.formatter_cases()), 2)
        self.assertEqual(len(viewer.layout_cases()), 2)


if __name__ == '__main__':
    unittest.main()
