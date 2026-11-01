"""Place the native tone editor over the pinned transport candidate."""
from dataclasses import dataclass
import json
import struct
from penf_emulator import BASE, ROOT, firmware
from penf_tone_candidate import HSL, assemble, extract, symbols
from penf_tone_probe import sha


@dataclass(frozen=True)
class EditorCandidate:
    image: bytes
    symbols: dict
    chunks: dict


def build_editor(folder, candidate, *, graph=False):
    folder.mkdir(parents=True, exist_ok=False)
    spec = json.loads((HSL / 'patch.json').read_text())
    group = next(g for g in spec['groups'] if g['name'] == 'editor_storage')
    source = (HSL / 'src/editor_storage/editor.s').read_text()
    start, end = source.index('.section .hsl_ui'), source.index('.section .hsl_wheel1_hook')
    ui = source[start:end].replace('sub 1,', 'add -1,').replace('sub 931,', 'add -931,')
    needle = ' mov d2,d0\n add 931,d0\nhsl_commit:'
    assert ui.count(needle) == 1
    ui = ui.replace(needle, 'hsl_commit:')
    source = source[:start] + ui + source[end:]
    start, end = source.index('.section .hsl_wheel,"'), source.index('.section .hsl_dispatch_hook')
    wheel = source[start:end].replace('sub 1,', 'add -1,').replace('sub 931,', 'add -931,')
    source = source[:start] + wheel + source[end:]
    compact = folder / 'hsl_compact.s'
    compact.write_text(source)
    sources = [compact if path == 'src/editor_storage/editor.s' else HSL / path for path in group['sources']]
    compact_elf = assemble(folder / 'hsl_compact', sources, HSL / group['linker'])
    names = dict(candidate.symbols, **symbols(compact_elf))
    image = bytearray(candidate.image)
    changed = []
    for section, address in group['sections'].items():
        address = int(address, 16)
        data = extract(compact_elf, section)
        before = candidate.reference[address-BASE:address-BASE+len(data)]
        if data != before:
            changed.append(section)
            image[address-BASE:address-BASE+len(data)] = data
    assert set(changed) == {'hsl_ui', 'hsl_get_pointer', 'hsl_default_pointer',
                            'hsl_wheel'}, changed
    assert len(extract(compact_elf, 'hsl_ui')) == 221
    assert extract(compact_elf, 'hsl_wheel')[-32:] == b'\xcb' * 32
    tone_source = ROOT / 'patches/tone/pen-f/src/editor.s'
    if graph:
        generated = folder / 'editor.s'
        source = tone_source.read_text().replace('.global tone_selected_id', '.section .tone_selected,"ax"\n.global tone_selected_id')
        generated.write_text(source)
        tone_source = generated
    layout = folder / 'editor.ld'
    external = dict(stock_active_set=0x602f0710, stock_active_get=0x602f06e7,
        hl_publish=names['hl_publish'], stock_manager=0x6075fbed, stock_manager_finish=0x6075fc45,
        stock_color1_refresh=0x602c1067, stock_color2_refresh=0x602c1080,
        stock_color3_refresh=0x602c1099, stock_bind_resume=0x60c878f2,
        stock_axis_eligibility=0x60c879c8, stock_parameter_get=0x60bba9e5,
        stock_parameter_set=0x60bba9fd, stock_event_finish=0x60c878e3,
        stock_info_timer=0x60c87878, stock_info_generic=0x60c877f1,
        stock_raw_get=0x602b9f84, stock_convert=0x604bddcc, stock_tone_gate=0x604bdd21,
        stock_tone_apply=0x604be08d, stock_gui_set=0x607363b3,
        stock_gui_service=0x607355e9, stock_timer=0x60d13bbb,
        stock_event_changed=0x60c878dd, stock_reset_resume=0x60c875ec,
        tone_signal_bounds=names['tone_signal_bounds'])
    external.update({f'stock_input_{name}_resume': at for name, at in
                     (('up',0x60c8720b), ('down',0x60c8726d), ('left',0x60c872d1),
                      ('right',0x60c87335), ('front',0x60c873b2), ('rear',0x60c8742e))})
    slots = {'tone_editor': (names['tone_rows'] + 180, 0x6115b7c0),
             'tone_reference': (0x610f1ea0, 0x610f1fc0),
             'tone_resident': (0x60c87670, 0x60c877f1),
             'tone_manager_gate': (0x60a4ff8d, 0x60a4ffa6),
             'tone_manager_unavailable': (0x6081b8af, 0x6081b8cf)}
    if graph:
        slots['tone_editor'] = (names['tone_rows']+180, 0x6115b800)
        slots['tone_reference'] = (0x610f1e54, 0x610f1f42)
        slots['tone_selected'] = (0x610f1fd8, 0x610f1ff6)
    layout.write_text('SECTIONS {\n' + ''.join(f'.{k} {a:#x} : {{ *(.{k}) }}\n' for k,(a,b) in slots.items()) +
                      '}\n' + ''.join(f'{key} = {value:#x};\n' for key,value in external.items()))
    elf = assemble(folder / 'assembly', [tone_source], layout)
    names.update(symbols(elf))
    chunks = {}
    for section, (address, end) in slots.items():
        data = extract(elf, section)
        chunks[section] = data
        assert address + len(data) <= end, (section, len(data), end-address)
        if section in ('tone_editor','tone_reference','tone_selected'):
            assert image[address-BASE:address-BASE+len(data)] == b'\xff' * len(data)
        image[address-BASE:address-BASE+len(data)] = data
    expected = {0x60c878ec: 'f1d39fbcf16f', 0x60c875e4: '5c040082fa20b400',
        0x60c87206: '9500f0f273', 0x60c87268: '9500f0f273',
        0x60c872cc: '9500f0f273', 0x60c87330: '9500f0f273',
        0x60c873ad: 'f0f2735c04', 0x60c87429: 'f0f2735c04'}
    for address, value in expected.items():
        assert image[address-BASE:address-BASE+len(bytes.fromhex(value))] == bytes.fromhex(value)
    gate = names['hsl_stock_set']
    assert image[gate-BASE:gate-BASE+5] == b'\xdc'+struct.pack('<i',0x6075fbed-gate)
    hooks = [(names['hsl_stock_set'], 5, names['tone_manager_gate']),
        (0x60c878ec, 6, names['tone_bind_gate']), (0x60c875e4, 8, names['tone_reset_gate'])]
    for address, size, target in hooks:
        image[address-BASE:address-BASE+size] = b'\xdc' + struct.pack('<i',target-address) + b'\xcb'*(size-5)
    for address, target in [(at, names['tone_input_arrow']) for at in
                            (0x60c87206,0x60c87268,0x60c872cc,0x60c87330)] + [
                            (at,names['tone_input_dial']) for at in (0x60c873ad,0x60c87429)]:
        image[address-BASE:address-BASE+5] = b'\xcd' + struct.pack('<h',target-address) + b'\x00\x04'
    (folder/'placement.json').write_text(json.dumps(dict(
        chunks={k: dict(address=hex(slots[k][0]),bytes=len(v),capacity=slots[k][1]-slots[k][0]) for k,v in chunks.items()},
        candidate_sha256=sha(image), source_sha256=sha((ROOT/'patches/tone/pen-f/src/editor.s').read_bytes()),
        compact_hsl_sections=changed, symbols={k:hex(v) for k,v in names.items()}),indent=2)+'\n')
    return EditorCandidate(bytes(image), names, chunks)
