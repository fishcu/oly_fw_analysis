# PEN-F HSL + Live ND + AF Limiter source

This builds the **live-nd-af-20261101** firmware from official PEN-F 3.1 build
3101. It is the HSL [alpha-20261017](../../hsl/pen-f/README.md) firmware with
two more features:

- **Live ND / Multiple Exposure:** Frame Off / 2f / 4f / 8f. 4f and 8f take all
  their frames from one held press in Sequential H. With Auto Gain on, the
  result is a RAW mean, so every frame count gives the same brightness and more
  frames give less noise. 2f still takes one frame per press. The maker-note
  tag `0x101c` records the frame count.
- **AF Limiter:** Custom Menu A row "AF Limiter: Off / 3/4 / 1/2 / 1/4", in
  place of Focus Ring. It keeps only the far part of the contrast-AF scan range.

The firmware still displays version 3.1. Function maps and evidence are in
[Multiple Exposure and Live ND](../../../docs/features/pen-f/MULTIPLE_EXPOSURE.md)
and [AF limiter and custom-menu rows](../../../docs/features/pen-f/AF_LIMITER.md).

## Build

Requirements are the same as for the [HSL source](../../hsl/pen-f/README.md):
Python 3.12 or later, GNU binutils for `mn10300-elf` (2.45 was used), and the
complete stock firmware identified in `patch.json`.

```bash
python3 patches/live-nd-af-limiter/pen-f/build.py \
  --stock /path/to/OLY_E_122_3101_0000_0000.BIN \
  --out generated/pen-f-live-nd-af
```

The builder first runs the HSL builder into `base-hsl/`, which checks the HSL
release hash. It then assembles the helpers in `src/`, checks the HSL bytes
under every range, applies the ranges and re-encodes the main component. The
OSD component is HSL's, unchanged. `--as`, `--ld` and `--objcopy` select the
tools, as for HSL. The output directory must be new.

Outputs:

- `install/DCOLYMP/E1229999.BIN`: main + OSD, 44,433,408 bytes.
- `restore-stock/DCOLYMP/E1229999.BIN`: matching stock main + OSD (the same
  file as the HSL restore).
- `base-hsl/`: the HSL build this one starts from.
- `assembly/`: helper objects and extracted sections.
- `build.json`: input, output and source hashes and tool versions.

The patched BIN SHA-256 is
`6d212c1117a9050601684195c2acd52c3f1bf469b5c22a3532aa334bc3ca7e41`.
The restore SHA-256 is
`e13f9813d01d15441082ed907966aec54356d70ba0f75ae9b6c2b259ff01f26a`.
The builder does not connect to or flash a camera.

## Source organization

| Group | Function |
| --- | --- |
| `live_nd` | Release source and take-done tail (one press), `Bayer_MultiExp` handles 5–8, view-path caps at 4 takes, maker-note frame count |
| `af_limiter` | Narrow POS_NEAR toward POS_FAR by setting 448 at the join of `fcs_sub_iaf_set_lens_pos_info` |

`patch.json` lists 43 ranges (623 bytes, 549 of them different from HSL), each
with its feature, purpose, size and the hashes of the HSL bytes before and the
new bytes after. Seven ranges are assembled helpers; the other 36 are small
data and instruction edits stored as hex. Helpers sit in loaded section tails
that HSL leaves erased, with margins to HSL code; each `layout.ld` lists the
gaps and defines the stock call targets.

## Verification

The built main was run in the MN103 emulator, stock against patched:

- the Frame value stepper, rules engine and menu label lookups;
- the controller with setting 267 = 8 (combine array, take count, freeing
  every handle);
- the take-done handler and `entryTAKE_PICTURE_CONT` for 2f, 4f and 8f
  (8f requests takes 2–8 and ends at 8; 2f is unchanged);
- `compose` through its CALLS entry and through the direct call at
  `0x607bbe14`, and `Bayer_MultiExp` through both entries, for 2, 4 and 8
  frames, with callee-saved registers and SP restored;
- the view-path entries with 8 takes (both pass at most 4);
- the maker-note writer for 2f, 4f and 8f;
- the COMPOSE_RAW fold for N = 2–5 and its per-frame gain for N = 8;
- `fcs_sub_iaf_set_lens_pos_info` for limiter values 0/1/2/3/7, both branches
  and both pulse directions;
- the custom-menu visible-row list, rules, popup kind and page action lookups;
- the section loader, SD client and native updater with the built package.

Those emulator harnesses depend on local decoded images and are not part of
this source. The ISP and the lens are not emulated.

## Camera test scope

One PEN-F body ran this exact package (SHA-256 above) from 1 November 2026,
with the 40-150 mm R and the 45 mm f/1.8:

- Frame 2f / 4f / 8f with Auto Gain, Sequential H: correct frame counts,
  constant brightness, lower noise with more frames, EXIF counts 2 / 4 / 8.
- Single-frame drive does not chain 4f or 8f.
- Handheld frames are not aligned (10–100 px drift).
- AF Limiter: the row opens, sets and applies all four values in C-AF.
- HSL behaves as in alpha-20261017.

Not tested: Sequential L with 8f, the electronic shutter, Overlay with 4f/8f,
Mysets, and persistence of the limiter across power-off. A checksum, emulator
run or one camera's behaviour is not proof that the package is safe on another
camera. Keep the restore file and read the
[recovery limits](../../../docs/boot/pen-f/RECOVERY.md) before installing.

Minimal displaced stock instructions remain at hook boundaries; repository
licenses do not license the supplied vendor firmware.
