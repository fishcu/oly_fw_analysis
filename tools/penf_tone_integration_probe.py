#!/usr/bin/env python3
"""Strict offline ordinary COLOR tone adapter and signal-anchor proof."""
if not __debug__:
    raise RuntimeError('Tone audit probes require assertions; optimized Python execution is unsupported')

import argparse
from dataclasses import dataclass, replace
import json
from itertools import product
import math
from pathlib import Path
import struct
import subprocess

from penf_emulator import BASE, ENGINE, ROOT, Region, firmware
from penf_hsl_context_probe import CACHE, LOCKS, reenter
from penf_probe import CALLER, ProbeState
from penf_tone_endpoints import TOOLCHAIN, ToneEndpoints, endpoint_oracle
from penf_tone_probe import (CONVERT, APPLY, GUARD, PRESERVED, INITIAL_SP, identity_lut,
                             _finish, _guarded, _check_guards, sha, source_hashes)

CODE = 0x19080000
JOB, OUTPUT, CONTEXT, DESCRIPTOR, LUT = (0x1a000020, 0x1a010020, 0x1a020020,
                                        0x1a030020, 0x1a040020)
REQUEST, RAW = JOB + 12228, JOB + 5568
COEFFICIENTS = CONTEXT + 60
TAG = 0xa5d00000
SOURCES = tuple(ROOT / 'patches/tone/pen-f/src' / name for name in
                ('signal_bounds.s', 'job_word.s', 'native_builder.s', 'endpoints.s'))


def packed(black, white):
    if any(type(v) is not int or not 0 <= v <= 1023 for v in (black, white)):
        raise ValueError('Endpoint coordinates must be 10-bit integers')
    return TAG | white << 10 | black


@dataclass(frozen=True)
class Adapter:
    code: bytes
    symbols: dict
    source_sha256: dict
    tool_sha256: dict


def build_adapter(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    tools = {name: TOOLCHAIN / path for name, path in
             (('assembler', 'gas/as-new'), ('linker', 'ld/ld-new'),
              ('objcopy', 'binutils/objcopy'), ('objdump', 'binutils/objdump'),
              ('nm', 'binutils/nm-new'))}
    objects = []
    for source in SOURCES:
        obj = out / (source.stem + '.o')
        subprocess.run([str(tools['assembler']), '-o', str(obj), str(source)],
                       check=True, capture_output=True)
        objects.append(str(obj))
    elf, raw = out / 'adapter.elf', out / 'adapter.bytes'
    subprocess.run([str(tools['linker']), '--no-relax', '-e', 'tone_native_builder',
                    f'--section-start=.text={CODE:#x}', '-o', str(elf), *objects,
                    '--defsym=stock_spline_coefficients=0x604bdea7',
                    '--defsym=stock_spline_evaluate=0x604bdfe1',
                    '--defsym=stock_tone_builder=0x604f7c76',
                    '--defsym=stock_tone_select=0x604f7c18',
                    '--defsym=stock_tone_gate=0x604bdd21',
                    '--defsym=stock_tone_apply=0x604be08d',
                    '--defsym=stock_tone_resume=0x604f85ef'],
                   check=True, capture_output=True)
    subprocess.run([str(tools['objcopy']), '-O', 'binary', '--only-section=.text',
                    str(elf), str(raw)], check=True, capture_output=True)
    (out / 'adapter.asm').write_text(subprocess.check_output(
        [str(tools['objdump']), '-d', str(elf)], text=True))
    symbols = {name: int(address, 16) for address, kind, name in
               (line.split() for line in subprocess.check_output(
                   [str(tools['nm']), '-n', str(elf)], text=True).splitlines())
               if kind.lower() == 't'}
    return Adapter(raw.read_bytes(), symbols,
                   {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in SOURCES},
                   {name: sha(path.read_bytes()) for name, path in tools.items()})


def prepare(curve, raw, *, endpoint_word=0, record=0, mode=11, custom=True,
            callback=0x604c4011, record_offset=None, parent=JOB, flags=2, variant=0, bypass=False, selection_stop=False, base_selection=0, mode_prefix=0):
    s = ProbeState(CONVERT, 0, 16, bytes(16),
                   dict(PRESERVED, a0=RAW, a1=COEFFICIENTS))
    job = bytearray(14948)
    struct.pack_into('<5h', job, 5568, *raw)
    struct.pack_into('<II', job, 12228, callback,
                     REQUEST + 1848 + 52 * record if record_offset is None else REQUEST + record_offset)
    struct.pack_into('<H', job, 12228 + 8, mode_prefix)
    struct.pack_into('<H', job, 12228 + 10, mode)
    struct.pack_into('<H', job, 12228 + 28, 0x200)
    if bypass:
        job[12228 + 1071] = 1
        struct.pack_into('<H', job, 12228 + 12, 0xa200)
    if selection_stop:
        struct.pack_into('<H', job, 12228 + 1092, 0x101)
    struct.pack_into('<I', job, 12228 + 948, RAW)
    struct.pack_into('<I', job, 12228 + 960, DESCRIPTOR if custom else 0)
    job[12228 + 1060] = base_selection & 255
    job[12228 + 1065] = variant << 7
    struct.pack_into('<I', job, 14076 + 52 * record, parent)
    struct.pack_into('<I', job, 14944, endpoint_word)
    context = bytearray(192)
    struct.pack_into('<I', context, 4, REQUEST)
    struct.pack_into('<I', context, 8, 0x1a060020)
    struct.pack_into('<I', context, 12, OUTPUT)
    struct.pack_into('<I', context, 56, flags)
    _guarded(s, 'job', JOB, bytes(job))
    _guarded(s, 'context', CONTEXT, bytes(context))
    _guarded(s, 'output', OUTPUT, bytes(5212))
    _guarded(s, 'flags', 0x1a060020, bytes(16))
    _guarded(s, 'descriptor', DESCRIPTOR, struct.pack('<3I', 0, 0, LUT))
    s.regions.append(Region('shared_base_lut', LUT - len(GUARD),
                           GUARD + struct.pack('<256H', *curve) + GUARD, 'r'))
    s.write(INITIAL_SP - 0x1000, GUARD)
    s.write(INITIAL_SP + 64, GUARD)
    _finish(s, s.run({CALLER + 7}, limit=100000))
    return s


def stock_signal(curve, raw):
    s = prepare(curve, raw)
    _guarded(s, 'stock_writable_lut', 0x1a050020, struct.pack('<256H', *curve))
    reenter(s, APPLY, 0xf0, 16,
            dict(PRESERVED, a0=0x1a050020, a1=COEFFICIENTS, d0=0))
    stop = s.run({0x604be107}, limit=100000)
    assert stop['status'] == 'breakpoint' and s.regs['pc'] == 0x604be107
    samples = struct.unpack('<27H', s.read(s.regs['sp'] + 68, 54))
    _finish(s, s.run({CALLER + 7}, limit=100000))
    knots = struct.unpack_from('<27H', firmware(), 0x605fa380 - BASE)
    shadow = next((knots[i - 1] for i in range(1, 27) if samples[i] >= 130), None)
    highlight = next((knots[i] for i in range(27) if samples[i] >= 832), None)
    if (samples[0] >= 130 or any(not 0 <= x <= 1023 for x in samples)
            or any(a > b for a, b in zip(samples, samples[1:]))
            or shadow is None or highlight is None or shadow >= highlight):
        return samples, None
    return samples, (shadow, highlight)


def run_builder(adapter, curve, raw, *, native=False, outer=False, **kwargs):
    s = prepare(curve, raw, **kwargs)
    before = {name: s.read(address, size) for name, address, size in
              (('job', JOB, 14948), ('context', CONTEXT, 192),
               ('descriptor', DESCRIPTOR, 12), ('base', LUT, 512))}
    s.regions.append(Region('tone_adapter', CODE, adapter.code, 'rx'))
    entry = 0x604f7c76 if native else adapter.symbols['tone_native_builder']
    if outer:
        from penf_diagnostic_lifetime_probe import helpers
        helpers(s)
        entry = 0x604f8543
        if not native:
            image = bytearray(firmware())
            hook = 0x604f85ea
            assert image[hook - BASE:hook - BASE + 5] == bytes.fromhex('cd8cf6f01c')
            image[hook - BASE:hook - BASE + 5] = b'\xdc' + struct.pack(
                '<i', adapter.symbols['tone_ordinary_call'] - hook)
            s.regions = [replace(r, data=bytes(image)) if r.name == 'main' else r for r in s.regions]
    reenter(s, entry, 0xf0, 40 if outer else 28, dict(PRESERVED, a0=CONTEXT))
    result = s.run({CALLER + 7}, limit=300000)
    checks = _finish(s, result)
    for name, address, size in (('job', JOB, 14948), ('context', CONTEXT, 192),
                                ('descriptor', DESCRIPTOR, 12), ('base', LUT, 512)):
        if not (outer and name == 'context'):
            assert s.read(address, size) == before[name], name
        _check_guards(s, address, size)
    _check_guards(s, OUTPUT, 5212)
    output = s.read(OUTPUT, 5212)
    pointer = struct.unpack_from('<I', output, 4656)[0]
    lut = struct.unpack('<256H', s.read(pointer, 512)) if pointer else None
    return dict(lut=lut, pointer=pointer, output=output, context=s.read(CONTEXT, 192),
                d0=s.regs['d0'], checks=checks, state=s)


def upload_result(result, bank):
    s = result['state']
    coefficient, table = ((0x9e001800, 0x9e00a400), (0x9e005800, 0x9e00cc00))[bank]
    s.write(CONTEXT + 52, struct.pack('<I', 17))
    s.write(CONTEXT + 100, bytes(4))
    s.write(CONTEXT + 189, bytes((bank,)))
    s.write(0x1a060020, struct.pack('<2I', 8 if bank == 0 else 0x10000, 0))
    s.ram('warm_tone_cache', CACHE, struct.pack('<2I', 17 if bank == 0 else 0, 17 if bank == 1 else 0))
    s.ram('coefficient_mmio', coefficient, b'\xa5' * 0x500, aliases=False)
    s.ram('tone_mmio', table, b'\xa5' * 0x2800, aliases=False)
    reenter(s, 0x604b4933, 0xf0, 24, dict(PRESERVED, a0=CONTEXT))
    modeled = []
    for _ in range(8):
        run = s.run({CALLER + 7} | set(LOCKS), limit=100000)
        pc = s.regs['pc']
        if run['status'] != 'breakpoint' or pc == CALLER + 7:
            break
        assert pc in LOCKS and s.regs['d0'] == 4
        modeled.append(hex(pc))
        s.return_from_model(0)
    checks = _finish(s, run)
    actual = s.read(table, 1024)
    assert actual == struct.pack('<256I', *result['lut'])
    assert modeled == ['0x604fa0ca', '0x604fa0ec']
    return dict(bank=bank, cache='same tag', dirty=0, checks=checks,
                lut_sha256=sha(actual), endpoints=list(result['lut'][::255]),
                modeled_functions=modeled)


def signal_case(adapter, curve, raw):
    samples, expected = stock_signal(curve, raw)
    s = prepare(curve, raw)
    s.regions.append(Region('tone_adapter', CODE, adapter.code, 'rx'))
    reenter(s, adapter.symbols['tone_signal_bounds'], 0xf0, 16,
            dict(PRESERVED, a0=LUT, a1=COEFFICIENTS))
    checks = _finish(s, s.run({CALLER + 7}, limit=100000))
    actual = (s.regs['d0'] & 255, s.regs['d0'] >> 8) if s.regs['d0'] else None
    assert actual == expected, (actual, expected, raw)
    assert s.read(LUT, 512) == struct.pack('<256H', *curve)
    return dict(raw=list(raw), samples=list(samples), bounds=actual, checks=checks)


def check_case(adapter, curve, raw, black, white, **kwargs):
    stock = run_builder(adapter, curve, raw, native=True, **kwargs)
    actual = run_builder(adapter, curve, raw, endpoint_word=packed(black, white), **kwargs)
    signal_curve = curve
    if not kwargs.get('custom', True):
        signal_curve = run_builder(adapter, curve, (0, 0, 0, 0, 0), native=True, **kwargs)['lut']
    _, bounds = stock_signal(signal_curve, raw) if signal_curve else (None, None)
    if bounds and stock['lut'] is not None:
        lo, hi = bounds
        endpoints = ToneEndpoints(min(black, stock['lut'][lo]), max(white, stock['lut'][hi]), lo, hi)
        expected = endpoint_oracle(stock['lut'], endpoints)
        assert actual['lut'] == expected, (raw, kwargs, actual['lut'], expected)
        assert actual['lut'][lo:hi + 1] == stock['lut'][lo:hi + 1]
        if (endpoints.black, endpoints.white) != (0, 1023):
            assert actual['pointer'] == OUTPUT + 4660
    else:
        assert actual['output'] == stock['output']
    assert actual['d0'] == stock['d0']
    return dict(raw=list(raw), black=black, white=white, bounds=bounds,
                source_pointer=hex(stock['pointer']), result_pointer=hex(actual['pointer']),
                endpoints=list(actual['lut'][::255]) if actual['lut'] else None,
                lut_sha256=sha(struct.pack('<256H', *actual['lut'])) if actual['lut'] else None,
                checks=actual['checks'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('--out must name a new directory')
    args.out.mkdir(parents=True, exist_ok=False)
    adapter = build_adapter(args.out / 'assembly')
    bases = {'identity': identity_lut(),
             'square': tuple(round(1023 * (i / 255) ** 2) for i in range(256)),
             'sqrt': tuple(round(1023 * math.sqrt(i / 255)) for i in range(256))}
    signals, cases, neutral = [], [], []
    for name, curve in bases.items():
        print('Checking source', name, flush=True)
        for first, second in product((-7, 0, 7), repeat=2):
            raw = (first, second, 4, -2, -3)
            signals.append(dict(base=name, **signal_case(adapter, curve, raw)))
            cases.append(dict(base=name, **check_case(adapter, curve, raw, 80, 940)))
    for inner in product((-7, 0, 7), repeat=3):
        cases.append(dict(base='identity', **check_case(adapter, bases['identity'], (0, 0, *inner), 1023, 0)))
    for record in range(16):
        cases.append(dict(base='identity', record=record, **check_case(
            adapter, bases['identity'], (0, 0, 0, 0, 0), 70, 950, record=record)))
    for raw in ((0, 0, 0, 0, 0), (0, 0, 4, -2, -3)):
        for options in ({'endpoint_word': 0}, {'endpoint_word': packed(0, 1023)},
                        {'endpoint_word': 0xffffffff}, {'endpoint_word': packed(50, 950), 'mode': 1},
                        {'endpoint_word': packed(50, 950), 'callback': 0},
                        {'endpoint_word': packed(50, 950), 'mode_prefix': 0x101},
                        {'endpoint_word': packed(50, 950), 'record_offset': 1849},
                        {'endpoint_word': packed(50, 950), 'record_offset': 1848 + 16 * 52},
                        {'endpoint_word': packed(50, 950), 'parent': JOB + 4}):
            stock = run_builder(adapter, bases['identity'], raw, native=True, **options)
            actual = run_builder(adapter, bases['identity'], raw, **options)
            assert actual['output'] == stock['output'] and actual['d0'] == stock['d0']
            neutral.append(dict(raw=list(raw), options=options, exact_native_output=True))
    extra = []
    for raw in ((0, 0, 0, 0, 0), (0, 0, 4, -2, -3)):
        extra.append(dict(native_selected=True, **check_case(adapter, bases['identity'], raw, 70, 950, custom=False)))
        extra.append(dict(variant=1, **check_case(adapter, bases['identity'], raw, 70, 950, variant=1)))
        extra.append(dict(outer=True, **check_case(adapter, bases['identity'], raw, 70, 950, outer=True)))
        for selection in (-1, 1):
            extra.append(dict(native_selected=selection, **check_case(
                adapter, bases['identity'], raw, 70, 950, custom=False, base_selection=selection)))
    for curve in (tuple([0] * 256), tuple([700] * 256), tuple([1023] * 256)):
        signals.append(dict(base='unsupported_flat', **signal_case(adapter, curve, (0, 0, 0, 0, 0))))
        actual = run_builder(adapter, curve, (0, 0, 0, 0, 0), endpoint_word=packed(70, 950))
        stock = run_builder(adapter, curve, (0, 0, 0, 0, 0), native=True)
        assert actual['output'] == stock['output'] and actual['d0'] == stock['d0']
    for options in ({'flags': 0}, {'selection_stop': True}):
        actual = run_builder(adapter, bases['identity'], (0, 0, 0, 0, 0), custom=False,
                             endpoint_word=packed(70, 950), **options)
        stock = run_builder(adapter, bases['identity'], (0, 0, 0, 0, 0), custom=False, native=True, **options)
        assert actual['output'] == stock['output'] and actual['d0'] == stock['d0']
    for options in ({'bypass': True}, {'mode': 1}, {'mode': 3}):
        actual = run_builder(adapter, bases['identity'], (0, 0, 4, -2, -3), outer=True,
                             endpoint_word=packed(70, 950), **options)
        stock = run_builder(adapter, bases['identity'], (0, 0, 4, -2, -3), outer=True, native=True, **options)
        assert actual['output'] == stock['output'] and actual['context'] == stock['context']
        neutral.append(dict(outer=True, options=options, exact_native_output=True))
    uploads = []
    for bank, black, white in ((0, 30, 970), (1, 60, 940), (0, 90, 920), (1, 0, 1023)):
        result = run_builder(adapter, bases['identity'], (0, 0, 4, -2, -3), outer=True,
                             endpoint_word=packed(black, white))
        uploads.append(upload_result(result, bank))
    report = dict(status='synthetic ordinary-builder integration; no placement or body UI',
                  adapter_bytes=len(adapter.code), symbols={k: hex(v) for k, v in adapter.symbols.items()},
                  sources=adapter.source_sha256, tools=adapter.tool_sha256,
                  engine_sha256=sha(ENGINE.read_bytes()), firmware_sha256=sha(firmware()),
                  execution_sources=dict(source_hashes(), integration_probe=sha(Path(__file__).read_bytes())),
                  signal_cases=signals, endpoint_cases=cases, neutral_cases=neutral, extra_cases=extra,
                  native_upload_cases=uploads, modeled_functions=[], limits='No installation image, camera I/O, owner acquisition, UI or physical ISP.')
    (args.out / 'audit.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(bytes=len(adapter.code), signals=len(signals), endpoints=len(cases),
                          neutral=len(neutral), report=str(args.out / 'audit.json'))))


if __name__ == '__main__':
    main()
