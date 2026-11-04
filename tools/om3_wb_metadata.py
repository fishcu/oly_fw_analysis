#!/usr/bin/env python3
"""Verify the WB field metadata in the supplied, decoded OM-3 1100 main image.

Verifies metadata, grouped argument IDs, setter prologues, the compact WB copy
and the bounded alternate-cell table audit. Semantic labels come from execution.
No image is modified or distributed.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

EXPECTED = '5e8d376e9111a44ac0352f26030d7c1b17026d42c45f3600cfa02a0e8c5b7d59'
FIELDS = {9:(0x8121,0),39:(0x84f9,0),84:(0x8e41,0),107:(0x8f22,1),
          132:(0x9679,0),1578:(0x1cc1,0),1592:(0x1ce9,19),
          1605:(0x1cf9,19),1632:(0x1d22,0),1720:(0x8131,0)}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('decoded_main', type=Path)
    args = parser.parse_args()
    data = args.decoded_main.read_bytes()
    if hashlib.sha256(data).hexdigest() != EXPECTED:
        parser.error('expected decoded OM-3 1100 main image')
    table = 0x6062555c - 0x60021020
    fields = {}
    for sid, expected in FIELDS.items():
        actual = struct.unpack_from('<HH',data,table+sid*4)
        if actual != expected:
            raise ValueError(f'metadata mismatch for setting {sid}: {actual}')
        fields[sid] = {'record':f'{actual[0]:04x}','index':actual[1]}
    indices = [0,18,5,1,7,14,10,12,13,15,16,17,19]
    for first, record in [(1580,0x1ce9),(1593,0x1cf9)]:
        for offset, index in enumerate(indices):
            if struct.unpack_from('<HH',data,table+(first+offset)*4) != (record,index):
                raise ValueError(f'correction bank mismatch at {first+offset}')
    def read(address,size):
        return data[address-0x60021020:address-0x60021020+size]
    groups={}
    for row in range(134):
        ids=struct.unpack('<17H',read(0x605b49d4+34*row,34))
        if ids[0] in (9,901):
            groups[ids[0]]=list(ids[1:ids.index(3200)])
    assert groups=={9:[9,1720,1765,84],901:[901,1111]},groups
    assert read(0x603f1ea1,5)==bytes.fromhex('f1e6831f8c')
    assert read(0x60aea1de,3)==bytes.fromhex('938782')
    copy_sha=hashlib.sha256(read(0x604876ba,0x60487736-0x604876ba)).hexdigest()
    assert copy_sha=='94ad7e55f07eb926a93723d35f4e6fcb3f29428320d0c0f540cf28ff015186a0'
    assert read(0x60457c44,6)==bytes.fromhex('fcccf9840000')
    assert read(0x60457c5d,6)==bytes.fromhex('fccc79960000')
    assert read(0x60457c76,6)==bytes.fromhex('fc600a930000')
    processing_sha=hashlib.sha256(read(0x60457c44,0x60457c80-0x60457c44)).hexdigest()

    for row in range(22):
        group,variant,address,count=struct.unpack('<HHII',read(0x605f6c7c+12*row,12))
        assert group and 0<count<3000
        entries=[struct.unpack('<HBB',read(address+4*i,4)) for i in range(count)]
        target=[x for x in entries if 904<=x[0]<=923]
        assert sorted(x[0] for x in target)==list(range(904,924))
        assert all(x[1]==0 for x in target)
    assert struct.unpack('<H',read(0x605f6c7c+22*12,2))[0]==0
    print(json.dumps({'sha256':EXPECTED,'fields':fields,'correction_indices':indices,
                      'raw_argument_groups':groups,'ui_setter':'0x60aea1de',
                      'commit_prologue':'0x603f1ea1','compact_copy_sha256':copy_sha,
                      'cwb_processing_slice_sha256':processing_sha,
                      'alt_table_audit':{'groups':22,'ids':'904..923','selected_part':0,
                                        'scope':'examined static mode tables only'}},indent=2))

if __name__ == '__main__':
    main()
