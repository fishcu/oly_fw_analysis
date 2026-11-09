#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Offline native updater experiments. No camera, USB, or real flash access.

Starts at reviewed functions with synthetic callers, not physical SD activation.
Unknown memory/instructions stop. Diagnostic output is modeled; write requests
are trapped before the backend, or modeled against an in-memory medium.
Synthetic containers remain in host RAM only.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from penf_emulator import Region,firmware,BASE,ROOT,ENGINE
from oly_container import encode,decode,sum32
from penf_probe import ProbeState, CALLER, BUFFER, RESULT, LOGS

def source_hashes():
    """Hash execution dependencies when a probe runs, not during import."""
    paths = (Path(__file__).resolve(), ROOT/'tools/penf_probe.py',
             ROOT/'tools/penf_boot_emulator.py', ROOT/'tools/penf_emulator.py',
             ROOT/'tools/oly_container.py', ENGINE)
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths}




def synthetic_block(kind=0x101,model=0x1220,address=0x41800000,size=256):
    """Small control-flow fixture, not a functional firmware image. Never saved."""
    if size<16 or size%16:raise ValueError('16-byte aligned positive payload required')
    h=bytearray(32);h[:2]=b'OE'
    struct.pack_into('>H',h,2,model)
    struct.pack_into('<II',h,8,address,size)
    struct.pack_into('<HHH',h,16,0x100,0,kind)
    payload=bytes((i*17+3)&255 for i in range(size))
    trailer=bytearray(h)
    struct.pack_into('<I',trailer,28,(-sum32(h+payload+trailer))&0xffffffff)
    return bytes(h)+encode(payload)+bytes(trailer)


def update_probe(package,mode=0,backend_result=0):
    if mode not in (0,1,2):raise ValueError('Only reviewed user-update modes')
    state=ProbeState(0x60b1d527,0xf0,16,package,
                    dict(d0=len(package),d1=mode,a0=BUFFER,a1=RESULT))
    hooks=LOGS|{CALLER+7,0x6013024b,0x601c8d7c,0x601c8eb2}
    writes=[]
    for _ in range(200):
        result=state.run(hooks,limit=100000000)
        pc=state.regs['pc']
        if result['status']=='instruction_limit' and state.steps<2000000000:continue
        if result['status']!='breakpoint' or pc==CALLER+7:break
        if pc in LOGS:state.diagnostic()
        elif pc==0x6013024b:
            row=dict(destination=hex(state.regs['a0']),source=hex(state.regs['a1']),
                bytes=state.regs['d0'],backend_mode=state.regs['d1'],result=backend_result,
                input_sha256=hashlib.sha256(state.read(state.regs['a1'],state.regs['d0'])).hexdigest())
            writes.append(row)
            state.events.append(dict(kind='model',name='flash backend request trapped',**row))
            state.return_from_model(backend_result)
        elif pc in (0x601c8d7c,0x601c8eb2):
            state.events.append(dict(kind='model',name='update progress notification suppressed',
                                     entry=hex(pc),d0=state.regs['d0'],d1=state.regs['d1']))
            state.return_from_model(0)
    return dict(scope='Native shared user updater; synthetic call, diagnostics/notifications modeled; backend trapped before any flash operation',
        mode=mode,backend_result_scenario=backend_result,input_size=len(package),
        input_sha256=hashlib.sha256(package).hexdigest(),main_sha256=hashlib.sha256(firmware()).hexdigest(),
        source_sha256=source_hashes(),
        returned=state.regs['pc']==CALLER+7,result=state.regs['d0'],
        pc=hex(state.regs['pc']),instructions=state.steps,write_requests=writes,events=state.events),state


def flash_probe(failure='none',backend_mode=1):
    """Run native backend/page wrapper/readback with a separate in-memory medium.

    Only reviewed low-level erase/program/read APIs are modeled. The program
    wrapper and checksum execute, so lost return values are observable.
    """
    if failure not in ('none','erase','program','read','readback-corrupt'):
        raise ValueError('Unknown injected failure')
    if backend_mode not in (1,8):raise ValueError('Only reviewed update backend modes')
    package=synthetic_block(kind=0x100,address=0x403a0000,size=4032)
    package=package[:32]+decode(package[32:-32])+package[-32:]
    dest=0x403a0000
    state=ProbeState(0x6013024b,0xf0,36,package,
        dict(d0=len(package),d1=backend_mode,a0=dest,a1=BUFFER))
    state.ram('native_access_mode',0x61171110,bytes(2))
    state.ram('native_debug_flag',0x61171198,bytes(4))
    state.ram('diagnostic_log_full',0x61c280c0,struct.pack('<I',100))
    state.ram('native_page_scratch',0x61c9c500,b'\xa5'*2048)
    # Explicit single-thread/non-RTOS branch. Native PSW masking still executes;
    # scheduler exclusion used when this flag is 0x77777777 is outside this probe.
    state.regions.append(Region('non_rtos_flag_scenario',0x8ff003fc,bytes(4),'r'))
    storage=bytearray(b'\x55'*131072)
    services={0x600226d0:'storage lock acquired; single-thread scenario',
        0x600226f9:'storage lock released; single-thread scenario',
        0x60022ee7:'elapsed counter fixed at zero',
        0x6007dc71:'coherent cache; maintenance completes immediately'}
    hooks=LOGS|set(services)|{CALLER+7,0x60022402,0x60021e3e,0x600224c2,0x60130389,0x6007129d}
    operations=[];lower_result=None;program_wrapper_result=None
    for _ in range(100):
        result=state.run(hooks,limit=200000)
        pc=state.regs['pc']
        if result['status']!='breakpoint' or pc==CALLER+7:break
        if pc in LOGS:state.diagnostic()
        elif pc in services:
            state.events.append(dict(kind='model',name=services[pc],entry=hex(pc)))
            state.return_from_model(0)
        elif pc in (0x60130389,0x6007129d):
            if pc==0x60130389:lower_result=state.regs['d0']
            else:program_wrapper_result=state.regs['d0']
            state.events.append(dict(kind='milestone',name='native lower result observed',
                entry=hex(pc),result=state.regs['d0']))
            step=state.run(hooks-{pc},limit=1)
            if step['completed']!=1 or step['status']!='instruction_limit':break
        else:
            if pc==0x60022402:
                address,size=state.regs['a0'],state.regs['d1']
                offset=address-dest
                if offset<0 or offset+size>len(storage):raise ValueError('Erase outside test medium')
                rc=0x3101 if failure=='erase' else 0
                if not rc:
                    lo=offset//131072*131072;hi=(offset+size+131071)//131072*131072
                    storage[lo:hi]=b'\xff'*(hi-lo)
                row=dict(operation='erase',address=hex(address),requested_bytes=size,result=rc)
            elif pc==0x60021e3e:
                address,size,source=state.regs['d1'],state.regs['a0'],state.regs['d0']
                offset=address-dest
                if offset<0 or offset+size>len(storage):raise ValueError('Program outside test medium')
                rc=0x3102 if failure=='program' else 0
                if not rc:storage[offset:offset+size]=state.read(source,size)
                row=dict(operation='program',address=hex(address),bytes=size,result=rc)
            else:
                address,size,target=state.regs['a0'],state.regs['d1'],state.regs['a1']
                offset=address-dest
                if offset<0 or offset+size>len(storage):raise ValueError('Read outside test medium')
                rc=0x3101 if failure=='read' else 0
                if not rc:
                    contents=bytearray(storage[offset:offset+size])
                    if failure=='readback-corrupt':contents[40]^=1
                    state.write(target,contents)
                row=dict(operation='readback',address=hex(address),bytes=size,result=rc)
            operations.append(row)
            state.events.append(dict(kind='model',name='simulated flash API',**row))
            state.return_from_model(rc)
    return dict(scope='Native flash backend, write wrapper and readback check; modeled storage APIs, locks, timer and coherent cache; single-thread/non-RTOS flag scenario; synthetic 4096-byte block',
        failure=failure,backend_mode=backend_mode,returned=state.regs['pc']==CALLER+7,
        result=state.regs['d0'],lower_write_readback_result=lower_result,
        native_program_wrapper_result=program_wrapper_result,
        pc=hex(state.regs['pc']),instructions=state.steps,operations=operations,
        stored_bytes_equal_input=bytes(storage[:len(package)])==package,
        source_sha256=source_hashes(),
        main_sha256=hashlib.sha256(firmware()).hexdigest(),events=state.events),state


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--kind',type=lambda x:int(x,0),default=0x101)
    p.add_argument('--mode',type=int,choices=(0,1,2),default=0)
    p.add_argument('--bad-checksum',action='store_true')
    p.add_argument('--backend-result',type=lambda x:int(x,0),default=0)
    p.add_argument('--stock-resource',action='store_true',
        help='Use only stock 3101 type-0101 block, in RAM; trap every backend request')
    p.add_argument('--flash-scenario',choices=('none','erase','program','read','readback-corrupt'))
    p.add_argument('--flash-mode',type=int,choices=(1,8),default=1)
    args=p.parse_args()
    if args.flash_scenario is not None:
        if args.stock_resource:p.error('Choose one probe entry')
        report,state=flash_probe(args.flash_scenario,args.flash_mode)
    else:
        if args.stock_resource:
            original=(ROOT/'firmware_files/OLY_E_122_3101_0000_0000.BIN').read_bytes()
            offset=0x1460000
            size=struct.unpack_from('<I',original,offset+12)[0]+64
            package=bytearray(original[offset:offset+size])
            if hashlib.sha256(package).hexdigest()!='17ddbd06e5ebe8e7ea5ae8edca2ed1553ea24ad4cd2842589e3d41d2199018fb':
                raise ValueError('Stock resource block differs')
        else:package=bytearray(synthetic_block(args.kind))
        if args.bad_checksum:package[40]^=1
        report,state=update_probe(bytes(package),args.mode,args.backend_result)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('events','source_sha256')},indent=2))
    if not report['returned']:print(json.dumps(report['events'][-1],indent=2))


if __name__=='__main__':main()
