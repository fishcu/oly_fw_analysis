#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Fresh main-entry replay with reviewed USTART3 preemption checkpoints."""
import hashlib
from pathlib import Path

import penf_boot_emulator as boot
import penf_boot_parameter_init as parameter
import penf_boot_parameter_budget as budget
from penf_emulator import ROOT
from penf_startup_interrupts import StartupInterrupts

BasePeer = parameter.ParameterInitPeer


class PreemptiblePeer(BasePeer):
    hooks = BasePeer.hooks | set(StartupInterrupts.boundaries)

    def handle(self, state, hooks, interrupts):
        pc = state.regs['pc']
        if pc in StartupInterrupts.boundaries and interrupts.checkpoint(state):
            return True
        if pc in StartupInterrupts.boundaries and pc not in BasePeer.hooks:
            return self.step(state, hooks)
        return super().handle(state, hooks, interrupts)


def main():
    original_peer, original_irq = parameter.ParameterInitPeer, parameter.CoreIdleInterrupts
    original_experiment = boot.boot_experiment
    sources = ('tools/penf_boot_startup_preemption.py', 'tools/penf_startup_interrupts.py')
    hashes = {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources}

    def experiment(*args, **kwargs):
        report, state = original_experiment(*args, **kwargs)
        report['source_sha256'].update(hashes)
        report['startup_preemption_scenario'] = dict(
            timer_instruction_interval=250000, cpu=0, task=49,
            boundaries={hex(k): v for k, v in StartupInterrupts.boundaries.items()},
            arbitration='Enabled/unmasked pending software IRQs and due timer, native priority then IRQ number',
            limitation='Selected task checkpoints only, no measured physical timing; unknown accesses remain strict stops')
        return report, state

    parameter.ParameterInitPeer = PreemptiblePeer
    parameter.CoreIdleInterrupts = StartupInterrupts
    boot.boot_experiment = experiment
    try:
        budget.main()
    finally:
        parameter.ParameterInitPeer, parameter.CoreIdleInterrupts = original_peer, original_irq
        boot.boot_experiment = original_experiment


if __name__ == '__main__':
    main()
