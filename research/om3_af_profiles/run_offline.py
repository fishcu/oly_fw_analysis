"""Portable launcher for preserved probes; never connects to a camera."""
from pathlib import Path
from hashlib import sha256
from datetime import datetime, timezone
import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
PIN = "539fcf1fa9eda5fdef8ede4deeab94a4691d94c3"
STOCK = "8c133084414533159f587bf46bfb4152714c4074312a47c8d8503e33d605696d"
PROOF = Path("analysis/button-af/readiness")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def check_recorded():
    imported = json.loads((ROOT / "import-manifest.json").read_text(encoding="utf-8"))
    for name, expected in imported["files"].items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"Imported file changed: {name}")
    base = json.loads((ROOT / "recorded-evidence/live-evidence-manifest.json").read_text())
    for name, expected in base["source_hashes"].items():
        if digest(ROOT / "scripts" / name) != expected:
            raise ValueError(f"Original full-run source changed: {name}")
    counts = {"integration/core-ram-settings-results.txt": 11,
              "live-profiles/live-profile-results.txt": 15,
              "live-component/native-codec-results.txt": 3,
              "live-component/mutex-ownership-results.txt": 2}
    for name, count in counts.items():
        rows = (ROOT / "recorded-evidence" / name).read_text().splitlines()
        if len(rows) != count or not all(r.startswith("PASS ") for r in rows):
            raise ValueError(f"Recorded result scope changed: {name}")
    print("Imported hashes and recorded source/result identities match; no firmware execution performed.")
    print(base["status"])


def prepare(stock):
    if digest(stock) != STOCK:
        raise ValueError("Wrong stock container SHA-256")
    parser_bytes = subprocess.run(["git", "show", f"{PIN}:tools/oly_container.py"],
                                  cwd=REPO, check=True, capture_output=True).stdout
    parser = ROOT / "reference/tools/oly_container.py"
    parser.parent.mkdir(parents=True, exist_ok=True)
    if parser.exists() and parser.read_bytes() != parser_bytes:
        raise ValueError("Existing parser differs from the pinned dependency")
    parser.write_bytes(parser_bytes)
    spec = importlib.util.spec_from_file_location("om3_pinned_container", parser)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    blocks = module.parse(stock.read_bytes())
    target = ROOT / "firmware/catalog/OLY_E_147_1100_0000_0000.BIN"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and digest(target) != STOCK:
        raise ValueError("Existing stock destination has a different hash")
    if stock.resolve() != target.resolve():
        shutil.copyfile(stock, target)
    decoded = ROOT / "analysis/decoded"
    decoded.mkdir(parents=True, exist_ok=True)
    for block in blocks:
        path = decoded / block.filename
        if path.exists() and path.read_bytes() != block.payload:
            raise ValueError(f"Existing decoded input differs: {path.name}")
        path.write_bytes(block.payload)
    print("Prepared exact stock inputs and pinned parser in ignored local directories.")


def run(args):
    launcher = args.ghidra / "support" / ("analyzeHeadless.bat" if os.name == "nt" else "analyzeHeadless")
    if not launcher.is_file() or not args.project_dir.is_dir():
        raise ValueError("Headless launcher or project directory does not exist")
    env = dict(os.environ, JAVA_HOME=str(args.java_home.resolve()))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    run_dir = ROOT / PROOF / "live-runs" / stamp
    run_dir.mkdir(parents=True)
    sources = set((ROOT / "scripts").glob("OM3*.java")) | set((ROOT / "scripts").glob("*om3_live*.py"))
    sources.add(ROOT / "scripts/run_om3_live_offline.ps1")
    before = {p.name: digest(p) for p in sorted(sources)}
    (run_dir / "source-hashes-before.json").write_text(json.dumps(before, indent=2))

    def headless(scripts, log):
        command = [str(launcher.resolve()), str(args.project_dir.resolve()), args.project_name,
                   "-process", "00_0100_50000020.decoded.bin", "-noanalysis", "-readOnly", "-scriptPath", "scripts"]
        for script, folder, *extra in scripts:
            (ROOT / PROOF / folder).mkdir(parents=True, exist_ok=True)
            command += ["-postScript", script + ".java", (PROOF / folder).as_posix(), *extra]
        command += ["-log", str(log)]
        subprocess.run(command, cwd=ROOT, env=env, check=True)
        if re.search(r"SCRIPT ERROR|Error running script|WARN.*Uninitialized memory", log.read_text(errors="replace")):
            raise RuntimeError(f"Headless script or memory failure; inspect {log}")

    phase = [("OM3CoreRAMSettingsProof", "integration"), ("OM3LiveProfiles", "live-profiles"),
             ("OM3LiveShooting", "live-shooting"), ("OM3LiveShootingErrors", "live-shooting-errors"),
             ("OM3LiveDispatch", "live-dispatch"), ("OM3ReceiverStartupProof", "receiver-startup"),
             ("OM3StockReceiverControl", "stock-receiver-control"), ("OM3CaptureConnectedProof", "capture-connected"),
             ("OM3NativeCodecProof", "live-component"), ("OM3MutexOwnershipProof", "live-component")]
    headless(phase, run_dir / "phase-one.log")
    for script in ["audit_om3_live_package.py", "check_om3_live_diff.py"]:
        subprocess.run([sys.executable, "scripts/" + script], cwd=ROOT, check=True)
    headless([("OM3FullComponentProof", "live-component", "integrated")], run_dir / "phase-two.log")
    for path in sources:
        if digest(path) != before[path.name]:
            raise ValueError(f"Source changed during execution: {path.name}")
    subprocess.run([sys.executable, "scripts/verify_om3_live_evidence.py", str(run_dir)], cwd=ROOT, check=True)
    headless([("OM3CaptureTransportProof", "capture-transport")], run_dir / "transport.log")
    outcome = ROOT / PROOF / "capture-transport/capture-transport-outcome.txt"
    if not outcome.read_text().startswith("BOUNDARY conditional native command-40 packaging"):
        raise ValueError("Unexpected supplemental transport outcome")
    print("Completed bounded offline suites and preserved boundaries. NOT READY TO FLASH.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-recorded", action="store_true")
    parser.add_argument("--prepare-inputs", action="store_true")
    parser.add_argument("--stock", type=Path)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--ghidra", type=Path)
    parser.add_argument("--java-home", type=Path)
    parser.add_argument("--project-dir", type=Path)
    parser.add_argument("--project-name", default="OM3_main_full")
    args = parser.parse_args()
    if not (args.check_recorded or args.prepare_inputs or args.run):
        parser.error("choose --check-recorded, --prepare-inputs or --run")
    if args.prepare_inputs and not args.stock:
        parser.error("--prepare-inputs requires --stock")
    if args.run and not all([args.ghidra, args.java_home, args.project_dir]):
        parser.error("--run requires --ghidra, --java-home and --project-dir")
    if args.check_recorded:
        check_recorded()
    if args.prepare_inputs:
        prepare(args.stock)
    if args.run:
        run(args)


if __name__ == "__main__":
    main()
