"""Input-free guards for the source-only aperture-ring builder."""
import importlib.util
import json
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from oly_container import encode, parse, reconstruct, replace_payload, sum32

module = importlib.util.spec_from_file_location('aperture_ring_build', ROOT/'patches/aperture-ring/build.py')
patch = importlib.util.module_from_spec(module)
module.loader.exec_module(patch)


def block(kind, address):
    header = bytearray(32)
    header[:4] = b'OE\x12\x20'
    struct.pack_into('<IIHHH', header, 8, address, 256, 0x3101, 0, kind)
    payload = bytes(range(256))
    trailer = bytearray(header)
    struct.pack_into('<I', trailer, 28, -(2*sum32(header)+sum32(payload)) & 0xffffffff)
    return bytes(header)+encode(payload)+bytes(trailer)


class ApertureRingBuildTests(unittest.TestCase):
    def setUp(self):
        self.original = bytes(range(64))
        self.ranges = [dict(name='hook', address='0x1004', bytes=3,
                           before_sha256=patch.sha(bytes((4, 5, 6))),
                           after_sha256=patch.sha(b'ABC'))]
        self.sections = dict(hook=b'ABC')

    def test_penf_source_profiles_match_their_pins(self):
        for model in patch.MODELS:
            with self.subTest(model=model):
                spec = patch.load_spec(model)
                self.assertEqual(spec['loaded_section'], 1)
                self.assertIn('ring.S', spec['source_sha256'])
                self.assertIn('layout.ld', spec['source_sha256'])
                self.assertEqual(spec['ae_probe']['official_minimum'], '0x6184d706')
                self.assertEqual(spec['ae_probe']['bounds_layout'],
                                 ['effective_av', 'official_minimum', 'official_maximum'])

    def test_original_hsl_conflict_and_relocated_ranges(self):
        hsl = json.loads((ROOT/'patches/hsl/pen-f/patch.json').read_text())
        standalone = patch.load_spec('pen-f')
        overlaps = patch.range_intersections(standalone['ranges'], hsl['main_ranges'])
        self.assertEqual(len(overlaps), 6)
        self.assertIn(dict(left='state', right='wifi_read_tail', start='0x601cafb0',
                           end_exclusive='0x601cafb4'), overlaps)
        combined = patch.load_spec('pen-f-hsl')
        moved = {(r['name'], r['address']) for r in combined['hsl_relocated_sections']}
        retained = [r for r in hsl['main_ranges'] if (r['name'], r['address']) not in moved]
        self.assertEqual(patch.range_intersections(combined['ranges'], retained), [])
        self.assertEqual(combined['state_address'], '0x601caa40')

    def test_touching_range_endpoints_are_not_overlaps(self):
        self.assertEqual(patch.range_intersections([dict(name='a', address='0x1000', bytes=4)],
                                                 [dict(name='b', address='0x1004', bytes=8)]), [])

    def test_unknown_model_cannot_select_another_source_directory(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            patch.load_spec('../hsl')

    def test_reject_wrong_stock_before_decode(self):
        spec = patch.load_spec('pen-f')
        with self.assertRaisesRegex(ValueError, 'stock container SHA'):
            patch.stock_blocks(b'not firmware', spec)

    def test_stock_guard_checks_layout_and_decoded_identity(self):
        raw = block(0x100, 0x403a0000)+block(0x101, 0x41800000)
        spec = dict(stock_container_sha256=patch.sha(raw), component_count=2,
                    original_main_sha256=patch.sha(bytes(range(256))))
        self.assertEqual(len(patch.stock_blocks(raw, spec)), 2)
        with self.assertRaisesRegex(ValueError, 'component layout'):
            patch.stock_blocks(raw, dict(spec, component_count=1))
        with self.assertRaisesRegex(ValueError, 'decoded main SHA'):
            patch.stock_blocks(raw, dict(spec, original_main_sha256='0'*64))

    def test_only_declared_bytes_are_changed(self):
        actual = patch.apply_sections(self.original, 0x1000, self.ranges, self.sections)
        self.assertEqual(actual, self.original[:4]+b'ABC'+self.original[7:])

    def test_reject_missing_and_unexpected_sections(self):
        for sections in ({}, dict(self.sections, extra=b'X')):
            with self.subTest(sections=sections), self.assertRaisesRegex(ValueError, 'section'):
                patch.apply_sections(self.original, 0x1000, self.ranges, sections)

    def test_reject_duplicate_names_and_overlaps(self):
        for extra in (self.ranges[0], dict(self.ranges[0], name='second', address='0x1005')):
            sections = dict(self.sections, **{extra['name']: b'ABC'})
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                patch.apply_sections(self.original, 0x1000, self.ranges+[extra], sections)

    def test_reject_outside_empty_and_truncated_ranges(self):
        for address, size in (('0xfff', 3), ('0x1040', 3), ('0x103f', 3), ('0x1004', 0)):
            with self.subTest(address=address, size=size), self.assertRaisesRegex(ValueError, 'outside'):
                patch.apply_sections(self.original, 0x1000,
                    [dict(self.ranges[0], address=address, bytes=size)], self.sections)

    def test_reject_altered_original_and_compiled_bytes(self):
        with self.assertRaisesRegex(ValueError, 'Original bytes'):
            patch.apply_sections(bytes(64), 0x1000, self.ranges, self.sections)
        for data in (b'AB', b'ABD'):
            with self.subTest(data=data), self.assertRaisesRegex(ValueError, 'Compiled bytes'):
                patch.apply_sections(self.original, 0x1000, self.ranges, dict(hook=data))

    def test_packages_only_main_preserving_metadata_and_restore(self):
        blocks = parse(block(0x100, 0x403a0000)+block(0x101, 0x41800000))
        main = bytes(256)
        spec = dict(patched_main_sha256=patch.sha(main), package_bytes=320,
                    install_sha256=patch.sha(reconstruct([replace_payload(blocks[0], main)])),
                    restore_sha256=patch.sha(reconstruct(blocks[:1])))
        install, restore = patch.packages(blocks, main, spec)
        self.assertEqual(restore, block(0x100, 0x403a0000))
        decoded = parse(install)
        self.assertEqual(len(decoded), 1)
        self.assertEqual(decoded[0].header, blocks[0].header)
        self.assertEqual(decoded[0].trailer[:28], blocks[0].trailer[:28])
        self.assertEqual(decoded[0].payload, main)
        for change in (dict(package_bytes=336), dict(install_sha256='0'*64),
                       dict(restore_sha256='0'*64), dict(patched_main_sha256='0'*64)):
            with self.subTest(change=change), self.assertRaises(ValueError):
                patch.packages(blocks, main, dict(spec, **change))

    def test_combination_requires_exact_hsl_osd_and_restores_both_components(self):
        blocks = parse(block(0x100, 0x403a0000)+block(0x101, 0x41800000))
        main, osd = bytes(256), blocks[1].payload
        spec = dict(patched_main_sha256=patch.sha(main), package_bytes=640,
            hsl_release='synthetic', hsl_osd_sha256=patch.sha(osd),
            install_sha256=patch.sha(reconstruct([replace_payload(blocks[0], main), blocks[1]])),
            restore_sha256=patch.sha(reconstruct(blocks)))
        install, restore = patch.packages(blocks, main, spec, osd)
        self.assertEqual(len(parse(install)), 2)
        self.assertEqual(parse(install)[1].payload, osd)
        self.assertEqual(restore, reconstruct(blocks))
        for invalid in (None, bytes(256)):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, 'Exact HSL OSD'):
                patch.packages(blocks, main, spec, invalid)


if __name__ == '__main__':
    unittest.main()
