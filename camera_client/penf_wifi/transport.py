# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Direct HTTP: no proxies, redirects, retries, or automatic session changes."""
import http.client
import math
import time
from urllib.parse import urlencode, urlsplit

from .protocol import ClientError

MAX_BODY = 1024 * 1024
DEFAULT_AGENT = "OlympusCameraKit"
DEFAULT_REQUEST_GAP = 0.05
ENDPOINTS = {
    "get_caminfo.cgi", "get_connectmode.cgi", "get_commandlist.cgi",
    "switch_cammode.cgi", "get_mcon.cgi", "set_mcon.cgi",
}


class TransportError(ClientError):
    pass


class HTTPError(TransportError):
    def __init__(self, status, endpoint):
        self.status = status
        hint = " Enter remote mode explicitly with 'session rec' if not already there." if status == 520 else ""
        super().__init__(f"HTTP {status} from {endpoint}.{hint} No retry was sent.")


def base_url(value):
    try:
        u = urlsplit(value if "://" in value else "http://" + value)
        port = u.port
    except ValueError as e:
        raise ClientError(f"Invalid camera address: {e}") from e
    if (u.scheme != "http" or not u.hostname or u.username or u.password or
            u.path not in ("", "/") or u.query or u.fragment or port == 0 or
            any(ord(c) <= 32 or ord(c) > 126 for c in value)):
        raise ClientError("Camera must be an http://host[:port] address without credentials or a path")
    host = f"[{u.hostname}]" if ":" in u.hostname else u.hostname.lower()
    return f"http://{host}" + (f":{port}" if port and port != 80 else "")


class HTTPTransport:
    def __init__(self, camera="http://192.168.0.10", timeout=40, user_agent=DEFAULT_AGENT,
                 record=None, request_gap=DEFAULT_REQUEST_GAP, ready_timeout=5):
        self.camera = base_url(camera)
        u = urlsplit(self.camera)
        self.host, self.port = u.hostname, u.port or 80
        if not math.isfinite(timeout) or timeout <= 0:
            raise ClientError("Timeout must be positive and finite")
        if not math.isfinite(ready_timeout) or ready_timeout <= 0:
            raise ClientError("Readiness timeout must be positive and finite")
        if not math.isfinite(request_gap) or not 0 <= request_gap <= 10:
            raise ClientError("Request gap must be finite and in 0..10 seconds")
        if not user_agent or any(ord(c) < 32 or ord(c) > 126 for c in user_agent):
            raise ClientError("User-Agent must be nonempty printable ASCII")
        self.timeout, self.user_agent = timeout, user_agent
        self.ready_timeout = min(ready_timeout, timeout)
        self.record = record or (lambda event: None)
        self.request_gap = request_gap
        self._last_completed = None

    def get(self, endpoint, params=None):
        if endpoint not in ENDPOINTS:
            raise ClientError(f"Endpoint not supported: {endpoint}")
        params = params or {}
        path = "/" + endpoint + ("?" + urlencode(params) if params else "")
        # Each request uses a fresh connection. Give the embedded server time
        # to retire the previous one. This is pacing, never replay of a request.
        if self._last_completed is not None:
            remaining = self.request_gap - (time.monotonic() - self._last_completed)
            if remaining > 0:
                time.sleep(remaining)
        event = {"event": "request", "method": "GET", "path": path, "camera": self.camera,
                 "user_agent": self.user_agent}
        # The attempt is flushed before a mutating request can leave the PC.
        self.record(event)
        connection = http.client.HTTPConnection(self.host, self.port, timeout=self.ready_timeout)
        start = time.monotonic()
        phase, timings = "connect", {}
        try:
            connection.connect()
            timings[phase] = round(time.monotonic() - start, 4)
            # Identification is a read-only readiness check, before the caller
            # arms a mode/setting mutation. Do not shorten response waits for
            # native application commands, which may complete much later.
            io_timeout = self.ready_timeout if endpoint == "get_caminfo.cgi" else self.timeout
            connection.sock.settimeout(io_timeout)
            phase, phase_start = "send_request", time.monotonic()
            connection.request("GET", path, headers={"User-Agent": self.user_agent,
                                                     "Connection": "close", "Accept": "text/xml"})
            timings[phase] = round(time.monotonic() - phase_start, 4)
            phase, phase_start = "response_headers", time.monotonic()
            response = connection.getresponse()
            timings[phase] = round(time.monotonic() - phase_start, 4)
            phase, phase_start = "response_body", time.monotonic()
            body = response.read(MAX_BODY + 1)
            timings[phase] = round(time.monotonic() - phase_start, 4)
            if len(body) > MAX_BODY:
                raise TransportError("Response exceeds the 1 MiB limit")
            self.record({"event": "response", "status": response.status,
                         "elapsed_seconds": round(time.monotonic() - start, 4),
                         "phase_seconds": timings,
                         "content_type": response.getheader("Content-Type"),
                         "body": body.decode("utf-8", errors="replace")})
            if response.status != 200:
                raise HTTPError(response.status, endpoint)
            return body
        except (OSError, http.client.HTTPException) as e:
            elapsed = round(time.monotonic() - start, 4)
            self.record({"event": "transport_error", "error": str(e), "path": path,
                         "phase": phase, "elapsed_seconds": elapsed, "phase_seconds": timings})
            hint = (" Check that Linux is connected to the camera's Wi-Fi and its connection screen is ready."
                    if endpoint == "get_caminfo.cgi" else "")
            raise TransportError(f"Request to {path} failed during {phase} after {elapsed:.1f}s: {e}."
                                 f"{hint} No retry was sent.") from e
        except KeyboardInterrupt:
            self.record({"event": "transport_interrupted", "path": path, "phase": phase,
                         "elapsed_seconds": round(time.monotonic() - start, 4), "phase_seconds": timings})
            raise
        finally:
            connection.close()
            self._last_completed = time.monotonic()
