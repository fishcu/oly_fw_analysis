#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Fresh PEN-F boot through one reviewed camera-clock initialization call.

The clock-source mux is hypothetically 0 (native query returns 24 MHz).
The old PLL control is hypothetically 0. Exact native writes are accepted
individually; their physical clock/power effects and locking are unmodeled.
No MMIO mapping survives its one reviewed instruction.
"""
import hashlib

import penf_boot_emulator as boot
import penf_boot_strobe_sequence as sequence
from penf_emulator import ROOT


class CameraClockPeer(sequence.StrobeSequencePeer):
    # (instruction, address, permissions, value, native return/caller context)
    clock_operations = (
        (0x6008f2b5,0x98800050,'r',0,0x6008f904),
        (0x6008f2b5,0x98800050,'r',0,0x6008f915),
        (0x6008f2b5,0x98800050,'r',0,0x6008f926),
        (0x6008f93f,0x98800100,'r',0,0x6008f926),
        (0x6008f946,0x98800100,'w',0,0x6008f926),
        (0x6008f94d,0x98800100,'w',0x000c0011,0x6008f926),
        (0x6008f9f4,0x98800110,'w',1,0x602b762b),
        (0x6008f9b9,0x988000b0,'w',0,0x602b7636),
    )
    hooks = sequence.StrobeSequencePeer.hooks | {x[0] for x in clock_operations} | {
        0x602b74d8,0x602b7554,
    }

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.camera_clock_active = False
        self.camera_clock_finished = False
        self.camera_clock_operation = 0

    def handle(self,state,hooks,interrupts):
        pc=state.regs['pc']
        try:
            if pc==0x602b74d8:
                if (state.cpu!=0 or self.camera_clock_active or self.camera_clock_finished
                        or state.regs['mdr']!=0x6025b940):
                    raise ValueError('Unreviewed camera-clock initializer caller or repeat')
                self.camera_clock_active=True
                self.event(state,'native camera-clock initializer entered',
                    assumption='Mux 0 and old PLL control 0 supplied only at reviewed instructions; physical clock behavior unmeasured.')
                return self.step(state,hooks)
            if pc in {x[0] for x in self.clock_operations}:
                if (state.cpu!=0 or not self.camera_clock_active
                        or self.camera_clock_operation>=len(self.clock_operations)):
                    raise ValueError('Camera-clock MMIO outside scoped initialization')
                expected,address,permission,value,ret=self.clock_operations[self.camera_clock_operation]
                if pc!=expected or state.regs['mdr']!=ret:
                    raise ValueError('Camera-clock MMIO order/caller differs')
                if pc in (0x6008f2b5,0x6008f93f,0x6008f946,0x6008f94d) and state.regs['a0']!=address:
                    raise ValueError('Camera-clock MMIO pointer differs')
                if permission=='w':
                    source='d2' if pc==0x6008f94d else 'd0' if pc==0x6008f946 else 'd1'
                    if state.regs[source]!=value:
                        raise ValueError('Camera-clock native write value differs')
                if any(r.address<address+4 and address<r.address+len(r.data) for r in state.regions):
                    raise ValueError('Camera-clock register already mapped')
                state.register(address,permission,value if permission=='r' else 0)
                try:
                    result=state.run(hooks-{pc},limit=1)
                    final_value=self.reg(state,address)
                finally:
                    state.regions=[r for r in state.regions if r.address!=address]
                if result['status']!='instruction_limit' or result['completed']!=1 or final_value!=value:
                    return False
                self.camera_clock_operation+=1
                self.event(state,'scoped native camera-clock register operation',
                    operation=self.camera_clock_operation,instruction=hex(pc),
                    address=hex(address),access=permission,value=hex(value))
                return True
            if pc==0x602b7554:
                if (state.cpu!=0 or not self.camera_clock_active
                        or self.camera_clock_operation!=len(self.clock_operations)
                        or state.read(0x6188448e,1)!=b'\x01'):
                    raise ValueError('Camera-clock initializer completion differs')
                self.camera_clock_active=False
                self.camera_clock_finished=True
                state.events.append(dict(kind='milestone',name='native camera-clock initialization completed',
                    cpu=state.cpu,entry=hex(pc),instructions=state.steps,reference_count=1))
                return self.step(state,hooks)
            return super().handle(state,hooks,interrupts)
        except ValueError as exc:
            return self.stop(state,'Camera-clock initialization context needs review',reason=str(exc))


def main():
    old_peer=sequence.StrobeSequencePeer
    original_experiment=boot.boot_experiment
    source='tools/penf_boot_camera_clock.py'
    digest=hashlib.sha256((ROOT/source).read_bytes()).hexdigest()
    def experiment(*args,**kwargs):
        report,state=original_experiment(*args,**kwargs)
        report['source_sha256'][source]=digest
        report['camera_clock_scenario']=dict(mux=0,frequency_query_hz=24000000,old_pll=0,
            scope='One 602b74d8 initializer; eight instruction-scoped MMIO accesses. Writes have no modeled physical effects.')
        return report,state
    sequence.StrobeSequencePeer=CameraClockPeer
    boot.boot_experiment=experiment
    try: sequence.main()
    finally:
        sequence.StrobeSequencePeer=old_peer
        boot.boot_experiment=original_experiment

if __name__=='__main__':main()
