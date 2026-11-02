"""Shared patch builder on synthetic containers; no firmware, toolchain or camera needed."""
import hashlib
import json
import struct
import sys
import tempfile
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from oly_container import encode, parse, sum32
import oly_patch


def sha(data):
    return hashlib.sha256(data).hexdigest()


def component(kind, payload):
    header = bytearray(32)
    header[:4] = b"OE\x12\x20"
    struct.pack_into("<IIHHH", header, 8, 0x40000000 + kind, len(payload), 0x3101, 0, kind)
    trailer = bytearray(header)
    struct.pack_into("<I", trailer, 28, -(2 * sum32(header) + sum32(payload)) & 0xFFFFFFFF)
    return bytes(header) + encode(payload) + bytes(trailer)


MAIN = bytes(range(256)) * 2
OTHER = bytes(255 - (i & 255) for i in range(256))
STOCK = component(0x100, MAIN) + component(0x101, OTHER)
BASE = 0x60021020


def definition(**overrides):
    patched = bytearray(MAIN)
    patched[16:20] = b"\xde\xad\xbe\xef"
    spec = {
        "schema": "oly-patch/1", "name": "test", "model": "synthetic", "firmware": "0",
        "camera_tested": False,
        "stock": {"sha256": sha(STOCK)},
        "components": {"0x100": {"cpu_base": hex(BASE), "before_sha256": sha(MAIN), "after_sha256": sha(bytes(patched))}},
        "ranges": [{"component": "0x100", "name": "edit", "address": hex(BASE + 16), "bytes": 4,
                    "before_sha256": sha(MAIN[16:20]), "after_sha256": sha(b"\xde\xad\xbe\xef")}],
        "data_edits": [{"component": "0x100", "name": "edit", "address": hex(BASE + 16), "after": "deadbeef"}],
        "package": {"components": "all", "file": "DCOLYMP/E0009999.BIN"},
    }
    spec.update(overrides)
    return spec, bytes(patched)


class PatchBuilderTests(unittest.TestCase):
    def run_build(self, spec, **kwargs):
        temp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (temp / "patch").mkdir()
        (temp / "patch" / "patch.json").write_text(json.dumps(spec))
        (temp / "stock.bin").write_bytes(STOCK)
        report = oly_patch.build(temp / "patch", temp / "stock.bin", temp / "out", **kwargs)
        return temp / "out", report

    def test_build_and_package(self):
        spec, patched = definition()
        out, report = self.run_build(spec, decoded=True, untested=True)
        self.assertEqual((out / "decoded/0100.bin").read_bytes(), patched)
        blocks = parse((out / "install/DCOLYMP/E0009999.BIN").read_bytes())
        self.assertEqual([b.payload for b in blocks], [patched, OTHER])
        self.assertEqual((out / "restore-stock/DCOLYMP/E0009999.BIN").read_bytes(), STOCK)
        self.assertEqual(report["components"]["0x100"]["changed_bytes"], 4)

    def test_untested_package_withheld_by_default(self):
        out, report = self.run_build(definition()[0])
        self.assertFalse((out / "install").exists())
        self.assertIsNone(report["install"])

    def test_selected_components_only(self):
        spec = definition(package={"components": ["0x100"], "file": "X.BIN"}, camera_tested=True)[0]
        out, _ = self.run_build(spec)
        self.assertEqual(len(parse((out / "install/X.BIN").read_bytes())), 1)

    def test_rejects_wrong_stock(self):
        spec = definition(stock={"sha256": "0" * 64})[0]
        with self.assertRaisesRegex(ValueError, "Wrong stock"):
            self.run_build(spec)

    def test_rejects_changed_original_bytes(self):
        spec = definition()[0]
        spec["ranges"][0]["before_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Original bytes differ"):
            self.run_build(spec)

    def test_rejects_wrong_result(self):
        spec = definition(data_edits=[{"component": "0x100", "name": "edit", "address": hex(BASE + 16), "after": "deadbeee"}])[0]
        with self.assertRaisesRegex(ValueError, "differ from the reference"):
            self.run_build(spec)

    def test_rejects_undeclared_and_overlapping(self):
        spec = definition(data_edits=[{"component": "0x100", "name": "other", "address": hex(BASE + 32), "after": "00"}])[0]
        with self.assertRaisesRegex(ValueError, "Unexpected"):
            self.run_build(spec)
        spec = definition()[0]
        spec["ranges"].append(dict(spec["ranges"][0], name="overlap", address=hex(BASE + 18), before_sha256=sha(MAIN[18:22])))
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            self.run_build(spec)

    def test_rejects_missing_range(self):
        with self.assertRaisesRegex(ValueError, "Not every declared range"):
            self.run_build(definition(data_edits=[])[0])

    def test_recorded_package_hash_enforced(self):
        spec = definition(package={"components": "all", "file": "X.BIN", "sha256": "0" * 64})[0]
        with self.assertRaisesRegex(ValueError, "Package sha256"):
            self.run_build(spec)


if __name__ == "__main__":
    unittest.main()
