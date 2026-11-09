# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Bounded extension of the hypothetical Alex peer through its bootstrap upload.

No device I/O or auxiliary CPU emulation. DMA consumes only three pinned native
blocks; completion/status and serial replies are explicit hardware hypotheses.
Native setup, checksums, comparisons, callbacks and retry branches still execute.
"""
from dataclasses import replace
import hashlib
import struct

from penf_alex_model import AlexPeer
from penf_emulator import BASE, firmware

BLOCKS = ((0x60042c00, 97472), (0x6005b0c0, 2048), (0x6005a8c0, 2048))
FRAMING = (
    ('e3400100a0', 'e4c07c01a0', 'e1112100a0'),
    ('e300a03fa0', 'e4000800a0', 'e1112200a0'),
    ('e300903fa0', 'e4000800a0', 'e1112300a0'),
)
FINAL = tuple((bytes.fromhex(tx), bytes.fromhex(rx)) for tx, rx in (
    ('e5400100a0', '20e5000000'), ('65000000a0', '2065400100'),
    ('e2000000a0', '20e2000000')))


class AlexBulkPeer(AlexPeer):
    landmarks = {0x600272d8:'CPU1 stores Alex result',
                 0x600272f6:'CPU1 publishes Alex completion',
                 0x601c927a:'USTART3 application/input initialization',
                 0x60315edd:'display service initialization',
                 0x601a7250:'USTART1 requests DISPLAY task start',
                 0x603160f8:'DISPLAY task entry'}
    reads = {0x6007d06e:0x9bf00044, 0x6007d0da:0x9bf00000,
             0x6007d0ec:0x9bf00030, 0x6007d10a:0x9bf00030,
             0x6007d11a:0x9bf00044, 0x6007d12a:0x9bf00044,
             0x6007d133:0x9bf00000, 0x6007d14e:0x9bf00000,
             0x6007d160:0x9bf00000, 0x6007d16c:0x9bf00000}
    hooks = AlexPeer.hooks | set(reads) | set(landmarks) | {0x6007cf6e, 0x6007d113,
              0x6007d1a8, 0x6007d1ad, 0x6007cc18, 0x6007cc1d,
              0x6007cca0, 0x6007c7ce, 0x60198e64}

    def __init__(self, scenario='bulk', stop_after='next', low_memory_word=None):
        if scenario not in ('bulk', 'bad-checksum'):
            raise ValueError('Unknown bulk scenario')
        super().__init__('startup')
        self.bulk_scenario = scenario
        self.stop_after = stop_after
        self.stage = None
        self.phase = 0
        self.final_phase = None
        self.uploads = []
        self.stages = []
        self.active_upload = None
        if low_memory_word not in (None, 0, 1):
            raise ValueError('Only two explicitly bounded low-memory hypotheses are supported')
        self.low_memory_word = low_memory_word

    def summary(self):
        return dict(**super().summary(), bulk_scenario=self.bulk_scenario,
                    uploads=self.uploads, stages=self.stages, final_phase=self.final_phase,
                    low_memory_word=self.low_memory_word)

    def reg(self, state, address):
        return struct.unpack('<I', state.read(address, 4))[0]

    def observed_read(self, state, hooks, address, value):
        old = next(r for r in state.regions if r.address == address and len(r.data) == 4)
        state.register(address, 'rw', value)
        self.event(state, 'alex bulk register response', address=hex(address), value=hex(value))
        try:
            return self.step(state, hooks)
        finally:
            state.regions = [replace(r, data=old.data, permissions=old.permissions)
                             if r.address == address else r for r in state.regions]

    def command_reply(self, state, tx):
        if self.final_phase is not None:
            if self.final_phase >= len(FINAL) or tx != FINAL[self.final_phase][0]:
                raise ValueError('Unreviewed final Alex command')
            reply = FINAL[self.final_phase][1]
            self.final_phase += 1
            return reply
        if self.phase < 3:
            if tx.hex() != FRAMING[self.stage][self.phase]:
                raise ValueError(('Unreviewed Alex block framing', self.stage, self.phase, tx.hex()))
            reply = bytes((0x20, tx[0], 0, 0, 0))
        else:
            if self.phase not in (3, 4) or tx != bytes((0x66+self.phase-3, 0, 0, 0, 0xa0)):
                raise ValueError('Unreviewed Alex checksum command')
            upload = self.uploads[-1]
            assert upload['stage'] == self.stage and upload['completed']
            value = upload['sum_be32'] >> (16*(self.phase-3))
            reply = bytes((0x20, tx[0], value & 255, (value >> 8) & 255, 0))
        self.phase += 1
        return reply

    def handle(self, state, hooks, interrupts):
        pc = state.regs['pc']
        if pc in self.landmarks:
            state.events.append(dict(kind='milestone', name=self.landmarks[pc],
                                     entry=hex(pc), cpu=state.cpu, instructions=state.steps))
            return self.step(state, hooks)
        if pc == 0x60198e64:
            self.event(state, 'native key-state query observed', key=hex(state.regs['d0']),
                       caller_return=hex(state.regs['mdr']))
            return self.step(state, hooks)
        if pc == 0x6007ca4b:
            self.stage = state.regs['d0']
            if self.stage not in range(3) or self.stage != len(self.stages):
                return self.stop(state, 'Unreviewed Alex bulk stage order', stage=self.stage)
            self.phase = 0
            self.event(state, 'native Alex bulk stage entered', stage=self.stage)
            return self.step(state, hooks)
        if pc == 0x6007cca4 and (self.stage is not None or self.final_phase is not None):
            tx = state.read(state.regs['a0'], state.regs['d1'] & 0xffff)
            assert state.regs['d0'] == 1 and len(tx) == 5
            rx = self.command_reply(state, tx)
            expected = self.reg(state, state.regs['sp']+60)
            assert state.read(expected, 5) == rx, ('Native checksum/framing differs', tx.hex())
            self.command = (tx, rx)
            self.transactions.append(dict(tx=tx.hex(), expected=rx.hex(), attempts=[], result=None))
            self.event(state, 'alex command entered', tx=tx.hex(), expected=rx.hex(),
                       assumption='Hypothetical peer; checksum independently computed from submitted block')
            return self.step(state, hooks)
        if pc in (0x6008b1f5, 0x6008b1fa) and self.bulk_scenario == 'bad-checksum' and self.command and self.command[0][0] == 0x66:
            index = self.index
            accepted = super().handle(state, hooks, interrupts)
            if accepted and index == 2:
                self.fifo[-1] ^= 1
                self.event(state, 'deliberately incorrect Alex checksum reply byte', index=index)
            return accepted
        if pc == 0x6007cf6e:
            address, size = BLOCKS[self.stage]
            assert state.regs['a0'] == address+0x40000000 and state.regs['d0'] == size
            self.active_upload = None
            for offset in (0, 4, 8, 0x0c, 0x30, 0x34, 0x38, 0x3c, 0x40, 0x44, 0x50, 0x54, 0x58):
                state.register(0x9bf00000+offset, 'w')
            for address in (0x98800088, 0x98800094, 0x98800098, 0x9880009c,
                            0x988000a0, 0x98800030, 0x988000e4):
                state.register(address, 'w')
            return self.step(state, hooks)
        if pc == 0x6007d113:
            address, size = BLOCKS[self.stage]
            start, end, length, count = (self.reg(state, 0x9bf00000+o) for o in (0x34, 0x38, 0x3c, 0x40))
            assert (start, end, length, count) == (address+0x40000000, address+0x40000000+size, size, size)
            assert state.regs['d0'] == 4 and self.reg(state, 0x9bf00000) == 7
            payload = state.read(start, size)
            assert payload == firmware()[address-BASE:address-BASE+size]
            self.active_upload = dict(stage=self.stage, address=hex(start), bytes=size,
                sha256=hashlib.sha256(payload).hexdigest(),
                sum_be32=sum(struct.unpack('>'+str(size//4)+'I', payload)) & 0xffffffff,
                completed=False)
            self.uploads.append(self.active_upload)
            self.event(state, 'alex bulk engine consumes native descriptor', **self.active_upload)
            return self.step(state, hooks)
        if pc in self.reads:
            address = self.reads[pc]
            value = self.reg(state, address)
            if pc in (0x6007d11a, 0x6007d12a):
                assert self.active_upload is not None
                value = 0x10 if pc == 0x6007d11a else 0x30
            elif pc == 0x6007d06e:
                value = 0
            return self.observed_read(state, hooks, address, value)
        if pc == 0x6007d1a8:
            assert state.regs['d0'] == 97 and state.regs['a0'] == 0
            if self.low_memory_word is not None:
                assert not any(r.address < 8 for r in state.regions)
                state.ram('alex_scoped_low_memory_hypothesis', 0,
                          struct.pack('<II', self.low_memory_word, 0), aliases=False)
                self.event(state, 'explicit low-memory GPIO descriptor hypothesis',
                    bytes=8, first_word=self.low_memory_word, callback_word=0,
                    assumption='Unverified accessibility/content of addresses 0..7. Scoped to this call; not a null-pointer repair.')
            return self.step(state, hooks)
        if pc == 0x6007d1ad:
            assert self.active_upload is not None
            if self.low_memory_word is not None:
                self.event(state, 'native low-memory GPIO call returned', data=state.read(0,8).hex())
                state.regions = [r for r in state.regions if r.name != 'alex_scoped_low_memory_hypothesis']
            self.active_upload['completed'] = True
            self.event(state, 'native alex bulk peripheral cleanup reached', stage=self.stage)
            return self.step(state, hooks)
        if pc == 0x6007cc18:
            result = self.reg(state, state.regs['sp']+20)
            self.stages.append(dict(stage=self.stage, result=result))
            self.event(state, 'native Alex block checksum validation completed', stage=self.stage, result=result)
            if result or (self.stop_after == 'bulk' and self.stage == 2):
                return self.stop(state, 'Requested Alex block validation boundary', result=result)
            return self.step(state, hooks)
        if pc == 0x6007cc1d:
            assert len(self.stages) == 3 and all(s['result'] == 0 for s in self.stages)
            self.final_phase = 0
            return self.step(state, hooks)
        if pc == 0x6007cca0:
            assert self.final_phase == 3 and state.regs['d2'] == 0
            self.event(state, 'native Alex final activation commands accepted')
            return self.step(state, hooks)
        if pc == 0x6007c7ce:
            state.events.append(dict(kind='milestone', name='native Alex bootstrap returned',
                                     entry=hex(pc), cpu=state.cpu, instructions=state.steps,
                                     result=state.regs['d0']))
            if self.stop_after == 'alex':
                return self.stop(state, 'Requested Alex bootstrap boundary')
            return self.step(state, hooks)
        return super().handle(state, hooks, interrupts)
