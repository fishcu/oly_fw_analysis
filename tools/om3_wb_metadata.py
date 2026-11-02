#!/usr/bin/env python3
"""Verify the WB field metadata in the supplied, decoded OM-3 1100 main image.

This verifies record identities only; semantic labels come from GUI observations.
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
    print(json.dumps({'sha256':EXPECTED,'fields':fields,'correction_indices':indices},indent=2))

if __name__ == '__main__':
    main()
