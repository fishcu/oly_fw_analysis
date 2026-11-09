# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""One native flash acquire/release pair, preserving outstanding IRQ contexts."""
from penf_remote_semaphore_interrupts import RemoteSemaphoreInterrupts


class SemaphoreReleaseInterrupts(RemoteSemaphoreInterrupts):
    release_words = (7, 0, 0, 1, 1, 116, 0, 0, 0, 0, 116, 0x101c, 3)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.release_phase = 'acquire'
        self.cleanup_worker = None
        self.cleanup_entered = False

    def send_request(self, state, hooks):
        if self.release_phase == 'acquire' and not self.remote_sent:
            return super().send_request(state, hooks)
        if (state.cpu, state.regs['pc'], state.regs['d0'], state.regs['a3']) != (
                1, 0x6006c62f, 1, self.request_address) or self.record(state) != self.release_words:
            raise ValueError('Only the reviewed semaphore-116 release may follow acquisition')
        if self.release_phase == 'acquire':
            return self.defer_for_cleanup(state)
        if self.release_phase != 'ready' or self.remote_frames or self.remote_returns != [1, 0]:
            raise ValueError('Release repeated or earlier interrupt return still pending')
        self._prepare_delivery(state, 0)
        self.release_phase = 'release'
        self.request_words = self.release_words
        self.remote_sent = self.remote_replied = False
        self._event(state, 'admit reviewed remote semaphore release', semaphore=116,
                    assumption='Second exchange only after the first worker has returned natively to USTART1')
        return super().send_request(state, hooks)

    def defer_for_cleanup(self, state):
        frame = self.remote_frames.get(0)
        saved = state.cpu_regs[0]
        if (not self.remote_replied or self.remote_returns != [1] or set(self.remote_frames) != {0}
                or not frame['acknowledged'] or frame['registers']['pc'] != 0x600701c9
                or saved['pc'] != 0x6006c57d or 0 in state.blocked or self.pending
                or self.word(state, 0x6182abe0) != 0):
            raise ValueError('Acquisition cleanup context differs')
        workers = [t for t in state.task_snapshot(0) if t['id'] == 141]
        if len(workers) != 1:
            raise ValueError('Expected one native acquisition worker')
        worker = workers[0]
        lo = int(worker['stack'], 16)
        if (worker['state'] != 1 or worker['entry'] != '0x6006bf73'
                or worker['priority'] & 0xffff != 15 or worker['stack_bytes'] != 1024
                or not lo+8 <= saved['sp'] <= lo+1024):
            raise ValueError('Acquisition worker stack/task differs')
        self.cleanup_worker = worker
        self.release_phase = 'cleanup'
        self._event(state, 'defer release write for native CPU0 worker cleanup',
                    worker=worker, cpu0_pc=hex(saved['pc']), sender_pc=hex(state.regs['pc']),
                    assumption='Independent cores may progress in this order; CPU1 is paused before its request write, not given a kernel wait result')
        state.switch_core(0)
        return True

    def finish_cleanup(self, state):
        if (state.cpu, state.regs['pc'], self.release_phase) != (0, 0x600701c9, 'cleanup'):
            raise ValueError('Unreviewed cleanup return boundary')
        if not self.cleanup_entered:
            raise ValueError('Worker cleanup call was not observed')
        self.remote_returned(state)
        if self.remote_frames or self.remote_returns != [1, 0] or self.record(state) != self.release_words:
            raise ValueError('Native cleanup did not preserve the pending sender')
        workers = [t for t in state.task_snapshot(0) if t['id'] == 141]
        if any(t['state'] == 1 for t in workers) or self.word(state, 0x6182abe0) != 0:
            raise ValueError('Acquisition worker still running or semaphore changed during cleanup')
        self._event(state, 'native acquisition worker cleanup and USTART1 return verified',
                    worker_after=workers, semaphore_count=0,
                    older_startup_return_pending=self.resume is not None,
                    older_cpu1_return_pending=self.cross_resume is not None)
        self.release_phase = 'ready'
        state.switch_core(1)

