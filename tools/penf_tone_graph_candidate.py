"""Link the native five-point graph into qualified section4/5/6/8 tails."""
from dataclasses import dataclass
import json
from pathlib import Path
import struct

from penf_emulator import BASE, ROOT
from penf_tone_candidate import assemble, build_candidate, extract, symbols
from penf_tone_editor_candidate import build_editor
from penf_tone_probe import sha


@dataclass(frozen=True)
class GraphCandidate:
    base: object
    editor: object
    image: bytes
    symbols: dict
    chunks: dict


def build_graph(folder, *, stock_main=None):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    base = build_candidate(folder/'transport', expanded=True, stock_main=stock_main)
    editor = build_editor(folder/'editor', base)
    names = dict(editor.symbols)
    names.update(native_tone_paint=0x60bbe8b6, native_tone_update=0x60c58464,
                 native_filter_resume=0x60bf7c47, native_filter_skip=0x60bf80cf,
                 stock_gui_service=0x607355e9, stock_variant=0x60c89710,
                 stock_string=0x60bcb228, stock_viewer_tail=0x60cfa572,
                 stock_middle_mono=0x60cfa28a,stock_viewer_pair_hint=0x60cfa4dd,
                 stock_viewer_publish_resume=0x60cf9bec,stock_pair_mono=0x60cf9f2e,
                 stock_viewer_log=0x60d10726)
    slots = {
        'tone_viewer_pair': (0x60cf9d81,0x60cf9e34),
        'tone_pair_lines': (0x60cf9e34,0x60cf9e3a),
        'tone_viewer_middle': (0x60cfa110,0x60cfa1ad),
        'tone_viewer_gate': (0x60cfa1ad,0x60cfa1dc),
        'tone_display_filter': (0x60a4fe6c,0x60a4feb0),
        'tone_display_active': (0x60a4ffb4,0x60a4ffe8),
        'tone_display_digits': (0x60a4ffe8,0x60a50000),
        'tone_display_entry_gates': (0x60fdc29c,0x60fdc2ce),
        'tone_display_brush': (0x60fdc2ce,0x60fdc2e0),
        'tone_display_filter_gate': (0x60fdc7b4,0x60fdc7d4),
        'tone_display_update': (0x60fdc7d4,0x60fdc800),
        'tone_display_rectangle': (0x610f1fca,0x610f1fd8),
        'tone_display_paint': (names['tone_manager']+len(editor.chunks['tone_editor']),0x6115c800),
    }
    layout=folder/'display.ld'
    layout.write_text('SECTIONS {\n'+''.join(f'.{name} {start:#x} : {{ *(.{name})' + (' *(.tone_footer) *(.tone_footer_tail) *(.tone_footer_tables) *(.tone_footer_strings) *(.tone_footer_small_strings)' if name == 'tone_display_paint' else '') + ' }\n' for name,(start,end) in slots.items())+'}\n'+
                      ''.join(f'{key} = {value:#x};\n' for key,value in names.items() if key.isidentifier()))
    elf=assemble(folder/'assembly',[ROOT/'patches/tone/pen-f/src'/name for name in ('display.s','viewer.s')],layout)
    names.update(symbols(elf))
    for name,width in (('tone_pair_lines',2),('tone_pair_ids',2),
                       ('tone_footer_english',4),('tone_footer_japanese',4),
                       ('footer_middle_en',2),('footer_endpoints_en',2),('footer_pair_en',2),
                       ('footer_middle_jp',2),('footer_endpoints_jp',2),('footer_pair_jp',2),
                       ('tone_footer_info',2)):
        assert names[name]%width==0,(name,hex(names[name]),width)
    for name,section in (('tone_viewer_pair','tone_viewer_pair'),
                         ('tone_viewer_middle','tone_viewer_middle'),
                         ('tone_viewer_publish','tone_viewer_gate')):
        assert names[name]==slots[section][0],(name,hex(names[name]))
    image=bytearray(editor.image)
    replaced = ((0x60cf9d81,0x60cf9f2e,'7cfbc8bd1d503dfb9b13806bfb32ccba1cf2e8a46b502b3e1f6175c94b83b9f5'),
                (0x60cfa110,0x60cfa28a,'a8ce9e71dbca9ec709d7db300fd0aefbfffe45ccbeb330cf44438a941d2e04a6'))
    for start,end,digest in replaced:
        assert sha(image[start-BASE:end-BASE]) == digest
        image[start-BASE:end-BASE] = b'\xcb' * (end-start)
    chunks={}
    for section,(start,end) in slots.items():
        data=extract(elf,section)
        assert start+len(data)<=end,(section,len(data),end-start)
        padding = b'\xcb' if any(lo <= start and end <= hi for lo,hi,_ in replaced) else b'\xff'
        assert image[start-BASE:start-BASE+len(data)] == padding*len(data),section
        image[start-BASE:start-BASE+len(data)] = data
        chunks[section]=data
    for address,expected,target in ((0x60ec4d4c,0x60bbe8b6,'tone_paint_gate'),
                                    (0x60ec4e3c,0x60c58464,'tone_update_gate')):
        assert image[address-BASE:address-BASE+4]==struct.pack('<I',expected)
        image[address-BASE:address-BASE+4]=struct.pack('<I',names[target])
    address=0x60cf9be6
    assert image[address-BASE:address-BASE+6] == bytes.fromhex('8e1a5c04f1e9')
    image[address-BASE:address-BASE+6] = b'\xdc'+struct.pack('<i',names['tone_viewer_publish']-address)+b'\xcb'
    address=0x60bf7c40
    assert image[address-BASE:address-BASE+7]==bytes.fromhex('5cccf004f82550')
    image[address-BASE:address-BASE+7]=b'\xdc'+struct.pack('<i',names['tone_filter_gate']-address)+b'\xcb\xcb'
    (folder/'main.bin').write_bytes(image)
    (folder/'placement.json').write_text(json.dumps(dict(candidate_sha256=sha(image),
        source_sha256=sha((ROOT/'patches/tone/pen-f/src/display.s').read_bytes()),
        viewer_source_sha256=sha((ROOT/'patches/tone/pen-f/src/viewer.s').read_bytes()),
        chunks={k:dict(address=hex(slots[k][0]),bytes=len(v),capacity=slots[k][1]-slots[k][0]) for k,v in chunks.items()},
        symbols={k:hex(v) for k,v in names.items()}),indent=2)+'\n')
    return GraphCandidate(base,editor,bytes(image),names,chunks)
