import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from penf_tone_graph_candidate import build_graph
import penf_tone_rgb_probe as rgb

class RgbToneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='penf-rgb-')
        cls.graph=build_graph(Path(cls.temp.name)/'candidate')
        cls.audit=Path(os.environ.get('PENF_RGB_AUDIT_DIR',cls.temp.name))
        cls.audit.mkdir(parents=True,exist_ok=True)
        cls.reports={}
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def check(self, probe, *args):
        self.reports[probe.__name__]=probe(*args)
        (self.audit/'rgb-audit.json').write_text(json.dumps(dict(
            main_sha256=hashlib.sha256(self.graph.image).hexdigest(),
            checks=self.reports),indent=2)+'\n')
    def test_four_channel_acquired_snapshots(self):self.check(rgb.snapshot_cases,self.graph.base)
    def test_explicit_channel_manager_requests(self):self.check(rgb.manager_cases,self.graph)
    def test_all_profile_channel_page_states(self):self.check(rgb.editor_cases,self.graph)
    def test_native_gamma_lane_isolation_and_repeated_reset(self):self.check(rgb.gamma_cases,self.graph.base)
    def test_native_gamma_upload_with_warm_cache(self):self.check(rgb.upload_cases,self.graph.base)
    def test_trash_cycles_without_setting_writes(self):self.check(rgb.cycle_cases,self.graph)
    def test_native_constructor_trash_and_active_timeout(self):self.check(rgb.native_cycle_cases,self.graph)
    def test_channel_footer_and_graph(self):self.check(rgb.channel_display_cases,self.graph,self.audit)
    def test_native_storage_ownership_and_all_bank_reset(self):
        from penf_tone_rgb_ownership_probe import storage_cases
        self.check(storage_cases)
    def test_native_extended_section_load_and_reload(self):
        from penf_tone_rgb_ownership_probe import residency_cases
        self.check(residency_cases,self.graph)
    def test_gamma_invalid_producers_owned_buffers_and_reserved_bits(self):self.check(rgb.gamma_boundary_cases,self.graph.base)
    def test_gamma_stack_bound(self):self.check(rgb.gamma_stack_case,self.graph.base)
    def test_channel_page_reset_and_request_rejection(self):self.check(rgb.reset_and_reject_cases,self.graph)
    def test_dispatch_hook_handled_and_stock_abi(self):self.check(rgb.dispatcher_cases,self.graph)
    def test_unloaded_encoded_selection_never_indexes_stock_tables(self):self.check(rgb.unloaded_selection_cases,self.graph)
