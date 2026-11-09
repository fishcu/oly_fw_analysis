#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Bounded native COLOR-label layout probes using the stock English assets.

The font/context are explicit fixtures, not captured running-camera objects.
Native text parsing, metrics, layout and clipping run to each glyph renderer.
Raster submission is recorded, not modeled as a physical display.
"""
import json
import struct
from pathlib import Path

from penf_emulator import Region
from penf_osd_bitmaps import BitmapBank
from penf_probe import ProbeState, CALLER
from penf_profile_lifecycle_probe import invoke, returned
from penf_profile_context_probe import resume
from penf_diagnostic_lifetime_probe import parser_state

CONTEXT, BACKEND, FONT, CONFIG = 0x19500000, 0x19501000, 0x19502000, 0x19502100
STYLE, RECT, STRING = 0x19503000, 0x19503100, 0x19503200
GLYPH = (0x60bc7c1a, 0x60bc82b1)


def fixture():
    s = ProbeState(0x60bc1fbf, 0xf0, 252, bytes(128), {})
    parser_state(s)
    bank = BitmapBank()
    for index, base in ((0, 0xa1fa6c00), (42, 0xa2c63c00),(8,0xa2ce3c00)):
        row = bank.rows[index]
        s.regions.append(Region('stock_font_resource_'+str(index), base,
                                bank.data[row['start']:row['end']], 'r'))
    s.ram('explicit_gui_globals', 0x6160c000, bytes(0x600), aliases=False)
    s.ram('explicit_font_bank_globals', 0x61a8e328, bytes(0x40), aliases=False)
    s.write(0x61a8e328, struct.pack('<II', 0xa1fa6c00, 0xa2c63c00))
    s.ram('explicit_font_globals', 0x61a8e6b0, bytes(0x40), aliases=False)
    s.ram('font_metrics', 0x19502300, struct.pack('<9H',15,0,32,0,0,0,0,32,0), aliases=False)
    common=bank.rows[0]
    common=bank.data[common['start']:common['end']]
    names=struct.unpack_from('<I',common,12)[0]-0xa1fa6c00
    english=common[names+78:names+156]
    assert struct.unpack_from('<H',english)[0]==15
    s.ram('stock_english_spacing', 0x19502400, english[72:77], aliases=False)
    s.ram('glyph_request_data', 0x19502500, bytes(0x100), aliases=False)
    s.write(0x61a8e6b0, struct.pack('<I', 0x19502300))
    s.write(0x61a8e6c8, struct.pack('<I', 0x19502400))
    s.write(0x61a8e6c4, struct.pack('<I', 0x19502500))
    s.write(0x61a8e6b4,struct.pack('<H',1))
    s.write(0x61a8e6b8,struct.pack('<III',0x19502600,FONT,CONFIG))
    s.ram('font_name_pool',0x19502600,b'\0\0'+english[2:66]+bytes(18),aliases=False)
    row=bank.rows[8]; lang=bank.data[row['start']:row['end']]
    font_table=struct.unpack_from('<I',lang,4)[0]
    s.ram('explicit_english_font_style_table',1633782008,struct.pack('<I',font_table),aliases=False)
    for address, target in ((0x6160c0ec,0x60bcf524), (0x6160c0f0,0x60bcf71c),
                            (0x6160c0d0,0x60bcf364),(0x6160c0dc,0x60bcf4d6),
                            (0x6160c0fc,0x60bcf3a9)):
        s.write(address, struct.pack('<I',target))
    context = bytearray(680)
    for offset in (4,24):struct.pack_into('<4h',context,offset,0,0,639,479)
    struct.pack_into('<H',context,52,2)
    struct.pack_into('<II',context,72,BACKEND,FONT)
    s.ram('drawing_context_fixture',CONTEXT,context,aliases=False)
    s.ram('drawing_backend_fixture',BACKEND,bytes(160),aliases=False)
    s.write(BACKEND,struct.pack('<3H',0,640,480))
    s.write(BACKEND+104,struct.pack('<I',0x60bcc752))
    s.ram('surface_pointer_fixture',0x61a8e308,bytes(24),aliases=False)
    # Exact backend contract: normal glyph callback is60bcc752; API135
    # returns NULL, so the generic scaled-font fast path is unavailable.
    r=invoke(s,0x60bcf8d3,0x20,4,dict(d0=135));returned(s,r)
    assert s.regs['a0']==0
    s.ram('font_object_fixture',FONT,struct.pack('<HHII',0,0,CONFIG,0),aliases=False)
    config=bytearray(24)
    struct.pack_into('<HH',config,0,32,32)
    config[16:18]=b'\x01\x01'
    s.ram('font_config_fixture',CONFIG,config,aliases=False)
    # The native formatter interprets byte12=1 as horizontal center and
    # byte13=1 as vertical center. Colors follow stock text style15.
    s.ram('text_style',STYLE,struct.pack('<III2B5H',0,15,15,1,1,0,0,0,0,0),aliases=False)
    s.ram('text_rectangle',RECT,bytes(8),aliases=False)
    s.ram('text_string',STRING,bytes(128),aliases=False)
    s.ram('line_storage_allocation',0x19504000,bytes(256),aliases=False)
    return s


def glyph_boundary(s):
    pc=s.regs['pc']; assert pc==GLYPH[0], 'Scaled renderer is not qualified on PEN-F'
    entry_sp,entry_return=s.regs['sp'],s.regs['mdr']
    context,pointer=s.regs['a0'],s.regs['a1']
    source=int.from_bytes(s.read(pointer,4),'little')
    record=dict(code=hex(int.from_bytes(s.read(source,2),'little')),
        origin=struct.unpack('<2h',s.read(context+32,4)),
        scale=[s.regs['d0'],s.regs['d1']] if pc==GLYPH[1] else [1,1],
        request=s.read(pointer,24).hex(),renderer=hex(pc))
    # Execute the actual camera-specific backend too: it adds native
    # character spacing after the generic glyph primitive. Stopping before
    # that tail gave misleading pen advances/centering in the early probe.
    draws=[]
    while True:
        r=resume(s,(entry_return,0x60bcd181,0x60bccfd2))
        if s.regs['pc']==entry_return:break
        assert s.regs['pc'] in (0x60bcd181,0x60bccfd2),{k:r[k] for k in ('status','pc','fault')}
        draws.append(dict(entry=hex(s.regs['pc']),font=s.regs['d0'],code=hex(s.regs['d1']),
                          surface=hex(s.regs['a0'])))
        s.return_from_model(1)
    record['native_pen_after']=struct.unpack('<2h',s.read(context+32,4))
    assert s.regs['sp']==entry_sp+84
    record['draw_calls']=draws
    return record


def layout(s, text, scale=1, rect=(0,0,639,95)):
    assert scale==1, 'Use the registered PEN-F glyph backend, not hypothetical scaling'
    s.write(STRING,(text+'\0').encode('utf-16le'))
    s.write(RECT,struct.pack('<4h',*rect))
    s.write(CONFIG+16,bytes([scale,scale]))
    glyphs=[]
    stops=(*GLYPH,0x60bcb01b,0x60bcb025)
    r=invoke(s,0x60bc1fbf,0xf0,252,dict(a0=CONTEXT,a1=RECT,d0=STYLE,d1=STRING),stops=stops)
    while s.regs['pc']!=CALLER+7:
        pc=s.regs['pc']
        if pc==0x60bcb01b:
            assert s.regs['a0']<=256,r
            s.return_from_model(0)
            s.regs['a0']=0x19504000
        elif pc==0x60bcb025:
            assert s.regs['a0']==0x19504000
            s.return_from_model(0)
        elif pc in GLYPH:
            glyphs.append(glyph_boundary(s))
        else:raise AssertionError({k:r[k] for k in ('status','pc','fault')})
        r=resume(s,(*stops,CALLER+7))
    returned(s,r)
    return dict(text=text,scale=scale,rectangle=rect,glyphs=glyphs,
                models=['line-storage allocation/free','glyph raster submission'])


if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    s=fixture()
    rows=[layout(s,text,scale) for text,scale in
          [('Hue',1),('Saturation',1),('Lightness',1),('Switch @A047@',1),('Value',1)]]
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(rows,indent=2)+'\n')
    print(args.out)
