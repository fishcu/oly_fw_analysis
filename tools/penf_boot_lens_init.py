#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Continue native startup through five reviewed lens-interface zero writes.

These are instruction-scoped write sinks, not a simulated working lens. Native
initializers, IRQ registration and callback registration execute unchanged.
Unknown reads and an unexpected lens IRQ entry stop. No device access.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import penf_boot_emulator as boot
from penf_boot_application import ApplicationPeer
from penf_boot_core_idle import CoreIdleInterrupts
from penf_boot_audit import summarize
from penf_button_boot_probe import input_levels
from penf_emulator import ROOT, Region


class LensInitPeer(ApplicationPeer):
    zero_writes = {0x6017cb31:0x9bf00068, 0x6017cb37:0x9bb00000,
                   0x6017cb3d:0x9bb00004, 0x6017e366:0x9bb00198,
                   0x6017e36e:0x9bb0019c}
    lens_landmarks = {0x6017cb48:'native lens interface initializer returned',
        0x60041fc8:'native lens subsystem initializer returned',
        0x60041fdc:'initial task requests LENS_MAIN',
        0x60041ff7:'initial task requests LENS_ASKDATA',
        0x60042021:'initial task publishes startup completion',
        0x601a7285:'USTART1 checks initial-task completion'}
    hooks = ApplicationPeer.hooks | set(zero_writes) | set(lens_landmarks) | {
        0x6017cb0b, 0x6017c895, 0x6017cf68}

    def handle(self, state, hooks, interrupts):
        pc = state.regs['pc']
        if pc in self.zero_writes:
            address = self.zero_writes[pc]
            assert state.regs['d0'] == 0
            assert not any(r.address <= address < r.address+len(r.data) for r in state.regions)
            name = 'scoped_lens_zero_write'
            state.regions.append(Region(name, address, b'\xa5'*4, 'w', True))
            try:
                accepted = self.step(state, hooks)
                if accepted:
                    assert state.read(address, 4) == bytes(4)
                    self.event(state, 'native lens interface zero write accepted',
                        instruction=hex(pc), address=hex(address), value=0,
                        assumption='Instruction-scoped write sink only. No read response, lens completion or IRQ supplied; physical effects unknown.')
                return accepted
            finally:
                state.regions = [r for r in state.regions if r.name != name]
        if pc in self.lens_landmarks:
            state.events.append(dict(kind='milestone', name=self.lens_landmarks[pc],
                                     entry=hex(pc), cpu=state.cpu, instructions=state.steps))
            return self.step(state, hooks)
        if pc == 0x6017cb0b:
            assert (state.regs['d0'], state.regs['d1'], state.regs['a0']) == (3, 3, 0x6017cf68)
            self.event(state, 'native lens IRQ handler registration', irq=3, priority=3,
                       handler='0x6017cf68', assumption='Registration executes natively; no lens IRQ is injected.')
            return self.step(state, hooks)
        if pc == 0x6017c895:
            assert (state.regs['d0'], state.regs['d1'], state.regs['a0']) == (0x121c, 3, 0x6017c8b4)
            self.event(state, 'native lens callback registration', selector='0x121c',
                       argument=3, callback='0x6017c8b4')
            return self.step(state, hooks)
        if pc == 0x6017cf68:
            return self.stop(state, 'Lens IRQ handler entered without a reviewed lens hardware model')
        return super().handle(state, hooks, interrupts)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    sources = ('penf_boot_lens_init.py', 'penf_boot_application.py', 'penf_boot_core_idle.py',
               'penf_boot_after_alex.py', 'penf_alex_bulk_model.py', 'penf_button_boot_probe.py')
    extra = {'tools/'+p:hashlib.sha256((ROOT/'tools'/p).read_bytes()).hexdigest() for p in sources}
    controller, gpio, _ = input_levels(0, True)
    original_peer, original_irq = boot.AlexPeer, boot.RuntimeInterrupts
    boot.AlexPeer = lambda scenario: LensInitPeer(scenario, 'next', 0)
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
    report['extension_scenario'] = dict(factory='LensInitPeer', low_memory='scoped zero', ok='held',
        core_8040='Scoped native write then park core; existing notifications can release it',
        timers='Existing timer IRQ model, only target cores at native kernel idle',
        memory='Exact 16380-byte native lens log allocation admitted after allocator return',
        lens='Five instruction-scoped zero write sinks; no lens status/completion/IRQ supplied')
    with gzip.open(args.out/'trace.json.gz', 'wt') as stream:
        json.dump(report, stream)
    state.save_snapshot(args.out/'state.json.gz')
    summary = summarize(report)
    summary['alex_peer_scenario'] = report['alex_peer_scenario']
    (args.out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(dict(instructions=state.steps, final=summary['final']), indent=2))


if __name__ == '__main__':
    main()
