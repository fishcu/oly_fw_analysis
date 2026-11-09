# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""One reviewed CPU0-to-CPU1 IRQ120 wakeup; physical wake timing is hypothetical."""
import struct

from penf_emulator import Region
from penf_startup_interrupts import StartupInterrupts


class CrossCoreInterrupts(StartupInterrupts):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cross_resume = None
        self.cross_requested = False
        self.cross_injected = False
        self.cross_acknowledged = False
        self.cross_returned = False

    @staticmethod
    def private_read(state, cpu, address, size):
        r = next(r for r in state.regions if r.address <= address and
                 address+size <= r.address+len(r.data))
        if not state.is_private(r):
            raise ValueError('Expected a CPU-private register')
        data = state.private_memory[cpu][r.name]
        offset = address-r.address
        return data[offset:offset+size]

    def request(self, state, hooks):
        if (state.cpu, state.regs['pc'], state.regs['a0'], state.regs['d0']) != (
                0, 0x6006fda5, 0x99300308, 8) or self.cross_requested:
            raise ValueError('Unreviewed/repeated cross-core request')
        if (self.word(state, 0xa1c583fc) != 3 or
                state.read(0xa1c274e0, 8) != struct.pack('<II', 0x600421e1, 0) or
                state.read(0xa1c26cc8, 8) != struct.pack('<II', 0x600701ff, 0) or
                state.read(0xa1c26fc8, 2) != b'\x01\x00'):
            raise ValueError('Cross-core queue differs from section-3 request')
        state.register(0x99300308, 'w')
        r = state.run(hooks-{state.regs['pc']}, limit=1)
        if r['status'] != 'instruction_limit' or r['completed'] != 1:
            return False
        if self.word(state, 0x99300308) != 8:
            raise ValueError('Native cross-core write differs')
        state.register(0x99300308, 'rw', 8)
        self.pending.add((1, 120))
        self.cross_requested = True
        state.events.append(dict(kind='model', name='section3 CPU1 interrupt request latched',
            cpu=0, entry='0x6006fda5', instructions=state.steps, irq=120, mask=8,
            assumption='Request/status register retains bit 3; delivery deferred to sender return from its critical section'))
        return True

    def wake_cpu1(self, state):
        if (state.cpu, state.regs['pc']) != (0, 0x600701c9):
            raise ValueError('Unreviewed sender return boundary')
        if not self.cross_requested or self.cross_injected or (1, 120) not in self.pending:
            raise ValueError('No unique pending CPU1 wake request')
        if self.delivered >= self.budget:
            raise ValueError('Cross-core interrupt budget exhausted')
        saved = dict(state.cpu_regs[1])
        if saved['pc'] != 0x600706ef or state.blocked.get(1) != 'hypothetical private 8040 idle':
            raise ValueError('CPU1 is not at the reviewed parked site')
        if int.from_bytes(state.read(0x61bdd74c, 2), 'little') != 1:
            raise ValueError('CPU1 initial task is not running')
        if not 0x617fdb48 <= saved['sp'] <= 0x617fe340:
            raise ValueError('CPU1 saved stack is outside initial task')
        enabled = self.word(state, 0x99300000+120*4)
        if enabled != 4 or not saved['psw'] & 0x800 or ((saved['psw'] >> 8) & 7) <= 2:
            raise ValueError('CPU1 IRQ120 priority/mask differs')
        if self.word(state, 0x99300308) != 8:
            raise ValueError('CPU1 request status differs')
        vector_word = int.from_bytes(self.private_read(state, 1, 0x801c, 4), 'little')
        offset = int.from_bytes(self.private_read(state, 1, 0x8008, 2), 'little')
        vector = (vector_word & 0xffff0000) | offset
        if state.read(vector, 1) != b'\xdc':
            raise ValueError('Unexpected CPU1 native vector')
        # The chosen point is after the sender's native interrupt-mask restore.
        # CPU0's active timer and saved USTART3 checkpoint remain untouched.
        state.switch_core(1)
        selector = 0x99300208
        state.register(selector, 'r', 121*4)
        if not any(r.address == 0x8a00 for r in state.regions):
            state.regions.append(Region('local_interrupt_source', 0x8a00, bytes(2), 'r'))
        state.write(0x8a00, struct.pack('<H', 0x48))
        state.write(saved['sp']-8, struct.pack('<H', saved['psw'] & 0xffff))
        state.write(saved['sp']-4, struct.pack('<I', saved['pc']))
        state.regs.update(sp=saved['sp']-8, pc=vector, psw=(saved['psw'] & ~0xf00) | 0x200)
        state.register(0x9930030c, 'w')
        self.active[1] = (120, selector)
        state.blocked.pop(1)
        self.cross_resume = saved
        self.cross_injected = True
        self.delivered += 1
        state.events.append(dict(kind='model', name='reviewed CPU1 halt wake and IRQ120 delivery',
            cpu=1, irq=120, level=2, vector=hex(vector), return_pc=hex(saved['pc']),
            stack_before=hex(saved['sp']), instructions=state.steps,
            assumption='IRQ120 wakes the halted core; inherited eight-byte MN103 frame and external-source selector. Physical wake latency unmeasured.'))

    def acknowledge(self, state, hooks):
        if ((state.cpu, state.regs['pc'], state.regs['d0']) != (1, 0x6006c90c, 8)
                or self.cross_resume is None or self.cross_acknowledged
                or self.active.get(1) != (120, 0x99300208)):
            raise ValueError('Unreviewed CPU1 IRQ120 acknowledgement')
        r = state.run(hooks-{state.regs['pc']}, limit=1)
        if r['status'] != 'instruction_limit' or r['completed'] != 1:
            return False
        if self.word(state, 0x9930030c) != 8:
            raise ValueError('Native clear write differs')
        state.write(0x99300308, bytes(4))
        state.write(0x99300208, bytes(4))
        self.pending.remove((1, 120))
        self.cross_acknowledged = True
        state.events.append(dict(kind='model', name='CPU1 IRQ120 acknowledged after native clear write',
            cpu=1, instructions=state.steps, assumption='Write-one-to-clear bit 3 deasserts this source; no other request bits supplied'))
        return True

    def returned(self, state):
        if state.cpu != 1 or state.regs['pc'] != 0x600706ef or self.cross_resume is None:
            raise ValueError('Unreviewed CPU1 return checkpoint')
        if not self.cross_acknowledged:
            raise ValueError('CPU1 returned before acknowledging the source')
        saved = self.cross_resume
        differences = {k: [saved[k], state.regs[k]] for k in self.register_keys
                       if saved[k] != state.regs[k]}
        if saved['psw'] & 0xffff != state.regs['psw'] & 0xffff:
            differences['psw_low16'] = [saved['psw'], state.regs['psw']]
        if differences:
            raise ValueError(f'CPU1 IRQ return changed registers: {differences}')
        state.events.append(dict(kind='model', name='native CPU1 IRQ120 return verified',
            cpu=1, instructions=state.steps, registers_restored=True,
            loop_registers_before={k: saved[k] for k in ('lir', 'lar')},
            loop_registers_after={k: state.regs[k] for k in ('lir', 'lar')}))
        self.cross_resume = None
        self.cross_returned = True
