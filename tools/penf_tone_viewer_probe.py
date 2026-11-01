#!/usr/bin/env python3
"""Bounded COLOR query compaction and canonical native footer publication."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import struct

from penf_emulator import BASE, Region
from penf_hsl_context_probe import reenter
from penf_osd_bitmaps import BitmapBank
from penf_probe import ProbeState
from penf_tone_candidate import assemble, extract
from penf_tone_editor_probe import fixture, current, SERVICE, actuator, mode, ACTUATOR
from penf_tone_graph_candidate import build_graph
from penf_tone_probe import PRESERVED, INITIAL_SP
from penf_tone_transport_probe import put32, set_words
from penf_tone_points import FivePoints, resolve

VIEWER, GETTER_TABLE, GETTER = 0x19109000, 0x19108000, 0x190a0000
DESTINATIONS={8:('MIDDLE','BLACK/WHITE','SHADOW/HIGH'),17:('中間部','黒点・白点','明部・暗部')}
LABELS={(language,page):name+(' S0320 H0704',' M+1',' B0064 W0960')[page]+'@A028@'
        for language,names in DESTINATIONS.items() for page,name in enumerate(names)}


def getter_adapter(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    source = folder/'getter.s'
    source.write_text('''.section .text,"ax"
 movm [d2,a2],(sp)
 add -4,sp
 mov a1,a2
 call stock_raw_get,[],4
 mov d0,(a2)
 clr d0
 add 4,sp
 ret [d2,a2],8
''')
    layout = folder/'getter.ld'
    layout.write_text(f'SECTIONS {{ .text {GETTER:#x} : {{ *(.text) }} }}\n'
                      'stock_raw_get = 0x602b9f84;\n')
    return extract(assemble(folder/'assembly', [source], layout), 'text')


def middle_state(graph, image, getter, profile, controls, language, public_mode=None):
    state = fixture(graph.base, replace(graph.editor, image=image))
    state.regions.append(Region('bounded_GUI_getter_adapter', GETTER, getter, 'rx'))
    state.ram('getter_vtable', GETTER_TABLE, struct.pack('<3I', 0, 0, GETTER), aliases=False)
    put32(state, SERVICE, GETTER_TABLE)
    current(state, profile, controls)
    state.ram('viewer', VIEWER, bytes(120), aliases=False)
    mode = 53 + profile if public_mode is None else public_mode
    for offset, value in ((16, VIEWER + 8), (24, VIEWER + 12), (32, VIEWER + 14),
                          (36, VIEWER + 15), (68, mode)):
        put32(state, INITIAL_SP + offset, value)
    bank = BitmapBank()
    row = bank.rows[language]
    data = bank.data[row['start']:row['end']]
    state.regions.append(Region('stock_language', 0xa2ce3c00, data, 'r'))
    state.ram('selected_string_slot', 0x6160c2ec, b'\x01', aliases=False)
    state.ram('string_slots', 0x6161886c,
              struct.pack('<II', 0, struct.unpack_from('<I', data)[0]), aliases=False)
    state.regs = dict(PRESERVED, pc=0x60cfa110, sp=INITIAL_SP, psw=0,
                      d3=VIEWER, d2=0x60f8bbf0)
    return state


def run_middle(state, stop=0x60cfa572):
    queries = []
    instructions = 0
    while True:
        result = state.run({GETTER, stop}, limit=10000)
        instructions += result['completed']
        assert result['status'] == 'breakpoint', (result, hex(state.regs['pc']))
        if state.regs['pc'] == stop:
            return queries, instructions
        queries.append([state.regs['d0'], state.regs['a1'] - INITIAL_SP])
        result = state.run(set(), limit=1)
        instructions += result['completed']
        assert result['status'] == 'instruction_limit'


def middle_cases(graph, getter):
    rows = []
    for profile in (1, 2, 3):
        for controls in ((-7, -7, -7), (0, 0, 0), (7, -2, 3)):
            old = middle_state(graph, graph.editor.image, getter, profile, controls, 8)
            queries, _ = run_middle(old)
            for language in (8,17):
                state = middle_state(graph, graph.image, getter, profile, controls, language)
                actual_queries, instructions = run_middle(state)
                assert actual_queries == queries
                assert old.read(VIEWER, 18) == state.read(VIEWER, 18)
                assert old.read(INITIAL_SP + 40, 32) == state.read(INITIAL_SP + 40, 32)
                for register in ('sp', 'd2', 'd3', 'a3'):
                    assert state.regs[register] == old.regs[register], register
                assert state.regs['sp'] == INITIAL_SP
                descriptor = state.read(VIEWER + 18, 74)
                label = descriptor[8:].decode('utf-16le').split('\0')[0]
                assert descriptor == old.read(VIEWER+18,74)
                assert state.read(VIEWER + 92, 28) == bytes(28)
                rows.append(dict(profile=profile, controls=controls, language=language,
                    label=label, queries=queries, instructions=instructions,
                    modeled_boundary='GUI property-getter envelope; actual602b9f84 executes'))
    return rows


def fallback_cases(graph, getter):
    rows = []
    for mode in (0, 1, 53, 57, 58, 59, 60, 0xffffffff):
        old = middle_state(graph, graph.editor.image, getter, 1, (0, 0, 0), 8, mode)
        state = middle_state(graph, graph.image, getter, 1, (0, 0, 0), 8, mode)
        before = state.read(INITIAL_SP, 80)
        old_queries, _ = run_middle(old, 0x60cfa28e)
        queries, instructions = run_middle(state, 0x60cfa28e)
        assert not old_queries and not queries
        assert state.regs == old.regs
        assert state.read(INITIAL_SP, 80) == before == old.read(INITIAL_SP, 80)
        assert state.read(VIEWER, 120) == old.read(VIEWER, 120) == bytes(120)
        rows.append(dict(public_mode=mode, native_join='0x60cfa28e',
                         instructions=instructions, models=[]))
    return rows


def data_alignment_cases(graph):
    rows=[]
    for name,width,count in (('tone_pair_lines',2,3),('tone_pair_ids',2,7),
                             ('tone_footer_english',4,3),('tone_footer_japanese',4,3)):
        for index in range(count):
            address=graph.symbols[name]+index*width
            rows.append(dict(symbol=name,index=index,address=hex(address),width=width,
                             aligned=address%width==0))
    return rows


def pair_cases(graph,getter):
    rows=[]
    for public in (0,1,53,54,55,56,57,58,59,0xffffffff):
        for controls in ((-7,0,7),(4,-2,-3)):
            pair=[]
            for image in (graph.editor.image,graph.image):
                profile=public-53 if 54<=public<=56 else 1
                state=middle_state(graph,image,getter,profile,controls,8,public)
                put32(state,INITIAL_SP+20,VIEWER+16);put32(state,INITIAL_SP+28,VIEWER+9)
                state.regs['pc']=0x60cf9d81
                logs=[];queries=[]
                while True:
                    result=state.run({0x60d10726,GETTER,0x60cf9f32},limit=10000)
                    assert result['status']=='breakpoint',(result,state.regs)
                    if state.regs['pc']==0x60cf9f32:break
                    if state.regs['pc']==0x60d10726:
                        logs.append(struct.unpack('<2I',state.read(state.regs['sp']+12,8)))
                        state.return_from_model(0)
                    else:
                        queries.append([state.regs['d0'],state.regs['a1']-INITIAL_SP])
                        result=state.run(set(),limit=1)
                        assert result['status']=='instruction_limit'
                pair.append((state,queries,logs))
            old,new=pair
            assert old[1:]==new[1:]
            relocated_returns={}
            if 54<=public<=56:
                for name,(state,_,_),image in zip(('stock','patched'),pair,(graph.editor.image,graph.image)):
                    address=state.regs['mdr']
                    call=image[address-7-BASE:address-BASE]
                    assert len(call)==7 and call[0]==0xdd and call[5:]==b'\xc0\x08'
                    assert address-7+struct.unpack_from('<i',call,1)[0]==0x60c89710
                    relocated_returns[name]=hex(address)
            else:
                assert old[0].regs['mdr']==new[0].regs['mdr']
            assert {k:v for k,v in old[0].regs.items() if k!='mdr'}=={k:v for k,v in new[0].regs.items() if k!='mdr'}
            assert old[0].read(VIEWER,120)==new[0].read(VIEWER,120)
            assert old[0].read(INITIAL_SP+16,56)==new[0].read(INITIAL_SP+16,56)
            rows.append(dict(public=public,controls=controls,queries=new[1],log_arguments=new[2],
                relocated_variant_call_returns=relocated_returns,
                models=['native logging return','GUI getter envelope with actual602b9f84']))
    return rows


def footer_state(graph,getter,*,profile=1,page=0,word=None,controls=(4,-2,-3),language=8,first=1,image=None):
    state=middle_state(graph,graph.image if image is None else image,getter,profile,controls,language)
    actuator(state,profile,page);mode(state,53+profile)
    word=FivePoints((64,320,544,704,960)).pack() if word is None else word
    set_words(state,(word,)*3)
    controller=0x1910a000
    state.ram('current_controller',controller,struct.pack('<II',ACTUATOR,VIEWER)+bytes(172),aliases=False)
    state.ram('current_controller_global',0x6161b810,struct.pack('<I',controller))
    put32(state,INITIAL_SP+4,VIEWER+8)
    state.regs=dict(PRESERVED,pc=0x60cf9be6,sp=INITIAL_SP,psw=0,a3=VIEWER,d3=first)
    return state


def footer_cases(graph,getter):
    rows=[]
    for profile in (1,2,3):
        for page in (0,1,2):
            for language in (8,17):
                state=footer_state(graph,getter,profile=profile,page=page,language=language)
                result=state.run({0x60cf9bec},limit=100000)
                assert result['status']=='breakpoint'
                assert tuple(state.regs[x] for x in ('sp','d2','d3','a3','a0','a1'))==(INITIAL_SP,1,1,VIEWER,VIEWER+8,1)
                label=state.read(VIEWER+26,66).decode('utf-16le').split('\0')[0]
                assert label==LABELS[language,page]
                assert state.read(VIEWER+11,1)==b'\x01'
                assert state.read(VIEWER+13,1)==bytes((2 if page==1 else 1,))
                assert state.read(VIEWER+92,28)==bytes(28)
                rows.append(dict(profile=profile,page=page,language=language,label=label,instructions=result['completed'],models=[]))
    return rows


def footer_fallback_cases(graph,getter):
    from penf_recovery_isolation_probe import without_ranges
    rows=[]
    for reason in ('mono','stale','page3','null_controller','non_tone','missing6','missing8','missing_both'):
        for first in (0,1):
            state=footer_state(graph,getter,first=first)
            if reason=='mono':mode(state,57)
            elif reason=='stale':mode(state,55)
            elif reason=='page3':state.write(ACTUATOR+194,b'\x03\0')
            elif reason=='null_controller':put32(state,0x6161b810,0)
            elif reason=='non_tone':put32(state,ACTUATOR,0x60de3ff8)
            else:
                mask={'missing6':0x84,'missing8':0x24,'missing_both':4}[reason]
                state.write(0x61c58404,bytes((mask,)))
                holes=[]
                if not mask&0x20:holes.append((0x610f1e54,0x610f2000))
                if not mask&0x80:holes.append((0x6115b014,0x6115b800))
                holes += [(lo+0x40000000,hi+0x40000000) for lo,hi in holes]
                state.regions=[r for r in state.regions if not any(lo<=r.address and r.address+len(r.data)<=hi for lo,hi in holes)]
                state.regions=without_ranges(state.regions,holes)
            before=state.read(VIEWER,120)
            result=state.run({0x60cf9bf0},limit=100000)
            assert result['status']=='breakpoint'
            assert tuple(state.regs[x] for x in ('sp','d0','d1','d2','d3','a2','a3','a0','a1'))==(INITIAL_SP,118,92,first,first,PRESERVED['a2'],VIEWER,VIEWER+8,first)
            assert state.read(VIEWER,120)==before
            rows.append(dict(reason=reason,first=first,instructions=result['completed'],models=[]))
    for word,controls,text,modified in ((FivePoints().pack(),(7,7,7),'M+0',0),(0,(-7,-7,-7),'M-7',1),(0,(8,0,0),'M+0',0)):
        state=footer_state(graph,getter,page=1,word=word,controls=controls,first=0)
        result=state.run({0x60cf9bec},limit=100000)
        assert result['status']=='breakpoint'
        label=state.read(VIEWER+26,66).decode('utf-16le').split('\0')[0]
        assert label=='BLACK/WHITE '+text+'@A028@'
        assert state.read(VIEWER+11,1)==bytes((modified,))
        assert state.regs['d3']==state.regs['d2']==state.regs['a1']==0
        rows.append(dict(word=hex(word),controls=controls,label=label,modified=modified,models=[]))
    return rows


def formatter_cases():
    rows = []
    for label in LABELS.values():
        descriptor = bytearray(74)
        struct.pack_into('<H', descriptor, 0, 5)
        encoded = (label + '\0').encode('utf-16le')
        descriptor[8:8 + len(encoded)] = encoded
        state = ProbeState(0x60cfd69b, 0xf0, 124, bytes(16), {})
        address, children, text = 0x19500000, 0x19501000, 0x19502000
        state.ram('label_descriptor', address, descriptor, aliases=False)
        state.ram('text_child_pair', children, struct.pack('<II', 0, text), aliases=False)
        reenter(state, 0x60cfd69b, 0xf0, 124, dict(PRESERVED, a0=address, a1=children))
        result = state.run({0x60c00c52}, limit=1000)
        assert result['status'] == 'breakpoint' and state.regs['pc'] == 0x60c00c52
        assert (state.regs['a0'], state.regs['a1']) == (text, address + 8)
        rows.append(dict(label=label, inline_bytes=len(encoded),
                         instructions=result['completed'], models=[],
                         stop='native text setter before allocation/rendering'))
    return rows


def layout_cases():
    from penf_color_text_probe import fixture as text_fixture, layout, STYLE
    rows = []
    for (language,page), text in LABELS.items():
        state = text_fixture()
        state.write(STYLE + 12, bytes((0, 1)))
        state.ram('icon_scratch_surface_pointer', 0x61a8e320, bytes(8), aliases=False)
        if language == 17:
            bank = BitmapBank()
            state.regions = [r for r in state.regions if r.name not in
                             ('stock_font_resource_42', 'stock_font_resource_8')]
            for index, base in ((51, 0xa2c63c00), (17, 0xa2ce3c00)):
                row = bank.rows[index]
                state.regions.append(Region('stock_japanese_resource_' + str(index), base,
                                            bank.data[row['start']:row['end']], 'r'))
            row = bank.rows[0]
            common = bank.data[row['start']:row['end']]
            offset = struct.unpack_from('<I', common, 12)[0] - 0xa1fa6c00
            japanese = common[offset:offset + 78]
            assert struct.unpack_from('<H', japanese)[0] == 11
            state.write(0x19502300, struct.pack('<9H', 11, 0, 32, 0, 0, 0, 0, 32, 0))
            state.write(0x19502400, japanese[72:77])
            state.write(0x19502600, b'\0\0' + japanese[2:66] + bytes(18))
            row = bank.rows[17]
            language_data = bank.data[row['start']:row['end']]
            state.write(1633782008, struct.pack('<I', struct.unpack_from('<I', language_data, 4)[0]))
        result = layout(state, text, rect=(20, 444, 619, 474))
        assert result['glyphs']
        right = max(glyph['native_pen_after'][0] for glyph in result['glyphs'])
        assert 20 < right <= 619, right
        rows.append(dict(language=language, label=text, right=right,
            models=['line-storage allocation/free', 'raster submission'], layout=result))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    graph = build_graph(args.out/'candidate')
    getter = getter_adapter(args.out/'getter')
    report = dict(middle=middle_cases(graph,getter), pair=pair_cases(graph,getter),
                  footer=footer_cases(graph,getter), footer_fallback=footer_fallback_cases(graph,getter),
                  fallback=fallback_cases(graph,getter),
                  formatter=formatter_cases(), layout=layout_cases())
    (args.out/'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({name:len(rows) for name, rows in report.items()}))


if __name__ == '__main__':
    main()
