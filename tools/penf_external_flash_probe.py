#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Bounded external photographic-flash reconnaissance, not a firmware patch.

Execute a received-device-info parser and GPIO wrapper with synthetic RAM and
write-capture MMIO. No flash, camera, hot-shoe voltage or transport is modeled.
"""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess

from penf_emulator import BASE, ROOT, ENGINE, firmware
from penf_hsl_context_probe import state, finished
from penf_probe import CALLER
from penf_disasm import window, DEFAULT_IMAGE, DEFAULT_OBJDUMP
from penf_repack_preflight import sha

RX=0x6188969e
ID=0x61889592
CAP=0x618895a4
PARSER=0x602d139d
CAMERAS=[('PEN-F',DEFAULT_IMAGE,BASE),
    ('E-P7',Path('analysis/ep7_1100/00_0100_406a0020.decoded.bin'),0x60020020),
    ('OM-3',Path('analysis/om3_1100/00_0100_50000020.decoded.bin'),BASE)]


def parser_cases(image):
    rows=[]
    for identifier in (0,9,10,13,54,77,127):
        for flag in (0,0x40):
            q=bytearray([identifier,0,flag,0,0,0,0])
            q[6]=(0x86+sum(q[:6]))&255
            s=state(image,PARSER,0xf0,20,{})
            s.ram('external_flash_state',0x61889000,bytes(0x1000),aliases=False)
            s.write(RX,q)
            r=s.run({CALLER+7},limit=2000);finished(s,r)
            assert struct.unpack('<H',s.read(ID,2))[0]==identifier
            assert s.regs['d0']==(1 if identifier==77 else 0)
            if identifier!=77:
                assert s.read(CAP,1)[0]==(2 if flag else 1)
                assert s.read(0x618897b5,6)==q[:6]
            rows.append(dict(reply=q.hex(),identifier=identifier,bit6=bool(flag),
                result=s.regs['d0'],capability_class=s.read(CAP,1)[0],instructions=s.steps))
    s=state(image,PARSER,0xf0,20,{})
    s.ram('external_flash_state',0x61889000,bytes(0x1000),aliases=False)
    s.write(ID,struct.pack('<H',0xbeef))
    s.write(RX,bytes([13,0,0,0,0,0,0])) # Deliberately invalid checksum.
    r=s.run({CALLER+7},limit=2000);finished(s,r)
    assert s.regs['d0']==0x2c2a and s.read(ID,2)==struct.pack('<H',0xbeef)
    return dict(cases=rows,bad_checksum=dict(result=hex(s.regs['d0']),id_preserved=True),
        scope='Synthetic received command-0x86 payloads, not captured FL-LM3 traffic. '
              'Numeric protocol IDs have not been tied to named flash models.')


def gpio_cases(image):
    rows=[]
    for port in (73,95):
        mappings=struct.unpack_from('<4H',image,0x600261b8-BASE+port*8)
        assert mappings==(port,)*4
        address=struct.unpack_from('<I',image,0x60025cec-BASE+port*4)[0]
        for value in (0,1):
            s=state(image,0x602dab47,0,16,dict(d0=port,d1=value))
            s.ram('board_selector',0x8ff00188,bytes(1),aliases=False)
            s.ram('gpio_mmio',address,bytes.fromhex('a5a5a5a5'),aliases=False)
            r=s.run({CALLER+7},limit=500);finished(s,r)
            assert s.read(address,4)==struct.pack('<I',value)
            rows.append(dict(logical_port=port,board_mappings=list(mappings),
                mmio=hex(address),written_value=value,instructions=s.steps))
    return dict(cases=rows,scope='Native GPIO output wrapper and board lookup; '
        'port electrical role and connection to hot-shoe power/contact remain unknown.')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    stock=firmware()
    strings=[]
    for m in re.finditer(rb'[ -~]{5,}',stock):
        text=m.group().decode('ascii')
        if re.search(r'(strobe|stb).*(external|detect|charge|device|id)|'
                     r'(external|detect|charge|device|id).*(strobe|stb)',text,re.I):
            strings.append(dict(address=hex(BASE+m.start()),text=text))
    generations=[]
    for name,path,base in CAMERAS:
        data=path.read_bytes()
        parser=list(re.finditer(re.escape(bytes.fromhex('2c86000408fcdc')),data))
        family=list(re.finditer(re.escape(bytes.fromhex(
            '1ca009c806a00ac9068001ca0d8002f8e104a504c8048001')),data))
        assert len(parser)==len(family)==1
        addresses=dict(parser=base+parser[0].start(),family_selector=base+family[0].start())
        names={}
        for text in ('FL-LM3','FL-LM2','FLLM3','FL_LM3'):
            for encoding in ('ascii','utf-16-le','utf-16-be'):
                names[text+'/'+encoding]=data.count(text.encode(encoding))
        for label,address in addresses.items():
            # Parser prefix ends just before its model-ID-special-case branch.
            size=0x3d if label=='parser' else 0x1e
            asm=subprocess.check_output([str(DEFAULT_OBJDUMP.resolve()),'-b','binary','-m','mn10300',
                '-D','-z','--insn-width=16',f'--adjust-vma={base:#x}',
                f'--start-address={address:#x}',f'--stop-address={address+size:#x}',str(path)],text=True)
            (args.out/(name+'-'+label+'.asm')).write_text(asm)
        generations.append(dict(camera=name,path=str(path),sha256=sha(data),
            analysis_base=hex(base),landmarks={k:hex(v) for k,v in addresses.items()},name_matches=names))
    windows={'device-info-parser':(PARSER,0x602d1558),
        'device-id-getter':(0x602d21a3,0x602d21ac),
        'device-id-api':(0x60306bdc,0x60306c31),
        'id-family-selector':(0x602ce94b,0x602ce96c),
        'gpio-release':(0x602d1cfe,0x602d1d44),
        'gpio-wrapper':(0x602dab47,0x602dab5b),
        'gpio-dispatch':(0x60083f5d,0x60083f78),
        'gpio-output':(0x60084664,0x600846ae),
        'capability-gpio-branch':(0x602d0ac0,0x602d0adc)}
    for name,(lo,hi) in windows.items():
        (args.out/(name+'.asm')).write_text(window(stock,DEFAULT_IMAGE,DEFAULT_OBJDUMP,lo,hi))
    result=dict(status='all assertions passed',main_sha256=sha(stock),
        external_flash_strings=strings,generations=generations,
        received_info_parser=parser_cases(stock),gpio_outputs=gpio_cases(stock),
        limits=['No explicit FL-LM3 handler or named protocol-ID mapping established.',
                'Shared subsystem code also exists in incompatible E-P7.',
                'No determination of new PEN/OM-5 II electrical power capability.',
                'No camera access, driver transport emulation, flash firing or firmware patch.'],
        source_sha256={str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in [
            Path(__file__).resolve(),ROOT/'tools/penf_hsl_context_probe.py',
            ROOT/'tools/penf_emulator.py',ROOT/'tools/penf_update_probe.py',ROOT/'tools/penf_probe.py',
            ROOT/'tools/penf_boot_emulator.py',ROOT/'tools/penf_disasm.py',ENGINE]})
    (args.out/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print('15 native reply-parser cases, 4 native GPIO cases, 3 firmware inventories passed.')


if __name__=='__main__':main()
