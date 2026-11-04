# MN103 emulator and native-call harness

The harness executes original MN103 instructions from an exact firmware image.
It uses GNU's instruction engine with explicit mapped memory, stop addresses
and modeled hardware/service boundaries. It is useful for checking dataflow,
calling conventions and parameter ownership; it is not a complete TruePic or
camera emulator.

For a complementary system model, see cmdada's
[E-M10 I emulator and plugin work](e-m10/PLUGINS.md). It reaches a rendered GUI
with modeled peripherals; its published revision also begins at main, not reset.

## Build

Python 3.12, a C/C++ build environment, GNU make and the GNU simulator's host
build dependencies are required. IDA and Wine are not needed. The builder
performs no downloads and installs nothing outside `toolchains/`.

Obtain the [pinned upstream archive](https://gnu.googlesource.com/binutils-gdb/+archive/87ffb882e0f4d73401a0746177ffabb8e8bbe4ac.tar.gz).
Required SHA-256:
`a5e7cd02f844bb2873c25e0ac8e9a5b50a72c3e8e6570a6b7821d2e4c21178ad`.
Then run from the repository root:

```bash
python3 tools/build_mn103_emulator.py --archive /path/to/binutils-gdb-87ffb882.tar.gz
```

The first run verifies and extracts the archive. The preparation tool saves
verified pristine MN103 sources inside the extracted tree and applies the
[reproducible patch](../../tools/mn103_strict.patch). Repeated preparation accepts
only the pinned original or known patched content. Subsequent builds may omit
`--archive`. The executable is `toolchains/mn103-gnu-build/penf-mn103`; the build
manifest records configuration and source/binary hashes.

GNU sources retain their upstream notices. The native wrapper
[mn103_runner.c](../../tools/mn103_runner.c) is GPL-3.0-or-later. Preserve the
corresponding source and license obligations if distributing a built engine.

## Input and execution contract

Follow [REPRODUCING](../../REPRODUCING.md) to decode the pinned PEN-F 3101 main
payload. `penf_emulator.firmware()` rejects any other hash. Individual regions
have exact extents, initial bytes, read/write/execute permissions and optional
coherent aliases. There is no implicit board RAM or default MMIO response.

`Region` and `execute` provide the basic interface;
[ProbeState](../../tools/penf_probe.py) adds native calls, bounded stack/RAM,
register state and reviewed diagnostic hooks. Each experiment starts a fresh
native process. A synthetic caller executes the real call/return convention;
reaching its declared return address means that scoped call completed.

Unknown instructions, unmapped accesses, permission violations, traps/syscalls
and instruction limits stop execution. A host timeout adds a second bound.
Results retain final and pre-instruction registers, fault address/access/size,
bounded traces, captured memory and dependency hashes. A fault does not undo
side effects from earlier instructions. Reading logically uninitialized bytes
inside an explicitly mapped region is not detected automatically.

Example commands:

```bash
python3 tools/penf_emulator.py checksum --hex 01000000ffffffff02000000
python3 tools/penf_emulator.py match E1229999BIN
python3 tools/penf_emulator.py color --saturation=7,0,0,0,0,0,0,0,0,0,0,0
python3 tools/penf_emulator.py --trace 100 boot-prefix
python3 tools/run_checks.py --native
```

The checksum example returns `d0=2`; a successful filename match returns
`d0=0`. `boot-prefix` stops intentionally on a four-byte controller read at
`0x98e00060`, from instruction `0x600210ef`. This starts at the downloaded main
entry `0x60021020`, not hardware reset.

The `color --override RECORD:FIELD:VALUE` interface changes native table values
in emulator RAM only. It uses native record order and coefficients, not GUI
slider values. A successful call is indicated by its declared return boundary,
not the final scratch value in `d0`.

## Connected startup and focused probes

The `penf_boot_*` modules compose a cooperative three-core startup model with
private internal memory and shared global RAM. Section copies, allocation,
RTOS bookkeeping and selected callbacks execute natively. Reviewed controller,
DMA, storage, peer and interrupt responses are explicit models. Interrupts are
delivered at admitted boundaries; physical scheduling and timing are not
reconstructed. `penf_boot_sd_mount.py` is the most advanced retained connected
SD-transport driver; `--out` writes a new trace/checkpoint directory.

Other probes begin at selected functions with deliberately bounded synthetic
state. They are not continuations of the complete boot path. The creative-job
matrix, for example, models dimensions, buffer allocation, service replies and
request acceptance while executing native list selection and request building.
This establishes request structure and CPU ordering, not ISP pixel order.

Use `penf_emulator_benchmark.py` to time a driver and
`penf_replay_compare.py` to compare generated traces/checkpoints. The comparator
allows only explicitly accounted source-hash changes; other differences fail.
Legacy checkpoint-dependent fixtures remain exact-input analyses and may need
requalification after changing the model or source. Missing private checkpoints
are not replaced by sanitized public JSON summaries.

## Fidelity limits

The largest known CPU-model gap is **data alignment**: GNU word/half-word
helpers accept unaligned loads that the supplied MN103 documentation requires
to be naturally aligned. An incorrectly aligned text-style structure passed
offline execution but caused a camera restart; correcting the structure fixed
it. General data-alignment enforcement is still absent. Check alignment and
calling conventions independently, especially for data passed to stock code.

The engine also uses GNU's interpretation of instruction extensions. Three
MAC context-transfer instructions were added for observed native context
operations; undefined flag behavior is modeled deterministically, not measured
on silicon. Strict access checks do not imply complete ISA fidelity.

No NAND physics, ECC, cache timing, real interrupt races, sensor behavior or ISP
pixel pipeline is reproduced. Modeled successful hardware responses can hide
real failures. Pre-main boot code and physical OK+power updater activation are
not established by this model. Passing tests or stopping at an RTOS wait is not
a proof of camera bootability, recoverability or hardware safety.
