#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Fresh main replay through native flash semaphore release and loader completion."""
import hashlib

import penf_boot_emulator as boot
import penf_boot_remote_semaphore as remote
from penf_emulator import ROOT
from penf_semaphore_release_interrupts import SemaphoreReleaseInterrupts


class SemaphoreReleasePeer(remote.RemoteSemaphorePeer):
    release_landmarks = {
        0x6006bf8a: 'remote worker enters native exit/delete wrapper',
        0x600319aa: 'native worker exit/delete service entered',
        0x6006c52d: 'remote service calls native semaphore signal',
        0x6006c534: 'remote native semaphore signal returned',
        0x60042280: 'section worker calls completion flag wrapper',
    }
    hooks = remote.RemoteSemaphorePeer.hooks | set(release_landmarks)

    def handle(self, state, hooks, interrupts):
        pc = state.regs['pc']
        try:
            if pc == 0x600701c9 and interrupts.release_phase == 'cleanup':
                interrupts.finish_cleanup(state)
                return True
            if pc in self.release_landmarks:
                if pc == 0x6006bf8a and interrupts.release_phase == 'cleanup':
                    if state.cpu != 0:
                        raise ValueError('Cleanup worker is on the wrong core')
                    interrupts.cleanup_entered = True
                state.events.append(dict(kind='milestone', name=self.release_landmarks[pc],
                    cpu=state.cpu, entry=hex(pc), instructions=state.steps,
                    d0=hex(state.regs['d0']), d1=hex(state.regs['d1']),
                    semaphore_count=interrupts.word(state, 0x6182abe0)))
                return self.step(state, hooks)
            return super().handle(state, hooks, interrupts)
        except ValueError as exc:
            return self.stop(state, 'Semaphore release context needs review', reason=str(exc))


def main():
    old_peer, old_irq = remote.RemoteSemaphorePeer, remote.RemoteSemaphoreInterrupts
    original_experiment = boot.boot_experiment
    paths = ('tools/penf_boot_semaphore_release.py', 'tools/penf_semaphore_release_interrupts.py')
    hashes = {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
    instances = []

    class ReplayInterrupts(SemaphoreReleaseInterrupts):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            instances.append(self)

    def experiment(*args, **kwargs):
        report, state = original_experiment(*args, **kwargs)
        assert len(instances) == 1
        model = instances[0]
        report['source_sha256'].update(hashes)
        report['semaphore_release_scenario'] = dict(
            phase=model.release_phase, remote_returns=model.remote_returns,
            outstanding_remote_frames=model.remote_frames,
            older_startup_context=model.resume, older_cpu1_context=model.cross_resume,
            acquisition_worker=model.cleanup_worker,
            scope='One acquire/release pair for flash semaphore 116, with native worker cleanup and verified returns; further requests stop')
        return report, state

    remote.RemoteSemaphorePeer, remote.RemoteSemaphoreInterrupts = SemaphoreReleasePeer, ReplayInterrupts
    boot.boot_experiment = experiment
    try:
        remote.main()
    finally:
        remote.RemoteSemaphorePeer, remote.RemoteSemaphoreInterrupts = old_peer, old_irq
        boot.boot_experiment = original_experiment


if __name__ == '__main__':
    main()
