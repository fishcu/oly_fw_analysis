"""Bound exact integrated payload changes to inspected code/data/hook ranges."""
from pathlib import Path
import hashlib
import json
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis/button-af/readiness"
BASE = 0x60021020
stock = (ROOT / "analysis/decoded/00_0100_50000020.decoded.bin").read_bytes()
assert hashlib.sha256(stock).hexdigest() == "5e8d376e9111a44ac0352f26030d7c1b17026d42c45f3600cfa02a0e8c5b7d59"
payload = (OUT / "live-profiles/live-main-payload.research-only.bin").read_bytes()
assert len(payload) == len(stock)
code = []
for row in (OUT / "live-profiles/live-profile-relocation-map.txt").read_text().splitlines():
    source, dest, size = re.fullmatch(r"([0-9a-f]+) -> ([0-9a-f]+) length=(\d+)", row).groups()
    code.append((int(source, 16), int(dest, 16), int(size)))
assert len(code) == 9
regions = [(dest, dest + size) for _, dest, size in code]
regions += [(0x6031e910, 0x6031e914), (0x6031e920, 0x6031ead0), (0x6031ead0, 0x6031eb4a)]
for lo, hi in regions:
    assert stock[lo - BASE:hi - BASE] == b"\xff" * (hi - lo), hex(lo)
tables = [(0x6131bd5c, 0x700d2000, 0x610b9197), (0x6131bd6c, 0x700d2200, 0x610b96f0),
          (0x6131c29c, 0x700d2400, 0x610b962a), (0x6131c2ac, 0x700d2600, 0x610b9653)]
word = lambda data, address: struct.unpack_from("<I", data, address - BASE)[0]
for table, source, original in tables:
    assert word(stock, table) == original
    assert word(payload, table) == next(dest for origin, dest, _ in code if origin == source)
    regions.append((table, table + 4))
regions += [(0x602153fd, 0x60215401), (0x60215407, 0x6021540b),
            (0x603cedfe, 0x603cee03), (0x609b3bb2, 0x609b3bbb)]
assert word(payload, 0x602153fd) == 4 and word(payload, 0x60215407) == 0x6031e910
assert word(payload, 0x6031e910) == 0x6031ead0
for hook, origin in [(0x603cedfe, 0x700d1200), (0x609b3bb2, 0x700d0f50)]:
    dest = next(dest for source, dest, _ in code if source == origin)
    assert payload[hook - BASE] == 0xdc and word(payload, hook + 1) == ((dest - hook) & 0xffffffff)
init = payload[0x6031ead0 - BASE:0x6031eb4a - BASE]
assert bytes.fromhex("fc8226e931a0") in init  # disable OWN+6 on mutex-create failure
changed = 0
for i, (old, new) in enumerate(zip(stock, payload)):
    if old != new:
        address = BASE + i
        assert any(lo <= address < hi for lo, hi in regions), hex(address)
        changed += 1
report = dict(integrated_payload_sha256=hashlib.sha256(payload).hexdigest(),
              checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              changed_bytes=changed, code_blocks=len(code), all_changes_within_explicit_ranges=True,
              original_descriptor_targets_verified=True, relocated_descriptor_targets_verified=True,
              constructor_count_and_table_verified=True, relative_hooks_verified=True,
              initialization_failure_disables_feature=True,
              scope="Byte placement and fingerprints only; no startup, SD admission, focus, flash or recovery assertion")
(OUT / "live-component/live-diff-results.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
