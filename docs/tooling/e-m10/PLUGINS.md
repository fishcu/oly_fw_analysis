# E-M10 I SD-card plugins

[cmdada/em10-fw](https://github.com/cmdada/em10-fw/tree/6adb3bef36239859ae3fcd94b0dbb7db6de6ffa1)
implements a resident loader for **E-M10 Mark I 1.4**. Installing it requires a
firmware update once. Later plugin changes are files on the SD card, loaded into
RAM at startup. Working hardware is an author report supported by source and
a photograph of the camera's Homebrew screen; it has not been retested here.

## Loading and callbacks

The loader reads `C:\PLUGINS\LOAD.TXT`, then each named `.EMP` file. It loads
at most six plugins into a shared 640 KiB arena and calls each plugin's
`em_main(api,self)`. That entry registers settings and callbacks. The current
SDK is API 7; older prose still refers to earlier versions.

| Part | Implementation |
| --- | --- |
| File format | `EMP1`; 32-byte header, text, data and relocation list; BSS is zeroed |
| Relocation | Absolute words are rebased byte by byte, including unaligned instruction operands |
| Memory | Cached code/rodata; uncached data/BSS/shared allocations |
| Load trigger | FILEFGND's message loop at `7DE9A297`, with up to 200 attempts for the list |
| Settings | `SETTINGS.TXT` on SD; loader/menu bookkeeping is deferred to the file task |
| Capture | Raw/YCC callbacks before final JPEG encoding; hardware-register callback separately |
| UI | Setup's Firmware screen repurposed as Homebrew |

The source loads once per startup. It has no general unload/reload mechanism,
and allocations are never freed. Removing a bad plugin can prevent its next
initialization, provided the resident loader still runs. Plugins execute native
code with camera privileges; this is not an exception sandbox or protection
against flash writes.

File-task context matters. The author reports that loading from a GUI callback
deadlocked the physical camera, although emulated file calls succeeded. The
loader now defers its own I/O to FILEFGND. SDK plugins can still call native file
functions directly, so this change does not make every callback context safe.

## Resident code and plugin RAM

The first section descriptor at `7D9988E8` ends at `7DC9D800`. The `load-padding`
patch extends it to `7DD00000`: two changed bytes cause another 403,456 bytes
to be copied. The resident loader uses this extension. The separate plugin
arena at `7E600000..7E6A0000` is populated from SD, not by that section patch.

Independent checks established:

- All 22 existing-code/data guards in the plugin patch match stock 1.4.
- The proposed resident tail and plugin arena are FF in the stock file.
- Under the upstream emulator's flash-read model, the extended section becomes
  resident byte-for-byte; stock leaves it as initial RAM noise. The separate
  plugin arena is unchanged by the descriptor edit.

These establish placement mechanics, not complete RAM ownership. Section
reloads, later uses, caches and DMA still need model-specific review. See
[code-space qualification](../../safety/CODE_SPACE.md).

The loader checks magic, API and aggregate size, but lacks an independent
entry-offset bound and per-relocation four-byte containment checks. Its size
arithmetic also needs overflow handling before accepting arbitrary plugin
files. It is useful development source, not a hardened general plugin format.

## Emulator and reuse

The upstream three-core emulator was built and independently run to a drawn
stock camera GUI with strict alignment stops enabled. It models RTOS scheduling,
interrupts, display and storage enough for useful UI tests. It starts at main,
supplies the early loader state, models flash reads and shortcuts selected
waits. It does not produce sensor/ISP image data or prove hardware timing.
Its `EMU_SD` file shortcut bypasses the task dispatch that caused the historical
deadlock; tests must retain that limitation.

This complements the [bounded native-call harness](../EMULATOR.md). The upstream
project also includes a FreeRTOS port. A forum post claims an early physical
UART/SPI boot, while the README labels it emulator-only; complete camera
firmware operation on FreeRTOS is not established.

Use [em10_source_audit.py](../../../tools/em10_source_audit.py) to reproduce the
static checks without running the upstream patcher:

```sh
python3 tools/em10_source_audit.py \
  --firmware /path/to/OLY_E_113_1400_0000_0000.BIN \
  --upstream /path/to/em10-fw \
  --out generated/em10-source-audit.json
```

The audit pins the stock input and records the source hashes it inspected.
Upstream source is GPL-3.0 with listed third-party exceptions. Porting to another
body requires its own hooks, ABI, memory ownership and services; the E-M10
addresses are not portable.
