# OM-3 COLOR settings and alternate cells

For the separate white balance fields and the limits of a per-COLOR WB
extension, see [white balance](WHITE_BALANCE.md).

Model OM-3, displayed firmware 1.1, internal build 1100. Update file SHA-256
`8c133084414533159f587bf46bfb4152714c4074312a47c8d8503e33d605696d`; decoded main
SHA-256 `5e8d376e9111a44ac0352f26030d7c1b17026d42c45f3600cfa02a0e8c5b7d59`.
Runtime addresses. Evidence: static disassembly and native execution in OM-Emu
(stand-ins for the camera application, card and NVRAM); no physical OM-3 test.

## Setting IDs

| ID | Meaning | Evidence |
| --- | --- | --- |
| 901 | Picture mode; COLOR1/2/3/4 = 54/55/56/**64** | emulator writes while selecting profiles |
| 903 | Profile shown by the editor, 1–4 | static reader `60b1d08d` |
| 916–927 | Effective saturation of the selected profile (record `f6ea`, indices 0–11) | static metadata, emulator label reads |
| 928–975 | Stored saturation, COLOR1–4 × 12 sectors (record `f6fa`, indices 0–47) | static metadata at `6062555c` |
| 2197–2200 | Selected sector per profile | editor cursor child |
| 2201–2204 | ALL indicator per profile (255) | editor caption checks |
| 2163 | Changes the Delete action on SCP direct pages | `6125c7c2` |

COLOR4 is not 57. Code that maps the picture mode to a profile must treat 64
explicitly. 903 follows the editor; 901 is the mode used for shooting.

The stored-profile reader `60b1d08d` selects 928/940/952/964 for profiles 1–4.
A second reader, `60cce94e`, sends profile 4 down its default branch to the
928 group; do not assume every consumer treats all four profiles identically.

## Alternate cells

Each setting ID 0–2255 has two 32-bit alternate cells in record `8b64`, at index
`2256 × part + ID`. Native accessors: read `604197e2`, write `6041980b`
(typed record calls `6041a1f9` / `60063431`). This mirrors the PEN-F
part-0/part-1 arrangement that its HSL patch uses for H/L.

For IDs 928–975:

- All 22 mode descriptor tables at `605f6c7c` select part 0 in the generic
  read/write loops (bounded static audit).
- On stock firmware in OM-Emu, part 1 equals part 0's factory values for
  IDs 904–987 (for example COLOR2/3 presets), and a stock saturation edit
  through the editor did not change the part-1 cell.
- The diagnostic loop `6040b5bb..6040b61a` (strings name `api_debug.c`) reads
  both parts of every ID, so part 1 is observable through at least one other
  stock path.

This is the same class of evidence the PEN-F patch relied on before its
physical tests. It is not ownership proof on OM-3.

## Persistence and custom modes

In OM-Emu, a value written to a part-1 cell with the native writer survives a
simulated power-off/on through the settings store, with no extension write
path.

Custom-mode recall carries part 1 with part 0. With COLOR1 sector 1 at
saturation +1 and a part-1 value set in P mode, turning the mode dial to C1
showed C1's own values for both (0 and an empty cell), and returning to P
restored both. Assigning to a custom mode and settings reset could not be
exercised: the emulator greys out the Custom Mode menu in its default switch
state.

The custom banks are MySET_1–5 (ids 4–8) and MOVIE_MYSET_1–5 (ids 134–138).
Their backup/restore surface is a set of CGI endpoints dispatched by
`61828f7e` (table `6194ac8c`). Whether a backup includes part-1 cells has not
been checked; extension data should not be assumed to survive a settings
backup and restore.
