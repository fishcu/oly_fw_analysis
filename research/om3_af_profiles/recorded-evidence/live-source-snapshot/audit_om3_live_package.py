"""Exact integrated research payload; full-container roundtrip stays in memory.

Writes a DECODED checksum fixture for the native validator, never an SD update.
"""
from pathlib import Path
import hashlib
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference/tools"))
from oly_container import parse, encode, decode, replace_payload, sha256

OUT = ROOT / "analysis/button-af/readiness/live-component"
OUT.mkdir(exist_ok=True)
raw = (ROOT / "firmware/catalog/OLY_E_147_1100_0000_0000.BIN").read_bytes()
assert sha256(raw) == "8c133084414533159f587bf46bfb4152714c4074312a47c8d8503e33d605696d"
blocks = parse(raw)
stock = blocks[0]
payload = (ROOT / "analysis/button-af/readiness/live-profiles/live-main-payload.research-only.bin").read_bytes()
assert len(payload) == len(stock.payload)
changed = replace_payload(stock, payload)
encoded = encode(payload)
assert decode(encoded) == payload
component = changed.header + encoded + changed.trailer
assert parse(component)[0].payload == payload
try:
    parse(stock.header + encoded + stock.trailer)
except ValueError as ex:
    assert "checksum mismatch" in str(ex)
else:
    raise AssertionError("Unrepaired integrated edits accepted")
# Keep every other component byte-for-byte as delivered, and validate them all.
outer = component + raw[len(component):]
assert len(outer) == len(raw)
reparsed = parse(outer)
assert len(reparsed) == len(blocks)
for i, (old, new) in enumerate(zip(blocks, reparsed)):
    assert old.header == new.header and old.trailer[:28] == new.trailer[:28]
    assert old.offset == new.offset and len(old.payload) == len(new.payload)
    if i:
        assert old == new
assert outer[len(component):] == raw[len(component):]
base = 0x60021020
spans = []
start = None
for i, (a, b) in enumerate(zip(stock.payload, payload)):
    if a != b and start is None:
        start = i
    if a == b and start is not None:
        spans.append([hex(base + start), hex(base + i), i - start])
        start = None
if start is not None:
    spans.append([hex(base + start), hex(base + len(payload)), len(payload) - start])
# Includes all hooks, descriptors, owned data, initializer and relocated code.
fixture = changed.header + payload + changed.trailer
assert len(fixture) == 0x2000000
(OUT / "integrated.decoded-research-only.bin").write_bytes(fixture)
report = dict(
    stock_sha256=sha256(raw), integrated_payload_sha256=sha256(payload),
    native_validator_fixture_sha256=sha256(fixture),
    full_container_in_memory_sha256=sha256(outer),
    component_count=len(blocks), full_container_bytes=len(outer),
    unchanged_other_components=True, metadata_and_lengths_preserved=True,
    encode_decode_identical=True, unrepaired_checksum_rejected=True,
    changed_byte_count=sum(n for _, _, n in spans), changed_spans=spans,
    saved_installable_update=False,
    scope="Host parser/encoding proof of exact integrated hooks, constructor, data and code. Decoded fixture only. No update-service admission, boot, flash, physical NVM or recovery proof."
)
(OUT / "live-package-results.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({k: v for k, v in report.items() if k != "changed_spans"}, indent=2))
