#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Continue native boot after Alex, mapping only reviewed application storage.

The first record-buffer allocation is admitted after native allocation. Section
initializers and allocation lifetime are observed, not replaced. Unknown native
accesses/instructions retain strict stops. No camera/device access.
"""
import argparse
import hashlib
import json
from pathlib import Path

import penf_boot_emulator as boot
from penf_boot_core_idle import CoreIdlePeer, CoreIdleInterrupts
from penf_boot_audit import summarize
from penf_button_boot_probe import input_levels
from penf_emulator import ROOT


class ApplicationPeer(CoreIdlePeer):
    application_landmarks = {0x601a70fb:'USTART1 initial section wait returned',
        0x601a7130:'USTART1 requests USTART3',
        0x6016d5c3:'native startup record buffer initialized'}
    hooks = CoreIdlePeer.hooks | set(application_landmarks) | {
        0x6016d5b4, 0x600233fc, 0x6006db0b, 0x6006db0d}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.record_allocation = None

    def handle(self, state, hooks, interrupts):
        pc = state.regs['pc']
        if pc == 0x6016d5b4:
            address, size = state.regs['a0'], 16380
            assert self.record_allocation is None and address == 0x6123a640
            assert self.reg(state, 0xa1c556b4) & (1 << 4)
            assert not any(r.capture and r.address < address+size and address < r.address+len(r.data)
                           for r in state.regions)
            self.record_allocation = (address, size)
            state.ram('startup_record_allocation', address, b'\xa5'*size)
            self.event(state, 'map reviewed native record allocation', address=hex(address), bytes=size,
                       assumption='Allocated RAM starts poisoned; native initializer must fill it. Exact requested extent only; coherent cached/uncached aliases.')
            return self.step(state, hooks)
        if pc in self.application_landmarks:
            if pc == 0x6016d5c3:
                assert self.record_allocation is not None
                address, size = self.record_allocation
                assert self.reg(state, 0x6184e04c) == address
                assert state.read(address, size) == (bytes.fromhex('3f3f3f00')+bytes(16))*819
            state.events.append(dict(kind='milestone', name=self.application_landmarks[pc],
                                     entry=hex(pc), cpu=state.cpu, instructions=state.steps))
            return self.step(state, hooks)
        if pc == 0x600233fc:
            if self.record_allocation and state.regs['a0'] in (
                    self.record_allocation[0], self.record_allocation[0]+0x40000000):
                return self.stop(state, 'Reviewed record allocation is being freed; lifetime review required')
            return self.step(state, hooks)
        if pc in (0x6006db0b, 0x6006db0d):
            self.event(state, 'native section initializer call' if pc == 0x6006db0b
                       else 'native section initializer returned',
                       table_entry=hex(state.regs['a2']),
                       target=hex(self.reg(state, state.regs['a2'])))
            return self.step(state, hooks)
        return super().handle(state, hooks, interrupts)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    sources = ('penf_boot_application.py', 'penf_boot_core_idle.py', 'penf_boot_after_alex.py',
               'penf_alex_bulk_model.py', 'penf_button_boot_probe.py')
    extra = {'tools/'+p:hashlib.sha256((ROOT/'tools'/p).read_bytes()).hexdigest() for p in sources}
    controller, gpio, _ = input_levels(0, True)
    original_peer, original_irq = boot.AlexPeer, boot.RuntimeInterrupts
    boot.AlexPeer = lambda scenario: ApplicationPeer(scenario, 'next', 0)
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
    report['extension_scenario'] = dict(factory='ApplicationPeer', low_memory='scoped zero', ok='held',
        core_8040='Scoped native write then park core; existing notifications can release it',
        timers='Existing timer IRQ model, only target cores at native kernel idle',
        memory='Exact 16380-byte native record allocation admitted after allocator return')
    boot.write_gzip_json(args.out/'trace.json.gz', report)
    state.save_snapshot(args.out/'state.json.gz')
    summary = summarize(report)
    summary['alex_peer_scenario'] = report['alex_peer_scenario']
    (args.out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(dict(instructions=state.steps, final=summary['final']), indent=2))


if __name__ == '__main__':
    main()
