# OM-3 COLOR editor: input, values and display

Model OM-3, displayed firmware 1.1, internal build 1100. Update file SHA-256
`8c133084414533159f587bf46bfb4152714c4074312a47c8d8503e33d605696d`; decoded main
component SHA-256 `5e8d376e9111a44ac0352f26030d7c1b17026d42c45f3600cfa02a0e8c5b7d59`.
Addresses are runtime addresses (decoded main offset + `60021020`).

Evidence is static disassembly plus native execution in OM-Emu, an MN10300
emulator that runs the GUI natively with named stand-ins for the camera
application, sensor, card and display timing. OM-Emu does not draw the
colour-wheel plane or model the ISP. No claim on this page has been tested on a
physical OM-3.

## Reaching the editor

From the shooting screen, OK opens the Super Control Panel with the COLOR item
selected, a second OK opens the Color Profile page (GUI state `0418`,
ID_ST_DIRECT_PICTUREMODE_ART) and Down selects "Color Vivid", the 12-sector
editor. Left/right on the profile row select COLOR1–4. Sub dial selects a
sector (or ALL), main dial changes the value, INFO toggles individual/ALL, held
OK resets.

## Key and command path

```text
UI_IN 02000084 (Delete) → GUI event 54 → 1000026 → widget command 9016
UI_IN 02001205 (INFO)   → GUI event 58 → 100002e → widget command 9014
```

Events map to commands through the table at `6133e244` and the 8-byte command
table at `6150088c` (`9014`/`9015` INFO press/release, `9016`/`9017` Delete
press/release). The Super Control Panel's direct pages are a state machine
(`610f5f88`) whose action table starts near `615d0a80`. Byte 0..1 of the screen
object hold the GUI state (`04 18` here).

- `9014` maps to forwarder `6125becc` (`615d0b08`), which passes the command
  to the focused widget chain.
- `9016` maps to `6125c7a7` (`615d0b64`). It reads setting 2163; only when that
  is 1 does it forward `900e`. Otherwise Delete is dropped on this page.
- The colour page container's command method `611c28e0` (vtable slot
  `615370e8`) forwards `9014` to its child at `(76,obj)` only for items
  5397/5398 and sends other commands, including `9016`, to its generic
  handler. The generic widget base (`6119a2be`, table `61502834`) does have
  an entry for `9016` (`6119a80f`).
- The editor's own dispatcher is `61223ca6` (viewer vtable slot `615af53c`).
  It receives `9014`, `9015`, `9012`, `900c` and others; the INFO handler is at
  `6122661b`.

A patch that wants Delete in this editor must therefore act at both the page
action entry and the container; patching only the editor dispatcher sees
nothing. This was established with OM-Emu execution traces and by an
emulator-only prototype that consumes `9016` at both points.

## Editor object

The editor parent has 13 children (`hu(obj+120) = 13`): the cursor child at
`(124,obj)` and twelve sector value children at `obj+128..+172`. The cursor
child's setting ID at `hu(child+80)` is 2197–2200 (COLOR1–4); the parallel
cursor set 2201–2204 reads 255 when ALL is selected. Each value child keeps its enum index
at `hu(child+94)` = 5 − value (list +5 … −5). Command `900c` sent to a child
refreshes its display. The constructor stores the parent pointer at
`61228102`; reset (held OK) goes through `61225de4`.

## Value label and wheel data

The numeric label below the wheel ("Vivid ±n") is refreshed by code at
`611d1401..611d1478`, which
reads setting `916 + sector` — the effective record, not the stored profile
IDs — through the generic settings getter returned by `60b8696a` (vtable +12),
then formats it with `%d`/`+%d` via `610fc42c` (`611d1471`). A redirected
stored value therefore does not reach this label unless this read is also
handled.

The wheel's twelve values come from a separate reader: `60b1d08d` reads
setting 903 (profile 1–4) and IDs 928–939, 940–951, 952–963 or 964–975 into a
12-byte buffer, builds a type-5 descriptor and passes it through `60b1d5a1` →
`604331b9` to `6042e4d3`, which bounds each value to −5…+5. As on PEN-F, text
and wheel are separate consumers.

## Drawing extra text

The colour-wheel view's paint method is in vtable slot `61452290` (stock
`610d8b67`). The PEN-F paint-wrapper technique works: clone the 684-byte
drawing context, load a font, draw with the stock text routine. The first word
of the text style selects a palette colour; observed values include 1
(yellow-green selection colour), 2 (light blue), 4 (blue), 10 and 13 (white)
and 15 (orange). Text accepts `@Axxx@` icon escapes; codes 000–08F render as icons
in this build, and `@A033@` is the erase/trash-style glyph. The renderer may consume text after the call returns,
so strings must outlive the paint call.
