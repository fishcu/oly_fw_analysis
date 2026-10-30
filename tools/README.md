# Firmware research tools

These tools inspect firmware files and execute selected MN103 routines offline.
The Wi-Fi client is separate: it deliberately sends commands to a connected
camera. No tool here is a general firmware installer.

Start with [reproduction](../REPRODUCING.md) and the
[research topics](../docs/README.md). Run commands from the repository root.
Python 3.12 and Pillow are the tested host setup. The container parser and Wi-Fi
client use the standard library; Pillow is needed by resource and atlas tools.

```bash
python3 tools/run_checks.py
python3 tools/oly_container.py /path/to/owned-firmware.BIN
python3 tools/om_firmware_catalog.py --help
```

`run_checks.py` parses every retained Python file, imports all tool modules, and
runs the container, serialization/cache, and simulated-client tests. It needs
no firmware, network, or camera. Add `--native` after preparing the pinned
firmware and emulator. `--loopback` separately enables local HTTP tests.

## Entry points

| Area | Tools | Purpose / inputs |
| --- | --- | --- |
| Container | [oly_container.py](oly_container.py) | Decode/re-encode OE components, validate wrappers/checksums, export a new decoded directory. Any supported container supplied explicitly. |
| Catalog | [om_firmware_catalog.py](om_firmware_catalog.py) | Read the public catalog or saved XML; optional stock download. This makes network requests only when requested by its CLI. |
| Disassembly | [penf_disasm.py](penf_disasm.py), [penf_landmarks.py](penf_landmarks.py), [regenerate_disassembly.py](regenerate_disassembly.py) | Pinned PEN-F addresses, candidate references, bounded listings, and regenerated evidence windows. Requires your decoded image and MN103 objdump. |
| IDA | [ida/prepare.py](ida/prepare.py), [ida/wine.py](ida/wine.py) | Optional bounded IDC export and isolated Linux automation. See the [setup guide](../docs/tooling/ida/README.md); requires a separately installed IDA/MN103 module. |
| HSL source | [PEN-F builder](../patches/hsl/pen-f/build.py) | Reproduce the released main + OSD BIN from stock and feature-organized assembly. See [build instructions](../patches/hsl/pen-f/README.md). |
| Aperture ring | [PEN-F builder](../patches/aperture-ring/build.py), [native probe](aperture_ring_probe.py), [HSL compatibility probe](aperture_ring_hsl_probe.py) | Reproduce the electronic-ring patch from exact PEN-F 3.1 stock, alone or with HSL; check lens bounds, native aperture text and preserved HSL helpers. |
| Image layout | [penf_firmware_atlas.py](penf_firmware_atlas.py), [penf_section3_layout_probe.py](penf_section3_layout_probe.py), [penf_code_space_load_probe.py](penf_code_space_load_probe.py) | Components, section relocation and code-space candidates. Cross-build checks also need older stock and the listed support audits. |
| Emulator | [build_mn103_emulator.py](build_mn103_emulator.py), [prepare_mn103_sim.py](prepare_mn103_sim.py), [penf_emulator.py](penf_emulator.py) | Pinned GNU core, strict access checks, mapped regions and isolated native calls. See [contracts and limits](../docs/tooling/EMULATOR.md). |
| Connected boot | [penf_boot_sd_mount.py](penf_boot_sd_mount.py), [penf_emulator_benchmark.py](penf_emulator_benchmark.py), [penf_replay_compare.py](penf_replay_compare.py) | Cooperative startup model, native allocation lifetimes and SD mount transport; replay timing and exact comparison. Model stops remain part of the result. |
| Updater | [penf_update_probe.py](penf_update_probe.py), [penf_sd_path_probe.py](penf_sd_path_probe.py), [penf_flash_guard_probe.py](penf_flash_guard_probe.py), [penf_repack_preflight.py](penf_repack_preflight.py) | Isolated update/parser/write-boundary experiments. Hardware writes are trapped or modeled. These do not establish the power-on activation path or recovery. |
| Processing jobs | [penf_creative_jobs_probe.py](penf_creative_jobs_probe.py), [penf_sharpening_probe.py](penf_sharpening_probe.py) | COLOR/MONO job lists, request formats, allocation bookkeeping, configuration controls and sharpening coefficients. Firmware + engine are enough for the job matrix. |
| Editor/state | [penf_color_state_probe.py](penf_color_state_probe.py), [penf_color_text_probe.py](penf_color_text_probe.py), [penf_profile_context_probe.py](penf_profile_context_probe.py) | Native editor state, text rendering contracts and profile ownership. Some state fixtures require the original pinned boot checkpoint; see below. |
| Capture | [penf_processing_lifecycle_probe.py](penf_processing_lifecycle_probe.py), [penf_capture_readiness_probe.py](penf_capture_readiness_probe.py) | Request ownership, notifications, release/return boundaries and capture readiness. These are scoped native fixtures, not complete ISP simulation. |
| Settings | [penf_settings_backup_probe.py](penf_settings_backup_probe.py) | Native backup resource, keys and save/restore handlers. Needs complete stock container and a pinned startup checkpoint. |
| ORF | [penf_orf_native_cmio.py](penf_orf_native_cmio.py) | Apply native CMIO H/S/L encoding to an explicit copied PEN-F ORF. Checks tuning block, metadata spans and untouched RAW strips. No Workspace DLL needed. |
| Resources | [penf_osd_symbols.py](penf_osd_symbols.py), [penf_osd_bitmaps.py](penf_osd_bitmaps.py) | Font/symbol tables and bounded format-3 bitmap decoding from your OSD component. Generated previews are palette-index views, not exact screen colors. |
| Wi-Fi internals | [penf_wifi_mcon_probe.py](penf_wifi_mcon_probe.py), [penf_wifi_commit_probe.py](penf_wifi_commit_probe.py), [penf_wifi_mcon_restart_probe.py](penf_wifi_mcon_restart_probe.py) | Offline native command/settings paths, including the distinction between raw stored-record writes and application setters. |
| Cross-model COLOR | [compare_color_generations.py](compare_color_generations.py), [compare_color_profile_defaults.py](compare_color_profile_defaults.py) | Compare pinned PEN-F/E-P7/OM-3 tables, gains, writers and defaults. Own images are required; no downloaded catalog logs are needed. |
| Existing hacks | [historical_hack_audit.py](historical_hack_audit.py), [om3_code_space_audit.py](om3_code_space_audit.py), [em1ii_boot_audit.py](em1ii_boot_audit.py) | Exact-build historical diff, padding/relocation and startup comparisons. Requires separately obtained stock/hacked images and, for OM-3, its third-party patch description. |
| Burst buffering | [om5_image_pool_probe.py](om5_image_pool_probe.py) | Follow the native OM-5/E-M1 II/E-M1 III pool configuration and rate consumers. Requires the images identified by the source-pins input. |
| External flash | [compare_external_flash.py](compare_external_flash.py), [ep7_flash_gpio_probe.py](ep7_flash_gpio_probe.py) | Cross-model external-flash capability/GPIO differences. Synthetic replies do not establish which electrical hardware is present. |

The remaining modules are the import closure of these entry points: shared
native-call fixtures, state models, parsers and supporting analyses. Their
names and address constants remain stable to keep evidence and imports useful.
[manifest.json](manifest.json) records this closure and original source hashes.

## Input contracts

The reusable parser accepts a file argument. Most native probes instead pin a
particular firmware SHA-256, CPU mapping and conventional workspace path. An
address match or the same displayed version does not make another build valid.
See [inputs.json](inputs.json) for the principal files and preparation notes.

Several advanced editor/backup probes retain checkpoint-dependent fixtures.
Their original `state.json.gz` files contain firmware/RAM bytes and are not
included. A newly generated checkpoint has new source hashes and may not satisfy
an old exact checkpoint seal; review and requalify that fixture rather than
removing the check. These sources preserve the method and boundaries, but are
not all one-command reproductions from an empty checkout.

Cross-model/historical scripts also require optional images, small support
audits or an external patch manifest. Paths are explicit in their source and
in the input inventory. Public evidence summaries with omitted byte dumps are
not substitutes for raw checkpoint inputs.

For new analysis, prefer `penf_probe.ProbeState` and an explicit synthetic
caller. Keep each modeled service boundary visible, stop on unknown accesses,
and record the exact image/engine/source hashes in the result. Put generated
outputs under `generated/`; outputs may contain firmware bytes or private image
metadata and are not automatically suitable for sharing.
