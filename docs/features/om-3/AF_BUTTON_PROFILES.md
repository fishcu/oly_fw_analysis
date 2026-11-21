# OM-3 autofocus button profiles

Research for **OM-3 E147, version 1.1, main build 1100**. The current design
would let half press keep the normal AF target and give AF-ON a separate zone,
size and position configured from the per-button AF page. Both would keep the
shared S-AF/C-AF setting. AF Home stays independent. Subject Detect for AF-ON
is left to the stock AF Button setting described under
[Menu and settings](#menu-and-settings). This design has no working menu or
persistent profile implementation and is not a firmware patch for
installation.

## Inputs and static reproduction

Obtain the exact stock container separately and decode it with
[oly_container.py](../../../tools/oly_container.py). The
[firmware inventory](../../../provenance/firmware-inventory.json) lists the other
components. Run from the repository root; use a new local output directory.

| Input | Bytes | SHA-256 |
| --- | ---: | --- |
| `OLY_E_147_1100_0000_0000.BIN`, model bytes `1470` | 240,517,120 | `8c133084414533159f587bf46bfb4152714c4074312a47c8d8503e33d605696d` |
| Decoded main `0100`, build `1100` | 33,554,368 | `5e8d376e9111a44ac0352f26030d7c1b17026d42c45f3600cfa02a0e8c5b7d59` |
| Decoded resource `0106`, build `0100` | 143,523,776 | `3d9fd4426b45fbe4b715599422af38c6d22392c08543a69f63c28291c5a0b059` |

```sh
python tools/oly_container.py /path/to/OLY_E_147_1100_0000_0000.BIN --out /path/to/decoded
python tools/om3_af_probe.py /path/to/decoded/00_0100_50000020.decoded.bin
OM3_MAIN=/path/to/decoded/00_0100_50000020.decoded.bin python -m unittest tests/test_om3_af_probe.py
```

The unit tests check envelope decoding and input pinning without firmware.
With `OM3_MAIN` set, they also assert the page-27/28 rows and queue-95 AF
handlers listed below for this exact image.

Main addresses below use the CPU mapping `0x60021020 + decoded offset` for
this image. They are distinct from logical flash and container addresses.
For code observations, import decoded main at that base with the pinned
MN10300 language in the [archived setup](https://github.com/tsmkirby/oly_fw_analysis/blob/04df764a6a2c4c3eb0882ba67241bb91246f3721/research/om3_af_profiles/README.md#reproduce-native-execution).
Disassemble from the listed function entries and follow branch and call
targets; the Python probe reads data and does not emulate instructions.

## Menu and settings

- **Observed in stock data:** Multi-row page 27 points to two 36-byte rows at
  `0x6158dc44`, UI IDs 2154 and 2155, each with values 1 and 0. They map to
  `MODE_AF_SUBJECT_PRIORITY_RELEASE` and `MODE_AF_SUBJECT_PRIORITY_CUSTOM_SW`,
  key `0x90a1`, indices 0 and 1. Page 28 has AF Home area lists; page 29 has
  AF Home rows without inline choices. The probe prints the row IDs, labels,
  option values and all four UI-ID maps' coverage for the selected AF keys.
- **Observed in code:** Viewer constructor `0x61203696` looks up a page
  descriptor; `0x61203a81` matches setting IDs to its rows. The viewer also
  reads a runtime list model, so adding to the descriptor alone is not known
  to make a row appear. AEL/AFL operation settings use a different viewer.
- **Observed on a stock camera:** On the contributor's OM-3 with stock
  firmware, **Menu > AF > 2. AF > AF Button** offers two choices for AF-ON:
  "Always tracks focus on the selected AF Target Point" and tracking a
  subject detected at the selected target point. With the first selected,
  AF-ON ignored Subject Detect. This is a firsthand observation of stock
  behavior, without modified firmware or recorded media.
- **Observed in the emulator:** Changing the page-27 rows through the menu
  shows that stored value 0 renders "AF is always performed at the selected
  AF target position" and value 1 renders detected-subject priority. The top
  row commits only ID 2154 and the bottom row only ID 2155. A blank emulator
  session reads 1 for both; the stock registration payload at `0x6011e790`
  is `00 00`. Details are in the
  [archived menu notes](https://github.com/tsmkirby/oly_fw_analysis/blob/06517cf15bca7cc63440f6c95ea98b7511fb4282/research/om3_af_profiles/analysis/button-af/AFON-MENU-RESEARCH.md#stock-per-button-subject-detect-setting-likely-answer-to-the-owners-belief).
- **Unproven:** Page 27 is the proposed home for the new AF-ON zone row.
  Which row belongs to AF-ON is inferred, not shown: the page help names the
  shutter and AF-ON buttons, and the names suggest 2154 is the shutter
  (`..._RELEASE`) and 2155 AF-ON (`..._CUSTOM_SW`). Whether 2155 follows the
  physical key or the assignable AF-ON function is also open. The selected
  AF target arrays have a UI mapping for every allocated cell. Neither that
  scan nor the absence of a UI ID proves spare storage. Editor routing,
  persistent storage ownership, reset/custom-mode behavior and the active
  EVF/monitor overlay remain open.

Normal area UI enum `0x99a1` is distinct from internal area kind `0x84d1`.
Stock type conversion `0x609b3ecd` and target building `0x609b3c79` are
reuse candidates. SCP Subject Detect uses `0x1e71[0]`; focus mode is
`0xc021`. These are separate from target data.

## Button dispatch and bounded execution

The stock handlers are `0x610b9197` (half press), `0x610b96f0` (half
release), `0x610b962a` (AF-ON press) and `0x610b9653` (AF-ON release).
Queue 95 has 93 dispatch slots starting at `0x6031e224`. Commands
`0x2a/0x2b/0x2c` map to `0x603c86d7/0x603c8af3/0x603c8d14`; start/end
payload flags are separate from the 16-byte envelope. The common 12-byte reply
contains a low-halfword status plus correlation and pointer words. To check
the format, run the same probe with this **synthetic** envelope and payload:

```sh
python tools/om3_af_probe.py /path/to/decoded/00_0100_50000020.decoded.bin --request 06000000000000002a00000000100070 --payload 0500000004000000 --reply 000000000000000000100070
```

Expect command `0x2a`, handler `0x603c86d7`, kind 5 and flags `0x4`.
A reply status or start acknowledgement alone is not a focus result.

## Emulator evidence

Everything in this section ran in an emulator with modeled OS and device
services. None of it was tested on a camera, and no flashable image is
supplied. The separate-profile result tests the current design; the two
AF Home results test an earlier prototype that reused the AF Home target.

| Test | Design | Result |
| --- | --- | --- |
| [Separate AF-ON profile](#separate-af-on-profile) | Current | 324 operations reproduced across two runs; 1,096 checks, 0 failed |
| [Live AF Home handoff](#live-af-home-handoff) | Earlier prototype | 12/12 handoff edges in each of S-AF and C-AF; full acceptance 0/14 |
| [Fixture AF Home matrix](#fixture-af-home-matrix) | Earlier prototype | 28/28 profile checks |

### Separate AF-ON profile

**Observed in the emulator, reproduced across two runs:** an emulator-only
hook gives AF-ON its own saved zone, size and position, and the stock writer
builds the AF-ON target record from it. The harness ran on E147 1.1 with
OM-Emu commit `4e4ec4ef084542a7e30eecce56970c7e09c123c9`, the
[archived local patch](https://github.com/tsmkirby/oly_fw_analysis/blob/06517cf15bca7cc63440f6c95ea98b7511fb4282/research/om3_af_profiles/analysis/button-af/readiness/om-emu-af-native1/reproduction/om-emu-local.patch)
(CR-stripped SHA-256
`61cd13270e82f9bc5236c36c945783defda4c97a2e99f93b75f11da521877702`) and
Node `v26.12.1`.

- **Identity process:** ran 324 operations and recorded the full state of
  each.
- **Proof process:** repeated the same operations; every recorded field
  matched the identity run exactly.
- **Checks:** both runs evaluated 1,096 cross-role checks with no failures.
  They compare a hooked candidate against two unhooked controls on the same
  overlay: K1e, whose half press supplies the reference records, and K2.
- **Subject Detect:** Off (`0x1e71[0] = 0`) in every operation.

The checks establish:

- AF-ON press record = K1e half-press record built from the same edited
  settings, in landscape and EXIF 6.
- AF-ON release record = the candidate's own half-press record.
- The edited profile is held separately from the live half-press settings,
  for each role.
- After an edit and a pose change, the live cells equal K2's, and the hook
  makes no live store of the saved position.
- The writer reads the saved bank: 0 in landscape, 4 in EXIF 6.
- The writer runs 3 times in the T8d sequence and 7 times across the zones.
- For six zones and a custom size, the AF-ON press and release records equal
  K1e's half-press records.

**Assumptions and limits:**

- **Reference not shown equal to stock AF-ON.** The reference is the
  half-press record. Static analysis did not decide whether stock AF-ON with
  "Always tracks" writes the same record as stock half press: one writer is
  shared, but which inputs each button feeds it, a 1×1 centre substitution
  and publication timing are unresolved.
- **Display not covered.** The EVF/monitor frame was not validated: the
  harness's display stage failed in the emulator.
- **Not implemented:** menu row, persistent storage and the hook's firmware
  placement.

To reproduce (Windows, because the harness uses a directory junction and
Node's permission model):

1. **Workspace layout:**
   - `ref` is a junction to `research/om3_af_profiles` of the
     [archive commit](https://github.com/tsmkirby/oly_fw_analysis/tree/06517cf15bca7cc63440f6c95ea98b7511fb4282/research/om3_af_profiles),
     with Node v26.12.1 for Windows x64 unpacked at
     `ref/tooling/node-v26.12.1-win-x64/`.
   - `om-emu` is OM-Emu at the commit above with the patch applied, set up
     as in its
     [reproduction notes](https://github.com/tsmkirby/oly_fw_analysis/blob/06517cf15bca7cc63440f6c95ea98b7511fb4282/research/om3_af_profiles/analysis/button-af/readiness/om-emu-af-native1/reproduction/README.md).
   - `inputs` holds the decoded main `0100` and resource `0106` from the
     table above.
   - `work/harness` is a copy of the
     [accepted harness](https://github.com/tsmkirby/oly_fw_analysis/tree/06517cf15bca7cc63440f6c95ea98b7511fb4282/research/om3_af_profiles/analysis/button-af/readiness/t13b-afon-core-proof/harness).
2. From the workspace root, run the commands below.
3. In each `work/out/<tag>.launch/exit.json`, expect `ok` and `valid` true,
   mode `real`, an empty problem list, 324 operations executed, and 1,096
   relations evaluated with 0 failed. Expect a reproduction count of 324 for
   the proof.

```sh
ref/tooling/node-v26.12.1-win-x64/node work/harness/test_v5.mjs check-1
ref/tooling/node-v26.12.1-win-x64/node work/harness/make_freeze_v5.mjs cap-1
ref/tooling/node-v26.12.1-win-x64/node work/harness/launch_v5.mjs identity id-1 --freeze-sha <digest printed by make_freeze>
ref/tooling/node-v26.12.1-win-x64/node work/harness/launch_v5.mjs proof proof-1 --freeze-sha <same digest> --identity id-1
```

The freeze records the absolute path behind the `ref` junction, so a new
checkout gets its own digest. The pure-Node tests (43) need no emulator. The
[recorded runs](https://github.com/tsmkirby/oly_fw_analysis/tree/06517cf15bca7cc63440f6c95ea98b7511fb4282/research/om3_af_profiles/analysis/button-af/readiness/t13b-afon-core-proof)
include the freeze
(`03db7d9640965afbb4fa8fe39b58cb088de063f87ce63941cb0caa3d2d03ae92`), both
exit and inventory records, every operation log, and file hashes.

### Live AF Home handoff

A player-driven test on E147 1.1, with the same OM-Emu commit plus archived
local changes, passes 12 button-handoff edges in each of S-AF and C-AF with
Subject Detect Off. Native AF initialization and a central application-task
hook restore the expected target records for both release orders. Native
enum conversion fixes an earlier C-AF setup error (raw value 1 was MF).

Full live acceptance is **0/14**: neither Off case demonstrates the complete
queue-95/queue-94 AF worker chain, and all 12 nonzero-SCP cases stop before
completing their first measured edge. Native callback `0x608418fe` returns
but posts an unserved CPU3 event-flag request. Disassembly identifies flag
`0x3003` at `0x6004367a`, receiving task `0x60841a6b`, and a subsequent
loader at `0x60842bde` waiting on flag `0x3004`. Callback return is not proof
of Subject Detect completion. Because AF-ON relies on the stock AF Button
setting, the CPU3 service matters here only for half-press regression with
detection enabled.

The [reproduction bundle](https://github.com/tsmkirby/oly_fw_analysis/tree/a2b6d446783f85af67a1582618014d9ffdd5b1fc/research/om3_af_profiles/analysis/button-af/readiness/om-emu-af-native1/reproduction)
contains exact-build requirements, tested sources, emulator patch, hashes and
commands. The [14-case report](https://github.com/tsmkirby/oly_fw_analysis/blob/a2b6d446783f85af67a1582618014d9ffdd5b1fc/research/om3_af_profiles/analysis/button-af/readiness/om-emu-af-native1/matrix-cpu3-final/report.json)
separates handoff from full acceptance. The section-7 hook used here has no
packaging or placement proof.

### Fixture AF Home matrix

The engine-routed press/release matrix passed 28/28 profile checks across
seven SCP values. AF-ON took precedence while both buttons were held, used
the AF Home target and suppressed detection; release restored the half-press
profile. Only the first AF-ON press submitted LOCK_START and reached its
native acknowledgement. Later starts were blocked after a display-output
transition; its completion was not supplied. This uses stock-reset and
shooting-context fixtures, a silent SCPU, supplied startup inputs and modeled
OS/device services.

To repeat it, use the [pinned research checkout](https://github.com/tsmkirby/oly_fw_analysis/tree/04df764a6a2c4c3eb0882ba67241bb91246f3721/research/om3_af_profiles),
its Ghidra setup and [MN10300 carry correction](https://github.com/tsmkirby/oly_fw_analysis/blob/04df764a6a2c4c3eb0882ba67241bb91246f3721/research/om3_af_profiles/recorded-evidence/review/carry-fix/README.md).
From that checkout's research directory, generate the local assembly export
as described in `DECOMPILATION.md` (used by the access audit), set
`JAVA_HOME`, create a fresh output directory, and run:

```sh
analyzeHeadless /path/to/projects OM3_main_full -process 00_0100_50000020.decoded.bin -noanalysis -readOnly -scriptPath scripts -postScript OM3TaskContextMutexProof.java /path/to/output
```

Compare `original-button-matrix.txt`, `af-consumer-evidence.txt` and
`task-context-mutex-summary.txt` with the [recorded run and source hashes](https://github.com/tsmkirby/oly_fw_analysis/tree/04df764a6a2c4c3eb0882ba67241bb91246f3721/research/om3_af_profiles/recorded-evidence/task-context-mutex2).
The expected result includes exactly one feature mutex create in task context
(modeled) and one LOCK_START submission. No AF or device completion was
injected. Headless exit status alone is not a pass.

Detailed [menu/storage notes](https://github.com/tsmkirby/oly_fw_analysis/blob/06517cf15bca7cc63440f6c95ea98b7511fb4282/research/om3_af_profiles/analysis/button-af/AFON-MENU-RESEARCH.md)
and the historical reports and hardware-planning logs stay in the fork.
