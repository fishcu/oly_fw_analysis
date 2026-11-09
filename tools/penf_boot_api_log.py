#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Continue USTART3 with its natively allocated API log mapped as bounded RAM.

Only the requested 16380 bytes are promoted, after allocation has executed.
The native store/clear and later settings access execute unchanged. Freeing,
reinitialization and unexpected allocation state stop for lifetime review.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import penf_boot_emulator as boot
from penf_boot_strobe_init import StrobeInitPeer
from penf_boot_core_idle import CoreIdleInterrupts
from penf_boot_audit import summarize
from penf_button_boot_probe import input_levels
from penf_emulator import ROOT


class ApiLogPeer(StrobeInitPeer):
    api_log_address = 0x61246700
    api_log_size = 16380
    api_landmarks = {
        0x601c928c: 'USTART3 application/input initializer returning',
        0x602dc671: 'USTART3 enters API subsystem initialization',
        0x601a7671: 'USTART3 API subsystem initialization returned',
        0x601a7697: 'USTART3 section wait returned',
        0x601a76ae: 'USTART3 sees USTART1 completion',
        0x600890f4: 'power-control initial delay returned',
        0x6008829a: 'power-control delay callback entered',
        0x600424ba: 'power-startup request completion dispatcher entered',
    }
    hooks = StrobeInitPeer.hooks | set(api_landmarks) | {0x602dfca8, 0x602dfcb9}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_log_mapped = False

    def handle(self, state, hooks, interrupts):
        pc = state.regs['pc']
        if pc == 0x602dfca8:
            address, size = self.api_log_address, self.api_log_size
            if (self.api_log_mapped or state.cpu != 0 or state.regs['a0'] != address or
                    self.reg(state, 0xa1c554c8) != 7 or
                    not (self.reg(state, 0xa1c556b4) & (1 << 7))):
                return self.stop(state, 'Unreviewed API log allocation or reinitialization')
            if any((r.capture or r.alias_of) and r.address < address+size and
                   address < r.address+len(r.data) for r in state.regions):
                return self.stop(state, 'API log allocation overlaps existing mutable storage')
            state.ram('api_log_allocation', address, b'\xa5'*size)
            self.api_log_mapped = True
            self.event(state, 'map native API log allocation', address=hex(address), bytes=size,
                slot=7, assumption='Native allocator chose this owned extent. Poisoned, non-executable RAM with coherent aliases; firmware must initialize it.')
            return self.step(state, hooks)
        if pc == 0x602dfcb9:
            if not self.api_log_mapped:
                return self.stop(state, 'API log clear returned without reviewed allocation')
            assert self.reg(state, 0x615fd92c) == self.api_log_address
            assert state.read(self.api_log_address, self.api_log_size) == bytes(self.api_log_size)
            self.event(state, 'native API log allocation cleared', address=hex(self.api_log_address),
                       bytes=self.api_log_size)
            return self.step(state, hooks)
        if pc == 0x600233fc and self.api_log_mapped and state.regs['a0'] in (
                self.api_log_address, self.api_log_address+0x40000000):
            return self.stop(state, 'API log allocation is being freed; lifetime review required')
        if pc in self.api_landmarks:
            state.events.append(dict(kind='milestone', name=self.api_landmarks[pc],
                entry=hex(pc), cpu=state.cpu, instructions=state.steps))
            return self.step(state, hooks)
        return super().handle(state, hooks, interrupts)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    sources = ('penf_boot_api_log.py', 'penf_boot_strobe_init.py', 'penf_boot_display_init.py',
               'penf_boot_usf_init.py', 'penf_boot_console_idle.py', 'penf_boot_lens_init.py',
               'penf_boot_application.py', 'penf_boot_core_idle.py', 'penf_boot_after_alex.py',
               'penf_alex_bulk_model.py', 'penf_button_boot_probe.py', 'penf_boot_audit.py')
    extra = {'tools/'+p: hashlib.sha256((ROOT/'tools'/p).read_bytes()).hexdigest() for p in sources}
    controller, gpio, _ = input_levels(0, True)
    original_peer, original_irq = boot.AlexPeer, boot.RuntimeInterrupts
    boot.AlexPeer = lambda scenario: ApiLogPeer(scenario, 'next', 0)
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
    report['extension_scenario'] = dict(factory='ApiLogPeer', low_memory='scoped zero', ok='held',
        core_8040='Scoped native write then park core; existing notifications can release it',
        timers='Existing timer IRQ model, only target cores at native kernel idle',
        memory='Exact native lens/API log allocations and twelve-byte shared display state',
        lens='Five instruction-scoped zero write sinks; no lens response/IRQ',
        console='Zero available input at native port-0 status reads only',
        usf='Three instruction-scoped writes of 1; requests/callbacks stop',
        strobe='Two scoped zero writes and first native configuration with temporary zero-based shadows; IRQ/transaction/completion stop',
        api_log='Native slot-7 allocation, 16380 bytes only; free/reinitialization stops')
    with gzip.open(args.out/'trace.json.gz', 'wt') as stream:
        json.dump(report, stream)
    state.save_snapshot(args.out/'state.json.gz')
    summary = summarize(report)
    summary['alex_peer_scenario'] = report['alex_peer_scenario']
    (args.out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(dict(instructions=state.steps, final=summary['final']), indent=2))


if __name__ == '__main__':
    main()
