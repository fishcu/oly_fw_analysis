#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Bounded native capture allocation, COLOR snapshots and buffer reuse.

Offline only. Native pool bookkeeping, slot allocation, capture population,
property refresh, packing and HSL selection. Kernel exclusion is modeled;
conversion remains an explicitly delimited interior contract. No firmware output.
"""
import argparse
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace

from penf_profile_context_probe import (
    Fixture, state, selected, invoke, returned, at, resume, current_record,
    native_block, BASE, BUFFER, CALLER, CHECKPOINT_SHA, DEFAULT_IMAGE,
    DEFAULT_OBJDUMP, ENGINE, sha, window,
)
from penf_color_refresh_probe import memory_initialize, Exclusion

SLOTS, PARAM_POOL = 0x618689b8, 0xa1c69c38
CAPTURE_BYTES = 22080
SECTOR_SPLIT = 0x60253c07  # First six native saturation reads have finished.


def word(s, address):
    return int.from_bytes(s.read(address, 4), 'little')


class Harness:
    def __init__(self, fixture, profile, fill):
        self.f, self.fill = fixture, fill
        self.s = s = state(fixture)
        selected(s, profile)
        self.events, self.mapped_blocks = [], set()
        self.exclusion = Exclusion()
        self.slot_lock = False
        self.preparation = {'memory': memory_initialize(SimpleNamespace(s=s, f=fixture), fill)}
        for name, address, size in (
            ('capture_slots', SLOTS, 41*20),
            ('capture_queue', 0x61868cec, 30),
            ('capture_counts', 0x61868d0a, 6),
        ):
            s.ram(name, address, bytes([fill])*size)
        r = invoke(s, 0x602496d8, 0x80, 12)
        returned(s, r)
        self.preparation['slot_initialization'] = r
        s.ram('captured_capture_activity_flags', 0x618662b2, fixture.read(0x618662b2, 2))
        # Native diagnostic policy: suppress output on the invalid-slot
        # control. The slot validation and null return still execute.
        s.ram('diagnostic_output_suppressed',0x61c5840c,b'\x01\x00')
        s.ram('captured_base_parameters', 0x618bb6b8, fixture.read(0x618bb6b8, CAPTURE_BYTES))
        rows = []
        for key, address, size in ((0xc2da,0x61ae9390,2),
                                  (0xc2ca,0x61ae9388,2),(0xc0d1,0x61ae92b4,1)):
            actual,count,pointer = struct.unpack('<HHI', fixture.read(0x61c281e4+(key>>4)*8,8))
            assert (actual,pointer,count*(key&7)) == (key,address,size)
            s.ram(f'captured_record_{key:x}', address, fixture.read(address,size))
            rows.append(dict(key=hex(key), address=hex(address), bytes=size))
        self.preparation['additional_records'] = rows
        # This is an explicit initialized-exposure scenario, not an AE result.
        s.ram('initial_exposure_halfwords',0x618d2672,bytes([fill])*8)
        r=invoke(s,0x605d76b6,0x80,4,stops=(0x605d76cf,))
        at(s,r,0x605d76cf)
        assert s.read(0x618d2672,8)==bytes(8)
        self.preparation['exposure_initializer_prefix']=r
        self.pool_base=word(s,PARAM_POOL+8)
        self.pool_stride=word(s,PARAM_POOL+12)
        assert self.pool_base==0xadafa3c0 and self.pool_stride==0xa400
        assert int.from_bytes(s.read(PARAM_POOL+24,2),'little')==40

    def run(self, result=None, stop=CALLER+7):
        s=self.s
        hooks=self.exclusion.hooks|{0x602498f2,stop}
        start=s.steps
        first=len(self.events)
        for _ in range(500):
            r=result if result is not None else resume(s,hooks)
            result=None
            pc=s.regs['pc']
            if r['status']!='breakpoint' or pc==stop:
                break
            ret=s.regs['mdr']
            if pc==0x602498f2:
                address=s.regs['d0']
                index=(address-self.pool_base)//self.pool_stride
                assert 0<=index<40 and address==self.pool_base+index*self.pool_stride
                if address not in self.mapped_blocks:
                    s.ram('native_parameter_pool_'+hex(address),address,
                          bytes([self.fill])*self.pool_stride)
                    self.mapped_blocks.add(address)
                self.events.append(dict(operation='map selected pool storage',
                    address=hex(address),bytes=self.pool_stride,index=index))
                step=s.run(hooks-{pc},limit=1)
                assert step['status']=='instruction_limit'
            elif pc in (0x60069606,0x600696f9) and ret in (
                0x6024972a,0x6024973f,0x6024998f,0x602499b5,
            ):
                enter=pc==0x60069606
                assert ret in ((0x6024972a,0x6024998f) if enter else (0x6024973f,0x602499b5))
                assert s.regs['d0']==25 and self.slot_lock != enter
                if enter: assert s.regs['d1']==0xffffffff
                self.slot_lock=enter
                self.events.append(dict(operation='slot semaphore take' if enter else 'slot semaphore give',
                    semaphore=25,caller_return=hex(ret)))
                s.return_from_model(0)
            else:
                self.exclusion.handle(s)
                self.events.append(dict(operation='reviewed memory exclusion',
                                        **self.exclusion.events[-1]))
        else:
            raise AssertionError('Repeated unexpected boundary')
        return dict(status=r['status'],pc=hex(s.regs['pc']),fault=r.get('fault'),
            instructions=s.steps-start,result=s.regs.get('d0'),models=self.events[first:])

    def call(self, entry, mask, frame, regs=None, stop=CALLER+7):
        hooks=self.exclusion.hooks|{0x602498f2,stop}
        first=invoke(self.s,entry,mask,frame,regs,stops=hooks)
        r=self.run(first,stop)
        r['instructions']+=first['instructions']
        if stop==CALLER+7:
            returned(self.s,r)
            self.exclusion.balanced()
            assert not self.slot_lock
        return r

    def values(self):
        return tuple(current_record(self.f,self.s,k) for k in range(919,931))

    def refresh(self, profile):
        return self.call(0x602c50be,0x80,160,dict(d0=0,d1=53+profile))

    def edit(self, key, value):
        return self.call(0x602b9f33,0xc0,16,dict(d0=key,d1=value & 0xffffffff))

    def allocate(self):
        r=self.call(0x60249718,0x80,8,dict(d0=0))
        index=r['result']
        assert 1<=index<=40
        row=SLOTS+20*index
        assert int.from_bytes(self.s.read(row,2),'little') & 4
        address=word(self.s,row+12)
        get=invoke(self.s,0x60249c22,0,20,dict(d0=index))
        returned(self.s,get)
        assert self.s.regs['a0']==address
        return index,address,dict(allocation=r,accessor=get,index=index,address=hex(address),
                                  handle=int.from_bytes(self.s.read(row+16,2),'little'))

    def populate(self,index,stop=CALLER+7):
        return self.call(0x6025350c,0xb0,16,dict(d0=index),stop=stop)

    def capture_values(self,address):
        return struct.unpack('<12h',self.s.read(address+18600,24))

    def release(self,index):
        row=SLOTS+20*index
        before=self.s.read(row,20)
        r=self.call(0x6024992a,0x80,24,dict(d0=index))
        assert self.s.read(row,2)==bytes(2)
        assert self.s.read(row+12,4)==before[12:16]
        get=invoke(self.s,0x60249c22,0,20,dict(d0=index))
        returned(self.s,get)
        assert self.s.regs['a0']==0
        return dict(release=r,invalidated_accessor=get,
                    before=before.hex(),after=self.s.read(row,20).hex())


def pack_capture(h,address,expected,ordinal):
    """Real capture source; converter's isolated COLOR block, full packer/selector."""
    s,f=h.s,h.f
    base=0x25000000+ordinal*0x10000
    job,request,context,output=base,base+0x4000,base+0x5000,base+0x6000
    for name,ptr,size in (('job',job,14000),('request',request,1132),
                          ('context',context,192),('coefficients',output,5632)):
        s.ram(f'image_{ordinal}_{name}',ptr,bytes(size),aliases=False)
    s.write(BUFFER,struct.pack('<I',address))
    # The outer job descriptor remains supplied; take its picture-mode byte
    # from the completed native capture instead of a literal COLOR value.
    s.write(job+12,b'\x00\x00'+s.read(address+18595,1)+b'\x00')
    copied=native_block(s,0x6052056e,0x605205f9,dict(d3=BUFFER),((4,job+36),))
    assert struct.unpack('<12b',s.read(job+36+5684,12))==tuple(expected)
    packed=invoke(s,0x604c3051,0xf0,28,dict(a0=job,a1=request,d0=0))
    returned(s,packed)
    assert struct.unpack('<12b',s.read(request+1076,12))==tuple(expected)
    s.write(context+4,struct.pack('<4I',request,0,output,output+5212))
    s.write(context+56,struct.pack('<I',0xffffffff))
    s.write(context+100,struct.pack('<I',0xffffffff))
    built=invoke(s,0x604f747f,0xf0,20,dict(a0=context))
    returned(s,built)
    assert word(s,output+0x3c4)==0xfff
    pointers=struct.unpack_from('<12I',f.image,0x6062fef8-BASE)
    coefficients=[]
    for sector,value in enumerate(expected):
        record=(sector%2)*6+sector//2
        source=0x60622d74+record*28-BASE
        amplitude=struct.unpack_from('<h',f.image,source+14)[0]
        gain=struct.unpack_from('<H',f.image,pointers[record]-BASE+2*(value<0))[0]
        numerator=((amplitude*gain)>>8)*value
        expected_s=(1 if numerator>=0 else -1)*(abs(numerator)//5)
        hue,saturation,lightness=struct.unpack('<3h',s.read(output+0x2a4+record*24+18,6))
        assert saturation==expected_s
        assert (hue,lightness)==struct.unpack_from('<h',f.image,source+12)+struct.unpack_from('<h',f.image,source+16)
        assert hue==lightness==0
        coefficients.append(dict(sector=sector,S=saturation,H=hue,L=lightness))
    return dict(converter_COLOR_block=copied,packer=packed,HSL_selector=built,
                request_address=hex(request),request_sha256=sha(s.read(request,1132)),
                coefficients_address=hex(output),coefficients=coefficients,
                coefficient_sha256=sha(s.read(output+0x2a4,292)),
                neutral_HL_stock=True)


def lifetime_case(f,profile,fill):
    h=Harness(f,profile,fill);s=h.s
    initial_refresh=h.refresh(profile)
    before=h.values()
    first,a,allocation_a=h.allocate()
    populated_a=h.populate(first)
    assert h.capture_values(a)==before
    bytes_a=s.read(a,CAPTURE_BYTES)
    sector=(1,6,12)[profile-1]-1
    key=931+12*(profile-1)+sector
    new_value=5 if before[sector]!=5 else -5
    edit=h.edit(key,new_value)
    after=h.values()
    assert after!=before and after[sector]==new_value
    assert s.read(a,CAPTURE_BYTES)==bytes_a
    second,b,allocation_b=h.allocate()
    assert first!=second and a!=b
    populated_b=h.populate(second)
    assert h.capture_values(b)==after
    bytes_b=s.read(b,CAPTURE_BYTES)
    packed_a=pack_capture(h,a,before,0)
    packed_b=pack_capture(h,b,after,1)
    target=profile%3+1
    switched=h.edit(910,53+target)
    future=h.values()
    assert future!=after
    assert s.read(a,CAPTURE_BYTES)==bytes_a and s.read(b,CAPTURE_BYTES)==bytes_b
    released=h.release(first)
    third,c,allocation_c=h.allocate()
    assert (third,c)==(first,a)
    # Stock allocation resets its subsidiary handle, not the old COLOR data.
    stale_before_population=h.capture_values(c)
    assert stale_before_population==before
    populated_c=h.populate(third)
    assert h.capture_values(c)==future and s.read(c+18625,1)==bytes([target])
    assert s.read(b,CAPTURE_BYTES)==bytes_b
    packed_c=pack_capture(h,c,future,2)
    for packed in (packed_a,packed_b):
        assert sha(s.read(int(packed['request_address'],0),1132))==packed['request_sha256']
        assert sha(s.read(int(packed['coefficients_address'],0)+0x2a4,292))==packed['coefficient_sha256']
    final_releases=[h.release(second),h.release(third)]
    assert word(s,PARAM_POOL+64)==0
    assert int.from_bytes(s.read(PARAM_POOL+20,2),'little')==40
    return dict(kind='capture_lifetime',profile=profile,fill=hex(fill),
        preparation=h.preparation,refresh=initial_refresh,
        old_values=before,edited_values=after,next_profile=target,next_values=future,
        allocations=[allocation_a,allocation_b,allocation_c],
        populations=[populated_a,populated_b,populated_c],edit=edit,switch=switched,
        first_release=released,final_releases=final_releases,
        stale_COLOR_before_repopulation=stale_before_population,
        packed=[packed_a,packed_b,packed_c],
        in_flight_blocks_unchanged=True,freed_slot_and_pool_address_reused=True,
        packed_COLOR_values_survive_capture_reuse=True)


def interleaving_case(f,fill):
    h=Harness(f,1,fill);s=h.s
    h.refresh(1);before=h.values()
    index,address,allocation=h.allocate()
    prefix=h.populate(index,stop=SECTOR_SPLIT);at(s,prefix,SECTOR_SPLIT)
    registers=s.regs.copy()
    stack=s.read(0x18010000,0x10000)
    # Controlled host interleaving: save/restore CPU and stack. Shared RAM
    # changes persist. This does not assert that real scheduling permits it.
    edit=h.edit(910,55);after=h.values()
    s.write(0x18010000,stack);s.regs=registers
    tail=h.run();returned(s,tail)
    mixed=h.capture_values(address)
    assert mixed==before[:6]+after[6:] and mixed not in (before,after)
    assert s.read(address+18625,1)==b'\x01'
    return dict(kind='forced_midcopy_profile_switch',fill=hex(fill),allocation=allocation,
        prefix=prefix,interleaved_public_switch=edit,tail=tail,
        before=before,after=after,capture_values=mixed,captured_profile=1,
        proves_atomic_copy=False,
        limitation='Forced host interleaving; surrounding camera serialization/eligibility is not established.')


def compact_case(f,fill):
    """Full small COLOR updater, with explicit slot-selection contracts."""
    h=Harness(f,1,fill);s=h.s
    h.refresh(1);before=h.values()
    table,pointers=0x60646720,0x61bca0b4
    records=[]
    # This exact native descriptor table declares the required settings.
    # Map missing declared records before running, never on a fault.
    for i in range(29):
        key,kind,_,offset=struct.unpack_from('<HBBI',f.image,table-BASE+i*8)
        actual,count,address=struct.unpack('<HHI',f.read(0x61c281e4+(key>>4)*8,8))
        assert actual==key and (key&7) in (1,2,4)
        size=count*(key&7)
        try:s.read(address,size)
        except ValueError:s.ram(f'compact_declared_record_{key:x}',address,f.read(address,size))
        records.append(dict(key=hex(key),kind=kind,offset=offset,address=hex(address),bytes=size))
    s.ram('native_compact_setting_pointer_array',pointers,bytes([fill])*116)
    registered=invoke(s,0x60568e0f,0xf0,24,dict(d0=29,a0=table,a1=pointers))
    returned(s,registered)
    slots=(0x26000000,0x26001000)
    for slot in slots:
        s.ram('compact_slot_'+hex(slot),slot,bytes([fill])*632,aliases=False)
        s.write(slot+204,bytes(2))
    a=invoke(s,0x6055761d,0xf0,24,dict(a0=slots[0],a1=slots[0]+328))
    returned(s,a)
    assert struct.unpack('<12h',s.read(slots[0]+382,24))==before
    old=s.read(slots[0],632)
    edit=h.edit(910,55);after=h.values()
    b=invoke(s,0x6055761d,0xf0,24,dict(a0=slots[1],a1=slots[1]+328))
    returned(s,b)
    assert struct.unpack('<12h',s.read(slots[1]+382,24))==after
    assert s.read(slots[0],632)==old
    # Native gate: existing block is untouched when bit0x8000 is set.
    s.write(slots[0]+204,struct.pack('<H',0x8000))
    gated=s.read(slots[0],632)
    bypass=invoke(s,0x6055761d,0xf0,24,dict(a0=slots[0],a1=slots[0]+328))
    returned(s,bypass)
    assert s.read(slots[0],632)==gated
    return dict(kind='compact_COLOR_copy',fill=hex(fill),records=records,
        native_pointer_registration=registered,old_values=before,new_values=after,
        first=a,intervening_profile_switch=edit,second=b,gated_no_copy=bypass,
        old_slot_unchanged=True,
        limits='Full COLOR updater, but supplied slots and gate values; runtime ring selection and live-view submission remain unjoined.')


def frontiers(f,fill):
    h=Harness(f,1,fill);s=h.s
    h.refresh(1)
    index,address,_=h.allocate()
    # Without the identified exposure initialization, retain the old strict
    # stop. No camera/hardware result is silently supplied.
    regions=s.regions.copy()
    s.regions=[r for r in s.regions if not r.name.startswith('initial_exposure_halfwords')]
    missing=invoke(s,0x6025350c,0xb0,16,dict(d0=index))
    assert missing['status']=='memory_fault' and missing['pc']=='0x605de5d5'
    assert missing['fault']['address']==0x618d2678
    # Restore the same memory objects, preserving any writes already made.
    removed=[r for r in regions if r.name.startswith('initial_exposure_halfwords')]
    s.regions.extend(removed)
    h.populate(index)
    s.ram('captured_iseq_debug_policy',0x618b5108,f.read(0x618b5108,4))
    s.ram('native_iseq_history',0x61c67324,bytes([fill])*1208)
    log_init=invoke(s,0x6051886e,0,4);returned(s,log_init)
    s.ram('native_conversion_configuration',0x61c67be8,bytes([fill])*26)
    s.ram('native_conversion_configuration_copy',0x618b5144,bytes([fill])*10)
    config_init=invoke(s,0x60522730,0x80,4);returned(s,config_init)
    # Deliberately incomplete enclosing descriptor. Its +124 pointer has no
    # established owner yet; keep it null and report the actual dereference.
    s.write(BUFFER,bytes(256))
    s.write(BUFFER,struct.pack('<I',address))
    output=0x27000000
    s.ram('full_converter_destination',output,bytes([fill])*6032,aliases=False)
    result=invoke(s,0x6052010f,0xf0,48,dict(a0=output,a1=BUFFER,d0=0))
    assert result['status']=='memory_fault' and result['pc']=='0x60521914',result
    assert result['fault']['address']==0x1314 and word(s,BUFFER+124)==0
    compact=lambda r:{k:v for k,v in r.items() if k not in ('trace_tail','stop_registers')}
    return [dict(kind='missing_exposure_initialization',fill=hex(fill),execution=compact(missing)),
            dict(kind='outer_converter_secondary_descriptor_frontier',fill=hex(fill),
                 history_initialization=log_init,configuration_initialization=config_init,
                 execution=compact(result),missing_input_pointer_offset=124,
                 first_secondary_read_offset=4884,
                 limitation='The enclosing job descriptor is incomplete, not evidence of a camera null-pointer fault.')]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--quick',action='store_true',help='One nonzero-fill development case only')
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    f=Fixture();cases=[]
    for fill in ((0xa5,) if args.quick else (0,0xa5)):
        for profile in ((1,) if args.quick else (1,2,3)):
            cases.append(lifetime_case(f,profile,fill))
            print(f'COLOR{profile}, fill {fill:#x}: allocation, edits, copies, release/reuse passed',flush=True)
        cases.append(interleaving_case(f,fill))
        print(f'Fill {fill:#x}: forced interleaving exposes mixed snapshot',flush=True)
        cases.append(compact_case(f,fill))
        print(f'Fill {fill:#x}: compact COLOR copies and bypass gate passed',flush=True)
        cases.extend(frontiers(f,fill))
        print(f'Fill {fill:#x}: missing-exposure and enclosing-descriptor boundaries passed',flush=True)
    spans={
        'slot-initialization':(0x602496d8,0x60249743),
        'slot-allocation':(0x60249743,0x6024992a),
        'slot-release':(0x6024992a,0x602499b8),
        'slot-accessor':(0x60249c22,0x60249c68),
        'parameter-release':(0x60249ecf,0x60249f1e),
        'capture-population':(0x6025350c,0x60253dd3),
        'exposure-initial-values':(0x605d76b6,0x605d76cf),
        'pool-allocation':(0x605488ae,0x60548999),
        'pool-get-pointer':(0x60548b10,0x60548bc1),
        'pool-inner-allocation':(0x60549fbd,0x6054a0a4),
        'converter-COLOR':(0x6052056e,0x605205f9),
        'packer':(0x604c3051,0x604c3260),
        'HSL-selector':(0x604f747f,0x604f7572),
        'compact-current-slot':(0x60557319,0x605573f0),
        'compact-COLOR-copy':(0x6055761d,0x605576f5),
        'compact-pointer-registration':(0x60568e0f,0x60568e3d),
        'compact-descriptor-copy':(0x60568e3d,0x60568eb6),
        'converter-entry':(0x6052010f,0x6052016a),
        'converter-secondary-descriptor':(0x6052190f,0x60521943),
        'converter-initial-configuration':(0x60522730,0x60522780),
        'iseq-history-initializer':(0x6051886e,0x60518893),
        'diagnostic-suppression':(0x600241b5,0x600241cf),
    }
    folder=args.out/'disassembly';folder.mkdir()
    for name,(lo,hi) in spans.items():
        (folder/(name+'.asm')).write_text(window(f.image,DEFAULT_IMAGE,DEFAULT_OBJDUMP,lo,hi))
    root=Path.cwd();sources={Path(__file__).resolve()}
    for module in list(sys.modules.values()):
        file=getattr(module,'__file__',None)
        if file and Path(file).resolve().is_relative_to(root/'tools'):sources.add(Path(file).resolve())
    report=dict(main_sha256=sha(f.image),checkpoint_sha256=CHECKPOINT_SHA,
        engine_sha256=sha(ENGINE.read_bytes()),
        source_sha256={str(path.relative_to(root)):sha(path.read_bytes()) for path in sorted(sources)},
        cases=cases,spans={key:list(map(hex,value)) for key,value in spans.items()},
        limits=[
            'Native capture-pool/slot operations, but supplied physical RAM and modeled uncontended kernel exclusion.',
            'Invalid-slot diagnostics use the native suppression flag; null-return validation still executes.',
            'Full capture-population function with an initialized-default exposure scenario and captured base object; not a physical exposure.',
            'Public property edit/refresh is native; physical GUI input and capture scheduling are not replayed here.',
            'The capture-to-job COLOR conversion is still an interior contract. Outer job metadata, submission and completion/release ordering remain open.',
            'Neutral H/L checks existing stock coefficients, not an implemented H/L extension.',
            'Forced midcopy interleaving tests function-local atomicity, not whether the camera permits that scheduling.',
            'Compact COLOR updater executes in full with its registered setting pointers; ring selection and live-view lifecycle are not yet joined.',
            'No firmware image, camera access, pixel rendering or recovery claim.',
        ])
    (args.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'{len(cases)} ownership/interleaving cases passed.',flush=True)


if __name__=='__main__':main()
