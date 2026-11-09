# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Recipe round trips, restore artifacts and read-only commands; no real camera."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from penf_wifi.__main__ import main
from penf_wifi.client import Camera
from penf_wifi.protocol import (ClientError, RECIPE_FORMAT, Setting, load_json,
                               recipe_plan)
from penf_wifi.recipes import recipe_check, snapshot_recipe
from penf_wifi.storage import CameraState, Run
from penf_wifi.transport import TransportError
from test_client import FakeCamera, ROOT

# Synthetic, intentionally non-neutral profile; no private camera snapshots.
SYNTHETIC_VALUES = {
    **{f"{axis}[{i}]": (i + offset) % 15 - 7
       for axis, offset in (("hue", 0), ("saturation", 3), ("lightness", 7))
       for i in range(12)},
    "contrast": 1, "highlights": -3, "midtones": 0, "shadows": 2,
}


class RecipeTests(unittest.TestCase):
    def setUp(self):
        self.baseline = {
            "format": "penf-wifi-snapshot-v1", "profile": 2,
            "camera": {"model": "PEN-F"},
            "capability": {"hsl1": True, "word": "48534C31"},
            "context": {"bank": 0, "native_shooting_mode": 4},
            "HL": "included", "values": deepcopy(SYNTHETIC_VALUES),
        }

    def test_snapshot_exports_all_values_without_camera_identity(self):
        exported = snapshot_recipe(self.baseline)
        self.assertEqual(set(exported), {"format", "name", "settings"})
        self.assertEqual(exported["settings"]["hue"], list(range(-7, 5)))
        self.assertEqual(exported["settings"]["contrast"], 1)
        plan, _ = recipe_plan(json.dumps(exported), 3)
        self.assertEqual(len(plan), 40)
        self.assertTrue(all(setting.profile == 3 for setting, _ in plan))
        self.assertEqual(dict((setting.label, value) for setting, value in plan),
                         SYNTHETIC_VALUES)

    def test_all_sector_positions_and_endpoints_survive_conversion(self):
        for profile in (1, 2, 3):
            snapshot = deepcopy(self.baseline)
            snapshot["profile"] = profile
            values = {**{f"{axis}[{i}]": (i + offset) % 15 - 7
                         for axis, offset in (("hue", 0), ("saturation", 3), ("lightness", 7))
                         for i in range(12)},
                      "contrast": -2, "highlights": 7, "midtones": -7, "shadows": 1}
            snapshot["values"] = values
            plan, _ = recipe_plan(json.dumps(snapshot_recipe(snapshot)), profile)
            self.assertEqual({s.label: v for s, v in plan}, values)

    def test_stock_snapshot_exports_only_known_settings(self):
        snapshot = Camera(FakeCamera(capability=0)).snapshot(1)
        recipe = snapshot_recipe(snapshot)
        self.assertNotIn("hue", recipe["settings"])
        self.assertNotIn("lightness", recipe["settings"])
        full, _ = recipe_plan(json.dumps(snapshot_recipe(self.baseline)), 1)
        result = recipe_check(full, snapshot)
        self.assertFalse(result["matches"])
        self.assertFalse(result["can_apply"])
        self.assertFalse(result["complete_hsl_profile"])
        self.assertEqual(len(result["unavailable"]), 24)
        self.assertFalse(result["network_access"])

    def test_partial_recipe_does_not_claim_complete_profile_match(self):
        result = recipe_check([(Setting(2, "contrast"), 1)], self.baseline)
        self.assertTrue(result["matches"])
        self.assertFalse(result["complete_hsl_profile"])
        self.assertEqual(len(result["not_requested"]), 39)
        self.assertFalse(result["persistent_save_verified"])

    def test_reject_incomplete_malformed_or_inconsistent_snapshots(self):
        bad = []
        for key, value in (("profile", True), ("profile", 4), ("camera", {"model": "OM-3"}),
                           ("HL", "unknown"), ("capability", {"hsl1": True, "word": "00000000"}),
                           ("capability", {"hsl1": False, "word": "48534C32"}),
                           ("context", None)):
            obj = deepcopy(self.baseline); obj[key] = value; bad.append(obj)
        for value in (True, 1.0, 8, None, "1"):
            obj = deepcopy(self.baseline); obj["values"]["hue[0]"] = value; bad.append(obj)
        obj = deepcopy(self.baseline); del obj["values"]["lightness[11]"]; bad.append(obj)
        obj = deepcopy(self.baseline); obj["values"]["wb_ab"] = 2; bad.append(obj)
        obj = deepcopy(self.baseline); obj["context"]["bank"] = True; bad.append(obj)
        for obj in bad:
            with self.subTest(obj=obj), self.assertRaises(ClientError):
                snapshot_recipe(obj)

    def test_duplicate_keys_and_nonfinite_snapshot_numbers_rejected(self):
        for text in ('{"profile":1,"profile":2}', '{"value":NaN}', '{"value":Infinity}'):
            with self.subTest(text=text), self.assertRaises(ClientError):
                load_json(text, "snapshot JSON")


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fake = FakeCamera()

    def cli(self, args, expected=0):
        out, err = io.StringIO(), io.StringIO()
        with patch("penf_wifi.__main__.HTTPTransport", return_value=self.fake), \
                redirect_stdout(out), redirect_stderr(err):
            code = main(["--out", str(self.root / "runs"), *map(str, args)])
        self.assertEqual(code, expected, err.getvalue())
        return json.loads(out.getvalue()) if out.getvalue() else err.getvalue()

    def file(self, name, obj):
        path = self.root / name
        path.write_text(json.dumps(obj))
        return path

    def test_preview_upload_export_verify_and_restore_each_profile(self):
        # A complete nonneutral target exercises every supported field and
        # checks that all unselected profiles remain untouched.
        recipe = load_json((ROOT / "camera_client/examples/subtle-color.json").read_text())
        target = self.file("target.json", recipe)
        for profile in (1, 2, 3):
            with self.subTest(profile=profile):
                baseline = self.fake.values.copy()
                saved = self.root / f"color{profile}.json"
                self.cli(["inspect", "--profile", profile, "--recipe-out", saved])
                writes = len(self.fake.writes)
                preview = self.cli(["preview", target, "--profile", profile])
                self.assertFalse(preview["matches"])
                self.assertTrue(preview["can_apply"])
                self.assertTrue(preview["complete_hsl_profile"])
                self.assertEqual(len(self.fake.writes), writes)
                result = self.cli(["apply", target, "--profile", profile, "--execute"])
                self.assertEqual(load_json(Path(result["restore_recipe"]).read_text())["settings"],
                                 load_json(saved.read_text())["settings"])
                checked = self.cli(["verify", result["applied_recipe"], "--profile", profile])
                self.assertTrue(checked["matches"])
                self.assertFalse(checked["persistent_save_verified"])
                self.assertTrue(self.cli(["apply", target, "--profile", profile, "--execute"])["no_op"])
                self.cli(["apply", result["restore_recipe"], "--profile", profile, "--execute"])
                self.assertEqual(self.fake.values, baseline)
        self.assertFalse(any(e == "switch_cammode.cgi" for e, _ in self.fake.calls))

    def test_restore_recipe_exists_before_first_write_and_survives_lost_reply(self):
        run = Run(self.root, "test"); self.addCleanup(run.close)
        state = CameraState(self.root, "http://fake", run)
        original = self.fake.get
        def observed(endpoint, params=None):
            if endpoint == "set_mcon.cgi":
                restore = load_json((run.path / "restore-recipe.json").read_text())
                self.assertEqual(restore["settings"]["lightness"], [0] * 12)
                self.assertFalse((run.path / "applied-recipe.json").exists())
            return original(endpoint, params)
        self.fake.get = observed
        self.fake.write_effect = "timeout"
        with self.assertRaises(TransportError):
            Camera(self.fake).apply([(Setting(2, "lightness", 7), 3)], state)
        self.assertEqual(len(self.fake.writes), 1)
        self.assertTrue(state.marker.exists())
        self.assertTrue((run.path / "restore-recipe.json").exists())
        self.assertFalse((run.path / "applied-recipe.json").exists())

    def test_backup_file_failure_prevents_all_setting_writes(self):
        run = Run(self.root, "test"); self.addCleanup(run.close)
        state = CameraState(self.root, "http://fake", run)
        original = run.save
        def fail(name, obj):
            if name == "restore-recipe.json":
                raise OSError("Disk full before backup")
            original(name, obj)
        run.save = fail
        with self.assertRaises(OSError):
            Camera(self.fake).apply([(Setting(1, "contrast"), 1)], state)
        self.assertFalse(self.fake.writes)
        self.assertFalse(state.marker.exists())

    def test_verify_and_preview_allowed_during_uncertainty_but_never_clear_it(self):
        recipe = self.file("target.json", {"format": RECIPE_FORMAT, "settings": {"contrast": 1}})
        self.fake.write_effect = "timeout"
        self.cli(["apply", recipe, "--profile", 2, "--execute"], expected=2)
        count = len(self.fake.writes)
        marker = next((self.root / "runs/state").glob("*/uncertain.json"))
        old = marker.read_bytes()
        for cmd in ("verify", "preview"):
            result = self.cli([cmd, recipe, "--profile", 2])
            self.assertTrue(result["matches"])
            self.assertTrue(result["client_stop_active"])
            self.assertFalse(result["can_apply"])
            self.assertEqual(marker.read_bytes(), old)
        self.assertEqual(len(self.fake.writes), count)

    def test_verify_mismatch_has_json_and_distinct_exit_status(self):
        recipe = self.file("target.json", {"format": RECIPE_FORMAT, "settings": {"contrast": 1}})
        result = self.cli(["verify", recipe, "--profile", 2], expected=3)
        self.assertEqual(result["differences"], [{"setting": "contrast", "current": 0, "requested": 1}])
        self.assertFalse(self.fake.writes)
        self.assertFalse(list((self.root / "runs").glob("state/*/uncertain.json")))

    def test_new_read_commands_validate_before_constructing_transport(self):
        recipe = self.file("invalid.json", {"format": RECIPE_FORMAT, "settings": {"wb_ab": 1}})
        for cmd in ("preview", "verify"):
            with patch("penf_wifi.__main__.HTTPTransport") as transport, redirect_stderr(io.StringIO()):
                self.assertEqual(main([cmd, str(recipe), "--profile", "1"]), 2)
                transport.assert_not_called()

    def test_export_is_offline_and_refuses_overwrite(self):
        snapshot = self.file("snapshot.json", Camera(self.fake).snapshot(2))
        exported = self.root / "recipe.json"
        with patch("penf_wifi.__main__.HTTPTransport") as transport, \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(main(["export", str(snapshot), "--output", str(exported), "--name", "My look"]), 0)
            before = exported.read_bytes()
            self.assertEqual(main(["export", str(snapshot), "--output", str(exported)]), 2)
            self.assertEqual(exported.read_bytes(), before)
            transport.assert_not_called()
        self.assertEqual(load_json(exported.read_text())["name"], "My look")

    def test_inspect_output_collision_stops_before_connecting(self):
        output = self.file("existing.json", {"keep": True})
        with patch("penf_wifi.__main__.HTTPTransport") as transport, redirect_stderr(io.StringIO()):
            self.assertEqual(main(["inspect", "--profile", "1", "--recipe-out", str(output)]), 2)
            transport.assert_not_called()
        self.assertEqual(load_json(output.read_text()), {"keep": True})


if __name__ == "__main__":
    unittest.main()
