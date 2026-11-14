# E-M5 III ARM co-processor and the ISC mailbox

Besides the MN103 cores that run the camera, the E-M5 III's processor has one ARM
Cortex-A9 core running its own Linux. It handles wireless (Wi-Fi, Bluetooth LE,
the phone app's HTTP API, remote live view) and one computation for handheld
High Res. It does not handle autofocus. The two sides talk through a hardware
mailbox the firmware calls **ISC** (Inter System Communication). This page covers
where the ARM software is stored, which programs use which mailbox channels, and
how the main CPU powers the ARM on and off. Build identities are in
[address spaces](../../format/e-m5-iii/ADDRESS_SPACES.md).

Evidence: static disassembly of the MN103 main and of the extracted ARM programs,
unless a result is marked as a **physical camera test**.

Terms used here:

- **CA9:** the firmware's name for the Cortex-A9 side.
- **Channel:** one of the mailbox's numbered message queues.
- **Take / Wi-Fi owner:** the two requesters the native power manager tracks
  when deciding whether the ARM stays on.

## Where the ARM software is

| Body | Location | Kernel | Wi-Fi chip |
| --- | --- | --- | --- |
| E-M5 III 1700 | PIC component sub-block `45ef4000` (no checksum of its own) | Linux 4.4.127 plus a uITRON image | CYW43455 |
| E-M1 III 1600 | sub-block `46000000` | 4.4.127 | CYW43455 |
| OM-5 1200 | sub-block `44ba0000`; same device tree | 4.4.127 | CYW43455 |
| OM-5 II 1100 | sub-block `44640000` | 5.10.197 | CYW43439 |
| OM-1 / OM-1 II | bank 9 | AArch64 Cortex-A53, 4.14.222 | CYW43455 |

On the E-M5 III the image is a chain: a vector stub, a uITRON image, a Linux
stub, the zImage kernel, device tree `dc13.dtb`, a gzip initramfs and an LZO
squashfs mounted at `/usr`. Linux sees 36 MB at ARM-physical 0. The console
(ttyS0, `9a500400`) runs a root shell.

## Programs and channels

At boot `/etc/init.d/S99oly` starts `dc13_rtc`, `sccore start` and `hhhr`.

| Program | Role | ISC channels |
| --- | --- | --- |
| sccore | supervisor, Wi-Fi start/stop, shell | tx 27, rx 26; command lines rx 15, output tx 14 |
| hhhr | handheld High Res matrix maths (NEON/VFP) | rx 30 (48-byte request), tx 31 to CPU0 (112-byte reply, three 3×3 matrices) |
| isc_olnet | Wi-Fi control | 17-21 |
| remocon | Wi-Fi remote live view over UDP | 1, 2 |
| isc_cgi / isc_file | phone-app HTTP API / files | 11-13, 16 / 5, 6, 8 |
| blebridge, bsa_server | Bluetooth LE (GATT server only) | 28, 29 |

The `hhhr` request: +0 Y image pointer, +4 statistics buffer pointer, +8 u16
frame index minus 1, +14/+16 = `0x510`/`0x3cc`, +18/+20 = 4, +0x2c a main-CPU
result pointer. Index 0 maps (+0) + `0x80000000` (about 1.3 MB); other indexes map
(+4) + `0x80000000` + `0x40` (about 22 KB). Both maps are read-only and shared,
the mmap result is not checked, and a mailbox error makes the program exit. It
replies 112 bytes even if mapping fails. OM-5 sends from compose (`603911c4` via
`60376613`) with a 100 ms send, then a blocking receive.

## The mailbox (main-CPU side)

- 48 channels; control blocks at `8ff00c00`; 128 KB shared memory at `62fe0000`
  (ARM view `22fe0000`).
- Send `61205800`. Blocking receive `6120581c` (service code 3). Non-blocking
  receive is service code 2 (`6120624f`, returns -5 when empty) through
  dispatcher `61206cfe`.
- The send and dispatcher locks spin with no timeout. There is no per-channel
  readiness check; native senders only test the "ARM started" byte `a2624f09`.
- ARM-physical address = MN103 address AND `0x3fffffff` (`600590c9`). ARM Linux
  uses MN103 `c0000000..c2aa0000` while it runs.

## Powering the ARM

Task TSK_CA9PWR_MNGR (loop `6005978d`) takes 16-byte requests on message buffer
`60041252`. Word +8: low half 1 = on, 0 = off; high half 0 = Take owner, 1 = Wi-Fi
owner. Owner flags: Take `a2624f0c`, Wi-Fi `a2624f10`. Take off stops the ARM only
if Wi-Fi is not held. Wi-Fi off (`0x00010000`) always stops it, then restarts it
if Take is held.

- Asynchronous post: `600514a2(d0 = id, d1 = timeout, a0 = &{ptr, 16})`; the
  payload is copied. The synchronous variant `600548f7` waits for Linux to boot.
- Every start reloads the ARM image from flash (`60058c3c`). The start worker
  `60058e21` waits for the ARM's boot message on channel 27, then sets
  `a2624f09` = 1. A 10 s start alarm (`60058e07`) faults the camera if that
  message never comes.
- An ARM watchdog interrupt (IRQ 171, `600584ba`) spins the main CPU.
- If `a2624f30` holds `0x77777777`, the image loader instead reads `bootlinux`,
  `zImage`, `dc13.dtb`, `rootfscpio` and `rootfssq` from `C:\TARGET\` on the card,
  with no size check. The debug command `arm load4` only sets that word.

**Physical camera tests:**

| Test | Result |
| --- | --- |
| Wireless off; wireless on with no phone | ARM not started (`a2624f09` = 0) |
| Phone connected in the phone app | ARM started; shots via the app's remote shutter normal |
| Send on channel 30 with the ARM stopped | black screen, then the camera powered off |
| Take on posted during a shot; Take off posted during a shot | camera reset in both cases |
| Take on and Take off posted at the first Idle/Standby after a shot | ARM booted and shut down cleanly; body-button shots normal in between |

## Verification and limits

- The channel map and request layouts come from the ARM binaries extracted from
  the PIC component of the pinned 1700 file. The main-CPU addresses come from the
  pinned 1700 main.
- The physical tests ran on one E-M5 III. The ARM's CPU clock is unknown, and a
  channel 30 request to `hhhr` with the ARM running has not been run yet.
