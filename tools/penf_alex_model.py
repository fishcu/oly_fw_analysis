# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Bounded hypothetical serial peer for seven native 'alex' startup commands.

The reply script comes from native expected-reply constants, not captured hardware.
Native TX, RX, IRQ dispatch, callback, comparison and retry code all still execute.
No device access, arbitrary commands, transfers of firmware, or forced task success.
"""
from dataclasses import replace
import struct


STARTUP = tuple((bytes.fromhex(tx), bytes.fromhex(rx)) for tx,rx in (
    ('f5020000a0','20f5000000'), ('f4010000a0','20f4000000'),
    ('f0000002a0','20f0000000'), ('f2228100a0','20f2000000'),
    ('f3010000a0','20f3000000'), ('f0011203a0','20f0000000'),
    ('f1010000a0','20f1000000')))


class AlexPeer:
    control_reads={0x6008b58a:0x98300028,0x6008b5a2:0x98300028,
        0x6008b5c0:0x98300014,0x6008b6bc:0x98300028,0x6008b6e6:0x98300014,
        0x6008b715:0x98300014,0x6008b723:0x98300040}
    hooks=set(control_reads)|{0x6007cca4,0x6007cd02,0x6007cd62,0x6007cde7,
        0x6008b1f5,0x6008b1fa,0x6008b1fd,0x6007cd3c,0x6007cd47,
        0x6008b8b5,0x6008b8f1,0x6008b95f,0x6008b6ca,0x6008b6f4,
        0x6008b542,0x6008b547,0x6007cf6b,0x6007ca48,0x6007ca4b}

    def __init__(self, scenario):
        if scenario not in ('startup','bad-first-reply'): raise ValueError('Unknown alex scenario')
        self.scenario=scenario
        self.command=None
        self.index=0
        self.fifo=[]
        self.irq_pending=False
        self.waiter=None
        self.transactions=[]
        self.bytes_tx=0
        self.bytes_rx=0
        self.callbacks=0

    def event(self,state,name,**kw):
        state.events.append(dict(kind='model',name=name,cpu=state.cpu,
                                 entry=hex(state.regs['pc']),**kw))

    def stop(self,state,name,**kw):
        state.events.append(dict(kind='unresolved',name=name,cpu=state.cpu,
                                 entry=hex(state.regs['pc']),**kw))
        return False

    @staticmethod
    def step(state,hooks):
        result=state.run(hooks-{state.regs['pc']},limit=1)
        return result['completed']==1 and result['status']=='instruction_limit'

    def read_word(self,state,hooks,address,value,reg='a0'):
        if state.regs[reg]!=address: return self.stop(state,'Serial read outside reviewed channel',address=hex(state.regs[reg]))
        old=next(r for r in state.regions if r.address==address)
        state.register(address,'rw',value)
        self.event(state,'alex serial read',address=hex(address),value=value)
        try: return self.step(state,hooks)
        finally:
            # Read-only status bits must never contaminate retained control writes.
            state.regions=[replace(r,data=old.data,permissions=old.permissions) if r.address==address else r for r in state.regions]

    def summary(self):
        return dict(scenario=self.scenario,transactions=self.transactions,bytes_tx=self.bytes_tx,
                    bytes_rx=self.bytes_rx,callbacks=self.callbacks,fifo=self.fifo)

    def handle(self,state,hooks,interrupts):
        pc=state.regs['pc']
        if pc in self.control_reads:
            address=self.control_reads[pc]
            return self.read_word(state,hooks,address,struct.unpack('<I',state.read(address,4))[0])
        if pc==0x6007cca4:
            tx=state.read(state.regs['a0'],state.regs['d1']&0xffff)
            if state.regs['d0']!=1 or tx not in dict(STARTUP):
                return self.stop(state,'Unscripted alex command',tx=tx.hex())
            expected=struct.unpack('<I',state.read(state.regs['sp']+60,4))[0]
            rx=dict(STARTUP)[tx]
            if state.read(expected,5)!=rx: raise ValueError('Native expected reply differs from reviewed constants')
            self.command=(tx,rx)
            self.transactions.append(dict(tx=tx.hex(),expected=rx.hex(),attempts=[],result=None))
            self.event(state,'alex command entered',tx=tx.hex(),expected=rx.hex(),
                assumption='Scripted reply inferred from native comparison constants; physical peer identity and timing unverified')
        elif pc==0x6007cd02:
            if self.fifo or self.waiter is not None: raise ValueError('Previous serial attempt not drained')
            self.index=0
        elif pc in (0x6008b1f5,0x6008b1fa):
            if state.regs['a2']!=0x98300018 or not self.command or self.index>=5:
                return self.stop(state,'Unreviewed serial transmission')
            tx,rx=self.command
            value=state.regs['d2']
            if value!=tx[self.index] or self.fifo: raise ValueError('Serial TX script mismatch or FIFO overrun')
            if not self.step(state,hooks): return False
            reply=rx[self.index]
            if self.scenario=='bad-first-reply' and tx==STARTUP[0][0] and self.index==0: reply^=1
            self.fifo.append(reply)
            self.irq_pending=True
            self.event(state,'alex transmitted byte and queued hypothetical reply',tx=value,rx=reply,index=self.index)
            self.index+=1
            self.bytes_tx+=1
            return True
        elif pc==0x6008b1fd:
            return self.read_word(state,hooks,0x9830001c,16,'a1')
        elif pc in (0x6007cd3c,0x6007cd47):
            if state.read(0xa1c389e4,1)==b'\x10': return self.step(state,hooks)
            if not self.irq_pending or not self.fifo: return self.stop(state,'Serial wait lacks a scripted reply')
            owners=[cpu for cpu,base in enumerate((0x99200000,0x99300000,0x99b00000))
                    if struct.unpack('<I',state.read(base+69*4,4))[0]]
            if owners!=[0] or state.cpu!=1: return self.stop(state,'Unreviewed serial IRQ ownership',owners=owners)
            if state.cpu_regs[0]['pc']!=0x6003718b: return self.stop(state,'Serial IRQ owner is not at reviewed idle boundary')
            if interrupts.delivered>=interrupts.budget: return self.stop(state,'Serial IRQ budget exhausted')
            if not struct.unpack('<I',state.read(0x98300014,4))[0]&128: raise ValueError('RX interrupt not natively enabled')
            self.waiter=state.cpu
            state.blocked[state.cpu]='native serial completion wait; peer reply pending on CPU0'
            self.event(state,'alex waiter yields to native IRQ owner',irq=69,owner=0)
            state.switch_core(0)
            interrupts.pending.add((0,69))
            return interrupts.deliver_pending(state)
        elif pc in (0x6008b8b5,0x6008b8f1,0x6008b95f):
            address={0x6008b8b5:0x98300050,0x6008b8f1:0x98300014,0x6008b95f:0x98300028}[pc]
            value=0 if pc==0x6008b8b5 else struct.unpack('<I',state.read(address,4))[0]&~0x10000
            if pc==0x6008b8f1 and self.irq_pending:value|=0x10000
            return self.read_word(state,hooks,address,value)
        elif pc in (0x6008b6ca,0x6008b6f4):
            value=state.regs['d2' if pc==0x6008b6ca else 'd0']
            if state.regs['a0']!=0x98300050 or value!=(512 if pc==0x6008b6ca else 256):
                return self.stop(state,'Unreviewed serial acknowledgement')
            if not self.step(state,hooks): return False
            if pc==0x6008b6f4 and self.irq_pending:
                irq,selector=interrupts.active[state.cpu]
                if irq!=69 or state.cpu!=0: raise ValueError('Wrong serial IRQ acknowledgement')
                state.write(selector,bytes(4))
                interrupts.pending.discard((state.cpu,irq))
                self.irq_pending=False
                self.event(state,'alex RX interrupt acknowledged by native handler',irq=irq)
            return True
        elif pc==0x6008b542:
            return self.read_word(state,hooks,0x9830000c,len(self.fifo),'a2')
        elif pc==0x6008b547:
            if not self.fifo: return self.stop(state,'Empty serial receive FIFO')
            if not self.read_word(state,hooks,0x98300008,self.fifo[0],'a3'):return False
            self.fifo.pop(0)
            self.bytes_rx+=1
            return True
        elif pc==0x6007cf6b:
            if self.fifo or self.waiter is None or state.read(0xa1c389e4,1)!=b'\x10':
                raise ValueError('Native serial callback failed to complete the transfer')
            self.event(state,'native alex completion callback observed',waiter=self.waiter)
            state.blocked.pop(self.waiter,None)
            self.waiter=None
            self.callbacks+=1
        elif pc==0x6007cd62:
            actual=state.read(0xa1c38a14,5).hex()
            result=state.regs['d0']
            self.transactions[-1]['attempts'].append(dict(rx=actual,compare=result))
            self.event(state,'native alex reply comparison returned',rx=actual,result=result)
        elif pc==0x6007cde7:
            self.transactions[-1]['result']=state.regs['d0']
            if state.regs['d0']:
                return self.stop(state,'Native alex transaction rejected peer reply',result=state.regs['d0'])
        elif pc==0x6007ca48:
            state.events.append(dict(kind='milestone',name='native alex seven-command startup completed',
                                     entry=hex(pc),cpu=state.cpu,instructions=state.steps))
        elif pc==0x6007ca4b:
            return self.stop(state,'Next alex initialization stage requires a separate transfer model')
        else: raise ValueError(f'Unknown alex hook {pc:#x}')
        return self.step(state,hooks)
