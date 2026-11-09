#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Fresh boot through one native cross-core flash semaphore acquisition."""
import hashlib

import penf_boot_cross_core as cross
import penf_boot_emulator as boot
from penf_emulator import ROOT
from penf_remote_semaphore_interrupts import RemoteSemaphoreInterrupts


class RemoteSemaphorePeer(cross.CrossCorePeer):
    remote_landmarks = {
        0x6006c73f: 'CPU0 remote service IRQ handler entered',
        0x6006bf4c: 'remote service task begins scanning requests',
        0x6006bf73: 'CPU1 request worker starts on target CPU',
        0x6006c483: 'remote kernel service dispatcher entered',
        0x6006c53f: 'remote service calls native semaphore wait',
        0x6006c546: 'remote native semaphore wait returned',
        0x6006968c: 'remote semaphore wrapper returned to flash guard',
    }
    hooks = cross.CrossCorePeer.hooks | set(remote_landmarks) | {
        0x6006c62f, 0x6006c756, 0x6006c577, 0x6006c88e, 0x6006c635}

    def handle(self, state, hooks, interrupts):
        pc = state.regs['pc']
        try:
            if pc == 0x6006c62f:
                return interrupts.send_request(state, hooks)
            if pc == 0x6006c577:
                return interrupts.send_reply(state, hooks)
            if pc in (0x6006c756, 0x6006c88e):
                return interrupts.acknowledge_remote(state, hooks)
            if pc in (0x600701c9, 0x6006c635) and state.cpu in interrupts.remote_frames:
                interrupts.remote_returned(state)
            if pc == 0x6006c635:
                return self.step(state, hooks)
            if pc in self.remote_landmarks:
                state.events.append(dict(kind='milestone', name=self.remote_landmarks[pc],
                    cpu=state.cpu, entry=hex(pc), instructions=state.steps,
                    d0=hex(state.regs['d0']), d1=hex(state.regs['d1']), a0=hex(state.regs['a0'])))
                return self.step(state, hooks)
            return super().handle(state, hooks, interrupts)
        except ValueError as exc:
            return self.stop(state, 'Remote semaphore context needs review', reason=str(exc))


def main():
    old_peer, old_irq = cross.CrossCorePeer, cross.CrossCoreInterrupts
    original_experiment = boot.boot_experiment
    paths = ('tools/penf_boot_remote_semaphore.py', 'tools/penf_remote_semaphore_interrupts.py')
    hashes = {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}

    def experiment(*args, **kwargs):
        report, state = original_experiment(*args, **kwargs)
        report['source_sha256'].update(hashes)
        report['remote_semaphore_scenario'] = dict(
            request='Only CPU1 slot 0 service 8 / flash semaphore 116 / infinite timeout',
            delivery='CPU0 at 600701c9, CPU1 reply at 6006c635; explicit immediate-delivery hypothesis',
            services='Native IRQs, kernel queues/flags, dynamic worker and semaphore operation execute',
            limitation='Further requests and unreviewed contexts stop. No physical recovery guarantee.')
        return report, state

    cross.CrossCorePeer, cross.CrossCoreInterrupts = RemoteSemaphorePeer, RemoteSemaphoreInterrupts
    boot.boot_experiment = experiment
    try:
        cross.main()
    finally:
        cross.CrossCorePeer, cross.CrossCoreInterrupts = old_peer, old_irq
        boot.boot_experiment = original_experiment


if __name__ == '__main__':
    main()
