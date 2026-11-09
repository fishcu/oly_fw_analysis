#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Compare explicit held/released OK levels during the existing bounded boot.

No camera access. Other type-2 buttons are supplied at their native release
level; non-button input levels retain the earlier scenario. No input edges,
GPIO IRQs or controller wake reasons are invented. Unknown accesses stop.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import struct

from penf_boot_emulator import boot_experiment
from penf_boot_audit import summarize
from penf_emulator import BASE, ROOT, firmware
from penf_input_recovery_probe import key_state


def input_levels(revision, held):
    data = firmware()
    variant = int(revision != 0)
    gpio = {pin: 0 for pin in (112,82,75,76,68,61,114,133,70,158,71,62,63,171,77)}
    gpio[83] = 1  # Existing hypothetical alex-ready input, unchanged.
    controller = 0
    records = []
    for group, table, count in ((0, (0x601c3674,0x601c369c)[variant], 5),
                                 (1, (0x601c3700,0x601c3770)[variant], 14)):
        for index in range(count):
            code, kind, active, _, _ = struct.unpack_from('<I4B', data, table-BASE+8*index)
            if kind != 2:
                continue
            level = active if code == 4 and held else active ^ 1
            row = dict(group=group,index=index,key_code=hex(code),level=level,
                       active_level=active,descriptor=hex(table+8*index))
            if group == 0:
                controller |= level << index
                row['register'] = hex(0x98e00058+4*index)
            else:
                physical_table = (0x601c37e0,0x601c3930)[variant]
                logical = struct.unpack_from('<I', data, physical_table-BASE+24*index)[0]
                pin = struct.unpack_from('<H', data, 0x600261b8-BASE+8*logical+2*revision)[0]
                assert pin < 191
                gpio[pin] = level
                row.update(logical_pin=logical, physical_pin=pin)
            records.append(row)
    return controller, gpio, records


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--revision',type=int,choices=(0,1),default=0)
    ap.add_argument('--ok',choices=('held','released'),required=True)
    ap.add_argument('--out',type=Path,required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    data=firmware()
    straps = {data[0x60026864-BASE+i+1]:data[0x60026864-BASE+i]
              for i in range(0,16,2)}
    controller,gpio,records=input_levels(args.revision,args.ok=='held')
    source_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report,state=boot_experiment(ideal_storage=True,erased_parameters=True,run_peers=True,
        strap_bits=straps[args.revision],timer_clock=True,counter_step=1000,
        controller_init=True,peripheral_reset=True,adc_clock=True,adc_sample=900,
        runtime_peers=True,runtime_irqs=120,serial_clock_word=0x200000,
        controller_input_bits=controller,gpio_inputs=gpio,input_counter=0,
        alex_peer='startup',segments=3200)
    with gzip.open(args.out/'trace.json.gz','wt') as f:json.dump(report,f)
    summary=summarize(report)
    def read(address,size):
        try:return state.read(address,size)
        except ValueError:return None
    samples={hex(a):(raw.hex() if (raw:=read(a,n)) is not None else None)
             for a,n in ((0x8ff00188,1),(0xa1c57fd8,4),(0xa1c583f0,1),
                         (0xa1c583ec,2),(0xa1c57fd0,4),(0x618505c8,1),(0x618505a0,2))}
    variant_raw=read(0xa1c57fd8,4)
    getter=None
    if variant_raw is not None:
        variant=int.from_bytes(variant_raw,'little')
        if variant in (0,1):
            raw=read(0xa1c583f0 if variant==0 else 0xa1c583ec,1 if variant==0 else 2)
            if raw is not None:
                getter,_=key_state(4,int.from_bytes(raw,'little'),variant)
    summary['button_scenario']=dict(requested_revision=args.revision,ok=args.ok,
        controller_mask=controller,gpio_levels=gpio,descriptor_inputs=records,
        final_input_ram=samples,isolated_getter_using_final_snapshot=getter,
        scope='Type-2 native button levels only; non-button levels, wake reason, IRQ generation and scheduler retain existing assumptions.')
    summary['source_sha256'].update({str(Path(__file__).resolve().relative_to(ROOT)):source_sha,
        'tools/penf_input_recovery_probe.py':hashlib.sha256((ROOT/'tools/penf_input_recovery_probe.py').read_bytes()).hexdigest(),
        'tools/penf_probe.py':hashlib.sha256((ROOT/'tools/penf_probe.py').read_bytes()).hexdigest()})
    (args.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(dict(ok=args.ok,revision=args.revision,instructions=state.steps,
        final_pc=report['final_pc'],last_event=report['events'][-1],samples=samples,
        key_getter=getter),indent=2))


if __name__=='__main__':main()
