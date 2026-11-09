#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Fresh boot with one scoped camera-peripheral enable register hypothesis.

The first enable reads zero from 9b000500, executes the native OR and write,
then loses its temporary mapping. No hardware completion or IRQ is supplied.
"""
import hashlib

import penf_boot_emulator as boot
import penf_boot_camera_clock as clock
from penf_emulator import ROOT


class CameraEnablePeer(clock.CameraClockPeer):
    hooks = clock.CameraClockPeer.hooks | {0x602a46c1,0x602a46c7,0x602a46cd,0x602a46ce}

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.enable_stage=0
        self.enable_old=0

    def handle(self,state,hooks,interrupts):
        pc=state.regs['pc']
        try:
            if pc in (0x602a46c1,0x602a46c7,0x602a46cd,0x602a46ce):
                sequence=(0x602a46c1,0x602a46c7,0x602a46cd,0x602a46ce)
                if (state.cpu!=0 or not self.camera_clock_finished or self.enable_stage>=4
                        or pc!=sequence[self.enable_stage] or state.regs['mdr']!=0x602a4339):
                    raise ValueError('Unreviewed peripheral-enable context/order')
                if self.enable_stage in (0,1) and state.regs['d0']!=1:
                    raise ValueError('Unreviewed peripheral-enable mask')
                if self.enable_stage in (1,2):
                    address=0x9b000500
                    if state.regs['a0']!=address:
                        raise ValueError('Peripheral-enable pointer differs')
                    if any(r.address<address+4 and address<r.address+len(r.data) for r in state.regions):
                        raise ValueError('Peripheral-enable register already mapped')
                    value=self.enable_old if self.enable_stage==1 else self.enable_old|1
                    if self.enable_stage==2 and state.regs['d0']!=value:
                        raise ValueError('Native enable result differs')
                    state.register(address,'r' if self.enable_stage==1 else 'w',self.enable_old)
                    try:
                        result=state.run(hooks-{pc},limit=1)
                        observed=self.reg(state,address)
                    finally:
                        state.regions=[r for r in state.regions if r.address!=address]
                    if result['status']!='instruction_limit' or result['completed']!=1 or observed!=value:
                        return False
                    self.event(state,'scoped camera peripheral enable access',access='r' if self.enable_stage==1 else 'w',
                        address=hex(address),value=hex(value),
                        assumption='Initial value hypothesis; native OR/write. No hardware side effect or readiness supplied.')
                    self.enable_stage+=1
                    return True
                self.enable_stage+=1
                return self.step(state,hooks)
            return super().handle(state,hooks,interrupts)
        except ValueError as exc:
            return self.stop(state,'Camera peripheral enable needs review',reason=str(exc))


def main():
    original_peer=clock.CameraClockPeer
    original_experiment=boot.boot_experiment
    source='tools/penf_boot_camera_enable.py'
    digest=hashlib.sha256((ROOT/source).read_bytes()).hexdigest()
    def experiment(*args,**kwargs):
        report,state=original_experiment(*args,**kwargs)
        report['source_sha256'][source]=digest
        report['camera_enable_scenario']=dict(register='0x9b000500',initial=0,
            scope='First enable call only, native bit-1 OR/write; no completion, timing or IRQ model.')
        return report,state
    clock.CameraClockPeer=CameraEnablePeer
    boot.boot_experiment=experiment
    try:clock.main()
    finally:
        clock.CameraClockPeer=original_peer
        boot.boot_experiment=original_experiment


if __name__=='__main__':main()
