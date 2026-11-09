#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Continue native boot through the three reviewed USF initialization writes.

The writes are instruction-scoped sinks. USF execution requests, callbacks,
reads and other hardware accesses are not modeled. No camera is accessed.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import penf_boot_emulator as boot
from penf_boot_console_idle import ConsoleIdlePeer
from penf_boot_core_idle import CoreIdleInterrupts
from penf_boot_audit import summarize
from penf_button_boot_probe import input_levels
from penf_emulator import ROOT, Region


class UsfInitPeer(ConsoleIdlePeer):
    init_writes = {0x600906a1: 0x9b800008, 0x600906a7: 0x9b800124,
                   0x600906ad: 0x9b80012c}
    usf_boundaries = {0x600906ca: 'USF synchronous execution request',
                      0x6009071b: 'USF asynchronous execution request',
                      0x60090757: 'USF BC callback'}
    startup_landmarks = {0x601a719c: 'native USF initializer returned',
                         0x601a7644: 'USTART3 entry actually executes',
                         0x601a7242: 'USTART1 calls display initializer',
                         0x601a7249: 'native display initializer returned',
                         0x601a7250: 'USTART1 requests DISPLAY'}
    hooks = ConsoleIdlePeer.hooks | set(init_writes) | set(usf_boundaries) | set(startup_landmarks)

    def handle(self, state, hooks, interrupts):
        pc = state.regs['pc']
        if pc in self.init_writes:
            address = self.init_writes[pc]
            if state.regs['d0'] != 1:
                return self.stop(state, 'Unreviewed USF initialization value', value=state.regs['d0'])
            if any(r.address < address + 4 and address < r.address + len(r.data)
                   for r in state.regions):
                return self.stop(state, 'Unreviewed existing USF register mapping', address=hex(address))
            name = 'scoped_usf_init_write'
            state.regions.append(Region(name, address, b'\xa5'*4, 'w', True))
            try:
                accepted = self.step(state, hooks)
                if accepted:
                    assert state.read(address, 4) == b'\x01\0\0\0'
                    self.event(state, 'native USF initializer write accepted',
                        instruction=hex(pc), address=hex(address), value=1,
                        assumption='Instruction-scoped write sink. Hardware effects, timing and completion remain unknown; no IRQ or callback supplied.')
                return accepted
            finally:
                state.regions = [r for r in state.regions if r.name != name]
        if pc in self.usf_boundaries:
            return self.stop(state, self.usf_boundaries[pc] + ' requires hardware/lifetime review')
        if pc in self.startup_landmarks:
            if pc == 0x601a719c:
                assert state.read(0x616fd2d4, 2) == b'\x28\0'
                assert self.reg(state, 0x616fd2e0) == 0x616fd2e4
            state.events.append(dict(kind='milestone', name=self.startup_landmarks[pc],
                                     entry=hex(pc), cpu=state.cpu, instructions=state.steps))
            return self.step(state, hooks)
        return super().handle(state, hooks, interrupts)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    sources = ('penf_boot_usf_init.py', 'penf_boot_console_idle.py', 'penf_boot_lens_init.py',
               'penf_boot_application.py', 'penf_boot_core_idle.py', 'penf_boot_after_alex.py',
               'penf_alex_bulk_model.py', 'penf_button_boot_probe.py')
    extra = {'tools/'+p: hashlib.sha256((ROOT/'tools'/p).read_bytes()).hexdigest() for p in sources}
    controller, gpio, _ = input_levels(0, True)
    original_peer, original_irq = boot.AlexPeer, boot.RuntimeInterrupts
    boot.AlexPeer = lambda scenario: UsfInitPeer(scenario, 'next', 0)
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
    report['extension_scenario'] = dict(factory='UsfInitPeer', low_memory='scoped zero', ok='held',
        core_8040='Scoped native write then park core; existing notifications can release it',
        timers='Existing timer IRQ model, only target cores at native kernel idle',
        memory='Exact 16380-byte native lens log allocation admitted after allocator return',
        lens='Five instruction-scoped zero write sinks; no lens status/completion/IRQ supplied',
        console='Zero available input at native port-0 status reads only',
        usf='Three instruction-scoped writes of 1. Requests/callbacks stop; no hardware completion supplied.')
    with gzip.open(args.out/'trace.json.gz', 'wt') as stream:
        json.dump(report, stream)
    state.save_snapshot(args.out/'state.json.gz')
    summary = summarize(report)
    summary['alex_peer_scenario'] = report['alex_peer_scenario']
    (args.out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(dict(instructions=state.steps, final=summary['final']), indent=2))


if __name__ == '__main__':
    main()
