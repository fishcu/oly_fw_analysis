#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Continue fresh boot with scoped reads of the retained media-state registers."""
import hashlib
from dataclasses import replace

import penf_boot_emulator as boot
import penf_boot_section_completion as completion
from penf_button_boot_probe import input_levels
from penf_emulator import ROOT


class RetainedStatePeer(completion.SectionCompletionPeer):
    retained_register_reads = {0x601a8932: 0x98e00060, 0x6007d89a: 0x98e00000,
             0x6007d89b: 0x98e00000, 0x601a8941: 0x98e00054}
    retained_landmarks = {
        0x601a7376: 'USTART1 retained media-state consumer returned',
        0x601a7389: 'USTART1 begins zoom initialization',
        0x601a73b8: 'USTART1 begins UI output initialization',
        0x601a73e7: 'USTART1 continues after UI_OUT launch',
        0x601a74fc: 'USTART1 calls post-strobe initialization',
    }
    hooks = completion.SectionCompletionPeer.hooks | set(retained_register_reads) | set(retained_landmarks) | {0x601a88cf}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.retained_active = False
        self.retained_reads = []
        self.retained_finished = False

    def sample(self, state, hooks):
        pc = state.regs['pc']
        address = self.retained_register_reads[pc]
        order = list(self.retained_register_reads)
        if (state.cpu != 0 or not self.retained_active
                or self.retained_reads != order[:len(self.retained_reads)]
                or len(self.retained_reads) >= len(order)
                or pc != order[len(self.retained_reads)]):
            raise ValueError('Unreviewed retained-state read order/context')
        if pc in (0x6007d89a, 0x6007d89b) and state.regs['a0'] != address:
            raise ValueError('Retained-byte pointer differs')
        existing = [r for r in state.regions if r.address == address]
        if address == 0x98e00054:
            if existing:
                raise ValueError('Unexpected preexisting live latch mapping')
            old = None
            value = 0  # No latched transition; physical latch behavior unmeasured.
        else:
            if len(existing) != 1 or existing[0].permissions != 'w':
                raise ValueError('Expected a write-only controller shadow')
            old = existing[0]
            value = int.from_bytes(old.data, 'little')
            if address == 0x98e00060:
                high = (input_levels(0, True)[0] >> 2) & 1
                value = (value & 0x7fffffff) | (high << 31)
            elif value != 0:
                raise ValueError('Retained-control scenario expects no retained byte or pending control bits')
        state.register(address, 'rw' if old else 'r', value)
        self.event(state, 'scoped retained media-state register read', address=hex(address),
            value=hex(value), assumption='Bank-2 high bit follows the existing held-input scenario; control has no retained byte; transition latch is zero. Configuration writes are preserved.')
        try:
            result = state.run(hooks-{pc}, limit=1)
        finally:
            if old is None:
                state.regions = [r for r in state.regions if r.address != address]
            else:
                state.regions = [replace(r, data=old.data, permissions=old.permissions)
                    if r.address == address else r for r in state.regions]
        if result['status'] != 'instruction_limit' or result['completed'] != 1:
            return False
        self.retained_reads.append(pc)
        return True

    def handle(self, state, hooks, interrupts):
        pc = state.regs['pc']
        try:
            if pc == 0x601a88cf:
                if (state.cpu != 0 or self.retained_active or self.retained_finished
                        or self.reg(state, 0xa1c57fd0) != 0x1000001
                        or self.reg(state, 0x6181e340) != 0):
                    raise ValueError('Unreviewed retained media-state entry')
                self.retained_active = True
                self.event(state, 'connected retained media-state consumer entered',
                           key_reason='0x1000001', early_bank2_snapshot=0)
                return self.step(state, hooks)
            if pc in self.retained_register_reads:
                return self.sample(state, hooks)
            if pc in self.retained_landmarks:
                if pc == 0x601a7376:
                    if (state.cpu != 0 or not self.retained_active
                            or self.retained_reads != list(self.retained_register_reads) or state.regs['d0'] != 0
                            or self.reg(state, 0x98e00000) != 0):
                        raise ValueError('Retained-state consumer did not finish as reviewed')
                    self.retained_active = False
                    self.retained_finished = True
                state.events.append(dict(kind='milestone', name=self.retained_landmarks[pc], cpu=state.cpu,
                    entry=hex(pc), instructions=state.steps, d0=hex(state.regs['d0'])))
                return self.step(state, hooks)
            return super().handle(state, hooks, interrupts)
        except ValueError as exc:
            return self.stop(state, 'Retained media-state context needs review', reason=str(exc))


def main():
    old_peer = completion.SectionCompletionPeer
    original_experiment = boot.boot_experiment
    source = 'tools/penf_boot_retained_state.py'
    digest = hashlib.sha256((ROOT/source).read_bytes()).hexdigest()

    def experiment(*args, **kwargs):
        report, state = original_experiment(*args, **kwargs)
        report['source_sha256'][source] = digest
        report['retained_state_scenario'] = dict(
            reads={hex(k):hex(v) for k,v in RetainedStatePeer.retained_register_reads.items()},
            scope='One connected USTART1 consumer, zero retained byte and transition latch; same bank-2 input level as prior input sampling. Native read/clear and branch logic execute; all mappings are instruction-scoped.')
        return report, state

    completion.SectionCompletionPeer = RetainedStatePeer
    boot.boot_experiment = experiment
    try:
        completion.main()
    finally:
        completion.SectionCompletionPeer = old_peer
        boot.boot_experiment = original_experiment


if __name__ == '__main__':
    main()
