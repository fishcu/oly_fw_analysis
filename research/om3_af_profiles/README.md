# OM-3 stock AF profile research workspace

This preserves the authored OM-3 1.1 research and emulator probes as of
7 November 2026. It is an incomplete research prototype, not an installable
firmware extension. No physical camera was connected or flashed.

Start with the topic references:

- [Independent AF-button profiles](../../docs/features/om-3/AF_BUTTON_PROFILES.md).
- [Human detection pipeline](../../docs/features/om-3/SUBJECT_DETECTION.md).

The original source layout is retained because the Ghidra scripts inherit from
one another and the original execution manifests pin their exact bytes. Earlier
experiments are retained for provenance; only the current runner's selected
scripts comprise its execution suite. Historical reports in this directory and
`analysis/button-af/FEATURE-SPEC.md` describe different checkpoints. Do not add
their test counts together or interpret a BOUNDARY as a successful feature test.

## Included and excluded material

`scripts/` contains 66 Java Ghidra scripts and the original Python/PowerShell
helpers. Root Python files support the earlier container/decompilation and
Human-detection investigation. `recorded-evidence/` contains compact recorded
outcomes and original manifests. `import-manifest.json` hashes the imported
source, reports and result files.

Vendor firmware, model weights, resources, extracted filesystems, full
decompilation/disassembly, Ghidra databases, tool binaries and bulk execution
logs are deliberately omitted. References to these paths in the historical
reports identify local inputs/generated outputs, not missing release assets.
Original execution manifests retain hashes of omitted traces for provenance;
their presence does not mean those traces are distributed here.

The scripts include short displaced instruction fragments and firmware-specific
constants. They are research source, not a license to redistribute the vendor
image. See the repository's [rights and provenance](../../RIGHTS-AND-PROVENANCE.md).
The decoded modified fixture and encoded outer container are never published.

## Check the imported evidence without firmware

From this directory:

```sh
python run_offline.py --check-recorded
```

This checks file hashes, original full-run source identities and selected
recorded outcomes. It does not execute the firmware or independently reproduce
the recorded emulator results. The later conditional transport probe has a
separate manifest and is not silently counted in the original full run.

## Reproduce native execution

Obtain the exact stock image separately under its applicable terms. The expected
container SHA-256 is
`8c133084414533159f587bf46bfb4152714c4074312a47c8d8503e33d605696d`
(240,517,120 bytes). The displayed version is 1.1; the catalog filename identifies
build 1100. Do not infer every component's internal version from this filename.

Use Ghidra 12.2 PUBLIC, JDK 25, and the MN10300 extension from
[ghidra-mn103-extension](https://github.com/aleph-void/ghidra-mn103-extension/tree/ghidra-rare),
module commit `32d7ce4d79dfd4c16c064e48858b2f087f165c4e`.
The original extension archive SHA-256 was
`d48d3f5068b08d94f71375047cf8c2bb323ebaa40e2375a63135ed4d0095d90b`.
No extension or JDK binaries are included.

```sh
python run_offline.py --prepare-inputs --stock /path/to/OLY_E_147_1100_0000_0000.BIN
```

Preparation validates the input hash, obtains the container parser from pinned
upstream commit `539fcf1fa9eda5fdef8ede4deeab94a4691d94c3` using the local Git
history, and writes the original decoded components into ignored local paths.
If that commit is absent from a shallow checkout, fetch its history first.
Existing differently hashed files are rejected rather than overwritten.

Prepare a dedicated Ghidra project with the decoded main component
`analysis/decoded/00_0100_50000020.decoded.bin`, BinaryLoader base `0x60021020`,
language `mn10300:LE:32:mn10300`. For example, from this directory:

```sh
analyzeHeadless /path/to/projects OM3_main_full -import analysis/decoded/00_0100_50000020.decoded.bin -loader BinaryLoader -loader-baseAddr 0x60021020 -processor mn10300:LE:32:mn10300 -noanalysis
```

The recorded run used the broad analyzed project. Regenerating that larger
analysis is described in `DECOMPILATION.md`; the firmware probes use original
instructions and explicit models, not exported C. Fresh project creation and
different platforms are not claimed equivalent merely because import succeeds.
Close any GUI use of the project before invoking headless execution.

```sh
python run_offline.py --run --ghidra /path/to/ghidra_12.2_PUBLIC --java-home /path/to/jdk --project-dir /path/to/projects --project-name OM3_main_full
```

The portable launcher supplies the project/tool paths explicitly; the unchanged
original PowerShell launchers retain the original workspace layout assumptions.
Expect several minutes of emulation. Generated files remain ignored. Headless
process exit code alone is insufficient: script errors and missing-memory
warnings are checked before evidence verification. A successful runner still
reports **NOT READY TO FLASH**; expected receiver/connection boundaries remain
unresolved. The supplemental command-transport probe stops before submission.

## Remaining work

Successful operational AF reception/acquisition; actual orientation and UI
editing/display; sleep, mode recall, reset and capture lifecycle; concurrent
readers and record lifetime; real settings reload; full boot; updater admission
and intact-camera recovery are not established. Some of these are unfinished
software analysis/modeling, not exclusively hardware-only checks. There is no
SD installation package in this contribution.
