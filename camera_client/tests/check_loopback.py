# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Opt-in real HTTP integration against 127.0.0.1 only (not a camera).

python3 -m unittest discover -s tests -p check_loopback.py -v
"""
from contextlib import redirect_stdout, redirect_stderr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlsplit, parse_qs

from penf_wifi.__main__ import main
from penf_wifi.transport import HTTPError
from test_client import FakeCamera


class LoopbackTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeCamera()
        self.headers = []
        fake, headers = self.fake, self.headers
        self.identify_release = threading.Event()
        self.identify_release.set()
        identify_release = self.identify_release

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                u = urlsplit(self.path)
                headers.append(dict(self.headers))
                if u.path == '/get_caminfo.cgi':
                    identify_release.wait(2)
                try:
                    body = fake.get(u.path.lstrip("/"), {k: v[0] for k, v in parse_qs(u.query).items()})
                    status = 200
                except HTTPError as e:
                    status, body = e.status, b""
                self.send_response(status)
                self.send_header("Content-Type", "text/xml")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # The readiness-timeout test deliberately closes early.

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.global_args = ["--camera", f"http://127.0.0.1:{self.server.server_port}", "--out", str(self.root)]

    def tearDown(self):
        self.identify_release.set()
        self.server.shutdown()
        self.worker.join()
        self.server.server_close()
        self.temp.cleanup()

    def cli(self, *args, expected=0):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = main(self.global_args + list(args))
        self.assertEqual(result, expected, err.getvalue())
        return json.loads(out.getvalue()) if result == 0 else err.getvalue()

    def test_current_firmware_discovery_session_readback_and_refusal(self):
        self.fake.capability = 0
        self.fake.remote = False
        self.cli("discover")
        self.assertFalse(self.fake.remote)
        self.cli("session", "rec")
        result = self.cli("inspect", "--profile", "2")
        self.assertEqual(len(result["values"]), 16)
        self.cli("set", "saturation", "1", "--sector", "0", "--profile", "2", "--execute", expected=2)
        self.assertFalse(self.fake.writes)
        self.cli("session", "play")
        self.assertFalse(self.fake.remote)
        self.assertTrue(all(h["User-Agent"] == "OlympusCameraKit" for h in self.headers))
        transcripts = list(self.root.glob("*/transcript.jsonl"))
        self.assertEqual(len(transcripts), 5)
        events = [json.loads(line) for path in transcripts for line in path.read_text().splitlines()]
        self.assertEqual(sum(e["event"] == "request" for e in events), len(self.fake.calls))
        self.assertEqual(sum(e["event"] == "response" for e in events), len(self.fake.calls))

    def test_extended_write_readback_and_200_noop_stop(self):
        self.cli("set", "lightness", "-7", "--sector", "0", "--profile", "2", "--execute")
        self.assertEqual(self.fake.writes, [{"mode": "03AF", "value": "4852FFF9"}])
        self.assertEqual(self.cli("read", "lightness", "--sector", "0", "--profile", "2")["value"], -7)
        self.fake.write_effect = "ignore"
        error = self.cli("set", "hue", "2", "--sector", "0", "--profile", "2", "--execute", expected=2)
        self.assertIn("Readback mismatch", error)
        calls = len(self.fake.calls)
        self.cli("set", "hue", "3", "--sector", "0", "--profile", "2", "--execute", expected=2)
        self.assertEqual(len(self.fake.calls), calls)
        self.assertEqual(len(self.fake.writes), 2)
        self.assertEqual(len(list(self.root.glob("state/*/uncertain.json"))), 1)

    def test_readiness_timeout_before_session_request(self):
        self.identify_release.clear()
        error = self.cli('--ready-timeout', '0.1', 'session', 'rec', expected=2)
        self.assertIn('response_headers', error)
        self.assertIn('No retry was sent', error)
        self.assertEqual(len(self.headers), 1)
        self.assertEqual(list(self.root.glob('state/*/uncertain.json')), [])
        self.identify_release.set()
        self.assertFalse(any(e == 'switch_cammode.cgi' for e, _ in self.fake.calls))

    def test_recipe_workflow_over_http_without_implicit_mode_switch(self):
        self.global_args += ["--request-gap", "0"]
        self.fake.remote = False
        self.cli("session", "rec")
        baseline = self.fake.values.copy()
        recipe = self.root / "baseline.json"
        self.cli("inspect", "--profile", "3", "--recipe-out", str(recipe))
        target = self.root / "target.json"
        obj = json.loads(recipe.read_text())
        obj['settings']['hue'][11] = -7
        obj['settings']['lightness'][0] = 7
        obj['settings']['contrast'] = 1
        target.write_text(json.dumps(obj))
        preview = self.cli("preview", str(target), "--profile", "3")
        self.assertEqual(len(preview['differences']), 3)
        self.assertFalse(self.fake.writes)
        self.cli("verify", str(target), "--profile", "3", expected=3)
        result = self.cli("apply", str(target), "--profile", "3", "--execute")
        self.assertEqual(len(self.fake.writes), 3)
        self.assertTrue(self.cli("verify", result['applied_recipe'], "--profile", "3")['matches'])
        self.cli("apply", result['restore_recipe'], "--profile", "3", "--execute")
        self.assertEqual(self.fake.values, baseline)
        self.assertEqual(len(self.fake.writes), 6)
        self.assertEqual(sum(e == 'switch_cammode.cgi' for e, _ in self.fake.calls), 1)
        self.cli("session", "play")


if __name__ == "__main__":
    unittest.main()
