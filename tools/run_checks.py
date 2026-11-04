#!/usr/bin/env python3
"""Check the curated source tree; native firmware execution is opt-in."""
import argparse
import ast
import importlib
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run_tests(directory, pattern):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests",
                    "-p", pattern], cwd=directory, env=env, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", action="store_true",
                        help="Also run core MN103/checksum/color tests; requires pinned firmware and engine")
    parser.add_argument("--loopback", action="store_true",
                        help="Also use a local HTTP test server on 127.0.0.1; never a camera")
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    files = [p for folder in ("tools", "tests", "camera_client", "patches")
             for p in (ROOT / folder).rglob("*.py")]
    for path in files:
        ast.parse(path.read_text(), filename=str(path.relative_to(ROOT)))
    modules = sorted((ROOT / "tools").glob("*.py"))
    sys.path.insert(0, str(ROOT / "tools"))
    for path in modules:
        importlib.import_module(path.stem)
    print(f"Parsed {len(files)} Python files; imported {len(modules)} tool modules.", flush=True)
    run_tests(ROOT, "test_oly_container.py")
    run_tests(ROOT, "test_penf_emulator_performance.py")
    run_tests(ROOT, "test_aperture_ring_patch.py")
    run_tests(ROOT / "camera_client", "test_*.py")
    if args.loopback:
        run_tests(ROOT / "camera_client", "check_loopback.py")
    if args.native:
        from penf_emulator import ENGINE, firmware
        firmware()  # Exact SHA-256 check, before any native execution.
        if not ENGINE.is_file():
            parser.error("Build the native harness first; see docs/tooling/EMULATOR.md")
        for name in ("emulator", "color_emulator", "mac_context", "probe"):
            run_tests(ROOT, f"test_penf_{name}.py")
    print("Checks passed. No camera was contacted or flashed.")


if __name__ == "__main__":
    main()
