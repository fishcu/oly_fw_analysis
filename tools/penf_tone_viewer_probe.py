#!/usr/bin/env python3
"""Bounded COLOR middle-page label and unchanged native query contracts."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import struct

from penf_emulator import Region
from penf_hsl_context_probe import reenter
from penf_osd_bitmaps import BitmapBank
from penf_probe import ProbeState
from penf_tone_candidate import assemble, extract
from penf_tone_editor_probe import fixture, current, SERVICE
from penf_tone_graph_candidate import build_graph
from penf_tone_probe import PRESERVED, INITIAL_SP
from penf_tone_transport_probe import put32

VIEWER, GETTER_TABLE, GETTER = 0x19109000, 0x19108000, 0x190a0000
LABELS = {8: 'BLACK / WHITE @A028@', 17: '黒点・白点@A028@'}


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
            for language, expected in LABELS.items():
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
                assert descriptor[:2] == b'\x05\0' and label == expected
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
    for language, text in LABELS.items():
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
    report = dict(middle=middle_cases(graph, getter), fallback=fallback_cases(graph, getter),
                  formatter=formatter_cases(), layout=layout_cases())
    (args.out/'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({name:len(rows) for name, rows in report.items()}))


if __name__ == '__main__':
    main()
