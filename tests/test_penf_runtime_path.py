#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Replay native startup with two explicit ADC input scenarios."""
import gzip
import json
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from penf_boot_emulator import boot_experiment
from penf_boot_audit import summarize
from penf_emulator import ROOT,firmware


class RuntimePathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs={}
        out=ROOT/'analysis/runtime_boot'
        out.mkdir(parents=True,exist_ok=True)
        for sample in (900,512):
            report,state=boot_experiment(ideal_storage=True,erased_parameters=True,
                run_peers=True,timer_clock=True,counter_step=1000,controller_init=True,
                peripheral_reset=True,adc_clock=True,adc_sample=sample,runtime_peers=True,
                runtime_irqs=90,serial_clock_word=0x200000,controller_input_bits=0,
                gpio_inputs={p:0 for p in (112,82,75,76,68,61,114,133,70,158,71,62,63,171,77)},
                segments=2000,input_counter=0)
            cls.runs[sample]=(report,state)
            with gzip.open(out/f'adc-{sample}-trace.json.gz','wt') as f:json.dump(report,f)
            state.save_snapshot(out/f'adc-{sample}-state.json.gz')
            (out/f'adc-{sample}-summary.json').write_text(json.dumps(summarize(report),indent=2)+'\n')

    def milestones(self,sample):
        return {e['name']:e for e in self.runs[sample][0]['events'] if e['kind']=='milestone'}

    def test_native_battery_result_changes_the_power_branch(self):
        low,high=self.milestones(512),self.milestones(900)
        self.assertEqual(low['initial battery requests returned']['d0'],1)
        self.assertEqual(high['initial battery requests returned']['d0'],100)
        self.assertIn('power gate rejected (camNoon)',low)
        self.assertNotIn('power gate accepted (camons)',low)
        self.assertIn('power gate accepted (camons)',high)
        self.assertNotIn('power gate rejected (camNoon)',high)
        self.assertEqual(struct.unpack('<I',self.runs[512][1].read(0x618642cc,4))[0],99)
        self.assertIn(struct.unpack('<I',self.runs[900][1].read(0x618642cc,4))[0],(0,1))

    def test_adc_queue_requires_native_software_interrupt_cleanup(self):
        for sample,(report,state) in self.runs.items():
            events=report['events']
            reads=[e for e in events if e.get('name')=='ADC sample read']
            self.assertEqual([e['channel'] for e in reads[:10]],[6]*5+[0]*5)
            self.assertEqual({e['value'] for e in reads},{sample})
            requests=[i for i,e in enumerate(events) if e.get('name')=='native software interrupt request latched' and e['irq']==31]
            deliveries=[i for i,e in enumerate(events) if e.get('name')=='idle-boundary hardware interrupt delivery' and e['irq']==31]
            self.assertTrue(requests and deliveries)
            self.assertLess(requests[0],deliveries[0])
            self.assertTrue(any(e.get('name')=='software interrupt deasserted after native disable' for e in events))
            self.assertTrue(any(e.get('name')=='timer interrupt acknowledged' for e in events))

    def test_application_sections_and_real_task_dispatch(self):
        data=firmware()
        for sample,(report,state) in self.runs.items():
            names=self.milestones(sample)
            self.assertTrue({'CPU1 initial task','CPU2 initial task','normal startup section loading','USTART1 task'}<=names.keys())
            reads=[e for e in report['events'] if e.get('name')=='decoded logical flash read' and int(e['source'],16)>=0x80000000]
            self.assertEqual([(int(e['source'],16),e['bytes']) for e in reads[:2]],[(0x804c1800,559104),(0x805a9800,2086912)])
            for e in reads:
                offset=int(e['source'],16)-0x803a0020
                expected=data[offset:offset+e['bytes']]
                self.assertEqual(len(expected),e['bytes'])
                # These loaded code sections have not been patched by this scenario.
                self.assertEqual(state.read(int(e['destination'],16),e['bytes']),expected)
            starts={e['task_id'] for e in report['events'] if e['kind']=='task_start_request'}
            self.assertIn(47,starts)
            self.assertEqual([len(state.task_snapshot(cpu)) for cpu in range(3)],[140,49,21])

    def test_unmodeled_boundary_is_reported_without_claiming_boot_complete(self):
        for report,state in self.runs.values():
            last=next(e['result'] for e in reversed(report['events']) if e['kind']=='execution')
            self.assertEqual(last['status'],'memory_fault')
            self.assertTrue(last['fault']['address'])
            for name in ('TPC USB task','FIRMUP service task','SD updater task'):
                self.assertFalse(any(e.get('name')==name for e in report['events']))


if __name__=='__main__':unittest.main(verbosity=2)
