# Reproducing the research

Start with the input-free checks below. For native firmware analysis, supply the
matching camera firmware and build the MN103 emulator. Check input identities
against the provenance catalog.

## Start without proprietary inputs

Use Python 3.12. Install Pillow if you want all resource/atlas modules available:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install Pillow
python3 tools/run_checks.py
```

The default checks use synthetic containers, numeric reference observations and
a simulated Wi-Fi camera. They make no network requests. The
[tool catalog](tools/README.md) identifies the useful entry points and the
[topic index](docs/README.md) explains what their results establish.

## Portable offline subset

The default client tests exercise POSIX storage and locking (`fcntl` and directory
fsync); the production client targets Linux. On Windows, or when only portable
coverage is wanted, explicitly select:

```bash
python3 tools/run_checks.py --portable
python3 -m unittest discover -s tests -p test_run_checks.py
```

`--portable` retains source parsing, tool imports, synthetic container tests and
input-free emulator-performance tests. It selects only `test_transport.py` from
the client suites; those HTTP calls are mocked, not sent over a network. It lists
the omitted client suites: currently `test_client.py` and `test_workflow.py`.
Their storage/locking/durability, simulated-camera state and recipe/workflow
coverage is **not** replaced. Native and loopback checks are also excluded;
combining their options with `--portable` is an error. The default selection and
production locking behavior are unchanged.

Tool-import dependencies, including Pillow, are still required. Missing imports
and selected-test failures remain errors; this option does not hide dependency
problems. Its success message means only the selected partial checks passed.
It neither enables Windows camera-client support nor verifies native firmware.
The option can be exercised on any host; a macOS run or simulated missing `fcntl`
is not evidence of an actual Windows run. Full default checks still need a host
with the client's POSIX facilities (for example Linux/WSL).

## Decode an exact stock input

Native PEN-F probes target the 3.1 **3101 build**, not every file advertised as
version 3.1. Supply the complete stock container at
`firmware_files/OLY_E_122_3101_0000_0000.BIN`:

```bash
python3 tools/oly_container.py firmware_files/OLY_E_122_3101_0000_0000.BIN \
  --expect-sha256 77398610b379f80238117f31a6d5bbf65d608b49ec563666c64d84367e969f2c \
  --code-base 0x60021020 --out analysis/penf_3.1
```

The output directory must be new. The decoder validates component wrappers,
additive checksums and exact decode/encode round trips. It does not create a
flashable patch. The resulting main payload must hash to
`a2eb1d1f1afe47cce148e9aae0a04dfb82547d9de9437d342e012341140913f4`.
Its CPU mapping begins at `0x60021020`; container flash addresses are different.

`om_firmware_catalog.py` can query the vendor catalog or read saved response XML.
The installed-version argument reports an existing version; it does not select
an arbitrary historical release. A returned file still needs identity checking:

```bash
python3 tools/om_firmware_catalog.py --model-id 1220 --model-name PEN-F \
  --out generated/catalog --download
```

## Execute bounded native probes

Build the [pinned GNU emulator](docs/tooling/EMULATOR.md), then:

```bash
python3 tools/run_checks.py --native
python3 tools/penf_creative_jobs_probe.py --matrix --out generated/creative-jobs
python3 tools/penf_emulator.py --trace 100 boot-prefix
```

The last command deliberately stops at the first unmodeled controller read and
exits nonzero. The processing-job matrix executes CPU bookkeeping with modeled
allocation/service responses; it does not process image pixels or emulate the
ISP. A passing probe proves its scoped assertions under the named assumptions.

## Disassembly and additional inputs

The [IDA 4.9/MN103 guide](docs/tooling/ida/README.md) provides an optional second
disassembler and a Wine/IDC exporter. GNU tools remain sufficient for the
probes and patch build.

Use an MN103-capable GNU objdump. `penf_disasm.py` takes `--objdump`, `--image`,
`--start` and `--stop`; choose reviewed instruction boundaries. The
[disassembly inventory](provenance/disassembly-windows.json) preserves original
address windows and known image hashes without redistributing listings.
`tools/regenerate_disassembly.py --help` describes regeneration of one window.
When the inventory has no unique image identity it reports that limitation;
an arbitrary byte match is not established code reachability.

Cross-model probes, historical hack comparisons and checkpoint-based editor
fixtures require extra inputs. [tools/inputs.json](tools/inputs.json) identifies
principal dependencies; [tools/README.md](tools/README.md) distinguishes the
self-contained native jobs from these archival fixtures. Rebuilt checkpoints
need their own qualification when source hashes or hardware models change.

Generated disassembly, RAM dumps, bitmaps and decoded firmware remain local.
They may contain protected code or private information even when wrapped in
JSON. The repository's ignore rules are convenience filters, not a licensing
or privacy review. No firmware image is installed by these reproduction steps.

## Build the HSL firmware

The [PEN-F HSL source](patches/hsl/pen-f/README.md) builds the released main + OSD
package from stock firmware and GNU binutils alone. It verifies exact equality
with the release, including the Value bitmap. Earlier patched firmware and
captured RAM checkpoints are not build dependencies.

Workspace internals are unnecessary for decoding, disassembly, the core native
probes or this build. Comparing actual rendered pixels is a separate task: the
MN103 emulator models CPU control flow, not the ISP, so it cannot reproduce or
validate JPEG appearance on its own.
