#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Qualify the published OM-3 V22 padding against native section boundaries.

Read-only inputs; decoded memory experiments only. Storage reads and one loaded
bit are explicit models. No installable firmware or camera access.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import struct

from oly_container import sha256
from om3_patch_audit import BASE, disassemble, require
from penf_code_space_audit import pointer_candidates, branch_candidates
from penf_emulator import ROOT, Region, firmware
from penf_probe import ProbeState, CALLER

STOCK = ROOT/'analysis/om3_1100/00_0100_50000020.decoded.bin'
PATCHED = ROOT/'analysis/om3_patch_v22/verified/patched-main-analysis-only.bin'
STOCK_SHA = '5e8d376e9111a44ac0352f26030d7c1b17026d42c45f3600cfa02a0e8c5b7d59'
PATCHED_SHA = '2fa0238100f8072b449b8722ef03069975e2a0180443ea338bd50f08a0e79f49'
DESCRIPTORS = 0x60029b28
END_GETTER = 0x60045e6c
LOADER = 0x60045ed5
READ = 0x600232d1
LOADED_BITS = 0xa32de590
# IDs follow native table indexing, not positional guesses from the FF runs.
CAVES = [(1, 0x6031e920, 0x6031efeb),
         (4, 0x60a8f100, 0x60a8f800),
         (9, 0x619a9680, 0x619a9800)]


class OM3Probe(ProbeState):
    def __init__(self, image, target, mask=0, frame=0, registers=None):
        super().__init__(target, mask, frame, bytes(128), registers or {})
        # Replace the entire pinned PEN-F image; no PEN-F address models run.
        self.regions = [Region(r.name, BASE, image, 'rx') if r.name == 'main'
                        else r for r in self.regions]


def call(state, target, mask=0, frame=0, **registers):
    state.write(CALLER, b'\xdd'+struct.pack('<i', target-CALLER)+bytes((mask, frame))+b'\xcb')
    state.regs = dict(pc=CALLER, sp=0x18018000, psw=0, **registers)


def exclude(state, low, high):
    """Leave a real unreadable hole, rather than filling it with harmless bytes."""
    regions = []
    for r in state.regions:
        end = r.address+len(r.data)
        if low < end and r.address < high:
            require(not r.capture and r.alias_of is None, 'Only exclude immutable input')
            if r.address < low:
                regions.append(replace(r, name=r.name+'_lo', data=r.data[:low-r.address]))
            if high < end:
                regions.append(replace(r, name=r.name+'_hi', address=high, data=r.data[high-r.address:]))
        else:
            regions.append(r)
    state.regions = regions


def end_probe(image, sid):
    state = OM3Probe(image, END_GETTER, registers={'d0': sid})
    result = state.run({CALLER+7}, limit=100)
    require(result['status'] == 'breakpoint' and state.regs['pc'] == CALLER+7,
            'End getter must return natively')
    require(state.regs['sp'] == 0x18018000, 'End getter stack')
    return state.regs['d0'], state.events


def load_probe(image, section):
    low, high = section['start'], section['end']
    state = OM3Probe(image, LOADER, 0xf0, 20, {'d0': section['id']})
    state.ram('loaded_section', low, b'\xa5'*(high-low), executable=True)
    state.ram('loaded_bits', LOADED_BITS, bytes(4))
    expected = image[low-BASE:high-BASE]
    passes = []
    for poison in (0xa5, 0x55):
        state.write(low, bytes([poison])*(high-low))
        state.write(LOADED_BITS, bytes(4))
        call(state, LOADER, 0xf0, 20, d0=section['id'])
        reads = []
        for _ in range(4):
            result = state.run({READ, CALLER+7}, limit=1000)
            require(result['status'] == 'breakpoint', 'Unexpected native loader stop')
            if state.regs['pc'] == CALLER+7:
                break
            args = tuple(state.regs[k] for k in ('a0','a1','d0','d1'))
            require(args == (low+0x40000000, section['source'], high-low, 0x10200),
                    f'Unexpected storage request: {args!r}')
            offset = section['source']-0x50000020
            require(image[offset:offset+high-low] == expected, 'Storage/source map disagreement')
            state.write(args[0], expected)
            reads.append(dict(destination=hex(args[0]), source=hex(args[1]), bytes=args[2], flags=hex(args[3])))
            state.return_from_model(0)
        require(state.regs['pc'] == CALLER+7 and state.regs['sp'] == 0x18018000, 'Loader return')
        require(len(reads) == 1 and state.read(low,high-low) == expected, 'Exact whole-section load')
        bits, = struct.unpack('<I',state.read(LOADED_BITS,4))
        require(bits == 1 << (section['id']-1), 'Wrong completion bit')
        passes.append(dict(initial_fill=hex(poison), read=reads[0], loaded_sha256=sha256(expected),
                           loaded_bit=hex(bits), stack_restored=True))
    return dict(passes=passes, events=state.events,
                limits='One modeled successful storage read and an explicit RAM loaded-bit word. '
                'No storage driver, boot/MPU/cache behavior or later scheduling/lifetime is modeled.')


def initializer_probe(image, target, pad_start, pad_end, nonzero_control=False):
    data = bytearray(image)
    require(data[target-BASE:target-BASE+6] == b'\xfc\xce'+bytes(4), 'Zero constructor byte count')
    if nonzero_control:
        struct.pack_into('<I', data, target-BASE+2, 4)
    state = OM3Probe(bytes(data), target, 0xa0, 12)
    exclude(state, pad_start, pad_end)
    result = state.run({CALLER+7}, limit=100)
    if nonzero_control:
        require(result['status'] == 'memory_fault' and result['fault']['address'] == pad_start,
                'Positive access control must fault on first constructor read')
    else:
        require(state.regs['pc'] == CALLER+7 and state.regs['sp'] == 0x18018000,
                'Zero-count constructor must skip the excluded padding')
    return dict(counterfactual_count_4=nonzero_control, events=state.events)


def tail_lookup_probe(image, pad_start, pad_end, wrap=False):
    # Stock 16-entry key/handler table immediately precedes the first cave.
    table = 0x6031e890
    data = bytearray(image)
    first_key, first_target = struct.unpack_from('<II', data, table-BASE)
    if wrap:
        # Replace only the last empty key in host memory to exercise the native
        # upper-bound wrap. The first key and all real targets stay unchanged.
        struct.pack_into('<I', data, table-BASE+15*8, first_key^0xffffffff)
    state = OM3Probe(bytes(data), 0x6031bdc9,
                     registers={'a0':120, 'd2':first_key})
    exclude(state, pad_start, pad_end)
    expected = first_target if wrap else 0x6031c0da
    result = state.run({expected, CALLER+7}, limit=100)
    require(result['status'] == 'breakpoint' and state.regs['pc'] == expected,
            'Bounded key lookup went outside the original table')
    return dict(counterfactual_last_key=wrap, target=hex(expected), events=state.events)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    require(not args.out.exists(), 'Use a fresh output directory')
    stock, patched = STOCK.read_bytes(), PATCHED.read_bytes()
    require(sha256(stock)==STOCK_SHA and sha256(patched)==PATCHED_SHA, 'Pinned OM-3 inputs')
    args.out.mkdir(parents=True)
    sections, native = [], {}
    for sid in range(1,11):
        end, events = end_probe(stock,sid)
        start, source, flag = struct.unpack_from('<III',stock,DESCRIPTORS-BASE+12*(sid-1))
        require(start <= end and start-BASE == source-0x50000020, 'Section descriptor map')
        sections.append(dict(id=sid,start=start,end=end,source=source,descriptor_flag=flag))
        native[f'end-{sid}']=events
    for sid in (0,11):
        end, events = end_probe(stock,sid)
        require(end==0, 'Out-of-range section selector')
        native[f'end-invalid-{sid}']=events
    rows=[]
    for sid,start,end in CAVES:
        section=sections[sid-1]
        lo,hi=start-BASE,end-BASE
        require(stock[lo:hi]==b'\xff'*(hi-lo), 'Patch bytes were not all FF')
        ff_lo,ff_hi=lo,hi
        while ff_lo and stock[ff_lo-1]==255:ff_lo-=1
        while ff_hi<len(stock) and stock[ff_hi]==255:ff_hi+=1
        pad_start=BASE+ff_lo;load_end=section['end']
        require(section['start']<=pad_start<=start<end<=load_end, 'Cave outside loaded padding')
        require(((pad_start+0x7ff)&~0x7ff)==load_end, 'Not 2-KiB tail alignment')
        native[f'load-stock-{sid}']=load_probe(stock,section)
        native[f'load-v22-{sid}']=load_probe(patched,section)
        refs=[]
        for name,low in [('runtime',start),('uncached',start+0x40000000),
                         ('logical_storage',section['source']+start-section['start'])]:
            refs += [dict(address_form=name,**r) for r in pointer_candidates(stock,low,low+end-start)]
        row=dict(section=sid,loaded_start=hex(section['start']),loaded_end=hex(load_end),
                 source=hex(section['source']),stock_ff_start=hex(pad_start),stock_ff_end=hex(BASE+ff_hi),
                 raw_ff_bytes=ff_hi-ff_lo,loaded_padding_bytes=load_end-pad_start,
                 added_start=hex(start),added_end=hex(end),guarded_bytes=end-start,
                 changed_bytes=sum(a!=b for a,b in zip(stock[lo:hi],patched[lo:hi])),
                 prefix_margin=start-pad_start,suffix_margin=load_end-end,
                 outside_loaded_ff_bytes=BASE+ff_hi-load_end,
                 stock_main_literal_candidates=refs)
        rows.append(row)
        if sid==1:
            native['lookup-empty']=tail_lookup_probe(stock,pad_start,load_end)
            native['lookup-wrap-control']=tail_lookup_probe(stock,pad_start,load_end,True)
        else:
            target={4:0x602153fb,9:0x6021543a}[sid]
            native[f'initializer-{sid}']=initializer_probe(stock,target,pad_start,load_end)
            native[f'initializer-access-control-{sid}']=initializer_probe(stock,target,pad_start,load_end,True)
    raw_branches=branch_candidates(stock,BASE,[(a,z) for _,a,z in CAVES])
    operand_sites={0x60a8d5e7:(0x60a8d5e5,'fc85ccf120a3'),
                   0x60a8d5fc:(0x60a8d5fa,'fc81ccf120a3'),
                   0x60a8d6cf:(0x60a8d6ce,'fccc0420001b'),
                   0x60a8dce1:(0x60a8dce0,'fccc00186702')}
    for row,hits in zip(rows,raw_branches):
        for hit in hits:
            site=int(hit['site'],16)
            if 0x6031e890<=site<0x6031e910:
                hit['classification']='Inside bounded 16-entry key/handler DATA table, not a branch instruction.'
            elif site in operand_sites:
                entry,expected=operand_sites[site]
                require(stock[entry-BASE:entry-BASE+len(expected)//2].hex()==expected,
                        'Branch-candidate enclosing instruction changed')
                hit['classification']='Starts inside an existing mov instruction, not a branch instruction.'
                hit['enclosing_instruction']=hex(entry)
        row['stock_main_relative_candidates']=hits
    # Recheck the comparison against actual PEN-F bytes, not only prose.
    penf=firmware()
    pa=json.loads((ROOT/'analysis/code_space/verified/audit.json').read_text())
    pc=next(c for c in pa['candidates'] if c['section']==3)
    low,high=int(pc['proposed_start'],16),int(pc['proposed_end_exclusive'],16)
    require(penf[low-BASE:high-BASE]==b'\xff'*(high-low),'PEN-F interior')
    table=struct.unpack_from('<11I',penf,0x6069b240-BASE)
    require(all(BASE<=v<BASE+len(penf) for v in table),'PEN-F constructor pointers')
    comparison=dict(candidate=pc,constructor_table_start='0x6069b240',constructor_count=11,
                    constructor_table_end='0x6069b26c',
                    same_2k_tail_alignment=((0x6069b26c+0x7ff)&~0x7ff)==0x6069b800,
                    existing_native_initializers='analysis/diagnostic_lifetime/final/')
    asm=args.out/'assembly';asm.mkdir()
    windows={'section-end-getter':(0x60045e6c,0x60045ed5),
             'native-section-loader':(LOADER,0x60045f44),
             'section-init-dispatch':(0x60045ff7,0x6004606d),
             'zero-count-initializers':(0x602153fb,0x6021545c),
             'bounded-neighbor-table':(0x6031bdbc,0x6031bdf0),
             'uncached-address-conversion':(0x60070fd4,0x60071018),
             'early-global-copy':(0x60021169,0x6002118c),
             'globals-at-end-of-first-ff-run':(0x6004b4cb,0x6004b500),
             'false-branch-store-operands':(0x60a8d5d6,0x60a8d603),
             'false-branch-mov-immediate-1':(0x60a8d6c5,0x60a8d6e1),
             'false-branch-mov-immediate-2':(0x60a8dcd1,0x60a8dcf7)}
    for name,(a,z) in windows.items():(asm/(name+'.asm')).write_text(disassemble(STOCK,a,z))
    unchanged=[]
    for a,z in [(DESCRIPTORS,DESCRIPTORS+120),(END_GETTER,0x60045f44),
                (0x602153fb,0x6021545c),(0x6031e890,0x6031e910)]:
        require(stock[a-BASE:z-BASE]==patched[a-BASE:z-BASE], 'V22 changed a qualification boundary')
        unchanged.append(dict(start=hex(a),end_exclusive=hex(z)))
    (args.out/'native.json').write_text(json.dumps(native,indent=2)+'\n')
    report=dict(stock_main_sha256=STOCK_SHA,patched_main_sha256=PATCHED_SHA,
                sections=sections,caves=rows,penf_comparison=comparison,unchanged_boundary_code_and_tables=unchanged,
                native_scenarios=len(native),all_assertions_passed=True,
                source_sha256={str(f.relative_to(ROOT)):sha256(f.read_bytes()) for f in
                    [Path(__file__).resolve(),ROOT/'tools/penf_probe.py',ROOT/'tools/penf_boot_emulator.py',
                     ROOT/'tools/penf_emulator.py',ROOT/'tools/om3_patch_audit.py',ROOT/'tools/penf_code_space_audit.py']},
                limits=['Bounded native loader and table-consumer cases; no complete OM-3 startup or hardware execution.',
                        'Storage service and loaded-bit RAM explicitly supplied; cache/MPU/DMA and later overwrites unproved.',
                        'Literal/relative scans cover main only and do not classify every raw match or computed access.',
                        'Author-reported success does not prove all three regions exercised by every demonstrated operation.',
                        'No independent PEN-F recovery or whole-lifecycle code ownership conclusion.'])
    (args.out/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(native_scenarios=len(native),caves=[{k:v for k,v in c.items() if 'candidates' not in k} for c in rows]),indent=2))


if __name__=='__main__':
    main()
