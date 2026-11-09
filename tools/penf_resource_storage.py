# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Bounded offline resource storage: exact package bytes and explicit gaps.

Unknown directories are write-only memory, not fabricated empty directories.
The lens directory alone uses an erased-data scenario with a native fallback.
"""
from dataclasses import replace
from functools import lru_cache
import hashlib

from oly_container import parse
from penf_emulator import ROOT

PACKAGE = 'firmware_files/OLY_E_122_3101_0000_0000.BIN'
PACKAGE_SHA256 = '77398610b379f80238117f31a6d5bbf65d608b49ec563666c64d84367e969f2c'
# Only these initial directory transfers can have unknown contents.
OPAQUE_READS = {
    (0x47560000, 0xa1c9d580, 1024): 'sound_directory',
    (0x44560000, 0xa1ca09a0, 4096): 'mode17_directory',
}
LENS_READ = (0x40240000, 0xa2d23c00, 1024)


@lru_cache(maxsize=1)
def resource_components():
    raw = (ROOT/PACKAGE).read_bytes()
    if hashlib.sha256(raw).hexdigest() != PACKAGE_SHA256:
        raise ValueError('Resource package build differs')
    blocks = parse(raw)  # Verifies every component checksum and header/trailer.
    return tuple((b.address, b.header+b.payload+b.trailer, b.kind)
                 for b in blocks if b.kind in (0x101, 0x102, 0x106))


def package_read(source, size):
    if size <= 0:
        raise ValueError('Resource read must be nonempty')
    for base, data, kind in resource_components():
        if base <= source < source+size <= base+len(data):
            offset = source-base
            return data[offset:offset+size], kind
    raise ValueError(f'Resource bytes are absent from the package: {source:#x}+{size:#x}')


def opaque_ram(state, name, address, size):
    """Isolate an exact RAM slice and its aliases, denying native CPU reads.

    Existing neighboring memory, capture flags and alias coherence survive.
    Later writes do not automatically establish initialized/readable contents.
    """
    cached = address-0x40000000 if 0xa0000000 <= address < 0xc0000000 else address
    end = cached+size
    if size <= 0 or not 0x60000000 <= cached < end <= 0x80000000:
        raise ValueError('Opaque resource slice is outside reviewed RAM')
    overlap = [r for r in state.regions if cached < r.address+len(r.data) and r.address < end]
    if not overlap:
        state.ram(name, cached, b'\xa5'*size)
        overlap = [r for r in state.regions if r.address == cached]
    if len(overlap) != 1:
        raise ValueError('Opaque slice crosses existing region boundaries')
    root = overlap[0]
    if (root.alias_of or not root.capture or root.permissions != 'rw' or
            not root.address <= cached < end <= root.address+len(root.data)):
        raise ValueError('Opaque slice lacks a writable, non-executable RAM owner')
    lo, hi = cached-root.address, end-root.address
    cuts = [(a, b) for a, b in ((0, lo), (lo, hi), (hi, len(root.data))) if a < b]
    rebuilt = []
    for region in state.regions:
        if region.name != root.name and region.alias_of != root.name:
            rebuilt.append(region)
            continue
        if region.data != root.data:
            raise ValueError('Opaque slice alias contents differ')
        for a, b in cuts:
            opaque = a == lo and b == hi
            suffix = f'__{name}_{a:x}'
            rebuilt.append(replace(region, name=region.name+suffix,
                address=region.address+a,
                data=b'\xa5'*(b-a) if opaque else region.data[a:b],
                permissions='w' if opaque else region.permissions,
                alias_of=root.name+suffix if region.alias_of else None))
    state.regions = rebuilt


def transfer(state, source, destination, size):
    request = (source, destination, size)
    if request in OPAQUE_READS:
        name = OPAQUE_READS[request]
        opaque_ram(state, name, destination, size)
        detail = dict(contents='unknown; native CPU reads denied', bank=name,
            assumption='Successful storage transfer of unavailable bytes. No contents or directory validity are asserted.')
    elif request == LENS_READ:
        state.ram('erased_lens_directory_scenario', destination, b'\xff'*size)
        detail = dict(contents='erased lens directory scenario',
            assumption='Unmeasured lens-directory contents; missing LENSDAT marker must take the native built-in fallback.')
    else:
        data, kind = package_read(source, size)
        state.ram(f'resource_read_{source:x}_{destination:x}', destination, data)
        detail = dict(contents='exact decoded official component including original header/trailer',
            component=hex(kind), sha256=hashlib.sha256(data).hexdigest(),
            assumption='Successful logical storage read; physical NAND/ECC/timing omitted.')
    state.events.append(dict(kind='model', name='reviewed resource storage transfer',
        cpu=state.cpu, source=hex(source), destination=hex(destination), bytes=size, **detail))
    return detail
