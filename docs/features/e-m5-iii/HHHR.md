# Handheld High Res: OM-5 design and E-M5 III groundwork

High Res Shot combines several frames, taken with the sensor shifted by small
amounts, into one 50 MP picture. The E-M5 III can do this on a tripod. The OM-5
can also do it handheld: it measures how the camera moved between frames and
aligns them before combining. This page records the OM-5 1200 handheld design
and what has been established towards running it on E-M5 III build 1700
(identities in [address spaces](../../format/e-m5-iii/ADDRESS_SPACES.md)).

**Status:** groundwork only. The OM-5's four image-engine programs load on the
E-M5 III, the memory is available, and the ARM co-processor can be powered on and
off for a shot. Whether the programs compose a correct picture on the E-M5 III
has not been tested. There is nothing user-visible.

Evidence: static disassembly unless a result is marked as a **physical camera
test**. No vendor job program or code bytes are reproduced.

Terms used here:

- **Tripod / handheld:** two methods of the same High Res feature, chosen on the
  OM-5 by a "Shooting Method" setting.
- **Jobs 14-17:** OM-5 image-engine programs that compose, fill, convert and
  resize the result (see [image-engine jobs](../../imaging/e-m5-iii/IMAGE_ENGINE_JOBS.md)).
- **ARM / `hhhr`:** the Cortex-A9 co-processor and the Linux program on it that
  computes alignment matrices (see [ARM co-processor and ISC](../../protocols/e-m5-iii/ARM_ISC.md)).
- **mdet:** the main CPU's motion-estimation service.

## OM-5 1200 design

- Handheld is a method of High Res Shot, not a separate mode. Property 7729
  ("Shooting Method", setting 1680) selects it, and 9 code readers branch on it.
  The pool selector `602bcb39` picks pool `0x6100` for handheld and `0x4f00` for
  tripod.
- Flow:
  1. Prepare, then `api_start`.
  2. For each frame (HsContTake callback), `api_comp`: take the frame's Y image,
     estimate motion against frame 1 (`mdet_hhhr_request`, type 17), and ask the
     ARM `hhhr` program for three 3×3 matrices (ISC channels 30 and 31).
  3. Job 14 composes the frames into 4 planes of 10416×7824. OM-5 keeps 12
     frames; E-M1 III uses up to 16.
  4. State 34 (PixShiftSrHandHeldEnd) runs job 15 (fill), job 16 (RGB) and job
     17 (resize) for a 50 MP output (`term_post_50m`).
  5. The done callback always runs, including on abort.
- The module spans about `6067f9xx..606871xx` (about 30 KB, 232 named
  functions). API: init `6067d37a`, start `6067d39d`, comp `6067d3f0`, term
  `6067d45b`, query `6067d4c8`, end `6067d527`.
- Buffers total about 640 MB: planes `0x5f00` and `0x6200` (4 × 28 MB each),
  `0x6000` (4 × 14 MB) and `0x6100` (12 × 31 MB).
- OM-5 holds the ARM on for the shot through its power manager: take task
  `602b7b51` posts a "Take" request when properties 61633 and 7729 are both 1,
  at the mode transition `60237696`.

## What E-M5 III 1700 contains

- Tripod High Res: states 25-30, pool `0x4f00`, and the 50 MP record path.
- The ARM `hhhr` program, started at boot, identical to E-M1 III's apart from
  addresses.
- Missing: the main-CPU handheld module, property 7729, pool `0x6100`, state 34
  and jobs 14-17. The setter slots for jobs 14-17 are return stubs (`60319bce`,
  `bd1`, `bd4`, `bd7`) in both setter tables (`60257ab0`, `60257b88`). Nothing on
  the E-M5 III sends on ISC channel 30, and nothing posts a Take request.
- The E-M5 III submit (`603185eb`) allocates a 76-byte packet (job at +60, slot
  at +63); the OM-5 one (`60328a27`) allocates 84 bytes (+68/+71). OM-5 setters
  therefore need an adapted payload.

## Physical camera tests

| Test | Result |
| --- | --- |
| Load OM-5 jobs 14-17 through the native flash path (`600c4922`, loader mode 258) into a main-pool frame, then check sums | all four loaded with matching sum32; 51 ms total (job 14 11.8 ms) |
| Pool census during a tripod High Res shot | tripod uses pool `0x4f00` = 8 frames at `b0000000..bfa3b000`; nothing else in the planned handheld layout was in use |
| Read ARM state with wireless off, and with wireless on but no phone | ARM not started in either case (`a2624f09` = 0) |
| Send on ISC channel 30 with the ARM stopped | screen went black and the camera powered off |
| Post Take on in the middle of a shot | camera reset |
| Post Take on and Take off at the first Idle/Standby after a shot | ARM booted, two body-button shots normal, clean shutdown, no reset |

So the ARM can be leased without Wi-Fi, but only by changing its power outside a
capture.

## Constraints for a port

- Plane buffers must stay below `c0000000`: ARM Linux uses MN103
  `c0000000..c2aa0000` while it runs.
- In flash, `45c86e00..45d60000` (PIC component) is zero-filled and fits jobs
  14-17; its last 32 bytes are a trailer, not free space. In RAM,
  `a4277140..a42bf540` (296 KB) fits job 14, or jobs 15+16+17.
- Job 14's setter reads defaults from the last 0x100 bytes of its own program,
  so relocating the program must move that pointer too.
- OM-5 II 1100 changed jobs 14 and 15; OM-1 jobs do not match. OM-5 1200 is the
  closer source for E-M5 III.

## Verification and limits

- The OM-5 rows come from disassembly of OM-5 1200 (container SHA-256
  `a0c91f3ac7caaf0925b2af609e711183cf3b5982b3333224bcef26c0c5943d11`). The E-M5 III rows come from the pinned
  1700 main.
- The physical tests ran on one E-M5 III. Jobs 14-17 were loaded and checked, not
  run on frames; mdet type 17, compose, record and the IS drive for handheld
  shots are untested.
