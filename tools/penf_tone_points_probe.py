"""Execute the shared five-point core against the integer state specification."""
import argparse
import json
from pathlib import Path
import random
import struct

from penf_emulator import ROOT, Region
from penf_tone_candidate import assemble, extract, symbols
from penf_probe import ProbeState, CALLER
from penf_tone_probe import PRESERVED, INITIAL_SP, GUARD, _guarded, _check_guards, _finish
from penf_tone_points import FivePoints, decode, resolve, LEGACY_NEUTRAL

CODE, LUT, RAW, HEIGHTS = 0x19080000, 0x19010020, 0x19020020, 0x19030020


def build_core(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    layout = folder/'core.ld'
    layout.write_text(f'SECTIONS {{ .text {CODE:#x} : {{ *(.text) }} }}\n')
    elf = assemble(folder/'assembly', [ROOT/'patches/tone/pen-f/src/points.s'], layout)
    return extract(elf, 'text'), symbols(elf)


def run(core, entry, *, word=0, raw=(0, 0, 0), curve=tuple(range(256)), axis=0, command=0):
    code, names = core
    registers = dict(PRESERVED, d0=word)
    registers.update(dict(a0=RAW, a1=HEIGHTS) if entry == 'tone_resolve' else
                     dict(a0=HEIGHTS) if entry == 'tone_decode' else
                     dict(a0=axis, d1=command & 0xffffffff) if entry == 'tone_edit' else dict(a0=LUT))
    state = ProbeState(names[entry], 0xf0, 16, bytes(16), registers)
    state.regions.append(Region('shared_five_point_core', CODE, code, 'rx'))
    _guarded(state, 'raw_hml', RAW, struct.pack('<3h', *raw))
    _guarded(state, 'heights', HEIGHTS, bytes(10))
    _guarded(state, 'lut', LUT, struct.pack('<256H', *curve))
    state.write(INITIAL_SP - 0x1000, GUARD)
    state.write(INITIAL_SP + 64, GUARD)
    checks = _finish(state, state.run({CALLER + 7}, limit=100000))
    for address, size in ((RAW, 6), (HEIGHTS, 10), (LUT, 512)):
        _check_guards(state, address, size)
    assert state.read(RAW, 6) == struct.pack('<3h', *raw)
    return state, checks


def states():
    result = [FivePoints(), FivePoints((0, 0, 288, 288, 288)),
              FivePoints((736, 736, 736, 1023, 1023))]
    rng = random.Random(103)
    for middle in range(15):
        m = 288 + 32 * middle
        for _ in range(3):
            s = rng.randrange(m // 16 + 1)
            b = rng.randrange(s + 1)
            h = rng.randrange(m // 16, 64)
            w = rng.randrange(h, 64)
            result.append(FivePoints(tuple(1023 if q == 63 else q * 16
                for q in (b, s, m // 16, h, w))))
    return result


def core_cases(core):
    rows = []
    for points in states():
        word = points.pack()
        state, checks = run(core, 'tone_decode', word=word)
        assert state.regs['d0'] == word
        assert struct.unpack('<5H', state.read(HEIGHTS, 10)) == points.heights
        for axis in range(5):
            for command in (-1, 0, 1):
                expected = points.edit(axis, command)
                state, checks = run(core, 'tone_edit', word=word, axis=axis, command=command)
                assert state.regs['d0'] == expected.pack(), (points, axis, command, hex(state.regs['d0']), expected)
                assert all(a == b for i, (a, b) in enumerate(zip(points.heights, expected.heights)) if i != axis)
        for offset in range(0, 1024, 256):
            curve = tuple(range(offset, offset + 256))
            state, checks = run(core, 'tone_apply', word=word, curve=curve)
            actual = struct.unpack('<256H', state.read(LUT, 512))
            assert actual == points.apply(curve), (points, offset)
            assert all(a <= b for a, b in zip(actual, actual[1:]))
            if points == FivePoints():
                assert actual == curve
        rows.append(dict(heights=points.heights, word=hex(word), models=[]))
    return rows


def migration_cases(core):
    rows = []
    words = (0, 0xffffffff, LEGACY_NEUTRAL, 0xbfffffff, 0xb000003f,
             *(0xa5d00000 | w << 10 | b for b, w in
               ((8, 1015), (9, 1008), (1000, 1007), (1007, 1008), (1008, 992), (1023, 0))))
    for word in words:
        for raw in ((0, 0, 0), (7, -7, 7), (-7, 7, -7), (8, 0, 0)):
            expected = resolve(word, raw)
            state, checks = run(core, 'tone_resolve', word=word, raw=raw)
            assert state.regs['d0'] == expected.pack(), (hex(word), raw, hex(state.regs['d0']), expected)
            assert struct.unpack('<5H', state.read(HEIGHTS, 10)) == expected.heights
            rows.append(dict(word=hex(word), raw=raw, heights=expected.heights, checks=checks))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    core = build_core(args.out/'core')
    report = dict(bytes=len(core[0]), states=core_cases(core), migration=migration_cases(core))
    (args.out/'audit.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(bytes=report['bytes'], states=len(report['states']), migration=len(report['migration']))))


if __name__ == '__main__':
    main()
