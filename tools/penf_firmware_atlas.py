#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Read-only structural atlas of pinned PEN-F 3101; no patch or device access.

Byte statistics are descriptive, not a code/data classifier or free-space proof.
Resource directories and startup descriptors reuse the project's earlier audits.
"""
import argparse
from collections import Counter
import io
import json
import math
from pathlib import Path
import re
import struct

from PIL import Image
from oly_container import parse, sha256, sum32
from penf_landmarks import BASE, MAIN_SHA256, COLOR_TABLE_ADDRESS, COLOR_TABLE_SIZE
from penf_code_space_reference_audit import resource_rows, jpeg_layout

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'firmware_files/OLY_E_122_3101_0000_0000.BIN'
SOURCE_SHA = '77398610b379f80238117f31a6d5bbf65d608b49ec563666c64d84367e969f2c'
WINDOW = 65536
LANDMARKS = [
    ('Main entry', 0x60021020, 0x60021021, 'entry point; earlier BOOT unavailable'),
    ('140 static task descriptors', 0x600396c4, 0x600396c4+140*28, 'structured data'),
    ('Settings schema: 968 descriptors', 0x603dffcc, 0x603dffcc+968*20, 'structured data'),
    ('Processing request packer', 0x604c3051, 0x604c3052, 'known function entry'),
    ('HSL selector', 0x604f747f, 0x604f7480, 'known function entry'),
    ('Shared COLOR LUT and parameters', COLOR_TABLE_ADDRESS, COLOR_TABLE_ADDRESS+COLOR_TABLE_SIZE, '3028-byte data table'),
    ('Red lightness candidate field', 0x60622e48, 0x60622e4a, 'signed 16-bit coefficient'),
    ('CMIO block matching ORF', 0x6067e000, 0x6069b240, '119360 bytes; serialized data'),
    ('Section 3 initializers', 0x6069b240, 0x6069b26c, '11 function pointers'),
    ('Section 3 proposed code interior', 0x6069b2b0, 0x6069b7c0, '1296 FF bytes; lifetime unproven'),
    ('SD updater client / task 95', 0x60b1cbb5, 0x60b1cbb6, 'known function entry; activation unresolved'),
    ('Shared firmware updater', 0x60b1d527, 0x60b1d528, 'known function entry'),
    ('Text renderer', 0x60bc1fbf, 0x60bc1fc0, 'known entry; COLOR paint context not joined'),
    ('COLOR/CRT viewer constructor', 0x60c84664, 0x60c84665, 'shared viewer type 88'),
]


def metrics(data):
    counts = Counter(data)
    n = len(data)
    ascii_bytes = sum(m.end()-m.start() for m in re.finditer(rb'[\x20-\x7e]{6,}', data))
    return dict(entropy=round(-sum((v/n)*math.log2(v/n) for v in counts.values()), 4),
                zero_fraction=round(counts[0]/n, 4), ff_fraction=round(counts[255]/n, 4),
                ascii_run_fraction=round(ascii_bytes/n, 4))


def indexed_assets(block, older):
    """Enumerate bounded address/length records; identify only verified JPEGs."""
    data = block.payload
    base = block.address+32
    result = []

    def walk(table, end, parent=()):
        for item in resource_rows(data, table, base, end):
            a, z = item['start'], item['end']
            path = (*parent, item['index'])
            row = dict(path=list(path), offset=a, size=z-a, logical_address=base+a,
                       kind='opaque indexed asset', sha256=sha256(data[a:z]),
                       identical_3100=data[a:z] == older[a:z])
            result.append(row)
            if data[a:a+2] == b'OE':
                # These nested resources are already decoded; not update components.
                assert data[a:a+28] == data[z-32:z-4]
                assert struct.unpack_from('<I', data, a+12)[0] == z-a-64
                row['kind'] = 'nested resource container'
                row['header_trailer_identical'] = data[a:a+32] == data[z-32:z]
                row['additive_sum_zero'] = sum32(data[a:z]) == 0
                walk(a+32, z-32, path)
                continue
            for prefix in (0, 64):
                if data[a+prefix:a+prefix+3] != b'\xff\xd8\xff':
                    continue
                raw = data[a+prefix:z]
                try:
                    layout = jpeg_layout(raw)
                    with Image.open(io.BytesIO(raw)) as im:
                        dimensions = list(im.size)
                        assert im.format == 'JPEG'
                        im.verify()
                    row.update(kind='verified JPEG', jpeg_prefix=prefix,
                               jpeg_bytes=layout['end'], dimensions=dimensions)
                except (AssertionError, ValueError, OSError, IndexError) as exc:
                    row['jpeg_validation_error'] = str(exc)
                break
            if block.kind == 0x106 and path == (6, 0):
                assert struct.unpack_from('<I', data, a)[0] == 1116
                row['kind'] = 'settings backup schema (1116 names; prior native audit)'
            if block.kind == 0x101 and path == (8,):
                row['kind'] = 'English text resource (2892 strings; prior native audit)'
    walk(0, len(data))
    return result


HTML = r'''<!doctype html><meta charset="utf-8"><title>PEN-F firmware atlas</title>
<style>
body{font:15px system-ui;max-width:1280px;margin:35px auto;padding:0 20px;background:#f7f8fb;color:#182334}
h1,h2{font-weight:650}p{max-width:1000px;line-height:1.55}button,select,input{font:inherit;padding:7px;margin:4px}
canvas{width:100%;height:150px;background:white;border:1px solid #bcc8d8;cursor:crosshair}
table{border-collapse:collapse;width:100%;background:white;margin:15px 0;font-size:13px}td,th{padding:8px;text-align:left;border-bottom:1px solid #dde3ec}
code,pre{font:12px monospace}pre{white-space:pre-wrap;background:#eaf0f7;padding:12px;min-height:70px}
.note{border-left:4px solid #cc9126;padding-left:12px}.scroll{max-height:470px;overflow:auto}th{position:sticky;top:0;background:#e6edf5}
</style>
<h1>PEN-F 3.1 / build 3101: structural atlas</h1>
<p>Read-only survey of the supplied stock update. The map combines verified component checksums,
loaded-section descriptors and resource directories with descriptive byte statistics.
It does not execute boot, establish recovery, or certify space for a patch.</p>
<p class="note">A loaded section can contain both instructions and data. High entropy does not prove compression or encryption.
FF/zero bytes do not prove unused memory. Main addresses below use the existing analysis map;
only verified section ranges assert the displayed load destination. Resource addresses are logical storage addresses.</p>
<div id="summary"></div><h2>Component byte map</h2>
<select id="component"></select><select id="metric"><option value="entropy">Entropy (0–8 bits/byte)</option><option value="ff_fraction">FF fraction</option><option value="zero_fraction">Zero fraction</option><option value="ascii_run_fraction">ASCII-run fraction</option><option value="difference_fraction">Difference from 3100</option></select>
<p>Each bar represents 64 KiB, except the last. Click or hover to inspect offsets, descriptors and nearby known landmarks.</p>
<canvas id="map" width="1200" height="150"></canvas><pre id="detail"></pre>
<h2>Known loaded sections</h2><p>These are descriptor boundaries, not inferred code/data boundaries. Startup code and other initial data also exist outside these staged sections.</p><div id="sections"></div>
<h2>Known main landmarks</h2><div id="landmarks"></div>
<h2>Indexed resources</h2><p>Containers and their children are listed separately; do not add their sizes together. Opaque means the asset was indexed but its format was not established here.</p>
<input id="filter" placeholder="Filter: JPEG, opaque, schema, 0106…" size="45"><div class="scroll" id="assets"></div>
<h2>Largest constant-byte runs</h2><p>Observed runs of at least 4 KiB. Main-map overlap with reserved RAM is shown where already known; lack of an overlap is not an allocation guarantee.</p><div id="runs"></div>
<h2>Evidence and limitations</h2><pre id="evidence"></pre>
<script>
const D=__DATA__;
const $=x=>document.getElementById(x), hx=n=>'0x'+n.toString(16).padStart(8,'0'), mb=n=>(n/1048576).toFixed(2)+' MiB';
function table(id,headers,rows){let t=document.createElement('table'),h=t.insertRow();for(let s of headers){let c=document.createElement('th');c.textContent=s;h.append(c)}for(let r of rows){let tr=t.insertRow();for(let v of r)tr.insertCell().textContent=v}$(id).replaceChildren(t)}
table('summary',['Component','Meaning','Payload size','Indexed leaves','Verified JPEGs','3100 comparison'],D.components.map(c=>[c.kind,c.label,mb(c.size),c.assets.filter(a=>a.kind!=='nested resource container').length,c.assets.filter(a=>a.kind==='verified JPEG').length,c.older_comparison]));
for(let c of D.components){let o=document.createElement('option');o.value=c.kind;o.textContent=c.kind+' — '+c.label;$('component').append(o)}
table('sections',['ID','Runtime start','End (exclusive)','Logical flash start','Size','Descriptor rechecked'],D.sections.map(s=>[s.id,s.destination,s.end_exclusive,s.flash_source,mb(s.length),'yes']));
table('landmarks',['Known item','Main analysis start','End (exclusive)','Evidence class'],D.landmarks.map(l=>[l.name,hx(l.start),hx(l.end),l.kind]));
function paint(){let c=D.components.find(c=>c.kind===$('component').value),m=$('metric').value,ctx=$('map').getContext('2d');ctx.clearRect(0,0,1200,150);c.windows.forEach((w,i)=>{let v=w[m]||0;if(m==='entropy')v/=8;ctx.fillStyle=`hsl(${215-190*v} 65% 48%)`;ctx.fillRect(i*1200/c.windows.length,150-145*v,Math.max(1,1200/c.windows.length),145*v)});inspect(0)}
function inspect(i){let c=D.components.find(c=>c.kind===$('component').value),w=c.windows[Math.min(c.windows.length-1,i)];let notes=c.kind==='0100'?D.landmarks.filter(l=>l.start< D.main_base+w.offset+w.size&&l.end>D.main_base+w.offset).map(l=>l.name):c.assets.filter(a=>a.offset<w.offset+w.size&&a.offset+a.size>w.offset).map(a=>a.path.join('/')+': '+a.kind).slice(0,12);$('detail').textContent=JSON.stringify({component:c.kind,decoded_offset:hx(w.offset),logical_storage:hx(c.logical_base+w.offset),main_analysis_address:c.kind==='0100'?hx(D.main_base+w.offset):undefined,...w,overlapping_items:notes},null,2)}
$('map').onmousemove=e=>{let c=D.components.find(c=>c.kind===$('component').value),r=$('map').getBoundingClientRect();inspect(Math.max(0,Math.floor((e.clientX-r.left)/r.width*c.windows.length)))};
$('component').onchange=paint;$('metric').onchange=paint;paint();
function assets(){let q=$('filter').value.toLowerCase();table('assets',['Component / index','Decoded offset','Logical address','Size','Classification','Dimensions','Same as 3100'],D.components.flatMap(c=>c.assets.map(a=>[c.kind+' / '+a.path.join('/'),hx(a.offset),hx(a.logical_address),mb(a.size),a.kind,a.dimensions?.join(' × ')||'',a.identical_3100?'yes':'no'])).filter(r=>r.join(' ').toLowerCase().includes(q)))}$('filter').oninput=assets;assets();
table('runs',['Component','Byte','Decoded offset','Size','Known reserved overlap (main analysis map)'],D.components.flatMap(c=>c.fill_runs.map(r=>[c.kind,r.byte,hx(r.offset),r.size,r.reserved_overlaps.join('; ')])).sort((a,b)=>b[3]-a[3]).slice(0,25).map(r=>[...r.slice(0,3),mb(r[3]),r[4]]));
$('evidence').textContent=JSON.stringify({source:D.source,sha256:D.source_sha256,main_analysis_base:hx(D.main_base),evidence_sources:D.evidence_sources,limits:D.limits},null,2);
</script>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('output directory must not already exist')
    raw = SOURCE.read_bytes()
    assert sha256(raw) == SOURCE_SHA
    blocks = parse(raw)
    assert sha256(blocks[0].payload) == MAIN_SHA256
    older_file = ROOT/'firmware_archive/stock/OLY_E_122_3100_0000_0000.BIN'
    older_raw = older_file.read_bytes()
    older = {b.kind: b for b in parse(older_raw)}
    assert sha256(older[0x100].payload) == '3d5963c6d9385aafc99ff51892ec706bef1c4783a84f586179271a64b8401bfd'
    section_file = ROOT/'analysis/preset_startup_final/audit.json'
    reserved_file = ROOT/'analysis/code_space/verified/audit.json'
    sections = json.loads(section_file.read_text())['startup_sections']
    reserved = json.loads(reserved_file.read_text())['known_reserved_ranges']
    for s in sections:
        off = int(s['descriptor'], 16)-BASE
        values = struct.unpack_from('<3I', blocks[0].payload, off)
        assert values == (int(s['destination'], 16), int(s['flash_source'], 16), int(s['destination'], 16)), values
        assert int(s['destination'], 16)-BASE == int(s['flash_source'], 16)-(blocks[0].address+32)
    labels = {0x100:'Main program and data', 0x101:'OSD/language resources',
              0x106:'Common resources, nested banks and settings schema', 0x102:'Picture resources'}
    components = []
    for block in blocks:
        data = block.payload
        windows = []
        old = older[block.kind].payload
        for off in range(0, len(data), WINDOW):
            chunk = data[off:off+WINDOW]
            row = dict(offset=off, size=len(chunk), **metrics(chunk))
            if len(old) == len(data):
                row['different_bytes'] = sum(a != b for a,b in zip(chunk, old[off:off+len(chunk)]))
                row['difference_fraction'] = row['different_bytes']/len(chunk)
            windows.append(row)
        runs = []
        for m in re.finditer(rb'\xff{4096,}|\x00{4096,}', data):
            overlaps = [r['name'] for r in reserved if
                        BASE+m.start()<int(r['end_exclusive'],16) and int(r['start'],16)<BASE+m.end()]
            runs.append(dict(offset=m.start(), size=m.end()-m.start(), byte=f'{data[m.start()]:02x}',
                             reserved_overlaps=overlaps if block.kind == 0x100 else []))
        assets = indexed_assets(block, old) if block.kind != 0x100 else []
        changed = sum(w.get('different_bytes', 0) for w in windows)
        comparison = 'identical decoded payload' if old == data else (
            f'{changed} changed bytes, same payload size' if len(old) == len(data)
            else 'different decoded payload')
        if block.kind == 0x106:
            diffs = {i for i,(a,b) in enumerate(zip(data,old)) if a != b}
            metadata = set()
            for a in assets:
                if a['kind'] == 'nested resource container':
                    metadata.update(range(a['offset']+24, a['offset']+28))
                    metadata.update(range(a['offset']+a['size']-8, a['offset']+a['size']-4))
            if diffs and diffs <= metadata:
                comparison += '; confined to nested header/trailer metadata'
        components.append(dict(kind=f'{block.kind:04x}', label=labels[block.kind], size=len(data),
            logical_base=block.address+32, decoded_sha256=sha256(data), windows=windows,
            assets=assets, fill_runs=runs, older_comparison=comparison))
        print(f'{block.kind:04x}: {len(data)} bytes; {len(assets)} directory records; {comparison}', flush=True)
    evidence = [Path(__file__).resolve(), ROOT/'tools/oly_container.py', ROOT/'tools/penf_landmarks.py',
                ROOT/'tools/penf_code_space_reference_audit.py', section_file, reserved_file]
    report = dict(source=str(SOURCE.relative_to(ROOT)), source_sha256=SOURCE_SHA,
        older_source=str(older_file.relative_to(ROOT)), older_source_sha256=sha256(older_raw),
        main_base=BASE, window_size=WINDOW, sections=sections, components=components,
        landmarks=[dict(name=n,start=a,end=z,kind=k) for n,a,z,k in LANDMARKS],
        evidence_sources={str(p.relative_to(ROOT)):sha256(p.read_bytes()) for p in evidence},
        limits=['No instruction discovery, whole-program xrefs, dynamic execution or camera access.',
                'Byte statistics do not distinguish instructions from tables, compression or encryption.',
                'Constant-byte regions are not certified free code or RAM space.',
                'Resource directories omit empty records. Nested containers include their child bytes.',
                'BOOT, sound and mode-17 persistent resources are outside this package.',
                'Main address map outside verified section descriptors is not a residency guarantee.',
                'Known landmarks come from earlier native/static audits; this survey does not re-execute them.'])
    args.out.mkdir(parents=True)
    payload = json.dumps(report, indent=2)
    (args.out/'atlas.json').write_text(payload+'\n')
    (args.out/'index.html').write_text(HTML.replace('__DATA__', json.dumps(report).replace('<','\\u003c')))
    print('Atlas:', args.out/'index.html')


if __name__ == '__main__':
    main()
