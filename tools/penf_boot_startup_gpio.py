#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Task-context IRQ continuation with scoped GPIO97 output-sample hypothesis."""
import hashlib
from dataclasses import replace

import penf_boot_emulator as boot
import penf_boot_startup_preemption as preemption
from penf_emulator import ROOT


class StartupGpioPeer(preemption.PreemptiblePeer):
    hooks = preemption.PreemptiblePeer.hooks | {0x6019419f, 0x601941a6}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.gpio97_sample = None

    def handle(self, state, hooks, interrupts):
        pc = state.regs['pc']
        if pc == 0x6019419f:
            if state.cpu != 0 or state.regs['d0'] != 97 or self.gpio97_sample is not None:
                raise ValueError('Unreviewed bc_ssc GPIO sample context')
            address = int.from_bytes(state.read(0x60025cec+97*4, 4), 'little')
            if address != 0x9b800b84:
                raise ValueError('GPIO97 register mapping differs')
            old = next(r for r in state.regions if r.address == address)
            if old.permissions != 'w':
                raise ValueError('GPIO97 is not an existing write-only latch shadow')
            output = int.from_bytes(old.data, 'little')
            value = (output & ~16) | ((output & 1) << 4)
            self.gpio97_sample = (old, state.regs['sp'], output & 1)
            state.register(address, 'rw', value)
            self.event(state, 'bc_ssc scoped GPIO97 output-sample hypothesis',
                address=hex(address), output_shadow=output, input_level=output & 1,
                assumption='At this read only, sample bit 4 follows the last native output bit 0. Electrical behavior is unmeasured; no transaction reply or completion is supplied.')
            return self.step(state, hooks)
        if pc == 0x601941a6:
            if self.gpio97_sample is None:
                raise ValueError('GPIO97 sample return without entry')
            old, sp, level = self.gpio97_sample
            if state.cpu != 0 or state.regs['sp'] != sp or state.regs['d0'] != level:
                raise ValueError('GPIO97 native reader returned an unexpected value/context')
            state.regions = [replace(r, data=old.data, permissions=old.permissions)
                             if r.address == old.address else r for r in state.regions]
            self.gpio97_sample = None
            self.event(state, 'bc_ssc native GPIO97 sample returned', value=level)
            return self.step(state, hooks)
        return super().handle(state, hooks, interrupts)


def main():
    original_peer = preemption.PreemptiblePeer
    original_experiment = boot.boot_experiment
    source = 'tools/penf_boot_startup_gpio.py'
    source_hash = hashlib.sha256((ROOT/source).read_bytes()).hexdigest()

    def experiment(*args, **kwargs):
        report, state = original_experiment(*args, **kwargs)
        report['source_sha256'][source] = source_hash
        report['startup_gpio_scenario'] = dict(
            pin=97, entry='0x6019419f', return_pc='0x601941a6',
            assumption='Sample follows native output latch only during this bc_ssc read; prior register shadow and permissions restored afterward')
        return report, state

    preemption.PreemptiblePeer = StartupGpioPeer
    boot.boot_experiment = experiment
    try:
        preemption.main()
    finally:
        preemption.PreemptiblePeer = original_peer
        boot.boot_experiment = original_experiment


if __name__ == '__main__':
    main()
