# Firmware update and recovery

PEN-F's SD client, shared update service and flash backend are mapped. The
physical **OK + power → SD client** selection is not connected end to end in
the available firmware. This distinction limits recovery claims.

## SD file selection and service

The reviewed client searches `DCOLYMP` using FAT-style pattern `E122????BIN`.
`E1229999.BIN` is the usual PEN-F SD filename. Model codes differ between cameras;
the filename is not a substitute for correct component headers.

| PEN-F 3101 landmark | Role |
| --- | --- |
| `60b1cbb5`, task 95 | SD updater client |
| `6003a128` | Task descriptor; priority 45, stack 2048 bytes |
| `6059cdb5` | Eleven-byte FAT filename matcher |
| `60b1cfba` | Hexadecimal suffix parser |
| `60b1d527` | Shared updater |
| `601c8e6e` | Fallback that starts USTART1/task 47 and exits the client |

The SD client mounts storage, finds a matching file, reads it and forwards it
to the firmware service. Native fixtures exercise this chain with modeled
filesystem/kernel calls. No matching file takes the ordinary-startup fallback.

The fallback is consistent with an alternate early startup route, but does not
prove where that route is selected. Task 95's descriptor is not auto-started;
ordinary constant-ID activation searches have not found the physical trigger.
A missing direct call does not rule out computed dispatch or pre-main code.

## Validation and writing are separate operations

| Shared updater mode | Purpose |
| ---: | --- |
| 0 | SD-style validate, then request component writes |
| 2 | USB check/decode, without writing |
| 1 | USB commit of the previously decoded buffer |

Native tests reject a stale main checksum with error `0x3211` before any flash
backend request. A valid component followed by a corrupt component is rejected
before writing either. Correct same-version main-only packages and stock
restoration pass the reviewed acceptance path.

This establishes the mapped routine's behavior, not proof that every possible
physical recovery entry uses it. Container validation also does not test whether
modified program logic will run correctly.

## Flash backend limitations

The reviewed main update rewrites a whole component. PEN-F main is 163 × 128 KiB
erase units; lower programming uses 2 KiB pages. Native traces identify erase,
program and readback checking, but some upper wrappers discard lower error
returns. A successful upper status is therefore not a complete verification
of physical programming.

The known backend is not an automatic rollback design. Small redundant settings
banks are not copies of the main firmware. No independent USB rescue loader or
immutable OK-button boot ROM has been established for PEN-F.

[E-M10 I reports](../e-m10/RECOVERY.md) describe separate boot stages and successful
SD recovery, followed by a simulated update that overwrites the first stage.
They provide a boot-dump method and useful comparison, not PEN-F recovery proof.

The [stock SD debug switch](../../protocols/pen-f/WIFI_DEBUG.md) supplies a
promising Wi-Fi route to PEN-F's existing diagnostic shell and flash readers.
Its parameter import and shell wiring are verified offline; physical PEN-F
operation and a boot dump remain unverified. The stock dump command is
[not qualified as read-only](FLASH_READERS.md): its reader can perform flash
maintenance, bypasses normal serialization and mishandles buffer exhaustion.
It runs from main firmware and
does not provide recovery when that environment cannot start.

A separate `S122????BIN` BOOT update path and logical destination `80000000`
exist in code. The ordinary E-file does not provide that earlier image. Its
existence indicates writable boot-related storage; it does not identify every
reset instruction or establish an immutable recovery layer.

## What physical tests establish

PEN-F component-selective HSL installs, restoration to stock and reinstalling
modified firmware have worked on a physical camera. A UI-related restart was
also recovered by restoring an earlier main. These establish recovery from
those specific states, not arbitrary startup corruption.

OM-3 added-code recovery is a contributor report on another model. It is useful
precedent, but does not prove PEN-F boot architecture or a general brick rate.

In bounded emulator tests, the mapped SD/service updater can run while selected
COLOR code, tables and patch regions are inaccessible. That isolates those
routines after entry; the untraced physical entry, concurrent tasks and storage
hardware remain outside the result.

## Runtime flash writes

Application code contains settings/calibration writes and flash service paths.
There is no demonstrated blanket protection that makes all flash unwritable
during ordinary operation. A patch that corrupts pointers or control flow must
not be assumed harmless merely because it is outside the updater.

See [startup](STARTUP.md), [USB initiation](../../protocols/pen-f/USB_UPDATE.md),
[container integrity](../../format/CONTAINERS.md) and [code space](../../safety/CODE_SPACE.md).
