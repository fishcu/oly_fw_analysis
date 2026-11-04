# PEN-F Multiple Exposure and Live ND

PEN-F 3.1, build 3101, stock container SHA-256
`77398610b379f80238117f31a6d5bbf65d608b49ec563666c64d84367e969f2c`.
Addresses are CPU addresses in the decoded main component (base `0x60021020`).

The stock in-camera Multiple Exposure is an N-frame RAW mean with Auto Gain on.
It offers only 2 frames. The [Live ND source build](../../../patches/live-nd-af-limiter/pen-f/README.md)
adds 4 and 8 frames, takes 4f and 8f from one held press, and writes the frame
count into the maker note.

Evidence is marked as **code** (disassembly), **native** (original instructions
run in the [MN103 emulator](../../tooling/EMULATOR.md) with the stated memory
models) or **camera** (one PEN-F body, firmware built from the source above).
The ISP is not emulated: pixel behaviour comes from camera tests only.

## Stock pipeline

```
CapMex_MultiExposure (singleton 0x61603f9c)
  0x607bbaad  compose(this, images[], count)          vtable slot 8 of CapMex_NotifyCombineObserver
              gathers count+1 handles into a 5-entry stack array
  0x60307ccd  api_rec_Bayer_MultiExp(handles, n)      CALLS entry 0x60307cc8 (registered callback)
              156-byte message: handles at +4..+20, usMode +40 = 0x1002, usMultiNum +74; API 0x20076
  0x6052cd87  message -> 216-byte executor request    copies 9 handles (+4 -> +32), +74 -> +96
  0x60531ca5  image-request dispatcher, table 0x6063e3f4: 0x1002 and 0x1005 -> 0x605389c1
  0x60538b95  COMPOSE_RAW fold: pass 1 = frame0 + frame1, pass k = result + frame k
  0x6053907a  per-frame gain G
```

**Gain** (code, native): for usMode `0x1002`, G = 2048 (unity, Q11), or
`(256 / img[18674]) << 3` when `img[18675] == 1` (Auto Gain). The fold is
therefore a mean of N frames. `256/N` is exact for N = 2, 4, 8, 16, 32. Native
runs of the fold give G = 512 for N = 4 and G = 256 for N = 8.

**Per-frame stamp** (code): `0x6025350c` fills each captured frame's image info
and copies setting 267 (Frame) to `+18674` and setting 268 (Auto Gain) to
`+18675`. It has 8 call sites in the take module.

**ISP parameter block** (code, from the debug dumper `0x61115c13`): two source
descriptors with per-channel OB and WB gains, `usGain1` at +82 and `usGain2` at
+170 (Q11), and the destination. No blend-mode field is dumped; the module
appears to be a weighted add. Pass k > 1 feeds the previous result as source 1
with unity gain and WB 128.

## Settings

| Id | Store key | Meaning |
| ---: | --- | --- |
| 267 | `0x1841` | Frame (`MODE_MULTI_EXPOSURE_FRAME`). The stored value is the frame count: 0 = Off, 2 = 2f. |
| 268 | `0x1851` | Auto Gain |
| 269 | `0x1861` | Overlay (adds one to the frame count; cleared by `exitEXECUTE`) |

`0x602f024a(id)` reads a setting and `0x602f029d(id, value)` writes it. The store
does not clamp setting 267 (code). The menu offers Frame values from the
descriptor at `0x603e1c14`, whose list is `{0, 2}` at `0x603df218`.

**Force-off rules** (code, native): setting 267's rule set at `0x603a05d0` has two
rules (conditions 15258 == 1 and 15206 == 1), both with the map `{0→0, 2→0}` at
`0x6037d8d8`. A value missing from a map passes unchanged, so a new frame count
must be added to the map, or it escapes the force-off.

**Menu labels** (code, native): the GUI menu record for Frame is `0x60f97520`
with two value-keyed option arrays of 12-byte records `{u32 value, u16 type,
u16 string id, ptr}`. Array A (row value, lookup `0x60c8972a`) and array B
(picker rows, row builder `0x60d0418d`) are separate; an unmatched value shows a
blank label. Strings 1431 = "4f" and 1902 = "8f" already exist.

## Capture-side limits

**Controller** `CmpSts_MultiExposureFunctionController` (`0x607fd600..0x607fe900`):

| Global | Meaning |
| --- | --- |
| `0x616047c0` u16 | take count; `addTakeCount` stops at setting 267 |
| `0x616047ac` u16 | combine-handle count; `setMesCombineImage` writes slot count+1 while count < setting 267 |
| `0x616047b4` ptr | combine-handle array, allocated as **20 bytes (5 slots)** at `0x607fe857` |

Stores are bounded by setting 267, not by the array. Setting 267 = 5 writes past
the 20-byte block (native). Four takes fit the stock layout exactly.

Other 5-slot structures that need changing for 8 frames (code):
`compose`'s stack array, the 5-handle copy in `Bayer_MultiExp`, and the
controller's init, reset and free loops (`cmp 5` at `0x607fe880`, `0x607fe0c7`,
`0x607fdaef`, `0x607fdb54`, `0x607fe37d`, `0x607fe3a9`). The view-path functions
`makePlayScaleHandle` (`0x607baf11`) and the review path at `0x607ad61e` keep
5-slot stack arrays; capping their take count at 4 leaves them stock-sized.

Downstream of the API message, everything already handles 9 handles
(accumulator + 8 frames): the converter loop at `0x6052d016` and the fold.

**Memory** (code): takes come from pool 0, 24 blocks of 32,481,280 bytes at
`0xB0000000`. The layout modes reserve at most 8, so 16 or more remain. Eight
takes plus the accumulator fit. More than about 15 frames would need a running
fold (accumulate and free each frame) rather than one request.

**Fold quirk** (code, native): the gain helper looks the frame index up in the
handle list (`0x6053908e`, `handles[handle]`). With 9 handles, a value of 9
would read the request's mode field. The patch uses the handle directly.

## Chaining takes from one press

`entryTAKE_PICTURE_CONT` (`0x608488cb`) runs after each take. It chains the next
take through `requestMesCombine` (`0x60849e19`) only when the release-source code
at `0x61604888` is 4 (`cmp 4,d0` at `0x608489e5`). That value is a source code
(1/2/4/8), not a "shutter held" flag (code). Camera: in stock firmware, holding
the shutter after a frame leaves the screen black and no further frame fires.
Native: stock chains only for source 4 and otherwise waits (key held) or ends.

The take-done handler `rcvTakePictureDoneIn_TAKE_PICTURE_CONT` runs once per
press. Camera: replacing the source alone gave 2 frames per press in Sequential
L/H. Requesting the next take from the take-done tail while
`takes + overlay < Frame` gives all frames from one press (camera, Sequential H).
Single-frame drive still does not chain (camera).

## Maker note

Olympus ImageProcessing IFD tag `0x101c` (int16u[2]) comes from image info
`+0x13fa` (descriptor record `0x60642818`). The capture writer
`0x602547ff..0x60254856` sets the first value to a flag (`|= 2` when Multiple
Exposure is on) and the second to the constant 1 (code). ExifTool's
"(2 frames)" label for the first value is not a count. The patch stores
setting 267 in the second value (camera: 2, 4 and 8 read back correctly).

## The patch

43 ranges, 623 bytes over HSL alpha-20261017
([source](../../../patches/live-nd-af-limiter/pen-f/README.md)); the Live ND
part is 36 of them.

| Area | Change |
| --- | --- |
| Settings | Frame list `{0,2,4,8}`; force-off map `{2→0, 4→0, 8→0}` for both rules |
| Menu | Arrays A and B with 4 records (Off 1454, 2f 42, 4f 1431, 8f 1902) |
| One press | Release-source helper returns 4 when Frame ≥ 4; take-done tail requests the next take |
| 9 slots | `compose` frame 52 → 60, memset 20 → 36, ret frame 68 → 76; controller array 20 → 40 bytes; six loop bounds 5 → 9; `Bayer_MultiExp` copies handles 5..8 when the count is above 4 |
| Preview | `makePlayScaleHandle` and the review path cap the take count at 4 |
| Fold | Gain helper uses the handle itself |
| Maker note | Tag `0x101c` second value = Frame |

2f stays one frame per press, as in stock firmware (native, camera).

### Camera results

- 4f and 8f: one held press in Sequential H gives all frames and one composite.
- Tripod, same exposure: 4f and 8f composites have the same brightness as a
  single frame, and 8f is less noisy. No ghosting.
- Handheld: each frame is sharp (IS works per exposure), but frames drift
  10–100 px; there is no alignment.
- The review preview looks correct; it was not analysed further.
- Single drive: no chaining.

### Stack frames and direct callers

The first 8f builds restarted the camera on the last frame of every
multiple exposure, with no composite saved. Bisecting builds on the camera put
the fault in `compose`. The emulator reproduced it once every entry was run.

`compose` has a CALLS entry with the `add -52,sp` prologue and a plain-call
entry right after it. Code that enters at the second address sets the frame
itself through the call's imm8 operand. The vtable path uses the CALLS entry,
but a direct `call 0x607bbab2,[d2,d3,a2,a3],68` at `0x607bbe14` uses the plain
entry. After the frame grew by 8, that caller still declared 68, so `ret`
returned through the wrong slot (native: fault at pc 0).

When changing an MN103 frame, patch the prologue, every `ret`/`retf` frame,
and the imm8 of every direct call to the post-prologue entry. Search for
callers of both entries, and emulate each entry path. Growing by 8 rather than 4
keeps the stock 8-byte stack alignment.

## Open questions

- 12f and 16f need more than the request's 9 slots: a running fold (a stage-2
  request accumulating into the stage-1 result) or chaining through Overlay.
- The view-path composite sends API `0x20075`, which is not mapped.
- Frame alignment for handheld use.
- Store key `0xC222` selects take mode 1, which uses pool 8 (3 blocks). Whether
  Multiple Exposure can run in that mode is unchecked.
- Conditions 15258 and 15206 are unnamed.
