#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native initialization of five camera units with exact write-only sinks.

Configuration copies, IRQ registration, reference counters and returns remain
native. No image result, peripheral completion or interrupt is supplied.
"""
import hashlib

import penf_boot_emulator as boot
import penf_boot_camera_gates as gates
from penf_emulator import ROOT


class CameraUnitsPeer(gates.CameraGatesPeer):
    units=(
        (0x6025d92c,0x615fcd90,0x6025f979,0x6025da23,(
            (0x6025d9b9,0x9b200000,0),(0x6025d9bf,0x9b200800,0),(0x6025d9c5,0x9b201000,0))),
        (0x6025e8d5,0x615fcde4,0x60260f74,0x6025e915,(
            (0x6025e903,0x9b300000,0),(0x6025e90f,0x9b300230,0x11111))),
        (0x60296ad8,0x615fd214,0x60296271,0x60296b0c,(
            (0x60296b06,0x9c500000,0),)),
        (0x60298b7a,0x615fd26c,0x602974e3,0x60298c16,(
            (0x60298bba,0x9b400000,0),(0x60298bc0,0x9b400800,0),
            (0x60298bc6,0x9b401000,0),(0x60298bcc,0x9b401800,0))),
        (0x6029c3b2,None,0x6029b51c,0x6029c400,(
            (0x6029c3d3,0x9b100000,0),(0x6029c3db,0x9b100004,1))),
    )
    config_writes={0x602b79de:2,0x602b7a19:1,0x602b7a95:2,0x602b7adc:1,
        0x602b7b20:4,0x602b7b5b:1,0x602b7bd7:4,0x602b7c15:1,
        0x602b7d09:8,0x602b7d44:1,0x602b7dc0:8,0x602b7dfe:1}
    hooks=gates.CameraGatesPeer.hooks|set(config_writes)|{
        p for entry,source,caller,ret,ops in units for p in (entry,ret,*[x[0] for x in ops])}

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.unit_index=0
        self.unit_stage=None

    def handle(self,state,hooks,interrupts):
        pc=state.regs['pc']
        relevant={p for e,s,c,r,ops in self.units for p in (e,r,*[x[0] for x in ops])}
        if pc not in relevant:return super().handle(state,hooks,interrupts)
        try:
            if state.cpu!=0 or not self.gates_active or self.unit_index>=len(self.units):
                raise ValueError('Camera unit outside reviewed initialization scope')
            entry,source,caller,ret,ops=self.units[self.unit_index]
            if pc==entry:
                expected_source=source if source is not None else state.regs['sp']+12
                if self.unit_stage is not None or state.regs['a0']!=expected_source or state.regs['mdr']!=caller:
                    raise ValueError('Camera unit caller/configuration differs')
                self.unit_stage=0
                return self.step(state,hooks)
            if self.unit_stage is None:raise ValueError('Camera unit entry not observed')
            if pc==ret:
                if self.unit_stage!=len(ops):raise ValueError('Camera unit writes incomplete')
                state.events.append(dict(kind='milestone',name='native camera unit initializer completed',
                    cpu=state.cpu,entry=hex(entry),instructions=state.steps,unit=self.unit_index))
                self.unit_index+=1;self.unit_stage=None
                return self.step(state,hooks)
            if self.unit_stage>=len(ops):raise ValueError('Camera unit unexpected extra write')
            expected,address,value=ops[self.unit_stage]
            if pc!=expected or state.regs['d0']!=value:raise ValueError('Camera unit write order/value differs')
            self.access(state,hooks,address,'w',value)
            self.unit_stage+=1
            return True
        except ValueError as exc:
            return self.stop(state,'Camera unit initialization needs review',reason=str(exc))


def main():
    original_peer=gates.CameraGatesPeer
    original_experiment=boot.boot_experiment
    source='tools/penf_boot_camera_units.py'
    digest=hashlib.sha256((ROOT/source).read_bytes()).hexdigest()
    def experiment(*args,**kwargs):
        report,state=original_experiment(*args,**kwargs)
        report['source_sha256'][source]=digest
        report['camera_units_scenario']=dict(scope='Five reviewed initializers, twelve exact MMIO writes.',
            hypothesis='Write-only sinks. No peripheral execution, completion or IRQ.')
        return report,state
    gates.CameraGatesPeer=CameraUnitsPeer;boot.boot_experiment=experiment
    try:gates.main()
    finally:
        gates.CameraGatesPeer=original_peer;boot.boot_experiment=original_experiment


if __name__=='__main__':main()
