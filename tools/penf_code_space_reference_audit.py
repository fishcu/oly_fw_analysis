#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Classify preferred section-3 reference candidates using actual data formats.

No patch generation. Remaining opaque assets stay unresolved. This is a
classification of the recorded literal/branch candidates, not an exhaustive
computed-access or DMA analysis.
"""
import argparse
import io
import json
from pathlib import Path
import struct

from PIL import Image
from oly_container import parse
from penf_emulator import ROOT, BASE, firmware
from penf_repack_preflight import sha, save
from penf_disasm import window, DEFAULT_IMAGE, DEFAULT_OBJDUMP


def resource_rows(data, table, address_base, end):
    """Read fixed 16-byte address/length records, with absolute flash pointers."""
    first=struct.unpack_from('<I',data,table)[0]-address_base
    assert table < first <= end and (first-table)%16==0
    result=[]
    for i in range((first-table)//16):
        pointer,size,x,y=struct.unpack_from('<4I',data,table+16*i)
        start=pointer-address_base
        if size and first<=start and start+size<=end:
            assert x==y==0
            result.append(dict(index=i,start=start,end=start+size))
    return result


def containing_asset(block, offset):
    data=block.payload;address_base=block.address+32
    rows=resource_rows(data,0,address_base,len(data))
    matching=[x for x in rows if x['start']<=offset<x['end']]
    assert len(matching)==1
    row=matching[0];path=[row['index']]
    if data[row['start']:row['start']+2]==b'OE':
        a,z=row['start'],row['end']
        assert data[a:a+32]==data[z-32:z]
        assert struct.unpack_from('<I',data,a+12)[0]==z-a-64
        nested=resource_rows(data,a+32,address_base,z-32)
        matching=[x for x in nested if x['start']<=offset<x['end']]
        assert len(matching)==1
        row=matching[0];path.append(row['index'])
    return row,path


def jpeg_layout(data):
    """Validate marker lengths and entropy spans through EOI; handle stuffing."""
    assert data[:2]==b'\xff\xd8'
    pos=2;segments=[];scans=[]
    while pos<len(data):
        assert data[pos]==255,hex(pos)
        while data[pos]==255:pos+=1
        marker=data[pos];pos+=1
        if marker==0xd9:
            return dict(end=pos,segments=segments,scans=scans)
        assert marker not in (0,0xd8) and not 0xd0<=marker<=0xd7
        size=int.from_bytes(data[pos:pos+2],'big')
        assert size>=2 and pos+size<=len(data)
        segments.append(dict(marker=hex(marker),start=pos+2,end=pos+size))
        pos+=size
        if marker==0xda:
            start=pos
            while True:
                candidate=data.index(b'\xff',pos)
                j=candidate+1
                while data[j]==255:j+=1
                if data[j]==0 or 0xd0<=data[j]<=0xd7:
                    pos=j+1;continue
                scans.append(dict(start=start,end=candidate))
                pos=candidate;break
    raise ValueError('JPEG has no end marker')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',required=True,type=Path)
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    audit_path=ROOT/'analysis/code_space/verified/audit.json'
    previous_path=ROOT/'analysis/code_space/reference_review/review.json'
    audit=json.loads(audit_path.read_text());b=firmware()
    candidate=next(x for x in audit['candidates'] if x['section']==3)
    previous=json.loads(previous_path.read_text())
    assert previous['main_image_sha256']==audit['main_sha256']==sha(b)
    blocks={hex(x.kind):x for x in parse((ROOT/'firmware_files/OLY_E_122_3101_0000_0000.BIN').read_bytes())}
    literals=[];jpegs={}
    for h in candidate['literal_reference_candidates']:
        row=dict(h)
        if h['component']=='0x100':
            review=next(x for x in previous['main_literal_candidates'] if x['section']==3 and
                        x['offset']==h['offset'] and x['alias']==h['alias'])
            row.update(classification='misaligned instruction bytes',evidence=review)
        else:
            block=blocks[h['component']];offset=int(h['offset'],16)
            asset,path=containing_asset(block,offset)
            row['resource_path']=path
            row['asset_range']=[hex(asset['start']),hex(asset['end'])]
            jpeg_start=None
            for prefix in (0,64):
                if block.payload[asset['start']+prefix:asset['start']+prefix+3]==b'\xff\xd8\xff':
                    jpeg_start=asset['start']+prefix;break
            if jpeg_start is None:
                row.update(classification='unresolved bytes inside indexed resource',
                           first32_hex=block.payload[asset['start']:asset['start']+32].hex())
            else:
                key=h['component']+':'+hex(jpeg_start)
                if key not in jpegs:
                    raw=block.payload[jpeg_start:asset['end']]
                    layout=jpeg_layout(raw)
                    im=Image.open(io.BytesIO(raw));size=im.size;fmt=im.format;im.verify()
                    assert fmt=='JPEG'
                    jpegs[key]=dict(start=hex(jpeg_start),bytes_through_eoi=layout['end'],
                        dimensions=list(size),sha256=sha(raw[:layout['end']]),layout=layout)
                item=jpegs[key];relative=offset-jpeg_start
                covering=[x for x in item['layout']['scans'] if x['start']<=relative and relative+4<=x['end']]
                assert len(covering)==1, (h,relative)
                row.update(classification='JPEG entropy-coded scan bytes',jpeg=key,
                           offset_within_jpeg=hex(relative))
        literals.append(row)
    cmio=b[0x6067e000-BASE:0x6069b240-BASE]
    assert len(cmio)==119360 and cmio[:4]==b'CMIO'
    assert sha(cmio)==previous['orf_cmio_sha256']
    relative=[]
    for h in candidate['relative_transfer_candidates']:
        assert 0x6067e000<=int(h['site'],16)<0x6069b240
        relative.append(dict(h,classification='CMIO serialized data, exact match to ORF block'))
    for name,a,z in [('cmio-copy-and-size',0x604db0f1,0x604db123),
                     ('section-initializer-table-consumer',0x6006da8c,0x6006db18)]:
        (args.out/(name+'.asm')).write_text(window(b,DEFAULT_IMAGE,DEFAULT_OBJDUMP,a,z))
    counts={}
    for x in literals:counts[x['classification']]=counts.get(x['classification'],0)+1
    older=(ROOT/'analysis/preset_startup_final/penf3100.main.bin').read_bytes()
    report=dict(main_sha256=sha(b),candidate=candidate['proposed_start'],
        literal_classification_counts=counts,literal_candidates=literals,
        relative_candidates=relative,jpeg_assets=jpegs,
        cmio=dict(start='0x6067e000',end_exclusive='0x6069b240',bytes=len(cmio),sha256=sha(cmio),
                  matches_recorded_ORF_block_sha256=previous['orf_cmio_sha256'],copy_function='0x604db0f1',
                  explicit_size_getter='0x604db11a',
                  identical_3100=cmio==older[0x6067e000-BASE:0x6069b240-BASE]),
        initializer_table=dict(start='0x6069b240',bytes=44,end_exclusive='0x6069b26c',
            functions=list(map(hex,struct.unpack_from('<11I',b,0x6069b240-BASE))),
            identical_3100=b[0x6069b240-BASE:0x6069b26c-BASE]==older[0x6069b240-BASE:0x6069b26c-BASE],
            section3_dispatch_branch_identical_3100=b[0x6006dab7-BASE:0x6006dacc-BASE]==older[0x6006dab7-BASE:0x6006dacc-BASE],
            constructor_code_region_identical_3100=b[0x60547d3e-BASE:0x60549f34-BASE]==older[0x60547d3e-BASE:0x60549f34-BASE]),
        source_sha256={str(x.relative_to(ROOT)):sha(x.read_bytes()) for x in
                       (Path(__file__).resolve(),audit_path,previous_path)},
        limits='Two opaque resource matches remain unresolved. No whole-program indirect-address, '
               'DMA or later-RAM-lifetime proof. JPEG marker parsing and Pillow verification do not '
               'constitute reverse engineering of the resource loader.')
    save(args.out,'audit',report)
    print(json.dumps(counts),flush=True)
    print(len(relative),'relative matches classified as exact ORF CMIO data;',len(jpegs),'JPEG assets verified')


if __name__=='__main__':main()
