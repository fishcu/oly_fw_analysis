# PEN-F five-point tone candidate

This composes body-controlled black and white endpoints with the existing
COLOR1–3 shadow, middle and highlight controls, on top of the pinned PEN-F HSL
release. It includes native profile/bank storage, capture-owner snapshots,
per-image tone processing, a five-point control graph and exact endpoint labels.
The main image and update container build reproducibly. Verification is offline
and bounded; no camera was flashed and physical operation remains unqualified.

## Body controls

Open the native COLOR1, COLOR2 or COLOR3 tone editor. INFO cycles through
shadow/highlight, middle, then endpoints. The first two pages retain their
native controls. On the endpoint page:

| Input | Effect |
|---|---|
| Right / left | Raise / lower the black endpoint |
| Up / down | Raise / lower the white endpoint |
| Front dial | Adjust black |
| Rear dial | Adjust white |
| Held OK | Reset this profile's endpoints to black0 / white1023 |
| INFO | Return to the shadow/highlight page |

Each relative input moves16 output codes, bounded by the current reference
shadow/highlight height. A final partial step keeps its exact value. The label
`B+0064 W-0063`, for example, means black64 and white960. It shows effective
reference coordinates, including clamping. Moving an endpoint preserves the
entire interval containing the three inner controls; it does not raise or lower
those inner heights. Switching profile or exiting cannot reinterpret an
unrelated native property request as an endpoint edit.

The graph is a control reference generated from the native identity LUT, zero
legacy contrast, and the current three inner settings. Actual image processing
uses the selected native image base and computes its own bounds and clamping.
The graph therefore does not promise to reproduce every image-processing effect.
Neutral endpoints preserve native output exactly, including the original
zero-inner-control gate. Unsupported or null selected LUTs preserve stock processing. The endpoint adapter
targets the ordinary COLOR builder; native mask/creative bypasses and separate
alternative-effect paths retain stock processing. MONO and other picture modes
retain their ordinary behavior.

Endpoints use native COLOR profile storage and custom-bank recall. Full native
settings reset clears them; held OK resets just the current endpoint page.
Existing HSL behavior and its Value OSD are retained. Endpoint extension records
for external settings backup/export and ORF metadata are not implemented. Those
formats must not be relied on to transfer endpoint state.

## Reproducible build

Requirements are Python3 and GNU MN103 assembler, linker, objcopy, objdump and
nm, plus the complete official PEN-F3.1 build3101 container. The default tools
are the existing `toolchains/tone-binutils-build` build. Override them with
`--as`, `--ld`, `--objcopy`, `--objdump` and `--nm` if needed. Building does not
require the emulator executable, Pillow or decoded files under `analysis/`.

```sh
python3 patches/tone/pen-f/build.py \
  --stock /path/to/OLY_E_122_3101_0000_0000.BIN \
  --out generated/pen-f-five-point
```

The output directory must be new. The builder rejects a different stock hash
before creating it. It rebuilds and checks the pinned HSL release, uses the main
payload decoded from the supplied stock, composes the new source, and retains
the HSL-modified OSD. Both component checksums, exact decode/encode round trip,
nonoverlapping before/after ranges, and unchanged header/trailer metadata are
checked. Python optimization flags that would disable assertions are rejected.

Outputs include `install/DCOLYMP/E1229999.BIN`, `candidate/main.bin`,
`candidate/placement.json`, and `build.json`. The latter records input/output,
source and tool hashes. `hsl-reference/` contains the exact baseline build and
its stock restore container. Producing these files performs no device access.

| Artifact | SHA-256 |
|---|---|
| Required full stock | `77398610b379f80238117f31a6d5bbf65d608b49ec563666c64d84367e969f2c` |
| Pinned HSL package | `4f9a36e6742728ded3d9b443915355f1d1eea0371e1da673f322de970994f717` |
| Five-point main | `fbb6d8bf4b793d6ae4061bbd5eb8749bb8302a757bd06b167eb95ce89b494aca` |
| Five-point container,44433408 bytes | `c53ecf80967cf347f2cab17a6a9ee3dcd7f1c0af907843ab7c424d43f899bc4b` |
| Retained HSL OSD | `f713df2a2d7d57a511e55cabb0f84ac4d612f99c58df4502a89b32bd8580084c` |

## Verification and limits

Run the build integrity tests with the full stock input:

```sh
PENF_STOCK_CONTAINER=/path/to/OLY_E_122_3101_0000_0000.BIN \
  python3 -m unittest discover -s tests -p test_penf_tone_build.py -v
```

Native probes additionally require the existing strict MN103 engine and pinned
decoded firmware. Graph/font probes require Pillow. Run the graph contracts,
including the relocated input and image paths, with:

```sh
PYTHONPATH=tools python3 tools/penf_tone_graph_probe.py --out /tmp/tone-graph-check
```

The optional `--full-reference-domain` checks all3375 legal inner-control
triples. That native domain has been exhausted with exact endpoints, range,
monotonicity and fixed reference bounds30/210. The default graph audit covers
all33 children on all three pages/profiles, both measured layouts, independently
computed rectangle geometry, exact numeric glyph requests, register/context
preservation, missing-section fallbacks and whole-receiver invalidation.

Body redraw has a direct native path after setter completion: the arrow/dial
or held-OK continuation returns1; the ordinary controller dispatcher calls its
outer viewer, which publishes parameters118 and209 even when inner values are
unchanged. Twenty-seven native join cases establish these return, dispatch and
publication boundaries without function models. Identical118 publication still
marks observers. The new receiver update then requests full graph invalidation.
These are explicit native joins after unchanged setter/refresh prerequisites;
physical button delivery, asynchronous completion and LCD delivery are not
claimed.

The graph's complete return fixture models line-storage allocation/free and
raster submission; native parsing, metrics, clipping and backend paths execute.
A separate probe reaches the real allocator stop without supplying that
allocation. The measured conditional paint path uses2000 stack bytes below its
caller. The GUI worker allocates8704 bytes, but its preexisting stack usage and
full-boot high-water mark are unknown. Loaded-tail placement checks establish
native boundaries and bounded load/execute/reload behavior, not every possible
computed write or physical permission. No ISP pixel engine or complete camera
boot is simulated.

The bounded units and their exact APIs are documented in
[TONE_INTEGRATION.md](../../../docs/color/pen-f/TONE_INTEGRATION.md),
[TONE_TRANSPORT.md](../../../docs/color/pen-f/TONE_TRANSPORT.md),
[TONE_EDITOR.md](../../../docs/color/pen-f/TONE_EDITOR.md), and
[TONE_GRAPH.md](../../../docs/color/pen-f/TONE_GRAPH.md).
