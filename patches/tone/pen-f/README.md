# PEN-F ALL/R/G/B five-point tone candidate

COLOR1–3 each have independent ALL, R, G and B curves with five vertically adjustable points at **0%,25%,50%,75%,100%**.
Black, shadow, middle, highlight and white form one nondecreasing piecewise
linear transfer. The camera controls, graph, native profile/bank storage and
per-image processing use the same state. The candidate retains the pinned HSL
release and Value OSD. Building performs no camera access or flashing.

The underlying equal-quarter ALL editor includes the earlier alignment and
physical dial corrections. The camera screen has been reported to open, while
a white-only realtime-update delay remains unresolved. This RGB extension has
bounded offline verification; its physical channel order and saved JPEG output
still require camera qualification.

## Body controls

Open the native COLOR1, COLOR2 or COLOR3 tone editor. INFO cycles
shadow/highlight → middle → black/white → shadow/highlight.
Trash cycles ALL → R → G → B while retaining the page. Held OK resets that
page of the selected channel. The footer and graph follow the selected channel.

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
Examples are `ALL 明部・暗部 S0256 H0768`, `R 中間部 M+0`, and
`B 黒点・白点 B0000 W1023`, followed by the native INFO icon and DEL hint. Non-Japanese languages
use short ASCII page names. S/H/B/W are absolute output codes0..1023, not
signed native tone settings. Native RESET controls remain visible.

The graph shows the exact five-point transfer using an identity input. ALL image processing applies it after the selected native base and native
legacy-only contrast stage. RGB applies each channel transfer to its native
packed gamma lane, then uses the native hardware upload path. It therefore need not match every image effect. Neutral five-point
state is exact identity for all1024 integer inputs. The original native H/M/L
overlay is replaced for these custom COLOR requests; its former heights and
sample positions are intentionally not preserved.

All five coordinates of one channel occupy one atomic native part1 word.
The twelve cells, explicit channel requests and16-byte acquired snapshots are
documented in [the RGB contract](../../../docs/color/pen-f/TONE_RGB.md). Existing
endpoint words and native H/M/L migrate into ALL on first use; RGB starts neutral;
[the state contract](../../../docs/color/pen-f/TONE_POINTS.md) defines rounding,
projection and invalid-data behavior. Native bank recall and full reset use the
existing settings machinery. External settings export/backup and ORF extension
records do not carry these words.

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
| RGB five-point main | `eab1448dd516303168aa30455a1a1a10f3124a9fd739668846e80cc0f59af4ed` |
| RGB five-point container,44433408 bytes | `cf3c34352d16928240d823882b0dab3e91954383c72d7353e789a7f0a03c9e4c` |
| Retained HSL OSD | `f713df2a2d7d57a511e55cabb0f84ac4d612f99c58df4502a89b32bd8580084c` |

The candidate main and container hashes for each build are recorded in `build.json`.

## Verification and limits

Physical R/G/B lane naming is inferred from low/middle/high packed lanes and
has not been confirmed with a named native calibration or camera measurement.
Native execution verifies each lane independently, selects the actual native
gamma bank once and submits the edited words. The single lane-shift table is
the correction point if physical testing establishes another order. This is an
offline candidate; LCD timing, silicon stage order and saved JPEG color output
remain unqualified. The earlier white-only delay is not claimed fixed.


The earlier 90-test and 27-test results are historical and do not qualify this
build. The 27 tests modeled the complete viewer update, hiding an HSL method
called against the tone viewer's incompatible 120-byte layout. The joined
regression now executes DEL dispatch, native tone/helper construction, the real
tone updater, both callbacks, footer publication, native parameter 118/92-byte
and 209/12-byte copies, helper refresh and the native draw-request wrapper to
its ABI return. The old HSL target fails at viewer offset 120 in the same fixture.

`tone_cycle` uses the viewer's first virtual method, matching the native
controller convention. The audit is under `generated/rgb-tone-del-viewer-fix/audit`.
It retains the failing test, test-only patch, focused logs and exact build hashes.
The new candidate is `generated/rgb-tone-del-viewer-fix/install/DCOLYMP/E1229999.BIN`.
The previous candidate remains in its original output directory.

The fixture models exact allocator returns, camera context properties, status,
logs, timer and GUI notification services. The helper executes its native
status-zero path. The display store has a native empty observer list. Lower
queue/lock services are modeled while the draw wrapper itself returns natively.
These checks do not execute the queue worker, LCD, or physical camera.

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
PYTHONPATH=tools python3 tools/penf_tone_rgb_viewer_probe.py --out /tmp/tone-rgb-viewer
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

The trash regression executes the native constructor at `0x60c87a89`, binding,
axis eligibility and common dispatcher with screen 897. The constructor leaves
actuator offset 100 untouched. The former screen comparison therefore rejected
valid trash presses. Native event `0x9749` sets offset 200 to 1 as an active timeout
flag, which must also permit cycling. The fix removes those two rejection checks
and keeps the profile, current-mode, modal, busy and selection-range checks.
Twelve constructor scenarios cover three COLOR profiles, zero and sentinel heap
contents, and inactive or natively activated timeouts. Each runs all four channel
transitions. Property, status, parameter and timer services have explicit models;
viewer and draw completion remain modeled. Hardware behavior is unverified.

The RGB native probes cover all36 profile/channel/page states, explicit async
requests, held reset, guarded trash dispatch, equal-neutral redraw, all45
four-word owner snapshots, all nine native banks and default reset, real
section1/2/8 load/reload, invalid/unloaded fallback, all256 packed gamma words,
sequential warm-cache edits/reset, source immutability and both hardware upload
banks. `PENF_RGB_AUDIT_DIR=/path/to/new/audit` retains the RGB suite JSON and
synthetic native-rectangle previews. They are fixture renders, not camera captures.

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
