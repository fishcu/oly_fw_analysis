#!/usr/bin/env python3
"""Compose an offline tone candidate over the exact pinned HSL main image."""
if not __debug__:
    raise RuntimeError('Tone audit probes require assertions; optimized Python execution is unsupported')

from dataclasses import dataclass
import json
from pathlib import Path
import struct
import subprocess

from penf_emulator import BASE, ROOT, firmware
from penf_landmarks import MAIN_SHA256
from penf_tone_endpoints import TOOLCHAIN
from penf_tone_integration_probe import SOURCES
from penf_tone_probe import sha

HSL = ROOT / 'patches/hsl/pen-f'
TOOLS = {name: TOOLCHAIN / path for name, path in (
    ('assembler','gas/as-new'),('linker','ld/ld-new'),('objcopy','binutils/objcopy'),
    ('objdump','binutils/objdump'),('nm','binutils/nm-new'))}


@dataclass(frozen=True)
class Candidate:
    image: bytes
    reference: bytes
    symbols: dict
    manifest: tuple


def run(*args):
    return subprocess.check_output([str(x) for x in args], stderr=subprocess.STDOUT, text=True)


def symbols(elf):
    return {name: int(address, 16) for address, kind, name in
            (line.split() for line in run(TOOLS['nm'], '-n', elf).splitlines())}


def assemble(folder, sources, layout):
    folder.mkdir(parents=True, exist_ok=False)
    objects = []
    for i, source in enumerate(sources):
        obj = folder / f'{i}.o'
        run(TOOLS['assembler'], '-o', obj, source)
        objects.append(obj)
    elf = folder / 'patch.elf'
    run(TOOLS['linker'], '--no-relax', '-T', layout, '-o', elf, *objects)
    (folder / 'patch.asm').write_text(run(TOOLS['objdump'], '-d', elf))
    return elf


def extract(elf, section):
    path = elf.parent / (section + '.bytes')
    run(TOOLS['objcopy'], '-O', 'binary', '--only-section=.' + section, elf, path)
    return path.read_bytes()


def reference_main(out, stock_main=None):
    spec = json.loads((HSL / 'patch.json').read_text())
    image = bytearray(firmware() if stock_main is None else stock_main)
    assert sha(image) == MAIN_SHA256, 'Wrong stock main hash'
    expected = {(r['name'], int(r['address'], 16)): r for r in spec['main_ranges']}
    written, names = set(), {}

    def install(name, address, data):
        row = expected[(name, address)]
        assert (name, address) not in written
        assert len(data) == row['bytes'] and sha(data) == row['after_sha256'], name
        at = address - BASE
        assert sha(image[at:at + len(data)]) == row['before_sha256'], name
        image[at:at + len(data)] = data
        written.add((name, address))

    for group in spec['groups']:
        elf = assemble(out / group['name'], [HSL / p for p in group['sources']], HSL / group['linker'])
        names.update(symbols(elf))
        for section, address in group['sections'].items():
            install(section, int(address, 16), extract(elf, section))
    for edit in spec['data_edits']:
        install(edit['name'], int(edit['address'], 16), bytes.fromhex(edit['after']))
    assert written == set(expected)
    assert sha(image) == spec['main_sha256']
    return bytes(image), names


def build_candidate(out, *, expanded=False, stock_main=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    reference, old = reference_main(out / 'hsl-reference', stock_main)
    late_start = 0x6115b014 if expanded else 0x6115b060
    late_end = 0x6115b800 if expanded else 0x6115b7c0
    layout = out / 'tone.ld'
    layout.write_text('''SECTIONS {
.tone_early 0x60427e78 : { *(.tone_early) }
.tone_job_gate 0x60427fa8 : { *(.tone_job_gate) }
.tone_source_gate 0x6069b580 : { *(.tone_source_gate) }
.tone_job_bridge 0x6069b7ac : { *(.tone_job_bridge) }
.text 0x6115b060 : { *(.text) }
.tone_rows : { *(.tone_rows) }
}
stock_spline_coefficients = 0x604bdea7;
stock_spline_evaluate = 0x604bdfe1;
stock_tone_builder = tone_stock_builder;
stock_tone_select = 0x604f7c18;
stock_tone_gate = 0x604bdd21;
stock_tone_apply = 0x604be08d;
stock_tone_resume = 0x604f85ef;
stock_active_get = 0x602f06e7;
stock_builder_after_entry = 0x604f7c7b;
tone_source_uncached = tone_source + 0x40000000;
tone_rows_uncached = tone_rows + 0x40000000;
tone_compact_rows = tone_rows_uncached + 160;
'''.replace('0x6115b060', hex(late_start)) + f'hl_owner_row = {old["hl_owner_row"]:#x};\nhl_return = {old["hl_no_owner"] + 2:#x};\n')
    elf = assemble(out / 'tone', [*SOURCES, ROOT / 'patches/tone/pen-f/src/transport.s'], layout)
    current = symbols(elf)
    image, manifest = bytearray(reference), []

    def install(name, address, data, expected=None):
        at = address - BASE
        before = reference[at:at + len(data)]
        assert len(before) == len(data)
        if expected is not None:
            assert before == expected, (name, before.hex())
        for row in manifest:
            assert address + len(data) <= row['address'] or row['address'] + row['bytes'] <= address, name
        image[at:at + len(data)] = data
        manifest.append(dict(name=name, address=address, bytes=len(data),
                             before_sha256=sha(before), after_sha256=sha(data)))

    allocations = {'tone_early': (0x60427e78, 0x60427ed0),
                   'tone_job_gate': (0x60427fa8, 0x60427fc0),
                   'tone_source_gate': (0x6069b580, 0x6069b590),
                   'tone_job_bridge': (0x6069b7ac, 0x6069b7b8),
                   'text': (late_start, late_end)}
    for name, (start, end) in allocations.items():
        data = extract(elf, name)
        assert start + len(data) <= end, (name, len(data), end - start)
        install(name, start, data)
    rows = extract(elf, 'tone_rows')
    assert len(rows) == 180 and current['tone_rows'] + len(rows) <= late_end
    install('tone_rows', current['tone_rows'], rows)

    def jump(name, at, target, short=False, expected=None):
        data = (b'\xcc' + struct.pack('<h', target - at) if short else
                b'\xdc' + struct.pack('<i', target - at))
        install(name, at, data, expected)

    assert reference[old['hl_no_owner'] + 2 - BASE:old['hl_no_owner'] + 5 - BASE] == bytes.fromhex('df0004')
    jump('publish_tail', old['hl_boot_publish'] - 3, current['tone_publish'], True, bytes.fromhex('df0004'))
    jump('source_tail', old['hl_source_done'], current['tone_source_gate'], True, bytes.fromhex('df0004'))
    jump('job_tail', old['hl_owner_row'] - 3, current['tone_job_bridge'], True, bytes.fromhex('df0004'))
    jump('native_tone_entry', 0x604f7c76, current['tone_build_gate'], expected=bytes.fromhex('f80404f1d3'))
    install('job_allocation', 0x604c1c0f, bytes.fromhex('2c643a'), bytes.fromhex('2c603a'))
    install('job_zero_count', 0x604c1d1f, bytes.fromhex('8528'), bytes.fromhex('8524'))

    raw_source = (HSL / 'src/raw_development/raw_development.s').read_text()
    needle = ' .endr\nhl_raw_done:'
    assert raw_source.count(needle) == 1
    raw_source = raw_source.replace(needle, ''' .endr
 movbu (0xa1c58404),d0
 btst 128,d0
 beq hl_raw_done
 call tone_clear_hl_row,[],4
hl_raw_done:''')
    raw = out / 'raw.s'
    raw.write_text(raw_source)
    raw_layout = out / 'raw.ld'
    raw_layout.write_text((HSL / 'src/raw_development/layout.ld').read_text() +
                          f'\ntone_clear_hl_row = {current["tone_clear_hl_row"]:#x};\n')
    raw_elf = assemble(out / 'raw', [raw], raw_layout)
    raw_code = extract(raw_elf, 'raw_acquire')
    assert len(raw_code) <= 112
    assert extract(raw_elf, 'raw_acquire_hook') == reference[0x60af2f56 - BASE:0x60af2f5c - BASE]
    install('composed_raw_acquire', 0x60fdc750, raw_code)
    all_symbols = dict(old, **current)
    (out / 'manifest.json').write_text(json.dumps(dict(
        status='offline main-image composition, not an installable container',
        reference_sha256=sha(reference), candidate_sha256=sha(image),
        spans=manifest, symbols={k: hex(v) for k, v in all_symbols.items()}), indent=2) + '\n')
    return Candidate(bytes(image), reference, all_symbols, tuple(manifest))
