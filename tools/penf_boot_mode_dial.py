#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Fresh PEN-F boot with A selected through ADC channel 7's native decoder.

Only that channel's sample changes from 900 to 415. The stock channel table
maps logical input 0x15 to bit 0x80, and the stock dial thresholds map 415
to A. No input cache, worker state, task or recovery selector is supplied.
"""
import hashlib

import penf_boot_emulator as boot
import penf_boot_retained_state as retained
from penf_emulator import ROOT


class ModeDialPeer(retained.RetainedStatePeer):
    mode_adc_pc = 0x6007a2b2
    mode_adc_register = 0x98c00058
    mode_sample = 415
    hooks = retained.RetainedStatePeer.hooks | {mode_adc_pc, 0x6019b892, 0x601a4dc5}

    def handle(self, state, hooks, interrupts):
        pc = state.regs['pc']
        try:
            if pc == self.mode_adc_pc:
                address = self.mode_adc_register
                if state.cpu != 0 or state.regs['d0'] != 0x80:
                    raise ValueError('Unreviewed mode ADC read context')
                if state.read(0x60129f8c, 4) != bytes.fromhex('15018000'):
                    raise ValueError('Logical-input-to-channel mapping differs')
                if any(r.address < address+4 and address < r.address+len(r.data)
                       for r in state.regions):
                    raise ValueError('Mode ADC register already mapped')
                state.register(address, 'r', self.mode_sample)
                try:
                    result = state.run(hooks-{pc}, limit=1)
                finally:
                    state.regions = [r for r in state.regions if r.address != address]
                if result['status'] != 'instruction_limit' or result['completed'] != 1:
                    return False
                self.event(state, 'mode dial ADC channel 7 sample', value=self.mode_sample,
                    register=hex(address), logical_input='0x15',
                    assumption='Fixed A-position sample; physical voltage/noise unmeasured. Other ADC channels retain the prior scenario.')
                return True
            if pc == 0x6019b892:
                if state.regs['d0'] & 0xffff != self.mode_sample:
                    raise ValueError('Mode ADC decoder received an unexpected sample')
                self.event(state, 'native mode-dial ADC decoder entered', sample=state.regs['d0'])
                return self.step(state, hooks)
            if pc == 0x601a4dc5:
                if state.regs['d0'] != 2 or state.read(0x61c5802c, 1) != b'\x08':
                    raise ValueError('Native startup mode query did not report A')
                self.event(state, 'USR_FAST native mode query returned A', mode_code=2, selector=8)
                return self.step(state, hooks)
            return super().handle(state, hooks, interrupts)
        except ValueError as exc:
            return self.stop(state, 'Mode-dial input context needs review', reason=str(exc))


def main():
    old_peer = retained.RetainedStatePeer
    original_experiment = boot.boot_experiment
    source = 'tools/penf_boot_mode_dial.py'
    digest = hashlib.sha256((ROOT/source).read_bytes()).hexdigest()

    def experiment(*args, **kwargs):
        report, state = original_experiment(*args, **kwargs)
        report['source_sha256'][source] = digest
        report['mode_dial_scenario'] = dict(mode='A', sample=415, channel=7,
            register='0x98c00058', physical_input_verified=False,
            scope='Native ADC sample collection, callbacks, threshold decoder and startup query; only one channel sample is modeled differently.')
        return report, state

    retained.RetainedStatePeer = ModeDialPeer
    boot.boot_experiment = experiment
    try:
        retained.main()
    finally:
        retained.RetainedStatePeer = old_peer
        boot.boot_experiment = original_experiment


if __name__ == '__main__':
    main()
