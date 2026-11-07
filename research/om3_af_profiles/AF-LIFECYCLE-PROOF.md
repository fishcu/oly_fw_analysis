# AF button profiles: all SCP classes, lifecycle and stock target conversion

OM-3 1.1, 31 October 2026. **The extension follows any SCP Subject Detect choice, including Off. Human is one example, not a restriction.** Half-press uses its stock target profile and the SCP choice; AF-ON uses its own stock target profile with stock-equivalent detection Off behavior. The current S-AF/C-AF setting is shared.

This follow-up adds 88 passing bounded native-instruction fixtures. It advances command construction, lifecycle routing and stock target conversion. It does not yet prove the complete two-button extension on a camera.

Later milestone: [nested stop/reset and active-target update investigation](AF-INTEGRATION-GAPS.md) executes several formerly modeled callees and identifies the selection-retention branch. This report retains the scope and counts of its earlier milestone.

## Coverage of every SCP class

The firmware enum recovered earlier is Off=0, Motor Sports=1, Airplane=2, Train=3, Bird=4, Animal=5, Human=6.

The native start wrapper at `0x608401af` accepts all six nonzero classes. For each one it constructs a record with command kind 1 at byte zero and the selected class at byte 12, submits the record through `0x60841102`, then calls a completion-wait service with mask `0x8`. The tests capture these original command-field writes; submission and waits are modeled.

Off takes the invalid-class branch and returns status 4 without submitting a start command. This is an important implementation constraint: resuming half-press with SCP Off must leave detection disabled, rather than issuing a class-zero start command.

All 49 old/new combinations over values 0..6 were tested through the active class-change gate at `0x603cee28`. Nonzero-to-different-nonzero transitions request a class change. Transitions involving zero and unchanged classes do not. This verifies the gate across the complete SCP enum, not the downstream class-change implementation or model loading.

Sources: [command wrappers](analysis/button-af/lifecycle/detection-command-wrappers.asm), [prior effective-mode gate](analysis/button-af/detect-off/subject-mode-apply.asm), [native results](analysis/button-af/lifecycle/lifecycle-results.txt).

## The stock stop operation and worker routing

The stop wrapper at `0x608402ad` constructs command kind 2, with a separate zero/one option at byte 12, then calls the wait service with mask `0x10`. That option is not a detector class. Both values were tested.

The stock caller at `0x603ce960` first checks bit zero of its input halfword at `+4`. When set, it calls a guard service, clears active byte `0x62a6a523`, chooses the stop option from bytes `0x62a6a0f0` and `0x62a6a0ef`, calls the stop wrapper, then releases the guard. Eight fixtures test the eligibility flag and all four zero/one auxiliary combinations. With eligibility clear, it performs none of those operations and leaves the active byte alone. Therefore this routine cannot be treated as an unconditional stop API without supplying the correct stock context.

The native command switch at `0x60841af4` routes:

- Kind 1 to start worker `0x60841bd1`.
- Kind 2 to stop worker `0x60841ce6`.
- Kind 3 to class-change worker `0x60841e24`.

Three fixtures verify that switch and its argument pointer. They begin after queue reception; queue scheduling and delivery are not tested.

Six further fixtures execute the start worker for each nonzero SCP class from worker state zero. Its instructions call initialization, set worker state `0xa33a1d10` to one, store the requested class at `0xa33a1d14`, call a reset helper, then call completion-signal services with masks 8 and 2. Initialization, reset and signaling implementations are modeled.

Two stop-worker fixtures begin in worker state one. They verify a call to `0x60842965`, a native state clear to zero, calls to cleanup/reset routines `0x6084e7b8` and `0x608714e9`, then the signal service with mask 16. The stop-related helper checks another execution-state byte in its static C and can call into the detector device wrapper. Its implementation is not executed here, so these fixtures prove call order, not that inference has drained or every stale result is gone.

This connects command kinds and completion masks to concrete worker handlers. It is stronger than merely finding a mode setter. The wrapper, stock stop caller, switch and worker fixtures remain separate tests; the complete asynchronous lifecycle has not been executed as one sequence.

Sources: [stock stop policy](analysis/button-af/lifecycle/stock-detection-stop.asm), [worker switch](analysis/button-af/lifecycle/detection-command-dispatch.asm), [start worker](analysis/human-detection/assembly/621-subject_detect_start.asm), [stop worker](analysis/human-detection/assembly/622-subject_detect_end.asm).

## Stock target-type conversion recovered

The earlier analysis correctly distinguished UI target-type key `0x99a1` from internal area key `0x84d1`. This follow-up finds a concrete stock conversion routine at `0x609b3ecd`. Its jump table at `0x60a7da08` handles enum inputs 0 through 10.

Eleven native fixtures run the original switch and four-byte output writes, preserving guard bytes around the output. Observed descriptor kinds are:

- Input 0 produces kind 2.
- Inputs 1 and 4 produce kind 0.
- Inputs 2, 3, 5 and 10 produce kind 3.
- Inputs 6 through 9 produce kind 7 and read custom dimensions from key `0x1dd1` plus central-priority values from `0x1df1`.

The adjacent caller reads several entries of target-type key `0x99a1` and invokes this converter for multiple descriptors. That is a stock mechanism worth reusing for profile construction. The fixture dimension and priority values are supplied by a modeled accessor; they are not measured stock preset sizes.

The converter's four-byte descriptor is not the previously examined ten-byte active target record. No direct copy between those formats is established. These findings do not yet assign camera-visible Single/Small/All names to every enum or prove complete profile activation, orientation handling or display updates.

Sources: [stock type reader/caller](analysis/button-af/lifecycle/stock-target-type-controls.asm), [conversion instructions](analysis/button-af/lifecycle/stock-target-type-conversion.asm).

## Updated implementation proof boundary

The firmware provides class-independent detection commands and a stock target conversion path. The desired behavior has no identified Human-specific dependency.

A candidate ownership transition must coordinate the following, with stock eligibility and synchronization still to be recovered completely:

1. Retain both stock target profiles and the current SCP choice.
2. On AF-ON ownership, apply its target profile and stock-equivalent detection Off behavior, including pending work and cached-result handling.
3. On return to half-press, apply its profile and restore the current SCP choice. For Off, do not start a detector. For classes 1..6, use the correct stock lifecycle rather than only overwriting a class byte.
4. Keep stock configuration refreshes, active geometry, selection snapshots and display consistent through the transition.

This is a proposed integration sequence, not a recovered existing per-button controller. AF-ON precedence while both buttons are held remains the proposed interaction policy. The shooting/request/AF-worker ownership bridge, asynchronous completion and failure handling, full result invalidation, target activation, C-AF/burst overlap, ABI, installation and recovery remain unresolved. No camera was connected, patched or flashed.

## Reproduction and validation

[OM3LifecycleContracts.java](scripts/OM3LifecycleContracts.java) passes 88 fixtures: seven start-wrapper cases, two stop-wrapper cases, eight stock-stop policy cases, 49 class-transition cases, eleven target conversions, three worker-switch cases, six start-worker cases and two stop-worker cases. They are bounded original instruction tests with explicit models, not 88 end-to-end camera tests. Earlier suites were not rerun for this follow-up.

Use the same read-only Ghidra project and bundled JDK as the [previous investigation](AF-DETECT-OFF-PROOF.md), with `-postScript OM3LifecycleContracts.java` and the absolute `analysis/button-af/lifecycle` output directory. [Results](analysis/button-af/lifecycle/lifecycle-results.txt), [scope](analysis/button-af/lifecycle/lifecycle-scope.txt), [final log](analysis/button-af/lifecycle/verified-run.log), [assembly export ranges](analysis/button-af/lifecycle/windows.tsv) and [hash manifest](analysis/button-af/lifecycle/validation.json) retain the evidence.
