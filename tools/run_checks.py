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
    parser.add_argument("--portable", action="store_true",
                        help="Run a partial offline subset without POSIX camera-state tests")
    args = parser.parse_args()
    if args.portable and (args.native or args.loopback):
        parser.error("--portable cannot be combined with --native or --loopback")
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
    if args.portable:
        print("Portable subset: partial coverage; production camera-state support is unchanged.",
              flush=True)
        print("Omitted client suites (not selected by this subset):", flush=True)
        for path in sorted((ROOT / "camera_client" / "tests").glob("test_*.py")):
            if path.name != "test_transport.py":
                print(f"  {path.relative_to(ROOT).as_posix()}", flush=True)
        print("POSIX storage/locking/durability and client workflow are not tested; "
              "native and loopback checks are not selected.", flush=True)
        run_tests(ROOT / "camera_client", "test_transport.py")
    else:
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
    if args.portable:
        print("Selected portable checks passed (partial coverage). No camera was contacted or flashed.")
    else:
        print("Checks passed. No camera was contacted or flashed.")


if __name__ == "__main__":
    main()
