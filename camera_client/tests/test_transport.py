# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""HTTP edge cases tested at the connection boundary, never a camera address."""
import http.client
import unittest
from unittest.mock import MagicMock, patch

from penf_wifi.protocol import ClientError
from penf_wifi.transport import (DEFAULT_AGENT, MAX_BODY, HTTPTransport, HTTPError,
                                 TransportError, base_url)


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.transport = HTTPTransport("http://localhost:18080", record=self.events.append)

    def connection(self, status=200, body=b"<response/>"):
        connection = MagicMock()
        response = connection.getresponse.return_value
        response.status = status
        response.read.return_value = body
        response.getheader.return_value = "text/xml"
        return connection

    def test_get_headers_wire_and_durable_log_order(self):
        connection = self.connection()
        connection.request.side_effect = lambda *a, **k: self.assertEqual(self.events[-1]["event"], "request")
        with patch("penf_wifi.transport.http.client.HTTPConnection", return_value=connection):
            self.transport.get("set_mcon.cgi", {"mode": "03AF", "value": "4851FFF9"})
        args, kwargs = connection.request.call_args
        self.assertEqual(args, ("GET", "/set_mcon.cgi?mode=03AF&value=4851FFF9"))
        self.assertEqual(kwargs["headers"]["User-Agent"], DEFAULT_AGENT)
        self.assertEqual([e["event"] for e in self.events], ["request", "response"])
        connection.getresponse.return_value.read.assert_called_once_with(MAX_BODY + 1)
        connection.close.assert_called_once()

    def test_redirect_and_error_are_not_followed_or_retried(self):
        for status in (301, 302, 500, 520):
            connection = self.connection(status)
            with self.subTest(status=status), patch("penf_wifi.transport.http.client.HTTPConnection", return_value=connection) as constructor:
                with self.assertRaises(HTTPError):
                    self.transport.get("set_mcon.cgi", {"mode": "03AF", "value": "48500001"})
                constructor.assert_called_once()
                connection.request.assert_called_once()
                connection.close.assert_called_once()

    def test_timeout_or_broken_http_no_retry(self):
        for error in (TimeoutError("timed out"), http.client.RemoteDisconnected("gone")):
            connection = self.connection()
            connection.getresponse.side_effect = error
            with self.subTest(error=error), patch("penf_wifi.transport.http.client.HTTPConnection", return_value=connection) as constructor:
                with self.assertRaises(TransportError):
                    self.transport.get("get_caminfo.cgi")
                constructor.assert_called_once()
                connection.request.assert_called_once()
                connection.close.assert_called_once()

    def test_short_readiness_wait_preserves_native_response_timeout(self):
        for endpoint, expected in (("get_caminfo.cgi", 5), ("get_mcon.cgi", 40),
                                   ("set_mcon.cgi", 40), ("switch_cammode.cgi", 40)):
            connection = self.connection()
            with self.subTest(endpoint=endpoint), \
                    patch("penf_wifi.transport.http.client.HTTPConnection", return_value=connection) as constructor:
                self.transport.get(endpoint)
                self.assertEqual(constructor.call_args.kwargs['timeout'], 5)
                connection.connect.assert_called_once()
                connection.sock.settimeout.assert_called_once_with(expected)
                self.assertEqual(set(self.events[-1]['phase_seconds']),
                                 {'connect', 'send_request', 'response_headers', 'response_body'})

    def test_connection_timeout_is_distinct_from_response_wait(self):
        for phase in ('connect', 'response_headers'):
            connection = self.connection()
            getattr(connection, 'connect' if phase == 'connect' else 'getresponse').side_effect = TimeoutError('timed out')
            with self.subTest(phase=phase), \
                    patch("penf_wifi.transport.http.client.HTTPConnection", return_value=connection) as constructor:
                with self.assertRaisesRegex(TransportError, phase):
                    self.transport.get('get_caminfo.cgi')
                constructor.assert_called_once()
                self.assertEqual(connection.request.call_count, 0 if phase == 'connect' else 1)
                self.assertEqual(self.events[-1]['phase'], phase)
                self.assertIn('elapsed_seconds', self.events[-1])
                connection.close.assert_called_once()

    def test_interrupt_logs_phase_without_retry(self):
        connection = self.connection()
        connection.getresponse.side_effect = KeyboardInterrupt
        with patch("penf_wifi.transport.http.client.HTTPConnection", return_value=connection) as constructor:
            with self.assertRaises(KeyboardInterrupt):
                self.transport.get('switch_cammode.cgi', {'mode': 'rec'})
            constructor.assert_called_once()
            connection.request.assert_called_once()
            connection.close.assert_called_once()
        self.assertEqual(self.events[-1]['event'], 'transport_interrupted')
        self.assertEqual(self.events[-1]['phase'], 'response_headers')

    def test_oversized_body_rejected(self):
        connection = self.connection(body=b"x" * (MAX_BODY + 1))
        with patch("penf_wifi.transport.http.client.HTTPConnection", return_value=connection):
            with self.assertRaisesRegex(TransportError, "1 MiB"):
                self.transport.get("get_caminfo.cgi")

    def test_address_and_timeout_validation(self):
        self.assertEqual(base_url("192.168.0.10:80/"), "http://192.168.0.10")
        self.assertEqual(base_url("http://[::1]:1234"), "http://[::1]:1234")
        for address in ("https://localhost", "http://u:p@localhost", "http://localhost/path", "http://localhost:0",
                        "http://localhost:99999", "http://[", "http://local host", "http://localhost\r\n/"):
            with self.subTest(address=address), self.assertRaises(ClientError):
                base_url(address)
        for timeout in (0, -1, float("nan"), float("inf")):
            with self.subTest(timeout=timeout), self.assertRaises(ClientError):
                HTTPTransport(timeout=timeout)
            with self.subTest(ready_timeout=timeout), self.assertRaises(ClientError):
                HTTPTransport(ready_timeout=timeout)
        self.assertEqual(HTTPTransport(timeout=1, ready_timeout=5).ready_timeout, 1)
        for gap in (-1, 11, float("nan"), float("inf")):
            with self.subTest(gap=gap), self.assertRaises(ClientError):
                HTTPTransport(request_gap=gap)
        with self.assertRaises(ClientError):
            HTTPTransport(user_agent="bad\r\nheader")

    def test_no_other_camera_endpoints(self):
        with patch("penf_wifi.transport.http.client.HTTPConnection") as constructor:
            with self.assertRaises(ClientError):
                self.transport.get("exec_shutter.cgi")
            constructor.assert_not_called()

    def test_pacing_waits_after_completion_without_replaying_requests(self):
        clock = [100.0]
        starts, sleeps = [], []
        connection = self.connection()

        def request(*args, **kwargs):
            starts.append(clock[0])
            clock[0] += 0.4  # A slow exchange must not consume the inter-request gap.

        def sleep(delay):
            sleeps.append(delay)
            clock[0] += delay

        connection.request.side_effect = request
        transport = HTTPTransport("http://localhost:18080", request_gap=0.15)
        with patch("penf_wifi.transport.http.client.HTTPConnection", return_value=connection), \
                patch("penf_wifi.transport.time.monotonic", side_effect=lambda: clock[0]), \
                patch("penf_wifi.transport.time.sleep", side_effect=sleep):
            transport.get("get_caminfo.cgi")
            transport.get("get_connectmode.cgi")
        self.assertEqual(connection.request.call_count, 2)
        self.assertEqual(len(sleeps), 1)
        self.assertAlmostEqual(sleeps[0], 0.15)
        self.assertAlmostEqual(starts[1] - starts[0], 0.55)


if __name__ == "__main__":
    unittest.main()
