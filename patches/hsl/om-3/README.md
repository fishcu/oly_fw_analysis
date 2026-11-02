# OM-3 HSL patch source (experimental)

Adds Hue and Lightness alongside the stock per-colour saturation of the OM-3
COLOR profiles, following the [PEN-F HSL patch](../pen-f/README.md). Built from
official OM-3 firmware 1.1 (internal build 1100) by the shared
[patch builder](../../README.md).

**Status: not tested on a camera.** Evidence is static disassembly and native
execution of the GUI in OM-Emu (no ISP, no normal capture path). The builder
withholds the install file unless `--write-untested-package` is given. A valid
checksum is not evidence that the image is safe to install; see the
[OM-3 update notes](../../../docs/boot/om-3/RECOVERY.md).

## Build

```bash
python3 tools/oly_patch.py patches/hsl/om-3 \
  --stock /path/to/OLY_E_147_1100_0000_0000.BIN --out generated/om3-hsl --decoded
```

The stock file must have SHA-256
`8c133084414533159f587bf46bfb4152714c4074312a47c8d8503e33d605696d`. Outputs:

- `decoded/0100.bin`: patched main component (SHA-256 `2097fee0…6f3f`), e.g.
  for an emulator.
- `install/DCOLYMP/E1479999.BIN` (only with `--write-untested-package`): the
  complete update file, all six components, only main changed
  (SHA-256 `859d32ee…7f3f`).
- `restore-stock/DCOLYMP/E1479999.BIN`: the unmodified stock file.

GNU binutils for `mn10300-elf` are required; 2.43 was used.

## In the camera (as exercised in OM-Emu)

Picture mode COLOR1–4, Color Vivid editor:

| Control | Action |
| --- | --- |
| Delete (trash) | Switch Saturation → Hue → Lightness |
| INFO | Stock: one colour / all colours |
| Sub dial / main dial | Select colour / set −5…+5 |
| OK held | Reset the current axis only |

The title above the wheel shows the axis and a "Switch [trash]" hint; the stock
value label follows the current axis. H/L values persist with the settings and
follow custom-mode recall like saturation.

## Changes

| Range | Purpose |
| --- | --- |
| `615d0b64` (pointer) | Delete action on the Color Profile page: forward 0x9016 to the focused widget when setting 2163 ≠ 1 |
| `615370e8` (pointer) | Colour page container: consume 0x9016 for the 13-child colour editor, cycle axis, refresh children |
| `611d1401` | Value label: substitute the active axis value for settings 916+sector |
| `60bb52f8`, `60bb534c` | Editor read/write of IDs 928–975: H/L to the part-1 alternate cells |
| `61225de4` | Reset: H/L axes reset to zero |
| `61228102` | Record the colour editor parent |
| `60b1d363` | Wheel values: H/L when that axis is active |
| `60518615` | After the COLOR builder: H/L output records for COLOR1–4 (setting 901 = 54/55/56/64) only |
| `61452290` (pointer) | Paint wrapper: axis title and hint |
| `6031e920..6031ef14`, `6031efa0..6031efe0` | Code and 64-byte state in the section-1 loaded tail |

H/L are stored as `0x4831CCVV` in part 1 of the alternate cells for IDs
928–975 (VV: H low nibble, L high nibble, CC = VV xor 0xff; −5…+5), the PEN-F
layout. Invalid words decode as neutral. See the
[editor](../../../docs/color/om-3/EDITOR.md),
[settings](../../../docs/color/om-3/SETTINGS_STORAGE.md) and
[capture](../../../docs/color/om-3/CAPTURE_PARAMETERS.md) references.

## Known limits

- H/L are read from the live settings when the COLOR builder runs, not
  snapshotted at capture. An image still being processed when H/L or the
  picture mode changes may receive the new values; in-camera RAW development
  uses the current H/L.
- Part-1 ownership rests on static mode tables and emulator observations
  (factory defaults, stock edits write part 0 only). Settings reset, assigning
  to a custom mode and settings backup/restore are not exercised; a backup may
  not carry H/L.
- The section-1 tail is the region used by the third-party OM-3 tethering
  patch; the two cannot be combined as they stand.
- The OM-Emu GUI checks cover axis switching, both selection modes, dials,
  reset, COLOR1/COLOR2 separation, power-cycle persistence and the builder
  output for COLOR1 and COLOR4. Nothing has run on an OM-3.
