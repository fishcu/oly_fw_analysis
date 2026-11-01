#!/usr/bin/env python3
"""Probe-only native endpoint kernel. Anchors are explicit, never inferred UI points."""
if not __debug__:
    raise RuntimeError('Tone audit probes require assertions; optimized Python execution is unsupported')

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import struct
import subprocess

from penf_emulator import ENGINE, ROOT, Region, firmware
from penf_probe import CALLER, ProbeState
from penf_tone_probe import (GUARD, INITIAL_SP, PRESERVED, _check_guards,
                             _finish, _guarded, identity_lut, sha, source_hashes)

SOURCE = ROOT / 'patches/tone/pen-f/src/endpoints.s'
TOOLCHAIN = ROOT / 'toolchains/tone-binutils-build'
KERNEL_ADDRESS = 0x19080000
LUT_ADDRESS = 0x19030020
PARAMETER_ADDRESS = 0x19040020


@dataclass(frozen=True)
class ToneEndpoints:
    black: int
    white: int
    shadow_index: int
    highlight_index: int

    def validate(self, curve):
        if (len(curve) != 256 or any(type(x) is not int or not 0 <= x <= 1023 for x in curve)
                or curve[0] != 0 or curve[-1] != 1023
                or any(a > b for a, b in zip(curve, curve[1:]))):
            raise ValueError('Source must be a monotone 256-entry 10-bit LUT with endpoints 0 and 1023')
        if (any(type(x) is not int for x in (self.black, self.white,
                                            self.shadow_index, self.highlight_index))
                or not 0 <= self.shadow_index < self.highlight_index < 256):
            raise ValueError('Explicit anchor indices must satisfy 0 <= shadow < highlight < 256')
        if not 0 <= self.black <= curve[self.shadow_index]:
            raise ValueError('Black endpoint must lie between 0 and the shadow anchor height')
        if not curve[self.highlight_index] <= self.white <= 1023:
            raise ValueError('White endpoint must lie between the highlight anchor height and 1023')

    def pack(self):
        return struct.pack('<4H', self.black, self.white, self.shadow_index, self.highlight_index)


def endpoint_oracle(curve, endpoints):
    """Independent integer specification with nearest rounding and ties upward."""
    endpoints.validate(curve)
    if endpoints.black == 0 and endpoints.white == 1023:
        return tuple(curve)
    result = list(curve)
    shadow = curve[endpoints.shadow_index]
    highlight = curve[endpoints.highlight_index]
    if shadow:
        for i in range(endpoints.shadow_index):
            numerator = curve[i] * (shadow - endpoints.black)
            result[i] = endpoints.black + (2 * numerator + shadow) // (2 * shadow)
    if highlight < 1023:
        for i in range(endpoints.highlight_index + 1, 256):
            numerator = (curve[i] - highlight) * (endpoints.white - highlight)
            denominator = 1023 - highlight
            result[i] = highlight + (2 * numerator + denominator) // (2 * denominator)
    return tuple(result)


@dataclass(frozen=True)
class EndpointKernel:
    code: bytes
    source_sha256: str
    tool_sha256: dict


def build_kernel(out):
    """Assemble and link at a synthetic probe address. Emit no firmware image."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    tools = dict(assembler=TOOLCHAIN / 'gas/as-new', linker=TOOLCHAIN / 'ld/ld-new',
                 objcopy=TOOLCHAIN / 'binutils/objcopy', objdump=TOOLCHAIN / 'binutils/objdump')
    obj, elf, raw = (out / name for name in ('endpoints.o', 'endpoints.elf', 'endpoints.bytes'))
    subprocess.run([str(tools['assembler']), '-o', str(obj), str(SOURCE)], check=True, capture_output=True)
    subprocess.run([str(tools['linker']), '--no-relax', '-e', 'tone_endpoints',
                    f'--section-start=.text={KERNEL_ADDRESS:#x}', '-o', str(elf), str(obj)],
                   check=True, capture_output=True)
    subprocess.run([str(tools['objcopy']), '-O', 'binary', '--only-section=.text',
                    str(elf), str(raw)], check=True, capture_output=True)
    assembly = subprocess.check_output([str(tools['objdump']), '-d', str(elf)], text=True)
    (out / 'endpoints.asm').write_text(assembly)
    return EndpointKernel(raw.read_bytes(), sha(SOURCE.read_bytes()),
                          {name: sha(path.read_bytes()) for name, path in tools.items()})


def native_endpoints(curve, endpoints, kernel):
    """Validate at the host boundary, then execute an in-place native LUT edit."""
    endpoints.validate(curve)
    before = struct.pack('<256H', *curve)
    packed = endpoints.pack()
    state = ProbeState(KERNEL_ADDRESS, 0xf0, 16, bytes(16),
                       dict(PRESERVED, a0=LUT_ADDRESS, a1=PARAMETER_ADDRESS))
    state.regions.append(Region('endpoint_kernel', KERNEL_ADDRESS, kernel.code, 'rx'))
    _guarded(state, 'endpoint_lut', LUT_ADDRESS, before)
    _guarded(state, 'endpoint_parameters', PARAMETER_ADDRESS, packed)
    state.write(INITIAL_SP - 0x1000, GUARD)
    state.write(INITIAL_SP + 64, GUARD)
    result = state.run({CALLER + 7}, limit=20000)
    report = _finish(state, result)
    _check_guards(state, LUT_ADDRESS, 512)
    _check_guards(state, PARAMETER_ADDRESS, 8)
    assert state.read(PARAMETER_ADDRESS, 8) == packed
    assert state.regs['d0'] == 0
    actual = struct.unpack('<256H', state.read(LUT_ADDRESS, 512))
    assert actual[endpoints.shadow_index:endpoints.highlight_index + 1] == tuple(
        curve[endpoints.shadow_index:endpoints.highlight_index + 1])
    assert (actual[0], actual[-1]) == (endpoints.black, endpoints.white)
    assert all(0 <= x <= 1023 for x in actual)
    assert all(a <= b for a, b in zip(actual, actual[1:]))
    report.update(entry=hex(KERNEL_ADDRESS), buffer_canaries=True, parameters_immutable=True,
                  inner_samples_unchanged=True, monotone=True, modeled_functions=[],
                  instructions=result['completed'], lut_sha256=sha(struct.pack('<256H', *actual)))
    return actual, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path, help='New report directory')
    parser.add_argument('--black', required=True, type=int)
    parser.add_argument('--white', required=True, type=int)
    parser.add_argument('--shadow-index', required=True, type=int,
                        help='Explicit synthetic test anchor, not a verified native UI point')
    parser.add_argument('--highlight-index', required=True, type=int,
                        help='Explicit synthetic test anchor, not a verified native UI point')
    args = parser.parse_args()
    endpoints = ToneEndpoints(args.black, args.white, args.shadow_index, args.highlight_index)
    curve = identity_lut()
    endpoints.validate(curve)
    if args.out.exists():
        parser.error('--out must name a new directory')
    args.out.mkdir(parents=True, exist_ok=False)
    kernel = build_kernel(args.out / 'kernel')
    actual, report = native_endpoints(curve, endpoints, kernel)
    assert actual == endpoint_oracle(curve, endpoints)
    audit = dict(status='probe-only endpoint kernel; body feature not integrated',
                 synthetic_address=hex(KERNEL_ADDRESS), anchors='explicit synthetic test anchors',
                 parameters=vars(endpoints), source_lut=list(curve), actual_lut=list(actual),
                 native_checks=report, firmware_sha256=sha(firmware()),
                 engine_sha256=sha(ENGINE.read_bytes()), kernel_sha256=sha(kernel.code),
                 assembly_source_sha256=kernel.source_sha256, tool_sha256=kernel.tool_sha256,
                 execution_source_sha256=dict(source_hashes(),
                     endpoint_probe=sha(Path(__file__).read_bytes())),
                 limits='No firmware placement, UI, storage, capture ownership, ISP pixels, or camera I/O.')
    path = args.out / 'audit.json'
    path.write_text(json.dumps(audit, indent=2) + '\n')
    print(json.dumps(dict(report=str(path), matched_oracle=True, **report)))


if __name__ == '__main__':
    main()
