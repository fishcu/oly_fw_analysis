#!/usr/bin/env python3
"""Check OM-3 1.1/V22 USB selector claims with bounded native execution.

Inputs are decoded MAIN payloads, not complete containers. No camera access,
patch generation, USB traffic or firmware writing. See the output's model limits.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from penf_boot_emulator import HOOK_RETURN
from penf_emulator import ENGINE, Region
from penf_probe import CALLER, ProbeState

BASE = 0x60021020
PINS = {
    "stock": "5e8d376e9111a44ac0352f26030d7c1b17026d42c45f3600cfa02a0e8c5b7d59",
    "v22": "2fa0238100f8072b449b8722ef03069975e2a0180443ea338bd50f08a0e79f49",
}
TRACE = {0x6040D4B7, 0x6040D51A}


def require(ok, message):
    if not ok:
        raise ValueError(message)


class Native(ProbeState):
    """Use the common runner without loading any PEN-F firmware or fixtures."""
    def __init__(self, image, target, mask=0, frame=0, *, direct=False, **regs):
        caller = b"\xdd" + struct.pack("<i", target - CALLER) + bytes((mask, frame)) + b"\xcb"
        self.regions = [
            Region("main", BASE, image, "rx"),
            Region("caller", CALLER, caller, "rx"),
            Region("stack", 0x18010000, bytes(0x10000), "rw", True),
            Region("return_trampoline", HOOK_RETURN, b"\xcb" * 8, "rx"),
        ]
        self.regs = dict(pc=target if direct else CALLER, sp=0x18018000, psw=0, **regs)
        self.events, self.steps, self.cpu = [], 0, 0


def until(state, stop, models=()):
    modeled = []
    for _ in range(12):
        result = state.run({stop, *models}, limit=300)
        require(result["status"] == "breakpoint", f"Unexpected stop: {result}")
        pc = state.regs["pc"]
        if pc == stop:
            return {"stop": hex(stop), "steps": state.steps, "modeled_calls": modeled}
        require(pc in models, "Unexpected service")
        modeled.append(hex(pc))
        state.return_from_model(0)
    raise ValueError("Too many modeled calls")


def audit(image, label):
    rows = []
    # Full predicates and real selector/status query; only trace output omitted.
    for gate, target, mask, frame, wanted in (
        ("0084", 0x60C1C42F, 0x80, 12, 11),
        ("0022-enable", 0x60C18D67, 0xA0, 16, 10),
    ):
        for api in (9, 10, 11, 12):
            for status in (0, 1):
                state = Native(image, target, mask, frame, d0=1)
                state.ram("stored_api", 0x62A884EE, bytes([api]))
                state.ram("query_status", 0x6035FBEC, struct.pack("<H", status))
                detail = until(state, CALLER + 7, TRACE)
                got = state.regs["d0"]
                require(got == int(api == wanted and status == 0), f"{gate} mismatch")
                require(state.regs["sp"] == 0x18018000, "Predicate stack not restored")
                rows.append(dict(kind="predicate", gate=gate, api=api, status=status,
                                 accepted=bool(got), stack_restored=True, **detail))
    # Stop before any external application services, using only the native mapping.
    for app, expected in ((10, 7), (12, 8)):
        state = Native(image, 0x6108E36D, direct=True, d0=app)
        detail = until(state, 0x6108E38E)
        require(state.regs["d2"] == expected, "Application/kind map mismatch")
        rows.append(dict(kind="application_to_connect", application=app,
                         connect_kind=expected, **detail))
    for kind, expected in ((7, 10), (8, 11)):
        state = Native(image, 0x60B0630D, direct=True, d0=kind, d1=0, a0=0, a1=0)
        detail = until(state, 0x60B0634A)
        require(state.regs["d2"] == expected, "Connect/API map mismatch")
        rows.append(dict(kind="connect_to_api", connect_kind=kind, selected_api=expected, **detail))
    # API-to-transport switch; mode-setup service is explicitly modeled, not run.
    for api in (10, 11):
        state = Native(image, 0x60408FDD, direct=True, d3=0)
        state.write(0x18018000 + 28, bytes([api]))
        detail = until(state, 0x60409098, {0x6040D103})
        expected = 11 if api == 10 or label == "v22" else 12
        require(state.regs["d3"] == expected, "API/transport mismatch")
        rows.append(dict(kind="api_to_transport", api=api, transport=expected, **detail))
    # Post-query D052 branch; this does not execute event delivery or the ack wait.
    for transport in (11, 12):
        state = Native(image, 0x618C3118, direct=True, d0=transport)
        detail = until(state, 0x618C313F)
        expected = 0x041B0084 if transport == (11 if label == "v22" else 12) else 0x041B0022
        require(state.regs["d2"] == expected, "D052 event mismatch")
        rows.append(dict(kind="enable_event", transport=transport, event=hex(expected), **detail))
    state = Native(image, 0x612BDE8B, direct=True, d0=3)
    detail = until(state, 0x612BDF54)
    expected = 27 if label == "v22" else 26
    require((state.regs["d0"], state.regs["d1"]) == (26, expected), "Popup mismatch")
    rows.append(dict(kind="popup_index3", gui_event=26, action=expected, **detail))
    for action, expected in ((19, 3), (26, 10), (27, 12)):
        state = Native(image, 0x6109AF7C, direct=True, d2=action, d3=0)
        detail = until(state, 0x6109AFF4)
        require(state.regs["d0"] == expected, "GUI action/application map mismatch")
        rows.append(dict(kind="action_to_application", action=action, application=expected, **detail))
    # Start after setting 82's getter, supplying its saved RAW value (10).
    state = Native(image, 0x6108E2B6, direct=True, d0=10)
    detail = until(state, 0x6108E30F)
    expected = 12 if label == "v22" else 10
    require(state.regs["d0"] == expected, "Persistent RAW operand mismatch")
    rows.append(dict(kind="persistent_raw_branch", setting_value=10, application=expected, **detail))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-main", required=True, type=Path)
    parser.add_argument("--patched-main", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    require(not args.out.exists(), "Choose a new output file")
    report = {"main_runtime_base": hex(BASE), "inputs": {}, "cases": {},
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "engine_sha256": hashlib.sha256(ENGINE.read_bytes()).hexdigest(),
        "limits": [
            "No connected boot, event queue, physical camera, USB stack or captured-image transfer is executed.",
            "Synthetic caller/stack and explicit API/status RAM. Two trace services return success without running.",
            "API-to-transport slice models 6040d103 mode setup returning success; stored API installation is not tested.",
            "Other slices stop at exact boundaries before external services; they are not whole-function execution.",
            "0022 is tested for enable input d0=1, not its distinct disable/fallback branches.",
        ]}
    images = {}
    for label, path in (("stock", args.stock_main), ("v22", args.patched_main)):
        image = path.read_bytes()
        sha = hashlib.sha256(image).hexdigest()
        require(sha == PINS[label], f"Unexpected {label} main payload")
        report["inputs"][label] = {"sha256": sha, "bytes": len(image)}
        images[label] = image
        report["cases"][label] = audit(image, label)
    table = list(struct.unpack_from("<9I", images["stock"], 0x60E0A9DC - BASE))
    require(table[6:8] == [0x60B06336, 0x60B0633E], "Mapping table targets")
    report["connect_table"] = {"address": "0x60e0a9dc", "function": "0x60b0630d",
                               "targets": [hex(t) for t in table]}
    report["persistent_edit"] = {"instruction_runtime": "0x6108e2fd", "changed_byte_runtime": "0x6108e2fe",
        "instruction_decoded_container_offset": "0x0106d2fd", "changed_byte_decoded_container_offset": "0x0106d2fe",
        "stock": images["stock"][0x6108E2FD-BASE:0x6108E2FF-BASE].hex(),
        "v22": images["v22"][0x6108E2FD-BASE:0x6108E2FF-BASE].hex()}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"cases": sum(map(len, report["cases"].values())), "passed": True, "output": str(args.out)}))


if __name__ == "__main__":
    main()
