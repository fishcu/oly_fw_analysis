# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Explicit, optional runtime hardware hypotheses. No camera/device access.

IRQ entry uses the base MN103 frame from the pinned GNU dv-mn103cpu.c and
the firmware's vector/priority setup. Physical vector-base and controller
arbitration behavior remain hypotheses. Deliver only at reviewed idle points.
"""
import struct


class RuntimeInterrupts:
    hooks={0x60030106,0x60030120,0x6006e7f5,0x6006e86e,0x6006e8cb,
           0x6008057a,0x600805d6,0x60080681,0x600806bd}

    def __init__(self,budget):
        if budget<1: raise ValueError('Positive interrupt budget required')
        self.budget=budget
        self.delivered=0
        self.next_cpu=0
        self.active={}
        self.context_word={}
        self.pending=set()

    def deliver_pending(self,state):
        candidates=sorted(irq for cpu,irq in self.pending if cpu==state.cpu)
        if not candidates or self.delivered>=self.budget: return False
        # Choose the lowest native priority-level number, then IRQ number.
        base=(0x99200000,0x99300000,0x99b00000)[state.cpu]
        candidates=[irq for irq in candidates if struct.unpack('<I',state.read(base+4*irq,4))[0]]
        if not candidates:return False
        irq=min(candidates,key=lambda irq:struct.unpack('<I',state.read(base+4*irq,4))[0])
        self.inject(state,irq)
        self.delivered+=1
        return True

    def timer(self,state):
        cpu=self.next_cpu
        self.next_cpu=(cpu+1)%3
        if self.delivered>=self.budget: return False
        if cpu!=state.cpu: state.switch_core(cpu)
        self.inject(state,58+cpu)
        self.delivered+=1
        return True

    def inject(self,state,irq):
        cpu=state.cpu
        if state.regs['pc']!=0x6003718b:
            raise ValueError('Only reviewed native kernel idle is an interrupt injection boundary')
        base=(0x99200000,0x99300000,0x99b00000)[cpu]
        enabled=struct.unpack('<I',state.read(base+irq*4,4))[0]
        if not enabled or enabled&(enabled-1) or enabled>64:
            raise ValueError(f'IRQ {irq} lacks a native one-hot priority: {enabled:#x}')
        level=enabled.bit_length()-1
        psw=state.regs['psw']
        if not psw&0x800 or level>=((psw>>8)&7):
            raise ValueError('IRQ masked by native PSW')
        vector_word=struct.unpack('<I',state.read(0x801c,4))[0]
        offset=struct.unpack('<H',state.read(0x8000+4*level,2))[0]
        vector=(vector_word&0xffff0000)|offset
        # Firmware initializes 801c with the full last vector; base selection
        # from its high 16 bits is an explicit unmeasured hardware assumption.
        if state.read(vector,1)!=b'\xdc': raise ValueError('Unexpected vector stub')
        selector=base+0x200+4*level
        state.register(selector,'r',(irq+1)*4)
        if not any(r.address==0x8a00 for r in state.regions):
            from penf_emulator import Region
            state.regions.append(Region('local_interrupt_source',0x8a00,bytes(2),'r'))
        state.write(0x8a00,struct.pack('<H',0x40+4*level))
        old_sp=state.regs['sp']
        state.write(old_sp-8,struct.pack('<H',psw&0xffff))
        state.write(old_sp-4,struct.pack('<I',state.regs['pc']))
        state.regs.update(sp=old_sp-8,pc=vector,psw=(psw&~0xf00)|(level<<8))
        state.register(0x9890007c,'w')
        self.active[cpu]=(irq,selector)
        state.blocked.pop(cpu,None)
        state.events.append({'kind':'model','name':'idle-boundary hardware interrupt delivery',
            'cpu':cpu,'irq':irq,'level':level,'vector':hex(vector),'stack_before':hex(old_sp),
            'assumption':'Base MN103 eight-byte exception frame; external-source selector; immediate arbitration, no nested/timed delivery',
            'evidence':'Native vector words, priority slot and callback tables; GNU dv-mn103cpu.c / rti frame'})

    def handle(self,state,hooks):
        pc=state.regs['pc']
        if pc in (0x6008057a,0x600805d6):
            if state.regs['d0']!=1: raise ValueError('Unexpected software interrupt request')
            step=state.run(hooks-{pc},limit=1)
            if step['completed']!=1 or step['status']!='instruction_limit': return False
            irq=30 if pc==0x6008057a else 31
            self.pending.add((state.cpu,irq))
            state.events.append({'kind':'model','name':'native software interrupt request latched',
                'cpu':state.cpu,'irq':irq,'entry':hex(pc),
                'assumption':'Reviewed doorbell write is delivered on the native selected core at its next idle boundary'})
            return True
        if pc in (0x60080681,0x600806bd):
            expected=30 if pc==0x60080681 else 31
            irq,selector=self.active[state.cpu]
            if irq!=expected: raise ValueError('Software IRQ disable mismatch')
            base=(0x99200000,0x99300000,0x99b00000)[state.cpu]
            if state.read(base+4*irq,4)!=bytes(4): raise ValueError('Native IRQ disable did not execute')
            state.write(selector,bytes(4))
            self.pending.discard((state.cpu,irq))
            state.events.append({'kind':'model','name':'software interrupt deasserted after native disable',
                                 'cpu':state.cpu,'irq':irq,'entry':hex(pc)})
            step=state.run(hooks-{pc},limit=1)
            return step['completed']==1 and step['status']=='instruction_limit'
        if pc in (0x60030106,0x60030120):
            expected=b'\xf6\xf0' if pc==0x60030106 else b'\xf5\x00'
            if state.read(pc,2)!=expected: raise ValueError('Context transfer bytes changed')
            if pc==0x60030106:
                state.regs['d0']=self.context_word.get(state.cpu,0)
            else:
                self.context_word[state.cpu]=state.regs['d0']
            state.events.append({'kind':'model','name':'opaque extension context transfer',
                'cpu':state.cpu,'entry':hex(pc),'value':state.regs['d0'],
                'assumption':'This save/restore pair transfers one opaque per-core word, initially zero; flags unchanged. Extension arithmetic and exact register identity unmodeled.'})
            state.regs['pc']+=2
            return True
        expected={0x6006e7f5:0,0x6006e86e:1,0x6006e8cb:2}[pc]
        if expected!=state.cpu or state.regs['d0']!=1<<expected:
            raise ValueError('Unexpected timer acknowledgement')
        irq,selector=self.active[state.cpu]
        if irq!=58+expected: raise ValueError('Timer ack without matching active interrupt')
        step=state.run(hooks-{pc},limit=1)
        if step['completed']!=1 or step['status']!='instruction_limit': return False
        state.write(selector,bytes(4))
        state.events.append({'kind':'model','name':'timer interrupt acknowledged',
                             'cpu':state.cpu,'irq':irq,'entry':hex(pc)})
        return True
