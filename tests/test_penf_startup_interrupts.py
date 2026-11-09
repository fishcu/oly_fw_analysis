# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Task-context frame, cadence and guard tests; full handlers run in boot replay."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_boot_emulator import BootState
from penf_emulator import REGISTERS
from penf_startup_interrupts import StartupInterrupts


class StartupInterruptTests(unittest.TestCase):
    def fixture(self):
        state = BootState()
        state.regs = {k: 0 for k in REGISTERS}
        state.regs.update(pc=0x601a7671, psw=0xf0a, sp=0x61772b80,
                          d0=123, a0=0x61246700, mdr=0x601a7671)
        state.ram('ustart3_test_stack', 0x6177239c, b'\xa5'*2048)
        state.ram('ustart3_task_state', 0x6182394c, struct.pack('<H', 1))
        state.write(0x8014, struct.pack('<H', 0x68))
        state.write(0x801c, struct.pack('<I', 0x60030070))
        for irq in (30, 31, 58):
            state.write(0x99200000+irq*4, struct.pack('<I', 0x20))
        state.steps = 100000
        return state

    def rti(self, state, return_pc):
        # Isolate the same native RTI used by the old frame-compatibility test.
        # This does not claim to execute the whole kernel interrupt handler.
        state.regs['pc'] = 0x6003952d
        result = state.run({return_pc}, limit=5)
        self.assertEqual(result['status'], 'breakpoint')

    def test_task_return_pc_and_native_rti_restore_frame(self):
        state = self.fixture(); before = dict(state.regs)
        model = StartupInterrupts(10)
        self.assertTrue(model.checkpoint(state))
        self.assertEqual(model.active[0][0], 58)
        self.assertEqual(state.read(before['sp']-4, 4), struct.pack('<I', before['pc']))
        self.assertEqual(state.regs['pc'], 0x60030068)
        self.rti(state, before['pc'])
        self.assertFalse(model.checkpoint(state))
        for key in (*model.register_keys, 'pc', 'psw'):
            self.assertEqual(state.regs[key], before[key])
        self.assertEqual(model.nonidle_delivered, 1)
        self.assertIsNone(model.resume)

    def test_invalid_task_site_stack_mask_and_priority_reject_before_mutation(self):
        for case in ('site', 'task', 'stack', 'disabled', 'masked', 'priority', 'source'):
            with self.subTest(case=case):
                state = self.fixture(); model = StartupInterrupts(10)
                if case == 'site': state.regs['pc'] = 0x60021020
                if case == 'task': state.write(0x6182394c, struct.pack('<H', 2))
                if case == 'stack': state.regs['sp'] = 0x61821df0
                if case == 'disabled': state.write(0x992000e8, bytes(4))
                if case == 'masked': state.regs['psw'] = 0xd00
                if case == 'priority': state.write(0x992000e8, struct.pack('<I', 3))
                before = dict(state.regs); regions = list(state.regions)
                with self.assertRaises(ValueError): model.inject(state, 29 if case == 'source' else 58)
                self.assertEqual(state.regs, before)
                self.assertEqual(state.regions, regions)

    def test_pending_priority_cadence_and_budget(self):
        for period in (100000, 250000, 500000):
            with self.subTest(period=period):
                state = self.fixture(); model = StartupInterrupts(3, period)
                model.pending.add((0, 30))
                self.assertTrue(model.checkpoint(state))
                self.assertEqual(model.active[0][0], 30)
                self.rti(state, 0x601a7671)
                model.pending.remove((0, 30))  # Simulated acknowledgement in this frame-only fixture.
                self.assertTrue(model.checkpoint(state))
                self.assertEqual(model.active[0][0], 58)
                due = model.next_tick
                self.rti(state, 0x601a7671)
                state.steps = due-1
                self.assertFalse(model.checkpoint(state))
                state.steps = due
                self.assertTrue(model.checkpoint(state))
                self.rti(state, 0x601a7671)
                state.steps += period
                self.assertFalse(model.checkpoint(state))
                self.assertEqual(model.delivered, 3)

    def test_masked_checkpoint_defers_and_corrupt_return_stops(self):
        state = self.fixture(); model = StartupInterrupts(10)
        state.regs['psw'] = 0x700
        self.assertFalse(model.checkpoint(state))
        self.assertEqual(model.delivered, 0)
        state.regs['psw'] = 0xf00
        model.checkpoint(state); self.rti(state, 0x601a7671)
        state.regs['d0'] ^= 1
        with self.assertRaisesRegex(ValueError, 'changed registers'):
            model.checkpoint(state)


if __name__ == '__main__':
    unittest.main()
