#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Check checkpoint boundaries, coherent aliases and trace tails before boot work."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from penf_emulator import Region, execute


class CheckpointTests(unittest.TestCase):
    def test_changed_capture_omits_unchanged_but_includes_alias_write(self):
        regions = [Region('code',0x60000000,b'\x60\x75','rx'),
                   Region('ram',0x61000000,bytes(4),'rw',True),
                   Region('alias',0xa1000000,bytes(4),'rw',True,'ram'),
                   Region('untouched',0x61001000,b'\xa5'*4096,'rw',True)]
        regs={'pc':0x60000000,'a0':0xa1000000,'a1':0x61000000,'d0':0x12345678}
        full=execute(regions,regs,0x60000002)
        changed=execute(regions,regs,0x60000002,changed_captures=True)
        self.assertEqual(full['registers'],changed['registers'])
        self.assertEqual(full['completed'],changed['completed'])
        self.assertEqual(changed['memory'],full['memory'][:2])
        self.assertEqual([m['name'] for m in changed['memory']],['ram','alias'])
        regs['d0']=0
        self.assertEqual(execute(regions,regs,0x60000002,changed_captures=True)['memory'],[])

    def test_alias_write_is_visible_to_other_view(self):
        # mov d0,(a0); mov (a1),d1
        r = execute([Region('code', 0x60000000, b'\x60\x75', 'rx'),
                     Region('ram', 0x61000000, bytes(4), 'rw', True),
                     Region('alias', 0xa1000000, bytes(4), 'rw', True, 'ram')],
                    {'pc': 0x60000000, 'a0': 0xa1000000, 'a1': 0x61000000, 'd0': 0x12345678}, 0x60000002)
        self.assertEqual(r['status'], 'returned')
        self.assertEqual(r['registers']['d1'], 0x12345678)
        self.assertEqual([m['hex'] for m in r['memory']], ['78563412']*2)

    def test_breakpoint_stops_before_instruction_and_can_resume(self):
        regions = [Region('code', 0x60000000, b'\x40\x40\x40', 'rx')]
        r = execute(regions, {'pc': 0x60000000, 'd0': 10}, 0x60000003,
                    breakpoints=[0x60000001], trace_limit=10)
        self.assertEqual(r['status'], 'breakpoint')
        self.assertEqual(r['registers']['d0'], 11)
        self.assertEqual(r['completed'], 1)
        continued = execute(regions, r['registers'], 0x60000003)
        self.assertEqual(continued['status'], 'returned')
        self.assertEqual(continued['registers']['d0'], 13)

    def test_tail_is_last_snapshots_in_chronological_order(self):
        r = execute([Region('code', 0x60000000, b'\x40'*10, 'rx')],
                    {'pc': 0x60000000}, 0x6000000a, trace_limit=3, trace_tail=True)
        self.assertEqual([s['d0'] for s in r['trace']], [7, 8, 9])
        self.assertEqual(r['trace_start_instruction'], 7)
        self.assertTrue(r['trace_truncated'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
