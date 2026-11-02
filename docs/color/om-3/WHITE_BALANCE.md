# OM-3 white balance and COLOR profiles

OM-3 firmware 1.1, internal build 1100. Decoded main SHA-256
`5e8d376e9111a44ac0352f26030d7c1b17026d42c45f3600cfa02a0e8c5b7d59`.
Addresses are runtime addresses. Evidence: static setting metadata and native
GUI execution in a modified OM-Emu with the experimental HSL image. The HSL
image does not intentionally change the WB page. No physical camera, ISP,
normal capture processing, or one-touch WB measurement was tested.

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

These pairs describe observed correspondence, not interchangeable APIs. In
particular, a write to a backing field alone has not been shown to refresh the
current field, notify the camera application, or affect the ISP.

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

## Feasibility and patch boundary

Per-COLOR WB is plausible as a settings save/recall extension: preserve WB
selection, custom Kelvin and the correction data for each COLOR1–4 slot;
on a profile transition, use the native WB update path to restore them.
This is a proposed design, not a working firmware patch.

The existing HSL builder hook is too late to serve as a demonstrated WB
hook: it edits COLOR output records, whereas WB belongs to an earlier
processing stage whose OM-3 parameter handoff has not been mapped here.
Writing Kelvin into HSL storage would establish neither WB processing nor
capture timing.

An implementation still needs:

- A traced profile transition covering menu, SCP, creative dial and custom
  mode recall, with safe ordering relative to stock settings refresh.
- A verified WB setter ABI and notifications. Direct experimental calls to
  OM-Emu's mapped API setter (disassembly address `50ad93d9`) with scalar registers faulted in
  the getter path; no callable setter contract is established by that test.
- Allocated persistent storage with an ownership audit. HSL already uses
  part 1 of IDs 928–975; WB must not overwrite those packed H/L words.
- A policy for entry from and exit to non-COLOR modes, first use, reset,
  custom-mode assignment/recall and settings backup/restore.
- A decision whether one-touch slots remain shared references or their
  measured gains are copied. Selecting slots 1–4 proves no gain storage.
- Verification of live view, captured JPEG, RAW metadata and RAW development,
  including a WB/profile edit while an earlier image is still processing.

The emulator experiments establish editable settings and a native per-WB-mode
recall mechanism. They do not yet qualify an extension to the installable HSL
patch. The current result is research for that extension, not a claim that
the feature is impossible or camera-tested.
