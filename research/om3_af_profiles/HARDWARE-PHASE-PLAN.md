# OM-3 AF profiles: hardware phase plan

Draft, updated 9 November 2026. This is a plan, not an authorization. The project has so
far been offline research. Nothing in this repository has been flashed, and no
installable image exists. The readiness decision stays **NO-GO** until the
stages below pass on a real camera. Every flash is the camera owner's own
decision, made separately at each stage.

## Why a hardware phase, and why so cautious

GO requires all four acceptance gates in
[FEATURE-SPEC.md](analysis/button-af/FEATURE-SPEC.md). The gate table in
[AF-GAP-CLOSURE-ASSESSMENT.md](AF-GAP-CLOSURE-ASSESSMENT.md) shows that two of
them cannot be closed offline:

- **Gate 4:** full boot, updater acceptance and recovery.
- **The physical half of gate 1:** real replies from the secondary chip (SCPU),
  the display and the AF hardware.

There is direct evidence that emulator success does not predict a safe boot:

- **Sibling-body incident.** On a sibling body (OM-5 Mark II, firmware E148
  1.1), two modified builds each produced a boot loop: a lit black screen with
  repeated AF movement, cycling about once a second. The first had passed
  static review and OM-Emu testing beforehand. The second reduced the changes
  further, and it still failed. This is recorded in xulfr's fork of the upstream
  repository (`patches/hsl/om-5-ii/BRICK-RISK.md` and
  `research/OM5II-BOOT-LOOP-TRACE-2026-11-05.md`). The root cause was never
  established. A stock re-flash recovered the camera, but on the first attempt
  only a sustained red light appeared, and a second attempt was needed.
- **Upstream recovery notes.** `docs/boot/pen-f/RECOVERY.md` and
  `docs/safety/VALIDATION.md` say:
  - no independent rescue loader or immutable boot-ROM recovery has been
    established;
  - main updates rewrite whole components;
  - some flash error returns are discarded;
  - an alignment fault once passed the emulator and then restarted a camera.
- **This project's own limits.** The emulator runs labelled startup steps
  directly, keeps the SCPU silent, and has no display or cache model. The
  remaining work items in `PREHARDWARE-AF-AUDIT.md` include owned data RAM,
  runtime loading, persistent storage and memory and loading for deployment.

The plan therefore proves recovery first. It then raises the amount of
modification one small step at a time, and each step needs its own decision.

Current offline progress is in [HARDWARE-STAGE0-RECORD.md](HARDWARE-STAGE0-RECORD.md).
The revised interrupt installer/task-context mutex passes 28/28, and its proposed
layout passes native section loading and exact changed-byte enumeration. These
results retain the documented fixtures and do not close physical boot, recovery,
cache/DMA ownership or acquisition. No stage-specific image has been built.

## Stage 0: decisions and prerequisites (no flashing)

1. **Owner's decision.** Record that the owner accepts the risk of a camera
   that will not boot and may not be recoverable.
   - Record whether a second (expendable) body is available.
   - If only one body is available, stages 3–6 carry the full brick risk.
2. **Exact inputs.** Archive the stock E147 1.1 `.BIN` that this research uses
   (main block SHA-256 `5e8d376e…`) with its hashes. Keep at least two copies
   off-camera.
3. **Recovery procedure research** (offline):
   - Confirm the OM-3's stock update entry: SD `DCOLYMP` / `E147????BIN`, and
     the vendor updater over USB.
   - Check whether the community manual-install method for the OM-1 applies to
     the OM-3 (`iKenndac/om-1-manual-firmware-install`, linked in
     `AF_BUTTON_PROFILES.md`).
   - Write down the exact button sequence, cards, cables and expected light and
     screen states.
4. **Equipment.** Two fully charged batteries; dedicated, freshly formatted
   cards; a USB cable known to work with the vendor updater; a written log
   template (time, image hash, observations, light colours, photos or video of
   the screen).
5. **Remaining offline exit criteria** before any image that contains new code
   (stage 4 onward):
   - **Owned memory.** Settle owned data RAM. The live layout uses section-1 tail state through its uncached alias;
     continue the secondary-CPU/DMA ownership review and physical confirmation.
   - **Placement.** Settle code placement: the section-4 FF tail
     `0x60a8f088`–`0x60a8f800` leaves 43 bytes in the live layout. The revised helper/installer uses
     171/176 bytes in its section-1 gap. Padding is not proof of ownership.
   - **Runtime loading.** Show that the placed code is loaded at boot through
     the stock section loader. OM-Emu does not run it.
   - **Alignment.** Audit every word and halfword access in the new code
     (`VALIDATION.md`).
   - **Narrow diff.** Change as little as possible. Identify every changed byte
     and justify each one.

**Exit:** the owner records a go/no-go for stage 1.

## Stage 1: recovery rehearsal with stock firmware only

Goal: prove, on this camera, that the stock same-version update can be
re-applied and observed. Nothing modified is used.

1. **Baseline record.** Record the current firmware version, settings and the
   behaviour of the buttons and SCP (half press, AF-ON, Subject Detect
   settings).
2. **Stock re-flash.** Re-apply stock E147 1.1 through the primary route.
   Record each step, how long it takes, and the light and screen states.
3. **Second route.** If a second route exists (SD versus USB updater), rehearse
   it too.
4. **Confirm.** Check normal boot, settings retention and the
   reset-to-default behaviour.

**Pass:** the stock re-flash completes and the camera boots normally on every
route tried.
**Abort:** any unexpected state. Stop and do not continue to later stages.

## Stage 2: stock observations that close emulator unknowns (no modification)

These cost nothing in risk and answer open questions from the assessment:

- **AF-ON timing and display.** Time AF-ON press, hold and release, and repeated
  AF-ON presses. Note whether the view changes or flickers when AF-ON is
  released. The emulator shows a display-output change starting at AF-ON
  release (state word `0x62b7f7b4`) that blocks re-pressing until the display
  confirms it.
- **Subject Detect with half press and AF-ON** under each SCP setting, on stock
  firmware. This is the behaviour the feature intends to change.
- **Eye sensor, EVF/monitor switching and sleep/wake** with AF-ON held. These
  are the display paths that the emulator fixtures assume.

**Pass:** the observations are recorded. They feed corrections to the
emulator fixtures, such as the secondary GUI state and the display
assumptions.

## Stage 3: packaging canary (no change to program behaviour)

Goal: test this project's packaging and checksum path, and the updater's
acceptance of a repacked file, with no change to program behaviour.

- Build an image whose component bytes are identical to stock, through the
  project's own decode/encode and checksum path. Prove the bytes are identical
  offline before using it.
- Flash, boot, verify, then restore stock (stage-1 procedure).

**Pass:** accepted, boots normally, restores cleanly.
**Note:** a byte-identical image proves the tool path, not that modified code
is safe.

## Stage 4: minimal modified-main canary

Goal: show that a main component with a tiny, inert change, plus repaired
checksums, boots and can be recovered.

- Change one data byte that only a user action reads (for example a menu
  string), never boot code. Use no new code.
- Flash, boot, check the changed string appears, use the camera normally, then
  restore stock.

**Pass:** it boots, the change is visible, and it restores.
**Abort:** any boot anomaly. Recover with the stage-1 procedure and stop. The
OM-5 II failures happened in modified-main images.

## Stage 5: inert placed code

Goal: separate "the new code is present and loaded" from "the new code runs".

- Place the final native components at their intended addresses. Install
  **no** table redirect, so nothing calls them.
- After boot, if a safe read-back path exists, confirm the bytes are present.
  Otherwise rely on normal-operation checks.
- Restore stock.

**Pass:** it boots and behaves exactly like stock. This stage tests placement,
section loading and checksum coverage for the real component.

## Stage 6: hooks installed, feature pass-through

- Redirect the four shooting-table entries to the wrappers. Make the wrappers
  continue straight to the original handlers, with the profile transaction
  disabled.
- Test: half press, AF-ON, each SCP value, sleep/wake, EVF/monitor switching,
  burst shooting, and power cycling.

**Pass:** behaviour is identical to the stage-2 stock observations.

## Stage 7: full feature

- Enable the profile transaction.
- **Acceptance matrix.** Physically repeat the emulator's 28-edge matrix (half
  press, AF-ON press, AF-ON release, half release, each for SCP 0–6), plus
  repeated AF-ON presses.
  - Half press: normal target, and Subject Detect follows SCP.
  - AF-ON: AF Home target, with Subject Detect bypassed.
  - Release restores the previous state.
- Also check:
  - **Gate 2:** orientation, target editing and display.
  - **Gate 3:** stress: rapid alternation, bursts, AF-ON during capture,
    custom modes, settings reset and reload.
  - **Lifecycle:** sleep, battery pull, power cycle.
- Restore stock at the end unless the owner decides to keep the feature
  installed.

**Pass:** all four gates are closed with recorded evidence. Only then can the
readiness decision be revisited.

## Rules that apply at every stage

- One image per stage, archived with its SHA-256. Never flash an image that has
  not been archived.
- Never reuse a failed image. Never retry a failed stage without new evidence.
- Restore stock between stages, and confirm that a normal boot follows each
  restore.
- **Stop conditions:**
  - a black screen or boot loop;
  - a red or other unexpected update light;
  - a stalled update progress indicator;
  - any setting or behaviour that is not reproducible.

  On any of these, recover using the rehearsed procedure only, and record
  everything.
- Keep the assessment updated after each stage, and push the evidence (the
  observations, not the images).

## Responsibilities

- **Offline work (assistant):** the stage-0 exit criteria, image construction
  only on the owner's explicit instruction for a named stage, byte-level diffs
  and checks, and updating the documents with results.
- **Physical work (owner):** every flash and every observation on the camera,
  and every stage decision.
