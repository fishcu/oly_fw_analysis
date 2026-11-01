"""Native placed tone-editor contracts; no camera or flash access."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import penf_tone_editor_probe as editor


class ToneEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='penf-tone-editor-')
        root = Path(cls.temporary.name)
        cls.candidate = editor.build_candidate(root / 'candidate')
        cls.editor = editor.build_editor(root / 'editor', cls.candidate)
        cls.adapter = editor.build_adapter(root / 'adapter')

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_tagged_native_gui_request_updates_selected_profile_only(self):
        editor.manager_cases(self.candidate, self.editor)

    def test_reference_curve_uses_current_native_controls(self):
        editor.reference_cases(self.candidate, self.editor, self.adapter)

    def test_relative_steps_keep_exact_clipped_heights(self):
        editor.step_cases(self.candidate, self.editor)

    def test_three_pages_reuse_native_color_bindings(self):
        editor.binding_cases(self.candidate, self.editor)

    def test_real_arrow_and_dial_callbacks(self):
        editor.input_cases(self.candidate, self.editor)

    def test_info_cycles_all_three_color_pages(self):
        editor.page_cases(self.candidate, self.editor)

    def test_held_reset_requests_neutral_endpoints(self):
        editor.reset_cases(self.candidate, self.editor)

    def test_unavailable_late_sections_do_not_edit_inner_controls(self):
        editor.unavailable_cases(self.candidate, self.editor)

    def test_compressed_info_preserves_stock_classification(self):
        editor.stock_info_cases(self.candidate, self.editor)

    def test_profile_changes_clear_stale_endpoint_routing(self):
        editor.stale_cases(self.candidate, self.editor)

    def test_other_native_family_keeps_four_page_binding_and_input(self):
        editor.other_family_cases(self.candidate, self.editor)

    def test_info_publishes_native_parameter_page(self):
        editor.publication_cases(self.candidate, self.editor)


if __name__ == '__main__':
    unittest.main()
