#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Summarize a boot experiment and export exact-build supporting disassembly."""
import argparse
from collections import Counter
import hashlib
import gzip
import json
from pathlib import Path
import re
import subprocess
import struct

from penf_emulator import firmware, ROOT, BASE
from penf_disasm import window, DEFAULT_IMAGE, DEFAULT_OBJDUMP

WINDOWS = {
    'primary_c_startup': (0x600210f9,0x600213ed),
    'primary_dma_clear': (0x600213ed,0x600215df),
    'kernel_entry_variants': (0x60032a04,0x60032a2d),
    'kernel_shared_readiness': (0x60033511,0x6003359c),
    'kernel_mac_selftest': (0x6003383b,0x60033920),
    'peer_notification_and_context': (0x6003008c,0x60030127),
    'initial_task': (0x6006ad97,0x6006ae7d),
    'system_services': (0x60041ae3,0x60041d9a),
    'normal_application_startup': (0x60041d9a,0x60042063),
    'gpio_configuration_readback': (0x6008454f,0x600845ff),
    'timer_frequency_query': (0x6008f263,0x6008f5e4),
    'elapsed_counter': (0x60022ee7,0x60022f00),
    'busy_delay': (0x6008ff06,0x6008ff2f),
    'controller_initialization': (0x6007d1c2,0x6007d371),
    'retained_controller_words': (0x6007d97b,0x6007d9a5),
    'controller_operation': (0x60022720,0x60022758),
    'watchdog_interface': (0x60090d50,0x60090ddf),
    'parameter_bank_selection': (0x60071658,0x60071b67),
    'battery_request_dispatch': (0x60076cd5,0x60076d0c),
    'battery_sample_request': (0x60075e15,0x60075eb5),
    'adc_setup': (0x60079a1e,0x60079c09),
    'adc_start_and_poll': (0x60079c09,0x60079ead),
    'adc_result_reader': (0x6007a207,0x6007a2c1),
    'adc_interrupt_handler': (0x6007a4d3,0x6007a5bd),
    'small_object_allocator': (0x600233bd,0x60023459),
    'flash_address_bases': (0x600221de,0x6002221e),
    'irq_vectors': (0x60030020,0x60030078),
    'irq_context_save_restore': (0x600300f7,0x60030127),
    'kernel_irq_wrapper': (0x600393eb,0x6003952f),
    'timer_handlers': (0x6006e7f0,0x6006e8e0),
    'software_doorbell_queue': (0x60080530,0x600805e8),
    'software_irq_handlers': (0x6008066f,0x60080717),
    'adc_deferred_cleanup': (0x6007b894,0x6007ba2c),
    'adc_callback_completion': (0x6007bee4,0x6007bf6f),
    'peer1_initial_task': (0x600271e7,0x600272a4),
    'peer2_initial_task': (0x6002764c,0x60027701),
    'cache_maintenance': (0x6007dc71,0x6007dd38),
    'retained_parameter_copy': (0x600735dc,0x60073625),
    'gpio_configuration_query': (0x60084ea5,0x60084f41),
    'serial_initialization': (0x6008a9f1,0x6008aa61),
    'serial_mode2_configuration': (0x6008ac46,0x6008ad52),
    'serial_clock_divisor': (0x6008c265,0x6008c2bb),
    'pll_multiplier_decode': (0x6008f5a9,0x6008f5e4),
    'power_startup_gate': (0x600419af,0x60041aa5),
    'gpio_input_read': (0x60022b92,0x60022c09),
    'controller_input_flags': (0x6007d43c,0x6007d48e),
    'gpio_irq_configuration': (0x6008474d,0x600847bb),
    'gpio_irq_enable_disable': (0x600848b9,0x600849e0),
    'input_peripheral_initialization': (0x6019d213,0x6019d285),
    'input_peripheral_configuration': (0x6019d285,0x6019d38a),
    'input_counter_and_enable': (0x6019d38a,0x6019d408),
    'serial_control_enable': (0x6008b5c8,0x6008b63c),
    'alex_ready_input': (0x6007ce88,0x6007ceb4),
    'alex_serial_transaction_prefix': (0x6007cca4,0x6007cd62),
    'alex_startup_first_command': (0x6007c914,0x6007c952),
    'alex_startup_commands': (0x6007c914,0x6007ca4b),
    'alex_transaction_and_retry': (0x6007cca4,0x6007cdea),
    'alex_compare_and_ready': (0x6007ce47,0x6007ceb4),
    'alex_completion_callback': (0x6007cf63,0x6007cf6e),
    'serial_irq_registration': (0x6008a924,0x6008a9f1),
    'serial_mode1_tx': (0x6008af4b,0x6008b09f),
    'serial_tx_fifo': (0x6008b1d3,0x6008b218),
    'serial_rx_fifo': (0x6008b4fe,0x6008b55b),
    'serial_irq_enable': (0x6008b55b,0x6008b5c8),
    'serial_irq_acknowledge': (0x6008b69e,0x6008b72e),
    'serial_common_irq_handler': (0x6008b898,0x6008b9b5),
    'serial_request_and_callback_dispatch': (0x6008e201,0x6008e301),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def summarize(report):
    executions=[e for e in report['events'] if e['kind']=='execution']
    per_cpu=Counter()
    for event in executions:
        per_cpu[event['cpu']]+=event['result']['completed']
    last=executions[-1]['result']
    milestones=[{k:v for k,v in e.items() if k!='tasks'}
                for e in report['events'] if e['kind']=='milestone']
    first=next((e['tasks'] for e in report['events'] if 'tasks' in e),[])
    return {
        'scope':report['scope'],
        'main_sha256':report['main_sha256'], 'source_sha256':report['source_sha256'],
        'scenarios':{k:v for k,v in report.items() if k.endswith('_scenario') or k in ('run_peers','assume_peer_ready')},
        'completed_instructions':report['completed_instructions'],
        'completed_by_cpu':dict(per_cpu), 'execution_segments':len(executions),
        'milestones':milestones,
        'task_start_requests':[e for e in report['events'] if e['kind']=='task_start_request'],
        'application_flash_reads':[e for e in report['events'] if e.get('name')=='decoded logical flash read' and int(e['source'],16)>=0x80000000],
        'delivered_interrupts':[e for e in report['events'] if e.get('name')=='idle-boundary hardware interrupt delivery'],
        'runtime_interrupt_state':report.get('runtime_interrupt_state'),
        'initial_cpu0_tasks':first, 'final_cpu0_tasks':report['final_cpu0_tasks'],
        'final_peer_tasks':report.get('final_peer_tasks',{}),
        'models':dict(Counter(e['name'] for e in report['events'] if e['kind']=='model')),
        'final':{'cpu':report['final_cpu'],'pc':report['final_pc'],'status':last['status'],
                 'fault':last['fault'],'registers':last['registers'],
                 'unresolved':last.get('unresolved'),
                 'last_event':report['events'][-1] if report['events'][-1]['kind']!='execution' else None},
        'limitations':[
            'Starts at downloaded main, not reset ROM; initial stack/status/straps are scenarios.',
            'Entire decoded main is initially executable; no execute-before-section-load detection.',
            'Conditional functional execution, not physical timing or recovery validation.',
            'Peer application tasks are cooperatively scheduled when enabled; IRQ delivery is restricted to reviewed idle boundaries and does not model physical timing, arbitrary preemption or nesting.',
            'The optional IRQ context model treats f6f0/f500 at two exact sites as an opaque save/restore pair. Its exact register identity and flag effects remain unverified.',
            'No peripheral MMU, caches, DMA timing, ECC faults, watchdog expiry or actual storage device.',
            'Mapped RAM poison helps expose some missing initialization; it is not byte-level uninitialized-read tracking.',
            'Task priority in snapshots is the creation parameter, not the mutable scheduler priority.',
        ],
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trace',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--snapshot',type=Path,help='Optional inspection snapshot from the same run')
    args=p.parse_args()
    if args.out.exists(): p.error('Use a new output directory')
    raw=args.trace.read_bytes()
    report=json.loads(gzip.decompress(raw) if args.trace.suffix=='.gz' else raw)
    for relative,expected in report['source_sha256'].items():
        if digest((ROOT/relative).read_bytes())!=expected:
            raise ValueError(f'Trace uses another source/engine revision: {relative}')
    data=firmware()
    if report['main_sha256']!=digest(data): raise ValueError('Main image differs')
    older=(ROOT/'analysis/preset_startup_final/penf3100.main.bin').read_bytes()
    if digest(older)!='3d5963c6d9385aafc99ff51892ec706bef1c4783a84f586179271a64b8401bfd':
        raise ValueError('Stock 3100 reference differs')
    args.out.mkdir(parents=True)
    result=summarize(report)
    if sum(result['completed_by_cpu'].values())!=result['completed_instructions']:
        raise ValueError('Inconsistent instruction totals')
    result['trace']={'path':str(args.trace),'sha256':digest(raw)}
    if args.snapshot:
        snapshot=json.load(gzip.open(args.snapshot,'rt'))
        if snapshot['completed']!=report['completed_instructions'] or snapshot['cpu']!=report['final_cpu']:
            raise ValueError('Snapshot belongs to another execution')
        byname={r['name']:r for r in snapshot['regions']}
        def read(address,size):
            r=next(r for r in snapshot['regions'] if r['address']<=address and address+size<=r['address']+r['size'])
            root=byname[r['alias_of']] if r['alias_of'] else r
            offset=address-r['address']
            return bytes.fromhex(root['hex'][2*offset:2*(offset+size)])
        pointer=struct.unpack('<I',read(0xa1c38694,4))[0]
        sample_buffer=struct.unpack('<I',read(0xa1c38414,4))[0]
        result['adc_frontier']={
            'request_address_or_sentinel':hex(pointer),
            'native_channel':struct.unpack('<H',read(0xa1c3840a,2))[0],
            'sample_buffer':hex(sample_buffer),
            'sample_count_and_completed':list(struct.unpack('<HH',read(sample_buffer,4))),
            'register_words':{hex(a):hex(struct.unpack('<I',read(a,4))[0]) for a in
                              (0x98c00000,0x98c00004,0x98c00008,0x98c0000c,0x98c00010,0x98c00014)},
            'note':'Final emulated state; register/sample values are explicit scenarios, not measured hardware responses. A request allocation can be stale after callback/free.',
        }
        if pointer not in (0,0xffffe,0xfffff):
            request=read(pointer,56)
            result['adc_frontier']['request']={'hex':request.hex(),
                'logical_id':request[2],'mode':request[3],
                'rate_parameter':struct.unpack_from('<I',request,8)[0],
                'requested_samples':struct.unpack_from('<I',request,12)[0],
                'result_destination':hex(struct.unpack_from('<I',request,16)[0]),
                'callback':hex(struct.unpack_from('<I',request,36)[0])}
        result['snapshot']={'path':str(args.snapshot),'sha256':digest(args.snapshot.read_bytes())}
        result['application_state']={
            'power_state_618642cc':struct.unpack('<I',read(0x618642cc,4))[0],
            'startup_flags_618656a8':read(0x618656a8,16).hex(),
            'note':'Native state under the selected inputs, not a hardware observation. Power gate writes 99 on rejection, 0 on acceptance, then 1 in its deferred callback.'}
        result['alex_initial_commands']=[{
            'address':hex(address),'tx_hex':read(address,5).hex(),
            'expected_rx_hex':read(address+5,5).hex(),
            'note':'Native relocated RAM constants; inferred request/reply pairs from 6007c914 and 6007cca4, not observed wire traffic.'}
            for address in range(0x611711d0,0x61171249,20)]
        if report.get('alex_peer_scenario'):
            result['alex_frontier']={
                'completion_byte':read(0xa1c389e4,1).hex(),
                'last_reply':read(0xa1c38a14,5).hex(),
                'serial_config':read(0xa1c3cd20,8).hex(),
                'packed_config':hex(struct.unpack('<I',read(0xa1c3cdc8,4))[0]),
                'irq_priority':{str(cpu):{str(irq):hex(struct.unpack('<I',read(base+4*irq,4))[0])
                    for irq in (68,69)} for cpu,base in enumerate((0x99200000,0x99300000,0x99b00000))},
                'note':'Native priority registers identify CPU0 as serial IRQ owner; replies remain hypothetical.'}
    exports={}
    for name,(lo,hi) in WINDOWS.items():
        asm=window(data,DEFAULT_IMAGE,DEFAULT_OBJDUMP,lo,hi)
        lines=[line for line in asm.splitlines() if re.match(r'^[0-9a-f]{8}:',line)]
        tail=lines[-1].split('\t')
        complete=int(tail[0][:-1],16)+len(tail[1].split())==hi
        exports[name]={'start':hex(lo),'end_exclusive':hex(hi),'file':name+'.asm',
                       'sha256':digest(data[lo-BASE:hi-BASE]),'ends_on_instruction_boundary':complete,
                       'identical_in_3100':data[lo-BASE:hi-BASE]==older[lo-BASE:hi-BASE]}
        (args.out/(name+'.asm')).write_text(asm)
    helper=data[0x113c9e0:0x113c9e0+0x1800]
    helper_path=args.out/'iram-helper.bin'
    helper_path.write_bytes(helper)
    asm=subprocess.check_output([str(DEFAULT_OBJDUMP),'-b','binary','-m','mn10300','-D','-z',
        '--insn-width=16','--adjust-vma=0x47000800','--start-address=0x47001112',
        '--stop-address=0x4700114d',str(helper_path)],text=True)
    (args.out/'relocated_watchdog_refresh.asm').write_text(asm)
    result['windows']=exports
    result['helper_sha256']=digest(helper)
    result['windows_identical_in_3100']=sum(w['identical_in_3100'] for w in exports.values())
    (args.out/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'instructions':result['completed_instructions'],'final':result['final'],
                      'windows':len(exports),'same_in_3100':result['windows_identical_in_3100']},indent=2))


if __name__=='__main__':
    main()
