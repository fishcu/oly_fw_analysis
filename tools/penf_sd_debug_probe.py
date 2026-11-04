#!/usr/bin/env python3
"""Verify PEN-F stock SD parameter parsing and Wi-Fi debug startup offline.

Runs native CSV parsing, RAM overlay installation/getter, startup selection and
listener construction. File discovery, scheduling and network I/O are separate
boundaries. Does not contact a camera or produce an installable firmware image.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from penf_emulator import ENGINE
from penf_landmarks import MAIN_SHA256
from penf_probe import BUFFER, CALLER, ProbeState

CONTEXT, SCRATCH = 0x20001000, 0x20002000
RECORDS, INDEX = 0x61AC7AC0, 0xA1C281E0
OVERLAY = INDEX + 0x8004
SAVED = dict(d2=0x12345678, d3=0x23456789, a2=0x3456789A, a3=0x456789AB)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def invoke(state, target, mask, frame, registers=None, models=None, stop=None):
    state.write(CALLER, b"\xdd" + struct.pack("<i", target - CALLER) + bytes((mask, frame)) + b"\xcb")
    state.regs.update(pc=CALLER, sp=0x18018000, **(registers or {}))
    boundaries = models or {}
    services = []
    for _ in range(256):
        result = state.run({stop or CALLER + 7, *boundaries}, limit=100000)
        require(result["status"] == "breakpoint", f"Unexpected stop in {target:#x}: {result}")
        pc = state.regs["pc"]
        if pc == (stop or CALLER + 7):
            if stop is None:
                require(state.regs["sp"] == 0x18018000, f"Stack not restored by {target:#x}")
            return services
        services.append(hex(pc))
        boundaries[pc](state)
    raise ValueError("Too many modeled services")


def fixture():
    state = ProbeState(0x60073802, 0xF0, 36, bytes(512), {})
    context = bytearray(64)
    struct.pack_into("<II", context, 36, RECORDS, 131068)
    state.ram("csv_context", CONTEXT, context)
    state.ram("csv_scratch", SCRATCH, bytes(16384))
    state.ram("csv_records", RECORDS, bytes(131072))
    state.ram("parameter_indices", INDEX, bytes(0x10004))
    state.ram("cpu_number", 0x8050, bytes(4))
    state.ram("debug_log_mode", 0xA1C552C8, b"\0")
    # A normal base entry prevents an unrelated debug-parameter diagnostic.
    state.ram("base_record", 0x20008000, bytes(8))
    state.write(INDEX + 4 + (0x7B64 >> 4) * 8, struct.pack("<HHI", 0x7B64, 1, 0x20008000))
    return state


def parse_line(state, line):
    require(len(line) < 512, "Fixture line too long")
    state.write(BUFFER, line + bytes(512 - len(line)))
    invoke(state, 0x60073802, 0xF0, 36,
           dict(a0=CONTEXT, a1=BUFFER, d0=SCRATCH, **SAVED))
    require(all(state.regs[k] == v for k, v in SAVED.items()), "CSV callee-saved registers changed")


def get(state, key):
    invoke(state, 0x600750EE, 0xC0, 12, dict(d0=key, d1=0, a0=0))
    return state.regs["d0"]


def csv_case(name, lines, expected, log_mode=0, delayed_ready=False, strobe_refresh=False):
    state = fixture()
    for line in lines:
        parse_line(state, line.encode("ascii"))
    record_bytes = struct.unpack("<I", state.read(CONTEXT + 36, 4))[0] - RECORDS
    records = state.read(RECORDS, record_bytes + 4).hex()
    invoke(state, 0x600745A1, 0x20, 8)
    require(get(state, 0xF971) == expected, f"{name}: wrong overlay value")
    require(get(state, 0xF981) == log_mode, f"{name}: wrong log overlay")
    checks = []
    # Synthetic parameter IDs isolate the native 106-entry pointer refresh.
    cache = b"".join(struct.pack("<HHI", 0x1004 + 16 * i, 1, 0) for i in range(106))
    state.ram("strobe_parameter_cache", 0x615FD4F8, cache)
    pointer_requests = []
    def parameter_pointer(s):
        key = s.regs["d0"]
        require(key == 0x1004 + 16 * len(pointer_requests), "Wrong strobe-cache order")
        pointer_requests.append(key)
        s.return_from_model(0)
        s.regs["a0"] = 0x21000000 + 4 * (len(pointer_requests) - 1)
    def readiness(s):
        checks.append(s.regs["d0"])
        s.return_from_model(0 if delayed_ready and len(checks) == 1 else 1)
    def success(s):
        s.return_from_model(0)
    calls = invoke(state, 0x6007439B, 0, 0, models={
        0x6004204B: readiness, 0x60069927: success,
        0x60AAA6DC: success, 0x60AAA71C: success,
        0x600750C4: parameter_pointer,
    })
    require(calls.count(hex(0x60AAA71C)) == int(expected != 0), f"{name}: boot switch mismatch")
    require(all(x == 6 for x in checks), "Unexpected readiness identifier")
    require(state.read(0xA1C552C8, 1) == bytes([log_mode]), "Diagnostic log mode not applied")
    require(calls.count(hex(0x60069927)) == int(delayed_ready and expected != 0), "Readiness wait mismatch")
    require(len(pointer_requests) == (106 if strobe_refresh else 0), "Strobe-cache refresh mismatch")
    for i in range(len(pointer_requests)):
        require(struct.unpack("<I", state.read(0x615FD4F8 + 8 * i + 4, 4))[0] == 0x21000000 + 4 * i,
                "Native strobe cache did not store resolved pointer")
    invoke(state, 0x600745D2, 0, 0)
    require(get(state, 0xF971) == 0 and get(state, 0xF981) == 0, "Native overlay clear failed")
    return dict(name=name, lines=lines, record_hex=records, parsed_value=expected,
                log_mode=log_mode, startup_services=calls, native_overlay_clear_returns_defaults=True,
                strobe_cache_pointer_refreshes=len(pointer_requests),
                steps=state.steps)


def log_case(mode, cursor, expected_cursor, expected_writes, prior_mode=0):
    state = fixture()
    state.ram("diagnostic_buffer_and_cursor", 0xA1C532C0, b"\xa5" * 8192 + struct.pack("<II", cursor, 0))
    state.ram("diagnostic_capture_guard", 0xA1C552C9, b"\0")
    # Suppress serial output so only the native RAM-capture branch executes.
    state.ram("serial_output_controls", 0x615FC816, struct.pack("<HH", 1, 0))
    state.write(0xA1C552C8, bytes([prior_mode]))
    state.write(BUFFER, b"ABCD\0")
    invoke(state, 0x6002302A, 0, 0, dict(d0=mode))
    actual_mode = mode if mode in (0, 1, 2) else prior_mode
    require(state.read(0xA1C552C8, 1) == bytes([actual_mode]), "Log mode selector mismatch")
    def interrupt_service(s):
        s.return_from_model(0)
    calls = invoke(state, 0x600230A7, 0xF0, 36, dict(a0=BUFFER, **SAVED), models={
        0x60086C0B: interrupt_service, 0x60086C54: interrupt_service,
    })
    expected = bytearray(b"\xa5" * 8192)
    for offset, byte in expected_writes:
        expected[offset] = byte
    require(state.read(0xA1C532C0, 8192) == expected, "Unexpected diagnostic buffer contents")
    require(struct.unpack("<I", state.read(0xA1C552C0, 4))[0] == expected_cursor,
            "Diagnostic cursor mismatch")
    require(all(state.regs[k] == v for k, v in SAVED.items()), "Logger callee-saved registers changed")
    return dict(name=f"native_log_mode_{mode}_cursor_{cursor}", requested_mode=mode,
                actual_mode=actual_mode, prior_mode=prior_mode, initial_cursor=cursor,
                final_cursor=expected_cursor, modified_bytes=len(expected_writes),
                modeled_calls=calls, steps=state.steps)


def listener_case():
    state = fixture()
    state.write(0x8050, struct.pack("<I", 1))
    state.ram("wifi_state", 0xA1C8AD4C, bytes(0x100))
    state.ram("allocated_shell_buffer", 0x20010000, bytes(16384))
    observations = []
    def allocate(s):
        require(s.regs["d0"] == 16384, "Unexpected shell allocation")
        s.return_from_model(0)
        s.regs["a0"] = 0x20010000
    def socket(s):
        require((s.regs["d0"], s.regs["d1"], s.regs["a0"]) == (2, 1, 0), "Not AF_INET/SOCK_STREAM")
        observations.append(dict(service="socket", family=2, type=1, protocol=0))
        s.return_from_model(42)
    def bind(s):
        data = s.read(s.regs["a0"], 16)
        require(s.regs["d0"] == 42 and s.regs["d1"] == 16, "Bind arguments")
        require(data[:8] == bytes.fromhex("0200001700000000"), "Bind address/port")
        observations.append(dict(service="bind", port=23, address="0.0.0.0"))
        s.return_from_model(0)
    def listen(s):
        require((s.regs["d0"], s.regs["d1"]) == (42, 1), "Listen arguments")
        observations.append(dict(service="listen", backlog=1))
        s.return_from_model(0)
    def create_task(s):
        request = s.read(s.regs["a0"], 24)
        entry = struct.unpack_from("<I", request, 8)[0]
        require(entry == 0x60AAA5D5, "Unexpected accept task")
        observations.append(dict(service="task_create", entry=hex(entry)))
        s.return_from_model(100)
    calls = invoke(state, 0x60AAA820, 0x80, 48, models={
        0x60023459: allocate, 0x60A828E9: socket, 0x60A82963: bind,
        0x60A82A8A: listen, 0x600306D3: create_task,
    })
    return dict(name="native_listener_construction", observations=observations,
                modeled_calls=calls, steps=state.steps)


def command_bridge_case():
    state = fixture()
    state.write(BUFFER, b"help\0" + bytes(251))
    observations = []
    def send_message(s):
        require(s.regs["d0"] == 0xCE and s.regs["d1"] == 256 and s.regs["a1"] == 1000,
                "Unexpected shell message-buffer arguments")
        require(s.regs["a0"] == BUFFER and s.read(BUFFER, 5) == b"help\0", "Line pointer changed")
        observations.append(dict(service="send_message_buffer", object_id=hex(s.regs["d0"]),
                                 bytes=s.regs["d1"], timeout=s.regs["a1"], fixture_line="help"))
        s.return_from_model(0)
    calls = invoke(state, 0x60AAA8D3, 0, 0, dict(a0=BUFFER), models={0x60037DCB: send_message})
    return dict(name="native_line_to_user_shell_queue", observations=observations,
                modeled_calls=calls, steps=state.steps)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    require(not args.out.exists(), "Choose a new output file")
    cases = [csv_case("reported_line", ["Wifi shell,0xF971,1,1"], 1),
             csv_case("line_feed", ["Wifi shell,0xF971,1,1\n"], 1),
             csv_case("crlf", ["Wifi shell,0xF971,1,1\r\n"], 1),
             csv_case("label_is_not_the_key", ["Another label,0xF971,1,1"], 1),
             csv_case("decimal_key", ["Wifi shell,63857,1,1"], 1),
             csv_case("disabled", ["Wifi shell,0xF971,1,0"], 0),
             csv_case("missing_key", [], 0),
             csv_case("wait_for_ready", ["Wifi shell,0xF971,1,1"], 1, delayed_ready=True),
             csv_case("separate_log_mode", ["Wifi shell,0xF971,1,1", "Log,0xF981,1,2"], 1, log_mode=2),
             listener_case(), command_bridge_case(),
             csv_case("strobe_refresh_bit_set", ["Strobe refresh,0x7B64,1,0x80000000"], 0, strobe_refresh=True),
             csv_case("strobe_refresh_other_bit", ["Strobe refresh,0x7B64,1,1"], 0),
             log_case(0, 0, 0, []),
             log_case(1, 0, 4, list(enumerate(b"ABCD"))),
             log_case(1, 8190, 8190, []),
             log_case(2, 0, 4, list(enumerate(b"ABCD"))),
             log_case(2, 8190, 2, [((8190 + i) & 8191, byte) for i, byte in enumerate(b"ABCD")]),
             log_case(3, 0, 4, list(enumerate(b"ABCD")), prior_mode=1)]
    report = dict(main_sha256=MAIN_SHA256, source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  engine_sha256=hashlib.sha256(ENGINE.read_bytes()).hexdigest(), cases=cases, limits=[
        "CSV parser, overlay installer/getter/clear and boot selector run native instructions with synthetic RAM.",
        "File discovery and line delivery are not replayed; each line is supplied directly to the native parser.",
        "Startup readiness/sleep and Wi-Fi initializer/start are modeled; no full boot or radio operation.",
        "Listener construction executes separately on modeled CPU1 with allocator/socket/bind/listen/task services replaced.",
        "Command bridge records its message-buffer send; U_SHELL dispatch and help execution are not run.",
        "Native overlay clear is not a power-cycle or hot-removal test; no flash writes or full persistence trace.",
        "7B64 native pointer refresh uses 106 synthetic strobe parameter IDs and modeled pointer resolution.",
        "F981 native RAM capture uses synthetic buffer/cursor; serial suppressed, interrupt services modeled.",
        "No TCP connection, authentication handshake, shell command, camera I/O or physical test is performed.",
    ])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(dict(passed=True, cases=len(cases), output=str(args.out))))


if __name__ == "__main__":
    main()
