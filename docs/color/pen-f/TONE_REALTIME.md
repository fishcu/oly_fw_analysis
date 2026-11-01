# Endpoint-only rebuild and next-page hint

The user tested candidate5591bb4 on a camera. Endpoint edits were stored, but the image changed only after a native shadow edit. The native retained updater604b3034 and comparator604b2d78 reproduce the cause: they do not compare the new job endpoint word. With unchanged native controls the comparator returns0xc0000000, outside the tone-change mask0x02e8063e. The previous endpoint adapter obeyed that mask and reused the old LUT. Its neutral shortcut also reused a previously modified curve when resetting endpoints.

The adapter now rebuilds every supported, valid tagged ordinary COLOR request, including neutral endpoints. It retains native base selection, the inner-overlay gate, selection early returns, invalid-tag fallback, unsupported-source behavior, and ordinary bypass decisions. It adds no retained state and does not forge native dirty bits. This trades additional native work on unchanged valid requests for a correct active LUT; probe instruction counts describe the executed fixture paths, not camera timing.

`cached_endpoint_cases` runs the actual retained updater and comparator, then consecutive endpoint changes and neutral reset with their resulting mask. Twenty-four transitions cover zero/nonzero native inner settings, selected/override bases, and both variants. They assert the complete active LUT against the independent oracle, unchanged inner interval and native controls, neutral pointer/return compatibility, stack and preserved registers. The graph composition probe runs the same cases through the production-linked entry. These tests use no function models. The measured production-linked builder paths execute6,542–43,308 instructions in this matrix; this is not elapsed camera time.

The middle page previously advertised the native pair page even though INFO now opens endpoints. The candidate replaces only the three repeated COLOR middle query blocks in60cfa110..60cfa28a. The279-byte replacement fits the original378-byte region; its preimage hash is checked before composition. Query order remains middle/high/low, with the same native values, output slots and variant conversion. Other public modes rejoin the unchanged native suffix. No global OSD resource is changed.

The label uses native descriptor format5. The parameter118 descriptor starts at byte10 and ends before byte84, leaving74 bytes. Its inline string starts at descriptor+8; the42-byte ASCII string and24-byte Japanese string both include their terminators. Native resource2778 lookup selects Japanese when its first glyph is明; the pinned34-language table has that glyph only in Japanese. The resulting labels are `黒点・白点@A028@` and `BLACK / WHITE @A028@`, where the native parser renders the INFO token.

The viewer probe compares18 COLOR/profile/control/language cases, and eight rejected-mode cases at the common native suffix after its comparison. It uses an explicit GUI getter-envelope adapter around the actual current-value getter602b9f84. The native formatter runs to the unchanged text setter without models. English/Japanese font parsing, metrics and clipping run through the actual backend with declared models for line allocation/free and raster submission; this does not prove physical pixels.

```sh
PYTHONPATH=tools python3 tools/penf_tone_integration_probe.py --out /tmp/tone-integration-check
PYTHONPATH=tools python3 tools/penf_tone_viewer_probe.py --out /tmp/tone-viewer-check
PYTHONPATH=tools python3 tools/penf_tone_graph_probe.py --out /tmp/tone-composed-check --only composed
```

These use the existing strict MN103 engine and pinned decoded firmware; viewer font probes also need Pillow. The image fix is verified at native request/LUT boundaries. The separate reported graph/BW refresh delay remains unresolved outside the exercised callback joins. Display production code is unchanged, and this revision needs physical retesting before either live-view timing or LCD refresh can be claimed.
