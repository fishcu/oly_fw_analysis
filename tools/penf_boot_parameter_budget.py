#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Run the reviewed parameter initialization with a larger native work budget.

Uses penf_boot_parameter_init's CLI and identical boot assumptions. The only
change is a 16-million-instruction allowance for a normal execution segment,
needed for the nested finite settings-table searches following bank creation.
Single-step model operations retain their original one-instruction limit.
Unknown instructions/accesses still stop immediately; no return is forced.
"""
import hashlib
from pathlib import Path

import penf_boot_emulator as boot
import penf_boot_parameter_init as parameter
from penf_emulator import ROOT


def main():
    original_run = boot.BootState.run
    original_experiment = boot.boot_experiment
    source = Path(__file__).resolve()
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()

    def run(state, hooks, limit=200000):
        if limit == 2000000:
            limit = 16000000
        return original_run(state, hooks, limit=limit)

    def experiment(*args, **kwargs):
        report, state = original_experiment(*args, **kwargs)
        report['source_sha256'][str(source.relative_to(ROOT))] = source_hash
        report['execution_budget_extension'] = dict(
            original_segment_limit=2000000, segment_limit=16000000,
            reason='Finite settings-table nested searches exceed the earlier work budget',
            semantics='No changed instructions, data, hardware responses or scheduling rules')
        return report, state

    boot.BootState.run = run
    boot.boot_experiment = experiment
    try:
        parameter.main()
    finally:
        boot.BootState.run = original_run
        boot.boot_experiment = original_experiment


if __name__ == '__main__':
    main()
