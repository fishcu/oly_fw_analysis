#!/usr/bin/env python3
# Copyright 2026 tsmkirby (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Inspect exact-build OM-3 AF tables and optional offline queue-95 bytes."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from struct import error as StructError, unpack_from

BASE = 0x60021020
MAIN = "5e8d376e9111a44ac0352f26030d7c1b17026d42c45f3600cfa02a0e8c5b7d59"
RESOURCES = "3d9fd4426b45fbe4b715599422af38c6d22392c08543a69f63c28291c5a0b059"
TABLE = 0x6031E224
GUARD_EXEMPT = {0x4A, 0x4B, 0x50, 0x51, 0x53, 0x54, 0x55, 0x5A}


def checked_input(path, size, expected):
    data = path.read_bytes()
    if len(data) != size or sha256(data).hexdigest() != expected:
        raise ValueError(f"{path}: expected {size} bytes, SHA-256 {expected}")
    return data


def words(main, address, fmt):
    return unpack_from("<" + fmt, main, address - BASE)


def menu_pages(main):
    result = {}
    for a in range(0x6158EE8C, 0x6158F3B4, 20):
        page, row_base, count, _, _ = words(main, a, "5I")
        if page not in (27, 28, 29):
            continue
        rows = []
        for address in range(row_base, row_base + count * 36, 36):
            setting, kind, label, viewer, options, n = words(main, address, "IHHIII")
            rows.append({"address": hex(address), "id": setting, "kind": kind,
                         "label_id": hex(label), "viewer": hex(viewer),
                         "option_values": [words(main, options + i * 12, "I")[0]
                                           for i in range(n)]})
        result[page] = {"descriptor": hex(a), "rows": rows}
    return result


def target_settings(main):
    cells = {}
    for first, count, start in [(0, 2256, 0x6062555C), (3000, 47, 0x606249BC),
                                (10000, 71, 0x6061DD72), (15000, 456, 0x6061906E)]:
        for i in range(count):
            key, index = words(main, start + i * 4, "HH")
            cells.setdefault(key, {}).setdefault(index, []).append(first + i)
    wanted = {0x99A1, 0x5962, 0x1DD1, 0x1DE1, 0x9A41, 0x84D1, 0x88B2,
              0x90A1, 0x99D2, 0x9FA1, 0xDFA1, 0x90D1, 0x5A11}
    result = {}
    address = 0x600E4BEC
    records = 0
    while address < 0x6011FE20:
        key, count = words(main, address, "HH")
        if key in wanted:
            if key in result:
                raise ValueError(f"duplicate target key {key:#06x}")
            mapped = cells.get(key, {})
            result[key] = {"descriptor": hex(address), "count": count, "ui_ids": mapped,
                           "unmapped_indices": sorted(set(range(count)) - mapped.keys())}
        # Stock settings-area width helper 0x60061333 uses two bits, not the
        # typed-accessor mask (which would misread e.g. key 0x6bcd as width 5).
        width = (key & 3) or 4
        if width not in (1, 2, 4) or count == 0:
            raise ValueError(f"invalid setting descriptor at {address:#010x}")
        address = (address + 4 + count * width + 3) & ~3
        records += 1
    if address != 0x6011FE20 or records != 1215 or result.keys() != wanted:
        raise ValueError("unexpected settings table extent or missing key")
    return {f"0x{key:04x}": result[key] for key in sorted(result)}


def decode_envelope(handlers, request, payload=None, reply=None):
    if len(request) != 16 or (reply is not None and len(reply) != 12):
        raise ValueError("expected a 16-byte request and, if supplied, a 12-byte reply")
    queue, correlation, command, pointer = unpack_from("<4I", request)
    result = {"reply_queue_word": queue, "correlation_word": hex(correlation),
              "command": hex(command), "payload_pointer": hex(pointer),
              "handler": handlers[command] if command < len(handlers) else None,
              "exempt_from_context_0x94_deferral": command in GUARD_EXEMPT}
    if payload is not None and command in (0x2A, 0x2B, 0x2C):
        if len(payload) < 8:
            raise ValueError("AF start/end payload needs at least 8 supplied bytes")
        kind, flags = unpack_from("<2I", payload)
        result["kind_word"], result["flags_word"] = kind, hex(flags)
    if reply is not None:
        status, tag, address = unpack_from("<H2xII", reply)
        result["reply"] = {"status_u16": hex(status), "padding": reply[2:4].hex(),
                           "correlation_word": hex(tag), "payload_pointer": hex(address)}
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("main", type=Path, help="decoded stock component 0100")
    ap.add_argument("--resources", type=Path, help="optional decoded component 0106")
    ap.add_argument("--request", type=bytes.fromhex, help="optional 16-byte queue-95 request, hex")
    ap.add_argument("--payload", type=bytes.fromhex, help="separately captured RAM payload, hex")
    ap.add_argument("--reply", type=bytes.fromhex, help="optional 12-byte queue-95 reply, hex")
    args = ap.parse_args()
    if args.request is None and (args.payload is not None or args.reply is not None):
        ap.error("--payload and --reply require --request")
    try:
        image = checked_input(args.main, 33_554_368, MAIN)
        handlers = [hex(v) for v in words(image, TABLE, "93I")]
        report = {"main_sha256": MAIN, "cpu_base": hex(BASE),
                  "menu_pages": menu_pages(image), "target_settings": target_settings(image),
                  "queue95_dispatch_base": hex(TABLE), "queue95_handlers": handlers}
        if args.resources:
            resource = checked_input(args.resources, 143_523_776, RESOURCES)
            report["subject_detect_enum"] = [
                {"value": unpack_from("<I", resource, i - 4)[0],
                 "name": resource[i:i + 48].split(bytes(1), 1)[0].decode("ascii")}
                for i in range(0x28D1DEC, 0x28D1F3C + 1, 56)
            ]
            resource_base = 0x458C0020
            directory_index = words(image, 0x602CB253 + 14, "B")[0]
            directory, _ = unpack_from("<II", resource, directory_index * 16)
            nested = directory - resource_base
            if resource[nested:nested + 2] != b"OE":
                raise ValueError("missing nested learning resource directory")
            logical, size = unpack_from("<II", resource, nested + 32 + 5 * 16)
            offset = logical - resource_base
            if not 0 <= offset < offset + size <= len(resource):
                raise ValueError("learning bank exceeds resource bounds")
            report["human_bank"] = {"resource_sha256": RESOURCES, "directory_index": directory_index,
                                    "bank_index": 5, "logical_address": hex(logical), "offset": hex(offset),
                                    "bytes": size, "sha256": sha256(resource[offset:offset + size]).hexdigest()}
            report["resize_dimensions"] = [words(image, 0x60A05B28 + i * 48, "2I") for i in range(3)]
        if args.request is not None:
            report["queue95_envelope"] = decode_envelope(handlers, args.request, args.payload, args.reply)
    except (OSError, ValueError, StructError) as exc:
        ap.error(str(exc))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
