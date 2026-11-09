#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Add one erased favorite-lens metadata read to the resource boot scenario."""
import hashlib

import penf_boot_emulator as boot
import penf_boot_resources as resources
from penf_emulator import ROOT

FAVORITE_READ = dict(source=0x40160000, destination=0xa1c49380, size=2048)


class FavoriteLensPeer(resources.ResourcePeer):
    hooks = resources.ResourcePeer.hooks | {0x60162c76, 0x60162d11, 0x60162d80}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.favorite_active = False
        self.favorite_read = False

    def handle(self, state, hooks, interrupts):
        pc = state.regs['pc']
        if pc == 0x60162c76:
            if state.cpu != 0 or self.favorite_active or self.favorite_read:
                return self.stop(state, 'Repeated/unreviewed favorite-lens initialization')
            self.favorite_active = True
            state.events.append(dict(kind='milestone', name='favorite-lens metadata initializer entered',
                cpu=state.cpu, entry=hex(pc), instructions=state.steps))
            return self.step(state, hooks)
        if pc == 0x600224c2 and self.favorite_active:
            actual = dict(source=state.regs['a0'], destination=state.regs['a1'], size=state.regs['d1'])
            if actual == FAVORITE_READ:
                if state.cpu != 0 or self.resource_request != actual or self.favorite_read:
                    return self.stop(state, 'Favorite-lens read lacks a matching native request')
                state.ram('erased_favorite_lens_scenario', actual['destination'], b'\xff'*actual['size'])
                self.favorite_read = True
                self.event(state, 'erased favorite-lens metadata read',
                    source=hex(actual['source']), destination=hex(actual['destination']), bytes=actual['size'],
                    assumption='Only this saved metadata prefix is hypothesized erased. Native check-byte/marker rejection and RAM defaults execute; no persistent write or spare-space claim.')
                state.return_from_model(0)
                return True
        if pc in (0x60162d11, 0x60162d80):
            if state.cpu != 0 or not self.favorite_active or not self.favorite_read:
                return self.stop(state, 'Favorite-lens return without reviewed erased read')
            expected = bytearray(b'\xff'*2048)
            expected[:7] = b'\0'+b'\xff'*6
            expected[152] = 0
            expected[334:349] = b'MyFavoriteLens\0'
            if pc != 0x60162d11 or state.read(FAVORITE_READ['destination'], 2048) != expected:
                return self.stop(state, 'Favorite-lens native defaults differ from isolated evidence')
            self.favorite_active = False
            state.events.append(dict(kind='milestone', name='favorite-lens native RAM defaults returning',
                cpu=state.cpu, entry=hex(pc), instructions=state.steps))
            return self.step(state, hooks)
        return super().handle(state, hooks, interrupts)


def main():
    original_peer = resources.ResourcePeer
    original_experiment = boot.boot_experiment
    source = 'tools/penf_boot_favorite_lens.py'
    source_hash = hashlib.sha256((ROOT/source).read_bytes()).hexdigest()

    def experiment(*args, **kwargs):
        report, state = original_experiment(*args, **kwargs)
        report['source_sha256'][source] = source_hash
        report['favorite_lens_scenario'] = dict(
            source='0x40160000', destination='0xa1c49380', bytes=2048,
            assumption='Erased favorite metadata; native validation/default path only')
        return report, state

    resources.ResourcePeer = FavoriteLensPeer
    boot.boot_experiment = experiment
    try:
        resources.main()
    finally:
        resources.ResourcePeer = original_peer
        boot.boot_experiment = original_experiment


if __name__ == '__main__':
    main()
