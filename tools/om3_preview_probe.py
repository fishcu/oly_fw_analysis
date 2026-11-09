#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Execute V22's OM-3 preview wrapper and descriptor reader with modeled I/O.

No camera connection or firmware output. The real producer and USB sender are
not executed, so this checks validation and bookkeeping, not frame delivery.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from om3_tethering_probe import Native, PINS, require
from penf_emulator import ENGINE
from penf_probe import CALLER

RING, READY, ENABLE = 0xA320FD28, 0xA320FDA0, 0xA320FC98
RESPONSE = 0x19000000
BUFFERS = (0xB6E5C000, 0xB6E81800, 0xB6EA7000)
LOCK, UNLOCK, COPY, SEND = 0x6031EB00, 0x6031EB08, 0x50002909, 0x618D092A
SAVED = dict(d2=0x12345678, d3=0x23456789, a2=0x3456789A, a3=0x456789AB)


def case(image, name, *, selected=0, pointer=None, length=100, status=1,
         ready=1, enabled=1, soi=0xD8FF, sender_result=0, rejection=0):
    pointer = BUFFERS[selected] if pointer is None else pointer
    state = Native(image, 0x6031E920, a1=RESPONSE, **SAVED)
    state.ram("response", RESPONSE, bytes(64))
    state.ram("enable", ENABLE, struct.pack("<H", enabled))
    ring = bytearray(120)
    for index in range(3):
        struct.pack_into("<H2xIII", ring, 40 * index, int(index == selected),
                         pointer if index == selected else BUFFERS[index], length, status)
    state.ram("ring", RING, ring)
    state.ram("ready", READY, struct.pack("<H", ready))
    # Only the SOI halfword is mapped. No JPEG payload is consumed by the model.
    for index, address in enumerate(BUFFERS):
        state.ram(f"jpeg{index}", address, struct.pack("<H", soi))
    services, copies, sends = [], [], []
    for _ in range(10):
        result = state.run({CALLER + 7, LOCK, UNLOCK, COPY, SEND}, limit=1000)
        require(result["status"] == "breakpoint", f"{name}: unexpected stop {result}")
        pc = state.regs["pc"]
        if pc == CALLER + 7:
            break
        regs = state.regs
        services.append(hex(pc))
        if pc == COPY:
            copies.append(dict(source=hex(regs["a1"]), destination=hex(regs["a0"]), bytes=regs["d0"]))
            require(regs["d0"] == 40, "Unexpected descriptor copy size")
            state.write(regs["a0"], state.read(regs["a1"], regs["d0"]))
        if pc == SEND:
            sends.append(dict(buffer=hex(regs["a0"]), length=regs["d0"],
                              total=regs["d1"], modeled_result=sender_result))
        state.return_from_model(sender_result & 0xFFFFFFFF if pc == SEND else 0)
    else:
        raise ValueError(f"{name}: no return")
    response = state.read(RESPONSE, 64)
    code = struct.unpack_from("<H", response)[0]
    detail = struct.unpack_from("<I", response, 16)[0]
    require(code == (0x200F if rejection else 0x2001), f"{name}: response code {code:#x}")
    require(detail == (0xD7000000 + rejection if rejection else 1), f"{name}: response detail")
    require(bool(sends) == (not rejection), f"{name}: unexpected send decision")
    require(state.regs["sp"] == 0x18018000, f"{name}: stack not restored")
    require(all(state.regs[key] == value for key, value in SAVED.items()), f"{name}: saved registers")
    require(state.regs["d0"] == 0, f"{name}: wrapper return")
    require(services == ([] if not enabled else
                        [hex(LOCK), hex(COPY), hex(UNLOCK)] + ([hex(SEND)] if sends else [])),
            f"{name}: service order")
    after_ring = state.read(RING, 120)
    after_states = [struct.unpack_from("<H", after_ring, 40 * i)[0] for i in range(3)]
    after_ready = struct.unpack("<H", state.read(READY, 2))[0]
    expected_states = [int(i == selected) for i in range(3)]
    if enabled and ready == 1:
        expected_states[selected] = 0
        expected_states[next(i for i in range(3) if i != selected)] = 1
    require(after_states == expected_states, f"{name}: descriptor states")
    require(after_ready == (0 if enabled and ready == 1 else ready), f"{name}: ready flag")
    if sends:
        require((sends[0]["buffer"], sends[0]["length"], sends[0]["total"]) ==
                (hex(pointer), length, length), f"{name}: sender arguments")
    return dict(name=name, input=dict(selected=selected, pointer=hex(pointer), length=length,
                                     status=status, ready=ready, enabled=enabled, soi=hex(soi)),
                response=hex(code), detail=hex(detail), services=services, copies=copies, sends=sends,
                ring_states_after=after_states, ready_after=after_ready,
                stack_and_saved_registers_restored=True, steps=state.steps)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patched-main", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    require(not args.out.exists(), "Choose a new output file")
    image = args.patched_main.read_bytes()
    require(hashlib.sha256(image).hexdigest() == PINS["v22"], "Unexpected V22 payload")
    rows = [case(image, f"ring-{i}-length-{length}", selected=i, length=length)
            for i in range(3) for length in (2, 100, 153600)]
    for name, kwargs in (
        ("disabled", dict(enabled=0, rejection=1)),
        ("descriptor-not-valid", dict(status=0, rejection=2)),
        ("zero-length", dict(length=0, rejection=3)),
        ("one-byte", dict(length=1, rejection=3)),
        ("too-large", dict(length=153601, rejection=4)),
        ("unsigned-large", dict(length=0xFFFFFFFF, rejection=4)),
        ("unmapped-pointer", dict(pointer=0x12340000, rejection=5)),
        ("bad-soi", dict(soi=0, rejection=6)),
        ("not-ready", dict(ready=0, rejection=3)),
        ("sender-error", dict(sender_result=-1)),
    ):
        rows.append(case(image, name, **kwargs))
    report = dict(main_sha256=PINS["v22"], source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  engine_sha256=hashlib.sha256(ENGINE.read_bytes()).hexdigest(), cases=rows, limits=[
        "Wrapper 6031e920 and descriptor reader 6031ea20 execute natively, with synthetic RAM and stack.",
        "Mutex trampolines return success, memcpy copies the specified descriptor, and USB sender only records arguments.",
        "No producer, DMA, competing task, USB phase, data transfer or physical camera is executed.",
        "Only ring states with exactly one selected descriptor and at least one free descriptor are supplied.",
        "Only the two-byte JPEG SOI is mapped; successful validation does not prove a decodable JPEG.",
    ])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(dict(passed=True, cases=len(rows), output=str(args.out))))


if __name__ == "__main__":
    main()
