#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Verify E-P7's missing external-flash GPIO routes using stock initializers.

No MMIO is mapped: an attempted hardware access stops the native experiment.
"""
import argparse
from dataclasses import replace
from pathlib import Path
import struct
from penf_probe import ProbeState, CALLER
from penf_hsl_context_probe import finished
from penf_repack_preflight import sha,save
from compare_external_flash import asm

IMAGE=Path('analysis/ep7_1100/00_0100_406a0020.decoded.bin')
BASE=0x60020020


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    b=IMAGE.read_bytes()
    assert sha(b)=='5dd9af164b4590c7e82f6905c919b3cc450bb58f2d5742ab2a0e3a4eb2e26190'
    # Startup 60020117..60020137 copies this exact initialized-data range.
    initial=b[0x6002e020-BASE:0x6002e8e8-BASE]
    assert len(initial)==0x8c8
    assert b[0x6016bb7b-BASE:0x6016bb7e-BASE]==bytes.fromhex('de0000')
    rows=[]
    for board in range(5):
        at=0x61b217cc-0x61b20fe0+board*8
        pointer,count=struct.unpack_from('<2I',initial,at)
        assert pointer==0x61b217a4+board*8 and count==0
        for value in (0,1):
            s=ProbeState(0x60172e44,0,16,bytes(16),dict(d0=255,d1=value))
            s.regions=[replace(r,address=BASE,data=b) if r.name=='main' else r for r in s.regions]
            s.ram('stock_initial_data',0x61b20fe0,initial,aliases=False)
            s.ram('board_selector',0x6203c794,bytes([board]),aliases=False)
            r=s.run({CALLER+7},limit=2000);finished(s,r)
            rows.append(dict(board_index=board,port=255,value=value,remap_count=count,
                instructions=s.steps,returned=True,mmio_regions_present=False))
    windows=[('capability-gpio-branch',0x6016a2da,0x6016a323),
        ('wrapper',0x60172e44,0x60172e6d),('release-empty',0x6016bb7b,0x6016bb7e),
        ('dispatcher',0x600688cf,0x6006890a),('output-handler',0x600691c3,0x60069204),
        ('board-remapper',0x60022254,0x60022299),('data-copy',0x60020117,0x60020139)]
    for name,lo,hi in windows:(args.out/(name+'.asm')).write_text(asm(IMAGE,BASE,lo,hi))
    save(args.out,'audit',dict(all_assertions_passed=True,source=str(IMAGE),main_sha256=sha(b),
        script_sha256=sha(Path(__file__).read_bytes()),cases=rows,
        release_is_bare_return=True,stock_initializer_source='6002e020..6002e8e8',
        stock_initializer_destination='61b20fe0',board_table='61b217cc',
        interpretation='For the five explicit stock remap descriptors, logical port 255 remains '
            '255 and the output handler exits before hardware write and callback. '
            'The corresponding release helper is a bare return. This is a compile-time '
            'hardware-configuration distinction, not evidence that changing a port creates '
            'missing circuitry. It does not identify a named FL-LM3 protocol ID.'))
    print('10 native GPIO cases returned without any MMIO mapping; stock remap descriptors checked.')


if __name__=='__main__':main()
