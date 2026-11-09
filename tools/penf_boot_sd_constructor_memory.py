#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Admit native section-constructor allocations from reviewed fixed pools.

Native allocation/bitmap operations execute. Only requested bytes of a newly
allocated CPU0 slot become RAM; frees and unfamiliar allocation classes stop.
"""
import hashlib

import penf_boot_emulator as boot
import penf_boot_sd_preparation as preparation
from penf_emulator import ROOT


class SDConstructorMemoryPeer(preparation.SDPreparationPeer):
    hooks=preparation.SDPreparationPeer.hooks|{0x600233bd,0x600233f9,0x600233fc}

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.constructor_allocation=None
        self.constructor_objects={}

    def handle(self,state,hooks,interrupts):
        pc=state.regs['pc']
        if pc==0x600233fc and state.regs['a0'] in self.constructor_objects:
            return self.stop(state,'Constructor allocation free requires lifetime review',
                address=hex(state.regs['a0']))
        if pc not in (0x600233bd,0x600233f9):return super().handle(state,hooks,interrupts)
        if self.preparation_state!='setup' and self.constructor_allocation is None:
            return self.step(state,hooks)
        try:
            if state.cpu!=0 or self.preparation_state!='setup':
                raise ValueError('Allocation outside native section setup')
            if pc==0x600233bd:
                size=state.regs['d0']
                if self.constructor_allocation is not None or not 0<size<=16384:
                    raise ValueError('Only reviewed fixed allocation classes are admitted')
                self.constructor_allocation=(size,state.regs['sp'])
                return self.step(state,hooks)
            if self.constructor_allocation is None:raise ValueError('Allocation return lacks entry')
            size,sp=self.constructor_allocation
            address=state.regs['a0']
            if size<=128:
                existing=next((r for r in state.regions if r.address<=address
                    and address+size<=r.address+len(r.data) and r.capture and 'w' in r.permissions),None)
                if (state.regs['sp']!=sp or not 0x61173fc0<=address<0x61221fc0
                        or existing is None):
                    raise ValueError('Small allocation does not belong to existing writable pool')
                self.constructor_allocation=None
                return self.step(state,hooks)
            base,stride,count,bitmap_base=(0x614d9000,2112,480,0xa1c556cc) if size<=2048 else (
                0x6122a540,16448,64,0xa1c556b4)
            offset=address-base
            if state.regs['sp']!=sp or offset<0 or offset%stride or offset//stride>=count:
                raise ValueError('Returned pointer is outside CPU0 pool slots')
            slot=offset//stride
            bitmap=self.reg(state,bitmap_base+4*(slot//32))
            if not bitmap&(1<<(slot%32)):raise ValueError('Native allocation bit is clear')
            if any(r.capture and r.address<address+size and address<r.address+len(r.data) for r in state.regions):
                raise ValueError('Returned allocation overlaps already mapped mutable RAM')
            state.ram(f'sd_constructor_allocation_{base:x}_{slot}',address,b'\xa5'*size)
            self.constructor_objects[address]=size
            self.constructor_objects[address+0x40000000]=size
            self.event(state,'native section-constructor allocation admitted',
                address=hex(address),bytes=size,pool_slot=slot,pool_base=hex(base),
                assumption='Requested extent only; poisoned initial contents; native allocator/bitmap untouched.')
            self.constructor_allocation=None
            return self.step(state,hooks)
        except ValueError as exc:
            return self.stop(state,'Section-constructor allocation needs review',reason=str(exc))


def main():
    old_peer=preparation.SDPreparationPeer;old_experiment=boot.boot_experiment
    source='tools/penf_boot_sd_constructor_memory.py'
    digest=hashlib.sha256((ROOT/source).read_bytes()).hexdigest()
    def experiment(*args,**kwargs):
        report,state=old_experiment(*args,**kwargs)
        report['source_sha256'][source]=digest
        report['sd_constructor_memory_scenario']=dict(pools=['0x614d9000','0x6122a540'],
            strides=[2112,16448],
            scope='New CPU0 section-setup allocations, requested 129..16384 bytes; no free/reuse model.')
        return report,state
    preparation.SDPreparationPeer=SDConstructorMemoryPeer;boot.boot_experiment=experiment
    try:preparation.main()
    finally:preparation.SDPreparationPeer=old_peer;boot.boot_experiment=old_experiment


if __name__=='__main__':main()
