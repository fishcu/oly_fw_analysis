#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Check cmdada's SYSDUMP wrapper against E-M10 I 1.4 native flash READ.

Extracts and assembles the wrapper from a pinned, separately supplied source.
Executes it and the stock READ routine, modeling semaphore, timer and sector I/O.
No camera access, flash writes, real boot dump or installable firmware output.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from penf_boot_emulator import HOOK_RETURN
from penf_emulator import ENGINE, Region
from penf_probe import CALLER, ProbeState

BASE, WRAPPER, STACK, BUFFER = 0x7D991020, 0x19000000, 0x18018000, 0x1A000040
MAIN_SHA = "e2b227662d782a2c75c6c6e872bc34fdfa45d34a9b1b2cee04a4435a00c54f0e"
SOURCE_SHA = "e4b75aec7c99a478840d608b1879789dce7d64f7e9ceb74d5194ea49c8c51f12"
READ, LOCK, UNLOCK, TIMER, SECTORS = 0x7D992410, 0x7D9925C3, 0x7D9925EC, 0x7D996BA7, 0x7D992D6E
SAVED = dict(d2=0x12345678, d3=0x23456789, a2=0x3456789A, a3=0x456789AB)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def assemble(source, assembler, linker):
    require(digest(source) == SOURCE_SHA, "Unexpected SYSDUMP source")
    fragment = source.decode().split("asm(", 1)[1].split("/* n passes", 1)[0]
    lines = [ast.literal_eval(line.strip()) for line in fragment.splitlines() if line.strip()]
    require(all(isinstance(line, str) for line in lines), "Invalid assembly string")
    assembly = "".join(lines)
    require(assembly.startswith("\t.text\n\t.global _fw_read\n_fw_read:\n"), "Wrapper entry moved")
    with tempfile.TemporaryDirectory(prefix="em10-read-probe-") as directory:
        work = Path(directory)
        (work / "wrapper.s").write_text(assembly)
        subprocess.run([str(assembler), "-o", str(work / "wrapper.o"), str(work / "wrapper.s")], check=True)
        subprocess.run([str(linker), "--oformat", "binary", "-Ttext", hex(WRAPPER), "-e", "_fw_read",
                        "-o", str(work / "wrapper.bin"), str(work / "wrapper.o")], check=True)
        return (work / "wrapper.bin").read_bytes()


class Native(ProbeState):
    def __init__(self, image, wrapper, address, size):
        # GCC convention: d0/d1 are the first two arguments; third is at sp+12.
        # CALLS stores a return address without changing sp; the wrapper owns its frame.
        caller = b"\xfc\xff" + struct.pack("<i", WRAPPER - CALLER) + b"\xcb"
        self.regions = [Region("main", BASE, image, "rx"),
                        Region("caller", CALLER, caller, "rx"),
                        Region("wrapper", WRAPPER, wrapper, "rx"),
                        Region("stack", 0x18010000, b"\xa5" * 0x10000, "rw", True),
                        Region("return_trampoline", HOOK_RETURN, b"\xcb" * 8, "rx")]
        self.regs = dict(pc=CALLER, sp=STACK, psw=0, d0=address, d1=BUFFER, **SAVED)
        self.events, self.steps, self.cpu = [], 0, 0
        self.write(STACK + 12, struct.pack("<I", size))
        self.ram("buffer_with_guards", BUFFER - 64, b"\xa5" * (0x10000 + 128))
        self.ram("debug_flag", 0x60000084, bytes(4))
        self.ram("read_log_count", 0xA0A433D0, struct.pack("<I", 100))


def case(image, wrapper, address, size=65536, result=0):
    state = Native(image, wrapper, address, size)
    # Check arguments at the real READ entry before allowing any stock instructions.
    stop = state.run({READ}, limit=100)
    require(stop["status"] == "breakpoint" and state.regs["pc"] == READ, "Wrapper failed to enter READ")
    regs = state.regs
    frame = regs["sp"]
    require((regs["a0"], regs["a1"], regs["d1"], regs["d0"]) == (address, BUFFER, size, 0),
            "Wrong READ arguments")
    require(frame == STACK - 68, "Wrong READ frame")
    require(struct.unpack("<II", state.read(frame + 44, 8)) == (0, 1), "Wrong stack arguments")
    services, calls = [], []
    for _ in range(10):
        stop = state.run({CALLER + 6, LOCK, UNLOCK, TIMER, SECTORS}, limit=500)
        require(stop["status"] == "breakpoint", f"Unexpected native stop: {stop}")
        pc = state.regs["pc"]
        if pc == CALLER + 6:
            break
        services.append(hex(pc))
        regs = state.regs
        if pc == SECTORS:
            calls.append(dict(volume=regs["d0"], sector=regs["d1"], count=regs["a1"], destination=hex(regs["a0"])))
            if result == 0:
                state.write(regs["a0"], b"\x5a" * (512 * regs["a1"]))
        state.return_from_model(result & 0xFFFFFFFF if pc == SECTORS else (123 if pc == TIMER else 0))
    else:
        raise ValueError("READ did not return")
    offset = address & 0x0FFFFFFF
    volume = int(offset >= 0x300000)
    count = (size + 511) // 512
    require(calls == [dict(volume=volume, sector=(offset - volume * 0x300000) // 512,
                           count=count, destination=hex(BUFFER))], "Wrong sector translation")
    require(services == [hex(LOCK), hex(TIMER), hex(SECTORS)] +
            ([hex(TIMER)] if result >= 0 else []) + [hex(UNLOCK)], "Service order or missing unlock")
    require(state.regs["d0"] == (result & 0xFFFF), "Wrong returned error/status")
    require(state.regs["sp"] == STACK, "Stack not restored")
    require(all(state.regs[key] == value for key, value in SAVED.items()), "Saved register damaged")
    require(state.read(BUFFER - 64, 64) == b"\xa5" * 64 and
            state.read(BUFFER + 65536, 64) == b"\xa5" * 64, "Buffer guard damaged")
    expected = (b"\x5a" * (count * 512) + b"\xa5" * (65536 - count * 512)
                if result == 0 else b"\xa5" * 65536)
    require(state.read(BUFFER, 65536) == expected, "Unexpected modeled buffer content")
    return dict(logical_address=hex(address), requested_bytes=size, sector_calls=calls,
                modeled_sector_result=result, returned_status=state.regs["d0"], services=services,
                stock_entry_arguments_verified=True, stack_and_registers_restored=True,
                buffer_guards_intact=True, steps=state.steps)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-main", required=True, type=Path)
    parser.add_argument("--upstream", required=True, type=Path)
    parser.add_argument("--assembler", required=True, type=Path)
    parser.add_argument("--linker", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    require(not args.out.exists(), "Choose a new output file")
    image = args.stock_main.read_bytes()
    require(digest(image) == MAIN_SHA, "Unexpected E-M10 I 1.4 main payload")
    source = (args.upstream / "plugins/sysdump/sysdump.c").read_bytes()
    wrapper = assemble(source, args.assembler.resolve(), args.linker.resolve())
    rows = [case(image, wrapper, address) for address in (0x40000000, 0x40020000, 0x402F0000, 0x40300000, 0x44600000)]
    rows += [case(image, wrapper, address, result=-5) for address in (0x40000000, 0x40300000)]
    rows += [case(image, wrapper, 0x40000000, size=size) for size in (512, 513)]
    report = dict(main_sha256=MAIN_SHA, upstream_source_sha256=SOURCE_SHA,
                  wrapper_sha256=digest(wrapper), wrapper_bytes=len(wrapper), source_sha256=digest(Path(__file__).read_bytes()),
                  engine_sha256=digest(ENGINE.read_bytes()), cases=rows,
                  toolchain={"assembler_sha256": digest(args.assembler.read_bytes()),
                             "linker_sha256": digest(args.linker.read_bytes())}, limits=[
        "Assembles only the supplied inline wrapper, not the complete plugin or compiler-generated caller.",
        "Synthetic GCC-style caller and RAM. Native wrapper and stock READ run; semaphore, timer and sector I/O are modeled.",
        "Flash debugging disabled and log counter saturated. No file operation, producer, DMA or camera is executed.",
        "Dummy successful sector data is 5A; this is not a bootloader dump or hardware read validation.",
        "513-byte case deliberately has 64 KiB backing: stock READ rounds up to sectors, so an exact-size buffer would be insufficient.",
    ])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(dict(passed=True, cases=len(rows), wrapper_bytes=len(wrapper), output=str(args.out))))


if __name__ == "__main__":
    main()
