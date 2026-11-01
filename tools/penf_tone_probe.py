#!/usr/bin/env python3
"""Execute stock PEN-F tone routines offline, with opaque native input slots."""
if not __debug__:
    raise RuntimeError('Tone audit probes require assertions; optimized Python execution is unsupported')

import argparse
from dataclasses import dataclass
import hashlib
import json
from itertools import product
from pathlib import Path
import struct

from penf_emulator import BASE, ENGINE, ROOT, firmware
from penf_hsl_context_probe import reenter
from penf_probe import CALLER, ProbeState

GATE = 0x604bdd21
CONVERT = 0x604bddcc
APPLY = 0x604be08d
IDENTITY = 0x605fdd38
RAW = 0x19010020
COEFFICIENTS = 0x19020020
LUT = 0x19030020
GUARD = bytes.fromhex('a55ac33c') * 8
PRESERVED = dict(d2=0x22334455, d3=0x66778899, a2=0x11223344, a3=0x55667788)
INITIAL_SP = 0x18018000
MAIN_SHA256 = 'a2eb1d1f1afe47cce148e9aae0a04dfb82547d9de9437d342e012341140913f4'
LIMITS = ('Isolated stock native calls with synthetic RAM and caller. No modeled '
          'functions, UI, settings storage, per-image ownership, capture, ISP pixels, '
          'or hardware qualification. Raw slot stress inputs are not established UI settings.')


def sha(data):
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class NativeToneParameters:
    slots: tuple[int, int, int, int, int] = (0, 0, 0, 0, 0)

    def __post_init__(self):
        if (type(self.slots) is not tuple or len(self.slots) != 5 or
                any(type(x) is not int or not -32768 <= x <= 32767 for x in self.slots)):
            raise ValueError('Native tone parameters require five signed 16-bit integer slots')

    def pack(self):
        return struct.pack('<5h', *self.slots)


@dataclass(frozen=True)
class NativeToneResult:
    parameters: NativeToneParameters
    coefficients: bytes
    lut: tuple[int, ...]
    stages: tuple[dict, ...]

    def report(self):
        return dict(slots=list(self.parameters.slots), coefficients_hex=self.coefficients.hex(),
                    lut=list(self.lut), lut_sha256=sha(struct.pack('<256H', *self.lut)),
                    stages=list(self.stages))


def identity_lut():
    image = firmware()
    if sha(image) != MAIN_SHA256:
        raise ValueError('Tone probe requires the exact stock PEN-F 3101 main image')
    return struct.unpack_from('<256H', image, IDENTITY - BASE)


def _guarded(state, name, address, data):
    state.ram(name, address - len(GUARD), GUARD + data + GUARD, aliases=False)


def _check_guards(state, address, size):
    assert state.read(address - len(GUARD), len(GUARD)) == GUARD
    assert state.read(address + size, len(GUARD)) == GUARD


def _finish(state, result):
    assert result['status'] == 'breakpoint' and state.regs['pc'] == CALLER + 7, (
        result['status'], result.get('fault'), hex(state.regs['pc']))
    assert state.regs['sp'] == INITIAL_SP
    assert all(state.regs[name] == value for name, value in PRESERVED.items())
    assert state.read(INITIAL_SP - 0x1000, len(GUARD)) == GUARD
    assert state.read(INITIAL_SP + 64, len(GUARD)) == GUARD
    return dict(entry=hex(result['inputs']['registers']['pc']),
                instructions=result['completed'], returned=True, stack_restored=True,
                preserved_registers=True, stack_canaries=True)


def native_gate(parameters=NativeToneParameters()):
    """Run the stock all-zero gate, without inferring activity from host math."""
    raw = parameters.pack()
    state = ProbeState(GATE, 0, 0, bytes(16), dict(PRESERVED, a0=RAW))
    _guarded(state, 'tone_raw', RAW, raw)
    state.write(INITIAL_SP - 0x1000, GUARD)
    state.write(INITIAL_SP + 64, GUARD)
    result = state.run({CALLER + 7}, limit=100)
    report = _finish(state, result)
    assert state.regs['d0'] in (0, 1)
    assert state.read(RAW, 10) == raw
    _check_guards(state, RAW, 10)
    report.update(entry=hex(GATE), buffer_canaries=True, inputs_immutable=True,
                  modeled_functions=[])
    return bool(state.regs['d0']), report


def native_tone(parameters=NativeToneParameters()):
    """Convert ten native input bytes, then apply them to the stock identity LUT."""
    base = identity_lut()
    raw = parameters.pack()
    state = ProbeState(CONVERT, 0, 16, bytes(16),
                       dict(PRESERVED, a0=RAW, a1=COEFFICIENTS))
    _guarded(state, 'tone_raw', RAW, raw)
    _guarded(state, 'tone_coefficients', COEFFICIENTS, b'\x6d' * 16)
    _guarded(state, 'tone_lut', LUT, struct.pack('<256H', *base))
    state.write(INITIAL_SP - 0x1000, GUARD)
    state.write(INITIAL_SP + 64, GUARD)
    result = state.run({CALLER + 7}, limit=200000)
    converted = _finish(state, result)
    converted['entry'] = hex(CONVERT)
    coefficients = state.read(COEFFICIENTS, 16)
    assert state.read(RAW, 10) == raw
    assert state.read(LUT, 512) == struct.pack('<256H', *base)
    for address, size in ((RAW, 10), (COEFFICIENTS, 16), (LUT, 512)):
        _check_guards(state, address, size)
    reenter(state, APPLY, 0xf0, 16, dict(PRESERVED, a0=LUT, a1=COEFFICIENTS, d0=0))
    result = state.run({CALLER + 7}, limit=200000)
    applied = _finish(state, result)
    applied['entry'] = hex(APPLY)
    assert state.read(RAW, 10) == raw
    assert state.read(COEFFICIENTS, 16) == coefficients
    for address, size in ((RAW, 10), (COEFFICIENTS, 16), (LUT, 512)):
        _check_guards(state, address, size)
    for stage in (converted, applied):
        stage.update(buffer_canaries=True, inputs_immutable=True, modeled_functions=[])
    return NativeToneResult(parameters, coefficients,
                            struct.unpack('<256H', state.read(LUT, 512)),
                            (converted, applied))


def source_hashes():
    paths = ['tools/penf_tone_probe.py', 'tools/penf_probe.py',
             'tools/penf_hsl_context_probe.py', 'tools/penf_boot_emulator.py',
             'tools/penf_emulator.py', 'tools/penf_landmarks.py',
             'tools/mn103_runner.c', 'tools/mn103_strict.patch']
    for name in ('interp.c', 'mn10300.igen', 'op_utils.c', 'sim-main.c',
                 'sim-main.h', 'mn10300-sim.h'):
        relative = 'toolchains/mn103-gnu-src/sim/mn10300/' + name
        if (ROOT / relative).is_file():
            paths.append(relative)
    return {name: sha((ROOT / name).read_bytes()) for name in paths}


def baseline_report():
    cases = [native_tone()]
    for slot in range(5):
        for value in (-7, 7):
            slots = [0] * 5
            slots[slot] = value
            cases.append(native_tone(NativeToneParameters(tuple(slots))))
    base = identity_lut()
    neutral_changes = [dict(index=i, base=x, forced_overlay=y)
                       for i, (x, y) in enumerate(zip(base, cases[0].lut)) if x != y]
    assert all(case.lut[0] == 0 and case.lut[-1] == 1023 for case in cases)
    mixed = [native_tone(NativeToneParameters((0, 0, *slots)))
             for slots in product((-7, 0, 7), repeat=3)]
    gates = [native_gate(case.parameters) for case in cases]
    assert all(case.lut[0] == 0 and case.lut[-1] == 1023 for case in mixed)
    mixed_gates = [native_gate(case.parameters) for case in mixed]
    assert [active for active, _ in gates] == [False] + [True] * 10
    return dict(status='native baseline only; body feature not integrated',
                firmware_sha256=sha(firmware()), engine_sha256=sha(ENGINE.read_bytes()),
                source_sha256=source_hashes(), identity_address=hex(IDENTITY),
                identity_lut=list(base), identity_sha256=sha(struct.pack('<256H', *base)),
                forced_neutral_overlay_changes=neutral_changes,
                stock_neutral_gate='0x604bdd21 skips overlay for five zero slots',
                cases=[dict(case.report(), gate_active=active, gate_stage=gate,
                            stock_lut=list(case.lut if active else base))
                       for case, (active, gate) in zip(cases, gates)],
                mixed_cases=[dict(case.report(), gate_active=active, gate_stage=gate,
                                  stock_lut=list(case.lut if active else base))
                             for case, (active, gate) in zip(mixed, mixed_gates)], limits=LIMITS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path, help='New report directory')
    args = parser.parse_args()
    if args.out.exists():
        parser.error('--out must name a new directory')
    report = baseline_report()
    args.out.mkdir(parents=True, exist_ok=False)
    path = args.out / 'audit.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(report=str(path), native_cases=len(report['cases']) + len(report['mixed_cases']),
                          forced_neutral_differences=len(report['forced_neutral_overlay_changes']),
                          endpoints_fixed=True,
                          status=report['status'])))


if __name__ == '__main__':
    main()
