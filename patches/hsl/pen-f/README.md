# PEN-F HSL patch source

This builds the **alpha-20261017** firmware from official PEN-F 3.1 build 3101.
The result is byte-for-byte identical to that released BIN: H/S/L for COLOR1–3,
−7…+7 editing, persistence, custom-bank recall, in-camera RAW development, native
ORF metadata, settings backup/restore, Wi-Fi settings and the “Value” graphic.

The firmware still displays version 3.1. This source does not add recording-limit,
grain or vignette modifications.

## Build

Requirements: Python 3.12, GNU binutils for `mn10300-elf`, and the complete stock
firmware identified in `patch.json`. GNU binutils 2.45 was used for verification.
No Workspace installation, DLL, photograph, settings file or earlier hacked BIN
is required.

```bash
python3 patches/hsl/pen-f/build.py \
  --stock /path/to/OLY_E_122_3101_0000_0000.BIN \
  --out generated/pen-f-hsl
```

The builder searches for `mn10300-elf-as`, `mn10300-elf-ld` and
`mn10300-elf-objcopy` on PATH. Supply `--as`, `--ld` and `--objcopy` for another
location. The local `toolchains/mn103-patch-build/` layout is also recognized.
The output directory must be new.

For a local cross-binutils build, obtain [GNU binutils 2.45
source](https://ftp.gnu.org/gnu/binutils/binutils-2.45.tar.xz), create a separate
build directory, and run the following there:

```bash
/path/to/binutils-2.45/configure --target=mn10300-elf \
  --disable-nls --disable-werror --disable-gdb --disable-sim \
  --disable-gprof --disable-gold --disable-libctf \
  --with-system-zlib --disable-shared
make -j4 all-gas all-ld all-binutils MAKEINFO=true
```

Pass `gas/as-new`, `ld/ld-new` and `binutils/objcopy` from that build to the
Python builder. The cross compiler emits MN103 instructions; the host's normal
assembler cannot substitute for it.

Outputs:

- `install/DCOLYMP/E1229999.BIN`: main + OSD, 44,433,408 bytes.
- `restore-stock/DCOLYMP/E1229999.BIN`: matching stock main + OSD.
- `assembly/`: compiled feature objects and extracted sections.
- `build.json`: input, output and source hashes and tool versions.

The patched BIN SHA-256 is
`4f9a36e6742728ded3d9b443915355f1d1eea0371e1da673f322de970994f717`.
The restore SHA-256 is
`e13f9813d01d15441082ed907966aec54356d70ba0f75ae9b6c2b259ff01f26a`.
Installation instructions and physical test scope belong to the
[corresponding release](https://github.com/fishcu/oly_fw_analysis/releases/tag/alpha-20261017).
The builder does not connect to or flash a camera.

## Source organization

| Group | Function |
| --- | --- |
| `image_parameters` | Apply image-owned H/L after the stock COLOR builder; preserve its registers, return path and saturation result |
| `editor_storage` | H/S/L selection, wheel/text display, saved cells, committed publication and capture/compact/recording snapshots |
| `raw_development` | Supply the selected profile to the in-camera RAW editor's image owner |
| `orf_metadata` | Store the captured H/L effect in existing CMIO fields |
| `settings_backup` | Export/import one validated extension record per settings bank |
| `extended_range` | Fifteen-position saturation encoding, number display and backup enum conversion |
| `wifi` | Marked remote reads/writes through the existing application setter path |

`patch.json` records section placement, the small instruction/data edits and
expected hashes in the shared [`oly-patch/1` format](../../README.md); `build.py`
runs the shared builder, [`tools/oly_patch.py`](../../../tools/oly_patch.py), on
this directory. `python3 tools/oly_patch.py patches/hsl/pen-f --stock … --out …`
is equivalent, and `--decoded` also writes the patched decoded components. Source groups describe functions, not independently switchable
features: they share state and entry points. `value-pixels.txt` freezes the
regular-font artwork as 52×26 palette indices, avoiding font-version differences
at build time. The format-3 encoder reuses the original four-byte slot header.

## Verification and modification

Every stock range is checked before modification. Every assembled span must
match its recorded size and hash; ranges cannot overlap. The builder checks the
complete decoded main and OSD, rebuilds checksums, parses its output again and
requires the final release hash. It preserves component headers, lengths and
version fields. The included payload changes are 5,145 main bytes and 725 OSD
bytes, plus four checksum bytes in each component.

The final assembly has been consolidated without changing any output bytes.
This is a reproducible source build of tested firmware, not new qualification
of arbitrary modifications. Editing a source file should fail the reference
checks. A new patch requires reviewed placements, ABI/state tests, updated
expected hashes and its own camera qualification. Do not remove the checks just
to make a different build pass.

Use the [editor/capture map](../../../docs/color/pen-f/EDIT_AND_CAPTURE_MAP.md),
[structure reference](../../../docs/color/pen-f/STRUCTURES.md) and
[recovery limits](../../../docs/boot/pen-f/RECOVERY.md) alongside the source.
[SOURCES.json](SOURCES.json) identifies the original assembly and release evidence.
The Value lettering was derived from DejaVu Sans Condensed; its
[font notice](../../../LICENSES/DejaVu.txt) is retained. Minimal displaced stock
instructions remain at hook boundaries; repository licenses do not license the
supplied vendor firmware.
