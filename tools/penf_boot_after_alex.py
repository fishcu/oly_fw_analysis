#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Continue after Alex with a scoped core-control write hypothesis.

The native CPUSW write of 8 to private halfword 8040 is accepted. Physical
sleep/clock/wake effects are not simulated. All other unknown accesses stop.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import penf_boot_emulator as boot
from penf_alex_bulk_model import AlexBulkPeer
from penf_boot_audit import summarize
from penf_button_boot_probe import input_levels
from penf_emulator import ROOT, Region


class PostAlexPeer(AlexBulkPeer):
    hooks = AlexBulkPeer.hooks | {0x600706ec, 0x60070e46}

    def handle(self, state, hooks, interrupts):
        pc = state.regs['pc']
        if pc == 0x600706ec:
            assert state.regs['d0'] == 8
            if not any(r.address == 0x8040 for r in state.regions):
                state.regions.append(Region('private_core_control_8040', 0x8040, bytes(2), 'w', True))
            self.event(state, 'core control halfword write accepted', address='0x8040', value=8,
                       assumption='Write shadow only. Exact SoC function and physical sleep/clock/wake effects remain unverified.')
            return self.step(state, hooks)
        if pc == 0x60070e46:
            state.events.append(dict(kind='milestone', name='native Alex completion consumer reached',
                                     entry=hex(pc), cpu=state.cpu, instructions=state.steps))
            return self.step(state, hooks)
        return super().handle(state, hooks, interrupts)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    sources = ('penf_boot_after_alex.py', 'penf_alex_bulk_model.py', 'penf_button_boot_probe.py')
    extra = {'tools/'+p:hashlib.sha256((ROOT/'tools'/p).read_bytes()).hexdigest() for p in sources}
    controller, gpio, _ = input_levels(0, True)
    original = boot.AlexPeer
    boot.AlexPeer = lambda scenario: PostAlexPeer(scenario, 'next', 0)
    try:
        report, state = boot.boot_experiment(ideal_storage=True, erased_parameters=True,
            run_peers=True, timer_clock=True, counter_step=1000, controller_init=True,
            peripheral_reset=True, adc_clock=True, adc_sample=900, runtime_peers=True,
            runtime_irqs=300, serial_clock_word=0x200000, controller_input_bits=controller,
            gpio_inputs=gpio, input_counter=0, alex_peer='bulk', segments=10000)
    finally:
        boot.AlexPeer = original
    report['source_sha256'].update(extra)
    report['extension_scenario'] = dict(factory='PostAlexPeer', low_memory='scoped zero', ok='held',
                                       core_8040='Accept write 8; no physical halt/clock/wake effects')
    with gzip.open(args.out/'trace.json.gz', 'wt') as stream:
        json.dump(report, stream)
    state.save_snapshot(args.out/'state.json.gz')
    summary = summarize(report)
    summary['alex_peer_scenario'] = report['alex_peer_scenario']
    (args.out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(dict(instructions=state.steps, final=summary['final'],
                         stages=report['alex_peer_scenario']['stages']), indent=2))


if __name__ == '__main__':
    main()
