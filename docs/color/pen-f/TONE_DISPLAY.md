# Native tone graph drawing prerequisite

The five-point editor needs vertically adjustable black and white endpoints while the existing inner heights stay fixed. The stock tone display selects bitmap variants. The offline probe now executes native clipping, brush and rectangle code against a supplied 256-entry LUT and five explicit marker indices. It does not install a camera paint callback.

[`tools/penf_tone_display_probe.py`](../../../tools/penf_tone_display_probe.py) assembles a 98-byte command painter at synthetic address `19000000`. That address is a host fixture, not a firmware placement candidate. Each command holds a u32 palette index and four inclusive s16 coordinates. A separate fixture descriptor holds a logical layer, a count, a command pointer and a clip pointer. This descriptor is not a native UI job.

The painter rejects fixture layers 2 and 3 before it changes the drawing context. On layer 1, it copies all 684 context bytes onto its stack, applies the native clip API, disables the pen, sets the brush and calls the native rectangle API for each command. Its synthetic frame uses 716 local bytes and a 16-byte register save, 732 bytes total. This establishes no native UI task stack capacity. Nested native callees need additional stack. The caller's context, shared backend bytes and distinct d2/d3/a2/a3 sentinels remain identical after return in the executed cases.

| Entry | Caller contract | Executed behavior |
|---|---|---|
| `60bc9f95` | a0 context, a1 inclusive 4×s16 clip, mask30/frame20 | Intersects the requested clip with the context bounds |
| `60bca2b4` | a0 context, d0=-1, maskf0/frame16 | Disables rectangle outline |
| `60bca074` | a0 context, d0=-2, d1=-1, a1 palette index, maske0/frame16 | Sets a solid indexed brush |
| `60bc69b8` | a0 context, a1 inclusive 4×s16 rectangle, maskb0/frame52 | Clips and submits the filled rectangle |

The executed fill path is `60bc69b8 → 60bc722b → 60bcc0e8 → 60bccf1b → 606e15cc`. The fixture registers `60bcc0e8` at backend+92, as the native registration code does at `60bcbd45`. The context points to that backend at +72. The native relocated libc helpers remain actual firmware code through `parser_state`.

At `606e15cc`, the probe records the exact 28-byte submission and returns a declared modeled raster result. No code below that raster boundary runs. A submission contains its surface pointer at +0, device layer at +4, x/y/width/height at +8/+10/+12/+14, indexed color at +20 and mode at +24. Color also appears as a halfword at +18. Inclusive input `(10,20,30,40)` becomes `(10,20,21,21)`. A disjoint rectangle produces no submission.

Backend IDs 0, 1 and 2 map through native table `60dcf38c` to device layers 1, 2 and 0. Global byte `6160c40c` selects one of two surface pointers for each backend at `61a8e308 + backend*8 + selector*4`. All six combinations execute and match the selected fixture surface. A fixture logical-layer gate does not establish how a live viewer assigns its backend or palette. [OSD resources](../../tooling/pen-f/RESOURCES.md) documents the separately established shooting-layer palette roles.

The graph uses the existing first-layout union rectangle `(348,107)..(609,372)`. It projects LUT input indices across that fixed rectangle and values 0..1023 vertically. Marker x coordinates come only from the five supplied indices. The graph never derives photographic anchors from the stock bitmap marker locations. Native rectangle requests cover a background, a grid, connected curve columns and five crosses. All recorded requests must equal the corresponding clipped command rectangles.

The coordinator's `display-fixture.json` supplies endpoint values 64 and 950 and experimental marker indices `[0,30,118,210,255]`. Their projected points are `(348,355)`, `(379,341)`, `(469,249)`, `(563,154)` and `(609,126)`. The three interior point records equal the source LUT's records. These experimental markers are not the stock bitmap's marker coordinates or a production signal-anchor contract. The native prototype submits 273 rectangles. The generated SVG and optional PNG explicitly say prototype, use illustrative colors and are not body screenshots.

Reproduction from the repository root uses the exact decoded 3101 main image, the native emulator and `toolchains/tone-binutils-build`:

```sh
python3 tools/penf_tone_display_probe.py \
  --fixture generated/tone-curve/display-fixture.json \
  --out generated/tone-curve/native-display
python3 -m unittest discover -s tests -p 'test_penf_tone_display.py' -v
```

The output includes `report.json`, `prototype.svg` and the assembled fixture source, object, ELF and binary. The optional `render_png(report["graph"]["draws"], path)` helper needs Pillow. The bundled workspace Python supplies it. The report embeds the input LUT, exact raster requests, native instruction count, source comparison and strict limits. The module refuses optimized Python execution, so `-O` cannot remove proof assertions and emit success evidence. Subprocess tests cover both CLI execution and direct import under `-O`, with no evidence directory created. Other tests cover clipping, context isolation, rejected layers, an empty command stream, malformed LUT inputs, fixed inner marker heights and an unknown backend callback that still causes a native memory fault.

The tone class constructor sets vtable `60ec4cac`. Its public paint slot +160 is the four-byte pointer at `60ec4d4c`, currently `60bbe8b6`. That wrapper saves a2/a3 and reserves eight local bytes before entering dispatcher `60bbe8bb`. The dispatcher calls background slot +448, `60bbe8d4`, followed by child traversal slot +444, `60bf7aec`. An eight-instruction native fixture run reaches the actual background callback with a0 receiver and a1 job unchanged. It stops there and supplies no fake callback success. The dispatch report therefore says `complete_paint_returned=false`.

A future hook can replace the tone class's own +160 pointer and preserve the shared stock implementation. The full paint callback, stock traversal, old-graph removal and redraw lifetime are still unqualified. Children 26..28 are gray graphs and 29..31 are active graphs in the prior resource investigation. Visibility helper `60cfcb51` is a concrete candidate for removing them, but calling visibility changes during paint may invalidate the viewer. This probe does not claim that operation is safe. Hiding only active children also leaves gray curves, and drawing over old bitmaps does not erase them.

The remaining camera contract must establish when to suppress and restore all stock graph children, how to preserve the grid and other widgets, and how param118 updates and viewer invalidation request another draw. The hook must call stock traversal before allocating its private drawing context, as the existing HSL painter does, and must preserve the stock return value. It must qualify stack headroom and actual logical layer, backend, surface and palette assignment. No receiver padding, object lifetime extension, firmware placement, full boot, flash or device access is part of this proof.
