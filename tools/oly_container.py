#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Offline Olympus update inspection. No device access or flashing.

Container/transform reference: Altsoph and mx3, CHDK thread 2471:
https://chdk.setepontos.com/d/2471-olympus-emjustylus-series-fw-analysis
Independently implemented and checked against all four supplied PEN-F blocks.
"""

import argparse
from array import array
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import struct
import sys


DECODE_ORDER = (1, 3, 0, 2, 6, 4, 7, 5, 11, 10, 9, 8, 13, 14, 12, 15)
INVERT = bytes(i ^ 0xFF for i in range(256))


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def decode(data):
    if len(data) % 16:
        raise ValueError("payload is not a multiple of 16 bytes")
    result = bytearray(len(data))
    for output_index, input_index in enumerate(DECODE_ORDER):
        result[output_index::16] = data[input_index::16].translate(INVERT)
    return bytes(result)


def encode(data):
    if len(data) % 16:
        raise ValueError("payload is not a multiple of 16 bytes")
    result = bytearray(len(data))
    for input_index, output_index in enumerate(DECODE_ORDER):
        result[output_index::16] = data[input_index::16].translate(INVERT)
    return bytes(result)


def sum32(data):
    if len(data) % 4:
        raise ValueError("checksum data is not a multiple of 4 bytes")
    words = array("I")
    if words.itemsize != 4:
        raise ValueError("host unsigned int is not 32 bits")
    words.frombytes(data)
    if sys.byteorder != "little":
        words.byteswap()
    return sum(words) & 0xFFFFFFFF


@dataclass(frozen=True)
class Block:
    index: int
    offset: int
    header: bytes
    payload: bytes
    trailer: bytes

    @property
    def address(self):
        return struct.unpack_from("<I", self.header, 8)[0]

    @property
    def kind(self):
        return struct.unpack_from("<H", self.header, 20)[0]

    @property
    def filename(self):
        return f"{self.index:02d}_{self.kind:04x}_{self.address + 32:08x}.decoded.bin"

    def metadata(self):
        return {
            "index": self.index,
            "container_offset": hex(self.offset),
            "payload_container_offset": hex(self.offset + 32),
            "payload_size": len(self.payload),
            "signature": self.header[:2].decode("ascii"),
            "model_bytes": self.header[2:4].hex(),
            "version_raw_le_u16": hex(struct.unpack_from("<H", self.header, 16)[0]),
            "kind": hex(self.kind),
            "header_address": hex(self.address),
            "container_payload_address": hex(self.address + 32),
            "address_note": "container address, NOT necessarily a code/disassembly address; PEN-F main code has a separate mapping",
            "header_hex": self.header.hex(),
            "trailer_hex": self.trailer.hex(),
            "decoded_sha256": sha256(self.payload),
            "checksum_valid": True,
            "decoded_file": self.filename,
        }


def parse(data):
    if not data:
        raise ValueError("empty image")
    blocks = []
    offset = 0
    model = None
    while offset < len(data):
        if len(data) - offset < 64:
            raise ValueError(f"truncated block at {offset:#x}")
        header = data[offset:offset + 32]
        if header[:2] != b"OE":
            raise ValueError(f"unsupported signature at {offset:#x}; this tool covers scrambled OE blocks only")
        if struct.unpack_from("<I", header, 20)[0] == 0:
            raise ValueError(f"unscrambled block is unsupported at {offset:#x}")
        if model is None:
            model = header[2:4]
        elif model != header[2:4]:
            raise ValueError(f"mixed model identifiers at {offset:#x}")
        size = struct.unpack_from("<I", header, 12)[0]
        if not size or size % 16:
            raise ValueError(f"invalid payload size at {offset:#x}")
        end = offset + size + 64
        if end > len(data):
            raise ValueError(f"payload exceeds image at {offset:#x}")
        trailer = data[end - 32:end]
        if header[:28] != trailer[:28]:
            raise ValueError(f"header/trailer mismatch at {offset:#x}")
        if header[28:32] != b"\0" * 4:
            raise ValueError(f"unexpected header checksum field at {offset:#x}")
        payload = decode(data[offset + 32:end - 32])
        if (sum32(header) + sum32(payload) + sum32(trailer)) & 0xFFFFFFFF:
            raise ValueError(f"checksum mismatch at {offset:#x}")
        blocks.append(Block(len(blocks), offset, header, payload, trailer))
        offset = end
    return blocks


def reconstruct(blocks):
    """Preserve original metadata/checksums; only valid for unchanged payloads."""
    return b"".join(b.header + encode(b.payload) + b.trailer for b in blocks)


def replace_payload(block, payload):
    """Replace a same-sized decoded payload and repair its additive checksum.

    Does not assert that code is executable or safe to flash. Container metadata
    stays unchanged. The exact historical 3100 patch is an independent fixture
    for this operation in penf_experiments.py.
    """
    if len(payload) != len(block.payload) or len(payload) % 16:
        raise ValueError("replacement must preserve the aligned payload size")
    if block.header[:28] != block.trailer[:28]:
        raise ValueError("unexpected header/trailer metadata")
    trailer = bytearray(block.trailer)
    trailer[28:32] = b"\0" * 4
    checksum = -(sum32(block.header) + sum32(payload) + sum32(trailer)) & 0xFFFFFFFF
    struct.pack_into("<I", trailer, 28, checksum)
    return Block(block.index, block.offset, block.header, bytes(payload), bytes(trailer))


def string_records(block, code_base=None):
    # ASCII diagnostics are leads, not proof of execution or feature support.
    for match in re.finditer(rb"[\x20-\x7e]{6,}", block.payload):
        record = {
            "block": block.index,
            "decoded_offset": hex(match.start()),
            "container_address": hex(block.address + 32 + match.start()),
            "text": match.group().decode("ascii"),
        }
        if block.index == 0 and code_base is not None:
            record["analysis_address"] = hex(code_base + match.start())
        yield record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--out", type=Path, help="new directory for decoded blocks and reports")
    parser.add_argument("--code-base", type=lambda s: int(s, 0), help="explicit analysis base for block 0; no inference from container address")
    parser.add_argument("--expect-sha256", help="require an exact input SHA-256")
    args = parser.parse_args()
    data = args.image.read_bytes()
    if args.expect_sha256 and sha256(data) != args.expect_sha256.lower():
        raise ValueError("source SHA-256 differs from the expected build")
    blocks = parse(data)
    repacked = reconstruct(blocks)
    if repacked != data:
        raise ValueError("decode/re-encode did not reproduce the source exactly")
    report = {
        "source": str(args.image),
        "source_size": len(data),
        "source_sha256": sha256(data),
        "roundtrip_sha256": sha256(repacked),
        "roundtrip_identical": True,
        "block0_analysis_base": None if args.code_base is None else hex(args.code_base),
        "scope": "offline container integrity only; not a bootability or recovery test",
        "blocks": [b.metadata() for b in blocks],
    }
    if args.out:
        if args.out.resolve() == args.image.parent.resolve():
            raise ValueError("output must be separate from original firmware directory")
        args.out.mkdir(parents=True, exist_ok=False)
        (args.out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
        pattern = re.compile(
            r"hue|satura|chroma|color.?profil|colou?r.?creat|monochro|lumin|lightness|"
            r"firmware|version|[er]122|rom.?ver|hsl|hsv|3\.1|rcu|updat", re.I
        )
        with (args.out / "strings.jsonl").open("w") as all_strings, \
             (args.out / "leads.jsonl").open("w") as leads:
            for block in blocks:
                (args.out / block.filename).write_bytes(block.payload)
                for record in string_records(block, args.code_base):
                    line = json.dumps(record, ensure_ascii=False) + "\n"
                    all_strings.write(line)
                    if pattern.search(record["text"]):
                        leads.write(line)
        # Deliberately do not create a file named like an SD-card update.
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        sys.exit(f"error: {exc}")
