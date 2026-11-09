#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native PEN-F CMIO look encoding on copies, for firmware implementation tests.

Only the pinned 3101/3100 tuning block is accepted. No private tags, camera
access, firmware writing, or changes to the original RAW file. H/L arguments
use Workspace/OES slider signs and order, rather than native table coefficients.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from penf_emulator import BASE, firmware
from penf_orf_controls import ORF

T_ROM, T_SIZE = 0x6067e000, 119360
CREATIVE_ROM, TABLE_SIZE = 0x60622d74, 3028
MODE_TABLES = ((0x2498, 0x60619f84, 0x398),
               (0x306c, 0x6061ab58, 0x3e0))
ORDER = (0, 6, 1, 7, 2, 8, 3, 9, 4, 10, 5, 11)
LIGHTNESS = (-300, -250, -200, -150, -100, -50, -25,
             0, 25, 50, 100, 150, 200, 250, 300)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rom(address, size):
    data = firmware()[address-BASE:address-BASE+size]
    assert len(data) == size
    return data


def trunc_div(n, d):
    return (abs(n)//d) * (-1 if n < 0 else 1)


def coefficients(hue, saturation, lightness):
    """Derive 12 native (H,S,L) triplets from existing camera constants."""
    for values in (hue, saturation, lightness):
        if len(values) != 12 or any(type(x) is not int or not -7 <= x <= 7 for x in values):
            raise ValueError('Expected twelve integer slider values in -7..+7')
    table = rom(CREATIVE_ROM, TABLE_SIZE)
    gains = struct.unpack('<12I', rom(0x6062fef8, 48))
    result = bytearray(72)
    for i, r in enumerate(ORDER):
        base = struct.unpack_from('<h', table, 28*r+14)[0]
        gain = struct.unpack_from('<H', rom(gains[r], 4), 2 if saturation[i] < 0 else 0)[0]
        s = trunc_div(trunc_div(base*gain*saturation[i], 5), 256)
        struct.pack_into('<3h', result, r*6, -1000*hue[i], s, LIGHTNESS[lightness[i]+7])
    return bytes(result)


def replace_encoded_span(encoded, offset, old_plain, new_plain):
    """Patch a CMIO T span without decrypting the surrounding block.

    For p>=9 the obfuscation is C[p]=P[p]^P[p-1]^K[p]. Thus a plaintext
    difference at p affects exactly C[p] and C[p+1]. Both boundary bytes
    matter. This is a format identity, not an assumption about checksums.
    """
    if len(old_plain) != len(new_plain) or not 9 <= offset < offset+len(old_plain) < 0x1d223:
        raise ValueError('Replacement must lie inside the encoded CMIO payload')
    for i, (old, new) in enumerate(zip(old_plain, new_plain)):
        delta = old ^ new
        encoded[offset+i] ^= delta
        encoded[offset+i+1] ^= delta


def bake(data, hue, saturation, lightness):
    """Return copied ORF plus audit; keep RAW strips and other metadata exact."""
    layout = ORF(data)
    ip = layout.ifd(layout.maker_base+layout.ints(layout.maker[0x2040])[0], layout.maker_base)
    p = bytearray(layout.value(ip[0x635]))
    t = bytearray(layout.value(ip[0x636]))
    if bytes(t) != rom(T_ROM, T_SIZE):
        raise ValueError('Requires the untouched, pinned PEN-F 3.x CMIO tuning block')
    if len(p) != 5764 or p[:8] != b'CMIO\x01\x00\x11\xdc':
        raise ValueError('Unexpected PEN-F processing block')
    weights = coefficients(hue, saturation, lightness)
    creative = rom(CREATIVE_ROM, TABLE_SIZE)
    for t_offset, old_rom, p_offset in MODE_TABLES:
        replace_encoded_span(t, t_offset, rom(old_rom, TABLE_SIZE), creative)
        p[p_offset:p_offset+72] = weights
    result = bytearray(data)
    for tag, block in ((0x635, p), (0x636, t)):
        at = ip[tag]['offset']
        assert len(block) == ip[tag]['bytes']
        result[at:at+len(block)] = block
    assert len(result) == len(data)
    assert all(result[a:a+n] == data[a:a+n] for a, n in layout.strips)
    changed = [i for i, (a, b) in enumerate(zip(data, result)) if a != b]
    allowed = [(ip[tag]['offset'], ip[tag]['offset']+ip[tag]['bytes']) for tag in (0x635, 0x636)]
    assert all(any(a <= i < z for a, z in allowed) for i in changed)
    return bytes(result), dict(source_sha256=sha(data), output_sha256=sha(result),
        unequal_bytes=len(changed), raw_strips_unchanged=True, only_native_cmio_changed=True,
        hue=hue, saturation=saturation, lightness=lightness,
        weights=list(struct.unpack('<36h', weights)),
        semantics='Native Natural sRGB/AdobeRGB look; explicit Adjust Color replaces it.')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input', type=Path)
    ap.add_argument('--recipe', type=Path, required=True,
                    help='JSON with hue, saturation, lightness arrays (OES order/signs)')
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    recipe = json.loads(args.recipe.read_text())
    result, audit = bake(args.input.read_bytes(), **{k: recipe[k] for k in ('hue','saturation','lightness')})
    # Exclusive create: never overwrite either an original or a previous copy.
    with args.output.open('xb') as f:
        f.write(result)
    print(json.dumps(audit, indent=2))


if __name__ == '__main__':
    main()
