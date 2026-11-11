"""Validate bounded evidence, preserve failures as boundaries, pin current files."""
from pathlib import Path
from datetime import datetime, timezone
import json
import re
import sys
from hashlib import sha256

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis/button-af/readiness"
run = ROOT / sys.argv[1]
counts = {
    "integration/core-ram-settings-results.txt": 11,
    "live-profiles/live-profile-results.txt": 15,
    "live-component/native-codec-results.txt": 3,
    "live-component/mutex-ownership-results.txt": 2,
}
evidence = {}
for name, expected in counts.items():
    p = OUT / name
    rows = p.read_text().splitlines()
    assert len(rows) == expected and all(row.startswith("PASS ") for row in rows), name
    evidence[name] = {"groups": expected, "sha256": sha256(p.read_bytes()).hexdigest()}
for folder, boundary in [("live-shooting", "Semaphore would block"), ("live-shooting-errors", "Stock response wait retried after two injected negative results")]:
    p = OUT / folder / "full-shooting-results.txt"
    rows = p.read_text().splitlines()
    assert len(rows) == 4 and sum(row.startswith("RETURNED") for row in rows) == 2
    for i in [1, 2]:
        assert rows[i].startswith("BOUNDARY") and boundary in rows[i], rows[i]
    trace = (OUT / folder / "full-shooting-trace-1.txt").read_text()
    assert "id=5e9:enable=1:kind=4:context=2:owner=2:effective-subject=0" in trace
    evidence[str(p.relative_to(OUT))] = {"returned": 2, "async_response_boundaries": 2, "sha256": sha256(p.read_bytes()).hexdigest()}
p = OUT / "live-dispatch/full-shooting-results.txt"
rows = p.read_text().splitlines()
assert len(rows) == 4 and all(row.startswith("RETURNED") for row in rows), rows
for i in range(4):
    trace = (OUT / f"live-dispatch/full-shooting-trace-{i}.txt").read_text()
    assert "CHECK:original-return-unlocked" in trace
    assert "CHECK:scheduled-original-return:" in trace
    if i in (1, 2):
        assert "SCHEDULED:native-main-thread-pop" in trace and "MODEL:owned-response-semaphore-delete:" in trace
        statuses = re.findall(r"NATIVE-RESPONSE-STATUS-MAP input=([0-9a-f]{8})", trace)
        assert statuses and set(statuses) == {"00000001"}, statuses
evidence[str(p.relative_to(OUT))] = {"returned": 4, "scope": "Native queued error replies have status 1 (API error f0000001); original-handler error cleanup only, not positive AF completion", "sha256": sha256(p.read_bytes()).hexdigest()}
for folder in ["receiver-startup", "stock-receiver-control"]:
    p = OUT / folder / "full-shooting-results.txt"
    rows = p.read_text().splitlines()
    assert len(rows) == 4 and [r.split()[0] for r in rows] == ["RETURNED", "BOUNDARY", "BOUNDARY", "RETURNED"], rows
    for i in (1, 2):
        assert "pc=60dd896d" in rows[i] and "Semaphore would block" in rows[i]
        trace = OUT / folder / f"full-shooting-trace-{i}.txt"
        body = trace.read_text()
        assert "NATIVE-CAPTURE-ROUTER pc=60db385c object=62b7315c state=7 backend=00000000 requested-backend=00000000" in body
        assert "SCHEDULED:native-main-thread-queue-empty" in body
        evidence[str(trace.relative_to(OUT))] = {"sha256": sha256(trace.read_bytes()).hexdigest()}
    startup = OUT / folder / "startup-trace.txt"
    assert "STARTUP:native-queue-quiescent:jobs=38:root-state=11" in startup.read_text()
    evidence[str(startup.relative_to(OUT))] = {"sha256": sha256(startup.read_bytes()).hexdigest()}
    evidence[str(p.relative_to(OUT))] = {"returned": 2, "capture_receiver_boundaries": 2, "sha256": sha256(p.read_bytes()).hexdigest()}
capture = OUT / "capture-connected/capture-connection-outcome.txt"
assert capture.read_text().startswith("BOUNDARY native capture initialization reaches unprovided kernel task/object state")
for name in ["capture-connection-outcome.txt", "capture-connection-boundary.txt", "capture-connection-trace.txt", "capture-factory-trace.txt"]:
    p = capture.parent / name
    evidence[str(p.relative_to(OUT))] = {"sha256": sha256(p.read_bytes()).hexdigest()}
body = (capture.parent / "capture-connection-trace.txt").read_text()
assert "NATIVE-CAPTURE-FACTORY:interface=62b71778 aeaf-vtable=60ebda38" in body
assert "SUPPLIED-INPUT:event-114 backend=62b71778" in body
assert "native-call:6004f3bd" in body and "native-call:600303db" in body
p = OUT / "live-component/full-component-results.txt"
assert "integrated, native validator result=0, native full checksum calls=1" in p.read_text()
evidence[str(p.relative_to(OUT))] = {"sha256": sha256(p.read_bytes()).hexdigest()}
package = json.loads((OUT / "live-component/live-package-results.json").read_text())
fixture = OUT / "live-component/integrated.decoded-research-only.bin"
assert sha256(fixture.read_bytes()).hexdigest() == package["native_validator_fixture_sha256"]
assert package["unchanged_other_components"] and not package["saved_installable_update"]
diff = json.loads((OUT / "live-component/live-diff-results.json").read_text())
assert diff["integrated_payload_sha256"] == package["integrated_payload_sha256"] and diff["all_changes_within_explicit_ranges"]
source_hashes = json.loads((run / "source-hashes-before.json").read_text(encoding="utf-8-sig"))
for name, digest in source_hashes.items():
    assert sha256((ROOT / "scripts" / name).read_bytes()).hexdigest() == digest, name
report = dict(
    verified_at_utc=datetime.now(timezone.utc).isoformat(), run_directory=str(run.relative_to(ROOT)),
    source_hashes=source_hashes, evidence=evidence, integrated_payload_sha256=package["integrated_payload_sha256"],
    native_validator_fixture_sha256=package["native_validator_fixture_sha256"],
    status="OFFLINE PROTOTYPE; NOT READY TO FLASH",
    unresolved=[
        "Only error-path original-handler completion established. With native receiver startup, both stock and extension block at the same null-backend capture router. Conditional native capture-factory/connection initialization reaches unprovided kernel task/object state; successful AF reception/acquisition is unproven",
        "Physical orientation source equivalence remains a candidate; supplied pose tests do not establish it",
        "Camera task scheduling, cross-CPU record visibility and retained-pointer lifetime",
        "Display/joystick editing while an owned profile is active and sleep/custom-mode/reset lifecycle",
        "Physical NVM reload, full startup, actual SD update-service admission and intact-camera recovery",
    ],
    note="Group counts describe different scopes and are deliberately not summed. All NVM and hardware/kernel inputs in these harnesses are fixtures or declared models."
)
(run / "evidence-manifest.json").write_text(json.dumps(report, indent=2) + "\n")
(OUT / "live-evidence-manifest.json").write_text(json.dumps(report, indent=2) + "\n")
print("Verified exact-source offline evidence, native error cleanup and stock/extension receiver boundaries. NOT READY TO FLASH.")
