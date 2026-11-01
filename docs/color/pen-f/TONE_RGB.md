# Four-channel five-point tone candidate

The COLOR1–3 tone editor has independent ALL, R, G and B curves. Trash cycles
ALL → R → G → B → ALL. INFO retains the selected channel and cycles the existing
shadow/highlight, middle and black/white pages. A held OK resets the current
page of the current channel. The native footer includes the channel, selected
values, INFO glyph and DEL hint. The graph uses that channel's identity-input
transfer. Channel switching always requests a redraw, including equal neutral
curves, and never writes a setting.

## Native state and asynchronous requests

Each profile owns four atomic canonical words in native ACTIVE part1.

| Profile | ALL | R | G | B |
|---|---:|---:|---:|---:|
| COLOR1 | 967 | 968 | 969 | 919 |
| COLOR2 | 970 | 971 | 972 | 920 |
| COLOR3 | 973 | 974 | 975 | 921 |

The stock part0 values remain native. The 1274-word parts and nine banks already
allocate these cells. All 54 mode filters reference these IDs only in part0.
All twelve IDs share reset-list membership. The 1315-key full reset and 855-key
default reset include them; the 25-key and 478-key resets exclude them. Native
getter/setter, all nine save/recall paths and the actual default reset execute
in `penf_tone_rgb_ownership_probe.py` with no native function models.

ALL retains the earlier canonical and legacy-H/M/L migration. RGB accepts only
valid canonical words and otherwise uses canonical neutral. Publication remains
on the existing committed HSL lifecycle. Source data is profile-major
`[ALL,R,G,B]`. Acquisition snapshots all 16 bytes into each of 40 large and five
compact owner rows. Every reuse overwrites the complete row; invalid/non-COLOR
owners clear it. Conversion copies the acquired row to job offsets14944..14959.
Allocation grows to14960 bytes and native final clearing grows to52 bytes from
14908. The bounded allocation-prefix/clear proof does not model the full heap.

GUI requests retain registered high IDs967/970/973. Their high nibble B/C/D/E
identifies ALL/R/G/B, independently of the current UI selection. The manager
normalizes to canonical B, validates, selects the table cell, performs one native
write, publishes, refreshes the matching profile, and completes with the original
registered ID. Unloaded late code rejects every private envelope.

The 208-byte native actuator stores `page + 3*channel` in its existing halfword
at194. The native constructor initializes0; screen reentry restores native page0
or1 and therefore ALL. Patched binding and INFO decode the page before any
native three-page table or parameter118 publication. Unloaded/stale bindings
clear the extension. Other native actuator families retain their native state.
The vtable's eighteen methods and the adjacent constructor/event region were
inspected for offset194 consumers; this is bounded static evidence.

## Native trash dispatch regression

Screen 897 selects native tone type 9 through `0x60cefa8e`. The default handler
at `0x60cd1bed` returns 20 for that screen. Table `0x60f7bba0` maps 20 to actuator
kind 3, whose factory at `0x60c87a49` calls constructor `0x60c87a89`. This constructor
selects the three supported tables `0x60f4cd08`, `0x60f4cd40` and `0x60f4cd78`.
The generic tone constructor does not produce these tables.

The dedicated constructor leaves actuator offset 100 untouched. The original
trash handler copied an HSL screen comparison against this field, so a
native-created tone actuator fell through to stock dispatch without cycling.
The former fixtures hid the defect by writing `0x13b8` into both offset 100 and
the current-screen global. The corrected fixtures use screen 897 and never
write offset 100. Native event `0x9749` also sets offset 200 to 1 and starts timer
500 for 8000 units. That field is an active timeout flag, not a busy-state guard.
The native arrow and INFO routes accept this state.

`tone_cycle` now omits the offset-100 comparison and offset 200 from its busy
checks. It retains the FSM 2/2 requirement, modal globals, controller and viewer
checks, exact supported profile table, current COLOR mode, busy fields 16 and
44, and selection range. It does not add a screen whitelist or alter the timer.

`native_cycle_cases` executes the constructor, binding and axis eligibility on
zero and sentinel allocations for all three COLOR profiles. It then drives the
real `0x9016` common dispatcher through ALL, R, G, B and ALL, both before and
after executing native `0x9749`. The regression checks unchanged settings and
retention of the native timeout flag. The 36-state matrix checks page retention.
Unloaded, modal and unsupported-actuator cases retain the stock fallback ABI.
External property, status, parameter and timer services are modeled. Viewer and
draw completion are modeled as in the existing dispatcher probe. The initial
failing log and test-only patch precede the production fix in the generated
audit. These checks do not execute event queue delivery or a physical LCD.

## Image processing and channel naming limit

ALL continues to transform the later luminance tone table. RGB transforms the
actual packed gamma output produced by native builder604f6083. Each packed u32
contains three ten-bit lanes and two reserved bits. The adapter preserves the
reserved bits and native source tables, and edits only exact output-owned
buffers at1060 or2084. It validates the existing callback, COLOR header, one of
sixteen exact request records and the parent job before reading channel words. A recognized ALL snapshot tag
B or A5D also distinguishes an acquired COLOR owner from an empty trailer.
At least one valid canonical RGB word is required before forcing a rebuild;
legacy ALL-only and entirely invalid RGB trailers retain stock gamma behavior.
Malformed RGB words are independent neutral no-ops; a malformed canonical ALL
coordinate payload does not suppress otherwise valid RGB words.

The ordinary outer call604f8588 enters a resident gate. Its late adapter saves
44 bytes of registers/local state, temporarily ORs mask0x02 into this job's context56,
executes the unchanged native builder with its original216-byte CALL frame, and
restores the exact original context56 value. The native gamma builder reads
context56 only at604f60e9 to decide whether to reuse cached data. Its inspected
helpers receive request/output pointers rather than this context. This forces a
fresh base even for neutral reset and prevents compounded edits. The measured
peak is356 bytes from entry to the ordinary outer builder with three nonneutral
RGB curves; this does not establish the image worker's full stack high water.

Single-bank results transform their sole owned table. The reachable native dual
path puts the selected source triplet at1060 and an identity companion at2084.
The adapter validates all256 companion words before transforming only the first
table. The native identity is `round(1023*i/255)`. It marks the active gamma
upload bits0/1 in context100 while preserving other bits. Native604b58c4 then
submits all256 words to hardware offsets3072/1024 even with a matching warm tag.
No new heap allocation or writable source-LUT alias is introduced.

**Physical color naming remains an inference.** `tone_rgb_lane_shifts` assigns
R/G/B to low/middle/high ten-bit lanes as0/10/20. Native execution proves lane
independence, selected-bank provenance and upload, but no named calibration or
physical pure-channel witness establishes those lanes' physical colors. The
single table is the explicit correction point if camera measurements establish
a different order. The fixed silicon order of the two banks is also unproved;
the tested dual composition applies the custom map once to the selected native
triplet and leaves its identity companion unchanged. This is an offline firmware
candidate, not a claim of verified camera RGB pixels.

## Placement and reproducible checks

Section8's native end selector at6004211d changes6115b800 to6115c800. Its loader
copies362496 bytes from logical41483000. The extra4096 bytes are stock FF and
remain4608 bytes below the next known library source at6115da00. Source48 lives
at60427c30, inside already loaded section2; the section2 initializer count is
zero and native execution leaves it untouched. The dispatch gate occupies
601cafc0..601cafe0 in section1, which already contains the application startup.
Every new slot has an exact FF preimage assertion. Linkers bound all final
sections, and missing-section tests remove the entire new section8 extent.

`penf_tone_rgb_ownership_probe.py` executes the native load/reload paths for
sections1/2/8 using the generated candidate image, preserves end canaries, runs
the section2 zero-count initializer with source memory present and unmapped,
and runs the section8 loaded-bit waiter. Logical storage, event/cache services
are explicit models. Literal/branch scans and known neighboring reservations
support the placement; they do not prove freedom from every computed/DMA write
or physical cache coherence.

`test_penf_tone_rgb.py` covers the four-word owner lifecycle, all36 UI states,
explicit async payloads, selected-page reset, guarded trash switching, actual
footer/graph paths, canonical-invalid/unloaded fallback, all256 native gamma
words, sequential cached edits/reset, source immutability, reserved bits,
foreign-pointer rejection, hardware submission and bounded stack consumption.
The existing ALL/HSL baseline, package roundtrip and exact pinned HSL OSD checks
remain required. Actual LCD timing and camera JPEG color output remain outside
these fixtures. The earlier reported white-only realtime delay is not claimed
fixed by this change.
