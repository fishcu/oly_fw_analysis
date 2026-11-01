# Native five-point control graph

`tools/penf_tone_graph_candidate.py` composes the graph with the endpoint editor,
profile storage and per-image adapter. The [feature README](../../../patches/tone/pen-f/README.md) documents the
composed container builder. Physical camera qualification remains separate.

The graph uses the current COLOR1–3 native high/middle/low values, the native
identity LUT, and zero legacy contrast inputs. The same native conversion,
inner overlay and endpoint kernel drive its line and five markers. It is a
**control reference**, not the selected per-image ISP base. Image processing
computes its own signal bounds and effective endpoint limits. The entire inner
interval remains unchanged in both paths.

On all three pages, the custom curve replaces native graph bitmap children
26–31. On the endpoint page it also filters children5–21 and24–25, including
stale page hints and native inner-value labels. The other pages retain their
native labels. The endpoint row reads `B+dddd W-dddd`: exact effective black
lift and white reduction in 10-bit output codes, after clamping against the
reference inner heights. It does not round a partial final step to a different
setting.

## Native ownership and lifecycle

The paint callback first calls the whole original tone paint method. The new
part then owns a 684-byte context copy and a 512-byte reference LUT in its stack
frame. Drawing changes only the private context; the caller's context after
native paint, shared backend and receiver are preserved. The current controller
provides its actuator at offset0. Exact actuator vtable, immutable COLOR table,
public picture mode54–56, and graph receiver vtable must agree. This access is
within the native GUI callback; no cross-task reference-counted lifetime is
claimed.

Filtering occurs at the native children traversal visibility join
`0x60bf7c40`. The hook uses the original frame's parent and current-child
pointers. Eligible selected children take the native hidden-child branch.
Every other child replays all three displaced loads and resumes the original
visibility call. No visibility bit or child object is changed, so leaving COLOR
or reusing the renderer cannot retain hidden graph children.

Paint, update and traversal entry gates remain in resident sections4/5. They
require the section6/8 loaded mask before entering late code, and retain native
fallback when the late ranges are unavailable. The class update wrapper calls
the original update and then invalidates the entire eligible receiver. This is
needed because an identical parameter118 publication can invalidate only the
native bottom label.

The geometry derives from native child31's current rectangle. Layout0 starts
at x351; layout1 shifts by70. The graph covers256 signal indices and maps
10-bit heights onto256 vertical pixels. Five 5×5 markers indicate endpoints and
reference indices30,118,210. The numeric row spans y400–431 in the measured
native layouts. Native font parsing, metrics and clipping are exercised with
the stock English resources.

## Placement

The complete display source occupies756 bytes across the qualified section
4/5/6/8 tails. Graph composition relocates the reference to `0x610f1e54`, the
selected-mode helper to `0x610f1fd8`, and the late core to `0x6115b014`. The
candidate builder records every linked display chunk and capacity. The full FF
tail boundaries are `60a4fe6c..60a50000`, `60fdc29c..60fdc800`,
`610f1e54..610f2000`, and `6115b014..6115b800`. Neighboring initializer extents,
native section end getters and exact loader ranges were checked. Marker code
at both ends loaded, executed and reloaded. Classified literal/branch matches
in added margins do not identify executable references into those bytes.
These bounded checks do not prove the absence of every later computed or DMA
write. Physical execution permissions and camera boot remain unqualified.

## Reproduce the contracts

Use the existing MN103 emulator/toolchain, decoded pinned firmware and a Python
runtime with Pillow for the font resource fixture:

```sh
PYTHONPATH=tools python3 tools/penf_tone_graph_probe.py --out /tmp/tone-graph-audit
PYTHONPATH=tools python3 -m unittest discover -s tests -p test_penf_tone_graph.py -v
```

The output directory must be new. `--only paint`, `filter`, `fallback`,
`update`, `allocator`, or `composed` runs one contract group. The optional
`--full-reference-domain` exhausts all3375 legal high/middle/low triples through
the actual native reference function, checking endpoints, range, monotonicity
and bounds30/210. It is deliberately outside the default unit suite.

The paint fixtures execute the placed callbacks, native reference and endpoint
math, context copy, rectangle path, font setup/release, text parsing, metrics,
clipping and backend. The whole original paint uses an explicitly empty child
list; the actual traversal join is tested separately for all33 child pointers,
three profiles and three pages. Legal current settings are−7..7. If an internal
current record is invalid, the reference rejects it; graph filtering may still
apply and no claim of preserving stock graph artwork is made for corrupted
records. The tests compare every new rectangle against
an independent integer oracle and check the complete numeric glyph request
string and row bounds.

The full paint-return fixture declares models at rectangle raster submission,
12-byte line-storage allocation/free, and glyph raster submission. It records
requests, not physical pixels. A separate fixture permits the real allocator
and stops at its unmapped pool descriptor `61a8e884`, instruction `60bd0ca7`.
The update-wrapper fixture treats the unchanged original update return as an
explicit boundary; its new tail invokes real native invalidation. An attached
receiver sets the root dirty flag and full rectangle before the real event
queue guard at `60bca69c`. Queue delivery and a full button-to-LCD boot session
are not simulated.

The measured conditional paint path reaches a 2000-byte peak below its caller
SP, including native drawing/text nesting under the declared models. The GUI
worker descriptor allocates8704 bytes, but the caller's preexisting stack use
and full-boot high-water mark remain unknown. This measurement is not a
physical stack-safety certification.
