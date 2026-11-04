#!/usr/bin/env python3
"""Execute PEN-F ring selection, official-limit caching and aperture text.

Caller RAM, publication, status and zoom geometry are synthetic fixtures.
Original getters, cache producer, patched snapshot and formatter run natively.
No successful service stubs, camera task, transport, exposure solver or iris.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import struct

import penf_emulator as engine
from penf_boot_emulator import BootState

ROOT = Path(__file__).resolve().parents[1]
module = importlib.util.spec_from_file_location('aperture_ring_build', ROOT/'patches/aperture-ring/build.py')
patch = importlib.util.module_from_spec(module)
module.loader.exec_module(patch)

STACK, SP = 0x18010000, 0x18018000
CALLER = 0x18000000
DEVICE, CONFIG, INPUT, BODY = 0x22000000, 0x23000100, 0x23000200, 0x23000b00
TEXT = 0x24002000


class RingState(BootState):
    def __init__(self, image, spec, *, raw=0x187, effective=0x194,
                 minimum=0x188, maximum=0x800, mode=4, connected=True,
                 capabilities=0x80, body=0x300):
        self.cfg = cfg = spec['ae_probe']
        self.regions = [engine.Region('candidate_main', int(spec['cpu_base'], 16), image, 'rx'),
                        engine.Region('stack', STACK, bytes(0x10000), 'rw', True)]
        self.events, self.steps, self.cpu = [], 0, 0
        self.mode, self.body = mode, body
        lens = bytearray(0x500)
        struct.pack_into('<I', lens, int(cfg['capability_offset'], 16), capabilities)
        self.ram('lens', DEVICE, lens, aliases=False)
        self.ram('lens_pointer', int(cfg['device_pointer'], 16), struct.pack('<I', DEVICE))
        connection = bytes.fromhex(cfg['connected_initial'])
        self.ram('connection', int(cfg['connected'], 16), connection if connected else bytes(len(connection)))
        self.ram('bounds', int(cfg['bounds'], 16), struct.pack('<hhh', effective, minimum, maximum))
        self.ram('publication', int(spec['state_address'], 16),
                 struct.pack('<I', 0 if raw is None else 0x52470000 | (raw & 0xffff)))
        self.ram('cpu_number', int(cfg['cpu_number'], 16), bytes(4), aliases=False)
        self.ram('registry_bank', int(cfg['registry_bank'], 16), bytes(2))
        self.ram('ae_handle', int(cfg['ae_handle'], 16), bytes(4))
        key = int(cfg['aperture_point'], 16)
        self.ram('body_aperture', BODY, struct.pack('<h', body), aliases=False)
        self.ram('body_descriptor', int(cfg['registry_descriptors'], 16)+(key >> 4)*8,
                 struct.pack('<HHI', key, 1, BODY))
        configuration = bytearray(0x54)
        configuration[2] = mode
        self.ram('config', CONFIG, configuration, aliases=False)
        self.ram('snapshot_input', INPUT, bytes(16), aliases=False)
        self.ram('call_site', CALLER, bytes(8), aliases=False, executable=True)
        self.ram('formatted_text', TEXT, b'\xa5'*32, aliases=False)
        self.snapshot_context()

    def snapshot_context(self):
        cfg = self.cfg
        self.regs = dict(pc=int(cfg['entry'], 16), sp=SP, psw=0,
                         d2=0x12345678, d3=0x89abcdef)
        self.write(SP+cfg['config_stack_offset'], struct.pack('<I', CONFIG+cfg['config_pointer_offset']))
        self.write(SP+cfg['input_stack_offset'], struct.pack('<I', INPUT))

    def call(self, target, mask, frame, registers=None):
        self.write(CALLER, b'\xdd'+struct.pack('<i', target-CALLER)+bytes((mask, frame))+b'\xcb')
        self.regs = dict(pc=CALLER, sp=SP, psw=0, **(registers or {}))
        result = self.run({CALLER+7}, limit=20000)
        patch.require(result['status'] == 'breakpoint' and self.regs['pc'] == CALLER+7 and
                      self.regs['sp'] == SP, dict(status=result['status'], fault=result.get('fault')))

    def cache(self, effective, minimum, maximum, zoom=0):
        self.write(DEVICE+8, bytes((zoom,)))
        self.write(DEVICE+0x10, struct.pack('<h', effective))
        self.write(DEVICE+0x280+zoom*16,
                   struct.pack('<8h', 15, minimum, maximum, minimum, maximum, 0, 0, 0))
        self.write(int(self.cfg['bounds'], 16), b'\xa5'*6)
        self.call(0x6015a895, 0x20, 8)
        actual = self.read(int(self.cfg['bounds'], 16), 6)
        patch.require(actual == struct.pack('<hhh', effective, minimum, maximum), 'Native lens cache differs')

    def snapshot(self):
        self.snapshot_context()
        stop = int(self.cfg['stop'], 16)
        result = self.run({stop}, limit=20000)
        patch.require(result['status'] == 'breakpoint' and self.regs['pc'] == stop,
                      dict(status=result['status'], fault=result.get('fault')))
        patch.require(self.regs['sp'] == SP and self.regs['d2'] == 0x12345678 and
                      self.regs['d3'] == 0x89abcdef, 'Native saved-register/stack contract differs')
        patch.require(self.read(BODY, 2) == struct.pack('<h', self.body), 'Body setting changed')
        return struct.unpack('<h', self.read(INPUT+4, 2))[0]

    def text(self, value, minimum, step=0x55):
        self.write(TEXT, b'\xa5'*32)
        self.write(SP+4, struct.pack('<I', step))
        self.call(0x605c596d, 0xf0, 28,
                  dict(d0=value & 0xffffffff, d1=minimum & 0xffffffff,
                       a0=TEXT, a1=minimum & 0xffffffff))
        result = self.read(TEXT, 32)
        patch.require(b'\0' in result and result[-1] == 0xa5, 'Formatter buffer boundary differs')
        return result.split(b'\0', 1)[0].decode('ascii')


def experiment(model, build):
    spec = patch.load_spec(model)
    image = (Path(build)/'decoded-main.bin').read_bytes()
    patch.require(patch.sha(image) == spec['patched_main_sha256'], 'Probe requires exact compiled main')
    controls = [('wide open', dict(raw=0x187), 0x188),
                ('next ring position', dict(raw=0x1b2), 0x1b2),
                ('effective status below minimum', dict(effective=0x100), 0x188),
                ('effective status above maximum', dict(effective=0x900), 0x188),
                ('M mode', dict(mode=6, raw=0x200), 0x200),
                ('A/auto', dict(raw=0x8000), 0x300),
                ('no publication', dict(raw=None), 0x300),
                ('disconnected', dict(connected=False), 0x300),
                ('no ring capability', dict(capabilities=0), 0x300),
                ('reversed official bounds', dict(minimum=0x800, maximum=0x187), 0x300),
                ('signed lower bound', dict(raw=0xffff), 0x188),
                ('upper bound', dict(raw=0x7fff), 0x800)]
    controls += [('body mode '+str(mode), dict(mode=mode), 0x300) for mode in (0, 1, 2, 3, 5, 7)]
    rows = []
    for name, inputs, expected in controls:
        state = RingState(image, spec, **inputs)
        actual = state.snapshot()
        patch.require(actual == expected, 'Native snapshot differs: '+name)
        rows.append(dict(case=name, inputs=inputs, expected=expected, snapshot_av=actual,
                         instructions=state.steps, body_and_saved_registers_preserved=True))
    values = []
    for minimum in (-0x25, 0x88, 0xf9, 0x188, 0x2f8, 0x400):
        for zoom in (0, 5):
            for mode in (4, 6):
                state = RingState(image, spec, raw=(minimum-1) & 0xffff, mode=mode)
                state.cache(minimum+0xc, minimum, 0x800, zoom)
                actual = state.snapshot()
                patch.require(actual == minimum, 'Official zoom-dependent lower bound differs')
                values.append(dict(minimum=minimum, effective=minimum+0xc, zoom=zoom, mode=mode,
                                   snapshot_av=actual, native_cache_producer_executed=True))
    display = []
    for step in (0x55, 0x80, 0x100):
        state = RingState(image, spec)
        state.cache(0x194, 0x188, 0x800)
        actual = state.snapshot()
        fixed = state.text(actual, 0x188, step)
        previous = state.text(0x194, 0x188, step)
        patch.require(fixed == '1.7' and previous != fixed, 'Wide-open label regression')
        display.append(dict(step=step, old_effective_clamp_label=previous, official_limit_label=fixed))
    state = RingState(image, spec, raw=0x1b2)
    patch.require(state.text(state.snapshot(), 0x188) == '1.8', 'Second detent no longer shows f/1.8')
    return dict(scope=__doc__, model='PEN-F', profile=model, build=spec['build'],
                patched_main_sha256=patch.sha(image), engine_sha256=patch.sha(engine.ENGINE.read_bytes()),
                source_sha256=patch.sha(Path(__file__).read_bytes()), controls=rows,
                dynamic_limits=values, display=display, second_detent='1.8',
                hardware_models=[], camera_access=False,
                boundaries=dict(snapshot=spec['ae_probe']['entry'], stop_before=spec['ae_probe']['stop'],
                                cache='0x6015a895', formatter='0x605c596d'))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', choices=patch.MODELS, required=True)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--engine', type=Path)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    if args.engine:
        engine.ENGINE = args.engine.resolve()
    report = experiment(args.model, args.build)
    with args.out.open('x') as f:
        json.dump(report, f, indent=2)
        f.write('\n')
    print('PEN-F', args.model, len(report['controls']), 'snapshot controls,',
          len(report['dynamic_limits']), 'native cache cases and aperture display checks passed')


if __name__ == '__main__':
    main()
