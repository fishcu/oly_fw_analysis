# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""One reviewed CPU1 flash-semaphore request/reply; native kernel services execute."""
import struct

from penf_cross_core_interrupts import CrossCoreInterrupts


class RemoteSemaphoreInterrupts(CrossCoreInterrupts):
    request_address = 0xa1bed9b8
    request_words = (8, 0xffffffff, 0, 1, 1, 116, 0xffffffff, 0, 0, 0, 116, 0x101c, 3)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.remote_sent = False
        self.remote_replied = False
        self.remote_frames = {}
        self.remote_returns = []

    def record(self, state):
        return struct.unpack('<13I', state.read(self.request_address, 52))

    def send_request(self, state, hooks):
        if (state.cpu, state.regs['pc'], state.regs['d0'], state.regs['a3']) != (
                1, 0x6006c62f, 1, self.request_address) or self.remote_sent:
            raise ValueError('Unreviewed/repeated remote semaphore request')
        if self.record(state) != self.request_words or not self.cross_acknowledged:
            raise ValueError('Remote semaphore record or prior handoff differs')
        self._prepare_delivery(state, 0)  # Validate before admitting the native write.
        state.register(0x99200308, 'w')
        r = state.run(hooks-{state.regs['pc']}, limit=1)
        if r['status'] != 'instruction_limit' or r['completed'] != 1:
            return False
        if self.word(state, 0x99200308) != 1:
            raise ValueError('Native CPU0 request write differs')
        state.register(0x99200308, 'rw', 1)
        self.pending.add((0, 120))
        self.remote_sent = True
        self._event(state, 'remote flash semaphore request latched', record=[hex(v) for v in self.record(state)])
        self.deliver_remote(state, 0)
        return True

    def send_reply(self, state, hooks):
        record = self.record(state)
        if (state.cpu, state.regs['pc'], state.regs['d0'], state.regs['a2']) != (
                0, 0x6006c577, 2, self.request_address+12) or not self.remote_sent or self.remote_replied:
            raise ValueError('Unreviewed/repeated remote semaphore reply')
        expected = list(self.request_words); expected[2] = record[2]; expected[12] = 5
        if record != tuple(expected):
            raise ValueError('Remote semaphore reply record differs')
        self._prepare_delivery(state, 1)
        r = state.run(hooks-{state.regs['pc']}, limit=1)
        if r['status'] != 'instruction_limit' or r['completed'] != 1:
            return False
        if self.word(state, 0x99300308) != 2:
            raise ValueError('Native CPU1 reply write differs')
        self.pending.add((1, 120))
        self.remote_replied = True
        self._event(state, 'remote flash semaphore reply latched', native_result=hex(record[2]))
        self.deliver_remote(state, 1)
        return True

    @staticmethod
    def _event(state, name, **data):
        state.events.append(dict(kind='model', name=name, cpu=state.cpu,
            entry=hex(state.regs['pc']), instructions=state.steps, **data))

    def _prepare_delivery(self, state, cpu):
        if state.cpu == cpu or cpu in self.remote_frames or self.delivered >= self.budget:
            raise ValueError('Remote IRQ target, outstanding frame or budget differs')
        saved = dict(state.cpu_regs[cpu])
        pc, lo, hi, tcb_state = {
            0: (0x600701c9, 0x617733cc, 0x61773bc4, 0x6182385c),
            1: (0x6006c635, 0x617f0040, 0x617f0438, 0x61bde37c),
        }[cpu]
        if saved['pc'] != pc or not lo <= saved['sp'] <= hi or cpu in state.blocked:
            raise ValueError('Remote IRQ target is outside the reviewed task/site')
        if int.from_bytes(state.read(tcb_state, 2), 'little') != 1:
            raise ValueError('Remote IRQ target task is not running')
        base = (0x99200000, 0x99300000)[cpu]
        psw = saved['psw']
        if self.word(state, base+120*4) != 4 or not psw & 0x800 or ((psw >> 8) & 7) <= 2:
            raise ValueError('Remote IRQ priority/mask differs')
        vector = (int.from_bytes(self.private_read(state, cpu, 0x801c, 4), 'little') & 0xffff0000) | int.from_bytes(self.private_read(state, cpu, 0x8008, 2), 'little')
        if state.read(vector, 1) != b'\xdc':
            raise ValueError('Unexpected remote IRQ vector')
        return saved, base, vector

    def deliver_remote(self, state, cpu):
        saved, base, vector = self._prepare_delivery(state, cpu)
        mask = 1 if cpu == 0 else 2
        if (cpu, 120) not in self.pending or self.word(state, base+0x308) != mask:
            raise ValueError('Remote pending IRQ/status differs')
        frame = dict(registers=saved, previous_active=self.active.get(cpu), acknowledged=False)
        state.switch_core(cpu)
        selector = base+0x208
        state.register(selector, 'r', 121*4)
        state.write(0x8a00, struct.pack('<H', 0x48))
        state.write(saved['sp']-8, struct.pack('<H', saved['psw'] & 0xffff))
        state.write(saved['sp']-4, struct.pack('<I', saved['pc']))
        state.regs.update(pc=vector, sp=saved['sp']-8, psw=(saved['psw'] & ~0xf00) | 0x200)
        state.register(base+0x30c, 'w')
        self.active[cpu] = (120, selector)
        self.remote_frames[cpu] = frame
        self.delivered += 1
        self._event(state, 'reviewed remote semaphore IRQ120 delivery', irq=120, level=2,
            mask=mask, vector=hex(vector), return_pc=hex(saved['pc']), stack_before=hex(saved['sp']),
            assumption='Immediate cross-core delivery at a reviewed enabled task boundary; inherited eight-byte exception frame. Native kernel services execute; physical timing unmeasured.')

    def acknowledge_remote(self, state, hooks):
        cpu = state.cpu; base = (0x99200000, 0x99300000)[cpu]
        pc, mask = (0x6006c756, 1) if cpu == 0 else (0x6006c88e, 2)
        frame = self.remote_frames.get(cpu)
        if (state.regs['pc'], state.regs['d0']) != (pc, mask) or frame is None or frame['acknowledged']:
            raise ValueError('Unreviewed remote IRQ acknowledgement')
        if self.active.get(cpu) != (120, base+0x208) or (cpu, 120) not in self.pending:
            raise ValueError('Remote acknowledgement lacks active/pending source')
        r = state.run(hooks-{pc}, limit=1)
        if r['status'] != 'instruction_limit' or r['completed'] != 1:
            return False
        if self.word(state, base+0x30c) != mask:
            raise ValueError('Native remote clear write differs')
        state.write(base+0x308, bytes(4)); state.write(base+0x208, bytes(4))
        self.pending.remove((cpu, 120)); frame['acknowledged'] = True
        self._event(state, 'remote semaphore IRQ120 acknowledged', mask=mask,
            assumption='Native write-one-to-clear deasserts the only supplied request bit')
        return True

    def remote_returned(self, state):
        frame = self.remote_frames[state.cpu]; saved = frame['registers']
        if not frame['acknowledged'] or state.regs['pc'] != saved['pc']:
            raise ValueError('Remote return before acknowledgement or wrong PC')
        changed = {k: [saved[k], state.regs[k]] for k in self.register_keys if saved[k] != state.regs[k]}
        if saved['psw'] & 0xffff != state.regs['psw'] & 0xffff:
            changed['psw_low16'] = [saved['psw'], state.regs['psw']]
        if changed:
            raise ValueError(f'Remote IRQ return changed registers: {changed}')
        self._event(state, 'native remote semaphore IRQ120 return verified', registers_restored=True,
            loop_registers_before={k:saved[k] for k in ('lir','lar')},
            loop_registers_after={k:state.regs[k] for k in ('lir','lar')})
        if frame['previous_active'] is None:
            self.active.pop(state.cpu, None)
        else:
            self.active[state.cpu] = frame['previous_active']
        self.remote_returns.append(state.cpu)
        del self.remote_frames[state.cpu]
