#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Fresh boot: deliver section 3's native completion flag after flash release."""
import hashlib

import penf_boot_emulator as boot
import penf_boot_semaphore_release as release
from penf_emulator import ROOT
from penf_remote_semaphore_interrupts import RemoteSemaphoreInterrupts


class SectionCompletionInterrupts(release.SemaphoreReleaseInterrupts):
    completion_words = (3, 0, 0, 1, 1, 182, 4, 0, 0, 0, 182, 0x101c, 3)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.completion_phase = 'pending'
        self.release_cleanup_entered = False

    def send_request(self, state, hooks):
        if self.release_phase != 'release' or not self.remote_replied:
            return super().send_request(state, hooks)
        if (state.cpu, state.regs['pc'], state.regs['d0'], state.regs['a3']) != (
                1, 0x6006c62f, 1, self.request_address) or self.record(state) != self.completion_words:
            raise ValueError('Only section-3 completion flag 182 / bit 4 is reviewed next')
        if self.completion_phase == 'pending':
            frame = self.remote_frames.get(0)
            saved = state.cpu_regs[0]
            if (self.remote_returns != [1, 0, 1] or set(self.remote_frames) != {0}
                    or not frame['acknowledged'] or frame['registers']['pc'] != 0x600701c9
                    or saved['pc'] != 0x6006c57d or 0 in state.blocked or self.pending
                    or self.word(state, 0x6182abe0) != 1 or self.word(state, 0x6182dddc) != 0):
                raise ValueError('Release cleanup or completion-flag context differs')
            workers = [t for t in state.task_snapshot(0) if t['id'] == 141]
            if len(workers) != 1:
                raise ValueError('Expected one native release worker')
            worker = workers[0]; lo = int(worker['stack'], 16)
            if (worker['state'] != 1 or worker['entry'] != '0x6006bf73'
                    or worker['priority'] & 0xffff != 15 or worker['stack_bytes'] != 1024
                    or not lo+8 <= saved['sp'] <= lo+1024):
                raise ValueError('Release worker stack/task differs')
            self.completion_phase = 'cleanup'
            self._event(state, 'defer section-completion write for release worker cleanup',
                        worker=worker, assumption='CPU0 finishes its native worker before CPU1 writes the next request')
            state.switch_core(0)
            return True
        if self.completion_phase != 'ready' or self.remote_frames or self.remote_returns != [1, 0, 1, 0]:
            raise ValueError('Completion repeated or release return still pending')
        self._prepare_delivery(state, 0)
        self.completion_phase = 'sent'
        self.request_words = self.completion_words
        self.remote_sent = self.remote_replied = False
        self._event(state, 'admit reviewed section-3 completion request', service=3, flag=182, pattern=4)
        return RemoteSemaphoreInterrupts.send_request(self, state, hooks)

    def finish_release_cleanup(self, state):
        if (state.cpu, state.regs['pc'], self.completion_phase) != (0, 0x600701c9, 'cleanup'):
            raise ValueError('Unreviewed release cleanup return')
        if not self.release_cleanup_entered:
            raise ValueError('Release worker cleanup call was not observed')
        self.remote_returned(state)
        workers = [t for t in state.task_snapshot(0) if t['id'] == 141]
        if (self.remote_frames or self.remote_returns != [1, 0, 1, 0]
                or self.record(state) != self.completion_words or workers
                or self.word(state, 0x6182abe0) != 1 or self.word(state, 0x6182dddc) != 0):
            raise ValueError('Release cleanup did not preserve the completion sender/state')
        self._event(state, 'native release worker cleanup and USTART1 return verified',
                    worker_after=workers, semaphore_count=1, completion_pattern=0)
        self.completion_phase = 'ready'
        state.switch_core(1)


class SectionCompletionPeer(release.SemaphoreReleasePeer):
    completion_landmarks = {
        0x6006c4e9:'remote service calls native section-completion flag set',
        0x6006c4f0:'native section-completion flag set returned',
        0x600421c9:'section constructors returned before loaded-mask update',
        0x600421de:'section wait/setup completed',
    }
    hooks = release.SemaphoreReleasePeer.hooks | set(completion_landmarks)

    def handle(self, state, hooks, interrupts):
        pc = state.regs['pc']
        try:
            if pc == 0x6006bf8a and interrupts.completion_phase == 'cleanup':
                if state.cpu != 0:
                    raise ValueError('Release cleanup worker is on the wrong core')
                interrupts.release_cleanup_entered = True
            if pc == 0x600701c9 and interrupts.completion_phase == 'cleanup':
                interrupts.finish_release_cleanup(state)
                return True
            if pc in self.completion_landmarks:
                state.events.append(dict(kind='milestone', name=self.completion_landmarks[pc],
                    cpu=state.cpu, entry=hex(pc), instructions=state.steps,
                    d0=hex(state.regs['d0']), d1=hex(state.regs['d1']),
                    completion_pattern=hex(interrupts.word(state, 0x6182dddc))))
                return self.step(state, hooks)
            return super().handle(state, hooks, interrupts)
        except ValueError as exc:
            return self.stop(state, 'Section-completion context needs review', reason=str(exc))


def main():
    old_peer, old_irq = release.SemaphoreReleasePeer, release.SemaphoreReleaseInterrupts
    original_experiment = boot.boot_experiment
    source = 'tools/penf_boot_section_completion.py'
    digest = hashlib.sha256((ROOT/source).read_bytes()).hexdigest()
    instances = []

    class ReplayInterrupts(SectionCompletionInterrupts):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            instances.append(self)

    def experiment(*args, **kwargs):
        report, state = original_experiment(*args, **kwargs)
        assert len(instances) == 1
        model = instances[0]
        report['source_sha256'][source] = digest
        report['section_completion_scenario'] = dict(phase=model.completion_phase,
            remote_returns=model.remote_returns,
            scope='Extends the inherited acquire/release scenario with one service-3 request: flag 182, pattern 4. Native kernel and constructors execute; other requests stop.')
        return report, state

    release.SemaphoreReleasePeer, release.SemaphoreReleaseInterrupts = SectionCompletionPeer, ReplayInterrupts
    boot.boot_experiment = experiment
    try:
        release.main()
    finally:
        release.SemaphoreReleasePeer, release.SemaphoreReleaseInterrupts = old_peer, old_irq
        boot.boot_experiment = original_experiment


if __name__ == '__main__':
    main()
