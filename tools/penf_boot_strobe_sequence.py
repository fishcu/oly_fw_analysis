#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Fresh A-mode PEN-F boot with two scoped strobe-sequencer control writes.

Accepts only the reviewed initialization writes, with no readback, interrupt,
or completion invented. Physical meanings/effects of the registers remain
unmeasured. Any later access needs its own review.
"""
import hashlib

import penf_boot_emulator as boot
import penf_boot_mode_dial as mode
from penf_emulator import ROOT


class StrobeSequencePeer(mode.ModeDialPeer):
    control_writes = {
        0x60147bdc: (0x9ba0001c, 2, 0x602daac1),
        0x602ccf27: (0x9b900024, 1, 0x602daac8),
    }
    sequence_landmarks = {
        0x602daa81:'STB_SEQ lower initialization returned',
        0x601a74e1:'USTART1 STB_SEQ initialization returned',
        0x601a750e:'USTART1 reaches USR_FAST event-2 post',
    }
    hooks = mode.ModeDialPeer.hooks | set(control_writes) | set(sequence_landmarks)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sequence_writes_seen = []

    def handle(self, state, hooks, interrupts):
        pc = state.regs['pc']
        try:
            if pc in self.control_writes:
                address, value, return_pc = self.control_writes[pc]
                expected = list(self.control_writes)
                if (state.cpu != 0 or self.sequence_writes_seen != expected[:len(self.sequence_writes_seen)]
                        or len(self.sequence_writes_seen) >= len(expected)
                        or pc != expected[len(self.sequence_writes_seen)]
                        or state.regs['d0'] != value or state.regs['mdr'] != return_pc):
                    raise ValueError('Unreviewed strobe-sequencer write context/order/value')
                if any(r.address < address+4 and address < r.address+len(r.data) for r in state.regions):
                    raise ValueError('Strobe-sequencer control register already mapped')
                state.register(address, 'w', 0)
                try:
                    r = state.run(hooks-{pc}, limit=1)
                    written = self.reg(state, address)
                finally:
                    state.regions = [r for r in state.regions if r.address != address]
                if r['status'] != 'instruction_limit' or r['completed'] != 1 or written != value:
                    return False
                self.sequence_writes_seen.append(pc)
                self.event(state, 'scoped native strobe-sequencer control write',
                    address=hex(address), value=value,
                    assumption='Write accepted; no hardware effect, readback or completion modeled. Mapping removed immediately.')
                return True
            if pc in self.sequence_landmarks:
                state.events.append(dict(kind='milestone', name=self.sequence_landmarks[pc],
                    entry=hex(pc),cpu=state.cpu,instructions=state.steps))
                return self.step(state,hooks)
            return super().handle(state,hooks,interrupts)
        except ValueError as exc:
            return self.stop(state,'Strobe-sequencer context needs review',reason=str(exc))


def main():
    old_peer = mode.ModeDialPeer
    original_experiment = boot.boot_experiment
    source = 'tools/penf_boot_strobe_sequence.py'
    digest = hashlib.sha256((ROOT/source).read_bytes()).hexdigest()
    def experiment(*args, **kwargs):
        report,state = original_experiment(*args,**kwargs)
        report['source_sha256'][source]=digest
        report['strobe_sequence_scenario']=dict(
            writes={hex(k):[hex(a),v,hex(ret)] for k,(a,v,ret) in StrobeSequencePeer.control_writes.items()},
            scope='Two instruction-scoped write acceptances in initialization. Native tasks/flags/queues run; hardware side effects unknown.')
        return report,state
    mode.ModeDialPeer=StrobeSequencePeer
    boot.boot_experiment=experiment
    try:
        mode.main()
    finally:
        mode.ModeDialPeer=old_peer
        boot.boot_experiment=original_experiment

if __name__=='__main__':
    main()
