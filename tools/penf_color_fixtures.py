# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native capture, COLOR request and checksum fixtures for PEN-F build 3101.

These helpers execute bounded routines with synthetic caller memory and capture
register writes. They do not simulate ISP pixels or install firmware.
"""
import hashlib
import json
import struct

from penf_emulator import Region, execute, firmware, checksum, BASE, ROOT
from oly_container import sum32


CALLER, STACK, SP = 0x18000000, 0x18010000, 0x18018000


OBJECT, META, META_PTR = 0x19000000, 0x19010000, 0x19020000


PARAM = OBJECT + 36


REQUEST, OUTPUT, CONTEXT = 0x19030000, 0x19040000, 0x19050000


TAG_PARAM, TAG_REQUEST, YELLOW_L = 0x164f, 0x443, 0x2ba


CALLEE = dict(d2=0x22334455, d3=0x66778899, a2=0x13579bdf, a3=0x2468ace0)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def changes(a, b):
    assert len(a) == len(b)
    return [i for i, (x, y) in enumerate(zip(a, b)) if x != y]


def memory(result, name):
    return bytes.fromhex(next(x['hex'] for x in result['memory'] if x['name'] == name))


def run(image, start, end, regs, regions, *, call=None, limit=10000):
    stack = next((r for r in regions if r.name == 'stack'), None)
    if stack is None:
        regions = list(regions) + [Region('stack', STACK, bytes(0x10000), 'rw', True)]
    initial = dict(CALLEE, sp=SP, pc=start, psw=0)
    initial.update(regs)
    if call:
        mask, frame = call
        code = b'\xdd'+struct.pack('<i', start-CALLER)+bytes((mask, frame))
        regions = list(regions)+[Region('caller', CALLER, code, 'rx')]
        initial['pc'] = CALLER
        end = CALLER + 7
    regions = [Region('main', BASE, image, 'rx'),
               Region('relocated_native_helpers', 0x47000800,
                      firmware()[0x113c9e0:0x113c9e0+0x1800], 'rx')] + list(regions)
    result = execute(regions, initial, end, limit=limit, trace_limit=30, trace_tail=True)
    if result['status'] != 'returned':
        raise AssertionError(json.dumps({k:result[k] for k in
            ('status','fault','registers','trace')}, indent=2))
    if call:
        for reg in ('d2','d3','a2','a3','sp'):
            assert result['registers'][reg] == initial[reg], reg
    return result


def capture(image, mode, profile, saturation, *, initial_tag=0, metadata_route=False):
    obj = bytearray(0x3450)
    # The separate native mode-copy tests check this small fixture's key layout.
    struct.pack_into('<H', obj, 14, mode)
    obj[36+TAG_PARAM] = initial_tag
    meta = bytearray(0x6000)
    meta[0x48a3], meta[0x48c1] = mode, profile
    struct.pack_into('<12h', meta, 0x48a8, *saturation)
    stack = bytearray(0x10000)
    struct.pack_into('<I', stack, SP-STACK+4, PARAM)
    struct.pack_into('<II', stack, SP-STACK+20, PARAM, META)
    regions = [Region('object', OBJECT, obj, 'rw', True),
               Region('metadata', META, meta),
               Region('metadata_pointer', META_PTR, struct.pack('<I',META)),
               Region('stack', STACK, stack, 'rw', True)]
    if metadata_route:
        result = run(image, 0x60532379, 0x60532391, {}, regions)
    else:
        result = run(image, 0x6052048b, 0x6052062f, {'d3':META_PTR}, regions)
    return memory(result,'object'), result


def pack(image, obj):
    result = run(image, 0x604c3051, None, {'a0':OBJECT,'a1':REQUEST,'d0':0},
                 [Region('object',OBJECT,obj,'r'),
                  Region('request',REQUEST,b'\xa5'*1132,'rw',True)], call=(0xf0,28))
    return memory(result,'request'), result


def dispatch(image, request, *, flags=2, output=None, extra=()):
    context = bytearray(104)
    struct.pack_into('<I',context,4,REQUEST)
    struct.pack_into('<I',context,12,OUTPUT)
    struct.pack_into('<I',context,56,flags)
    struct.pack_into('<I',context,100,0xffffffff)
    result = run(image, 0x604f747f, None, {'a0':CONTEXT},
        [Region('request',REQUEST,request),
         Region('output',OUTPUT,output or bytes(5212),'rw',True),
         Region('context',CONTEXT,context,'rw',True)]+list(extra), call=(0xf0,20), limit=20000)
    return memory(result,'output'), result


def write_registers(image, output, bank):
    result=run(image,0x604b5006,None,{'a0':bank,'a1':OUTPUT},
        [Region('output',OUTPUT,output),
         Region('register_bank',bank,b'\xa5'*0x500,'w',True)],call=(0xf0,24))
    return memory(result,'register_bank'),result


def checksum_preview(patched):
    """Exercise the firmware checksum on decoded RAM buffers; save no package."""
    original=ROOT/'firmware_files/OLY_E_122_3101_0000_0000.BIN'
    with original.open('rb') as f:
        header=f.read(32)
        size=struct.unpack_from('<I',header,12)[0]
        assert size==len(patched)
        f.seek(32+size)
        trailer=f.read(32)
    assert header[:28]==trailer[:28]
    assert sum32(header+firmware()+trailer)==0
    stale=header+patched+trailer
    expected=sum32(stale)
    assert expected!=0
    stale_native=checksum(stale)
    assert stale_native['status']=='returned' and stale_native['registers']['d0']==expected
    old=struct.unpack_from('<I',trailer,28)[0]
    new=(old-expected)&0xffffffff
    corrected_trailer=trailer[:28]+struct.pack('<I',new)
    corrected=header+patched+corrected_trailer
    corrected_native=checksum(corrected)
    assert corrected_native['status']=='returned' and corrected_native['registers']['d0']==0
    return dict(scope='Native additive checksum only, not the updater or any boot verifier; decoded temporary RAM buffers only',
        stock_trailer_checksum=hex(old),prototype_trailer_checksum=hex(new),
        with_stock_checksum_native_sum=hex(expected),with_corrected_checksum_native_sum=0,
        trailer_bytes_that_would_change=len(changes(trailer,corrected_trailer)),
        hypothetical_trailer_container_offset=hex(32+size+28),
        instructions_each=corrected_native['completed'],container_created=False)
