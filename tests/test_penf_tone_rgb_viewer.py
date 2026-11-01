import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_tone_graph_candidate import build_graph
from penf_tone_rgb_viewer_probe import joined_cases, negative_case, fallback_cases


class NativeRgbViewerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='penf-rgb-viewer-')
        cls.graph = build_graph(Path(cls.temp.name)/'candidate')
        cls.audit = Path(os.environ.get('PENF_RGB_VIEWER_AUDIT_DIR', cls.temp.name))
        cls.audit.mkdir(parents=True, exist_ok=True)
        cls.reports = {}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def check(self, probe):
        self.reports[probe.__name__] = probe(self.graph)
        (self.audit/'viewer-audit.json').write_text(json.dumps(self.reports, indent=2)+'\n')

    def test_joined_DEL_native_update_publication_and_return(self):
        self.check(joined_cases)

    def test_old_HSL_target_overruns_same_exact_viewer(self):
        self.check(negative_case)

    def test_rejected_DEL_does_not_update_publish_or_draw(self):
        self.check(fallback_cases)
