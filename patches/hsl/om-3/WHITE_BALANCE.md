# Per-COLOR white balance implementation

OM-3 firmware 1.1, build 1100 only. Experimental: no physical camera test.
The combined decoded main SHA-256 is
`659f6c517cb30688169acb464ee85eac66e9832460b7bf9a892e5f6bfba02cc5`.

## Behaviour

Use the existing WB controls. COLOR1–4 independently remember the WB mode,
custom Kelvin, and the current A/B and G/M corrections. On first use, a profile
inherits the currently active WB. Other picture modes share a fifth WB record;
leaving COLOR recalls it. These records follow the native settings bank.
One-touch choices refer to the camera's four shared measurement slots. Replacing
a measurement therefore affects every profile referencing that slot.

Each profile remembers one current WB configuration. The native per-WB-mode
tint tables remain shared; this does not create thirteen tint presets per COLOR
profile. Switching COLOR profiles restores the saved configuration's correction
pair through the appropriate native backing entries.

## Native calls and hook

`wb.s` intercepts the five-byte prologue of native commit `603f1ea1`. Its caller
already supplies the register-saving frame. Unrelated IDs replay the prologue
immediately. WB IDs and picture mode 901 pass through a section-1 dispatcher,
which checks section 4's loaded bit and, when necessary, calls `60045ed5(4)`.
After either the loaded-bit check or a load attempt, the dispatcher verifies
the XOR of all 123 body words through the uncached alias. A mismatch clears
section 4's loaded bit and replays the stock commit without entering the WB
body. This guards extension execution; it cannot repair other section data or
qualify hardware cache behaviour. See [hardening tests](HARDENING.md).
The WB body occupies `60a8f100..60a8f2ec`, inside section 4's loaded FF tail.
The dispatcher occupies `6031ef14..6031ef9c`, after the HSL body and before its
state. These placements are separate from the firmware container checks.

The wrapper lets the stock commit finish its dependency callbacks, then saves
WB edits for 1578, 1632 and 1580–1605. A picture-mode change saves the outgoing
record before the stock commit, then recalls the destination record afterwards.
A guard at HSL state +56 prevents the extension's own WB writes recursing.
There is no cached settings-bank pointer or delayed polling loop.

Recall uses `60aea1de(id,value,a0=1)`, the native UI write path observed during
GUI edits. It writes 1578 (displayed WB choice), 1632 (Kelvin), then the backing
A/B and G/M entries for that choice. This updates the active values and their
backing records through stock propagation. Passing an integer to the distinct
`60afa3f9` API for grouped settings 9 or 901 is incorrect: that interface expects
an array and does not perform the UI-value conversion.

| WB choice | Display value | A/B ID | G/M ID |
| --- | ---: | ---: | ---: |
| Auto | 0 | 1580 | 1593 |
| Underwater | 18 | 1581 | 1594 |
| Fluorescent | 3 | 1582 | 1595 |
| Incandescent | 1 | 1583 | 1596 |
| Sunny | 6 | 1584 | 1597 |
| Flash | 17 | 1585 | 1598 |
| Cloudy | 7 | 1586 | 1599 |
| Shade | 8 | 1587 | 1600 |
| One-touch 1–4 | 13–16 | 1588–1591 | 1601–1604 |
| Custom Kelvin | 9 | 1592 | 1605 |

## Stored words

Part 1 of alternate record `8b64` uses IDs 904–923, four words each:
COLOR1 starts at 904, COLOR2 at 908, COLOR3 at 912, COLOR4 at 916, and the
non-COLOR record at 920. HSL's IDs 928–975 and all part-0 cells are separate.

| Word | Contents |
| --- | --- |
| 0 | WB display value |
| 1 | Custom Kelvin |
| 2 | Signed A/B byte, signed G/M byte, upper 16 bits zero |
| 3 | Words 0 xor 1 xor 2 xor `57420101` |

Saving clears word 3 first and writes it last. Recall checks the checksum,
mode membership, Kelvin range 2000–14000 and both corrections −7…+7. Invalid
records inherit and save the current WB. The checksum detects accidental
inconsistency; this is not a storage transaction or proof of flash-write atomicity.

All 22 examined native mode tables select part 0 for IDs 904–923. Native
alternate-cell persistence and bank recall were exercised. This is bounded
ownership evidence: reset, defaults, backup and every dynamic caller have not
been qualified. Section reload clears the volatile recursion guard, and its
concurrency with an in-progress recall remains untested.

## Reproduce the integration test

Build `decoded/0100.bin` with the shared builder, then run:

```sh
python3 tools/om3_wb_emulator_probe.py \
  --emulator /path/to/om-emu --node /path/to/node \
  --image generated/om3-hsl/decoded/0100.bin
```

The probe copies OM-Emu's source into a temporary directory and links its
unpacked firmware without writing to those files. It checks the candidate hash and permitted edit
ranges. The supplied checkout is not edited. Tested with OM-Emu commit
`21b04a5cea6dd725117c5b1d4611a98891648b10` and Node 26.12.1.

The harness explicitly models a successful read of the exact section-4 image,
accepts the restored SCPU backup marker, and omits the unsupported ARGB display
plane. WB save/recall is executed by the assembled firmware, never supplied by
the harness. The test covers four different WB records, native GUI profile
switches, native WB dial edits, non-COLOR recall, power cycles, process restart,
custom-bank edits and return, all thirteen WB selections, corrupt/invalid records,
and HSL coexistence. With the native default save policy, unassigned edits in
C1 are discarded on its next recall; this was checked for native WB and the
extension records. Assigning C1 or enabling a different save policy was not tested.

At each WB check it also executes unmodified stock slice
`604876ba..60487736` against the live native settings DB, with an explicit scratch
output and stop boundary. It verifies A/B at +33, G/M at +34 and Kelvin at +38,
plus unchanged surrounding bytes. This proves a compact WB parameter copy sees
the recalled values. It does not execute a complete shutter-to-JPEG path or
establish when all WB inputs are locked for queued images.

A controlled native processing-slice test also demonstrates that an earlier
Kelvin snapshot can be combined with later live tint values. This is a remaining
capture-timing concern, described in [HARDENING.md](HARDENING.md); a complete
image-owned WB path has not been established.

No camera was contacted or flashed. Live view, ISP/JPEG output, RAW metadata,
in-camera development, burst timing, real startup/loading, reset, assigning a
custom mode and settings backup remain physical or further research checks.
The builder continues to withhold an installable package by default.
