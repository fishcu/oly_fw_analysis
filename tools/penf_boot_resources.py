#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Fresh boot continuation through scoped native resource-loader reads."""
import hashlib

import penf_boot_emulator as boot
import penf_boot_startup_gpio as gpio
from penf_emulator import ROOT
from penf_resource_storage import PACKAGE, PACKAGE_SHA256, transfer


class ResourcePeer(gpio.StartupGpioPeer):
    hooks = gpio.StartupGpioPeer.hooks | {
        0x602b8573, 0x602b874d, 0x602b92bb, 0x602b9300, 0x602b8672}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hooks = set(self.hooks)
        self.resource_request = None

    def handle(self, state, hooks, interrupts):
        pc = state.regs['pc']
        if pc in (0x602b8573, 0x602b874d):
            state.events.append(dict(kind='milestone', cpu=state.cpu, entry=hex(pc),
                instructions=state.steps, name='resource initializer entered' if pc == 0x602b8573
                else 'resource initializer returning'))
            return self.step(state, hooks)
        if pc == 0x602b92bb:
            if state.cpu != 0 or self.resource_request is not None or state.regs['d1'] != 0x101:
                return self.stop(state, 'Unreviewed resource read context/mode')
            source, dest, size = state.regs['a0'], state.regs['a1'], state.regs['d0']
            self.resource_request = dict(source=source & ~511, destination=(dest+15) & ~15,
                size=(size+(source & 511)+15) & ~15)
            # The global runner already breaks at this logical-storage API.
            # Own it only while a reviewed resource read is active.
            self.hooks.add(0x600224c2)
            return self.step(state, hooks)
        if pc == 0x600224c2:
            expected = self.resource_request
            actual = dict(source=state.regs['a0'], destination=state.regs['a1'], size=state.regs['d1'])
            if state.cpu != 0 or actual != expected:
                return self.stop(state, 'Resource logical read differs from native aligned request', actual=actual, expected=expected)
            try:
                transfer(state, actual['source'], actual['destination'], actual['size'])
            except ValueError as exc:
                return self.stop(state, 'Resource read needs further data/ownership review', reason=str(exc), **actual)
            state.return_from_model(0)
            return True
        if pc == 0x602b9300:
            if self.resource_request is None:
                return self.stop(state, 'Resource read return without entry')
            self.event(state, 'native resource read wrapper returned', result=state.regs['d0'], **self.resource_request)
            self.resource_request = None
            self.hooks.remove(0x600224c2)
            return self.step(state, hooks)
        if pc == 0x602b8672:
            expected = state.read(0x603713ac, 1024)
            pointer = int.from_bytes(state.read(0xa1c58828, 4), 'little')
            if pointer != 0xa2d23c00 or state.read(pointer, 1024) != expected:
                return self.stop(state, 'Lens directory did not reach the reviewed built-in fallback')
            self.event(state, 'native LENSDAT default copied', bytes=1024, destination=hex(pointer))
            return self.step(state, hooks)
        return super().handle(state, hooks, interrupts)


def main():
    original_peer = gpio.StartupGpioPeer
    original_experiment = boot.boot_experiment
    paths = ('tools/penf_boot_resources.py', 'tools/penf_resource_storage.py', 'tools/oly_container.py')
    hashes = {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}

    def experiment(*args, **kwargs):
        report, state = original_experiment(*args, **kwargs)
        report['source_sha256'].update(hashes)
        report['resource_storage_scenario'] = dict(package=PACKAGE, package_sha256=PACKAGE_SHA256,
            unknown_banks='Exact sound/mode17 directory slices are write-only; first native CPU content read stops',
            lens_directory='Erased 1024-byte directory; native LENSDAT fallback executes',
            package_resources='Exact decoded component 0101/0102/0106 bytes, unchanged headers and trailers')
        return report, state

    gpio.StartupGpioPeer = ResourcePeer
    boot.boot_experiment = experiment
    try:
        gpio.main()
    finally:
        gpio.StartupGpioPeer = original_peer
        boot.boot_experiment = original_experiment


if __name__ == '__main__':
    main()
