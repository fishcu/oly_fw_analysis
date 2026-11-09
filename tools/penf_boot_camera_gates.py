#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Scoped camera clock-gate latch hypothesis during native subsystem startup.

Register 9b000500 retains native enable writes; writes to 9b000504 clear the
specified bits. This inferred latch behavior supplies no IRQ, DMA or readiness.
Only reviewed call sites within the current broad initializer are admitted.
"""
import hashlib

import penf_boot_emulator as boot
import penf_boot_camera_registers as registers
from penf_emulator import ROOT

PARENT_HOOKS=registers.CameraRegistersPeer.hooks

class CameraGatesPeer(registers.CameraRegistersPeer):
    enable_callers={0x602b77cd:1,0x602b78ff:2,0x602b79dc:4,0x602b7a28:64,
        0x602b7b1e:8,0x602b7b6a:64,0x602b7c5f:16,0x602b7d07:32,
        0x602b7d53:64,0x602b7e8c:1}
    clear_callers={0x602b7842:1,0x602b795e:2,0x602b7a93:4,0x602b7ada:64,
        0x602b7bd5:8,0x602b7c24:64,0x602b7ccb:16,0x602b7dbe:32,
        0x602b7e0d:64,0x602b7f06:1}
    config_writes={0x602b7b20:4,0x602b7b5b:1,0x602b7bd7:4,0x602b7c15:1}
    hooks=registers.CameraRegistersPeer.hooks|{0x602a32ae,0x6029ec4a,0x602a432a,
        0x602a4388,0x602a4339,0x602a4397,0x602a476d,0x602a4776}|set(config_writes)
    passive_hooks=frozenset(hooks-PARENT_HOOKS)

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.gates_active=False
        self.gates_finished=False
        self.gate_value=0
        self.gate_request=None
        self.gate_stage=0

    def access(self,state,hooks,address,access,value):
        pc=state.regs['pc']
        overlap=[r for r in state.regions if r.address<address+4 and address<r.address+len(r.data)]
        existing=bool(overlap)
        if existing:
            if not (address==0x98800128 and access=='w' and len(overlap)==1
                    and overlap[0].address==address and len(overlap[0].data)==4
                    and overlap[0].permissions=='w'):
                raise ValueError('Unexpected clock-gate mapping')
        else:
            state.register(address,access,value if access=='r' else 0)
        try:
            result=state.run(hooks-{pc},limit=1)
            observed=self.reg(state,address)
        finally:
            if not existing:
                state.regions=[r for r in state.regions if r.address!=address]
        if result['status']!='instruction_limit' or result['completed']!=1 or observed!=value:
            raise ValueError('Native gate instruction outcome differs')
        self.event(state,'scoped camera gate access',instruction=hex(pc),address=hex(address),
            access=access,value=hex(value),assumption='Inferred enable/clear latch; no DMA, IRQ or readiness.')
        return True

    def handle(self,state,hooks,interrupts):
        pc=state.regs['pc']
        try:
            if pc==0x602a32ae:
                if (state.cpu!=0 or not self.controller_finished or self.gates_active
                        or self.gates_finished or state.regs['mdr']!=0x6029eb9a):
                    raise ValueError('Unreviewed camera gate scope')
                self.gates_active=True
                return self.step(state,hooks)
            if not self.gates_active:
                if pc in self.passive_hooks:
                    return self.step(state,hooks)
                return super().handle(state,hooks,interrupts)
            guarded={0x6029ec4a,0x602a432a,0x602a4388,0x602a4339,0x602a4397,
                0x602a46c1,0x602a46c7,0x602a46cd,0x602a46ce,0x602a476d,
                0x602a4770,0x602a4776,0x602b7848}|set(self.config_writes)
            if pc in guarded and state.cpu!=0:raise ValueError('Camera gate scope changed CPU')
            if pc==0x6029ec4a:
                if self.gate_request is not None:raise ValueError('Gate operation still pending')
                self.gates_active=False;self.gates_finished=True
                state.events.append(dict(kind='milestone',name='native broad camera initializer completed',
                    cpu=state.cpu,entry=hex(pc),instructions=state.steps))
                return self.step(state,hooks)
            if pc in (0x602a432a,0x602a4388):
                choices=self.enable_callers if pc==0x602a432a else self.clear_callers
                mask=choices.get(state.regs['mdr'])
                if self.gate_request is not None or mask!=state.regs['d0']:
                    raise ValueError('Unreviewed gate caller, mask or nesting')
                self.gate_request=('enable' if pc==0x602a432a else 'clear',mask)
                self.gate_stage=0
                return self.step(state,hooks)
            if pc in (0x602a4339,0x602a4397):
                expected='enable' if pc==0x602a4339 else 'clear'
                if self.gate_request is None or self.gate_request[0]!=expected or self.gate_stage!=3:
                    raise ValueError('Gate return without matching native access')
                self.gate_request=None
                return self.step(state,hooks)
            if pc in (0x602a46c1,0x602a46c7,0x602a46cd,0x602a46ce,0x602a476d,0x602a4770,0x602a4776):
                if self.gate_request is None:raise ValueError('Gate helper outside reviewed wrapper')
                kind,mask=self.gate_request
                seq=(0x602a46c1,0x602a46c7,0x602a46cd,0x602a46ce) if kind=='enable' else (0x602a476d,0x602a4770,0x602a4776)
                if self.gate_stage>=len(seq) or pc!=seq[self.gate_stage]:
                    raise ValueError('Gate helper instruction order differs')
                if pc in (0x602a46c1,0x602a476d) and state.regs['d0']!=mask:
                    raise ValueError('Gate helper argument differs')
                if pc==0x602a46c7:
                    self.access(state,hooks,0x9b000500,'r',self.gate_value)
                elif pc==0x602a46cd:
                    value=self.gate_value|mask
                    if state.regs['d0']!=value:raise ValueError('Native OR differs')
                    self.access(state,hooks,0x9b000500,'w',value);self.gate_value=value
                elif pc==0x602a4770:
                    if state.regs['d0']!=mask:raise ValueError('Native clear mask differs')
                    self.access(state,hooks,0x9b000504,'w',mask);self.gate_value&=~mask
                else:
                    if not self.step(state,hooks):return False
                if pc not in (0x602a46ce,):self.gate_stage+=1
                return True
            if pc in self.config_writes:
                value=self.config_writes[pc]
                if self.gate_request is not None or state.regs['d0']!=value:
                    raise ValueError('Clock configuration value/context differs')
                return self.access(state,hooks,0x98800128,'w',value)
            if pc==0x602b7848:
                region=next((r for r in state.regions if r.address==0x988000e4),None)
                if (self.gate_request is not None or state.regs['d0']!=0x10000000
                        or region is None or region.permissions!='w' or len(region.data)!=4):
                    raise ValueError('Clock release write sink differs')
                return self.step(state,hooks)
            return super().handle(state,hooks,interrupts)
        except ValueError as exc:
            return self.stop(state,'Camera subsystem gates need review',reason=str(exc))


def main():
    original_peer=registers.CameraRegistersPeer
    original_experiment=boot.boot_experiment
    source='tools/penf_boot_camera_gates.py'
    digest=hashlib.sha256((ROOT/source).read_bytes()).hexdigest()
    def experiment(*args,**kwargs):
        report,state=original_experiment(*args,**kwargs)
        report['source_sha256'][source]=digest
        report['camera_gate_scenario']=dict(scope='After controller initialization, until 6029ec4a.',
            initial=0,hypothesis='9b000500 enable latch; 9b000504 write-mask clears bits. No IRQ/DMA/readiness.')
        return report,state
    registers.CameraRegistersPeer=CameraGatesPeer;boot.boot_experiment=experiment
    try:registers.main()
    finally:
        registers.CameraRegistersPeer=original_peer;boot.boot_experiment=original_experiment


if __name__=='__main__':main()
