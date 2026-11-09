#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Continue boot with the exact native display-state storage mapped as RAM.

Only 8ff001a4..8ff001af is added, at its native initializer. Its current,
previous and auxiliary words are initialized by firmware, not injected by
the host. Display hardware and physical callback delivery remain unmodeled.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import penf_boot_emulator as boot
from penf_boot_usf_init import UsfInitPeer
from penf_boot_core_idle import CoreIdleInterrupts
from penf_boot_audit import summarize
from penf_button_boot_probe import input_levels
from penf_emulator import ROOT, Region


class DisplayStatePeer(UsfInitPeer):
    display_landmarks = {0x603160f8: 'DISPLAY task entry actually executes',
                         0x6031a115: 'display helper task 80 actually executes'}
    hooks = UsfInitPeer.hooks | set(display_landmarks) | {
        0x60042664, 0x60042681, 0x60199329, 0x60199349}

    def handle(self, state, hooks, interrupts):
        pc = state.regs['pc']
        if pc == 0x60042664:
            address, size = 0x8ff001a4, 12
            if state.regs['mdr'] != 0x60315f9d:
                return self.stop(state, 'Display state initializer from an unreviewed caller')
            if any(r.address < address+size and address < r.address+len(r.data)
                   for r in state.regions):
                return self.stop(state, 'Display state storage already mapped; review repeated initialization')
            state.regions.append(Region('display_shared_state', address, b'\xa5'*size, 'rw', True))
            self.event(state, 'map native display state storage', address=hex(address), bytes=size,
                assumption='Shared writable non-executable RAM. Poisoned before native initialization; no peripheral response, callback or completion injected.')
            return self.step(state, hooks)
        if pc == 0x60042681:
            assert state.read(0x8ff001a4, 12) == bytes.fromhex('703000000000000000000000')
            self.event(state, 'native display state initialized', current='0x3070', previous=0, auxiliary=0)
            return self.step(state, hooks)
        if pc in self.display_landmarks:
            state.events.append(dict(kind='milestone', name=self.display_landmarks[pc],
                                     entry=hex(pc), cpu=state.cpu, instructions=state.steps))
            return self.step(state, hooks)
        if pc in (0x60199329, 0x60199349):
            self.event(state, 'native input destination setter observed' if pc == 0x60199329
                       else 'native input destination setter returning',
                       destination=hex(self.reg(state, 0xa1c58028)),
                       retained_marker=hex(self.reg(state, 0xa1c57fd4)),
                       argument=state.regs['d0'] if pc == 0x60199329 else None)
            return self.step(state, hooks)
        return super().handle(state, hooks, interrupts)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    sources = ('penf_boot_display_init.py', 'penf_boot_usf_init.py', 'penf_boot_console_idle.py',
               'penf_boot_lens_init.py', 'penf_boot_application.py', 'penf_boot_core_idle.py',
               'penf_boot_after_alex.py', 'penf_alex_bulk_model.py', 'penf_button_boot_probe.py')
    extra = {'tools/'+p: hashlib.sha256((ROOT/'tools'/p).read_bytes()).hexdigest() for p in sources}
    controller, gpio, _ = input_levels(0, True)
    original_peer, original_irq = boot.AlexPeer, boot.RuntimeInterrupts
    boot.AlexPeer = lambda scenario: DisplayStatePeer(scenario, 'next', 0)
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
    report['extension_scenario'] = dict(factory='DisplayStatePeer', low_memory='scoped zero', ok='held',
        core_8040='Scoped native write then park core; existing notifications can release it',
        timers='Existing timer IRQ model, only target cores at native kernel idle',
        memory='Exact 16380-byte native lens log allocation admitted after allocator return',
        lens='Five instruction-scoped zero write sinks; no lens status/completion/IRQ supplied',
        console='Zero available input at native port-0 status reads only',
        usf='Three instruction-scoped writes of 1. Requests/callbacks stop; no hardware completion supplied.',
        display='Twelve bytes of poisoned shared RAM, mapped at native initializer; no display hardware modeled.')
    with gzip.open(args.out/'trace.json.gz', 'wt') as stream:
        json.dump(report, stream)
    state.save_snapshot(args.out/'state.json.gz')
    summary = summarize(report)
    summary['alex_peer_scenario'] = report['alex_peer_scenario']
    (args.out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(dict(instructions=state.steps, final=summary['final']), indent=2))


if __name__ == '__main__':
    main()
