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

## Hardware phase (added 10 November 2026)

[HARDWARE-PHASE-PLAN.md](HARDWARE-PHASE-PLAN.md) sets out staged camera work,
starting with stock-firmware recovery rehearsal.
[HARDWARE-STAGE0-RECORD.md](HARDWARE-STAGE0-RECORD.md) records the stock inputs,
update routes, exit criteria and the 9 November task-context mutex repair
(`task-context-mutex2`, `native-mutex-context1`, `task-context-placement1`).
[HARDWARE-STAGE1-2-LOG.md](HARDWARE-STAGE1-2-LOG.md) is the owner's log template
for stock-only stages 1 and 2. The proposed changed-byte table from
`task-context-placement1` is omitted because it contains stock bytes; its
manifest keeps the hash. No image has been built or flashed.

## Included and excluded material

`scripts/` contains 110 Java Ghidra scripts and the Python/PowerShell
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

This checks imported current-file hashes, archived original full-run source
identities in `recorded-evidence/live-source-snapshot/`, and selected recorded
outcomes. Three current scripts have since been refactored; the historical run
does not establish execution results for those revised scripts. It does not
execute the firmware or independently reproduce the recorded emulator results. The later conditional transport probe has a
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

## Supplemental AF-command and emulator findings

The later investigation is documented in
[AF-GAP-CLOSURE-ASSESSMENT.md](AF-GAP-CLOSURE-ASSESSMENT.md). It supersedes the
earlier transport-only boundary for its separately labelled scenarios; it is
not part of the original complete-run result counts above.

- Stock task 207 and port-2 transport were followed to the SCPU link boundary.
  Silent-peer timeout and full stock-reset scenarios preserve failure paths.
- The reset scenario obtains mode key 3 from stock initialization. The installed
  MN10300 language had an aliased-register carry/overflow defect; the included
  source diff and before/after tests document its correction. A carry-fixed
  reset run passes the numeric loop and sends queue-95 command 0x1d, then waits
  on reply buffer 1032. Backend connection and successful AF remain unproven.
- Queue 95's 93-slot dispatch table, request/reply format and start/end family
  were decoded. The offline decoder can inspect captured bytes:
  `python scripts/decode_om3_queue95.py --request HEX --payload HEX --reply HEX`.
  Payload and reply are optional. This imported decoder adds a fallback to the
  packaged dispatch-map location; original probe manifests retain original
  source hashes, while `import-manifest.json` pins this packaged adaptation.
- `OM3CaptureAfTaskProof.java` runs the stock queue-95 AF-command task (and the
  queue-94 worker) natively when a caller would block on its reply. It also runs
  the stock memory-pool constructor group `0x602153e6` and corrects four harness
  models. Run 6 (`recorded-evidence/capture-aftask-run6/`) completes the capture
  connection in each iteration: the AF-command task serves command 0x1d itself,
  half-press and shutter-release return, and AF-ON press and release wait at
  `0x60dd896d`. No handler sends an AF start command.
- Run 7 (`recorded-evidence/capture-aftask-run7/`) adds observation-only logging
  at the router's state-12 handler. Its results are identical to run 6. The router
  is waiting for requested backend `0x62b71778` to report "started" (type 0x1b),
  and that report never comes. The ninth follow-up in the assessment records the
  event tally and the partial decode of the backend's sub-components. Backend
  activation, AF-ON response and AF acquisition remain unproven.
- Assessment follow-ups 10–22 add the stock-mode connection (`OM3StockMode*`),
  the original button/SCP matrix and AF consumer scheduling, complete ROM OS
  tables, and native AF mode start from labelled stock startup steps
  (`OM3AFStartupConsumerProof`). Their compact outcomes, results, summaries and
  manifests are under `recorded-evidence/<run>/`, and their derived ROM tables
  under `recorded-evidence/review/`. Traces, memory images and disassembly
  excerpts are omitted.
  - In `af-startup-consumer2`, an original AF-ON press reaches LOCK_START, and
    the AF worker reads the AF-ON target profile (owner 2, Subject Detect
    bypassed). It then waits for a reply from an AF-family task that is not yet
    scheduled (message buffers 92/93).
  - No AF acknowledgement, focus result or hardware completion is supplied.
- Later follow-up 22 runs schedule the queue-92 AF task (ROM task 104) and park
  a blocked AF task with its native context until its flag is set
  (`af-startup-consumer4`).
  - **Matrix result:** the original button/SCP matrix passes **28 / 28**.
  - **AF-ON chain:** the first AF-ON press completes the native LOCK_START
    chain (worker, task 104, callback and replies), all produced by stock code.
  - **Engine routing:** `OM3EngineRoutedConsumerProof` (`engine-routed4/5`)
    delivers every edge through the stock GUI engine and the feature's table
    wrappers, again 28 / 28.
  - **Open:** later AF-ON presses are refused while a display-output change
    flag (`0x62b7f7b4`) awaits a display-complete notification that the
    emulation does not produce.

Compact outcomes and manifests are under `recorded-evidence/capture-*` and
`recorded-evidence/review/`. Review subdirectories preserve derived ROM facts,
the queue dispatch map, a mathematical carry reproduction, and language-fix
results. Full listings, original language backups, compiled language binaries
and bulk traces are omitted. References to `analysis/review/` in the original
notes refer to local generated evidence; packaged compact counterparts are in
`recorded-evidence/review/`. The local byte-verification scripts referenced by
those notes are not bundled as standalone firmware-free checks.

The language diff modifies the Apache-2.0 MN10300 extension referenced above;
its license and attribution are preserved beside the diff. Apply it to that
pinned extension and recompile before reproducing carry-fixed supplemental
runs. The old complete-run evidence remains historical evidence of the earlier
toolchain; targeted revalidation of flag-sensitive results remains necessary.
No full firmware run was performed merely to prepare this Git update.

## Remaining work

Successful operational AF reception/acquisition; actual orientation and UI
editing/display; sleep, mode recall, reset and capture lifecycle; concurrent
readers and record lifetime; real settings reload; full boot; updater admission
and intact-camera recovery are not established. Some of these are unfinished
software analysis/modeling, not exclusively hardware-only checks. There is no
SD installation package in this contribution.
