#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native camera-controller configuration with instruction-scoped MMIO sinks.

One control read assumes zero. Remaining accesses accept stock configuration
writes; no readiness, interrupt, DMA transfer or imaging result is fabricated.
"""
import hashlib

import penf_boot_emulator as boot
import penf_boot_camera_enable as enable
from penf_emulator import ROOT


class CameraRegistersPeer(enable.CameraEnablePeer):
    operations=(
        (0x602a44ea,0x9b000000,'r',0),
        (0x602a44f1,0x9b000000,'w',0),
        (0x602a4501,0x9b000008,'w',0x781f80),
        (0x602a4512,0x9b00000c,'w',0x7e000),
        (0x602a4525,0x9b000010,'w',0x87800000),
        (0x602a452f,0x9b000064,'w',4),
        (0x602a4539,0x9b000068,'w',0),
        (0x602a4543,0x9b00006c,'w',0x78),
        (0x602a454d,0x9b000028,'w',4),
        (0x602a4557,0x9b00002c,'w',0),
        (0x602a4561,0x9b000030,'w',0x78),
        (0x602a456d,0x9b000018,'w',0),
        (0x602a4579,0x9b00001c,'w',0),
        (0x602a4585,0x9b000020,'w',0),
        (0x602a458c,0x9b0000f8,'w',0),
        (0x60261e60,0x9be00004,'w',0x3f),
        (0x60261e66,0x9be0000c,'w',0x3f),
        (0x602a4770,0x9b000504,'w',1),
        (0x602b7848,0x988000e4,'w',0x10000000),
    )
    hooks=enable.CameraEnablePeer.hooks|{x[0] for x in operations}|{
        0x602a448d,0x602a45da,0x602a32ab}

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.register_stage=0
        self.register_active=False
        self.register_initializer_returned=False
        self.controller_finished=False

    def handle(self,state,hooks,interrupts):
        pc=state.regs['pc']
        try:
            if pc==0x602a448d:
                if (state.cpu!=0 or self.enable_stage!=4 or self.register_active
                        or self.controller_finished or state.regs['a0']!=0x6036b4e0
                        or state.regs['mdr']!=0x602a31f6):
                    raise ValueError('Unreviewed camera configuration caller')
                self.register_active=True
                return self.step(state,hooks)
            if pc in {x[0] for x in self.operations}:
                if (state.cpu!=0 or not self.register_active
                        or self.register_stage>=len(self.operations)):
                    raise ValueError('Camera configuration access outside scope')
                expected,address,access,value=self.operations[self.register_stage]
                if pc!=expected:
                    raise ValueError('Camera configuration access order differs')
                if self.register_stage>=15 and not self.register_initializer_returned:
                    raise ValueError('Configuration initializer has not returned')
                if access=='w' and state.regs['d0']!=value:
                    raise ValueError('Camera configuration write value differs')
                if pc in (0x602a44ea,0x602a44f1) and state.regs['a1']!=address:
                    raise ValueError('Camera control-register pointer differs')
                overlap=[r for r in state.regions if r.address<address+4 and address<r.address+len(r.data)]
                existing=bool(overlap)
                if existing:
                    if not (address==0x988000e4 and access=='w' and len(overlap)==1
                            and overlap[0].address==address and len(overlap[0].data)==4
                            and overlap[0].permissions=='w'):
                        raise ValueError('Camera configuration register has unreviewed mapping')
                else:
                    state.register(address,access,0)
                try:
                    result=state.run(hooks-{pc},limit=1)
                    observed=self.reg(state,address)
                finally:
                    if not existing:
                        state.regions=[r for r in state.regions if r.address!=address]
                if result['status']!='instruction_limit' or result['completed']!=1 or observed!=value:
                    return False
                self.register_stage+=1
                self.event(state,'scoped native camera configuration access',instruction=hex(pc),
                    address=hex(address),access=access,value=hex(value),operation=self.register_stage,
                    assumption='Single zero control-read hypothesis; writes accepted without hardware effects, completion or IRQs.')
                return True
            if pc==0x602a45da:
                if (not self.register_active or self.register_stage!=15
                        or self.register_initializer_returned):
                    raise ValueError('Camera configuration return differs')
                self.register_initializer_returned=True
                return self.step(state,hooks)
            if pc==0x602a32ab:
                if (not self.register_active or self.register_stage!=len(self.operations)
                        or self.controller_finished):
                    raise ValueError('Camera controller return differs')
                self.register_active=False;self.controller_finished=True
                state.events.append(dict(kind='milestone',name='native camera controller initializer completed',
                    cpu=state.cpu,entry=hex(pc),instructions=state.steps))
                return self.step(state,hooks)
            return super().handle(state,hooks,interrupts)
        except ValueError as exc:
            return self.stop(state,'Camera controller configuration needs review',reason=str(exc))


def main():
    original_peer=enable.CameraEnablePeer
    original_experiment=boot.boot_experiment
    source='tools/penf_boot_camera_registers.py'
    digest=hashlib.sha256((ROOT/source).read_bytes()).hexdigest()
    def experiment(*args,**kwargs):
        report,state=original_experiment(*args,**kwargs)
        report['source_sha256'][source]=digest
        report['camera_register_scenario']=dict(initial_control=0,
            operations=[[hex(p),hex(a),m,hex(v)] for p,a,m,v in CameraRegistersPeer.operations],
            scope='One configuration call and following clock release. No DMA, readiness or interrupt model.')
        return report,state
    enable.CameraEnablePeer=CameraRegistersPeer
    boot.boot_experiment=experiment
    try:enable.main()
    finally:
        enable.CameraEnablePeer=original_peer
        boot.boot_experiment=original_experiment


if __name__=='__main__':main()
