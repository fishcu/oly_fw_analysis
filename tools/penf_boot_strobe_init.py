#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Continue boot through the first reviewed strobe-controller configuration.

Temporary register shadows admit configuration only. Reset values are a stated
zero hypothesis, not measured hardware. No flash firing, completion or IRQ is
modeled. A repeated configuration or a transaction entry stops for review.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import penf_boot_emulator as boot
from penf_boot_display_init import DisplayStatePeer
from penf_boot_core_idle import CoreIdleInterrupts
from penf_boot_audit import summarize
from penf_button_boot_probe import input_levels
from penf_emulator import ROOT, Region


class StrobeInitPeer(DisplayStatePeer):
    reset_writes = {0x602cc72d: 0x9b900000, 0x602cc741: 0x9b900004}
    # Exact registers used by the reviewed descriptor (the +8 pointer is null).
    config_offsets = (0x08, 0x0c, 0x10, 0x14, 0x18, 0x1c, 0x20, 0x24,
                      0x28, 0x2c, 0x30, 0x44, 0x48, 0x4c, 0x50, 0x54,
                      0x58, 0x5c, 0x60, 0x64, 0x68, 0x6c)
    boundaries = {0x602ccf43: 'Strobe IRQ', 0x602ccfd7: 'Strobe deferred completion',
                  0x602ccd77: 'Strobe transaction start'}
    strobe_landmarks = {0x601a7278: 'native strobe application initializer returned',
                 0x601a72ad: 'USTART1 requests USR_PCHG'}
    hooks = DisplayStatePeer.hooks | set(reset_writes) | set(boundaries) | set(strobe_landmarks) | {
        0x602cc75f, 0x602d3c48}

    def handle(self, state, hooks, interrupts):
        pc = state.regs['pc']
        if pc in self.boundaries:
            return self.stop(state, self.boundaries[pc] + ' requires hardware/request review')
        if pc in self.reset_writes:
            address = self.reset_writes[pc]
            if state.regs['d0'] != 0 or any(
                    r.address < address+4 and address < r.address+len(r.data) for r in state.regions):
                return self.stop(state, 'Unreviewed strobe reset value or mapping')
            name = 'scoped_strobe_reset'
            state.regions.append(Region(name, address, b'\xa5'*4, 'w', True))
            try:
                accepted = self.step(state, hooks)
                if accepted:
                    assert state.read(address, 4) == bytes(4)
                    self.event(state, 'native strobe reset write accepted',
                               instruction=hex(pc), address=hex(address), value=0)
                return accepted
            finally:
                state.regions = [r for r in state.regions if r.name != name]
        if pc == 0x602cc75f:
            if (state.regs['a0'], state.regs['mdr']) != (0x6188994c, 0x602d3c48):
                return self.stop(state, 'Unreviewed strobe configuration caller/descriptor')
            if getattr(self, 'strobe_config_seen', False):
                return self.stop(state, 'Repeated strobe configuration requires review')
            expected = bytes.fromhex('98988861a89888610000000000000000')
            first = bytearray(16)
            first[12] = 7
            second = bytearray(72)
            second[3] = 1
            if (state.read(0x6188994c, 16) != expected or
                    state.read(0x61889898, 16) != first or
                    state.read(0x618898a8, 72) != second):
                return self.stop(state, 'Strobe configuration differs from reviewed native startup data')
            addresses = [0x9b900000+x for x in self.config_offsets]
            if any(r.address < a+4 and a < r.address+len(r.data)
                   for a in addresses for r in state.regions):
                return self.stop(state, 'Existing strobe configuration mapping requires review')
            self.strobe_config_seen = True
            for a in addresses:
                state.regions.append(Region(f'scoped_strobe_config_{a:x}', a, bytes(4), 'rw', True))
            self.event(state, 'map first strobe configuration shadows', registers=[hex(a) for a in addresses],
                assumption='Zero initial register readbacks. Native read/modify/write configuration only; all mappings removed at return. Status acknowledgement is captured as a write, not a pending event. No IRQ, firing or completion.')
            return self.step(state, hooks)
        if pc == 0x602d3c48:
            if not getattr(self, 'strobe_config_seen', False):
                return self.stop(state, 'Strobe configuration return without scoped mappings')
            registers = {hex(0x9b900000+x): hex(self.reg(state, 0x9b900000+x))
                         for x in self.config_offsets}
            assert self.reg(state, 0x6188933c) == 0x6188994c
            self.event(state, 'native strobe configuration returned', registers=registers,
                       descriptor='0x6188994c', callback=hex(self.reg(state, 0x61889958)))
            state.regions = [r for r in state.regions if not r.name.startswith('scoped_strobe_config_')]
            return self.step(state, hooks)
        if pc in self.strobe_landmarks:
            state.events.append(dict(kind='milestone', name=self.strobe_landmarks[pc],
                                     entry=hex(pc), cpu=state.cpu, instructions=state.steps))
            return self.step(state, hooks)
        return super().handle(state, hooks, interrupts)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    sources = ('penf_boot_strobe_init.py', 'penf_boot_display_init.py', 'penf_boot_usf_init.py',
               'penf_boot_console_idle.py', 'penf_boot_lens_init.py', 'penf_boot_application.py',
               'penf_boot_core_idle.py', 'penf_boot_after_alex.py', 'penf_alex_bulk_model.py',
               'penf_button_boot_probe.py')
    extra = {'tools/'+p: hashlib.sha256((ROOT/'tools'/p).read_bytes()).hexdigest() for p in sources}
    controller, gpio, _ = input_levels(0, True)
    original_peer, original_irq = boot.AlexPeer, boot.RuntimeInterrupts
    boot.AlexPeer = lambda scenario: StrobeInitPeer(scenario, 'next', 0)
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
    report['extension_scenario'] = dict(factory='StrobeInitPeer', low_memory='scoped zero', ok='held',
        core_8040='Scoped native write then park core; existing notifications can release it',
        timers='Existing timer IRQ model, only target cores at native kernel idle',
        memory='Exact native lens log allocation and twelve-byte shared display state',
        lens='Five instruction-scoped zero write sinks; no lens response/IRQ',
        console='Zero available input at native port-0 status reads only',
        usf='Three instruction-scoped writes of 1; requests/callbacks stop',
        strobe='Two scoped zero writes and first native configuration with temporary zero-based shadows; IRQ/transaction/completion stop')
    with gzip.open(args.out/'trace.json.gz', 'wt') as stream:
        json.dump(report, stream)
    state.save_snapshot(args.out/'state.json.gz')
    summary = summarize(report)
    summary['alex_peer_scenario'] = report['alex_peer_scenario']
    (args.out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(dict(instructions=state.steps, final=summary['final']), indent=2))


if __name__ == '__main__':
    main()
