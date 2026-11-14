# E-M5 III firmware update and recovery

This page covers what the E-M5 III checks at power-on, what a firmware update
writes and in what order, and which failures an SD card can recover from. The
short version: the SD updater checks the whole file before it writes anything,
but the updater is part of the main program. A patch that crashes every boot
early enough can leave no SD-card rescue.

Addresses refer to E-M5 III build 1700 (identities in
[address spaces](../../format/e-m5-iii/ADDRESS_SPACES.md)). Evidence is static
disassembly unless a result is marked as **native execution** (original
instructions run in om-emu with modeled hardware) or as a **physical camera
test**.

Terms used here:

- **Watchdog:** a timer that resets the camera if software stops refreshing it.
- **Boot loop:** a camera that faults, resets and faults again on every start.
- **Component:** one flash image inside the update file (main, OSD, RESCOM, PIC,
  LUKE).

## What is checked at power-on

- The code that runs before the main entry (boot area `40000000..40060000`, or a
  mask ROM) is not available. Whether it checks the main component is unknown.
- The main does not check itself. The startup copy and the section loader
  (`60045e2e`) copy without a checksum or signature, and a read error is only
  logged. Section 7's constructors (table `611d4364`) run as soon as it loads.
- Every boot reads the other flash components. `60166a64` (`res.c`, on the
  USRSTART_LOAD path) reads OSD `42160000`, RESCOM `43f60000`, PIC `47180000` and
  data `47a80000`.
- The hardware watchdog is in the sub-CPU. `600226e1(n)` writes `n` to `98e0008c`
  bits 0-5 with command `20041001`. Startup sets 10 at `60045200`, and task PER_WDT
  (id 25, `600741c0`) refreshes it through `4700101b` every 3 s.
- "COMMON Reboot" (`6005849f`), the NMI handlers (to `60069f5a`; registers saved
  at `629be000`, "NMI_INT Hassei!") and the flash write guard (`600c4680`) all
  reset the same way: set watchdog 1, then spin. So a fault resets in about a
  second, and a fault on every boot is a boot loop.
- **Physical camera test:** a hang inside one task does not reset the camera,
  because PER_WDT keeps refreshing the watchdog. A battery pull was needed.

## Flash map and runtime writes

The flash is 128 MB at `40000000` (alias `80000000`).

| Range | Content |
| --- | --- |
| `40000000..40060000` | boot area; written only by update kind BOOT (`0x10`) |
| `40780000..41f60000` | main (kind `0x100`) |
| `42160000` | OSD (`0x101`) |
| `43f60000` | RESCOM (`0x106`) |
| `47180000..47a80000` | PIC (`0x102`) |

During normal operation, writes are allowed only to `40060000..40780000`,
`41f60000..42160000` and `47a80000..48000000`. A write anywhere else trips the
guard (`600c463a`), which sets watchdog `0x81` and spins, so the camera resets.

## SD update

The SD file is `DCOLYMP/E137????BIN`, usually `E1379999.BIN`. Holding OK at
power-on selects it. The updater is part of the main and has the same design and
task ids as the E-P7:

| Landmark | Role |
| --- | --- |
| `60c3a1b3`, task 88 | FIRMUP_CLI (SD client); no static start found |
| `60c3a638`, task 18 | FIRMUP_SRV; started only in USRSTART5 (`6019de8a`), after all ten sections are ready |
| task 118, `601fca3a` | FIRMUP_LED |
| `60c3aa36(buf, size, mode, out)` | validator |
| `609ee601` | `start_usb_firmup` (USB updates) |

**The file is validated before anything is written.** The validator checks every
component in the file: model `0x1370`, type `E`, header equal to trailer, and a
word checksum over the descrambled payload. It does not check the version.

**Native execution:** the stock 1700 file passes. With one byte flipped it
returns `0x3211`. An OM-5 file and a truncated file both return `0x3202`. None of
these cases writes to flash.

**Write order (native execution of the camera's writer on the stock file):**
LUKE (`0x10e`, sent to the IS sub-CPU), then PIC, RESCOM, OSD, and **the main
last**. Each flash component is erased in full, programmed and read back
(`60022353`, `600c4922`). There is no rollback.

The lamp is solid while working (255), blinks slowly on success (250) and blinks
fast on failure (100). Then the updater waits for power-off. The solid and
slow-blink states were seen on the camera.

## What an SD card can recover

The SD and USB updaters need almost the whole startup: the startup copy, the
loader, all ten sections, USRSTART2-5, the file-system task and the resource
reads. No separate rescue loader has been found.

| Failure | Expected recovery | Evidence |
| --- | --- | --- |
| Corrupt, wrong-model or truncated file | rejected before writing; fast blink | native execution |
| Crash only on a feature path | power off (battery pull if hung), boot, reflash | physical camera test |
| Intermittent boot failure from a section-load race | retry power-on with OK held | race seen on the camera; retry inferred |
| Crash on every normal boot in a shooting, live-view, lens or USB hook | OK + power with a stock file, if the update boot does not start the shooting app | inferred |
| Crash in the startup chain (USRSTART, loader, section 7 constructors, file system, resource reads) | not reachable by SD or USB | inferred |
| Power loss while the main is being written | main partly erased | inferred from the write order |

## Verification and limits

- The validator and write-order results came from running the camera's own code
  in om-emu on the pinned 1700 file, with flash writes recorded rather than
  performed. The hardware below the flash driver is modeled.
- Not yet established: what starts FIRMUP_CLI, and whether the OK-held boot skips
  the shooting application. A test that writes nothing would settle both: put the
  stock file with its last byte changed on the card, hold OK at power-on, and
  expect a fast blink.
