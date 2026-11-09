#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Generate exact-build PEN-F 3101 research landmarks and bounded disassembly.

Literal matches and opcode-pattern matches are candidates, not semantic xrefs.
The 0x60021020 mapping is supported by the historical author and multiple local
string references. It must not be generalized to other blocks or firmwares.
"""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess

from oly_container import sha256

MAIN_SHA256 = "a2eb1d1f1afe47cce148e9aae0a04dfb82547d9de9437d342e012341140913f4"
BASE = 0x60021020
COLOR_TABLE_ADDRESS = 0x60622d74
COLOR_TABLE_SIZE = 3028
SEEDS = (
    "disp_set_color_creator_param usShade  ",
    "disp_set_color_creator2_param vivid No ",
    "chColorCreator2Saturation[0]  ",
    "ColorCreator2Saturation[0]     ",
    "mode_color_creator_2_vivid[0] ",
    "startVersionCheckMenuSubAppStateMisc",
    "Maintenance::getSystemVersion",
    "API_VERSION_USER          ",
    "E122????BIN",
)
WINDOWS = {
    # Boundary at 0x602fc370 follows a return; the loop is internally consistent.
    "color_creator2_conversion": (0x602FC370, 0x602FC619),
    # Known string ref; context includes the structure offset for twelve bytes.
    "color_creator2_debug_fields": (0x6111260F, 0x61112721),
    # Boundary follows a return; string establishes association, not display code.
    "version_menu_event": (0x60BB12E7, 0x60BB130F),
    "version_diagnostic_command": (0x60719470, 0x607194F0),
    "maintenance_object": (0x606F80CE, 0x606F8138),
    "version_api_wrapper": (0x606F86CC, 0x606F873E),
    "version_api_dispatch": (0x6075EDAB, 0x6075EEC0),
    "device_information_getter": (0x60310FAF, 0x6031112F),
    "version_display_candidate": (0x60C8B640, 0x60C8B839),
}


def matches(data, needle):
    return [m.start() for m in re.finditer(re.escape(needle), data)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("decoded_main", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--objdump", type=Path)
    args = parser.parse_args()
    data = args.decoded_main.read_bytes()
    if sha256(data) != MAIN_SHA256:
        parser.error("this script requires the exact decoded PEN-F 3101 main block")
    rows = []
    for text in SEEDS:
        for offset in matches(data, text.encode("ascii")):
            address = BASE + offset
            refs = matches(data, struct.pack("<I", address))
            rows.append({
                "text": text,
                "decoded_offset": hex(offset),
                "analysis_address": hex(address),
                "literal_reference_candidates": [
                    {"decoded_offset": hex(r), "analysis_address": hex(BASE + r)} for r in refs
                ],
            })
    report = {
        "main_sha256": MAIN_SHA256,
        "analysis_base": hex(BASE),
        "mapping_source": "https://micro43club.pro/forum/threads/modifikacija-proshivki-kamer-olympus.22086/page-2#post-521460",
        "caveat": "literal matches require instruction/data interpretation before they can be called cross references",
        "strings": rows,
    }
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "landmarks.json").write_text(json.dumps(report, indent=2) + "\n")
    if args.objdump:
        exe = str(args.objdump.resolve())
        version = subprocess.check_output([exe, "--version"], text=True)
        (args.out / "objdump-version.txt").write_text(version)
        for name, (start, end) in WINDOWS.items():
            command = [exe, "-b", "binary", "-m", "mn10300", "-D", "-z",
                       "--insn-width=16", f"--adjust-vma={BASE:#x}",
                       f"--start-address={start:#x}", f"--stop-address={end:#x}",
                       str(args.decoded_main)]
            result = subprocess.check_output(command, text=True)
            (args.out / (name + ".asm")).write_text(result)
    print(f"Saved {len(rows)} landmarks to {args.out}")


if __name__ == "__main__":
    main()
