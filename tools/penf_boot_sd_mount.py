#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Continue native SD transport lifetimes and mount under exact COLOR guard."""
import hashlib
import os
import struct

import penf_boot_emulator as boot
import penf_boot_sd_filesystem as filesystem
from penf_boot_sd_preparation import CALL_SEQUENCE
from penf_coefficient_watch import guard_red_coefficient
from penf_emulator import ROOT

DESCRIPTOR_CALLERS={
    0x605a637c:{0x605a63e3,0x605a647b},  # Media dispatcher and its callback.
    0x60591ce4:{0x60591d1a},             # Filesystem mount wrapper.
    0x6058b8bf:{0x6058b8f7},             # Lower device operation 3.
}


class SDMountPeer(filesystem.SDFilesystemPeer):
    hooks=filesystem.SDFilesystemPeer.hooks|{0x6002352a,0x604b509e,0x60b1ce0c,0x60590d07}

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.packet_free=None
        self.red_guarded=False
        self.red_value=int(os.environ.get('PENF_SD_RED','0'))
        if self.red_value not in (0,250):raise ValueError('Unreviewed Red fixture')
        self.mount_received=False
        self.mount_allocation=None
        self.media_descriptors=set()
        self.descriptor_free_callers={}

    def handle(self,state,hooks,interrupts):
        pc=state.regs['pc']
        if pc==CALL_SEQUENCE+6 and self.section_plan[self.section_index]==3 and not self.red_guarded:
            guard_red_coefficient(state,self.red_value)
            self.red_guarded=True
        if pc==0x604b509e:
            return self.stop(state,'Native ISP coefficient write reached; exposure review required',registers=dict(state.regs))
        if pc in (0x60b1ce0c,0x60590d07):
            self.event(state,'native SD mount/precheck boundary',registers=dict(state.regs))
            return self.step(state,hooks)
        if pc==0x60023459 and state.regs['mdr'] in DESCRIPTOR_CALLERS:
            if state.cpu!=0 or state.regs['d0']!=128 or self.mount_allocation is not None:
                return self.stop(state,'Unreviewed mount request allocation')
            self.mount_allocation=(state.regs['sp'],state.regs['mdr'])
            return self.step(state,hooks)
        if pc==0x60023495 and self.mount_allocation is not None:
            address=state.regs['a0'];offset=address-0xa1221fc0;slot=offset//192
            allocation_sp,caller=self.mount_allocation
            if (state.cpu!=0 or state.regs['sp']!=allocation_sp or offset<0
                    or offset%192 or slot>=178
                    or not self.reg(state,0xa1c5569c+4*(slot//32))&(1<<(slot%32))):
                return self.stop(state,'Mount request allocation provenance differs')
            if not self.map_workspace(state,f'filesystem_physical_{address:x}',address,128):return False
            self.filesystem_heap_objects.update((address,address-0x40000000))
            self.media_descriptors.add(address)
            self.descriptor_free_callers[address]=DESCRIPTOR_CALLERS[caller]
            self.mount_allocation=None
            self.event(state,'native SD media request allocation admitted',address=hex(address),bytes=128,caller=hex(caller),
                assumption='Native physical allocator; exact descriptor extent; free remains guarded.')
            return self.step(state,hooks)
        if pc==0x60023498 and state.regs['a0'] in self.media_descriptors:
            address=state.regs['a0'];slot=(address-0xa1221fc0)//192
            word=0xa1c5569c+4*(slot//32);mask=1<<(slot%32)
            if (state.cpu!=0 or state.regs['mdr'] not in self.descriptor_free_callers[address]
                    or self.filesystem_free is not None or not self.reg(state,word)&mask):
                return self.stop(state,'Unreviewed native media descriptor free')
            self.filesystem_free=(address,state.regs['sp'],word,mask)
            self.media_descriptors.remove(address)
            del self.descriptor_free_callers[address]
            self.event(state,'native SD media descriptor release begins',address=hex(address),
                callback_result=state.regs['d3'],caller=hex(state.regs['mdr']))
            return self.step(state,hooks)
        if pc==0x6002351f and state.regs['a0'] in self.transport_buffers:
            address=state.regs['a0'];slot=(address-0xa1221fc0)//192
            word=0xa1c5569c+4*(slot//32);mask=1<<(slot%32)
            if (state.cpu!=0 or self.packet_free is not None
                    or state.regs['mdr'] not in (0x6006d543,0x6006d54c)
                    or not self.reg(state,word)&mask):
                return self.stop(state,'Unreviewed SD transport free')
            self.packet_free=(address,state.regs['sp'],word,mask,slot)
            self.event(state,'native SD transport release begins',address=hex(address),
                result_halfword=state.regs['d2'],caller=hex(state.regs['mdr']))
            return self.step(state,hooks)
        if pc==0x6002352a:
            if self.packet_free is None:return self.step(state,hooks)
            address,sp,word,mask,slot=self.packet_free
            if state.cpu!=0 or state.regs['sp']!=sp or self.reg(state,word)&mask:
                return self.stop(state,'Native SD transport free did not release its slot')
            name=f'sd_transport_packet_{slot}'
            owned=[r for r in state.regions if r.name==name or r.alias_of==name]
            if len(owned)!=2 or {r.address for r in owned}!={address,address-0x40000000}:
                return self.stop(state,'Released SD packet mapping differs')
            state.regions=[r for r in state.regions if r.name!=name and r.alias_of!=name]
            self.transport_buffers.remove(address);self.packet_free=None
            self.event(state,'native SD transport allocation released',address=hex(address),
                assumption='Native bitmap cleared; both aliases removed. Subsequent use stops; reuse requires another native allocation.')
            return self.step(state,hooks)
        if pc==0x60598ac0:
            packet=state.read(state.regs['a0'],16)
            reply,requester,command,body=struct.unpack('<4I',packet)
            if command==97:
                if (state.cpu!=0 or self.filesystem_phase!='complete' or self.mount_received
                        or (reply,requester&0xffff)!=(36,95)):
                    return self.stop(state,'Unreviewed native SD mount dispatch',packet=packet.hex())
                self.mount_received=True
                self.event(state,'native FILECLBK received SD mount request',packet=packet.hex(),
                    packet_address=hex(state.regs['a0']),body=hex(body),body_hex=state.read(body,48).hex())
                return self.step(state,hooks)
        return super().handle(state,hooks,interrupts)


def main():
    old_peer=filesystem.SDFilesystemPeer;old_experiment=boot.boot_experiment
    paths=('tools/penf_boot_sd_mount.py','tools/penf_coefficient_watch.py')
    hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
    def experiment(*args,**kwargs):
        report,state=old_experiment(*args,**kwargs)
        report['source_sha256'].update(hashes)
        report['sd_mount_scenario']=dict(red_fixture=int(os.environ.get('PENF_SD_RED','0')),
            coefficient_guard='Both CPU aliases unreadable after native section-3 copy; no DMA model.',
            transport='Native allocation and release, exact packet lifetime. No card or filesystem success supplied.')
        return report,state
    filesystem.SDFilesystemPeer=SDMountPeer;boot.boot_experiment=experiment
    try:filesystem.main()
    finally:filesystem.SDFilesystemPeer=old_peer;boot.boot_experiment=old_experiment


if __name__=='__main__':main()
