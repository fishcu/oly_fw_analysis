#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Convert a same-build OE firmware modification to an om-emu RAM overlay.

Reads two separately obtained update files; writes JSON, never a firmware BIN.
The emulator still checks its exact stock hashes, preimages and loaded extents.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path

from oly_container import parse


def changed_ranges(before, after):
    if len(before) != len(after):
        raise ValueError("component sizes differ")
    start = None
    for offset, (old, new) in enumerate(zip(before, after)):
        if old != new and start is None:
            start = offset
        elif old == new and start is not None:
            yield start, offset
            start = None
    if start is not None:
        yield start, len(before)


def overlay(stock, modified):
    original, candidate = parse(stock), parse(modified)
    by_kind = {}
    for block in original:
        key = (block.kind, block.address)
        if key in by_kind:
            raise ValueError("duplicate stock component")
        by_kind[key] = block
    seen, patches, components = set(), [], []
    for block in candidate:
        key = (block.kind, block.address)
        if key in seen or key not in by_kind:
            raise ValueError("duplicate or unmatched modified component")
        seen.add(key)
        before = by_kind[key]
        if block.header != before.header:
            raise ValueError("component headers differ: requires the same build and layout")
        ranges = list(changed_ranges(before.payload, block.payload))
        if not ranges:
            continue
        if block.kind not in (0x0100, 0x0101):
            raise ValueError(f"changed component {block.kind:#06x}: only main and resource overlays are supported")
        name = "main" if block.kind == 0x0100 else "resource"
        for start, end in ranges:
            patches.append({"block": name, "offset": start,
                            "old": base64.b64encode(before.payload[start:end]).decode("ascii"),
                            "new": base64.b64encode(block.payload[start:end]).decode("ascii")})
        components.append({"block": name, "changed_bytes": sum(end-start for start, end in ranges),
                           "ranges": len(ranges), "last_changed_end": max(end for _, end in ranges),
                           "decoded_sha256": hashlib.sha256(block.payload).hexdigest()})
    if not patches:
        raise ValueError("no changed main/resource payload bytes")
    return {"format": "om-emu-overlay-from-OE-diff-v1",
            "stock_sha256": hashlib.sha256(stock).hexdigest(),
            "modified_sha256": hashlib.sha256(modified).hexdigest(),
            "components": components, "patches": patches}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock", type=Path)
    parser.add_argument("modified", type=Path)
    parser.add_argument("output", type=Path, help="new JSON file; existing files are refused")
    args = parser.parse_args()
    try:
        result = overlay(args.stock.read_bytes(), args.modified.read_bytes())
        with args.output.open("x") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
    except (OSError, ValueError) as error:
        parser.exit(1, f"Error: {error}\n")
    print(json.dumps({"components": result["components"], "patches": len(result["patches"])}, indent=2))


if __name__ == "__main__":
    main()
