# Stock SD parameters and Wi-Fi debug shell

Stock firmware contains a parameter-file loader that can enable a Wi-Fi
diagnostic shell without a firmware patch. **Enduity reports physical success
on E-M5 III 1.7.** PEN-F 3101 has the same mechanism, verified through disassembly
and bounded native execution; physical PEN-F operation remains untested.
[Source: enduity, November 1, 2026](https://www.mu-43.com/threads/modified-firmware-looking-for-users.99804/post-1888641).

## SD file

The reported file, relative to the SD-card root, is `PARAMDT/CP000001.CSV`:

```text
Wifi shell,0xF971,1,1
```

The fields are a label, parameter ID, element count and value. `F971` is the
one-byte debug-enable parameter; the label is ignored. The loader searches the
FAT-style pattern `CP??????CSV` in `PARAMDT`, so the reported filename is one
valid match. Native PEN-F tests accept the exact line, LF/CRLF endings and a
different label. Zero or a missing entry does not enable this startup branch.

Enduity reports an automatically started **open Wi-Fi network**, debug-console
access and ordinary OI.Share connection. A brief battery removal before boot
was sometimes needed. PEN-F's network request is consistent with this report,
but its actual radio/security behavior has not been physically checked. An open
diagnostic network should only be enabled in a controlled test environment.

Cmdada identified the F971 startup gate on E-M10 I and proposed forcing the
getter with a firmware patch. The SD-file discovery provides a way to supply
that parameter using existing firmware code.
[Source: cmdada, October 24, 2026](https://www.mu-43.com/threads/modified-firmware-looking-for-users.99804/post-1886911).

## PEN-F path

| PEN-F 3101 address | Purpose |
| --- | --- |
| `605843a3` | Discover the parameter directory and matching files. |
| `6007363b`, `60073802` | Import files and parse CSV lines. |
| `600745a1`, `600750ee` | Install a RAM override and read a typed parameter. |
| `6007439b` | Read F971, wait for readiness ID 6 and request debug Wi-Fi. |
| `60aaa71c` | Build the network request using stored SSID/password. |
| `60aaa820` | Construct listener on `0.0.0.0:23`, backlog 1. |
| `60aaa5d5` | Accept worker, launching receive/transmit tasks. |
| `60aaa8d3` | Forward a completed command line to message buffer `CE`. |
| `6006fc98`, `601a6f5a` | Receive that message and return the line to U_SHELL. |
| `601a700e`, `601a6f6c` | User-shell task and command dispatcher. |

The import uses a 128 KiB record arena at `61ac7ac0`, with lookup indices at
`a1c281e4`/`a1c301e4` and an active flag at `a1c281e0`. Clear routine `600745d2`
removes the override in native tests. No nonvolatile write was identified along
the traced import path. This supports a temporary RAM override, but does not
prove every hot-removal, shutdown or restart scenario restores the original state.
F971 is a start gate, not a live on/off switch: its zero branch does not shut
down Wi-Fi that is already running.

The port-23 service feeds the existing Olympus RTOS command shell. It is not a
Linux shell. Its table at `601c8424` has 59 commands, including `help`, `prm`,
`flash`, `file`, `mcon`, `buff`, `isp` and `ui`. No credential challenge was found
in the inspected receive-to-command path; a complete physical session has not
been independently captured.

This supplies a plausible external route to already mapped diagnostic readers,
including flash-reading code. It does **not** qualify every shell command for
physical use: some write storage or use shared scratch memory. Lower flash-read
review found that the stock dump command can enter flash maintenance and has
locking and allocation-failure problems. See
[flash readers and diagnostic dumps](../../boot/pen-f/FLASH_READERS.md).
The transmit ring is 8 KiB and can lose unread output; shell access alone does
not establish a safe or complete boot-dump procedure.

## Related parameter F981

PhotoDmiK pointed out the nearby F981 access.
[Source: November 2, 2026](https://www.mu-43.com/threads/modified-firmware-looking-for-users.99804/post-1888681).
On PEN-F, it selects RAM diagnostic capture through `6002302a`:

| Value | Behavior |
| ---: | --- |
| 0 | Capture disabled. |
| 1 | Fill an 8 KiB buffer, stopping at its limit. |
| 2 | Circular capture in the same buffer. |

The buffer begins at `a1c532c0`; its mode byte is at `a1c552c8`. F981 is separate
from Wi-Fi enable and is unnecessary for enabling the shell. This detailed
interpretation is verified for PEN-F, not assumed for every model.
Native cases verify buffer writes, whole-message rejection when bounded capture
has insufficient room, circular wrapping and refusal to change to invalid mode 3.

The callback also checks `7B64` bit 31. That refreshes 106 cached strobe-control
parameter pointers, through `602db9f0 → 602db754`; it is not a firmware-update
operation or another shell switch. See [other debug files and hooks](DEBUG_FILES.md).

## Cross-model landmarks

| Role | PEN-F 3101 | E-M5 III 1700 | E-M10 I 1400 |
| --- | --- | --- | --- |
| CSV discovery | `605843a3` | `60615f6d` | `7de87a33` |
| Debug selection | `6007439b` | `6005bafb` | `7da88235` |
| Wi-Fi request | `60aaa71c` | `6122e9f6` | `7e712e61` |

E-M5 III has the same import-completion callback pattern and socket bind;
its readiness identifier and RAM layout differ. E-M10 also contains the file
patterns and F971 startup test. Addresses and network-structure offsets must be
mapped for each build.

## Verification and limits

[penf_sd_debug_probe.py](../../../tools/penf_sd_debug_probe.py) runs 19 cases using
the pinned PEN-F main and MN103 engine:

```sh
python3 tools/penf_sd_debug_probe.py --out generated/sd-debug.json
```

Parsing, override installation/readback/clear and startup selection execute
original instructions. Separate cases verify socket arguments and the line-to-
message-buffer callback. Readiness, delays, Wi-Fi calls, network I/O, task creation
and queue sending are modeled. Filesystem delivery and a complete concurrent
boot/network/shell session are outside the tests. Image hashes and report
attribution are in [community provenance](../../../provenance/community-reports.json).
The strobe-refresh case supplies synthetic parameter IDs and models pointer
resolution; RAM-log cases suppress serial output and model interrupt services.

The CSV mechanism imports parameters; it does not establish stock executable
loading from SD. [Cmdada's plugin loader](../../tooling/e-m10/PLUGINS.md) is a
separate patched implementation. The debug shell also depends on running main
firmware, so it is not an independent [recovery environment](../../boot/pen-f/RECOVERY.md).
