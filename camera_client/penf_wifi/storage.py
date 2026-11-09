# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Durable local records and one-client-at-a-time coordination on Linux."""
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile

from .protocol import ClientError


def now():
    return datetime.now(timezone.utc).isoformat()


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save_json(path, obj, *, overwrite=True):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, indent=2, allow_nan=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        if overwrite:
            os.replace(tmp, path)
        else:
            # Publish a complete file, failing if any file/symlink already
            # occupies the destination. The temporary file is on the same FS.
            os.link(tmp, path)
        sync_directory(path.parent)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Run:
    def __init__(self, root, command):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.path = Path(tempfile.mkdtemp(prefix=f"{stamp}-{command}-", dir=root))
        self.log = (self.path / "transcript.jsonl").open("x")

    def record(self, event):
        self.log.write(json.dumps({"time": now(), **event}, allow_nan=False) + "\n")
        self.log.flush()
        os.fsync(self.log.fileno())

    def save(self, name, obj):
        save_json(self.path / name, obj)

    def close(self):
        self.log.close()


class CameraState:
    """A crash/timeout marker persists until an explicit local acknowledgment.

    This coordinates clients using this same directory and camera address.
    It does not lock out OI.Share, other machines or alternative address aliases.
    """
    def __init__(self, root, camera, run):
        self.directory = Path(root) / "state" / hashlib.sha256(camera.encode()).hexdigest()[:24]
        self.directory.mkdir(parents=True, exist_ok=True)
        self.camera, self.run = camera, run
        self.marker = self.directory / "uncertain.json"
        self.lock = None

    def __enter__(self):
        self.lock = (self.directory / "client.lock").open("a+")
        try:
            fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            self.lock.close()
            raise ClientError("Another client using this camera address is running") from e
        return self

    def __exit__(self, *exc):
        self.lock.close()

    def require_clean(self):
        if self.marker.exists():
            raise ClientError("A previous operation has an uncertain outcome. Reads are allowed; further writes/session "
                              "changes are stopped. Reconnect Wi-Fi on the camera, then use "
                              "'acknowledge-reconnect --after-manual-reconnect'.")

    def arm(self, operation):
        self.require_clean()
        save_json(self.marker, {"camera": self.camera, "time": now(), "operation": operation,
                               "run": str(self.run.path.resolve())})

    def complete(self):
        self.marker.unlink()
        sync_directory(self.directory)

    def acknowledge_reconnect(self):
        if not self.marker.exists():
            return {"cleared": False, "camera_reconnection_performed_by_client": False}
        old = json.loads(self.marker.read_text())
        self.run.save("acknowledged-uncertainty.json", old)
        self.complete()
        return {"cleared": True, "previous": old, "camera_reconnection_performed_by_client": False}
