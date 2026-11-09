#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Add native FILECLBK initialization before the experimental SD activation.

The call order is supplied by the harness. No filesystem return, card content,
task scheduling or queue delivery is fabricated.
"""
import hashlib
import os
import struct

import penf_boot_emulator as boot
import penf_boot_sd_client as client
from penf_emulator import ROOT, Region
from penf_resource_storage import opaque_ram

FS_CALLS=0x18040100


class SDFilesystemPeer(client.SDClientPeer):
    stop_at_sd_wait=False
    hooks=client.SDClientPeer.hooks|{FS_CALLS+7,FS_CALLS+16,
        0x6058ffc6,0x6059d318,0x60023459,0x60023495,0x60023498,0x600234f2,0x60598ac0,
        0x605989bc,0x605989d9,0x605989e5,0x605989ef,0x605989f4,
        0x605989f9,0x60598a05,0x60598a11,0x60598a1d,0x60598a29}

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.filesystem_phase='pending'
        self.filesystem_saved=None
        self.filesystem_workspaces=set()
        self.filesystem_allocation=None
        self.filesystem_heap_objects=set()
        self.filesystem_free=None
        self.filelog_loaded=False
        self.filelog_scenario=os.environ.get('PENF_SD_FILELOG','opaque')
        if self.filelog_scenario not in ('opaque','erased'):
            raise ValueError('Unreviewed FILECLBK filelog scenario')

    def handle(self,state,hooks,interrupts):
        pc=state.regs['pc']
        if pc==0x60598ac0:
            packet=state.read(state.regs['a0'],16)
            reply,requester,command,body=struct.unpack('<4I',packet)
            if (state.cpu!=0 or self.filesystem_phase!='complete' or
                    (reply,requester&0xffff,command)!=(36,95,18)):
                return self.stop(state,'Unreviewed native FILECLBK request dispatch',packet=packet.hex())
            self.event(state,'native FILECLBK received SD unmount request',packet=packet.hex(),
                packet_address=hex(state.regs['a0']),reply_queue=reply,requester=requester&0xffff,
                command=command,body=hex(body))
            return self.step(state,hooks)
        if pc==0x600224c2 and self.filesystem_phase=='initializing':
            request=(state.regs['a0'],state.regs['a1'],state.regs['d1'])
            if (state.cpu!=0 or self.filelog_loaded or state.regs['mdr']!=0x600711b0
                    or request!=(0x402a0000,0xa2f03c00,0xba00)):
                return self.stop(state,'Unreviewed filesystem persistent-data read',request=list(map(hex,request)))
            if self.filelog_scenario=='opaque':
                opaque_ram(state,'filesystem_unknown_filelog',request[1],request[2])
                assumption='Successful logical read; unknown contents remain write-only, CPU reads stop. No empty or valid filelog asserted.'
            else:
                state.ram('filesystem_erased_filelog_scenario',request[1],b'\xff'*request[2])
                assumption='Explicit erased filelog contents, not measured camera data. Native header check/default path runs.'
            self.filelog_loaded=True
            self.event(state,'explicit FILECLBK persistent filelog transfer',source=hex(request[0]),
                destination=hex(request[1]),bytes=request[2],scenario=self.filelog_scenario,
                assumption=assumption)
            state.return_from_model(0)
            return True
        if pc==0x60023498 and state.regs['a0'] in self.filesystem_heap_objects:
            address=state.regs['a0']
            if (state.cpu!=0 or self.filesystem_phase!='complete' or self.filesystem_free is not None
                    or state.regs['mdr'] not in (0x605a3d05,0x605a3d10,0x605a3d21)
                    or address<0xa0000000):
                return self.stop(state,'Filesystem allocation free requires lifetime review')
            if 0xa1221fc0<=address<0xa122a540:
                slot=(address-0xa1221fc0)//192;bitmap=0xa1c5569c
            else:
                slot=(address-0xa142c540)//16448;bitmap=0xa1c556c4
            word=bitmap+4*(slot//32);mask=1<<(slot%32)
            if not self.reg(state,word)&mask:
                return self.stop(state,'Filesystem native free starts with clear allocation bit')
            self.filesystem_free=(address,state.regs['sp'],word,mask)
            return self.step(state,hooks)
        if pc==0x600234f2 and self.filesystem_free is not None:
            address,sp,word,mask=self.filesystem_free
            if state.cpu!=0 or state.regs['sp']!=sp or self.reg(state,word)&mask:
                return self.stop(state,'Filesystem native free did not release allocation')
            canonical=address-0x40000000
            name=f'filesystem_physical_{address:x}'
            owned=[r for r in state.regions if r.name==name or r.alias_of==name]
            if len(owned)!=2 or {r.address for r in owned}!={address,canonical}:
                return self.stop(state,'Filesystem released allocation mapping differs')
            state.regions=[r for r in state.regions if r.name!=name and r.alias_of!=name]
            self.filesystem_workspaces.remove(canonical)
            self.filesystem_heap_objects.difference_update((address,canonical))
            self.filesystem_free=None
            self.event(state,'native FILECLBK allocation released',address=hex(address),
                assumption='Native bitmap cleared; both RAM aliases unmapped to catch later use.')
            return self.step(state,hooks)
        if pc==0x600234f2:return self.step(state,hooks)
        if pc in (0x60023459,0x60023495) and self.filesystem_phase in ('initializing','complete'):
            if pc==0x60023459:
                allowed=({0x6059d16e:16384} if self.filesystem_phase=='initializing' else
                    {0x605a3c39:128,0x605a3c63:128,0x605a3c75:16384})
                if (state.cpu!=0 or self.filesystem_allocation is not None
                        or allowed.get(state.regs['mdr'])!=state.regs['d0']):
                    return self.stop(state,'Unreviewed filesystem physical allocation')
                self.filesystem_allocation=(state.regs['d0'],state.regs['sp'])
                return self.step(state,hooks)
            if self.filesystem_allocation is None:
                return self.stop(state,'Filesystem allocation return lacks entry')
            size,sp=self.filesystem_allocation
            base,stride,count,bitmap=(0xa1221fc0,192,178,0xa1c5569c) if size==128 else (
                0xa142c540,16448,43,0xa1c556c4)
            address=state.regs['a0'];offset=address-base;slot=offset//stride
            if (state.cpu!=0 or state.regs['sp']!=sp
                    or offset<0 or offset%stride or slot>=count
                    or not self.reg(state,bitmap+4*(slot//32))&(1<<(slot%32))):
                return self.stop(state,'Filesystem physical allocation provenance differs')
            if not self.map_workspace(state,f'filesystem_physical_{address:x}',address,size):return False
            self.filesystem_allocation=None
            self.filesystem_heap_objects.update((address,address-0x40000000))
            self.event(state,'native FILECLBK physical allocation admitted',address=hex(address),bytes=size,
                pool_slot=slot,assumption='Native allocator and bitmap; requested extent only, no free/reuse model.')
            return self.step(state,hooks)
        if pc in (0x6058ffc6,0x6059d318):
            # These native getters return literal static extents. Poison the
            # contents, then let the firmware clear only the fields it uses.
            label,expected,extent,stack_offset=(
                ('SD_AU',0xa1e43c00,8192,16) if pc==0x6058ffc6 else
                ('file_records',0xa1e3ec00,4096,4))
            address=state.regs['a0']
            size=int.from_bytes(state.read(state.regs['sp']+stack_offset,4),'little')
            if (state.cpu!=0 or self.filesystem_phase!='initializing'
                    or address!=expected or size!=extent):
                return self.stop(state,'Unreviewed filesystem static workspace')
            if not self.map_workspace(state,'filesystem_static_'+label,address,size):return False
            self.event(state,'native FILECLBK static workspace admitted',address=hex(address),bytes=size,
                provenance='Literal native getter; native filesystem initialization follows.',
                assumption='RAM available at the returned fixed address; unspecified initial bytes poisoned.')
            return self.step(state,hooks)
        if pc in (0x60023459,0x60023495,0x60023498):return self.step(state,hooks)
        if pc==self.activation_site and self.preparation_state=='complete' and self.filesystem_phase=='pending':
            if state.cpu!=0 or state.regs['d0']!=47:
                return self.stop(state,'Filesystem preparation checkpoint differs')
            self.filesystem_saved=dict(state.regs)
            blob=b'\xdd'+struct.pack('<i',0x605989bc-FS_CALLS)+bytes((0,4))
            blob+=b'\x80\x11'
            blob+=b'\xdd'+struct.pack('<i',0x600697ff-(FS_CALLS+9))+bytes((0xc0,12))
            state.regions.append(Region('explicit_filesystem_preparation_calls',FS_CALLS,blob+b'\xcb','rx'))
            state.regs['pc']=FS_CALLS
            self.filesystem_phase='initializing'
            self.hooks.add(0x600224c2)
            self.event(state,'explicit native FILECLBK preparation sequence',
                initializer='0x605989bc',receiver_task=17,
                assumption='Harness-selected caller order; initializer and task-start bodies remain native.')
            return True
        if pc in (FS_CALLS+7,FS_CALLS+16):
            if state.cpu!=0 or state.regs['sp']!=self.filesystem_saved['sp']:
                return self.stop(state,'Filesystem preparation return stack differs')
            self.event(state,'native FILECLBK preparation call returned',phase=self.filesystem_phase,
                result=hex(state.regs['d0']),dependencies=self.dependency_state(state))
            if state.regs['d0']!=0:
                return self.stop(state,'Native FILECLBK prerequisite rejected initialization',result=hex(state.regs['d0']))
            if pc==FS_CALLS+7:
                self.filesystem_phase='start'
                self.hooks.remove(0x600224c2)
                return self.step(state,hooks)
            self.filesystem_phase='complete'
            state.regs=dict(self.filesystem_saved)
            return True
        if pc in (0x605989bc,0x605989d9,0x605989e5,0x605989ef,0x605989f4,
                  0x605989f9,0x60598a05,0x60598a11,0x60598a1d,0x60598a29):
            self.event(state,'native FILECLBK initializer boundary',result=hex(state.regs['d0']))
            return self.step(state,hooks)
        return super().handle(state,hooks,interrupts)

    def map_workspace(self,state,name,address,size):
        canonical=address-0x40000000 if address>=0xa0000000 else address
        if canonical in self.filesystem_workspaces or any(
                (r.capture or r.alias_of or set(r.data[max(0,canonical-r.address):
                    min(len(r.data),canonical+size-r.address)])!={255})
                for r in state.regions if r.address<canonical+size and canonical<r.address+len(r.data)):
            return self.stop(state,'Filesystem workspace overlaps another mapping')
        state.ram(name,address,b'\xa5'*size)
        self.filesystem_workspaces.add(canonical)
        return True


def main():
    old_peer=client.SDClientPeer;old_experiment=boot.boot_experiment
    source='tools/penf_boot_sd_filesystem.py';digest=hashlib.sha256((ROOT/source).read_bytes()).hexdigest()
    def experiment(*args,**kwargs):
        report,state=old_experiment(*args,**kwargs)
        report['source_sha256'][source]=digest
        report['sd_filesystem_scenario']=dict(initializer='0x605989bc',receiver_task=17,
            filelog=os.environ.get('PENF_SD_FILELOG','opaque'),
            limitation='Explicit call order; native filesystem/device boundaries stop.')
        return report,state
    client.SDClientPeer=SDFilesystemPeer;boot.boot_experiment=experiment
    try:client.main()
    finally:client.SDClientPeer=old_peer;boot.boot_experiment=old_experiment


if __name__=='__main__':main()
