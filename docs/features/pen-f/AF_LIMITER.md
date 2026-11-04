# PEN-F contrast-AF range limiter and custom-menu rows

PEN-F 3.1, build 3101, stock container SHA-256
`77398610b379f80238117f31a6d5bbf65d608b49ec563666c64d84367e969f2c`.
Addresses are CPU addresses in the decoded main component (base `0x60021020`).
Evidence is marked **code**, **native** (MN103 emulator) or **camera** (one
PEN-F body).

The [source build](../../../patches/live-nd-af-limiter/pen-f/README.md) adds a
Custom Menu A row, "AF Limiter: Off / 3/4 / 1/2 / 1/4". It keeps only the far
part of the contrast-AF scan range, so AF stops racking to the near end when
the subject is far away. It replaces the Focus Ring row.

## Scan range

`fcs_sub_iaf_set_lens_pos_info` (CALLS entry `0x6047eeab`, 7 direct callers)
fills the I-AF context `I = (ctx+12)` (code):

| Field | Name | Lens reports position info (`0x60469e85() != 0`) | Otherwise |
| --- | --- | --- | --- |
| `I+44` | POS_INI | s16 at `L+38` | `I+1600` |
| `I+100` | POS_FAR | s16 at `L+20` | `I+56` |
| `I+104` | POS_NEAR | s16 at `L+34` | `I+56 + table[L+8].+652` |

`L = (ctx+28)` is the lens-info block. Values are lens drive pulses; the sign of
NEAR − FAR depends on the lens, so a limiter must work relative to both ends.
Both branches meet at `0x6047ef38`, before a gated debug print.

31 sites in `0x60461f2e..0x6047f740` read both fields, including the FtAF scan
info (`0x6047cb40..0x6047cce0`), the scan-start helper `0x6047e045` and C-AF code
(code). Narrowing the fields at their source therefore reaches S-AF and C-AF.

The firmware also has lens-side limit commands (`LENS_FOCUS_MODE_LIMIT`,
`CONTLD_SET_NEAR_LD/FAR_LD`), probably for lenses with a limit switch. They are
not used here.

## Hook

At `0x6047ef38` the 10 stock bytes `mov (0x618a36a0),d0; btst 2048,d0` become
`call af_limit,[],4` and 3 NOPs. The helper reads setting 448 (v), sets
`NEAR = FAR + (NEAR − FAR) · (4 − v) / 4` for v < 4, and redoes the two
instructions. MN103 `ret` leaves PSW alone, so the stock `beq` after the call
sees the `btst` result.

Native: the whole function runs stock against patched for v = 0/1/2/3/7, both
branches, both pulse directions and both debug-flag states. NEAR for a
100 → 900 range becomes 900 / 700 / 500 / 300 / 900. FAR, POS_INI, the debug
path, callee-saved registers and SP match stock.

Camera (40-150 mm R, C-AF, fixed 1/2 in an earlier test build): AF felt faster
and made small corrections instead of full racks. Focus "dances" slightly when
the subject approaches the limit, as expected at the edge of the range. The menu
build sets and applies all four values.

## Setting

Setting 448 is the external-EVF auto switch. It is read only when an accessory
EVF is detected (display id `0x02021010` at `0x602ee094`), which the PEN-F cannot
have. The built-in EVF switch is setting 591. Descriptor `0x603e2830` points to
the stock list `{0,1,2,3}` at `0x603df178` instead of `{0,1}`.

A stored value carries over from the stock firmware: if the external-EVF switch
was On, the limiter starts at 3/4.

## Custom-menu row anatomy

The custom menu has 133 rows of 36 bytes at `0x60f51a50` (code):

| Offset | Field |
| ---: | --- |
| +0 | u16 setting id, u16 option count |
| +8 | title: u16 type, u16 string id, ptr text |
| +16 | help: same layout |
| +24 | option array A (row value) |
| +32 | option array B (popup) |

Option records are `{u32 value, u16 type, u16 string id, ptr}`. Type 4 is a
string id; type 5 is inline ASCII and is used 581 times in stock data. The row
title goes through the generic label copy `0x60c897d0`, which also handles
type 5 (native, camera).

Groups are 20-byte descriptors at `0x60f52d3c..0x60f52e58` with a first row and
a count. Group A (AF/MF) is `0x60f52d7c`. Adding a row inside a group means
moving the following groups, so the patch reuses the Focus Ring row
(`0x60f51c90`, setting 38).

## Reusing a setting in a custom-menu row: five places

Each was found by a camera test that failed after the previous one was fixed.

1. **Row:** setting id, option count, title, help, arrays A and B.
2. **Group's visible ids.** The menu shows only the ids in the group's list
   (records `{u16 0, u16 n, ptr}` at `0x60f484a4..0x60f48514`) and looks each up
   in the group's rows. Group A's list is in .data RAM `0x61619048`; its
   initializer is in the image at `0x60207308` (copied from
   `0x601ea800..0x6020b220` to `0x615fc540` at startup). Without this, the row is
   hidden. Group A's stock list also omits setting 598 (C-AF Lock).
3. **Rule set of the setting.** A row is enabled only if CANEXEC
   (`0x6075f0c9` → `0x60760e2d`) passes. For ids without an `app_check_mode`
   record, that is the rules engine `0x602bd488(id, 2, 2000)`. Setting 448 has
   rule set `0x603a164c`, "15210 == 1 → {0→0, 1→0}", which greys the row and
   would force values back to Off. The patch sets its rule count to 0; the rule
   itself is shared with setting 591 and stays.
4. **Popup kind table** `0x60f52f10`: 82 entries of `{u16 setting, u16 kind}`.
   The popup opener `0x60c8c43c` copies the kind into the popup struct; a missing
   id leaves that field uninitialised.
5. **Page action list.** Page table `0x60f43f24` holds 132 records of 36 bytes;
   +12/+16 give a list of `{u32 popup type, u32 setting, u32 fn}`. For page 67
   (group A, `0x60f44b84`) the list is at `0x60f4396c`. The key handler
   `0x60c7816d` searches it for the highlighted id and opens the popup only on
   a match. Without an entry, OK and right do nothing.

Check all five before the first camera build. The native checks for 2–5 are
table lookups through the stock routines; the popup itself needs live model
objects and was tested only on the camera.

## Open questions

- Persistence across power-off and coverage by Mysets (C1–C4).
- A viewfinder indicator when the limiter is on.
- A "focus here" limit from the current position (`L+38`) on a button.
- Pulse travel is not linear in distance; real distances would need the lens's
  distance-to-pulse commands.
