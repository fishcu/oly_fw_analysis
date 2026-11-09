#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Run the SD prefix after explicit native section preparation.

PENF_SD_DEFER_CONSTRUCTORS=1 is a separate dependency-isolation control.
No filesystem or queue API result is supplied in either scenario.
"""
from dataclasses import replace
import hashlib
import os
import struct

import penf_boot_emulator as boot
import penf_boot_sd_preparation as preparation
import penf_boot_sd_constructor_memory as memory
from penf_emulator import ROOT


class SDClientPeer(memory.SDConstructorMemoryPeer):
    stop_at_sd_wait=True
    hooks=memory.SDConstructorMemoryPeer.hooks|{
        0x60b1ce50,0x60b1ce10,0x6006d4c2,0x60069429,0x6006932d,0x601c8e6e,
        0x60023511,0x6002351c,0x6002351f,0x6006d507,0x6006d526,0x60032709,
        0x600694db,0x60069464}

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.sd_running=False
        self.sd_watchdog=None
        self.transport_pending=None
        self.transport_buffers=[]
        self.defer_constructors=os.environ.get('PENF_SD_DEFER_CONSTRUCTORS','0')=='1'

    def handle(self,state,hooks,interrupts):
        pc=state.regs['pc']
        if self.stop_at_sd_wait and self.sd_running and int.from_bytes(state.read(0x61824edc,2),'little')&4:
            state.events.append(dict(kind='milestone',name='SD task entered native wait',
                cpu=state.cpu,entry=hex(pc),instructions=state.steps,
                tcb_hex=state.read(0x61824ed0,120).hex(),dependencies=self.dependency_state(state)))
            return self.stop(state,'Native SD task wait reached; queue/service dependency inspection')
        if pc==preparation.CALL_SEQUENCE+6 and self.defer_constructors:
            if self.preparation_state!='copy' or state.regs['sp']!=self.preparation_registers['sp']:
                return self.stop(state,'SD code-only native copy return differs')
            self.event(state,'general section constructors explicitly deferred',
                section=self.section_plan[self.section_index],
                limitation='Dependency-isolation experiment; copied bytes do not establish initialized objects.')
            self.section_index+=1
            state.regs=dict(self.preparation_registers)
            if self.section_index<len(self.section_plan):self.begin_section(state)
            else:
                self.preparation_state='complete'
                # Selector is left as the last supplied section; no loaded-bit
                # or constructor-completion success is fabricated.
            return True
        if pc==0x60b1cbb5:
            if not self.sd_selected or state.cpu!=0 or self.sd_running:
                return self.stop(state,'Unexpected code-only SD client entry')
            self.sd_running=True
            self.hooks.update((0x60022720,0x6002274b,0x60022755))
            state.events.append(dict(kind='milestone',name='native scheduled SD task entry',
                cpu=state.cpu,entry=hex(pc),instructions=state.steps,
                dependencies=self.dependency_state(state)))
            return self.step(state,hooks)
        if self.sd_running and pc in (0x60022720,0x6002274b,0x60022755):
            if pc==0x60022720:
                if state.cpu!=0 or state.regs['mdr']!=0x60b1e1f9 or state.regs['d0']!=0 or self.sd_watchdog is not None:
                    return self.stop(state,'Unreviewed SD watchdog request')
                old=self.reg(state,0x98e0008c)
                self.sd_watchdog=old&0xffffffc0
                for a in (0x98e0008c,0x98e000a4):state.register(a,'rw',self.reg(state,a))
            elif pc==0x6002274b:
                if self.sd_watchdog is None or self.reg(state,0x98e0008c)!=self.sd_watchdog or self.reg(state,0x98e000a4)!=0x20041001:
                    return self.stop(state,'SD watchdog command differs')
                state.write(0x98e000a4,bytes(4))
                self.event(state,'explicit SD watchdog acknowledgement',
                    parameter=hex(self.sd_watchdog),command='0x20041001',
                    assumption='Hardware command acknowledged; no reset or timeout simulated.')
            else:
                state.regions=[replace(r,permissions='w') if r.address in (0x98e0008c,0x98e000a4) else r for r in state.regions]
            return self.step(state,hooks)
        if self.sd_running and pc==0x601c8e6e:
            return self.stop(state,'SD prefix chose no-update/error fallback; dependency review required')
        if pc in (0x600694db,0x60069464):
            if self.sd_running:
                self.event(state,'native SD message-buffer send returned',result=hex(state.regs['d0']),
                    dependencies=self.dependency_state(state))
                if state.regs['d0']&0x80000000:
                    return self.stop(state,'Native SD message-buffer send failed before diagnostic handling',
                        result=hex(state.regs['d0']))
            return self.step(state,hooks)
        if pc==0x60032709:
            if self.stop_at_sd_wait and self.sd_running and state.cpu==0:
                sd=next(t for t in state.task_snapshot(0) if t['id']==95)
                if sd['state']==4:
                    state.events.append(dict(kind='milestone',name='SD task entered native wait',
                        cpu=0,entry=hex(pc),instructions=state.steps,
                        tcb_hex=state.read(int(sd['tcb'],16),120).hex(),
                        dependencies=self.dependency_state(state)))
                    return self.stop(state,'Native SD task wait reached; queue/service dependency inspection')
            return self.step(state,hooks)
        if pc in (0x60023511,0x6002351c):
            if not self.sd_running:return self.step(state,hooks)
            if pc==0x60023511:
                if (state.cpu!=0 or self.transport_pending is not None or len(self.transport_buffers)>=2
                        or state.regs['mdr'] not in (0x6006d4ce,0x6006d4d6)):
                    return self.stop(state,'Unreviewed SD transport buffer allocation')
                self.transport_pending=state.regs['sp']
                return self.step(state,hooks)
            address=state.regs['a0'];offset=address-0xa1221fc0
            slot=offset//192
            if (self.transport_pending!=state.regs['sp'] or offset<0 or offset%192 or slot>=178
                    or not self.reg(state,0xa1c5569c+4*(slot//32))&(1<<(slot%32))):
                return self.stop(state,'SD transport buffer is not natively allocated')
            canonical=address-0x40000000
            if any(r.capture and r.address<canonical+16 and canonical<r.address+len(r.data) for r in state.regions):
                return self.stop(state,'SD transport buffer overlaps modeled RAM')
            state.ram(f'sd_transport_packet_{slot}',address,b'\xa5'*16)
            self.transport_buffers.append(address);self.transport_pending=None
            self.event(state,'native SD transport allocation admitted',address=hex(address),
                pool_slot=slot,bytes=16,assumption='Reviewed 16-byte request/reply extent within native 128-byte pool allocation.')
            return self.step(state,hooks)
        if pc==0x6002351f:
            if state.regs['a0'] in self.transport_buffers:
                return self.stop(state,'SD transport buffer free requires lifetime review')
            return self.step(state,hooks)
        if pc in (0x6006d507,0x6006d526):
            if self.sd_running:
                self.event(state,'native SD transport API returned',result=hex(state.regs['d0']))
                if state.regs['d0']!=0:
                    return self.stop(state,'Native SD queue operation rejected request',result=hex(state.regs['d0']))
            return self.step(state,hooks)
        if pc in (0x60b1ce50,0x60b1ce10,0x6006d4c2,0x60069429,0x6006932d):
            if self.sd_running:
                self.event(state,'native SD service boundary observed',
                    d0=state.regs['d0'],d1=hex(state.regs['d1']),a0=hex(state.regs['a0']),a1=hex(state.regs['a1']))
            return self.step(state,hooks)
        return super().handle(state,hooks,interrupts)


def main():
    old_peer=memory.SDConstructorMemoryPeer;old_experiment=boot.boot_experiment
    source='tools/penf_boot_sd_client.py';digest=hashlib.sha256((ROOT/source).read_bytes()).hexdigest()
    def experiment(*args,**kwargs):
        report,state=old_experiment(*args,**kwargs)
        report['source_sha256'][source]=digest
        report['sd_client_dependency_scenario']=dict(constructors='Explicitly deferred' if os.environ.get('PENF_SD_DEFER_CONSTRUCTORS','0')=='1' else 'Native section setup',
            watchdog='One argument-0 command acknowledged',
            services='No filesystem, queue, task or validator API shortcuts')
        return report,state
    memory.SDConstructorMemoryPeer=SDClientPeer;boot.boot_experiment=experiment
    try:memory.main()
    finally:memory.SDConstructorMemoryPeer=old_peer;boot.boot_experiment=old_experiment


if __name__=='__main__':main()
