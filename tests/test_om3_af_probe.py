# Copyright 2026 tsmkirby (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""OM-3 AF probe checks. Synthetic cases need no firmware.

Set OM3_MAIN to the exact decoded stock main (component 0100) to also check
the documented exact-build observations; that case is skipped otherwise.
"""
import os
import struct
import sys
import tempfile
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from om3_af_probe import MAIN, TABLE, checked_input, decode_envelope, menu_pages, words

HANDLERS = [hex(0x60000000 + i) for i in range(93)]


class EnvelopeTests(unittest.TestCase):
    def test_af_start_request_payload_and_reply(self):
        request = struct.pack("<4I", 6, 0x1234, 0x2A, 0x70001000)
        payload = struct.pack("<2I", 5, 4)
        reply = struct.pack("<H2xII", 1, 0x1234, 0x70001000)
        result = decode_envelope(HANDLERS, request, payload, reply)
        self.assertEqual(result["command"], "0x2a")
        self.assertEqual(result["handler"], HANDLERS[0x2A])
        self.assertEqual((result["kind_word"], result["flags_word"]), (5, "0x4"))
        self.assertEqual(result["reply"]["status_u16"], "0x1")
        self.assertEqual(result["reply"]["correlation_word"], "0x1234")
        self.assertFalse(result["exempt_from_context_0x94_deferral"])

    def test_payload_ignored_for_other_commands(self):
        request = struct.pack("<4I", 6, 0, 0x4A, 0)
        result = decode_envelope(HANDLERS, request, struct.pack("<2I", 5, 4))
        self.assertNotIn("kind_word", result)
        self.assertTrue(result["exempt_from_context_0x94_deferral"])

    def test_out_of_table_command_has_no_handler(self):
        result = decode_envelope(HANDLERS, struct.pack("<4I", 0, 0, 93, 0))
        self.assertIsNone(result["handler"])

    def test_rejects_wrong_lengths(self):
        with self.assertRaises(ValueError):
            decode_envelope(HANDLERS, bytes(15))
        with self.assertRaises(ValueError):
            decode_envelope(HANDLERS, bytes(16), reply=bytes(11))
        with self.assertRaises(ValueError):
            decode_envelope(HANDLERS, struct.pack("<4I", 0, 0, 0x2B, 0), bytes(7))


class InputTests(unittest.TestCase):
    def test_checked_input_rejects_wrong_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.bin"
            path.write_bytes(bytes(16))
            with self.assertRaises(ValueError):
                checked_input(path, 16, MAIN)
            with self.assertRaises(ValueError):
                checked_input(path, 17, MAIN)


@unittest.skipUnless(os.environ.get("OM3_MAIN"), "set OM3_MAIN to the exact decoded stock main")
class ExactBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = checked_input(Path(os.environ["OM3_MAIN"]), 33_554_368, MAIN)

    def test_per_button_page_rows(self):
        pages = menu_pages(self.image)
        rows = pages[27]["rows"]
        self.assertEqual(pages[27]["descriptor"], "0x6158f0f8")
        self.assertEqual([r["id"] for r in rows], [2154, 2155])
        self.assertEqual([r["address"] for r in rows], ["0x6158dc44", "0x6158dc68"])
        self.assertTrue(all(r["option_values"] == [1, 0] for r in rows))
        self.assertEqual([r["id"] for r in pages[28]["rows"]], [238, 1692, 1693])

    def test_queue95_af_handlers(self):
        handlers = words(self.image, TABLE, "93I")
        self.assertEqual([hex(h) for h in handlers[0x2A:0x2D]],
                         ["0x603c86d7", "0x603c8af3", "0x603c8d14"])


if __name__ == "__main__":
    unittest.main()
