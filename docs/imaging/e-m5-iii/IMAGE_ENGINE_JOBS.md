# E-M5 III image-engine jobs

Next to the control CPUs, the camera's processor has an image engine for heavy
pixel work such as developing raw frames, resizing and merging. It does not run
the main program. Instead, the CPU loads a short program for it (a **job**),
writes the job's parameters, and submits a record that describes the buffers.
The job programs are opaque microcode. This page maps where they are stored, how
they are called and what their records hold, for E-M5 III build 1700 (identities
in [address spaces](../../format/e-m5-iii/ADDRESS_SPACES.md)). It also compares
the job tables of other bodies. No job program bytes are reproduced.

Evidence: static disassembly unless a result is marked as a **physical camera
test**. Purposes marked *inferred* come from callers and data shapes, not from
running the job.

Terms used here:

- **Setter:** a CPU function, one per job, that writes the job's parameters
  before it is submitted.
- **Parameter window:** the address range at `9d000000` that setters write.
- **Record:** the structure submitted with a job, holding buffer addresses and
  sizes.
- **OB:** the sensor's optical black level.

## Storage and loading

- Programs are in the PIC component (block 2), resource `0x8007`, one entry per
  job. E-M5 III's own programs end at flash `45c77400`; `45c86e00..45d60000` is
  zero-filled.
- At runtime, native programs occupy RAM `a411f540` (job 0) to `a4277140` (end of
  job 10). `a4277140..a42bf540` has no code references.
- Loader `6005a177(a0 = dst, a1 = flash, d0 = size, d1 = 258)`. A destination
  outside `a0000000..bfffffff` reset the camera (physical camera test).
- Jobs do not need their native address: OM-5 job 11 ran from spare RAM and from
  a descriptor-pool slot (physical camera test). OM-5 job 14's native load address overlaps
  E-M5 III job 9, so donor jobs must be relocated.

## Job tables by body (entry sizes in bytes)

| Job | E-M5 III 1700 | E-M1 III 1600 | OM-5 1200 | OM-5 II 1100 | Use |
| --- | --- | --- | --- | --- | --- |
| 0-10 | present | same | same | same | native jobs below |
| 11 | placeholder (`0x600`) | `0x4400` | same | same | Live ND photo merge |
| 12 | placeholder | `0xb600` | same | same | Live ND live-view accumulator |
| 14 | placeholder | `0x48000` | `0x41800` | `0x42a00` | handheld high res compose |
| 15 | placeholder | `0xe000` | `0xd600` | `0x9000` | handheld high res fill |
| 16 | placeholder | `0x29c00` | same | same | handheld high res RGB |
| 17 | placeholder | `0x7200` | `0x7600` | same | handheld high res resize |
| 18 | absent | `0x4400` | same | same | unknown (OM-5 setter `603292c0`) |

"Same" means identical SHA-256 per entry. No OM-1 / OM-1 II job entry matches any
of these.

## Native jobs 0-10

Wrappers `60318301..603185c3` reload a program when bit `1 << job` of `8ff001b8`
is set (jobs 2-7 and 9), then call `603185eb(job, 0, rec, flags)`, which copies 17
record words. The setter table is at `60257b88` (OM-5: `6025f8e8`).

| Job | RAM program | Size | Purpose |
| --- | --- | --- | --- |
| 0 | `a411f540` | `0x51400` | AF image processing (caller `606aff4c`), inferred |
| 1 | after job 0 | `0x5b200` | unknown; no setter |
| 2 | `a41cc140` | `0x19000` | raw combine of 2-3 frames for Live Composite (`602a7745 → 602bf7b4 → 603720a9`), inferred; one 0/1 option, only 0 used natively |
| 3 | `a41e5540` | `0x14400` | focus-stack merge step (6 buffers), inferred |
| 4 | `a41f9d40` | `0x11400` | motion-compensated warp: 4736×3616 YC frame and a 22×16 vector field (`MDET_CALC_FLAME_VECTOR` `605de1f5`) to 4480×3360 planar (caller `60381776`) |
| 5 | `a420b540` | `0xb600` | resize to full and half size, inferred |
| 6 | `a4217540` | `0x4800` | focus-stack merge step (3 buffers), inferred |
| 7 | `a421c540` | `0xe800` | focus-stack merge step and final pass, inferred |
| 8 | `a422b540` | `0x1600` | hardware copy (`CAvpiPcomMemToMemHwcpy` `603f43b8`, 128 KB chunks) |
| 9 | `a422d140` | `0x38000` | raw development in 8 strips, inferred |
| 10 | `a4265540` | `0x11c00` | unknown; mode-selected coefficient tables |

Jobs 3-7 together are most likely the in-camera focus-stack merge (shot kind 19:
motion vectors, job 4 warp, then jobs 5, 3, 6, 7). No native average, minimum or
subtract job was found.

## Parameter window

Setters write parameters to a window at `9d000000` (slot 1 = `9e000000`, chosen by
record byte +0x3f for jobs 3-6 and 9) and the program address to `9d200010`. On
E-M5 III, job 8 uses offsets 0x00-0x08, job 10 0x10-0x18, job 7 0xac-0xc0;
0x1c-0x54 is unused. OM-5's job 12 setter (`6032a739`) writes 15 words at
0x1c-0x54, including 65536/N and log2(N). OM-5's job 11 setter (`6032a626`) writes
no window words. Job 14's setter reads defaults from the last 0x100 bytes of its
own program, so relocating the program must move that pointer too.

## Job 11 record (420 bytes)

| Offset | Field |
| --- | --- |
| 0 | 32 × 12-byte inputs: u32 address, 4 × u16 OB |
| 384 | output address |
| 396 / 400 / 404 / 408 | number of inputs, memory width (pitch), width, height |
| 412 | 4 × u16 WBClip |

**Physical camera test:** OB read 1025; a full frame used 5240/5240/3912 with slot stride
`0x1f47600`. The output is the average of the inputs in the same packed 12-bit
format (80 of 80 sampled pixels). Inputs may repeat. The output may overwrite one
of the inputs.

## Submitting safely

- Submit with `603185eb(d0 = job, d1 = 1, a0 = packet, a1 = 16)`. The worker then
  sets C+4 to 2 (done) or 3 (failed).
- A bridge function validates each record. It checks capacity = min(BC+12,
  BC+16) / 12 and limits on the number of inputs. **Physical camera test:** when
  it refused a record, the worker stopped, and the next use of the image engine
  hung the camera until a battery pull.
- **Physical camera test:** job 12 run without its setter completed, but its
  output was not checked. With its setter and the OM-5's geometry it runs on
  E-M5 III live-view frames (2912 × 544): the reset form (no accumulator input)
  passes the frame through, and add, slide and average give correct results.
  Submitted from the live-view task it records CPU 1 in job byte 69, see
  [Live ND](../../features/e-m5-iii/LIVE_ND.md#live-view-preview-on-the-e-m5-iii).

## Verification and limits

- The job tables were compared by SHA-256 of each resource entry across the
  container files of the listed builds. The native job map comes from the setter
  table, the wrappers and their callers in the pinned 1700 main.
- The job 11 results come from one E-M5 III running OM-5 job 11 on full-size
  frames, with 80 sampled output pixels compared against the average of the
  inputs. The purposes of jobs 0, 1, 2, 3, 5, 6, 7, 9 and 10 have not been
  checked by running them.
