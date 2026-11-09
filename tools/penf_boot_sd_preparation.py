#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Constructed SD-start prerequisites, using native loader/setup bodies.

Fresh replay; temporary harness CALL instructions do not modify firmware.
The harness requests section 5 locally on CPU0 before the supplied SD start.
This is a dependency experiment, not a discovered physical startup route.
"""
from dataclasses import replace
import hashlib
import os
import struct

import penf_boot_emulator as boot
import penf_boot_sd_dependencies as dependencies
from penf_emulator import ROOT, Region, BASE, firmware

CALL_SEQUENCE = 0x18040000
SECTION_ENDS = (0x601cb000,0x60428000,0x6069b800,0x60a50000,
                0x60fdc800,0x610f2000,0x61100000,0x6115b800)


def sections():
    b = firmware()
    return [dict(id=i+1, start=struct.unpack_from('<I', b, 0x60026d7c-BASE+i*12)[0], end=end)
            for i,end in enumerate(SECTION_ENDS)]


def preparation_calls():
    """Worker uses CALLS/self-prologue; completion helper uses ordinary CALL."""
    blob=b'\xfc\xff'+struct.pack('<i',0x600421e1-CALL_SEQUENCE)
    return blob+b'\xdd'+struct.pack('<i',0x60042123-(CALL_SEQUENCE+6))+bytes((0xe0,44))


def protect_unloaded_sections(state):
    """Deny native access to section bytes without an observed matching copy."""
    reads = [e for e in state.events if e.get('name')=='decoded logical flash read']
    guarded = []
    for section in sections():
        lo,hi = section['start'],section['end']
        if lo==hi:continue
        if any(((int(e['destination'],16)&0x3fffffff)|0x60000000)==lo
               and e['bytes']==hi-lo for e in reads):
            continue
        rebuilt=[]
        for r in state.regions:
            end=r.address+len(r.data)
            if lo<end and r.address<hi:
                if r.capture or r.alias_of:
                    raise ValueError('Unloaded section overlaps mutable runtime mapping')
                start=max(lo,r.address);stop=min(hi,end)
                if r.address<start:
                    rebuilt.append(replace(r,name=r.name+'_before_guard',data=r.data[:start-r.address]))
                # Omit this interval entirely. The storage model creates the
                # destination only when the native loader requests its copy.
                if stop<end:
                    rebuilt.append(replace(r,name=r.name+'_after_guard',address=stop,data=r.data[stop-r.address:]))
            else:rebuilt.append(r)
        state.regions=rebuilt
        guarded.append(section)
    return guarded


class SDPreparationPeer(dependencies.SDDependenciesPeer):
    hooks=dependencies.SDDependenciesPeer.hooks|{CALL_SEQUENCE+6,CALL_SEQUENCE+13}

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.preparation_state='pending'
        self.preparation_registers=None
        self.section_plan=tuple(int(x) for x in os.environ.get('PENF_SD_SECTIONS','5').split(','))
        if self.section_plan not in ((5,),(3,5),(4,5),(2,4,5),(3,4,5),(2,3,4,5)):
            raise ValueError('Unreviewed section preparation plan')
        self.section_index=0

    def begin_section(self,state):
        section=self.section_plan[self.section_index]
        if state.read(0xa1c58405,1)!=b'\0':
            raise ValueError('Unexpected section already-loaded shortcut flag')
        state.write(0xa1c583fc,struct.pack('<I',section))
        state.regs['pc']=CALL_SEQUENCE
        self.preparation_state='copy'
        self.event(state,'explicit local section preparation input',section=section,
            ordinal=self.section_index,assumption='Native worker called locally with supplied selector.')

    def handle(self,state,hooks,interrupts):
        pc=state.regs['pc']
        if pc==self.activation_site and self.preparation_state=='pending':
            if state.cpu!=0 or state.regs['d0']!=47 or self.reg(state,0xa1c583fc)!=0:
                return self.stop(state,'SD preparation checkpoint differs')
            self.preparation_registers=dict(state.regs)
            guarded=protect_unloaded_sections(state)
            # Worker has its own MOVM/local-frame prologue and is called by
            # CALLS in native dispatch. Ordinary CALL would allocate twice.
            blob=preparation_calls()
            state.regions.append(Region('explicit_sd_preparation_calls',CALL_SEQUENCE,blob+b'\xcb','rx'))
            self.event(state,'explicit SD dependency preparation sequence',
                guarded_sections=guarded,section_plan=self.section_plan,
                calls=['0x600421e1','0x60042123'],
                assumption='Harness invokes native section-copy worker on CPU0, then native completion/setup; not physical selection.')
            self.begin_section(state)
            return True
        if pc in (CALL_SEQUENCE+6,CALL_SEQUENCE+13):
            if state.cpu!=0 or state.regs['sp']!=self.preparation_registers['sp']:
                return self.stop(state,'SD preparation native return stack differs')
            self.event(state,'native SD prerequisite call returned',return_checkpoint=hex(pc),
                phase=self.preparation_state,d0=hex(state.regs['d0']),
                dependencies=self.dependency_state(state))
            if pc==CALL_SEQUENCE+6:
                if self.preparation_state!='copy':return self.stop(state,'Unexpected SD copy return')
                self.preparation_state='setup'
                return self.step(state,hooks)
            if self.preparation_state!='setup':return self.stop(state,'Unexpected SD setup return')
            self.section_index+=1
            if self.section_index<len(self.section_plan):
                state.regs=dict(self.preparation_registers)
                self.begin_section(state)
                return True
            self.preparation_state='complete'
            state.regs=dict(self.preparation_registers)
            return True
        return super().handle(state,hooks,interrupts)


def main():
    original_peer=dependencies.SDDependenciesPeer
    original_experiment=boot.boot_experiment
    source='tools/penf_boot_sd_preparation.py'
    digest=hashlib.sha256((ROOT/source).read_bytes()).hexdigest()
    def experiment(*args,**kwargs):
        report,state=original_experiment(*args,**kwargs)
        report['source_sha256'][source]=digest
        report['sd_preparation_scenario']=dict(section_plan=os.environ.get('PENF_SD_SECTIONS','5'),worker_cpu=0,
            residency='Uncopied declared sections deny native reads/execution until storage copy',
            limitation='Explicit harness call order and selector input; no physical recovery inference.')
        return report,state
    dependencies.SDDependenciesPeer=SDPreparationPeer
    boot.boot_experiment=experiment
    try:dependencies.main()
    finally:
        dependencies.SDDependenciesPeer=original_peer
        boot.boot_experiment=original_experiment


if __name__=='__main__':main()
