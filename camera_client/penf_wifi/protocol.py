# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Bounded PEN-F setting names and the offline HSL1 prototype protocol.

The native IDs are pinned in parameter-coverage.json, with the HSL1 wire
format in analysis/penf_wifi_recipe_20261015. No arbitrary-ID write API.
"""
from dataclasses import dataclass
import json
import re
import xml.etree.ElementTree as ET

CAPABILITY = 0x48534C31
UNAVAILABLE = 0x80000000
RECIPE_FORMAT = "penf-color-recipe-v1"
AXES = {"saturation": 0, "hue": 1, "lightness": 2}
TONES = {"highlights": 0, "midtones": 1, "shadows": 2}


class ClientError(Exception):
    """Expected failure; the CLI reports this without a traceback."""


def integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ClientError(f"{name} must be an integer in {low}..{high}; got {value!r}")
    return value


def xml_root(body):
    # No DTD/entity processing, including UTF-16 encoded documents.
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise ClientError("Camera returned non-UTF-8 XML") from e
    if re.search(r"<!\s*(DOCTYPE|ENTITY)", text, re.I):
        raise ClientError("DTD/entity declarations are not accepted")
    try:
        return ET.fromstring(text)
    except ET.ParseError as e:
        raise ClientError(f"Malformed XML response: {e}") from e


def named(root, tag):
    return [x for x in root.iter() if x.tag.rsplit("}", 1)[-1] == tag]


def scalar(body):
    root = xml_root(body)
    values = named(root, "value")
    if root.tag.rsplit("}", 1)[-1] != "response" or len(values) != 1:
        raise ClientError("Expected one <response><value> hexadecimal word")
    text = (values[0].text or "").strip()
    if not re.fullmatch(r"[0-9A-Fa-f]{1,8}", text):
        raise ClientError(f"Invalid hexadecimal response value {text!r}")
    return int(text, 16)


def signed(word):
    return word if word < 0x80000000 else word - 0x100000000


@dataclass(frozen=True)
class Setting:
    profile: int
    name: str
    sector: int | None = None

    def __post_init__(self):
        integer(self.profile, 1, 3, "COLOR profile")
        if self.name in AXES:
            integer(self.sector, 0, 11, "sector (zero-based)")
        elif self.name in ("contrast", *TONES):
            if self.sector is not None:
                raise ClientError(f"{self.name} does not take a sector")
        else:
            raise ClientError(f"Unsupported upload setting {self.name!r}; WB offsets are not qualified yet")

    @property
    def key(self):
        if self.name in AXES:
            return 931 + (self.profile - 1) * 12 + self.sector
        if self.name == "contrast":
            return 915 + self.profile
        return 967 + (self.profile - 1) * 3 + TONES[self.name]

    @property
    def axis(self):
        return AXES.get(self.name, 0)

    @property
    def label(self):
        return self.name + (f"[{self.sector}]" if self.sector is not None else "")

    @property
    def read_mode(self):
        return self.key | {0: 0, 1: 0x8000, 2: 0xC000}[self.axis]

    def validate(self, value):
        n = 2 if self.name == "contrast" else 7
        return integer(value, -n, n, self.label)

    def write_params(self, value):
        value = self.validate(value)
        return {"mode": f"{self.key:04X}",
                "value": f"{((0x4850 + self.axis) << 16) | (value & 0xffff):08X}"}


def profile_settings(profile, extended):
    names = ("saturation", "hue", "lightness") if extended else ("saturation",)
    return [Setting(profile, name, i) for name in names for i in range(12)] + [
        Setting(profile, name) for name in ("contrast", *TONES)]


def reject_duplicate_keys(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ClientError(f"Duplicate JSON key {key!r}")
        result[key] = value
    return result


def reject_json_constant(value):
    raise ClientError(f"Invalid JSON number {value}")


def load_json(text, description="JSON"):
    try:
        return json.loads(text, object_pairs_hook=reject_duplicate_keys,
                          parse_constant=reject_json_constant)
    except (ValueError, TypeError) as e:
        raise ClientError(f"Invalid {description}: {e}") from e


def recipe_plan(text, profile):
    integer(profile, 1, 3, "COLOR profile")
    obj = load_json(text, "recipe JSON")
    if not isinstance(obj, dict) or obj.get("format") != RECIPE_FORMAT:
        raise ClientError(f"Expected recipe format {RECIPE_FORMAT}")
    if set(obj) - {"format", "name", "settings", "recommendations"}:
        raise ClientError("Unknown recipe fields; no settings are silently discarded")
    if "name" in obj and not isinstance(obj["name"], str):
        raise ClientError("Recipe name must be text")
    recommendations = obj.get("recommendations", {})
    if (not isinstance(recommendations, dict) or
            set(recommendations) - {"white_balance", "exposure_compensation"} or
            any(not isinstance(v, str) for v in recommendations.values())):
        raise ClientError("Recommendations allow only text white_balance and exposure_compensation")
    values = obj.get("settings")
    if not isinstance(values, dict) or not values:
        raise ClientError("Recipe settings must be a nonempty object")
    plan = []
    for name, value in values.items():
        if name in AXES:
            if not isinstance(value, list) or len(value) != 12:
                raise ClientError(f"{name} must contain exactly twelve values, in sector order 0..11")
            for sector, v in enumerate(value):
                setting = Setting(profile, name, sector)
                plan.append((setting, setting.validate(v)))
        else:
            # Includes rejection of WB mode, WB offsets, EV and Kelvin.
            setting = Setting(profile, name)
            plan.append((setting, setting.validate(value)))
    return plan, recommendations


def validate_plan(plan):
    """Validate an entire named-setting plan before any camera request."""
    if not plan:
        raise ClientError("Empty upload plan")
    if not isinstance(plan[0][0], Setting):
        raise ClientError("Upload requires named COLOR settings")
    profile = plan[0][0].profile
    seen = set()
    for setting, value in plan:
        if not isinstance(setting, Setting) or setting.profile != profile or setting.label in seen:
            raise ClientError("Upload must contain distinct settings for one COLOR profile")
        setting.validate(value)
        seen.add(setting.label)
    return profile


def describe_plan(plan, recommendations=None):
    return {"format": "penf-wifi-plan-v1", "network_access": False,
            "profile": plan[0][0].profile,
            "changes": [{"setting": s.label, "value": v, "wire": s.write_params(v)} for s, v in plan],
            "recommendations_only": recommendations or {}}
