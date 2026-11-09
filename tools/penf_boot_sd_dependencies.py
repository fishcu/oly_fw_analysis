#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Counterfactual SD activation inside a fresh native boot replay.

Change one runtime task-start argument, never firmware bytes. Native kernel
activation and scheduling remain intact. Physical OK selection is not modeled.
Stop at SD entry until code residency and service dependencies are reviewed.
"""
import hashlib

import penf_boot_emulator as boot
import penf_boot_camera_units as units
from penf_emulator import ROOT


class SDDependenciesPeer(units.CameraUnitsPeer):
    activation_site = 0x60041de8
    original_task = 47
    hooks = units.CameraUnitsPeer.hooks | {activation_site, 0x60b1cbb5}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sd_selected = False

    def dependency_state(self, state):
        tasks = state.task_snapshot(0)
        return dict(tasks=[t for t in tasks if t['id'] in (1,17,18,19,47,49,50,51,64,65,95)],
            loaded_mask=hex(self.reg(state, 0xa1c58404)),
            section_selector=hex(self.reg(state, 0xa1c583fc)),
            logical_reads=[e for e in state.events if e.get('name')=='decoded logical flash read'])

    def handle(self, state, hooks, interrupts):
        pc = state.regs['pc']
        if pc == self.activation_site:
            if state.cpu != 0 or self.sd_selected or state.regs['d0'] != self.original_task:
                return self.stop(state, 'SD experiment activation checkpoint differs')
            sd = next(t for t in state.task_snapshot(0) if t['id']==95)
            if sd['state'] != 16 or sd['entry'] != '0x60b1cbb5':
                return self.stop(state, 'SD task is not the expected dormant task')
            self.event(state, 'explicit experimental SD activation argument',
                original_task=self.original_task, supplied_task=95,
                instruction=hex(pc), dependencies=self.dependency_state(state),
                assumption='One task-start argument substituted. Physical selector remains unknown.')
            state.regs['d0'] = 95
            self.sd_selected = True
            return self.step(state, hooks)
        if pc == 0x60b1cbb5:
            if not self.sd_selected or state.cpu != 0:
                return self.stop(state, 'Unexpected SD entry outside selected experiment')
            state.events.append(dict(kind='milestone', name='native scheduled SD task entry',
                cpu=state.cpu, entry=hex(pc), instructions=state.steps,
                dependencies=self.dependency_state(state)))
            return self.stop(state, 'SD entry reached; code residency and service readiness need review')
        return super().handle(state, hooks, interrupts)


def main():
    original_peer = units.CameraUnitsPeer
    original_experiment = boot.boot_experiment
    source = 'tools/penf_boot_sd_dependencies.py'
    digest = hashlib.sha256((ROOT/source).read_bytes()).hexdigest()
    def experiment(*args, **kwargs):
        report, state = original_experiment(*args, **kwargs)
        report['source_sha256'][source] = digest
        report['sd_dependency_scenario'] = dict(
            activation_site=hex(SDDependenciesPeer.activation_site),
            original_task=SDDependenciesPeer.original_task, supplied_task=95,
            physical_selector_identified=False,
            scope='Fresh main replay; one supplied activation argument, native scheduler; stop at SD entry.')
        return report, state
    units.CameraUnitsPeer = SDDependenciesPeer
    boot.boot_experiment = experiment
    try:
        units.main()
    finally:
        units.CameraUnitsPeer = original_peer
        boot.boot_experiment = original_experiment


if __name__ == '__main__':
    main()
