# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Bounded CPU0 task-context interrupt hypothesis for reviewed USTART3 sites.

Keeps the earlier idle model unchanged. Timer cadence is native instruction
count, not physical time. Existing pending software IRQs participate in the
same priority arbitration; no readiness flags or kernel returns are supplied.
"""
import struct

from penf_boot_core_idle import CoreIdleInterrupts
from penf_emulator import Region


class StartupInterrupts(CoreIdleInterrupts):
    boundaries = {
        0x601a7671: 'API initializer returned',
        0x602c5aea: 'parameter default outer iteration',
        0x602c5fd5: 'parameter filter outer iteration',
        0x602f067a: 'parameter bank store entry',
    }
    register_keys = ('d0', 'd1', 'd2', 'd3', 'a0', 'a1', 'a2', 'a3', 'sp', 'mdr')

    def __init__(self, budget, period=250000):
        super().__init__(budget)
        if period <= 0:
            raise ValueError('Positive instruction interval required')
        self.period = period
        self.next_tick = 0
        self.resume = None
        self.nonidle_delivered = 0

    @staticmethod
    def word(state, address):
        return int.from_bytes(state.read(address, 4), 'little')

    def eligibility(self, state, irq):
        enabled = self.word(state, 0x99200000+irq*4)
        if not enabled:
            return None
        if enabled & (enabled-1) or enabled > 64:
            raise ValueError('Invalid native interrupt priority word')
        level = enabled.bit_length()-1
        psw = state.regs['psw']
        return level if psw & 0x800 and level < ((psw >> 8) & 7) else None

    def checkpoint(self, state):
        """Return True on injection; otherwise let the original instruction run."""
        pc = state.regs['pc']
        if state.cpu != 0 or pc not in self.boundaries:
            raise ValueError('Unreviewed task-context interrupt checkpoint')
        if self.resume is not None:
            saved = self.resume
            if pc != saved['pc'] or state.regs['sp'] != saved['registers']['sp']:
                raise ValueError('Reached a new checkpoint before reviewed IRQ return')
            differences = {key: [saved['registers'][key], state.regs[key]]
                           for key in self.register_keys
                           if saved['registers'][key] != state.regs[key]}
            if state.regs['psw'] & 0xffff != saved['registers']['psw'] & 0xffff:
                differences['psw_low16'] = [saved['registers']['psw'], state.regs['psw']]
            if differences:
                raise ValueError(f'Native task-context IRQ return changed registers: {differences}')
            state.events.append(dict(kind='model', name='native return to interrupted USTART3 checkpoint',
                cpu=0, irq=saved['irq'], entry=hex(pc), instructions=state.steps,
                general_registers_restored=True,
                loop_registers_before={k: saved['registers'][k] for k in ('lir', 'lar')},
                loop_registers_after={k: state.regs[k] for k in ('lir', 'lar')}))
            self.resume = None
        if self.delivered >= self.budget:
            return False
        candidates = [irq for cpu, irq in self.pending if cpu == 0]
        if state.steps >= self.next_tick:
            candidates.append(58)
        admitted = [(level, irq) for irq in candidates
                    if (level := self.eligibility(state, irq)) is not None]
        if not admitted:
            return False
        _, irq = min(admitted)
        self.inject(state, irq)
        self.delivered += 1
        self.nonidle_delivered += 1
        if irq == 58:
            self.next_tick = state.steps+self.period
        return True

    def inject(self, state, irq):
        if state.regs['pc'] == 0x6003718b:
            return super().inject(state, irq)
        pc, sp = state.regs['pc'], state.regs['sp']
        if state.cpu != 0 or pc not in self.boundaries or irq not in (30, 31, 58):
            raise ValueError('Unreviewed task-context interrupt source/site')
        if self.resume is not None:
            raise ValueError('Nested task-context interrupt not reviewed')
        if int.from_bytes(state.read(0x6182394c, 2), 'little') != 1:
            raise ValueError('USTART3 is not the running task')
        if not 0x6177239c+8 <= sp <= 0x61772b9c:
            raise ValueError('Interrupted stack is outside USTART3')
        level = self.eligibility(state, irq)
        if level is None:
            raise ValueError('Task-context IRQ is disabled or masked')
        psw = state.regs['psw']
        vector_word = self.word(state, 0x801c)
        offset = int.from_bytes(state.read(0x8000+4*level, 2), 'little')
        vector = (vector_word & 0xffff0000) | offset
        if state.read(vector, 1) != b'\xdc':
            raise ValueError('Unexpected native vector stub')
        saved = dict(state.regs)
        selector = 0x99200200+4*level
        state.register(selector, 'r', (irq+1)*4)
        if not any(r.address == 0x8a00 for r in state.regions):
            state.regions.append(Region('local_interrupt_source', 0x8a00, bytes(2), 'r'))
        state.write(0x8a00, struct.pack('<H', 0x40+4*level))
        state.write(sp-8, struct.pack('<H', psw & 0xffff))
        state.write(sp-4, struct.pack('<I', pc))
        state.regs.update(sp=sp-8, pc=vector, psw=(psw & ~0xf00) | (level << 8))
        state.register(0x9890007c, 'w')
        self.active[0] = (irq, selector)
        state.blocked.pop(0, None)
        self.resume = dict(pc=pc, irq=irq, registers=saved)
        state.events.append(dict(kind='model', name='reviewed USTART3 interrupt delivery',
            cpu=0, irq=irq, level=level, vector=hex(vector), return_pc=hex(pc),
            checkpoint=self.boundaries[pc], stack_before=hex(sp), instructions=state.steps,
            instruction_interval=self.period,
            assumption='Same base MN103 exception frame/vector hypothesis as idle delivery; selected task boundaries and instruction-count timing, no nested injection or physical clock claim'))
