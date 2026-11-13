# Live ND: OM-5 design and an E-M5 III port

Live ND is a digital ND filter. Instead of one long exposure through a dark
filter, the camera takes N frames at the selected shutter time and averages them
in the image engine. Moving water or clouds blur as if a filter were used, and
the displayed "digital" exposure is N × Tv. The OM-5 has the feature; the E-M5 III
does not offer it. This page records the OM-5 1200 design and what was found
running the OM-5's merge on E-M5 III build 1700 (identities in
[E-M5 III address spaces](../../format/e-m5-iii/ADDRESS_SPACES.md)).

**Status:** a full Live ND shot works on an E-M5 III with the OM-5's own shooting
states ported: one press captures N frames at the set shutter time, job 11 merges
them, and the shot ends cleanly (ND2 to ND16, at 1/8 s and 1/125 s, several
presses in a row). The live-view preview (job 12) also runs on the E-M5 III. It is
an experiment switched on by a card file, not a menu feature; the dark-frame pass
is not ported.

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

1. The DigitalNd builder (`602b9405`) writes N (frame_max) into the request's two
   source frame counts, and the capture start (`602bbb77`) leaves them alone, so
   the sensor sequence itself is N frames long.
2. DigitalNd reserves an output frame (job +6 = 1). The sensor never fills it.
3. All N sensor frames arrive at the add step (event 63, then event 80), are
   added and go back to the pool. At the end the merge result is written into the
   reserved output frame, which is developed and saved (builder `602b97bf`,
   kind-7 output `602bc2c1`). **Physical camera test:** with no merge, the saved
   photo is the unwritten buffer.
4. The frame-supply helper (`602b9faf`) is cyclic: it hands out a "run-dry" job
   with frame id 0 when three or fewer of the N remain. The event-63 handler skips
   the capture call for id 0 (`602b995e`). The sequence then finishes (events 33,
   24, 66 and 56).

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

## Ending the capture: what the E-M5 III needs

The OM-5's states (ported as E-M5 III states 35-37) depend on details where the
E-M5 III's own functions behave differently. Each item below was found by
tracing a run live over the stock Wi-Fi debug shell (`take dbgmode 1` streams
the shooting sequencer's states and events), then fixed and confirmed in a
**physical camera test**:

| Point | OM-5 1200 | E-M5 III 1700 | What the port needs |
| --- | --- | --- | --- |
| Capture start | `602bbb77` writes no status words | `602b0a5a` writes -1 through three request pointers (+40, +24 then +8, +44) and so turns the N-frame sequence into an endless burst; +44 = 0 is a write to address 0 (NMI, camera resets about 1 s later) | a copy of the start without those writes, +44 pointing at a real word (the native StlUhs builder `602b4cea` uses ctx+964) |
| Run-dry job | event-63 handler skips the capture call when frame id = 0 | `602bc619` with id 0 reaches a NULL descriptor (NMI) | keep the OM-5's id-0 check |
| Stop handshake | sent on entry to the End state (33), which then waits for the replies (events 47 and 87) | the native burst states send stop message `602b98de` from their event-33 handler (reply event 47) | the handshake must complete; setting the native stop request (`6210f59a`) is not a usable end for this sequence |
| Display at the end | one "resume live view" handler releases when the Live ND flag is set | the display task's handler `6044605d` waits with no timeout for flag 4 on `60040e96`, set only from the sequencer's event-83 handler; native StlEnd handler `602b8305` releases only when continue_mode is 0 | handle events 81, 82 and 83 while the Live ND end state is current |
| Button release | — | an event with no handler in the current state makes the dispatcher (`602a0f90`) print a history dump (`60227bb0`); during a fast series this stalls the frame refill and frames are lost | add the release events (exec 17, event 39) to the Live ND states' tables with the native no-op handler `602a14bb` |

The general lesson: when ported code calls an E-M5 III function, compare that
function with the OM-5 function it replaces, not just the arguments.

**Physical camera tests** after these changes: ND2, ND4, ND8 and ND16 merged
(16 frames merged by job 11 in 142 ms), 16 frames at 1/125 s with no frames lost,
four presses in a row, and the camera returned to normal shooting after each.

## Live-view preview on the E-M5 III

The OM-5 switches the preview per live-view frame inside its live-view module:
with LV Simulation on, every new frame is added to a ring and job 12 averages the
last frame_max frames (30 per second of digital time, up to 240). The E-M5 III
computes the same AE values (frame_max and digital Tv, AE `6041e1ce`, copied at
`60427c71`) but has no preview code. Results so far, each a **physical camera
test**:

- The E-M5 III live-view raw frame is 2912 × 544 pixels, rows of 3328 bytes
  (14 × 9-bit pixels per 16 bytes), `0x1ba000` bytes per frame.
- Job 12 runs on E-M5 III frames. With no accumulator input it runs a reset form
  (output = input, factor and shift ignored); its add, slide and average steps
  give correct results.
- Called from the per-frame live-view function (hook point `6034931b`), job 12
  keeps up with live view. The job record stores the CPU that submitted it (byte
  69, `603185eb`); live view runs on CPU 1, so completion counting must not
  assume CPU 0.
- A window that follows frame_max up to 240 frames, held in borrowed main-pool
  frames, works; with LV Simulation on, live view runs at 30 fps, as on the OM-5.
- The borrowed frames must go back before a photo. The live-view end handler
  `6034e4c6` is passed before photos, but not when opening the menu or playback.

## Limits

- 20 main-pool slots allow 16 held frames plus 2 streaming at ND16. ND32 would
  need two passes or a running accumulator. OM-1 does this natively with
  accumulators, but its jobs do not match the OM-5 or E-M5 III jobs.
- The live-view preview needs job 12 and its setter, and frame memory for the
  ring; the E-M5 III has no pool reserved for it.
- The dark-frame pass (OM-5 state DarkRdy, used with long-exposure noise
  reduction) is not ported; it reuses the native dark-frame subtraction.
- Card reads and log writes were safe only from a silent single shot, never
  during a burst.
- For OM-5 and E-M1 III pool and ring sizes, see
  [silent burst and Pro Capture](../om-5/BURST.md).

## Verification and limits of the evidence

- The OM-5 rows come from disassembly of OM-5 1200 (container SHA-256
  `a0c91f3ac7caaf0925b2af609e711183cf3b5982b3333224bcef26c0c5943d11`) at the listed addresses. The E-M5 III rows come from the pinned 1700 main.
- The physical results come from one E-M5 III, with the patch switched on by a
  card file. The brightness comparison is one tripod scene. The live-view
  preview was judged by eye and by job counts and timings, not by comparing
  pixels with an OM-5.
