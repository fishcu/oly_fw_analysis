#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Continue startup with no input arriving at the reviewed diagnostic port.

Only the two native receive-availability reads may observe zero, at port 0.
Native shell polling, task waits and scheduling still run; command execution
and other peripheral accesses are not modeled. No camera access.
"""
import argparse
from dataclasses import replace
import gzip
import hashlib
import json
from pathlib import Path

import penf_boot_emulator as boot
from penf_boot_lens_init import LensInitPeer
from penf_boot_core_idle import CoreIdleInterrupts
from penf_boot_audit import summarize
from penf_button_boot_probe import input_levels
from penf_emulator import ROOT, Region


class ConsoleIdlePeer(LensInitPeer):
    hooks = LensInitPeer.hooks | {0x6006d25e, 0x6006d23b}

    def handle(self, state, hooks, interrupts):
        pc = state.regs['pc']
        if pc in (0x6006d25e, 0x6006d23b):
            address = 0x9870000c
            assert state.regs['a0'] == address
            assert state.read(0x8ff0007c, 1) == b'\0'
            overlapping = [r for r in state.regions if r.address <= address < r.address+len(r.data)]
            old = overlapping[0] if overlapping else None
            if overlapping and not (len(overlapping) == 1 and old.address == address and
                    len(old.data) == 4 and old.permissions == 'w' and old.alias_of is None):
                return self.stop(state, 'Unreviewed diagnostic status mapping',
                    mappings=[dict(name=r.name, address=hex(r.address), bytes=len(r.data),
                                   permissions=r.permissions) for r in overlapping])
            name = 'scoped_empty_console_receive_status'
            if old is None:
                state.regions.append(Region(name, address, bytes(4), 'r'))
            else:
                # Boot has already admitted descriptor-listed configuration writes.
                # Supply a status value only for this instruction, retaining its
                # original write shadow and permissions afterward.
                state.regions = [replace(r, data=bytes(4), permissions='r')
                                 if r is old else r for r in state.regions]
            self.event(state, 'diagnostic receive availability is zero', address=hex(address),
                assumption='No diagnostic bytes arrive at selected port 0. Native read/poll/wait executes; no shell command or interrupt is supplied.')
            try:
                return self.step(state, hooks)
            finally:
                if old is None:
                    state.regions = [r for r in state.regions if r.name != name]
                else:
                    state.regions = [old if r.name == old.name else r for r in state.regions]
        return super().handle(state, hooks, interrupts)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    sources = ('penf_boot_console_idle.py', 'penf_boot_lens_init.py', 'penf_boot_application.py',
               'penf_boot_core_idle.py', 'penf_boot_after_alex.py', 'penf_alex_bulk_model.py',
               'penf_button_boot_probe.py')
    extra = {'tools/'+p:hashlib.sha256((ROOT/'tools'/p).read_bytes()).hexdigest() for p in sources}
    controller, gpio, _ = input_levels(0, True)
    original_peer, original_irq = boot.AlexPeer, boot.RuntimeInterrupts
    boot.AlexPeer = lambda scenario: ConsoleIdlePeer(scenario, 'next', 0)
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
    report['extension_scenario'] = dict(factory='ConsoleIdlePeer', low_memory='scoped zero', ok='held',
        core_8040='Scoped native write then park core; existing notifications can release it',
        timers='Existing timer IRQ model, only target cores at native kernel idle',
        memory='Exact 16380-byte native lens log allocation admitted after allocator return',
        lens='Five instruction-scoped zero write sinks; no lens status/completion/IRQ supplied',
        console='Zero available input at native port-0 status reads only')
    with gzip.open(args.out/'trace.json.gz', 'wt') as stream:
        json.dump(report, stream)
    state.save_snapshot(args.out/'state.json.gz')
    summary = summarize(report)
    summary['alex_peer_scenario'] = report['alex_peer_scenario']
    (args.out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(dict(instructions=state.steps, final=summary['final']), indent=2))


if __name__ == '__main__':
    main()
