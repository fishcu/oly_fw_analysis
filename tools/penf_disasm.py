#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Read-only windows and reference candidates for the exact PEN-F 3101 main block.

The caller must choose instruction-aligned window boundaries. A raw-byte call
or pointer match is a candidate until its surrounding instructions are checked.
"""
import argparse
from pathlib import Path
import re
import struct
import subprocess

from oly_container import sha256
from penf_landmarks import BASE, MAIN_SHA256

DEFAULT_IMAGE = Path('analysis/penf_3.1/00_0100_403a0020.decoded.bin')
DEFAULT_OBJDUMP = Path('toolchains/binutils-2.45-build/binutils/objdump')


def refs(data, address):
    pointers = [BASE + m.start() for m in re.finditer(re.escape(struct.pack('<I', address)), data)]
    calls = []
    for m in re.finditer(b'[\xcd\xdd]', data):
        p = m.start()
        size = 2 if data[p] == 0xcd else 4
        if p + size + 1 <= len(data):
            delta = int.from_bytes(data[p + 1:p + 1 + size], 'little', signed=True)
            if BASE + p + delta == address:
                calls.append(BASE + p)
    return pointers, calls


def annotate(line, data):
    match = re.search(r'\bmov\s+(-?\d+),[ad][0-3]', line)
    if match:
        address = int(match[1]) & 0xffffffff
        if BASE <= address < BASE + len(data):
            raw = data[address - BASE:address - BASE + 160]
            string = raw.split(b'\0')[0]
            label = ''
            if len(string) >= 4 and all(32 <= c < 127 for c in string):
                label = ' ' + repr(string.decode('ascii'))
            return line + f' ; pointer candidate {address:#x}' + label
    return line


def window(data, image, objdump, start, stop):
    if not BASE <= start < stop <= BASE + len(data):
        raise ValueError('window lies outside the main-block analysis mapping')
    result = subprocess.check_output([
        str(objdump.resolve()), '-b', 'binary', '-m', 'mn10300', '-D', '-z',
        '--insn-width=16', f'--adjust-vma={BASE:#x}',
        f'--start-address={start:#x}', f'--stop-address={stop:#x}', str(image)
    ], text=True)
    return '\n'.join(annotate(line, data) for line in result.splitlines()) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, default=DEFAULT_IMAGE)
    parser.add_argument('--objdump', type=Path, default=DEFAULT_OBJDUMP)
    parser.add_argument('--start', type=lambda x: int(x, 0))
    parser.add_argument('--stop', type=lambda x: int(x, 0))
    parser.add_argument('--refs', type=lambda x: int(x, 0))
    args = parser.parse_args()
    data = args.image.read_bytes()
    if sha256(data) != MAIN_SHA256:
        parser.error('requires the exact decoded PEN-F 3101 main block')
    if args.refs is not None:
        pointers, calls = refs(data, args.refs)
        print('Pointer candidates:', ', '.join(hex(x) for x in pointers))
        print('Call candidates:', ', '.join(hex(x) for x in calls))
    if args.start is not None and args.stop is not None:
        print(window(data, args.image, args.objdump, args.start, args.stop), end='')
    elif args.start is not None or args.stop is not None:
        parser.error('both --start and --stop are required for a window')


if __name__ == '__main__':
    main()
