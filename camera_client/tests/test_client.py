# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Protocol/state tests with an explicitly simulated camera; no camera network I/O."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from penf_wifi.__main__ import main, compare
from penf_wifi.client import Camera
from penf_wifi.protocol import (CAPABILITY, ClientError, Setting, RECIPE_FORMAT,
                               recipe_plan, scalar, signed)
from penf_wifi.storage import CameraState, Run
from penf_wifi.transport import HTTPError, TransportError

ROOT = Path(__file__).resolve().parents[2]


def xml_word(value):
    return f'<response><value>{value & 0xffffffff:08X}</value></response>'.encode()


class FakeCamera:
    """Independent key/register model; does not model native scheduling or flash."""
    def __init__(self, capability=CAPABILITY):
        self.capability = capability
        self.model, self.bank, self.mode, self.remote = "PEN-F", 0, 3, True
        self.calls, self.write_effect = [], "normal"
        # Keys from the native profile registry, not Setting.key under test.
        self.values = {key: 0 for key in (*range(931, 967), *range(916, 919), *range(967, 976))}
        self.values.update({key | flag: 0 for flag in (0x8000, 0xc000) for key in range(931, 967)})

    def get(self, endpoint, params=None):
        params = params or {}
        self.calls.append((endpoint, params.copy()))
        if endpoint == "get_caminfo.cgi":
            return f'<caminfo><model>{self.model}</model><MISOAExpComp>available</MISOAExpComp></caminfo>'.encode()
        if endpoint == "get_connectmode.cgi":
            return b'<connectmode><mode>private</mode></connectmode>'
        if endpoint == "get_commandlist.cgi":
            return b'<oishare><cgi name="get_caminfo"/><cgi name="switch_cammode"/><cgi name="get_camprop"/></oishare>'
        if endpoint == "switch_cammode.cgi":
            self.remote = params["mode"] == "rec"
            if self.write_effect == "timeout":
                raise TransportError("Simulated lost session reply")
            return b""
        if not self.remote:
            raise HTTPError(520, endpoint)
        mode = int(params["mode"], 16)
        if endpoint == "get_mcon.cgi":
            value = {0xffff: self.capability, 41: self.bank, 26: self.mode}.get(mode, self.values.get(mode, 0))
            return xml_word(value)
        if endpoint != "set_mcon.cgi":
            raise AssertionError(endpoint)
        value = int(params["value"], 16)
        tag = value >> 16
        assert tag in (0x4850, 0x4851, 0x4852), "Raw write must never be sent"
        key = mode | {0x4850: 0, 0x4851: 0x8000, 0x4852: 0xc000}[tag]
        if self.write_effect != "ignore":
            self.values[key] = (value & 0xffff) - (0x10000 if value & 0x8000 else 0)
        if self.write_effect == "timeout":
            raise TransportError("Reply lost AFTER camera changed its setting")
        if self.write_effect == "interrupt":
            raise KeyboardInterrupt
        if self.write_effect == "invalid_xml":
            return b"not XML"
        if self.write_effect == "bank_change":
            self.bank = 1
        if self.write_effect == "other_change":
            self.values[968] = 4
        return b""

    @property
    def writes(self):
        return [p for e, p in self.calls if e == "set_mcon.cgi"]


class ProtocolTests(unittest.TestCase):
    def test_wire_examples_and_key_boundaries(self):
        self.assertEqual(Setting(2, "saturation", 0).write_params(5), {"mode": "03AF", "value": "48500005"})
        self.assertEqual(Setting(2, "hue", 0).write_params(-7), {"mode": "03AF", "value": "4851FFF9"})
        self.assertEqual(Setting(2, "lightness", 0).write_params(7), {"mode": "03AF", "value": "48520007"})
        self.assertEqual(Setting(1, "saturation", 0).key, 931)
        self.assertEqual(Setting(3, "saturation", 11).key, 966)
        self.assertEqual([Setting(3, k).key for k in ("contrast", "highlights", "midtones", "shadows")],
                         [918, 973, 974, 975])

    def test_native_recorded_xml_and_signed_results(self):
        # Reuse retained emulator output, not a freshly synthesized expectation.
        readers = json.loads((Path(__file__).parent / "fixtures/native-readers.json").read_text())["readers"]
        self.assertEqual(scalar(readers["stock_discovery"]["xml"].encode()), 0)
        self.assertEqual(scalar(readers["extension_discovery"]["xml"].encode()), CAPABILITY)
        for row in readers["direct_reads"]:
            self.assertEqual(signed(row["native"]["result"]), row["value"])
            candidates = [Setting(p, axis, i) for p in (1, 2, 3) for axis in ("hue", "lightness") for i in range(12)]
            self.assertEqual(sum(s.read_mode == int(row["mode"], 16) for s in candidates), 1)

    def test_malformed_scalar_responses(self):
        for body in (b"", b"<html>error</html>", b"<response><value>-7</value></response>",
                     b"<response><value>0x03</value></response>",
                     b"<response><value>0</value><value>1</value></response>",
                     b"<!DOCTYPE response><response><value>0</value></response>",
                     b"<response><value>100000000</value></response>"):
            with self.subTest(body=body), self.assertRaises(ClientError):
                scalar(body)

    def test_whole_recipe_validation_and_recommendations(self):
        plan, notes = recipe_plan((ROOT / "camera_client/examples/subtle-color.json").read_text(), 2)
        self.assertEqual(len(plan), 40)
        self.assertEqual(set(notes), {"white_balance", "exposure_compensation"})
        for values in ({"contrast": 0.2}, {"hue": [0] * 11}, {"saturation": [0] * 11 + [8]},
                       {"highlights": -8}, {"shadows": True}, {"white_balance": "auto"},
                       {"wb_ab": 1}, {"kelvin": 5000}, {"exposure_compensation": 1}, {}):
            text = json.dumps({"format": RECIPE_FORMAT, "settings": values})
            with self.subTest(values=values), self.assertRaises(ClientError):
                recipe_plan(text, 2)
        for text in ('{"format":"penf-color-recipe-v1","settings":{"contrast":0,"contrast":1}}',
                     '{"format":"penf-color-recipe-v1","settings":{"contrast":NaN}}'):
            with self.assertRaises(ClientError):
                recipe_plan(text, 2)

    def test_no_arbitrary_settings_or_bad_sectors(self):
        for args in ((2, "wb_ab"), (2, "contrast", 0), (2, "hue", 12), (2, "saturation"),
                     (0, "contrast"), (True, "contrast")):
            with self.subTest(args=args), self.assertRaises(ClientError):
                Setting(*args)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = Run(self.root, "test")
        self.addCleanup(self.run.close)
        self.state = CameraState(self.root, "http://fake", self.run)
        self.fake = FakeCamera()
        self.camera = Camera(self.fake)

    def test_discovery_does_not_switch_mode_or_write(self):
        self.fake.remote = False
        result = self.camera.discover()
        self.assertEqual(result["camera"]["model"], "PEN-F")
        self.assertIn("get_caminfo", result["advertised_commands"])
        self.assertEqual([e for e, _ in self.fake.calls],
                         ["get_caminfo.cgi", "get_connectmode.cgi", "get_commandlist.cgi"])

    def test_stock_snapshot_does_not_invent_hl_values(self):
        self.fake.capability = 0
        result = self.camera.snapshot(2)
        self.assertEqual(len(result["values"]), 16)
        self.assertIn("unknown", result["HL"])
        self.assertTrue(all(e.startswith("get_") for e, _ in self.fake.calls))
        self.assertFalse(any(k.startswith(("hue", "lightness")) for k in result["values"]))

    def test_unknown_capability_refuses_even_saturation(self):
        for cap in (0, 0x48534c32, 0x80000000):
            self.fake.capability = cap
            with self.subTest(cap=cap), self.assertRaisesRegex(ClientError, "Refusing all writes"):
                self.camera.apply([(Setting(2, "saturation", 0), 1)], self.state)
            self.assertFalse(self.fake.writes)
            self.assertFalse(self.state.marker.exists())

    def test_wrong_model_stops_before_hidden_commands(self):
        self.fake.model = "OM-3"
        with self.assertRaisesRegex(ClientError, "PEN-F only"):
            self.camera.apply([(Setting(2, "contrast"), 1)], self.state)
        self.assertEqual(len(self.fake.calls), 1)

    def test_custom_bank_refused(self):
        self.fake.bank = 1
        with self.assertRaisesRegex(ClientError, "bank 0"):
            self.camera.apply([(Setting(2, "contrast"), 1)], self.state)
        self.assertFalse(self.fake.writes)

    def test_invalid_plan_rejected_before_network(self):
        for plan in ([], [("raw ID", 3)], [(Setting(1, "contrast"), 9)],
                     [(Setting(1, "contrast"), 1), (Setting(2, "contrast"), 1)],
                     [(Setting(1, "contrast"), 1), (Setting(1, "contrast"), 2)]):
            with self.subTest(plan=plan), self.assertRaises(ClientError):
                self.camera.apply(plan, self.state)
        self.assertEqual(self.fake.calls, [])

    def test_complete_recipe_and_repeat_noop(self):
        # Every setting changes, exercising both signed endpoints on all axes.
        obj = {"format": RECIPE_FORMAT, "settings": {axis: [-7, 7] * 6 for axis in ("hue", "saturation", "lightness")}}
        obj["settings"].update(contrast=2, highlights=7, midtones=-7, shadows=1)
        obj["recommendations"] = {"white_balance": "Daylight", "exposure_compensation": "+1/3 EV"}
        for profile in (1, 2, 3):
            plan, notes = recipe_plan(json.dumps(obj), profile)
            result = self.camera.apply(plan, self.state, notes)
            self.assertEqual(len(result["changed"]), 40)
            self.assertTrue(result["readback_verified"])
            self.assertFalse(result["persistent_save_verified"])
            self.assertFalse(self.state.marker.exists())
            count = len(self.fake.writes)
            self.assertTrue(self.camera.apply(plan, self.state)["no_op"])
            self.assertEqual(len(self.fake.writes), count)
        self.assertEqual(len(self.fake.writes), 120)
        self.assertTrue((self.run.path / "before.json").exists())
        self.assertTrue((self.run.path / "after.json").exists())
        self.assertFalse(any(e == "switch_cammode.cgi" for e, _ in self.fake.calls))

    def test_success_status_without_change_stops_immediately(self):
        self.fake.write_effect = "ignore"
        with self.assertRaisesRegex(ClientError, "Readback mismatch"):
            self.camera.apply([(Setting(2, "hue", 0), 2), (Setting(2, "lightness", 0), 3)], self.state)
        self.assertEqual(len(self.fake.writes), 1)
        self.assertTrue(self.state.marker.exists())

    def test_lost_reply_after_change_stops_across_process_lifetimes(self):
        self.fake.write_effect = "timeout"
        plan = [(Setting(2, "lightness", 0), 7), (Setting(2, "hue", 0), 1)]
        with self.assertRaises(TransportError):
            self.camera.apply(plan, self.state)
        self.assertEqual(self.fake.values[0xc3af], 7)
        self.assertEqual(len(self.fake.writes), 1)
        second_state = CameraState(self.root, "http://fake", self.run)
        calls = len(self.fake.calls)
        with self.assertRaisesRegex(ClientError, "uncertain"):
            self.camera.apply(plan, second_state)
        self.assertEqual(len(self.fake.calls), calls)
        # Reads remain possible. No mode toggle or automatic rollback occurs.
        self.assertEqual(self.camera.snapshot(2)["values"]["lightness[0]"], 7)
        self.assertEqual(len(self.fake.writes), 1)
        self.assertTrue(second_state.acknowledge_reconnect()["cleared"])
        self.assertFalse(self.state.marker.exists())
        self.assertTrue((self.run.path / "acknowledged-uncertainty.json").exists())

    def test_keyboard_interrupt_and_malformed_reply_keep_marker(self):
        for behavior, error in (("interrupt", KeyboardInterrupt), ("invalid_xml", ClientError)):
            self.fake.write_effect = behavior
            with self.subTest(behavior=behavior), self.assertRaises(error):
                self.camera.apply([(Setting(2, "contrast"), 1 if behavior == "interrupt" else 2)], self.state)
            self.assertTrue(self.state.marker.exists())
            self.state.acknowledge_reconnect()

    def test_context_change_stops_before_next_write(self):
        self.fake.write_effect = "bank_change"
        with self.assertRaisesRegex(ClientError, "context changed"):
            self.camera.apply([(Setting(2, "contrast"), 1), (Setting(2, "highlights"), 2)], self.state)
        self.assertEqual(len(self.fake.writes), 1)
        self.assertTrue(self.state.marker.exists())

    def test_unrequested_edit_detected_at_final_snapshot(self):
        self.fake.write_effect = "other_change"
        with self.assertRaisesRegex(ClientError, "differs from the expected"):
            self.camera.apply([(Setting(1, "contrast"), 1)], self.state)
        self.assertTrue(self.state.marker.exists())

    def test_unavailable_hl_cannot_be_mistaken_for_zero(self):
        self.fake.values[0x83af] = 0x80000000
        with self.assertRaisesRegex(ClientError, "unavailable"):
            self.camera.snapshot(2)

    def test_session_mode_is_explicit_and_not_a_liveview_request(self):
        self.fake.remote = False
        with self.assertRaises(HTTPError):
            self.camera.snapshot(2)
        self.camera.session("rec", self.state)
        self.camera.snapshot(2)
        self.camera.session("play", self.state)
        switches = [p for e, p in self.fake.calls if e == "switch_cammode.cgi"]
        self.assertEqual(switches, [{"mode": "rec", "lvqty": "0320x0240"}, {"mode": "play"}])
        self.assertFalse(self.state.marker.exists())
        self.assertFalse(self.fake.writes)

    def test_failed_session_change_also_stops(self):
        self.fake.write_effect = "timeout"
        with self.assertRaises(TransportError):
            self.camera.session("rec", self.state)
        self.assertTrue(self.state.marker.exists())
        count = len(self.fake.calls)
        with self.assertRaises(ClientError):
            self.camera.session("play", self.state)
        self.assertEqual(len(self.fake.calls), count)

    def test_concurrent_local_clients_are_excluded(self):
        with self.state:
            with self.assertRaisesRegex(ClientError, "Another client"):
                with CameraState(self.root, "http://fake", self.run):
                    self.fail("Second lock succeeded")

    def test_compare_saved_snapshots(self):
        before = self.camera.snapshot(2)
        self.run.save("before.json", before)
        self.fake.values[0x83af] = -7
        self.run.save("after.json", self.camera.snapshot(2))
        diff = compare(self.run.path / "before.json", self.run.path / "after.json")
        self.assertEqual(diff["changed"], {"hue[0]": {"before": 0, "after": -7}})


class CLITests(unittest.TestCase):
    def test_progress_keeps_stdout_machine_readable_and_makes_no_extra_calls(self):
        fake = FakeCamera()
        with tempfile.TemporaryDirectory() as d, \
                patch('penf_wifi.__main__.HTTPTransport', return_value=fake):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(main(['--out', d, 'set', 'hue', '-2', '--sector', '7',
                                       '--profile', '2', '--execute']), 0)
            result = json.loads(out.getvalue())
            self.assertEqual(result['changed'], [{'setting': 'hue[7]', 'value': -2}])
            self.assertIn('Contacting camera', err.getvalue())
            self.assertIn('Reading COLOR2: 40/40', err.getvalue())
            self.assertIn('Edit 1/1: hue[7] +0 -> -2', err.getvalue())
            self.assertIn('Verifying complete profile', err.getvalue())
            self.assertEqual(len(fake.calls), 95)

    def test_identity_failure_sends_no_session_change_and_leaves_no_uncertainty(self):
        fake = FakeCamera()
        def fail_identity(endpoint, params=None):
            self.assertEqual(endpoint, 'get_caminfo.cgi')
            raise TransportError('Identification timed out')
        fake.get = fail_identity
        with tempfile.TemporaryDirectory() as d, \
                patch('penf_wifi.__main__.HTTPTransport', return_value=fake):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(main(['--out', d, 'session', 'rec']), 2)
            self.assertIn('Contacting camera', err.getvalue())
            self.assertNotIn('Requesting rec', err.getvalue())
            self.assertEqual(list(Path(d).glob('state/*/uncertain.json')), [])
            error = json.loads(next(Path(d).glob('*/error.json')).read_text())
            self.assertFalse(error['uncertain_operation'])

    def test_help_and_dry_run_are_offline(self):
        examples = ROOT / "camera_client/examples/subtle-color.json"
        for args in ([], ["set", "hue", "-7", "--profile", "2", "--sector", "0"],
                     ["apply", str(examples), "--profile", "3"]):
            output = io.StringIO()
            with self.subTest(args=args), patch("penf_wifi.__main__.HTTPTransport") as transport:
                with redirect_stdout(output):
                    self.assertEqual(main(args), 0)
                transport.assert_not_called()
                if args:
                    self.assertFalse(json.loads(output.getvalue())["network_access"])

    def test_invalid_recipe_never_constructs_transport(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bad.json"
            path.write_text(json.dumps({"format": RECIPE_FORMAT, "settings": {"exposure_compensation": 1}}))
            with patch("penf_wifi.__main__.HTTPTransport") as transport, redirect_stderr(io.StringIO()):
                self.assertEqual(main(["apply", str(path), "--profile", "1", "--execute"]), 2)
                transport.assert_not_called()


if __name__ == "__main__":
    unittest.main()
