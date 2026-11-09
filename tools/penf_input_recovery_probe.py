#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Offline PEN-F input and SD-client probes; no device access or image output.

Native instructions run until an explicit boundary or an unknown access. SD
filesystem calls are modeled, so this does not establish physical activation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from penf_emulator import BASE,ROOT,Region,firmware,call_function
from penf_probe import ProbeState, CALLER, RESULT, LOGS
from penf_update_probe import source_hashes

INITIALIZER_SOURCE=0x601ea800
INITIALIZER_END=0x6020b220
INITIALIZER_RAM=0x615fc540


def initialize_pointers(state):
    b=firmware()
    state.ram('startup_pointer_initializers',INITIALIZER_RAM,
              b[INITIALIZER_SOURCE-BASE:INITIALIZER_END-BASE])


def key_lookup(event,variant=0):
    s=ProbeState(0x6019ac8e,0xb0,20,b'\0'*16,
        dict(d0=event,d1=RESULT+2,a0=RESULT,a1=RESULT+1))
    initialize_pointers(s)
    s.ram('key_variant',0x61c57fd8,struct.pack('<I',variant))
    result=s.run({CALLER+7},limit=30000)
    return dict(event=hex(event),variant=variant,returned=s.regs['pc']==CALLER+7,
        group=s.regs['d0'],outputs=list(s.read(RESULT,3)),instructions=s.steps,
        stop=result['status'],pc=hex(s.regs['pc'])),s


def dial_delta(before,after):
    output=0x19000000
    r=call_function(0x6019867d,0x601986af,0xc0,8,
        [Region('magnitude',output,bytes(2),'rw',True)],
        dict(d0=before,d1=after,a0=output),trace_limit=0)
    out=next(x for x in r['memory'] if x['name']=='magnitude')
    return dict(before=before,after=after,status=r['status'],
        direction=r['registers']['d0'],capture=out),r


def key_state(event,matrix,variant=0):
    if event&0xffff!=4:raise ValueError('This fixture is for the low-level OK key, code 4')
    s=ProbeState(0x60198e64,0xe0,24,b'\0'*16,dict(d0=event))
    initialize_pointers(s)
    s.ram('key_globals',0x61c57fd8,bytes(0x500))
    s.write(0x61c57fd8,struct.pack('<I',variant))
    snapshot,width=(0x61c583f0,1) if variant==0 else (0x61c583ec,2)
    s.write(snapshot,matrix.to_bytes(width,'little'))
    s.write(0x615fcc30,b'\0')
    result=s.run({CALLER+7},limit=30000)
    return dict(event=hex(event),variant=variant,matrix=matrix,snapshot=hex(snapshot),
        returned=s.regs['pc']==CALLER+7,result=s.regs['d0'],
        instructions=s.steps,stop=result['status'],pc=hex(s.regs['pc'])),s


def board_selector(revision,dials=False):
    """Native key selector or dial-selector prefix; stop before dial hardware."""
    target,mask,frame,stop,globals_address=(
        (0x60197f66,0xf0,72,0x60197fc8,0x61c57f30) if dials else
        (0x60198d0a,0xc0,12,CALLER+7,0x61c57fd8))
    s=ProbeState(target,mask,frame,b'\0'*16,{})
    initialize_pointers(s)
    s.ram('selected_input_tables',globals_address,bytes(12))
    s.ram('decoded_board_revision',0x8ff00188,bytes((revision,)),aliases=False)
    result=s.run({stop},limit=30000)
    variant,table,configuration=struct.unpack('<III',s.read(globals_address,12))
    return dict(kind='dials' if dials else 'keys',board_revision=revision,
        reached_boundary=s.regs['pc']==stop,variant=variant,table=hex(table),
        configuration=hex(configuration),instructions=s.steps,
        stop=result['status'],pc=hex(s.regs['pc'])),s


def sd_client(package=None):
    """Run task entry, with modeled mount/file-load and trapped queue send.

    Only E122????BIN is present when a package is supplied. All other firmware
    patterns return the native client's not-found code. No service/write runs.
    """
    s=ProbeState(0x60b1cbb5,0,4,b'\0'*16,{})
    initialize_pointers(s)
    models={0x60022ee7:'timer fixed at zero',0x60b1ce50:'unmount completes',
            0x60b1ce10:'mount completes',0x60022720:'controller indication acknowledged',
            0x601c9016:'update LED indication suppressed'}
    hooks=LOGS|set(models)|{0x60b1ce80,0x60069429,0x601c8e6e,0x601c8eb2}
    searches=[];request=None
    for _ in range(200):
        r=s.run(hooks,limit=50000);pc=s.regs['pc']
        if r['status']!='breakpoint':break
        if pc in (0x60069429,0x601c8e6e,0x601c8eb2):
            if pc==0x60069429:
                envelope=struct.unpack('<II',s.read(s.regs['a0'],8))
                descriptor=s.read(envelope[0],envelope[1])
                pointer,size=struct.unpack_from('<II',descriptor)
                request=dict(queue=s.regs['d0'],envelope=[hex(x) for x in envelope],
                    descriptor_hex=descriptor.hex(),buffer=hex(pointer),bytes=size,
                    data_sha256=hashlib.sha256(s.read(pointer,size)).hexdigest())
            break
        if pc in LOGS:s.diagnostic()
        elif pc in models:
            s.events.append(dict(kind='model',entry=hex(pc),name=models[pc]))
            s.return_from_model(0)
        else:
            args=s.regs['a0']
            directory,pattern,dest,capacity,timeout=struct.unpack('<5I',s.read(args+4,20))
            name=s.read(pattern,11).decode('ascii')
            found=package is not None and name=='E122????BIN'
            searches.append(dict(pattern=name,directory=s.read(directory,11).decode('ascii'),
                destination=hex(dest),capacity=capacity,timeout=timeout,found=found))
            if found:
                if len(package)>capacity:raise ValueError('Fixture exceeds native client capacity')
                s.ram('modeled_file_contents',dest,package)
                s.write(args+32,struct.pack('<I',len(package)))
            s.events.append(dict(kind='model',entry=hex(pc),name='filesystem search/load modeled',
                                 pattern=name,result=0 if found else 0xe00))
            s.return_from_model(0 if found else 0xe00)
    return dict(scope='Native SD task after entry; filesystem, timer/controller/LED modeled; stop before service queue send or fallback. Physical OK trigger is outside scope.',
        supplied_size=0 if package is None else len(package),
        supplied_sha256=None if package is None else hashlib.sha256(package).hexdigest(),
        stop=r['status'],pc=hex(s.regs['pc']),instructions=s.steps,
        searches=searches,request=request,events=s.events),s


def sd_service(package,request,active_task=False):
    """Deliver the client's descriptor to native service; trap shared updater.

    Client output pointers are relocated into separate synthetic client RAM.
    Kernel queue/task/semaphore APIs are explicit models. Native preparation
    and dispatch execute, including the task-26 active/dormant branch.
    """
    s=ProbeState(0x60b1d012,0,4,b'\0'*16,{})
    s.ram('service_globals',0x619a5f88,bytes(32))
    s.ram('update_active_flag',0x61c5889c,bytes(4))
    s.ram('modeled_file_contents',int(request['buffer'],16),package)
    s.ram('separate_client_outputs',0x19000000,bytes(128),aliases=False)
    s.ram('task26_state',0x61c38b0c,bytes(56)+bytes((int(active_task),))+bytes(7))
    descriptor=bytearray.fromhex(request['descriptor_hex'])
    struct.pack_into('<I',descriptor,20,0x19000000)
    struct.pack_into('<I',descriptor,28,0x19000040)
    hooks=LOGS|{0x6006932d,0x6003535d,0x60069606,0x600696f9,0x60038368,0x60b1d527}
    dispatch=None;kernel_calls=[]
    for _ in range(50):
        r=s.run(hooks,limit=50000);pc=s.regs['pc']
        if r['status']!='breakpoint':break
        if pc==0x60b1d527:
            dispatch=dict(buffer=hex(s.regs['a0']),bytes=s.regs['d0'],mode=s.regs['d1'],
                result_pointer=hex(s.regs['a1']),data_sha256=hashlib.sha256(s.read(s.regs['a0'],s.regs['d0'])).hexdigest())
            break
        if pc in LOGS:s.diagnostic();continue
        row=dict(entry=hex(pc),d0=s.regs['d0'],d1=s.regs['d1'])
        if pc==0x6006932d:
            target,capacity=struct.unpack('<II',s.read(s.regs['a0'],8))
            assert s.regs['d0']==125 and capacity==32
            s.write(target,descriptor);row['model']='deliver captured SD request'
        elif pc==0x6003535d:
            assert s.regs['d0']==26
            s.write(s.regs['a0'],struct.pack('<H',2 if active_task else 16))
            row['model']='task 26 active' if active_task else 'task 26 dormant'
        elif pc==0x60038368:
            assert s.regs['d0']==26;row['model']='task 26 wake acknowledged'
        else:
            assert s.regs['d0']==21;row['model']='semaphore 21 succeeds'
        kernel_calls.append(row);s.events.append(dict(kind='model',**row))
        s.return_from_model(0)
    return dict(scope='Native service preparation and dispatch; modeled kernel calls; stops before shared updater. Client result pointers relocated into separate host RAM.',
        active_task26_scenario=active_task,stop=r['status'],pc=hex(s.regs['pc']),
        instructions=s.steps,dispatch=dispatch,kernel_calls=kernel_calls,
        native_update_active_flag=struct.unpack('<I',s.read(0x61c5889c,4))[0],
        native_task26_current_flag=s.read(0x61c38b44,1)[0],
        native_task26_previous_flag=s.read(0x61c38b45,1)[0],events=s.events),s


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    tests=[]
    for variant in range(4):
        for event in (0x02000004,0x02010004,0x0202ffff,0x02021901):
            r,s=key_lookup(event,variant);tests.append(r)
            assert r['returned'],(r,s.events[-1])
            expected=(0 if variant==0 else 1) if event in (0x02000004,0x02010004) else (11 if event==0x0202ffff else 255)
            assert r['group']==expected,r
            if r['group']<11:assert r['outputs']==[4 if variant==0 else 13,2,0],r
    states=[]
    for variant in range(4):
        bit,full=(16,255) if variant==0 else (8192,65535)
        for event in (4,0x02000004,0x02010004):
            for matrix in (0,bit,full^bit,full):
                r,s=key_state(event,matrix,variant);states.append(r)
                assert r['returned'],(r,s.events[-1])
                assert r['result']==(1 if matrix&bit else 0),r
    deltas=[]
    for before,after,direction,count in ((0,1,1,1),(1,0,0,1),(1023,0,1,1),(0,1023,0,1),(100,104,1,4),(104,100,0,4),(400,400,1,0)):
        r,raw=dial_delta(before,after);deltas.append(r)
        assert r['status']=='returned',r
        assert r['direction']==direction and int.from_bytes(bytes.fromhex(r['capture']['hex']),'little')==count,r
    boards=[]
    for revision in range(5):
        for dials in (False,True):
            r,s=board_selector(revision,dials);boards.append(r)
            assert r['reached_boundary'],(r,s.events[-1])
            assert r['variant']==int(revision!=0),r
            if dials:assert r['table']==('0x601c300c' if revision==0 else '0x601c3054'),r
    for name,package in [('absent',None),('resource',None)]:
        if name=='resource':
            stock=(ROOT/'firmware_files/OLY_E_122_3101_0000_0000.BIN').read_bytes()
            package=stock[0x1460000:0x2a60000]
            assert hashlib.sha256(package).hexdigest()=='17ddbd06e5ebe8e7ea5ae8edca2ed1553ea24ad4cd2842589e3d41d2199018fb'
        r,s=sd_client(package)
        (args.out/f'sd_{name}.json').write_text(json.dumps(r,indent=2)+'\n')
        print(name,r['stop'],r['pc'],r['request'],flush=True)
        if r['stop']!='breakpoint':print(str(s.events[-1])[:1200],flush=True)
        assert r['pc']==('0x601c8e6e' if package is None else '0x60069429'),r['pc']
        if package is not None:
            assert r['request']['data_sha256']==r['supplied_sha256']
            assert r['request']['queue']==125 and r['request']['bytes']==len(package)
            descriptor=bytes.fromhex(r['request']['descriptor_hex'])
            assert len(descriptor)==32 and struct.unpack_from('<III',descriptor,8)==(0,35,1)
            for active in (False,True):
                service,state=sd_service(package,r['request'],active)
                (args.out/f'service_active_{active}.json').write_text(json.dumps(service,indent=2)+'\n')
                print('service',active,service['pc'],service['dispatch'],flush=True)
                if not service['dispatch']:print(str(state.events[-1])[:1200],flush=True)
                assert service['dispatch'] and service['dispatch']['mode']==0
                assert service['dispatch']['bytes']==len(package)
                assert service['dispatch']['data_sha256']==r['supplied_sha256']
                assert service['native_update_active_flag']==1
                assert service['native_task26_current_flag']==0
                assert service['native_task26_previous_flag']==int(active)
                assert len(service['kernel_calls'])==(5 if active else 2)
    report=dict(main_sha256=hashlib.sha256(firmware()).hexdigest(),
        source_sha256=dict(source_hashes(),**{str(Path(__file__).resolve().relative_to(ROOT)):hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}),
        key_lookups=tests,key_states=states,dial_deltas=deltas,board_selectors=boards)
    (args.out/'input_tests.json').write_text(json.dumps(report,indent=2)+'\n')
    manifest=dict(scope='Offline native input and modeled SD client/service slices; no physical trigger, full boot, filesystem or flash emulation.',
        main_sha256=report['main_sha256'],source_sha256=report['source_sha256'],
        test_counts=dict(key_lookup=len(tests),key_state=len(states),dial_delta=len(deltas),
                         board_selector=len(boards),sd_client=2,sd_service=2),
        output_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(args.out.glob('*.json'))})
    (args.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest['test_counts'],indent=2))


if __name__=='__main__':main()
