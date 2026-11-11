# Live ND: OM-5 design and an E-M5 III port

Live ND is a digital ND filter. Instead of one long exposure through a dark
filter, the camera takes N frames at the selected shutter time and averages them
in the image engine. Moving water or clouds blur as if a filter were used, and
the displayed "digital" exposure is N × Tv. The OM-5 has the feature; the E-M5 III
does not offer it. This page records the OM-5 1200 design and what was found
running the OM-5's merge on E-M5 III build 1700 (identities in
[E-M5 III address spaces](../../format/e-m5-iii/ADDRESS_SPACES.md)).

**Status:** merged ND2, ND4, ND8 and ND16 photos work on an E-M5 III. Ending the
capture with the OM-5's own shooting states does not work yet (see "Open"). It is
an experiment switched on by a card file, not a menu feature.

Evidence: static disassembly unless a result is marked as a **physical camera
test**. No vendor job program or code bytes are reproduced here.

Terms used here:

- **Job 11 / job 12:** OM-5 image-engine programs. Job 11 averages frames into a
  photo; job 12 accumulates the live-view preview. See
  [image-engine jobs](../../imaging/e-m5-iii/IMAGE_ENGINE_JOBS.md).
- **Route:** a number (0-4) chosen for each shot that decides which shooting
  states it passes through. Route 4 leads to state 15, **StlUhs**, the firmware's
  still high-speed burst state.
- **Armed:** the patch's own on switch. When it is off, every hook falls through
  to stock behaviour.
- **WBClip:** the per-channel white clip level passed to the merge.

## OM-5 1200 design

| Item | OM-5 1200 |
| --- | --- |
| Live ND on / ND number / LV simulation | properties 7745 / 7761 / 7777 |
| Photo merge | job 11; up to 16 frames at the set Tv; WBClip computed per channel |
| ND code | 1..4 = ND2..ND16 (strings up to ND32 exist, but the engine stops at ND16); light table `a26f0644` caps at 16 |
| Live-view preview | job 12 (`iseq_ndlv`: start, add, roll); frame_max = 30 × digital time |
| Shooting states | 31 DigitalNd, 32 DarkRdy, 33 End; entered when continue_mode = 4 and the Live ND context flag (ctx+2196) is set |
| Sensor request | DigitalNd sends its own type-7 request: kind `0x400`, flag 1, fps 0, so frames can be slower than 1/15 s |
| Limit | N × Tv ≤ 64 s |

How a capture runs and ends:

1. DigitalNd reserves an output frame first. The first sensor frame lands in it
   and becomes the merge target.
2. Every other frame is added to it, then goes back to the pool.
3. The frame-supply helper (`602b9faf`) stops handing out pool frames when three
   or fewer of the N remain.
4. Capture ends because the state's frame supplier returns null once its queue
   (`620cfe48`) is empty. Native per-frame completion then marks the descriptor
   (`0x8000`) and raises the sequence end flag, and the sequence finishes (events
   56 and 66).

OM-5 II 1100 has the same engine, also ending at ND16.

## What E-M5 III 1700 already contains

- The Live ND plumbing is compiled in but inactive: take-parameter bytes
  +119/+120 are zero, the related functions are identity stubs, and AE ids
  299-302 exist. The DigitalNd states and jobs 11 and 12 are missing; their job
  entries are placeholders.
- No drive mode selects route 4. The chooser is `602b3441` and the route byte is
  `6211020e`, loaded at `602b2263`. **Physical camera test:** forcing route 4 at
  Standby works.
- The main image pool has 20 slots of `0x1f47600` bytes in two blocks (vtable
  `6053e778`). Ids up to 8 are at `b0000000` and ids 9-20 are at `c4000000`
  (address method `603f9cb7`). Computing a slot address from a stride is wrong
  after slot 8, so always ask the pool. **Physical camera test:** writing by
  stride corrupted memory outside the buffers.

## Approach that works on the camera

1. For an armed shot, force route 4 and keep the burst frames in the event-63
   handler, which runs in task context.
2. Run OM-5 job 11 on the kept frames, writing the output into the last kept
   frame. That frame is then developed and saved as the photo.
3. ND2 and ND4 repeat inputs (input i = frame i mod K). ND8 uses 8 frames and
   ND16 uses 16.
4. Send the kind `0x400`, fps 0 request only from the armed burst's own request
   builders (Standby `602b30e5`, StlUhs `602b4c5d`, sub-state `602ba103`).
   **Physical camera test:** giving kind `0x400` to every caller while armed hung
   the camera.

**Physical camera tests:**

| Observation | Result |
| --- | --- |
| Route-4 burst without the request change | 60 fps (16.6-16.7 ms) at every Tv; merges at 1/60, 1/30 and 1/15 match a 1/60 single |
| With kind `0x400`, fps 0 | frames 125.0 ms apart at Tv 1/8 |
| Merged ND8 (8 × 1/8 s) vs a 1/8 s single, on a tripod | same brightness within 0.03 EV |
| Job 11 time | 2 frames 32.5 ms, 8 frames about 87 ms, 16 frames 142.5 ms |
| JPEG size for ND2 / ND4 / ND8 | 3.96 / 3.23 / 2.64 MB (less noise) |

The port uses a constant WBClip of 4095, where the OM-5 computes one per channel
(`6067dcb5`).

## Open: ending the capture cleanly

Merging after a native burst works. Running the OM-5's own states (ported as
E-M5 III states 35-37) to stop after N frames does not work yet. Either the
capture never ends and a battery pull is needed, or the camera resets about a
second later. What is known so far:

- The ported end states must use E-M5 III structure offsets. An earlier port
  carried E-M1 III offsets in several places: the frame-header pointer table,
  header fields, and the context byte for property 35873.
- Native builder `602b97bf` takes d1 = a boolean and a record pointer on the
  stack, read at (24,sp). Passing 0 there causes a null+0x3c read. Fixing it
  removed one reset, but the capture still did not complete.
- The end state waits with no timeout on the kind-7 output (`602bc2c1`), a
  command-38 RPC (`602bacb3`) and queue sends. No single static cause has been
  found.
- No RAM log survives the reset. A block written before the reset reads back
  afterwards as a power-on pattern.

## Limits

- 20 main-pool slots allow 16 held frames plus 2 streaming at ND16. ND32 would
  need two passes or a running accumulator. OM-1 does this natively with
  accumulators, but its jobs do not match the OM-5 or E-M5 III jobs.
- The live-view preview needs job 12 and its setter.
- Card reads and log writes were safe only from a silent single shot, never
  during a burst.
- For OM-5 and E-M1 III pool and ring sizes, see
  [silent burst and Pro Capture](../om-5/BURST.md).

## Verification and limits of the evidence

- The OM-5 rows come from disassembly of OM-5 1200 (container SHA-256
  `a0c91f3ac7caaf0925b2af609e711183cf3b5982b3333224bcef26c0c5943d11`) at the listed addresses. The E-M5 III rows come from the pinned 1700 main.
- The physical results come from one E-M5 III, with the patch switched on by a
  card file. The brightness comparison is one tripod scene. The live-view
  preview (job 12) and the OM-5 end states were not shown working.
