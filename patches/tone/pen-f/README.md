# PEN-F five-point tone candidate

COLOR1–3 have five vertically adjustable points at **0%,25%,50%,75%,100%**.
Black, shadow, middle, highlight and white form one nondecreasing piecewise
linear transfer. The camera controls, graph, native profile/bank storage and
per-image processing use the same state. The candidate retains the pinned HSL
release and Value OSD. Building performs no camera access or flashing.

This revision replaces the earlier endpoint-only design. A first equal-quarter
candidate froze before the tone screen appeared on a camera. The current build
corrects unaligned native lookup tables and UTF-16 stores; its correction has
bounded offline verification. A subsequent camera report confirmed that the
screen opens, but a white-only realtime-update delay remains unresolved.
This build corrects the physical front/rear dial assignment; it does not claim
to resolve that delay.

## Body controls

Open the native COLOR1, COLOR2 or COLOR3 tone editor. INFO cycles
shadow/highlight → middle → black/white → shadow/highlight.

| Page | Left/right | Down/up | Front dial | Rear dial | Held OK |
|---|---|---|---|---|---|
| Shadow/highlight | Lower/raise shadow | Lower/raise highlight | Highlight | Shadow | Reset S/H toward256/768 within unchanged neighbors |
| Middle | Adjust middle | Adjust middle | Middle | Middle | Reset M toward0 within S/H |
| Black/white | Lower/raise black | Lower/raise white | White | Black | Reset B/W to0/1023 |

The rear dial's positive native event lowers its selected point; the front
dial's positive event raises its selected point. Arrow directions in the table
are literal camera directions. Middle uses−7..+7, with height512+32×M.
The other four coordinates use16-code increments, with a final31-code interval
from992 to1023. Only the selected coordinate moves; adjacent points bound it.
Equal neighboring heights are allowed.

The native footer names the current page and shows its selected values.
Examples are `明部・暗部 S0256 H0768`, `中間部 M+0`, and
`黒点・白点 B0000 W1023`, followed by the native INFO icon. Non-Japanese languages
use short ASCII page names. S/H/B/W are absolute output codes0..1023, not
signed native tone settings. Native RESET controls remain visible.

The graph shows the exact five-point transfer using an identity input. Image
processing applies it after the selected native base and the native legacy-only
contrast stage. It therefore need not match every image effect. Neutral five-point
state is exact identity for all1024 integer inputs. The original native H/M/L
overlay is replaced for these custom COLOR requests; its former heights and
sample positions are intentionally not preserved.

All five coordinates occupy one atomic native part1 profile word. Existing
endpoint words and native H/M/L settings migrate consistently on first use;
[the state contract](../../../docs/color/pen-f/TONE_POINTS.md) defines rounding,
projection and invalid-data behavior. Native bank recall and full reset use the
existing settings machinery. External settings export/backup and ORF extension
records do not carry this new word.

Supported tagged requests always rebuild, including neutral reset, even when
the stock comparator sees unchanged native controls. The earlier endpoint cache
fix is retained. Invalid producer relationships, absent late sections, null or
unsupported selected LUTs and native mask/creative bypasses keep their stock
processing paths. The separate alternative-effect path is outside this feature.
MONO, other picture modes and unrelated native editor families retain their
ordinary behavior.

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
| Five-point main | `3c4c065fc0c4d6c4a8d3f39d6f45505853fd2efc8d6b42e934c465aab3c5982f` |
| Five-point container,44433408 bytes | `b5799d614d49d9478e4a92ec80913585192bb20d440f3afcb360b8a9c451dc3a` |
| Retained HSL OSD | `f713df2a2d7d57a511e55cabb0f84ac4d612f99c58df4502a89b32bd8580084c` |

The candidate main and container hashes for each build are recorded in `build.json`.

## Verification and limits

The core probe executes canonical decode, legacy migration, selected-axis edits
and all1024 transfer inputs for48 representative states. It checks neutral exact
identity, monotonicity, quantization edges and callee/stack preservation against
an independent integer specification. The native image matrix covers selected
and override bases, both variants and legacy-only processing. Sequential cached
changes/reset use the actual stock retained updater and comparator.

```sh
PYTHONPATH=tools python3 tools/penf_tone_points_probe.py --out /tmp/tone-points
PYTHONPATH=tools python3 tools/penf_tone_integration_probe.py --out /tmp/tone-image
PYTHONPATH=tools python3 tools/penf_tone_graph_probe.py --out /tmp/tone-graph
PYTHONPATH=tools python3 tools/penf_tone_viewer_probe.py --out /tmp/tone-viewer
PENF_STOCK_CONTAINER=/path/to/OLY_E_122_3101_0000_0000.BIN \
  python3 -m unittest discover -s tests -p 'test_penf_tone*.py' -v
```

Native probes require the pinned decoded firmware and MN103 execution harness;
viewer/font fixtures additionally require Pillow. Build integrity checks cover
wrong-stock rejection, optimized-Python rejection, exact round trips, range
checks, unchanged metadata and retained HSL OSD. The optional graph
`--full-reference-domain` exhausts all3375 legal legacy H/M/L migration tuples;
it is outside the default suite.

All three pages send explicit canonical words through the unchanged GUI setter.
The native viewer publication wrapper adds the actual selected values to
parameter118, preserves the first-publication flag, and keeps the existing
whole-receiver invalidation tail. Twenty-seven earlier native joins establish
the successful input→controller→outer-viewer publication route after setter
completion. The new footer changes real displayed content rather than spare
payload bytes. Async setter completion, event queue delivery and physical LCD
refresh timing remain outside these fixtures; this is not a claim that the
reported camera display delay has been physically resolved.

The painter owns its context copy and LUT. Its native drawing paths are executed
up to declared raster-submission models, without a custom text allocator.
The native footer uses actual parsing, metrics and clipping with explicit
line-storage/raster models. No physical pixels or ISP pixel engine are simulated.
The GUI worker allocates8704 stack bytes, but full-boot stack usage is unknown.
Loaded-tail bounds and load/execute/reload fixtures do not prove absence of all
later computed/DMA writes or establish physical execution permissions.

Details: [state](../../../docs/color/pen-f/TONE_POINTS.md),
[image adapter](../../../docs/color/pen-f/TONE_INTEGRATION.md),
[transport](../../../docs/color/pen-f/TONE_TRANSPORT.md),
[editor](../../../docs/color/pen-f/TONE_EDITOR.md),
[graph and publication](../../../docs/color/pen-f/TONE_GRAPH.md),
[earlier cache defect](../../../docs/color/pen-f/TONE_REALTIME.md),
[entry alignment regression](../../../docs/color/pen-f/TONE_ENTRY_ALIGNMENT.md).
