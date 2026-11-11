> Later audit: [PREHARDWARE-AF-AUDIT.md](PREHARDWARE-AF-AUDIT.md) covers all seven follow-up areas, reproduces two prototype defects and tests the revised mechanism. This page retains the original 66-check baseline scope.

# OM-3 1.1: integrated offline AF profile proof

31 October 2026. This replaces the earlier fragment-only assessment for the paths tested here.

**A native MN10300 prototype now switches two retained target records, applies effective Subject Detect Off for AF-ON, restores the latest SCP selection, and runs the original detection lifecycle and target/snapshot code in one emulator state. The consolidated suite passes 66 checks, including all 224 finite button-state/event combinations across SCP choices and S-AF/C-AF settings. This establishes a working software mechanism under stated fixtures; it does not establish a complete, installable camera extension or exhaust every question that could be investigated offline.**

The requirements remain: stock target choices for both buttons; half-press follows the current SCP Subject Detect selection, including Off and all six classes; AF-ON bypasses Subject Detect; S-AF/C-AF remains shared. AF-ON precedence while both buttons are held is the proposed interaction policy.

## What changed materially

Earlier tests manually supplied return-state postconditions and replaced several internal calls. The new runner executes actual MN10300 calls, stack saves, returns, hardware loops, queue copies, geometry calculations and selection-reset helpers. A deterministic kernel model supplies locks, scheduling, events and imported memset. Its limits are explicit below.

The new controller is **548 bytes of native research code**, assembled by the harness and executed from temporary emulator RAM. It is not a host-language button-state simulation. Three proposed hooks also execute as native instructions: target-accessor redirection, effective-mode guarding, and wrappers for four shooting-table callbacks. Changes to the Ghidra program are temporary memory mapping only; headless opens the project read-only and explicitly discards changes. Emulator code writes do not alter the original binary or saved project.

## Integrated transaction

The controller receives the recovered event IDs, updates held-button state, selects an owner and reads SCP key `0x1e71[0]` through the modeled settings service. The controller itself executes natively.

On a changed owner or effective class, it checks the stock target-update permission/state gates. It then runs the stock synchronous stop wrapper if detection is running and verifies stopped state before proceeding. It sets effective detection Off, selects the retained target record, calls the native target update and 50-byte snapshot exporter, sets the desired effective class, and runs the stock synchronous start wrapper for a nonzero class. It verifies worker state/class before recording success. Off skips start.

AF-ON chooses class zero. Half-press and idle restoration use the latest SCP class. Changing SCP while AF-ON is held therefore remains bypassed, and releasing AF-ON restores the newly selected class rather than a remembered Human-only value.

The native mode guard forces calls to the stock effective-mode setter to zero while AF-ON is held. This prevents a subsequent stock configuration refresh through that setter from undoing the bypass. An exact-address operand scan found the setter's store and an initialization store of zero at `0x6070120a`; it did not identify another direct nonzero store. That scan is not proof against indirect or bulk writes.

## Original firmware paths now connected

Target path:

- Stock refresh/accessor `0x609b3c79` / `0x609b3bb2` produces a ten-byte record from supplied setting values.
- Proposed native accessor hook supplies one retained record to the unchanged stock copy routine.
- `0x609029f1` runs the actual copy `0x60903e55`, geometry calculation `0x60903e88` and finalizer `0x6090419d`.
- Native grid builder `0x609dc311` and complete exporter `0x608ff478` produce the current 50-byte subject-search snapshot.
- After each successful button event, the harness checks the entire ten-byte active cache, the snapshot's target-derived rectangle and the actual detection decision `0x60703dde` under an eligible-frame fixture. Effective Off rejects that detection request; all six selected classes pass the examined eligible decision.

Lifecycle path:

- Original wrappers `0x608401af` and `0x608402ad` construct start and stop commands and reach their waits.
- Original submit `0x60841102` requests callback `0x608418fe`.
- The scheduler model delivers that actual callback, which initializes the ready queue, runs native enqueue `0x6084dc38` and signals the worker event.
- Actual worker loop `0x60841a6b`, queue availability/pop/consume routines and native switch dispatch run the real start and stop handlers.
- The start path establishes reset eligibility itself. The test no longer needs to assert that eligibility as a substitute for the preceding native start.
- In-flight stop executes `0x60842965`, the device wrapper/callback and actual device-stop register instructions, then all stock buffer and selection reset helpers. The device dispatcher, delay and critical-section services are models; MMIO is emulator memory with a supplied completion value.
- All eleven previously identified seeded result-buffer ranges clear before the tested stop returns. Stop option zero avoids the coordinate-retention behavior found in earlier tests.

This resolves the earlier missing connection between serialized wrappers, callback delivery, the native FIFO and worker dispatch **under the deterministic scheduler contract**. It does not prove real kernel preemption, interrupt ordering, device quiescence or arbitrary concurrent producers. The separate deferred replacement slot is still not a FIFO; the prototype avoids immediately submitting stop and restart together.

## Button routing and ABI evidence

Firmware tables identify these records:

- `0x6131bd50`: event `0x01000002`, half-press, handler `0x610b9197`.
- `0x6131bd60`: event `0x01000003`, half-release, handler `0x610b96f0`.
- `0x6131c290`: event `0x01050007`, AF-ON press, handler `0x610b962a`.
- `0x6131c2a0`: event `0x01050008`, AF-ON release, handler `0x610b9653`.

These are concrete shooting-table entries, not evidence that one table covers every UI state. Named first-release strings separately support the half-press event IDs. The previously tempting caller `0x610b953f` belongs to event `0x01060012`; it must not be presented as the half-press entry.

The proposed native table wrappers execute the profile transaction, restore D0–D3, A0–A3 and SP, then reach the unchanged original handler entry. Four fixtures verify this boundary. **They stop before the original handler body.** No claim is made that the complete stock UI dispatcher, subsequent shooting state transitions, AF locks or lens commands ran in those tests.

Blocked-update and incomplete-stop fixtures verify that the wrapper withholds the original AF-ON handler. An incomplete-start fixture records a failure rather than accepting missing worker state as success. Pending commands after an injected wait failure remain a recovery problem; these tests do not establish retry or rollback policy.

## Test coverage and interpretation

The 66 checks comprise:

- Four complete native target/snapshot checks for narrow and wide fixtures.
- Six native FIFO checks: both queues, three full 16-entry cycles each, complete 124-byte records and pointer wrap verified.
- Six complete stock start → stop → restart → in-flight stop checks, one per non-Off class, including eleven seeded buffer ranges.
- Twenty-eight integrated profile checks: four categories for each SCP choice 0–6. They cover duplicate presses, both press orders, release/resume, stock mode refresh interference, dirty/poisoned stock target storage, changing SCP through all classes and forty deterministic mixed button events per initial class.
- Four native table-wrapper ABI/continuation checks.
- Four injected-failure checks: denied update permission, state `0x3000`, uncompleted stop and uncompleted start.
- Fourteen exhaustive button-state groups: four held states × four press/release events × seven SCP choices × two shared focus settings = 224 checked edges. Stock resource labels identify `MODE_FOCUS` values 0 as S-AF and 2 as C-AF. Both the setting and context byte remain unchanged. This is preservation of the examined software setting, not a lens continuity trial.

These are assertions about specific fixtures, not 66 independent proofs of complete camera behavior. The new suite is reported separately from historical counts.

## Stock options: what is and is not proved

Retaining the stock-produced ten-byte record avoids writing an unproved dropdown-enum translator. Capture preserves frame position, internal area kind, target size, vertical/horizontal dimensions, center priority and C-AF center-start fields. Exact cache equality is tested.

The fixtures supply narrow and wide setting values to the stock record builder. **They are not recordings of a user selecting stock Single and All in the camera's UI.** The implementation still needs configuration capture wired to the stock controls, correct menu labels, movement and orientation handling, persistence/custom-mode recall, and active-zone display. It must not globally replace stock target selection with two fixed records.

Additional static setting mapping clarifies the existing rotation-related converter: `0x1db1` is `MODE_AF_AREA_TYPE_ROTATE_ONOFF`; `0x5991` is `MODE_FOCUS_AF_AREA_TYPE_CHANGE_ONOFF_STILL/MOVIE`; `0xe1f1` is `MODE_AF_CHANGE`. The four-byte conversion path is distinct from the active ten-byte record. It should not be described as a proven AF-Home bridge.

Correction to earlier terminology: key `0x3081` maps to `MODE_ASPECT_RATIO`. Key `0x85b1` maps to `MODE_CONTINUE_TAKE`; the snapshot bounds conditional on that key were previously loosely called an aspect rectangle. The numeric bounds tests remain valid, but that label was unsupported. Helper `0x609832f5` copies a precomputed override record; its limited window does not itself prove an orientation transformation.

## Remaining boundaries

There is now an executable offline mechanism rather than just disconnected primitives. It would still be misleading to say every software gap is closed or only flashing remains.

Further offline engineering can address the full configuration UI/capture bridge, orientation and target movement, original shooting-handler continuation, all relevant UI states, display publication, reentrancy and recovery from failed transitions. The current suite does not implement or verify these. The original handlers' source and tables remain available for investigation; they are not being relabeled hardware-only gaps.

Real-device evidence is needed for physical button timing, actual kernel/device completion and stale inference callbacks, lens motion and acquisition quality, S-AF/C-AF continuity, burst behavior/latency, code/data ownership across runtime loading, and complete install/boot/recovery acceptance. The existing component checksum test does not establish the latter chain.

The definite conclusion is **software mechanism demonstrated under emulator fixtures; production extension feasibility remains conditional**. No result establishes impossibility. No camera trial or installable modified firmware has been produced.

## Reproduce and audit

Run `scripts/Run-OM3OfflineProof.ps1` from PowerShell. It opens the existing Ghidra project read-only, runs `OM3OfflineSuite.java`, rejects script errors or unexpected results and writes a hash manifest. Expected source main SHA-256: `5e8d376e9111a44ac0352f26030d7c1b17026d42c45f3600cfa02a0e8c5b7d59`.

The verified results, traces and log are in `analysis/button-af/closure/`. Older exploratory logs and failure files document earlier attempts; the manifest identifies the current verified run. `native-controller.emulator-only.bin` is a harness artifact at artificial RAM addresses, not a camera firmware image.

The multiplication instruction model is limited to the observed nonnegative operands and references the [GNU MN10300 simulator implementation](https://gnu.googlesource.com/binutils-gdb/+/refs/heads/master/sim/mn10300/mn10300.igen). The downloaded source is retained and hashed. Other UDF instructions are rejected. This improves the community processor model; it is not independent validation of the OM-3's silicon.
