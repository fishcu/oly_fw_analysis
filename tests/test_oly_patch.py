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
from oly_compress import MAGIC, _encode, repack_image
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
    def run_build(self, spec, *, stock=STOCK, **kwargs):
        temp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (temp / "patch").mkdir()
        (temp / "patch" / "patch.json").write_text(json.dumps(spec))
        (temp / "stock.bin").write_bytes(stock)
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

    def test_compressed_component_checks_both_images_and_withholds_install(self):
        raw = b'abcd' * 128
        packed = _encode(b'abcd' * 4, 4, 496) + _encode(b'')
        stored = bytearray(b'\xff' * len(raw))
        stored[:16] = MAGIC
        struct.pack_into('<II', stored, 16, len(packed), len(raw))
        stored[24:32] = bytes(8)
        stored[32:32 + len(packed)] = packed
        target = bytearray(raw)
        target[100:104] = b'edit'
        repacked = repack_image(bytes(stored), bytes(target), split=True, literal_limit=0)
        stock = component(0x100, bytes(stored))
        spec = {
            "schema": "oly-patch/1", "name": "compressed test", "model": "synthetic",
            "firmware": "0", "camera_tested": False, "stock": {"sha256": sha(stock)},
            "components": {"0x100": {"image_transform": "olycompress", "repack": "split",
                "before_sha256": sha(raw), "after_sha256": sha(target),
                "stored_before_sha256": sha(stored), "stored_after_sha256": sha(repacked)}},
            "ranges": [{"component": "0x100", "name": "edit", "offset": hex(100), "bytes": 4,
                        "before_sha256": sha(raw[100:104]), "after_sha256": sha(b'edit')}],
            "data_edits": [{"component": "0x100", "name": "edit", "offset": hex(100), "after": b'edit'.hex()}],
            "package": {"components": "all", "file": "X.BIN"},
        }
        out, report = self.run_build(spec, stock=stock, decoded=True)
        self.assertEqual((out / "decoded/0100.bin").read_bytes(), target)
        self.assertEqual(report["components"]["0x100"]["sha256"], sha(repacked))
        self.assertFalse((out / "install").exists())
        self.assertEqual(parse((out / "restore-stock/X.BIN").read_bytes())[0].payload, stored)
        spec["components"]["0x100"]["stored_after_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Repacked component"):
            self.run_build(spec, stock=stock)


if __name__ == "__main__":
    unittest.main()
