# PEN-F electronic aperture-ring support

Adds Panasonic electronic aperture-ring input to **PEN-F 3.1/build3101** in
aperture priority (A) and manual (M). A/auto hands control back to the saved
body setting. The patch uses the lens's advertised capability and reported
aperture range, with no lens whitelist or fixed aperture-value table.

The contributor reports working A/M control, depth of field preview and
combined HSL/aperture operation on camera. Correct wide-open f/1.7 values are
confirmed on the Panasonic Leica 15 mm, 10–25 mm and 25–50 mm. Earlier reports
also found correct displayed values across the range on 12 mm, 42.5 mm and
200 mm lenses. These observations do not quantify iris position or exposure
accuracy and do not establish compatibility with every lens.

## Profiles and exact input

| Profile | Baseline and contents | Size of each update BIN |
| --- | --- | ---: |
| `pen-f` | Official 3.1 main; stock OSD retained | 21,364,736 bytes |
| `pen-f-hsl` | Electronic ring + HSL alpha-20261017 main and HSL OSD | 44,433,408 bytes |

Both require the full official `OLY_E_122_3101_0000_0000.BIN`, SHA-256
`77398610b379f80238117f31a6d5bbf65d608b49ec563666c64d84367e969f2c`.
Obtain it separately using the [firmware inventory](../../provenance/firmware-inventory.json).
No vendor images or prebuilt updates are included here.

Each [profile manifest](pen-f/patch.json) pins the stock container, original
and modified decoded main, every original/compiled section, assembly sources
and encoded install/restore. The [HSL profile](pen-f-hsl/patch.json) also pins
the existing HSL release and OSD. The standalone placement overlaps that HSL
release; choose the combined profile when using HSL. Concatenating packages
does not resolve those overlaps.

## Build

Use Python 3.12 and GNU MN103 binutils. Binutils 2.45 reproduces the pinned
bytes. Put `mn10300-elf-as`, `mn10300-elf-ld` and `mn10300-elf-objcopy` on PATH,
or provide explicit `--as`, `--ld` and `--objcopy` paths. The HSL builder's
local `toolchains/mn103-patch-build` tools are also supported.

```sh
python3 patches/aperture-ring/build.py --model pen-f \
  --stock firmware_files/OLY_E_122_3101_0000_0000.BIN \
  --out generated/aperture-pen-f
python3 patches/aperture-ring/build.py --model pen-f-hsl \
  --stock firmware_files/OLY_E_122_3101_0000_0000.BIN \
  --out generated/aperture-pen-f-hsl
```

Output directories must be new and outside the patch source directory. They
contain the assembled source snapshot, ELF and section files, decoded main,
build report, `SHA256SUMS` and:

| Folder | Contents |
| --- | --- |
| `install/DCOLYMP/E1229999.BIN` | Selected aperture-ring profile |
| `restore-stock/DCOLYMP/E1229999.BIN` | Original main for standalone; original main + OSD for combined |
| `restore-hsl/DCOLYMP/E1229999.BIN` | Combined profile only: exact original HSL alpha-20261017 main + OSD |

Standalone install SHA-256:
`af42e92ab4b9e6df4b13e597526f58217f185b4ffb93fc324e9bacc35d90bbc7`.
Combined install SHA-256:
`81781482738718549e54c97d4e16a606e016abf6381bef98cb7b578f61ec2f47`.

The builder verifies source and stock identity before patching, checks every
section and final hash, re-parses packages and preserves original update
metadata. There is no mismatch-bypass option. Keep other components on the
official 3.1 baseline. The displayed version remains 3.1 and does not identify
the modification. The existing [update/recovery reference](../../docs/boot/pen-f/RECOVERY.md)
describes the limits of checksum acceptance and stock restoration.

## Aperture values and HSL compatibility

The native cache holds live effective Av, official minimum and official maximum.
Selection uses the last two, including the current zoom-dependent minimum.
Using effective Av as a lower limit raises the first f/1.7 input and makes the
stock formatter show f/1.8. Reading the official minimum preserves the stock
wide-open endpoint handling; no display text or f/1.7 special case is inserted.

The HSL profile reclaims only the existing ORF helper group, keeps ring helpers
and publication in section 1, and relocates the ORF helpers into reviewed
section-8 padding. A section-1 guard retains the stock CMIO copy until the
native loaded-section mask marks section 8 ready. All non-ORF HSL edits and
the HSL OSD remain exact. Its builder reproduces the existing HSL release
first and checks that the retained edits remain unchanged.

## Reproduce native checks

```sh
python3 tools/run_checks.py
python3 tools/aperture_ring_probe.py --model pen-f \
  --build generated/aperture-pen-f --out generated/aperture-pen-f/native.json
python3 tools/aperture_ring_probe.py --model pen-f-hsl \
  --build generated/aperture-pen-f-hsl --out generated/aperture-pen-f-hsl/native.json
python3 tools/aperture_ring_hsl_probe.py --build generated/aperture-pen-f-hsl \
  --out generated/aperture-pen-f-hsl/hsl-native.json
```

The native commands need the strict GNU runner described in the
[emulator reference](../../docs/tooling/EMULATOR.md); `--engine` selects an
existing runner. They execute the original getter, cache producer, patched
snapshot and stock aperture formatter on explicit synthetic RAM. Tests cover
independent effective/official values, nonzero zoom rows, signed limits,
A/auto, modes, capability/connection gates, body setting preservation and the
f/1.7/f/1.8 distinction. The HSL probe checks original-versus-relocated CMIO
arithmetic and readiness-guard arguments, stopping before metadata transfer.

These bounded probes do not run a camera scheduler, electrical transport,
exposure solver, flash backend, physical cache/DMA or iris. Half/whole-stop
intermediate labels retain stock step-dependent rounding. Camera observations
are contributor reports, separate from native execution. See the
[feature reference](../../docs/features/APERTURE_RING.md) and
[source/input provenance](SOURCES.json).
