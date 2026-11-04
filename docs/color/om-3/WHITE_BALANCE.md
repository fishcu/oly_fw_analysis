# OM-3 white balance and COLOR profiles

OM-3 firmware 1.1, internal build 1100. Decoded main SHA-256
`5e8d376e9111a44ac0352f26030d7c1b17026d42c45f3600cfa02a0e8c5b7d59`.
Addresses are runtime addresses. Evidence: static setting metadata and native
GUI execution in OM-Emu. Initial observations used the HSL image without WB
changes; subsequent integration checks executed the experimental HSL/WB
extension. No physical camera, ISP, complete capture processing, or one-touch
WB measurement was tested.

## Established settings

The metadata table at `6062555c` contains four-byte `{u16 record, u16 index}`
entries. The native getter used for the observations is `603f039d`
(OM-Emu disassembly address `503cf37d`). Each comparison read all 2256 IDs.

| Setting | Record / index | Observation |
| --- | --- | --- |
| 9 | `8121` / 0 | Current WB selection |
| 1578 | `1cc1` / 0 | Changes with 9 on the direct WB page |
| 107 | `8f22` / 1 | Custom WB Kelvin |
| 1632 | `1d22` / 0 | Changes with 107 on Kelvin edits |
| 39 | `84f9` / 0 | Current A/B correction; +1 displays A1 |
| 132 | `9679` / 0 | Current G/M correction; +2 displays G2 |
| 1592 | `1ce9` / 19 | CWB A/B correction backing field |
| 1605 | `1cf9` / 19 | CWB G/M correction backing field |
| 84 | `8e41` / 0 | One-touch slot cursor: 1–4 |
| 1720 | `8131` / 0 | Changes on WB selection; meaning not established |

These pairs describe correspondence through the high-level getter, not
interchangeable raw values or APIs. The raw record for 9 holds a WB category
(for example 3 for CWB), while its high-level getter presents the combined WB
choice (9 for CWB). Native UI writes to the backing fields have now been
verified to propagate into current fields; ISP output remains untested.

## Reproduced GUI observations

Start a fresh E147 session in P mode, COLOR1. Open the Super Control Panel,
move from Picture Mode to WB, and open its direct page (`0417`, panel 496).
Starting from Auto, successive Right presses select:

| WB mode | Setting 9 and 1578 |
| --- | --- |
| Auto | 0 |
| Sunny | 6 |
| Shade | 8 |
| Cloudy | 7 |
| Incandescent | 1 |
| Fluorescent | 3 |
| Underwater | 18 |
| Flash | 17 |
| One-touch 1–4 | 13, 14, 15, 16 |
| Custom WB | 9 |

At Custom WB, Down selects the Kelvin row. Main dial +1 changed 5400 to
5600 in **107 and 1632**, with no other setting value changed. Down selects
the correction row. Main +1 changed **132 and 1605** from 0 to 1. Right
opened the correction grid (`0408`, panel 460), changed **39 and 1592** from
0 to 1, and displayed A1/G1. Main +1 changed **132 and 1605** to 2 and
displayed A1/G2. These observations establish both axes rather than treating
WB as a Kelvin value alone.

Returning to the WB selection and choosing Auto changed the current
corrections 39 and 132 back to 0 while leaving CWB's 1592/1605 at 1/2.
Choosing CWB again recalled 1/2 into 39/132. Thus stock firmware already
recalls corrections by WB mode. This is not evidence of recall by COLOR
profile. Static metadata contains 13 exposed entries each for records
`1ce9` and `1cf9`, with indices
`0,18,5,1,7,14,10,12,13,15,16,17,19` in ID order (1580–1592 and
1593–1605 respectively).

## Native setter and profile transition

A working experimental settings-recall extension is now included in
[PR #11](https://github.com/fishcu/oly_fw_analysis/pull/11). It uses the native
settings path before capture rather than changing the late HSL builder.

During GUI profile changes, `60aea1de(id,value,a0=1)` receives 901 with
54/55/56/64. It acquires the stock UI lock, calls `603f011a`, and converts the
UI value before entering commit `603f1ea1`. The latter receives the grouped
901/1111 representation, finishes dependency propagation, and updates editor
profile 903. This provides an observed commit boundary for native GUI profile
changes. Direct native calls through this UI path also reproduce profile changes.

The failed scalar setter experiment used a different interface:
`60afa3f9` -> `603f015d` -> `603f1ea1`. Groups are listed at `605b49d4`, 34 bytes
per row, terminated by ID 3200 within each row:

| Group | Member IDs | Argument to the raw commit interface |
| --- | --- | --- |
| WB, 9 | 9, 1720, 1765, 84 | Pointer to four 32-bit raw values |
| Picture mode, 901 | 901, 1111 | Pointer to two 32-bit raw values |

Passing an integer instead of a pointer faults in `603f17d2` when it loads
array elements at `603f17f1`. Passing displayed values as raw values is also
incorrect: CWB's displayed choice 9 has raw WB category 3; COLOR's raw picture
mode is 11 with its profile in 1111. Native UI conversion avoids both mistakes.

For WB recall, verified calls use UI ID 1578 for the selected WB choice, 1632
for Kelvin, and the backing correction pair below. CWB calls for 9, 5600, +2,
+3 produce matching active 9/107/39/132 and backing 1578/1632/1592/1605 values.
Changing only current IDs 39/132 fails to update the backing correction table.
A low-level write and a complete native UI transaction therefore differ.

| Displayed WB | A/B ID | G/M ID |
| --- | ---: | ---: |
| Auto (0) | 1580 | 1593 |
| Underwater (18) | 1581 | 1594 |
| Fluorescent (3) | 1582 | 1595 |
| Incandescent (1) | 1583 | 1596 |
| Sunny (6) | 1584 | 1597 |
| Flash (17) | 1585 | 1598 |
| Cloudy (7) | 1586 | 1599 |
| Shade (8) | 1587 | 1600 |
| One-touch (13–16) | 1588–1591 | 1601–1604 |
| CWB (9) | 1592 | 1605 |

The mapping was established by putting distinct signed values in all thirteen
backing entries through native setters, selecting each WB choice, and reading
current 39/132. The combined extension's reproducible integration probe recalls
every choice through actual firmware and verifies the active correction pair.

## Native WB parameter copies

Stock slice `604876ba..60487736` copies WB fields into a compact record:

| Destination | Native source |
| --- | --- |
| +33, signed byte | Record `84f9`, index 0: A/B |
| +34, signed byte | Record `9679`, index 0: G/M |
| +35, byte | Record `8131`, index 0 |
| +36, byte | Record `8121`, index 0: raw WB category |
| +38, halfword | Record `8f22`, index selected by `8a61` |

The integration probe executes this unmodified slice with an explicit scratch
destination and stop boundary, against OM-Emu's live native settings DB after
WB recall. Kelvin and both tint bytes match each restored configuration;
surrounding bytes remain unchanged. This establishes one native parameter-copy
path, not a complete capture test or the ownership/timing of every live job.

Other static routes matter: `603e8c12` copies raw WB category to snapshot+37644;
`603e8e8d..603e8e9d` copies Kelvin to snapshot+37642. The processing branch near
`60457949` selects WB handling using snapshot+37644, while branches including
`60457979` and `60457c44` read tint records. This mix of snapshot and live-record
inputs means queued/burst timing must be tested explicitly. A compact-copy
result alone does not prove the full pipeline locks all WB inputs at shutter time.

## Extension evidence and remaining limits

The extension stores four checked words for each COLOR profile and one
non-COLOR record in part 1 of IDs 904–923. HSL's part-1 IDs 928–975 are separate.
All 22 examined native mode tables select part 0 for the WB IDs. This is a
bounded table audit, not universal storage-ownership proof.

Verified in OM-Emu: four independent COLOR configurations; normal WB dial edits;
native GUI profile changes; non-COLOR WB restore; simulated power cycle and
process restart; custom-bank switching; all thirteen WB choices; invalid record
fallback; HSL coexistence; and the compact native copy above. Native C1 recall
loads its saved defaults and discards unassigned C1 edits under its default save
policy. Both native WB and extension records follow that behaviour; returning
to the ordinary shooting bank restores its separate values.

The isolated emulator harness models the exact section-4 storage read, handles
the restored SCPU backup marker and omits an unsupported ARGB graphics plane.
Save/recall is executed by the assembled firmware, not simulated by the harness.
The source, placement, storage format and repeatable probe are included in
[PR #11](https://github.com/fishcu/oly_fw_analysis/pull/11).

Still unqualified: real startup and section residency/reload concurrency;
physical creative-dial transitions; ISP/live-view/JPEG output; RAW metadata and
development; queued/burst timing; reset; custom-mode assignment/save policies;
settings backup/restore; and the measured-gain storage behind one-touch slots.
One-touch choices currently remain references to the four shared camera slots.
No hardware result or camera-safe installation claim follows from these tests.

## Further fault and capture-timing experiments

The hardening work in [PR #11](https://github.com/fishcu/oly_fw_analysis/pull/11)
adds reproducible native ABI, failed-load and lifecycle probes. The native
loader sets section 4's loaded bit even after the modeled read reports failure;
the previous extension could enter missing/partial WB code. A full-body check
and stock fallback now reject failed, partial, already-marked-invalid and
single-bit-corrupted WB bodies. This protects extension entry, not the integrity
of the remainder of section 4 or physical cache behaviour.

The ABI audit also found nested-call stack preservation bugs: SP+0 is a CALL
return-address slot. A WB return value, HSL display/Delete D1, HSL builder D0,
and HSL label D3 were stored there across calls. The extension now reserves that
slot. Isolated WB/display/Delete/builder regressions fail on the previous image
and pass on the corrected image; the label is covered by inspection and GUI
regression. Native commit completion is modeled in the isolated ABI cases.

All six boundaries of a five-write WB save were injected as alternate-record
states. After a simulated power cycle, old/new complete records recalled and
incomplete records inherited the active WB. This tests RAM record states and a
clean modeled power cycle, not power loss during physical flash programming.
A 1,000-switch deterministic run preserved the cleared recursion guard and
showed no before/after changes outside IDs 904–923 in all 2,256 part-1 cells.
This is a bounded storage-footprint test, not a global RAM watchpoint or proof
against concurrent tasks. An eight-state creative-input attempt produced no
picture-mode transitions in this emulator state, so that route remains unqualified.

The capture concern now has a controlled native reproduction. COLOR1's compact
parameters held 4000 K with A/B -2 and G/M +2. After selecting COLOR2 at 5000 K
with A/B -1 and G/M +1, stock CWB processing slice `60457c44..60457c80` was
entered with the earlier 4000 K snapshot at context+37642. It wrote 4000 K to
context+5422, but -1/+1 from the live records to context+37734/+37736. Thus this
branch can combine earlier Kelvin with later tint under controlled scheduling.
The experiment uses a synthetic processing object and explicit entry/stop;
whether a real queued capture can encounter that ordering remains unproven.

A new hash-pinned stock route audit (`tools/om3_wb_capture_route.py`) checks two
identified callers of preparation routine `603e8e04`, at `603e37e2` and
`603e6325`. Within the routine, `603e8e9d` stores Kelvin in the snapshot and
`603e8f44` calls `60454b7c`, which synchronously calls formatter `60456793`.
The CWB formatter reads live A/B and G/M at `60457c44` and `60457c5d`.
This is static call-order evidence; it does not prove whether preemption or
callbacks allow a GUI edit between the reads in normal capture.

The two callers have different surrounding event paths. The increment at
`603e62c5..603e62cd` is not yet tied to a matching decrement, every relevant
capture, or an apply context. No verified native completion signal currently
supports a deferred profile/WB transaction. The existing commit hook runs
after the UI setter has entered settings commit, so it cannot defer the whole
transaction on its own. The current extension does not claim queued/burst WB
correctness. A fix requires either a verified image-owned correction source or
a deferral mechanism covering all relevant settings reads and outstanding
captures. See `patches/hsl/om-3/HARDENING.md` in PR #11 for the implementation
status and bounded emulator probes.

Run the static audit on the stock decoded main with
`python3 tools/om3_wb_capture_route.py ../../extracted/om3-1100/00_0100_50000020.decoded.bin`.
