# Hardware stages 1–2: owner's log template

This is the written log template from item 4 of stage 0 in
[HARDWARE-PHASE-PLAN.md](HARDWARE-PHASE-PLAN.md). Stages 1 and 2 use **stock
firmware only**. Nothing modified is flashed. The owner makes every entry and
every decision. Copy this file once for each session (for example
`logs/2026-11-DD-stage1.md`) and fill it in during the session, not afterwards.

**Do not start** until every row of section 1 in
[HARDWARE-STAGE0-RECORD.md](HARDWARE-STAGE0-RECORD.md#1-owner-decisions-to-be-completed-by-the-camera-owner)
is filled in, including the stage-1 go/no-go.

---

## A. Session header

| Field | Entry |
|---|---|
| Date, start time | |
| Stage (1 or 2) | |
| Camera body serial (last 4 digits are enough) | |
| Expendable body? (yes / no) | |
| Firmware shown in the menu before starting (expected 1.1) | |
| Battery 1 / battery 2 charge | |
| Card used (make, size; freshly formatted in camera: yes/no) | |
| USB cable (only if the USB route is rehearsed) | |
| Recording device for screen/lamp video | |

## B. Image verification (stage 1 only, before every flash)

Expected container SHA-256 (from the stage-0 record):
`8c133084414533159f587bf46bfb4152714c4074312a47c8d8503e33d605696d`
(240,517,120 bytes).

Compute it from PowerShell, on the exact file copied to the card:

```powershell
Get-FileHash -Algorithm SHA256 'X:\DCOLYMP\E1479999.BIN'
(Get-Item 'X:\DCOLYMP\E1479999.BIN').Length
```

| Copy | Location | SHA-256 matches (yes/no) | Size matches (yes/no) |
|---|---|---|---|
| Off-camera copy 1 | | | |
| Off-camera copy 2 | | | |
| File on the card | | | |

**Stop** if any row says no. Never flash a file whose hash you have not checked
on the card itself.

## C. Stage 1, step 1: baseline record (before any flash)

Back up settings first (OM Workspace or OI.Share). Then photograph each menu page
that holds AF settings, button assignments, AF Home, and the SCP.

| Item | Observation |
|---|---|
| Settings backup done (tool, file name) | |
| Shutter half-press: AF target/zone | |
| AF-ON button assignment | |
| AF Home settings | |
| S-AF / C-AF | |
| SCP Subject Detect setting | |
| Half press focuses normally (yes/no) | |
| AF-ON focuses normally (yes/no) | |
| Anything unusual before starting | |

## D. Stage 1, step 2: stock re-flash by SD (primary route)

The procedure is from section 3 of the stage-0 record (community guide, which
lists the OM-3). The card is in **slot 1**, with the file at
`DCOLYMP\E1479999.BIN`.

Start a video recording of the camera's front lamp and screen before step D2,
and keep it running until D6.

| Step | Expected | Time | Observed (lamp colour, screen, sound) |
|---|---|---|---|
| D1. Camera off; card with the file in slot 1; battery fully charged | — | | |
| D2. Hold **OK** and power on | screen stays blank | | |
| D3. Release OK once the lamp is lit | **solid orange** front lamp: installing. **Never cut power now.** | | |
| D4. Wait | solid orange for a few minutes | | |
| D5. Lamp changes | **blinking**: done | | |
| D6. Power off, then on | normal boot | | |
| D7. Menu firmware version | 1.1 | | |
| D8. Delete the file from the card (on a computer) | — | | |

Total time from D3 to D5: ________

**Stop immediately and record everything** if you see any of these:
- a red lamp, or any colour other than the expected ones;
- a lamp that stays solid orange for much longer than the first run (write
  down how long);
- a black screen or a boot loop after D6 (lit screen with repeated AF movement);
- anything you did not expect.

After a stop, use only the rehearsed procedure above. Do not try anything else
before recording what happened. The OM-5 II owner needed a second SD attempt
before the camera recovered; that is the only recovery evidence for this
firmware generation.

## E. Stage 1, step 3: second route (optional)

The official routes (OM Workspace over USB, OI.Share over Wi-Fi) are reported to
refuse a same-version or older update. Record what each one does when offered
the same version; do not try to force it.

| Route | What it offered or refused | Notes |
|---|---|---|
| OM Workspace (USB) | | |
| OI.Share (Wi-Fi) | | |

## F. Stage 1, step 4: confirm

| Check | Result |
|---|---|
| Normal boot from power-off (3 times) | |
| Settings kept or reset? (the guide says they are not kept) | |
| Settings restored from the backup in C | |
| Half press and AF-ON behave as in C | |
| Reset to defaults, then restore settings again | |

**Stage 1 pass:** the stock re-flash completed and the camera booted normally on
every route tried. Pass / abort: ________

---

## G. Stage 2: stock observations

These need no flashing. They answer questions the emulator cannot. Video is
the most useful record; note the clip file name next to each row.

### G1. AF-ON timing and display

| Test | Observation | Clip |
|---|---|---|
| AF-ON press: time to focus confirmation | | |
| AF-ON hold for 5 s: does the view change? | | |
| AF-ON release: does the view change, blank or flicker? | | |
| AF-ON pressed again straight after release: does it focus? Any delay? | | |
| 10 rapid AF-ON presses: does each one start AF? | | |

The emulator shows a display-output change starting at AF-ON release that
blocks the next press until the display confirms it. The rows above test
whether the real camera does anything visible at that moment.

### G2. Subject Detect with half press and AF-ON

Repeat for each SCP Subject Detect setting. Use the same scene each time and
note what is shown (detection frame, target, focus point). Confirm the option
names against your camera's menu.

| SCP setting | Half press: detection frame shown? Target used | AF-ON: detection frame shown? Target used |
|---|---|---|
| Off | | |
| Human | | |
| Motorsports | | |
| Airplanes | | |
| Trains | | |
| Birds | | |
| Dogs & Cats | | |

### G3. Display paths with AF-ON held

| Test | Observation | Clip |
|---|---|---|
| Eye to EVF while holding AF-ON | | |
| Eye away from EVF while holding AF-ON (back to monitor) | | |
| Manual EVF/monitor switch while holding AF-ON | | |
| Camera goes to sleep, then wake it with AF-ON | | |
| Wake with half press, then AF-ON | | |

**Stage 2 pass:** every row is recorded.

---

## H. After the session

- Keep the video clips and photos. Do not commit firmware images.
- Hand the filled log back so the stage-0 record, the plan and the gap
  assessment can be updated, and the emulator fixtures corrected from G1–G3.
