#!/usr/bin/env python3
"""Bounded execution of azqeurio's PEN-F aperture-ring hooks, entirely offline.

Requires the original release EXE as a data source and the pinned stock main.
Models lens-object availability, the stock parameter getter and shooting modes;
executes packet reads, cache checks and the mode-selection shim natively.
Does not model lens electronics, task scheduling, aperture movement or boot.
"""
import argparse
import json
from pathlib import Path
import struct

from oly_release_inspect import EXE_SHA256, patch_records, patched_main, profiles_from_exe, require, sha
from penf_emulator import BASE, ENGINE, Region, firmware
from penf_probe import ProbeState

DESCRIPTOR = 0xA1000000
CACHE, POINTER, STATE_WORD = 0xA0060800, 0xA1C40090, 0xA1C492D0
PACKET, OUTPUT = 0x19000000, 0x19001000
GET, GET_ACTIVE = 0x60160FB1, 0x60160FDF
PARAM, MODE, CUSTOM = 0x600750EE, 0x602BA340, 0x605DEFF5
IDENTITY = b'ABCDEF'
STOCK_VALUE, RING_VALUE = 777, 456  # Raw native units, not f-numbers.
IMAGE = None


def state(entry, registers=None, capability=True, pointer=DESCRIPTOR, state_word=2):
    s = ProbeState(entry, 0, 0, bytes(16), registers or {})
    s.regions[0] = Region('ring_main', BASE, IMAGE, 'rx')
    s.regs['pc'] = entry  # Hook interior, not a function call.
    s.ram('ring_cache', CACHE, struct.pack('<HHI6sH', RING_VALUE, 0, 1, IDENTITY, state_word))
    s.ram('lens_pointer', POINTER, struct.pack('<I', pointer))
    descriptor = bytearray(0x8600)
    descriptor[0x23C] = 0x80 if capability else 0
    descriptor[0x240:0x246] = IDENTITY
    s.ram('lens_descriptor', DESCRIPTOR, descriptor)
    s.ram('lens_state_word', STATE_WORD, struct.pack('<H', state_word))
    s.ram('packet', PACKET, bytes(256), aliases=False)
    s.ram('output', OUTPUT, bytes(32), aliases=False)
    return s


def execute(s, stops, mode=4, custom=6, attached=True, active=True, stock=STOCK_VALUE):
    modeled = {GET, GET_ACTIVE, PARAM, MODE, CUSTOM}
    calls = []
    for _ in range(24):
        r = s.run(set(stops) | modeled, limit=2000)
        require(r['status'] == 'breakpoint', f'Unexpected execution stop: {r}')
        pc = s.regs['pc']
        if pc in stops:
            return calls
        calls.append(hex(pc))
        if pc in (GET, GET_ACTIVE):
            require(s.regs['d0'] == 0, 'Unexpected lens channel')
            s.regs['a0'] = DESCRIPTOR if (attached if pc == GET else active) else 0
            s.return_from_model(0)
        else:
            s.return_from_model({PARAM: stock, MODE: mode, CUSTOM: custom}[pc])
    raise ValueError('Too many service calls')


def input_case(label, expected_ring=False, **options):
    setup = {k: options.pop(k) for k in ('capability', 'pointer', 'state_word') if k in options}
    value = options.pop('value', RING_VALUE)
    valid = options.pop('valid', 1)
    identity = options.pop('identity', IDENTITY)
    cached_state = options.pop('cached_state', setup.get('state_word', 2))
    s = state(0x605DDB6C, dict(d0=0x80CA, d1=0, a0=0x19002000), **setup)
    s.write(CACHE, struct.pack('<HHI6sH', value, 0, valid, identity, cached_state))
    old_sp = s.regs['sp']
    calls = execute(s, {0x605DDB73}, **options)
    expected = (struct.unpack('<h', struct.pack('<H', value))[0] & 0xFFFFFFFF) if expected_ring else STOCK_VALUE
    require(s.regs['d0'] == expected, f'{label}: wrong aperture result')
    require(s.regs['sp'] == old_sp, f'{label}: stack changed')
    return dict(case=label, aperture_raw=s.regs['d0'], used_ring=expected_ring,
                cache_valid=struct.unpack('<I', s.read(CACHE + 4, 4))[0], calls=calls, steps=s.steps)


def request_case(entry, command, capability=True, state_word=2):
    dispatch = entry == 0x60175F48
    s = state(entry, dict(a0=PACKET, a1=OUTPUT, d0=0x1200),
              capability=capability, state_word=state_word)
    s.write(PACKET + 18, bytes(command))
    s.write(PACKET + 21, b'\x20')
    stops = {0x60175F51} if dispatch else {0x60173DDB}
    execute(s, stops)
    expected_enabled = capability and state_word == 2 and command in ((0xC1, 0x80), (0xC1, 0), (0x81, 0xE3))
    result = s.read(PACKET + 21, 1)[0] if dispatch else s.read(OUTPUT + 1, 1)[0]
    expected = (0x20 if dispatch else 0x12) | int(expected_enabled)
    require(result == expected, 'Wrong requested-field bit')
    require(s.regs['sp'] == 0x18018000, 'Request stack changed')
    return dict(entry=hex(entry), command=list(command), capability=capability,
                state_word=state_word, field_requested=expected_enabled, result=result, steps=s.steps)


def parser_case(channel, flags=1, state_word=2):
    s = state(0x6016527E, dict(a3=PACKET, d3=flags), state_word=state_word)
    s.write(PACKET, struct.pack('<H', 1234))
    s.write(s.regs['sp'] + 24, struct.pack('<I', channel))
    execute(s, {0x60165284})
    primary = channel in (0, 2, 6)
    expected_valid = int(flags & 1 != 0 and state_word == 2) if primary else 1
    value, _, valid, identity, cached_state = struct.unpack('<HHI6sH', s.read(CACHE, 16))
    require(valid == expected_valid, 'Wrong parser cache validity')
    require(value == (1234 if primary and flags & 1 and state_word == 2 else RING_VALUE), 'Wrong cached value')
    require(s.regs['a3'] == PACKET + (2 if flags & 1 else 0), 'Wrong parser cursor')
    require(s.regs['sp'] == 0x18018000 and s.regs['d3'] == flags, 'Parser context changed')
    return dict(channel=channel, flags=flags, state_word=state_word, value=value,
                valid=valid, consumed=s.regs['a3'] - PACKET, steps=s.steps)


def guard_case(entry, continuation, channel, flags, length):
    s = state(entry, dict(d0=PACKET + 64, d1=1, a0=flags, a1=channel, a2=PACKET))
    s.write(PACKET + 24, struct.pack('<H', length))
    # Two selector sites use the original stack argument instead of a2.
    s.write(s.regs['sp'] + 8, struct.pack('<I', PACKET))
    stops = {0x601651C7, continuation, 0x60173ECE}
    execute(s, stops)
    accepted = s.regs['pc'] == 0x601651C7
    expected_length = 14 + (2 if flags & 1 else 0) + (16 if flags & 2 else 0) + (4 if flags & 8 else 0)
    if channel == 6:
        expected_length += 2
    expected = length >= expected_length if channel in (0, 2, 6) else not flags & 1
    require(accepted == bool(expected), 'Guard decision differs')
    if not accepted:
        require(s.regs['d0' if entry != 0x60173E92 else 'd2'] == 0x6507, 'Wrong malformed-packet status')
        require(s.regs['sp'] == 0x18018000, 'Reject stack changed')
    return dict(entry=hex(entry), channel=channel, flags=flags, length=length,
                parser_called=accepted, stop=hex(s.regs['pc']), steps=s.steps)


def main():
    global IMAGE
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('release_exe', type=Path)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    profiles = profiles_from_exe(args.release_exe)
    p = next(p for p in profiles if p['id'] == 'penf-3.1')
    stock = firmware()
    IMAGE = patched_main(p, stock)
    require(sha(IMAGE) == 'fc70d367c734c1700ba757f0b5152c23416b25d6ec5233785554039074387a9d', 'Patched image differs')
    cases = [input_case('A mode', True, mode=2), input_case('M mode', True, mode=4),
             input_case('P mode', mode=1), input_case('S mode', mode=3),
             input_case('ring A sentinel', value=0x8000),
             input_case('signed native value', True, value=0xFFFF),
             input_case('ringless descriptor', capability=False),
             input_case('missing descriptor', pointer=0),
             input_case('misaligned descriptor', pointer=DESCRIPTOR + 1),
             input_case('descriptor outside RAM', pointer=0xFFFFFFFF),
             input_case('invalid cache', valid=0), input_case('changed identity', identity=b'ABCDEF'[::-1]),
             input_case('changed state', cached_state=10), input_case('state predicate false', state_word=0),
             input_case('special excluded state', state_word=0xB0A),
             input_case('no attached lens', attached=False), input_case('no active lens', active=False)]
    for mode in range(53, 57):
        for custom in (4, 6, 3):
            cases.append(input_case(f'C{mode-52}, underlying {custom}', custom in (4, 6), mode=mode, custom=custom))
    requests = [request_case(entry, command, capability, state_word)
                for entry in (0x60173DD5, 0x60175F48)
                for command in ((0xC1, 0x80), (0xC1, 0), (0x81, 0xE3), (0xC1, 1))
                for capability, state_word in ((True, 2), (False, 2), (True, 0))]
    parsers = [parser_case(channel, flags, word) for channel in (0, 2, 6, 1)
               for flags, word in ((1, 2), (0, 2), (1, 0))]
    guards = []
    for entry, continuation in ((0x60173E92, 0x60173E99), (0x60171CC3, 0x60171CCA),
                                (0x60174468, 0x6017446F), (0x60174DE5, 0x60174DEC),
                                (0x60174E4C, 0x60174E53)):
        for channel, flags, length in ((0, 1, 15), (0, 1, 16), (0, 0, 14),
                                        (2, 1, 16), (6, 1, 17), (6, 1, 18), (1, 1, 40)):
            guards.append(guard_case(entry, continuation, channel, flags, length))
    report = dict(release_asset_sha256=EXE_SHA256, stock_main_sha256=sha(stock),
                  patched_main_sha256=sha(IMAGE), engine_sha256=sha(ENGINE.read_bytes()),
                  sites=patch_records(p), case_count=len(cases)+len(requests)+len(parsers)+len(guards),
                  input=cases, requests=requests, parsers=parsers, guards=guards,
                  models=['Synthetic stack, lens descriptor, packet and cache RAM',
                          'Lens pointer availability; stock parameter result; shooting mode services'],
                  limits=['No lens, camera, boot, scheduler or live-view test',
                          'No absolute f-number calibration or capability-bit semantic proof',
                          'No validation of every packet variant or every error callback'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f'{report["case_count"]} bounded native cases passed; no camera access')


if __name__ == '__main__':
    main()
