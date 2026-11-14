# E-M5 III address spaces and loaded sections

At power-on the E-M5 III copies only a small part of its main program into RAM.
The rest arrives in ten sections that load in the background while the camera
is already starting. This is the main reason a patch can boot most of the time
and still fail now and then. This page gives the ranges, the load order and the
ready flags for that process.

Addresses refer to E-M5 III build 1700: container
`OLY_E_137_1700_0000_0000.BIN`, SHA-256
`939260fc22b4217fce64274eb5a6707d307a499804d8a316b6b39019c4afded2`; decoded main
(kind `0x100`, container address `0x40780000`) SHA-256
`4097f57751ac30c24589448865b2824891a754744eae63ab14359fd46c1cf4be`. Runtime
addresses use analysis base `0x60021020`, so runtime = base + offset in the
decoded main payload. Evidence is static disassembly unless a result is marked
as a physical camera test.

Terms used here:

- **Resident range:** code that is copied before anything else runs, so it is
  always in RAM.
- **Section:** a block of the main that a loader task copies in later.
- **Ready bit:** a flag the firmware sets once a section is copied and
  initialized.

## Startup copy and the resident range

The main entry `60021020` copies one range first. The copy goes from logical
flash `4078f000` to `a0030000` through `60022180`. Its exclusive end is the
immediate `600d0800` at `600211af`.

| Range | Loaded by | In RAM |
| --- | --- | --- |
| `60030000..600d0800` | startup copy | before the RTOS starts |
| `600d0800..600de000` | nothing | FF in the image; no literal references found |
| sections 1-10 | section loader task | in the background (see below) |

Raising the end immediate at `600211af` would also make the FF run after
`600d0800` resident. That is only a placement candidate, with the limits in
[code placement](../../safety/CODE_SPACE.md).

## Application sections

A loader task copies the remaining code in ten sections while startup goes on.
The loader is `60045e2e`, the descriptor table is `600272a4` and the end helper
is `60045dc5`. The load order is 1, 7, 2, 3, 4, 5, 6, 8, 9, 10.

| Section | Runtime range (exclusive end) |
| --- | --- |
| 1 | `600de000..6022d800` |
| 2 | `60298000..6056c000` |
| 3 | `60582000..605d4000` |
| 4 | `605da800..6079d800` |
| 5 | `..60bef800` |
| 6 | `60c17000..61124000` |
| 9 | `61209800..613bb000` |
| 10 | `..61478000` (end immediate at `60045e24`) |

After `61478000` the image is FF padding up to `61800fe0` and is never loaded.
Three places compute section 10's length from `60045dc5`: the loader
(`60045e33`) and two cache paths (`60045f0c`, `60045fc6`). Changing the end
immediate therefore moves all three.

## Section status

| Address | Meaning |
| --- | --- |
| `a26565c4` | loaded bits |
| `a26565c0` | ready bits, set after MMU/cache setup and the section's initializers |
| `60045eb3(n)` | waits for section `n`, then sets its ready bit |
| `60045d92(n)` | returns 1 when section `n` is ready |

Section 4 is bit 3 (`0x8`). Section 9 is bit 8 (`0x100`).

## Why early hooks need a ready test

The firmware prints progress tags during startup (from `60023bbc`). They give
this order:

1. `2_1`: section 2 ready. Tasks STB_SEQ, TAKE_EXPOSE, DSP0/DSP1, MVR and UI_OUT
   are created.
2. Section 3.
3. `3_4`: section 4 ready (`6019cf48`). FCS (focus), face detection, REC, USB and
   ISEQ start.
4. Sections 5 and 6.
5. `5_1`: sections 7-10.

Stock code never calls forward into a section without waiting for it. A patch
that branches from an early section into code placed in section 4 or 9 can run
before that code is in RAM.

**Physical camera test:** a patched build with such a hook in section 1 failed
intermittently at power-on. Sometimes it was dead at power-on, and sometimes it
showed live view and then reset in a loop. The same feature was then routed
through resident code that tests the ready bit at `a26565c0` and runs the
original instructions when the section is not ready. That build booted 10 times
out of 10.

## Verification and limits

- The ranges, immediates and order come from disassembly of the pinned main. To
  check them, disassemble `60021020..600212c0` (startup copy) and
  `60045d92..60045fd0` (loader, end helper and ready test), for example with
  `objdump -D -b binary -m am33-2 --adjust-vma=0x60021020`.
- The 10 boots show the guard fixed that one build. They do not prove that every
  early hook is safe, and the "no literal references" check for `600d0800..600de000`
  cannot rule out computed accesses.
