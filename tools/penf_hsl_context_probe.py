#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Offline native HSL configuration and hardware-table submission probes.

Synthetic request/context, not a full capture. MMIO is write-capture memory,
not a pixel engine. Only the two LUT-cache lock helpers are modeled.
Never accesses a camera or saves an installable firmware image.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import struct

from penf_emulator import BASE, ROOT, ENGINE, Region, firmware
from penf_probe import ProbeState, CALLER
from penf_color_fixtures import CONTEXT, REQUEST, OUTPUT, changes, YELLOW_L
from penf_color_table_patch import candidate
from penf_diagnostic_lifetime_probe import helpers, HOLE
from penf_recovery_isolation_probe import without_ranges
from penf_repack_preflight import save, sha
from penf_disasm import window, DEFAULT_IMAGE, DEFAULT_OBJDUMP

FLAGS = 0x19060000
CACHE = 0xa1c61df8
# (packed-output pointer offset, MMIO LUT-bank offset, source element bytes)
LUTS = [(0x1434,0x1400,4),(0x1438,0x1600,4),(0x143c,0x1800,4),
        (0x1440,0x1a00,2),(0x1444,0x1c00,4),(0x1448,0x1e00,2),
        (0x144c,0x2000,2),(0x1450,0x2200,2),(0x1454,0x2400,2),
        (0x1458,0x2600,2)]
LOCKS = {0x604fa0ca:'LUT-cache lock; single-thread model',
         0x604fa0ec:'LUT-cache unlock; single-thread model'}
SUBMIT_LOCKS = {**LOCKS,0x604fa11a:'engine reservation lock; single-thread model',
               0x604fa14c:'engine reservation unlock; single-thread model'}
CALLBACK = 0x19070000
JOB_SLOTS = 0x618a3c24  # CPU 0 entry in native pointer table 605f9cc0


def state(image, target, mask, frame, registers):
    s = ProbeState(target,mask,frame,bytes(16),registers)
    s.regions = [replace(r,data=image) if r.name=='main' else r for r in s.regions]
    s.regions = without_ranges(s.regions,[HOLE])
    return s


def finished(s, result):
    assert result['status']=='breakpoint' and s.regs['pc']==CALLER+7, (
        result['status'],result.get('fault'),hex(s.regs['pc']))
    assert s.regs['sp']==0x18018000


def build(image, mode=11, saturation=0, process_type=0x200, bypass=False):
    s = state(image,0x604f2973,0x20,8,dict(a0=CONTEXT))
    context = bytearray(192)
    struct.pack_into('<3I',context,4,REQUEST,FLAGS,OUTPUT)
    struct.pack_into('<I',context,56,2 if mode==11 else 0x64602e)
    request = bytearray(1132)
    struct.pack_into('<H',request,10,mode)
    struct.pack_into('<H',request,28,process_type)
    struct.pack_into('<12b',request,1076,*([saturation]*12))
    if bypass:
        request[1071]=1
        struct.pack_into('<H',request,12,0xa200)
    s.ram('context',CONTEXT,context,aliases=False)
    s.ram('request',REQUEST,request,aliases=False)
    s.ram('output',OUTPUT,bytes(5212),aliases=False)
    helpers(s)
    result = s.run({CALLER+7},limit=200000)
    finished(s,result)
    output,context = s.read(OUTPUT,5212),s.read(CONTEXT,192)
    report = dict(mode=mode,saturation=saturation,process_type=hex(process_type),
        bypass=bypass,instructions=s.steps,output_sha256=sha(output),
        hsl_enable=hex(struct.unpack_from('<I',output,0x3c4)[0]),
        tone_pointer=hex(struct.unpack_from('<I',output,0x1230)[0]),
        lut_pointers=[hex(x) for x in struct.unpack_from('<10I',output,0x1434)],
        packed_hue_lightness=[dict(sector=i,
            hue=struct.unpack_from('<h',output,0x2a4+i*24+18)[0],
            lightness=struct.unpack_from('<h',output,0x2a4+i*24+22)[0]) for i in range(12)],
        dirty_mask=hex(struct.unpack_from('<I',context,100)[0]),
        modeled_functions=[],returned=True,stack_restored=True)
    return output,context,s,report


def upload(image, output, context, bank=0, cache='new', dirty=0):
    assert bank in (0,1) and cache in ('new','same','other')
    coeff,lut = [(0x9e001800,0x9e00a400),(0x9e005800,0x9e00cc00)][bank]
    context = bytearray(context)
    struct.pack_into('<I',context,52,17)
    struct.pack_into('<I',context,100,dirty)
    context[189]=bank
    cached=[0,0]
    if cache!='new':cached[bank if cache=='same' else 1-bank]=17
    s=state(image,0x604b4933,0xf0,24,dict(a0=CONTEXT))
    s.ram('context',CONTEXT,context,aliases=False)
    s.ram('output',OUTPUT,output,aliases=False)
    s.ram('hardware_flags',FLAGS,struct.pack('<2I',8 if bank==0 else 0x10000,0),aliases=False)
    s.ram('lut_cache',CACHE,struct.pack('<2I',*cached))
    s.ram('coefficient_mmio',coeff,b'\xa5'*0x500,aliases=False)
    s.ram('lut_mmio',lut,b'\xa5'*0x2800,aliases=False)
    hooks={CALLER+7}|set(LOCKS)
    modeled=[]
    for _ in range(8):
        result=s.run(hooks,limit=200000)
        pc=s.regs['pc']
        if result['status']!='breakpoint' or pc==CALLER+7:break
        assert pc in LOCKS and s.regs['d0']==4
        modeled.append(hex(pc))
        s.events.append(dict(kind='model',entry=hex(pc),name=LOCKS[pc]))
        s.return_from_model(0)
    finished(s,result)
    registers, tables = s.read(coeff,0x500),s.read(lut,0x2800)
    enabled=struct.unpack_from('<I',output,0x3c4)[0]!=0
    should_upload=enabled and (cache!='same' or bool(dirty&4))
    details=[]
    for ptr_off,dest_off,width in LUTS:
        source=struct.unpack_from('<I',output,ptr_off)[0]
        actual=tables[dest_off:dest_off+512]
        if should_upload:
            values=struct.unpack('<128'+('I' if width==4 else 'H'),s.read(source,128*width))
            assert actual==struct.pack('<128I',*values)
        else:assert actual==b'\xa5'*512
        details.append(dict(pointer_offset=hex(ptr_off),source=hex(source),
            source_element_bytes=width,entries=128,destination=hex(lut+dest_off),
            uploaded=should_upload,sha256=sha(actual)))
    tone=struct.unpack_from('<I',output,0x1230)[0]
    if tone:
        assert tables[:1024]==struct.pack('<256I',*struct.unpack('<256H',s.read(tone,512)))
    else:assert tables[:1024]==b'\xa5'*1024
    if enabled:assert registers[0x2d8:0x3fc]==output[0x2a4:0x3c8]
    else:assert registers[0x3f8:0x3fc]==bytes(4)
    expected_cache=[0,0];expected_cache[bank]=17
    assert list(struct.unpack('<2I',s.read(CACHE,8)))==expected_cache
    assert modeled==['0x604fa0ca','0x604fa0ec']
    report=dict(bank=bank,coefficient_bank=hex(coeff),lut_bank=hex(lut),cache=cache,
        dirty=hex(dirty),instructions=s.steps,returned=True,stack_restored=True,
        coefficient_sha256=sha(registers),tables_sha256=sha(tables),
        hsl_luts_uploaded=should_upload,tone_uploaded=bool(tone),lut_details=details,
        modeled_functions=modeled,cache_after=expected_cache)
    return registers,tables,s,report


def reenter(s, target, mask, frame, registers=None):
    """A new synthetic caller, retaining the preceding stage's memory."""
    code=b'\xdd'+struct.pack('<i',target-CALLER)+bytes((mask,frame))+b'\xcb'
    s.regions=[replace(r,data=code) if r.name=='caller' else r for r in s.regions]
    s.regs=dict(pc=CALLER,sp=0x18018000,psw=0,**(registers or {}))


def submission(image, bank):
    output,context,built,_=build(image)
    context=bytearray(context)
    struct.pack_into('<I',context,0,17)
    struct.pack_into('<I',context,52,17)
    context[189]=bank
    request=bytearray(built.read(REQUEST,1132))
    struct.pack_into('<2I',request,0,CALLBACK,0x12345678)
    flags=bytearray(0x2100)
    mask=8 if bank==0 else 0x10000
    struct.pack_into('<I',flags,0,mask)
    struct.pack_into('<I',flags,0x3c,8)  # Synthetic channel mask, not a capture preset.
    s=state(image,0x604b3eb0,0xf0,24,dict(a0=CONTEXT))
    s.ram('context',CONTEXT,context,aliases=False)
    s.ram('output',OUTPUT,output,aliases=False)
    s.ram('request',REQUEST,request,aliases=False)
    s.ram('hardware_flags',FLAGS,flags,aliases=False)
    s.ram('lut_cache',CACHE,bytes(8))
    coeff,lut=[(0x9e001800,0x9e00a400),(0x9e005800,0x9e00cc00)][bank]
    router=0x9e000400+bank*0x4000
    s.ram('coefficient_mmio',coeff,b'\xa5'*0x500,aliases=False)
    s.ram('lut_mmio',lut,b'\xa5'*0x2800,aliases=False)
    s.ram('engine_control_mmio',0x9e000000,bytes(0x200),aliases=False)
    s.ram('router_mmio',router,bytes(0x200),aliases=False)
    s.ram('clock_request_mmio',0x988000d4,bytes(8),aliases=False)
    s.ram('engine_users',0x8ff00198,bytes(1),aliases=False)
    s.regions.append(Region('cpu0',0x8050,bytes(4),'r'))
    s.ram('job_slots_cpu0',JOB_SLOTS,bytes(8*44))
    # IRQ enable copies a pre-existing shadow configuration to MMIO.
    # Marker 1234 is only to verify that data flow, not a valid hardware setup.
    s.ram('irq_shadow',0xa1bf33cc,struct.pack('<122I',*([0x1234]*122)))
    s.ram('irq_mmio',0x99200000,bytes(488),aliases=False)
    # Native callback stub is a harness witness: mov 1,d0; retf [],0.
    s.regions.append(Region('callback_witness',CALLBACK,b'\x80\x01\xde\x00\x00','rx'))
    modeled=[]
    for _ in range(12):
        result=s.run({CALLER+7}|set(SUBMIT_LOCKS),limit=200000)
        pc=s.regs['pc']
        if result['status']!='breakpoint' or pc==CALLER+7:break
        assert pc in SUBMIT_LOCKS
        modeled.append(dict(entry=hex(pc),argument=s.regs['d0']))
        s.return_from_model(0)
    finished(s,result)
    submit_steps=s.steps
    slot=JOB_SLOTS+3*44
    record=s.read(slot,44)
    assert struct.unpack_from('<3I',record)==(17,CALLBACK,0x12345678)
    assert struct.unpack_from('<I',record,12)[0]==mask
    assert record[43]==(2|bank) and s.read(CONTEXT+190,1)==b'\x01'
    assert s.read(0x99200000+101*4,4)==struct.pack('<I',0x1234)
    assert s.read(coeff+0x2d8,292)==output[0x2a4:0x3c8]
    assert s.read(0x8ff00198,1)==b'\x01'
    # Native start path, with explicit MMIO capture for the mode-zero helper.
    s.ram('aux_enable_mmio',0x99900008,bytes(4),aliases=False)
    s.ram('aux_config_mmio',0x99901000,bytes(0x30),aliases=False)
    s.ram('aux_cached_state',0xa1c6310c,bytes(1))
    reenter(s,0x604b3fd2,0,4,dict(a0=CONTEXT))
    result=s.run({CALLER+7},limit=200000);finished(s,result)
    start_steps=s.steps-submit_steps
    expected={0x48:0x800000,0x1c:0,0x50:8,0x58:8,0xac:0x100000}
    for offset,value in expected.items():
        assert s.read(0x9e000000+offset,4)==struct.pack('<I',value)
    assert s.read(0x99901000,4)==struct.pack('<I',0x8005)
    # Explicitly injected status; no pixels are generated and no interrupt
    # controller dispatch is simulated. Call the registered handler directly.
    irq_cases=[]
    for label,status_b,mask_b,notify in [('status',0x100000,0x100000,True),
            ('masked',0x100000,0,False),('no_status',0,0x100000,False)]:
        for offset,value in {0x68:0,0xa8:0,0x70:status_b,0xac:mask_b}.items():
            s.write(0x9e000000+offset,struct.pack('<I',value))
        before=s.steps
        # Handler has its own MOVM prologue; the synthetic CALL saves no regs.
        reenter(s,0x604bd56f,0,0)
        result=s.run({CALLER+7,CALLBACK},limit=200000)
        callback=None
        if s.regs['pc']==CALLBACK:
            callback={k:hex(s.regs[k]) for k in ('d0','a0','a1')}
            assert callback==dict(d0='0x9',a0='0x0',a1='0x12345678')
            result=s.run({CALLER+7},limit=200000)
        finished(s,result)
        assert bool(callback)==notify
        assert s.read(0x9e0000a8,8)==bytes(8)
        irq_cases.append(dict(name=label,status_b=hex(status_b),mask_b=hex(mask_b),
            callback=callback,instructions=s.steps-before,returned=True))
    report=dict(bank=bank,submit_instructions=submit_steps,start_instructions=start_steps,
        registered_slot=3,job_record=record.hex(),enabled_irq=101,
        irq_shadow_marker='0x1234 (synthetic, not a hardware configuration)',
        modeled_functions=modeled,start_registers={hex(0x9e000000+k):hex(v) for k,v in expected.items()},
        interrupt_cases=irq_cases,coefficient_sha256=sha(s.read(coeff,0x500)),
        tables_sha256=sha(s.read(lut,0x2800)),returned=True,
        limits='Separate native stage calls with preserved memory, synthetic engine masks, '
               'single-thread locks, MMIO write capture and manually injected status. '
               'IRQ handler invoked directly, with a synthetic notification callback.')
    return s.read(coeff,0x500),s.read(lut,0x2800),report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    stock,patched=firmware(),candidate(7)
    builds=[];uploads=[]
    for mode,sat,ptype,bypass in [(11,s,t,False) for s in (-5,0,5) for t in (0x100,0x200)]+[
            (2,0,0x200,False),(3,0,0x200,False),(4,0,0x200,False),(5,0,0x200,False),
            (11,0,0x200,True)]:
        a,ca,sa,ra=build(stock,mode,sat,ptype,bypass)
        b,cb,sb,rb=build(patched,mode,sat,ptype,bypass)
        expected=[YELLOW_L,YELLOW_L+1] if mode==11 and not bypass else []
        assert changes(a,b)==expected
        assert ca==cb and sa.regs==sb.regs and sa.steps==sb.steps
        rb['stock_to_candidate_output_diff']=list(map(hex,expected))
        builds.append(rb)
        if mode==11 and sat==0 and ptype==0x200 and not bypass:
            for bank in (0,1):
                for cache,dirty in [('new',0),('same',0),('same',4),('other',0)]:
                    wa,ta,_,ua=upload(stock,a,ca,bank,cache,dirty)
                    wb,tb,_,ub=upload(patched,b,cb,bank,cache,dirty)
                    assert changes(wa,wb)==[0x2ee,0x2ef] and ta==tb
                    assert ua['instructions']==ub['instructions']
                    ub['stock_to_candidate_register_diff']=['0x2ee','0x2ef']
                    ub['stock_and_candidate_luts_identical']=True
                    ub['mode']=mode
                    uploads.append(ub)
        if mode in (2,4):
            for bank in (0,1):
                wa,ta,_,ua=upload(stock,a,ca,bank)
                wb,tb,_,ub=upload(patched,b,cb,bank)
                assert wa==wb and ta==tb and ua==ub
                ub['mode']=mode
                ub['stock_to_candidate_register_diff']=[]
                ub['stock_and_candidate_luts_identical']=True
                uploads.append(ub)
    submissions=[]
    for bank in (0,1):
        wa,ta,ra=submission(stock,bank)
        wb,tb,rb=submission(patched,bank)
        assert changes(wa,wb)==[0x2ee,0x2ef] and ta==tb
        assert {k:v for k,v in ra.items() if k!='coefficient_sha256'}=={
            k:v for k,v in rb.items() if k!='coefficient_sha256'}
        rb['stock_to_candidate_register_diff']=['0x2ee','0x2ef']
        submissions.append(rb)
    windows={
        'processing-job':(0x604a6821,0x604a68b9),
        'processing-dispatch':(0x604aa595,0x604aa7fe),
        'mode-dispatch':(0x604f2973,0x604f29de),
        'full-builder':(0x604f8543,0x604f860e),
        'builder-wrappers':(0x604f88e3,0x604f89c3),
        'hsl-builder':(0x604f7272,0x604f747f),
        'hsl-selector':(0x604f747f,0x604f7572),
        'tone-builder':(0x604f7c66,0x604f7d3e),
        'hardware-submission':(0x604b3eb0,0x604b3fed),
        'register-dispatch':(0x604b4933,0x604b4d2e),
        'coefficient-writer':(0x604b5006,0x604b51de),
        'lut-writer':(0x604b58c4,0x604b5af6),
        'register-job':(0x604b65dc,0x604b66a8),
        'simple-start':(0x604b488a,0x604b4933),
        'start-auxiliary':(0x604fc5f2,0x604fc87d),
        'slot3-interrupt':(0x604bd56f,0x604bd60c),
        'callback-dispatch':(0x604b31a2,0x604b31b9),
        'irq-enable-wrapper':(0x60086d10,0x60086d1e),
        'irq-enable':(0x6006d94e,0x6006d99b)}
    old_path=ROOT/'analysis/historical_patch_3100/stock-3100-main.bin'
    old=old_path.read_bytes();stability=[]
    for name,(lo,hi) in windows.items():
        (args.out/(name+'.asm')).write_text(window(stock,DEFAULT_IMAGE,DEFAULT_OBJDUMP,lo,hi))
        stability.append(dict(name=name,start=hex(lo),end_exclusive=hex(hi),
            bytes=hi-lo,identical_3100_3101=old[lo-BASE:hi-BASE]==stock[lo-BASE:hi-BASE]))
    report=dict(status='offline native configuration, submission, start and status probes passed',
        main_sha256=sha(stock),candidate_sha256=sha(patched),build_pairs=builds,
        upload_pairs=uploads,submission_pairs=submissions,
        candidate_padding_inaccessible=list(map(hex,HOLE)),
        reviewed_windows=stability,stock_3100_sha256=sha(old),
        limits=['Synthetic requests and contexts, not a full capture/live-view lifecycle.',
            'Hardware flags select only either color-processing register bank.',
            'LUT-cache lock/unlock modeled as successful single-thread operations.',
            'MMIO captures writes only; no hardware pixel processing, DMA or interrupt delivery.',
            'LUT field semantics and some source-boundary overlaps remain unidentified.',
            'No whole-program proof of padding ownership or physical recovery.'],
        source_sha256={str(q.relative_to(ROOT)):sha(q.read_bytes()) for q in
            [Path(__file__).resolve(),ROOT/'tools/penf_emulator.py',
             ROOT/'tools/penf_boot_emulator.py',ROOT/'tools/penf_update_probe.py',ROOT/'tools/penf_probe.py',
             ROOT/'tools/penf_color_table_patch.py',ROOT/'tools/penf_diagnostic_lifetime_probe.py',
             ROOT/'tools/penf_recovery_isolation_probe.py',ROOT/'tools/penf_disasm.py',ENGINE]})
    save(args.out,'audit',report)
    print(json.dumps(dict(build_pairs=len(builds),upload_pairs=len(uploads),
        submission_pairs=len(submissions),status=report['status']),indent=2))


if __name__=='__main__':main()
