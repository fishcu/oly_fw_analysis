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


def build_graph(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    base = build_candidate(folder/'transport', expanded=True)
    editor = build_editor(folder/'editor', base, graph=True)
    names = dict(editor.symbols)
    names.update(native_tone_paint=0x60bbe8b6, native_tone_update=0x60c58464,
                 native_filter_resume=0x60bf7c47, native_filter_skip=0x60bf80cf)
    slots = {
        'tone_display_filter': (0x60a4fe6c,0x60a4feb0),
        'tone_display_active': (0x60a4ffb4,0x60a4ffe8),
        'tone_display_digits': (0x60a4ffe8,0x60a50000),
        'tone_display_entry_gates': (0x60fdc29c,0x60fdc2ce),
        'tone_display_brush': (0x60fdc2ce,0x60fdc2e0),
        'tone_display_filter_gate': (0x60fdc7b4,0x60fdc7d4),
        'tone_display_update': (0x60fdc7d4,0x60fdc800),
        'tone_display_text': (0x610f1f42,0x610f1fca),
        'tone_display_rectangle': (0x610f1fca,0x610f1fd8),
        'tone_display_paint': (names['tone_manager']+len(editor.chunks['tone_editor']),0x6115b800),
    }
    layout=folder/'display.ld'
    layout.write_text('SECTIONS {\n'+''.join(f'.{name} {start:#x} : {{ *(.{name}) }}\n' for name,(start,end) in slots.items())+'}\n'+
                      ''.join(f'{key} = {value:#x};\n' for key,value in names.items() if key.isidentifier()))
    elf=assemble(folder/'assembly',[ROOT/'patches/tone/pen-f/src/display.s'],layout)
    names.update(symbols(elf))
    image=bytearray(editor.image)
    chunks={}
    for section,(start,end) in slots.items():
        data=extract(elf,section)
        assert start+len(data)<=end,(section,len(data),end-start)
        assert image[start-BASE:start-BASE+len(data)]==b'\xff'*len(data),section
        image[start-BASE:start-BASE+len(data)]=data
        chunks[section]=data
    for address,expected,target in ((0x60ec4d4c,0x60bbe8b6,'tone_paint_gate'),
                                    (0x60ec4e3c,0x60c58464,'tone_update_gate')):
        assert image[address-BASE:address-BASE+4]==struct.pack('<I',expected)
        image[address-BASE:address-BASE+4]=struct.pack('<I',names[target])
    address=0x60bf7c40
    assert image[address-BASE:address-BASE+7]==bytes.fromhex('5cccf004f82550')
    image[address-BASE:address-BASE+7]=b'\xdc'+struct.pack('<i',names['tone_filter_gate']-address)+b'\xcb\xcb'
    (folder/'main.bin').write_bytes(image)
    (folder/'placement.json').write_text(json.dumps(dict(candidate_sha256=sha(image),
        source_sha256=sha((ROOT/'patches/tone/pen-f/src/display.s').read_bytes()),
        chunks={k:dict(address=hex(slots[k][0]),bytes=len(v),capacity=slots[k][1]-slots[k][0]) for k,v in chunks.items()},
        symbols={k:hex(v) for k,v in names.items()}),indent=2)+'\n')
    return GraphCandidate(base,editor,bytes(image),names,chunks)
