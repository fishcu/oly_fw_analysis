#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Offline, data-only yellow-lightness candidate for PEN-F 3101.

Edits one existing halfword in the shared COLOR table. No hooks, new state,
spare bytes, version edit, camera access or saved installable container.
Defaults to L +6 (one changed byte); L +7 changes two bytes at the same field.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import struct

from penf_emulator import firmware, Region, color_builder, ROOT, BASE, ENGINE
from penf_color_fixtures import (capture, pack, dispatch, write_registers, run,
    memory, changes, sha, checksum_preview, OBJECT, PARAM, META, META_PTR,
    YELLOW_L, TAG_PARAM, TAG_REQUEST)
from penf_disasm import refs, window, DEFAULT_IMAGE, DEFAULT_OBJDUMP
from oly_container import encode, decode

TABLE, FIELD = 0x60622d74, 0x60622d84
VALUES = {6:250, 7:300}


def candidate(lightness):
    stock=firmware()
    offset=FIELD-BASE
    assert stock[offset:offset+2]==b'\0\0'
    result=bytearray(stock)
    struct.pack_into('<h',result,offset,VALUES[lightness])
    result=bytes(result)
    diff=changes(stock,result)
    assert diff==[offset] if lightness==6 else diff==[offset,offset+1]
    return result


def compact_request(image, saturation):
    """Run the native compact color-field excerpt, then the complete packer."""
    obj=bytearray(0x3450)
    struct.pack_into('<H',obj,14,11)
    compact=bytearray(0x300)
    struct.pack_into('<12b',compact,620,*saturation)
    r=run(image,0x60520b1c,0x60520c39,{'d3':PARAM,'a2':META_PTR},[
        Region('object',OBJECT,obj,'rw',True),Region('compact_source',META,compact),
        Region('compact_pointer',META_PTR,struct.pack('<I',META))])
    request,_=pack(image,memory(r,'object'))
    assert request[TAG_REQUEST]==0
    assert struct.unpack_from('<12b',request,1076)==tuple(saturation)
    return request


def verify(image, lightness, out):
    stock=firmware(); value=VALUES[lightness]
    expected=[YELLOW_L] if lightness==6 else [YELLOW_L,YELLOW_L+1]
    register_diff=[0x2ee] if lightness==6 else [0x2ee,0x2ef]
    vectors=[[s]*12 for s in range(-5,6)]+[list(range(-5,6))+[0],
        [7,-7,0,5,-5,1,-1,2,-2,3,-3,4]]
    rows=[]
    for profile in (1,2,3):
        for saturation in vectors:
            a,_=capture(stock,11,profile,saturation)
            b,_=capture(image,11,profile,saturation)
            assert a==b and b[36+TAG_PARAM]==0
            qa,_=pack(stock,a);qb,_=pack(image,b)
            assert qa==qb and qb[TAG_REQUEST]==0
            oa,ra=dispatch(stock,qa);ob,rb=dispatch(image,qb)
            assert changes(oa,ob)==expected
            assert struct.unpack_from('<h',ob,YELLOW_L)[0]==value
            assert memory(ra,'context')==memory(rb,'context')
            # Code is identical: instruction count and all returned registers
            # are compared, in addition to whole-buffer output differences.
            assert ra['completed']==rb['completed']
            assert ra['registers']==rb['registers']
            rows.append(dict(kind='all_color_profiles',profile=profile,
                saturation=saturation,changed_offsets=expected,
                output_sha256=sha(ob),instructions=rb['completed']))
    for saturation in vectors:
        qa=compact_request(stock,saturation)
        qb=compact_request(image,saturation)
        assert qa==qb
        oa,ra=dispatch(stock,qa);ob,rb=dispatch(image,qb)
        assert changes(oa,ob)==expected
        reference=color_builder(saturation,overrides=[(0,16,value)])
        assert reference['status']=='returned' and memory(reference,'output')==ob
        assert memory(ra,'context')==memory(rb,'context')
        rows.append(dict(kind='compact_color_path',saturation=saturation,
            changed_offsets=expected,output_sha256=sha(ob)))
    for mode in (1,2,3,4,5,6,7,8,9,10,12):
        request=bytearray(1132);struct.pack_into('<H',request,10,mode)
        oa,ra=dispatch(stock,request,flags=0x64602e)
        ob,rb=dispatch(image,request,flags=0x64602e)
        assert oa==ob and memory(ra,'context')==memory(rb,'context')
        assert ra['registers']==rb['registers']
        rows.append(dict(kind='ordinary_mode_unchanged',mode=mode,output_sha256=sha(ob)))
    for bypass in ('sentinel','custom_unrelated_table','custom_color_table',
                   'custom_disabled','nonzero_group','nonzero_type'):
        request=bytearray(1132);struct.pack_into('<H',request,10,11)
        extra=[];flags=0
        if bypass=='sentinel':struct.pack_into('<H',request,12,0xf00d)
        elif bypass.startswith('custom'):
            address=0x19060000
            descriptor=bytearray(20)
            table=TABLE if bypass=='custom_color_table' else 0x60619f84
            struct.pack_into('<I',descriptor,16,table)
            struct.pack_into('<I',request,960,address)
            extra=[Region('custom_descriptor',address,descriptor)]
            flags=0 if bypass=='custom_disabled' else 0x10000000
        else:request[8 if bypass=='nonzero_group' else 9]=1
        oa,ra=dispatch(stock,request,flags=flags,extra=extra)
        ob,rb=dispatch(image,request,flags=flags,extra=extra)
        diff=changes(oa,ob)
        # Data edit affects any caller deliberately using this table, including
        # a synthetic custom descriptor. Do not claim a universal mode firewall.
        assert diff==(expected if bypass=='custom_color_table' else [])
        assert memory(ra,'context')==memory(rb,'context')
        rows.append(dict(kind='bypass_or_custom_table',path=bypass,changed_offsets=diff))
    for flags in (0,2):
        request=compact_request(stock,[0]*12)
        oa,ra=dispatch(stock,request,flags=flags)
        ob,rb=dispatch(image,request,flags=flags)
        assert changes(oa,ob)==expected
        assert ra['registers']==rb['registers']
        assert memory(ra,'context')==memory(rb,'context')
        rows.append(dict(kind='update_flags_unchanged',incoming_flags=flags,
            resulting_context_plus100=hex(struct.unpack_from('<I',memory(rb,'context'),100)[0])))
    for saturation in ([0]*12,[5]*12,[-5]*12):
        request=compact_request(stock,saturation)
        oa,_=dispatch(stock,request);ob,_=dispatch(image,request)
        for bank in (0x9e001800,0x9e005800):
            wa,_=write_registers(stock,oa,bank)
            wb,r=write_registers(image,ob,bank)
            assert changes(wa,wb)==register_diff
            assert wb[0x2d8:0x3fc]==ob[0x2a4:0x3c8]
            rows.append(dict(kind='native_register_writer',bank=hex(bank),
                saturation=saturation[0],changed_offsets=register_diff,
                yellow_word=hex(struct.unpack_from('<I',wb,0x2ec)[0]),
                instructions=r['completed']))
    # A shared output reused across COLOR and ordinary processing must not
    # retain the added lightness after the ordinary builder runs.
    oa=ob=bytes(5212)
    for mode in (11,2,11,5,11,3):
        request=bytearray(1132);struct.pack_into('<H',request,10,mode)
        flags=2 if mode==11 else 0x64602e
        oa,ra=dispatch(stock,request,flags=flags,output=oa)
        ob,rb=dispatch(image,request,flags=flags,output=ob)
        assert changes(oa,ob)==(expected if mode==11 else [])
        rows.append(dict(kind='reused_output_mode_switch',mode=mode,
            changed_offsets=changes(oa,ob)))
    (out/'native-tests.json').write_text(json.dumps(rows,indent=2)+'\n')
    return rows


def encoded_preview(image, integrity):
    """Check encoding independently against stock; save no encoded package."""
    original=ROOT/'firmware_files/OLY_E_122_3101_0000_0000.BIN'
    with original.open('rb') as f:
        f.seek(32);old=f.read(len(image))
    assert encode(firmware())==old
    new=encode(image)
    assert decode(new)==image
    differences=changes(old,new)
    return dict(encoded_payload_edits=[dict(container_offset=hex(i+32),
        before=f'{old[i]:02x}',after=f'{new[i]:02x}') for i in differences],
        total_container_bytes_that_would_change=len(differences)+integrity['trailer_bytes_that_would_change'],
        full_encoded_container_created=False,encoded_payload_saved=False)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--lightness',type=int,choices=VALUES,default=6)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    image=candidate(args.lightness)
    target=args.out/f'all-color-yellow-L{args.lightness}.NONINSTALLABLE.decoded'
    target.write_bytes(image)
    rows=verify(image,args.lightness,args.out)
    integrity=checksum_preview(image)
    transport=encoded_preview(image,integrity)
    pointers,calls=refs(firmware(),TABLE)
    assert pointers==[0x604f7502] and calls==[]
    table_audit=json.loads((ROOT/'analysis/profile_tables/profile-tables.json').read_text())
    assert table_audit['source_sha256']==sha(firmware())
    assert all(int(d['table'],16)!=TABLE for d in table_audit['generic_descriptors'])
    flash=0x407b1800+FIELD-0x60432800
    report=dict(status='Offline data-only candidate; no camera test or saved installable package',
        displayed_lightness=args.lightness,native_lightness=VALUES[args.lightness],
        applies_to='All consumers of the shared COLOR table; tested COLOR1/2/3 and compact path',
        stock_sha256=sha(firmware()),candidate_sha256=sha(image),decoded_size=len(image),
        decoded_bytes_changed=len(changes(firmware(),image)),parameter_sites=1,
        field=dict(table=hex(TABLE),runtime_address=hex(FIELD),decoded_offset=hex(FIELD-BASE),
            before=firmware()[FIELD-BASE:FIELD-BASE+2].hex(),
            after=image[FIELD-BASE:FIELD-BASE+2].hex(),logical_flash_address=hex(flash),
            loaded_section=3,erase_unit_index_from_main=(flash-0x403a0000)//0x20000),
        code_bytes_changed=0,added_code_bytes=0,new_state_bytes=0,file_growth=0,
        reused_padding_bytes=0,version_changed=False,tests_passed=len(rows),
        test_counts=dict(Counter(r['kind'] for r in rows)),checksum_preview=integrity,
        encoding_preview=transport,actual_main_update_extent_bytes=0x1460000,
        actual_main_update_erase_units=163,table_literal_reference=hex(pointers[0]),
        no_generic_descriptor_uses_color_table=True,
        limits=['Strict native routine tests and modeled register banks, not physical pixel output.',
          'Capture/compact parameter excerpts, not complete live-view or capture lifecycles.',
          'Full register-write scheduling is not connected end-to-end; native flags remain unchanged.',
          'Computed table consumers are not exhaustively excluded.',
          'Boot integrity and independent recovery remain unresolved.'],
        provenance={str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in
            (Path(__file__).resolve(),ROOT/'tools/penf_color_fixtures.py',
             ROOT/'tools/penf_emulator.py',ROOT/'tools/oly_container.py',ENGINE,
             ROOT/'analysis/profile_tables/profile-tables.json')})
    for name,lo,hi in [('shared_table_selection',0x604f74d8,0x604f7513),
                       ('compact_color_excerpt',0x60520b1c,0x60520c39)]:
        (args.out/(name+'.asm')).write_text(window(firmware(),DEFAULT_IMAGE,DEFAULT_OBJDUMP,lo,hi))
    (args.out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('displayed_lightness','decoded_bytes_changed',
        'code_bytes_changed','tests_passed','field','encoding_preview')},indent=2))


if __name__=='__main__':main()
