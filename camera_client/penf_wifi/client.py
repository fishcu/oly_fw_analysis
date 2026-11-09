# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Explicit camera operations; reads never initiate a remote-mode transition."""
from .protocol import (CAPABILITY, UNAVAILABLE, ClientError, Setting, integer,
                       named, profile_settings, scalar, signed, xml_root, validate_plan)
from .recipes import recipe_check, snapshot_recipe
from .storage import now


def check_ack(body):
    # Stock numeric setter can return an empty 200 response. Numeric readback
    # is mandatory afterwards; HTTP status alone never completes an upload.
    if body.strip():
        root = xml_root(body)
        if any(named(root, tag) for tag in ("error", "errorcode", "errcode")):
            raise ClientError("Camera returned an error in its response body")


class Camera:
    def __init__(self, transport, progress=None):
        self.transport = transport
        self.progress = progress or (lambda message: None)

    def identify(self):
        self.progress("Contacting camera (read-only identification)...")
        root = xml_root(self.transport.get("get_caminfo.cgi"))
        nodes = named(root, "model")
        if root.tag.rsplit("}", 1)[-1] != "caminfo" or len(nodes) != 1:
            raise ClientError("Expected camera information with one model name")
        model = (nodes[0].text or "").strip()
        if model.upper() != "PEN-F":
            raise ClientError(f"This client supports PEN-F only; camera reported {model!r}")
        return {"model": model,
                "fields": {x.tag.rsplit("}", 1)[-1]: x.text for x in root if len(x) == 0}}

    def discover(self):
        info = self.identify()
        connection = xml_root(self.transport.get("get_connectmode.cgi"))
        commands = xml_root(self.transport.get("get_commandlist.cgi"))
        if commands.tag.rsplit("}", 1)[-1] != "oishare":
            raise ClientError("Expected the camera's <oishare> command list")
        return {"camera": info, "connection": {
            x.tag.rsplit("}", 1)[-1]: x.text for x in connection.iter() if len(x) == 0},
                "advertised_commands": [x.attrib.get("name") for x in named(commands, "cgi")],
                "note": "No mode change or setting write. Hidden mcon is not expected in the command list."}

    def word(self, mode):
        return scalar(self.transport.get("get_mcon.cgi", {"mode": f"{mode:04X}"}))

    def capability(self):
        value = self.word(0xffff)
        return {"word": f"{value:08X}", "hsl1": value == CAPABILITY,
                "status": "HSL1" if value == CAPABILITY else "not advertised" if value == 0 else "unknown version"}

    def context(self):
        # Stable destination witnesses, not the physical PASM dial position.
        return {"bank": self.word(41), "native_shooting_mode": self.word(26)}

    def read(self, setting, extended):
        if setting.axis and not extended:
            raise ClientError("H/L readback requires the HSL1 firmware extension")
        value = self.word(setting.read_mode)
        if value == UNAVAILABLE:
            raise ClientError(f"{setting.label} is unavailable (busy, wrong bank or invalid ID)")
        value = signed(value)
        setting.validate(value)
        return value

    def snapshot(self, profile, info=None, capability=None):
        integer(profile, 1, 3, "COLOR profile")
        info = info if info is not None else self.identify()
        capability = capability if capability is not None else self.capability()
        before = self.context()
        settings = profile_settings(profile, capability["hsl1"])
        self.progress(f"Reading COLOR{profile}: 0/{len(settings)} settings...")
        values = {}
        for count, setting in enumerate(settings, 1):
            values[setting.label] = self.read(setting, capability["hsl1"])
            if count % 10 == 0 or count == len(settings):
                self.progress(f"Reading COLOR{profile}: {count}/{len(settings)} settings")
        after = self.context()
        if before != after:
            raise ClientError("Camera settings context changed while reading; snapshot is not consistent")
        return {"format": "penf-wifi-snapshot-v1", "time": now(), "camera": info,
                "profile": profile, "context": before, "capability": capability, "values": values,
                "HL": "included" if capability["hsl1"] else "unknown; no HSL1 readback, not assumed neutral",
                "scope": "Profile numeric readback, not a full camera-settings backup or durability proof"}

    def session(self, mode, state):
        if mode not in ("rec", "play"):
            raise ClientError("Only explicit rec and play session modes are supported")
        state.require_clean()
        info = self.identify()
        params = {"mode": mode}
        if mode == "rec":
            params["lvqty"] = "0320x0240"
        self.progress(f"Requesting {mode} session...")
        state.arm({"session_mode": mode})
        body = self.transport.get("switch_cammode.cgi", params)
        check_ack(body)
        # A successful mcon read establishes remote request admission on rec.
        if mode == "rec":
            self.progress("Checking remote settings access...")
        context = self.context() if mode == "rec" else None
        result = {"camera": info, "requested_session_mode": mode,
                  "command_acknowledged": True, "context_after": context,
                  "note": "No live-view stream or capture requested. This is not a persistence check."}
        state.run.save("session.json", result)
        state.complete()
        return result

    def check(self, plan, run, recommendations=None):
        profile = validate_plan(plan)
        snapshot = self.snapshot(profile)
        run.save("snapshot.json", snapshot)
        result = recipe_check(plan, snapshot, recommendations)
        result["network_access"] = True
        return result

    def apply(self, plan, state, recommendations=None):
        profile = validate_plan(plan)
        state.require_clean()
        info = self.identify()
        cap = self.capability()
        if not cap["hsl1"]:
            raise ClientError(f"Refusing all writes: camera does not advertise HSL1 ({cap['word']})")
        before = self.snapshot(profile, info, cap)
        if before["context"]["bank"] != 0:
            raise ClientError("Uploads currently require PASM bank 0; custom-bank loading is not supported")
        state.run.save("before.json", before)
        restore = snapshot_recipe(before, f"COLOR{profile} before upload")
        state.run.save("restore-recipe.json", restore)
        artifacts = {"restore_recipe": str((state.run.path / "restore-recipe.json").resolve()),
                     "applied_recipe": str((state.run.path / "applied-recipe.json").resolve())}
        expected = before["values"].copy()
        changed = [(s, v) for s, v in plan if expected[s.label] != v]
        if not changed:
            self.progress("Requested settings already match; no edits sent.")
            state.run.save("applied-recipe.json", snapshot_recipe(before))
            return {"changed": [], "no_op": True, "profile": profile,
                    "readback_verified": True, "persistent_save_verified": False,
                    "recommendations_only": recommendations or {}, **artifacts}
        # Keep this marker even on KeyboardInterrupt/process death or later log failure.
        state.arm({"profile": profile, "settings": [s.label for s, _ in changed]})
        applied = []
        for count, (setting, value) in enumerate(changed, 1):
            self.progress(f"Edit {count}/{len(changed)}: {setting.label} "
                          f"{expected[setting.label]:+d} -> {value:+d}")
            if self.context() != before["context"]:
                raise ClientError("Destination context changed during upload; stopped")
            if self.read(setting, True) != expected[setting.label]:
                raise ClientError(f"{setting.label} changed externally during upload; stopped")
            state.run.record({"event": "setting_attempt", "profile": profile,
                              "setting": setting.label, "old": expected[setting.label], "new": value})
            check_ack(self.transport.get("set_mcon.cgi", setting.write_params(value)))
            observed = self.read(setting, True)
            if observed != value:
                raise ClientError(f"Readback mismatch for {setting.label}: requested {value}, got {observed}; stopped")
            expected[setting.label] = value
            applied.append({"setting": setting.label, "value": value})
            state.run.record({"event": "setting_verified", **applied[-1]})
        self.progress("Verifying complete profile after edits...")
        after = self.snapshot(profile, info, cap)
        state.run.save("after.json", after)
        if after["context"] != before["context"] or after["values"] != expected:
            raise ClientError("Final profile/context differs from the expected result; stopped")
        state.run.save("applied-recipe.json", snapshot_recipe(after, f"COLOR{profile} after upload"))
        result = {"changed": applied, "readback_verified": True, "persistent_save_verified": False,
                  "recommendations_only": recommendations or {}, "profile": profile, **artifacts}
        state.run.save("upload.json", result)
        state.complete()
        return result
