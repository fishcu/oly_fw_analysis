# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Exact CPU-access guard for the first Red-lightness experiment.

This is an emulator observation, not a firmware patch or hardware protection.
Storage/model copies can inspect bytes; native CPU reads of either alias stop.
"""
from dataclasses import replace

RED_LIGHTNESS=0x60622e48


def guard_red_coefficient(state,value=0):
    if value not in (0,250):raise ValueError('Only stock and the reviewed Red +250 fixture')
    address=RED_LIGHTNESS;end=address+2
    roots=[r for r in state.regions if not r.alias_of and r.address<=address
           and end<=r.address+len(r.data)]
    if len(roots)!=1 or not roots[0].capture or 'w' not in roots[0].permissions:
        raise ValueError('Red coefficient must belong to a witnessed mutable section copy')
    root=roots[0]
    aliases=[r for r in state.regions if r.alias_of==root.name]
    if len(aliases)!=1 or aliases[0].address!=root.address+0x40000000 or aliases[0].data!=root.data:
        raise ValueError('Red coefficient copy lacks coherent aliases')
    if state.read(address,2)!=bytes(2):raise ValueError('Red coefficient does not match pinned stock')
    state.write(address,value.to_bytes(2,'little'))
    lo,hi=address-root.address,end-root.address
    rebuilt=[]
    for region in state.regions:
        if region.name!=root.name and region.alias_of!=root.name:
            rebuilt.append(region);continue
        for a,b in ((0,lo),(lo,hi),(hi,len(region.data))):
            if a==b:continue
            suffix=f'__red_watch_{a:x}'
            rebuilt.append(replace(region,name=region.name+suffix,address=region.address+a,
                data=region.data[a:b],permissions='w' if (a,b)==(lo,hi) else region.permissions,
                alias_of=root.name+suffix if region.alias_of else None))
    state.regions=rebuilt
    state.events.append(dict(kind='model',name='exact Red coefficient CPU-read guard installed',
        cpu=state.cpu,entry=hex(state.regs['pc']),address=hex(address),alias=hex(address+0x40000000),
        value=value,bytes=2,instructions=state.steps,
        assumption='Applied after native section copy. Value 250 is a RAM fixture for the preflighted candidate; no container is written. Both CPU aliases deny reads/execution; DMA is not modeled.'))
