#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Conditional continuation: treat reviewed 8040 writes as core-idle points.

Only existing native-kernel-idle sites receive modeled timer interrupts. A peer
parked at 8040 can resume through an existing modeled native notification; its
real clock/sleep/wakeup semantics remain unknown. No camera access.
"""
import argparse
import hashlib
import json
from pathlib import Path

import penf_boot_emulator as boot
from penf_boot_after_alex import PostAlexPeer
from penf_boot_audit import summarize
from penf_button_boot_probe import input_levels
from penf_emulator import ROOT, Region
from penf_runtime_model import RuntimeInterrupts


class CoreIdleInterrupts(RuntimeInterrupts):
    def timer(self, state):
        for offset in range(3):
            cpu = (self.next_cpu+offset) % 3
            regs = state.regs if cpu == state.cpu else state.cpu_regs.get(cpu, {})
            if regs.get('pc') == 0x6003718b:
                self.next_cpu = cpu
                return super().timer(state)
        return False


class CoreIdlePeer(PostAlexPeer):
    hooks = PostAlexPeer.hooks | {0x60070b72}

    def handle(self, state, hooks, interrupts):
        pc = state.regs['pc']
        if pc in (0x600706ec, 0x60070b72):
            assert state.regs['d0'] == 8
            assert state.cpu == (1 if pc == 0x600706ec else 2)
            assert not any(r.address == 0x8040 for r in state.regions)
            state.regions.append(Region('scoped_private_core_idle_8040', 0x8040, bytes(2), 'w', True))
            self.event(state, 'hypothetical private core idle request',
                       assumption='Native write executes, then park this core until a modeled native notification. Timer IRQs remain restricted to kernel idle.')
            accepted = self.step(state, hooks)
            state.regions = [r for r in state.regions if r.name != 'scoped_private_core_idle_8040']
            if not accepted:
                return False
            if state.schedule_wait('hypothetical private 8040 idle'):
                return True
            if interrupts and interrupts.timer(state):
                return True
            return self.stop(state, 'No reviewed wake source for parked cores')
        return super().handle(state, hooks, interrupts)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    sources = ('penf_boot_core_idle.py', 'penf_boot_after_alex.py', 'penf_alex_bulk_model.py', 'penf_button_boot_probe.py')
    extra = {'tools/'+p:hashlib.sha256((ROOT/'tools'/p).read_bytes()).hexdigest() for p in sources}
    controller, gpio, _ = input_levels(0, True)
    original_peer, original_irq = boot.AlexPeer, boot.RuntimeInterrupts
    boot.AlexPeer = lambda scenario: CoreIdlePeer(scenario, 'next', 0)
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
    report['extension_scenario'] = dict(factory='CoreIdlePeer', low_memory='scoped zero', ok='held',
        core_8040='Scoped native write then park core; existing notifications can release it',
        timers='Existing timer IRQ model, only target cores at native kernel idle')
    boot.write_gzip_json(args.out/'trace.json.gz', report)
    state.save_snapshot(args.out/'state.json.gz')
    summary = summarize(report)
    summary['alex_peer_scenario'] = report['alex_peer_scenario']
    (args.out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(dict(instructions=state.steps, final=summary['final']), indent=2))


if __name__ == '__main__':
    main()
