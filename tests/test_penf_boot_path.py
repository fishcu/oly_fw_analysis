#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Replay the conditional startup and verify native milestones and its hard stop."""
import json
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from penf_boot_emulator import boot_experiment
from penf_boot_audit import summarize
from penf_emulator import ROOT


class BootPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report,cls.state=boot_experiment(ideal_storage=True,erased_parameters=True,
            run_peers=True,timer_clock=True,counter_step=1000,controller_init=True,
            peripheral_reset=True,adc_clock=True,adc_idle=True)
        out=ROOT/'analysis/boot_emulation/replay-validation.json'
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(summarize(cls.report),indent=2)+'\n')

    def test_three_real_kernel_initializations_and_task_objects(self):
        r,s=self.report,self.state
        self.assertEqual(struct.unpack('<H',s.read(0x8ff00000,2))[0],7)
        pointers=struct.unpack('<3I',s.read(0x8ff00004,12))
        self.assertEqual(pointers,(0x600414c4,0x60041650,0x600417dc))
        self.assertEqual([len(s.task_snapshot(cpu)) for cpu in range(3)],[140,49,21])
        self.assertEqual([s.task_snapshot(cpu)[0]['state'] for cpu in (1,2)],[2,2])
        names={e.get('name') for e in r['events']}
        self.assertIn('all three kernels initialized shared readiness',names)
        self.assertNotIn('assumed peer kernel readiness',names)
        self.assertEqual({e['cpu'] for e in r['events'] if e['kind']=='execution'},{0,1,2})

    def test_native_task_switches_but_updaters_still_dormant(self):
        r=self.report
        entries={e.get('entry') for e in r['events'] if e['kind']=='milestone'}
        self.assertTrue({'0x6006ad97','0x6006bf05','0x6007025b','0x60041ae3'}<=entries)
        tasks={t['id']:t for t in r['final_cpu0_tasks']}
        self.assertEqual(tasks[1]['state'],1)
        for task in (100,138,139): self.assertEqual(tasks[task]['state'],4)
        for task in (19,42,46,47,48,49,95): self.assertEqual(tasks[task]['state'],16)
        starts={e['task_id'] for e in r['events'] if e['kind']=='task_start_request'}
        self.assertTrue({11,12,27,28,100,138,139}<=starts)
        self.assertFalse({19,42,95}&starts)

    def test_adc_request_stops_before_unmodeled_completion(self):
        r,s=self.report,self.state
        last=next(e['result'] for e in reversed(r['events']) if e['kind']=='execution')
        self.assertEqual(r['completed_instructions'],319893)
        self.assertEqual(last['status'],'memory_fault')
        self.assertEqual(last['fault']['pc'],0x60079dc3)
        self.assertEqual(last['fault']['address'],0x98c00014)
        self.assertEqual(last['fault']['access'],'read')
        self.assertEqual(last['fault']['size'],4)
        self.assertEqual(s.read(0x98c00004,4),struct.pack('<I',1))
        # Writing an acknowledgement does not create a readable completion bit.
        self.assertEqual(s.read(0x98c00014,4),struct.pack('<I',1))
        region=next(x for x in s.regions if x.address==0x98c00014)
        self.assertNotIn('r',region.permissions)
        sample_buffer=struct.unpack('<I',s.read(0xa1c38414,4))[0]
        self.assertEqual(struct.unpack('<HH',s.read(sample_buffer,4)),(5,0))


if __name__=='__main__':
    unittest.main(verbosity=2)
