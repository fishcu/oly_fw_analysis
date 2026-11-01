"""Boundary checks for the offline tone graph native drawing prerequisite."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from penf_tone_display_probe import (
    BACKEND, GRAPH, assemble, fixture, graph_commands, paint, tone_paint_dispatch, validate_input,
)


def inputs():
    return dict(lut=[(i*1023+127)//255 for i in range(256)],
                marker_indices=[0, 30, 118, 210, 255])


class ToneDisplayBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory()
        cls.code = assemble(Path(cls.scratch.name))

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_optimized_cli_cannot_create_evidence(self):
        tool = Path(__file__).resolve().parents[1] / 'tools/penf_tone_display_probe.py'
        output = Path(self.scratch.name) / 'optimized-output'
        result = subprocess.run([sys.executable, '-O', str(tool), '--fixture', 'unused.json',
                                 '--out', str(output)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Native display evidence requires assertions', result.stderr)
        self.assertFalse(output.exists())

    def test_optimized_import_cannot_bypass_evidence_guard(self):
        tools = Path(__file__).resolve().parents[1] / 'tools'
        code = f"import sys\nsys.path.insert(0, {str(tools)!r})\nimport penf_tone_display_probe\n"
        result = subprocess.run([sys.executable, '-O', '-c', code], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Native display evidence requires assertions', result.stderr)

    def test_native_clip_and_context_isolation(self):
        s = fixture(self.code, [(5, (0, 0, 100, 100)), (5, (50, 50, 60, 60))],
                    clip=(10, 20, 30, 40))
        result = paint(s)
        self.assertEqual([(d['x'], d['y'], d['width'], d['height'])
                          for d in result['draws']], [(10, 20, 21, 21)])
        self.assertTrue(result['caller_context_unchanged'])
        self.assertTrue(result['backend_unchanged'])
        self.assertTrue(result['stack_restored'])
        self.assertTrue(result['callee_saved_registers_unchanged'])

    def test_rejected_layers_never_submit(self):
        for layer in (2, 3):
            with self.subTest(layer=layer):
                result = paint(fixture(self.code, [(5, GRAPH)], layer=layer))
                self.assertEqual(result['draws'], [])

    def test_tone_dispatch_stops_before_unqualified_traversal(self):
        result = tone_paint_dispatch()
        self.assertEqual(result['stopped_at'], '0x60bbe8d4')
        self.assertEqual(result['modeled_functions'], [])
        self.assertFalse(result['complete_paint_returned'])

    def test_empty_command_list_returns(self):
        self.assertEqual(paint(fixture(self.code, []))['draws'], [])

    def test_unknown_backend_remains_a_strict_stop(self):
        s = fixture(self.code, [(5, GRAPH)])
        s.write(BACKEND+92, struct.pack('<I', 0x19010000))
        with self.assertRaisesRegex(RuntimeError, 'memory_fault'):
            paint(s)

    def test_endpoints_move_vertically_and_inner_markers_stay_fixed(self):
        before = inputs()
        after = inputs()
        after['lut'][0], after['lut'][-1] = 64, 950
        _, old = graph_commands(before)
        _, new = graph_commands(after)
        self.assertEqual(old[1:4], new[1:4])
        for i in (0, 4):
            self.assertEqual(old[i]['x'], new[i]['x'])
            self.assertNotEqual(old[i]['y'], new[i]['y'])

    def test_invalid_signal_shapes_are_rejected(self):
        for key, value in [('lut', [0]*255), ('lut', [1024]*256),
                           ('lut', [True]*256), ('marker_indices', [0, 30, 30, 210, 255]),
                           ('marker_indices', [1, 30, 118, 210, 255]),
                           ('marker_indices', [0, 30, 118, 256, 255])]:
            with self.subTest(key=key, value=str(value[:5])):
                data = inputs()
                data[key] = value
                with self.assertRaises(ValueError):
                    validate_input(data)


if __name__ == '__main__':
    unittest.main(verbosity=2)
