#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Fresh boot with one reviewed section-3 CPU1 wake request and native dispatch."""
import hashlib

import penf_boot_emulator as boot
import penf_boot_favorite_lens as favorite
import penf_boot_startup_preemption as preemption
from penf_cross_core_interrupts import CrossCoreInterrupts
from penf_emulator import ROOT


class CrossCorePeer(favorite.FavoriteLensPeer):
    cross_landmarks = {
        0x6006c840: 'CPU1 IRQ120 handler entered',
        0x6006feb0: 'CPU1 cross-core ring drainer entered',
        0x600701ff: 'CPU1 dispatch message callback entered',
        0x60070324: 'CPU1 task dispatch received a message',
        0x600421e1: 'native section worker entered',
        0x6004223d: 'native section worker storage read returned',
        0x60042287: 'native section worker returning after completion signal',
        0x60042123: 'native section completion wait entered',
        0x6004215b: 'native section completion wait returned',
        0x6006da8c: 'native section initializer dispatcher entered',
        0x604f6a2e: 'picture-profile selector entered',
        0x604f7272: 'COLOR builder entered',
        0x604f747f: 'color-table dispatch entered',
    }
    hooks = favorite.FavoriteLensPeer.hooks | set(cross_landmarks) | {
        0x6006fda5, 0x600701c9, 0x6006c90c, 0x600706ef}

    def handle(self, state, hooks, interrupts):
        pc = state.regs['pc']
        if pc in (0x6006fda5, 0x600701c9, 0x6006c90c, 0x600706ef):
            try:
                if pc == 0x6006fda5:
                    return interrupts.request(state, hooks)
                if pc == 0x600701c9 and interrupts.cross_requested and not interrupts.cross_injected:
                    interrupts.wake_cpu1(state)
                    return True
                if pc == 0x6006c90c:
                    return interrupts.acknowledge(state, hooks)
                if pc == 0x600706ef and interrupts.cross_resume is not None:
                    interrupts.returned(state)
            except ValueError as exc:
                return self.stop(state, 'Cross-core interrupt context needs review', reason=str(exc))
            return self.step(state, hooks)
        if pc in self.cross_landmarks:
            state.events.append(dict(kind='milestone', name=self.cross_landmarks[pc], cpu=state.cpu,
                entry=hex(pc), instructions=state.steps, d0=state.regs['d0'], a0=hex(state.regs['a0']),
                section=int.from_bytes(state.read(0xa1c583fc, 4), 'little')))
            return self.step(state, hooks)
        try:
            return super().handle(state, hooks, interrupts)
        except ValueError as exc:
            return self.stop(state, 'Inherited model rejected a newly reached context', reason=str(exc))


def main():
    original_peer, original_irq = favorite.FavoriteLensPeer, preemption.StartupInterrupts
    original_experiment = boot.boot_experiment
    paths = ('tools/penf_boot_cross_core.py', 'tools/penf_cross_core_interrupts.py')
    hashes = {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}

    def experiment(*args, **kwargs):
        report, state = original_experiment(*args, **kwargs)
        report['source_sha256'].update(hashes)
        report['cross_core_scenario'] = dict(
            request='One CPU0-to-CPU1 section-3 request at 6006fda5; bit 3 -> IRQ120',
            wake='After sender returns at 600701c9, wake CPU1 from 600706ef with native priority level 2',
            acknowledgement='Native 9930030c write clears pending bit and external selector',
            limitations='Physical halt wake, interrupt frame and timing remain hypotheses. Native handlers/queues/tasks execute; unknown accesses stop.')
        report['final_peer_tasks'] = {str(cpu): state.task_snapshot(cpu) for cpu in (1, 2)}
        return report, state

    favorite.FavoriteLensPeer = CrossCorePeer
    preemption.StartupInterrupts = CrossCoreInterrupts
    boot.boot_experiment = experiment
    try:
        favorite.main()
    finally:
        favorite.FavoriteLensPeer = original_peer
        preemption.StartupInterrupts = original_irq
        boot.boot_experiment = original_experiment


if __name__ == '__main__':
    main()
