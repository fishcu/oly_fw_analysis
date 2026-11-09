#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Observe native parameter-bank copies without changing boot semantics.

The API-log replay exhausted its per-segment budget inside a finite 2548-word
copy. Entry/return landmarks split these long computations into bounded native
segments; no data, return values, hardware responses or IRQ rules are changed.
"""
import argparse
import hashlib
import json
from pathlib import Path

import penf_boot_emulator as boot
from penf_boot_api_log import ApiLogPeer
from penf_boot_core_idle import CoreIdleInterrupts
from penf_boot_audit import summarize
from penf_button_boot_probe import input_levels
from penf_emulator import ROOT


class ParameterInitPeer(ApiLogPeer):
    parameter_landmarks = {
        0x602f063e: 'parameter bank load entered',
        0x602f0677: 'parameter bank load returning',
        0x602f067a: 'parameter bank store entered',
        0x602f06b3: 'parameter bank store returning',
        0x602ba469: 'application parameter initialization entered',
        0x602ba4ed: 'application parameter initialization returning',
        0x602f0d1d: 'parameter reset descriptor entered',
        0x602f0d80: 'parameter reset descriptor returning',
        0x601a8b31: 'USTART3 parameter setup returning',
    }
    hooks = ApiLogPeer.hooks | set(parameter_landmarks)

    def handle(self, state, hooks, interrupts):
        pc = state.regs['pc']
        if pc in self.parameter_landmarks:
            state.events.append(dict(kind='milestone', name=self.parameter_landmarks[pc],
                entry=hex(pc), cpu=state.cpu, instructions=state.steps,
                d0=state.regs['d0'], d2=state.regs['d2'], d3=state.regs['d3']))
            return self.step(state, hooks)
        return super().handle(state, hooks, interrupts)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    sources = ('penf_boot_parameter_init.py', 'penf_boot_api_log.py', 'penf_boot_strobe_init.py',
               'penf_boot_display_init.py', 'penf_boot_usf_init.py', 'penf_boot_console_idle.py',
               'penf_boot_lens_init.py', 'penf_boot_application.py', 'penf_boot_core_idle.py',
               'penf_boot_after_alex.py', 'penf_alex_bulk_model.py', 'penf_button_boot_probe.py',
               'penf_boot_audit.py')
    extra = {'tools/'+p: hashlib.sha256((ROOT/'tools'/p).read_bytes()).hexdigest() for p in sources}
    controller, gpio, _ = input_levels(0, True)
    original_peer, original_irq = boot.AlexPeer, boot.RuntimeInterrupts
    boot.AlexPeer = lambda scenario: ParameterInitPeer(scenario, 'next', 0)
    boot.RuntimeInterrupts = CoreIdleInterrupts
    try:
        report, state = boot.boot_experiment(ideal_storage=True, erased_parameters=True,
            run_peers=True, timer_clock=True, counter_step=1000, controller_init=True,
            peripheral_reset=True, adc_clock=True, adc_sample=900, runtime_peers=True,
            runtime_irqs=300, serial_clock_word=0x200000, controller_input_bits=controller,
            gpio_inputs=gpio, input_counter=0, alex_peer='bulk', segments=10000)
    finally:
        boot.AlexPeer, boot.RuntimeInterrupts = original_peer, original_irq
    report['source_sha256'].update(extra)
    report['extension_scenario'] = dict(factory='ParameterInitPeer',
        baseline='ApiLogPeer: identical hardware, memory and scheduling assumptions',
        change='Observational landmarks at native parameter-bank copies and application initializer only')
    boot.write_gzip_json(args.out/'trace.json.gz', report)
    state.save_snapshot(args.out/'state.json.gz')
    summary = summarize(report)
    summary['alex_peer_scenario'] = report['alex_peer_scenario']
    (args.out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(dict(instructions=state.steps, final=summary['final']), indent=2))


if __name__ == '__main__':
    main()
