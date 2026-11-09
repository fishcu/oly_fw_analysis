# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Portable numeric recipes derived from validated client snapshots.

Snapshots retain camera/context evidence; exported recipes contain only a
name and supported settings. Missing H/L is never converted to neutral H/L.
"""
from .protocol import (AXES, CAPABILITY, RECIPE_FORMAT, ClientError, integer,
                       profile_settings, validate_plan)


def snapshot_recipe(snapshot, name=None):
    if not isinstance(snapshot, dict) or snapshot.get("format") != "penf-wifi-snapshot-v1":
        raise ClientError("Expected a penf-wifi-snapshot-v1 snapshot")
    camera = snapshot.get("camera")
    if not isinstance(camera, dict) or camera.get("model") != "PEN-F":
        raise ClientError("Snapshot must identify a PEN-F")
    profile = integer(snapshot.get("profile"), 1, 3, "Snapshot COLOR profile")
    context = snapshot.get("context")
    if not isinstance(context, dict):
        raise ClientError("Snapshot lacks its settings context")
    for key in ("bank", "native_shooting_mode"):
        integer(context.get(key), 0, 0xffffffff, f"Snapshot {key}")
    cap = snapshot.get("capability")
    if not isinstance(cap, dict) or type(cap.get("hsl1")) is not bool:
        raise ClientError("Snapshot lacks its HSL capability evidence")
    extended = cap["hsl1"]
    # An unrecognized capability word is not a qualified stock snapshot.
    expected_word = f"{CAPABILITY:08X}" if extended else "00000000"
    if cap.get("word") != expected_word:
        raise ClientError("Snapshot capability word is unsupported or inconsistent")
    expected_hl = "included" if extended else "unknown; no HSL1 readback, not assumed neutral"
    if snapshot.get("HL") != expected_hl:
        raise ClientError("Snapshot H/L availability is inconsistent")
    settings = profile_settings(profile, extended)
    values = snapshot.get("values")
    if not isinstance(values, dict) or set(values) != {s.label for s in settings}:
        raise ClientError("Snapshot has missing or unexpected settings; cannot export a partial read")
    recipe_values = {}
    for setting in settings:
        value = setting.validate(values[setting.label])
        if setting.name in AXES:
            recipe_values.setdefault(setting.name, []).append(value)
        else:
            recipe_values[setting.name] = value
    if name is None:
        name = f"COLOR{profile} readback"
    if not isinstance(name, str):
        raise ClientError("Recipe name must be text")
    return {"format": RECIPE_FORMAT, "name": name, "settings": recipe_values}


def recipe_check(plan, snapshot, recommendations=None):
    """Compare only requested fields; report unknown and omitted fields explicitly."""
    profile = validate_plan(plan)
    if snapshot.get("profile") != profile:
        raise ClientError("Recipe check requires a snapshot of the destination profile")
    # Reuse the completeness/capability checks used by export before trusting
    # the snapshot's values. No omitted axis may silently become zero.
    snapshot_recipe(snapshot)
    current = snapshot["values"]
    differences, unavailable = [], []
    for setting, requested in plan:
        if setting.label not in current:
            unavailable.append(setting.label)
        elif current[setting.label] != requested:
            differences.append({"setting": setting.label,
                                "current": current[setting.label], "requested": requested})
    requested_labels = {setting.label for setting, _ in plan}
    reasons = []
    if not snapshot["capability"]["hsl1"]:
        reasons.append("Camera does not advertise HSL1; all uploads are refused")
    if snapshot["context"]["bank"] != 0:
        reasons.append("Uploads require PASM bank 0; direct custom-bank loading is unsupported")
    return {"format": "penf-wifi-recipe-check-v1", "profile": profile,
            "network_access": False, "read_only": True,
            "context": snapshot["context"], "capability": snapshot["capability"],
            "matches": not differences and not unavailable,
            "complete_hsl_profile": snapshot["capability"]["hsl1"] and len(plan) == 40,
            "requested_count": len(plan), "compared_count": len(plan) - len(unavailable),
            "unchanged_count": len(plan) - len(unavailable) - len(differences),
            "differences": differences, "unavailable": unavailable,
            "not_requested": sorted(set(current) - requested_labels),
            "can_apply": not reasons, "upload_blockers": reasons,
            "persistent_save_verified": False,
            "recommendations_only": recommendations or {},
            "note": "Compares current readback. Reboot is a manual step; omitted fields are not verified against the recipe."}
