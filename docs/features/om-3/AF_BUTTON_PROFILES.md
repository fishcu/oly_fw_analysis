# Independent stock AF target profiles on OM-3

The requested behavior is an independent stock target/zone configuration for
shutter half press and AF-ON. Half press follows the current SCP Subject Detect
choice, including Off and all six subject classes. AF-ON bypasses detection;
S-AF/C-AF remains shared. AF-ON precedence while both are held is proposed.

The research prototype executes these transitions under emulator fixtures.
It is **not ready to flash**. No camera was accessed or flashed, and no
installable modified SD image is distributed.

Later supplemental work recovered queue 95's 93-slot dispatch table and common
request/reply format, applied a verified carry/overflow fix to the local Ghidra
MN10300 language, and reran the labelled stock-reset scenario. That run reaches
queue-95 command 0x1d and stops waiting for its receiver's reply on buffer 1032;
it does not establish successful backend connection or autofocus. See the
[current assessment and continuation plan](../../../research/om3_af_profiles/AF-GAP-CLOSURE-ASSESSMENT.md)
and [supplemental evidence notes](../../../research/om3_af_profiles/README.md#supplemental-af-command-and-emulator-findings).

## Input and address spaces

All findings concern OM-3 version 1.1, catalog filename
`OLY_E_147_1100_0000_0000.BIN`, 240,517,120 bytes, SHA-256
`8c133084414533159f587bf46bfb4152714c4074312a47c8d8503e33d605696d`.
The decoded main payload is 33,554,368 bytes, SHA-256
`5e8d376e9111a44ac0352f26030d7c1b17026d42c45f3600cfa02a0e8c5b7d59`.
Code addresses below use CPU base `0x60021020`. Container/logical storage
addresses and cached/uncached aliases are different address spaces. Constants
are specific to this exact input, not every firmware with the same version label.

## Configuration and transition mechanism

The source reads normal stock target settings for half press and existing AF
Home settings for AF-ON, reusing stock controls rather than adding a new menu.
UI enum `0x99a1` differs from internal area kind `0x84d1`. Native converter
`0x609b3ecd` and target builder `0x609b3c79` provide stock normalization.
Home sources include `0x9fa1` (enum), `0x99d2` (position), `0xdfa1` (size),
`0x1db1` / `0x1dc1` (independent area/position orientation enables), and
`0x1dd1` / `0x1df1` (custom dimensions/priority). The Home-recall command
mutates normal settings; the prototype instead reads Home settings directly.

SCP selection is `0x1e71[0]`. The prototype retains it, applies effective Off
while AF-ON owns AF, reconciles native worker start/stop, publishes a staged
ten-byte target record, calls native target update `0x609029f1` and snapshot
`0x608ff478`, and applies the desired worker/detection mode. Shared focus mode
uses `0xc021`; `0x3851` is magnification type, not focus mode.

The integrated source uses a dedicated mutex, inactive records, guarded target
accessor/mode setter and stock fallbacks. Mutex-creation failure disables the
extension. Hooks and data occupy tested sections 1/2/4; the effective-mode guard
is in section 2 to avoid its former dependency on section 4 being loaded.
The initializer runs through the stock constructor loop. These bounded tests
do not establish complete boot or arbitrary reload ordering.

## Native button and capture integration

Original bodies: half press `0x610b9197`, AF-ON press `0x610b962a`, AF-ON
release `0x610b9653`, half release `0x610b96f0`. The basic native queue-dispatch
fixture lets all four return, but reply status 1 maps to API error
`0xf0000001`: this proves error cleanup, not successful AF. Negative wait inputs
cause native retry, not a successful completion.

More complete native startup runs singleton/prototype constructors, a supplied
start event and 38 native messages, reaching root state 11. AF-ON request
`0x3bf` reaches capture router `0x62b7315c` in state 7 with null active/requested
backend pointers (`+0xb8` / `+0xbc`), is buffered, and waits at `0x60dd896d`.
A complete unmodified-payload control reaches the same boundary. This locates
a missing operational context in the harness, not successful AF integration.

Native shooting-component factory `0x60dae512` returns `0x62b71778` and
constructs `CmpSts_AEAFLockController` at `0x62b72f2c`, vtable `0x60ebda38`.
The conditional factory test supplies a parent and diagnostic counter
`0x98e000d0=0`. Supplied connection event `0x114` advances to state 12,
requested backend `0x62b71778`, active backend null, then requires unprovided
kernel task/object state `0x97f00004` via `0x600303db` / `0x6004f3bd`.
The connection event's normal producer and timing remain unproven.

That synchronous request targets task 207 (ROM `0x60043312`), command 8.
Handler `0x61061b4f` leads toward producer `0x61061c4c`. A separate conditional
probe bypasses the uninitialized task/RPC layer: native `0x6007a931` constructs
a 36-byte packet, header type `0x0b`, payload length `0x1c`, command `0x40`,
callback `0x610619a7`, reaching transport `0x6007a7b5`, port 2, timeout 5000.
It stops before submission. No positive device/AF response is invented.

## Validation and open requirements

The recorded complete run has separate groups: 11 RAM-setting checks, 15
profile groups, three decoder groups and two mutex-ownership groups. Profile
coverage includes all 11 Home enums, three supplied poses, independent
orientation enables, SCP Off/six classes, shared focus mode, 280 mixed button
events, native gates, invalid-pointer and initialization-failure fallbacks.
These distinct scopes must not be added into a feature-success score.

An instruction observer made 1,984,566 checks without seeing a published record
overwritten before pointer replacement. This does not prove delayed-reader
lifetime or cross-CPU ordering. Pose source `0xe91[3]` remains a candidate.
Synthetic cache input is not physical NVM reload.

The integrated component passes native validator `0x6106b712` and its complete
32 MiB checksum loop. A full six-part encoded container was reconstructed only
in RAM, with the other five components unchanged. Integrated payload SHA-256:
`961f3dbb7049fb2653edb19f3bf840919651f911a23c64636985a6a637b6450a`.
Decoded full-component fixture SHA-256:
`6a3424f1417950c55708bd3d7e49ccea8a574240af671dd555c979e9a6104dfd`.
Checksum/placement validation does not establish updater admission or bootability.

Still open: successful operational AF; actual orientation/UI editing/display;
full-shutter/burst, sleep/wake, mode recall and reset; concurrency/record
lifetime; physical settings reload; whole boot; SD admission and intact-camera
recovery. These include unfinished software analysis/modeling, not exclusively
hardware-only checks. Stock SD selection uses `DCOLYMP` / `E147????BIN`;
selector probes model the filesystem/acknowledgements. Community
[manual-update instructions](https://github.com/iKenndac/om-1-manual-firmware-install)
do not prove recovery from a broken modified startup.

Source, compact results, original manifests and reproduction instructions:
[research workspace](../../../research/om3_af_profiles/README.md).
