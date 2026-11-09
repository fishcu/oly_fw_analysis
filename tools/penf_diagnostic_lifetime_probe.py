#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Offline shell/read-request and section-initializer probes; no camera I/O.

Native execution stops at unreviewed accesses. Flash reads are replaced by
explicit synthetic page contents; no boot bytes or installable firmware are produced.
"""
import argparse
import json
from pathlib import Path
import struct

from penf_emulator import BASE, ROOT, ENGINE, Region, firmware
from penf_probe import ProbeState, CALLER, LOGS
from penf_recovery_isolation_probe import without_ranges
from penf_repack_preflight import save, sha
from penf_disasm import window, DEFAULT_IMAGE, DEFAULT_OBJDUMP

HOLE = (0x6069b2b0, 0x6069b7c0)


def helpers(s):
    b = firmware()
    s.regions.append(Region('relocated_helpers', 0x47000800,
        b[0x113c9e0:0x113c9e0+0x1800], 'rx'))


def parser_state(s):
    # Same explicitly scoped libc state as the previous diagnostic probe.
    s.ram('libc_locale_pointers', 0x61bc1a40, bytes(0x34))
    s.ram('libc_scanf_state', 0x61bc1d70, bytes(12))
    s.ram('libc_printf_locale_pointer', 0x61bc1d80, bytes(4))
    s.ram('libc_scanf_character_set', 0x61bc1c70, bytes(255))
    s.ram('libc_numeric_token', 0x61bc1a74, bytes(32))
    helpers(s)


def initializers(out, fill):
    s = ProbeState(0x6006da8c, 0xa0, 12, bytes(16), dict(d0=3))
    s.regions = without_ranges(s.regions, [HOLE])
    # Explicit destination objects established by the eleven constructor
    # call sequences; never turn the loaded section into writable scratch.
    s.ram('section3_static_objects', 0x61c69320, bytes([fill])*0x30c0)
    s.ram('internal_static_objects', 0x8ff001b4, bytes([fill])*0x240, aliases=False)
    helpers(s)
    constructors = struct.unpack_from('<11I', firmware(), 0x6069b240-BASE)
    hooks = LOGS | set(constructors) | {CALLER+7}
    reached = []
    for _ in range(40):
        result = s.run(hooks, limit=200000)
        pc = s.regs['pc']
        if result['status'] != 'breakpoint' or pc == CALLER+7:
            break
        if pc in LOGS:
            s.diagnostic()
        else:
            reached.append(hex(pc))
            step = s.run(hooks-{pc}, limit=1)
            assert step['status'] == 'instruction_limit' and step['completed'] == 1
    report = dict(returned=s.regs['pc']==CALLER+7,
        stack_restored=s.regs['sp']==0x18018000, instructions=s.steps,
        table_start='0x6069b240', table_bytes=44, constructors=reached,
        inaccessible_range=list(map(hex, HOLE)), initial_object_fill=hex(fill),
        object_sha256=sha(s.read(0x61c69320,0x30c0)),
        internal_object_sha256=sha(s.read(0x8ff001b4,0x240)),
        events=s.events,
        limits='Native section-3 initializer dispatcher and eleven constructor bodies only; '
               'two explicit initial-RAM scenarios, not all later application states.')
    save(out, 'initializers-'+hex(fill), report)
    assert report['returned'] and report['stack_restored'], (result['status'], result.get('fault'))
    assert reached == list(map(hex, constructors))
    return {k:v for k,v in report.items() if k != 'events'}


def dump_request(out, cpu):
    args = ['flash', 'p', 'dump', '40000000']
    argv, strings = 0x19000000, 0x19000100
    blob = b''; pointers = []
    for arg in args:
        pointers.append(strings+len(blob)); blob += arg.encode()+b'\0'
    # Start at the normal U_SHELL name dispatcher, not directly at flash.
    s = ProbeState(0x601a6f6c, 0xf0, 20, bytes(16), dict(a0=argv,d0=len(args)))
    s.ram('argv', argv, struct.pack('<4I',*pointers), aliases=False)
    s.ram('strings', strings, blob, aliases=False)
    s.ram('flash_command_buffer_pointers', 0x6117119c, bytes(8))
    s.ram('large_buffer_allocation_bits', 0x61c556b4, bytes(16))
    # Native 60023b28 advances this cursor before selecting a bitmap slot.
    s.ram('large_buffer_allocation_cursor', 0x61c554c8, struct.pack('<I',0xffffffff))
    s.regions.append(Region('CPU_index_scenario', 0x8050, struct.pack('<I',cpu), 'r'))
    parser_state(s)
    services = {0x60022ee7:'fixed timer', 0x60086c0b:'interrupt exclusion',
                0x60086c54:'interrupt restoration', 0x60070bc0:'diagnostic context enter',
                0x60070cb1:'diagnostic context leave'}
    forbidden = {0x60021e3e,0x60022402,0x60071267}
    hooks = LOGS | set(services) | forbidden | {CALLER+7,0x600219b5,0x60021ad0}
    request = None; reads = []
    s.ram('dump_line_format_scratch',0x61c9cd00,bytes(256))
    for _ in range(400):
        result = s.run(hooks, limit=200000)
        pc = s.regs['pc']
        if result['status'] != 'breakpoint' or pc == CALLER+7:
            break
        assert pc not in forbidden, 'Unexpected flash mutation request'
        if pc == 0x600219b5:
            request = dict(source=hex(s.regs['d1']), destination=hex(s.regs['d0']),
                           bytes=s.regs['a0'])
            slot=(0,64,96)[cpu]
            buffer=0x6122a540+slot*0x4040
            assert request == dict(source='0x40000000',destination=hex(buffer),bytes=2048)
            s.ram('allocated_dump_slot',buffer,b'\xa5'*0x4040)
            s.write(buffer,bytes(range(256))*8)
            reads.append(dict(operation='modeled main-page read',**request))
            s.events.append(dict(kind='model',**reads[-1]));s.return_from_model(0)
        elif pc == 0x60021ad0:
            assert s.regs['d0']==0x40000000 and s.regs['a0']==buffer+2048
            s.write(buffer+2048,b'\x5a'*128)
            reads.append(dict(operation='modeled spare read',source=hex(s.regs['d0']),
                              destination=hex(s.regs['a0']),bytes=128))
            s.events.append(dict(kind='model',**reads[-1]));s.return_from_model(0)
        elif pc in LOGS:
            s.diagnostic()
        else:
            s.events.append(dict(kind='model',name=services[pc],entry=hex(pc)))
            s.return_from_model(0)
    formatted=[e['message'] for e in s.events if e.get('kind')=='model' and
               e.get('message','').startswith('4000')]
    sample=bytes(range(256))*8
    expected_lines=[f'{0x40000000+i:08X} : '+
                    ' '.join(f'{x:04X}' for x in struct.unpack_from('<8H',sample,i))
                    for i in range(0,2048,16)]
    expected_lines.append('40000800 : '+' '.join(['5A5A']*6))
    report = dict(arguments=args,cpu=cpu,request=request,reads=reads,instructions=s.steps,
        pc=hex(s.regs['pc']),allocation_bits=s.read(0x61c556b4,16).hex(),events=s.events,
        returned=s.regs['pc']==CALLER+7,stack_restored=s.regs['sp']==0x18018000,
        formatted_main_rows=128,formatted_spare_bytes=12,
        exact_formatted_output=formatted==expected_lines,
        limits='Synthetic normal shell dispatch. Native parser and free-slot allocation; '
               'empty allocation bitmap and modeled exclusion/context/timer. Main/spare reads '
               'are synthetic successful results; native formatting/release execute. No actual '
               'boot data, transport delivery, hardware read/ECC or allocation-failure behavior established.')
    save(out,'dump-request-cpu'+str(cpu),report)
    assert request is not None, (result['status'], result.get('fault'))
    expected_slot = (0,64,96)[cpu]
    expected_buffer = 0x6122a540 + expected_slot*0x4040
    assert request == dict(source='0x40000000',destination=hex(expected_buffer),bytes=2048),request
    assert report['returned'] and report['stack_restored'], (result['status'],result.get('fault'))
    assert len(reads)==2 and s.read(0x61c556b4,16)==bytes(16)
    assert report['exact_formatted_output']
    return {k:v for k,v in report.items() if k != 'events'}


def uart_byte(out, port, available):
    s = ProbeState(0x6006d22c,0,0,bytes(16),{})
    s.regions.append(Region('console_port_scenario',0x8ff0007c,bytes([port]),'r'))
    status, data = ((0x9870000c,0x98700008),(0x9840000c,0x98400008))[port]
    s.regions.append(Region('RX_available_scenario',status,struct.pack('<I',int(available)),'r'))
    if available:
        s.regions.append(Region('RX_byte_scenario',data,struct.pack('<I',ord('f')),'r'))
    result=s.run({CALLER+7},limit=100)
    assert result['status']=='breakpoint' and s.regs['pc']==CALLER+7
    assert s.regs['d0']==(ord('f') if available else 0)
    report=dict(port=port,available=available,status_register=hex(status),data_register=hex(data),
        result=s.regs['d0'],instructions=s.steps,events=s.events,
        limits='Native polling byte-reader with fixed hardware values; no physical serial pins or USB transport established.')
    save(out,'uart-'+str(port)+'-'+str(int(available)),report)
    return {k:v for k,v in report.items() if k!='events'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args(); args.out.mkdir(parents=True,exist_ok=False)
    init=[initializers(args.out,x) for x in (0,0xa5)]
    print('Both native section-3 initializer cases passed',flush=True)
    dumps=[dump_request(args.out,cpu) for cpu in range(3)]
    print('Three native allocate / modeled read / format / free cases passed',flush=True)
    uart=[uart_byte(args.out,p,a) for p in range(2) for a in (False,True)]
    print('Four native UART byte cases passed',flush=True)
    windows={
        'initializer-dispatch':(0x6006da8c,0x6006db18),
        'postload-waiter':(0x60042123,0x600421e1),
        'uart-input':(0x6006d22c,0x6006d262),
        'line-reader':(0x6006fb2e,0x6006fb85),
        'shell-task':(0x601a700e,0x601a70cc),
        'system-shell-task':(0x6006fbae,0x6006fc98),
        'shell-message-receive':(0x6006fc98,0x6006fcd2),
        'shell-start':(0x60041ecf,0x60041eea),
        'shell-dispatch':(0x601a6f6c,0x601a6fa7),
        'shell-serial-init':(0x60b2ad44,0x60b2ae3f),
        'shell-serial-input':(0x60b2b7dd,0x60b2b828),
        'dump-allocation':(0x600236bb,0x60023733),
        'dump-command':(0x60072bbf,0x60072d3b),
        'fixed-buffer-other-owner':(0x610a15ca,0x610a1685),
    }
    b=firmware();older=(ROOT/'analysis/preset_startup_final/penf3100.main.bin').read_bytes()
    window_report=[]
    for name,(a,z) in windows.items():
        (args.out/(name+'.asm')).write_text(window(b,DEFAULT_IMAGE,DEFAULT_OBJDUMP,a,z))
        window_report.append(dict(name=name,start=hex(a),end_exclusive=hex(z),
                                  identical_3100=b[a-BASE:z-BASE]==older[a-BASE:z-BASE]))
    paths=(Path(__file__).resolve(),ROOT/'tools/penf_update_probe.py',ROOT/'tools/penf_probe.py',
           ROOT/'tools/penf_recovery_isolation_probe.py',ROOT/'tools/penf_emulator.py',
           ROOT/'tools/penf_boot_emulator.py',ENGINE)
    save(args.out,'summary',dict(all_assertions_passed=True,main_sha256=sha(b),
        initializers=init,dump_requests=dumps,uart=uart,windows=window_report,
        source_sha256={str(x.relative_to(ROOT)):sha(x.read_bytes()) for x in paths}))


if __name__=='__main__':
    main()
