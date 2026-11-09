#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Measure a fresh connected replay, including native transport and artifacts.

No checkpoint resume and no changes to the driver's modeled hardware behavior.
"""
import argparse
import cProfile
import importlib
import json
import os
from pathlib import Path
import pstats
import sys
import time

import penf_emulator as emulator


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--driver', default='penf_boot_remote_semaphore')
    parser.add_argument('--profile', action='store_true')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    driver = importlib.import_module(args.driver)
    original = emulator.subprocess.run
    stats = dict(native_calls=0, native_wall_seconds=0.0, input_bytes=0, output_bytes=0,
                 driver=args.driver, profiled=args.profile)

    def run(*call_args, **kwargs):
        start = time.perf_counter()
        result = original(*call_args, **kwargs)
        if call_args and isinstance(call_args[0], list) and call_args[0][0] == str(emulator.ENGINE):
            stats['native_calls'] += 1
            stats['native_wall_seconds'] += time.perf_counter()-start
            stream = kwargs.get('stdin')
            stats['input_bytes'] += os.fstat(stream.fileno()).st_size if stream else len(kwargs.get('input', b''))
            stats['output_bytes'] += len(result.stdout)
            if stats['native_calls'] % 1000 == 0:
                print(json.dumps(stats), flush=True)
        return result

    profile = cProfile.Profile() if args.profile else None
    previous_argv = sys.argv
    sys.argv = [args.driver, '--out', str(args.out/'run')]
    emulator.subprocess.run = run
    start = time.perf_counter()
    if profile:
        profile.enable()
    try:
        driver.main()
    finally:
        if profile:
            profile.disable()
        stats['wall_seconds'] = time.perf_counter()-start
        sys.argv = previous_argv
        emulator.subprocess.run = original
        (args.out/'timing.json').write_text(json.dumps(stats, indent=2)+'\n')
        if profile:
            profile.dump_stats(str(args.out/'profile.bin'))
            with (args.out/'profile.txt').open('w') as out:
                pstats.Stats(profile, stream=out).strip_dirs().sort_stats('cumulative').print_stats(50)
        print(json.dumps(stats), flush=True)


if __name__ == '__main__':
    main()
