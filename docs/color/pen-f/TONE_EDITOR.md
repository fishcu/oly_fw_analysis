# Native COLOR five-point editor

INFO cycles pair → middle → endpoints. Every page now edits the atomic canonical
word; native property IDs still bind the concrete axes, but no custom page writes
separate native H/M/L scalar values. The exact code/height, selected-axis clamp,
page reset and legacy migration rules are in [TONE_POINTS.md](TONE_POINTS.md).

The concrete actuator vtable60f4d350, one of three immutable COLOR tables and
public mode54–56 must agree. All eight native arrow/dial prefixes route to an
explicit operation0 through the unchanged GUI setter, using registered high
ID967/970/973 and the full word. No global proxy flag crosses a setter wait.
The native busy guards and async envelope remain unchanged.

On the black/white page, the front dial selects white and the rear dial selects
black. The native rear callback60c8736f uses the low binding at offset180;
the front callback60c873ec uses the high binding at offset184. The same bindings
select shadow/highlight on the first page. This physical identity follows the
[official PEN-F manual, page44](https://learning.omsystem.com/PEN-F/zz_pdf/pen-f_eng.pdf),
which assigns rear to shadows and front to highlights. The previous revision
misnamed those callbacks and incorrectly exchanged the endpoint bindings.
Arrow bindings and rotation directions are unchanged.

The manager validates canonical state, writes native ACTIVE part1, publishes
all three source words and invokes the correct profile refresh. It retains the
high ID for native manager completion. Legal native−7..7 requests cannot match
the tag. All five coordinates commit atomically. Native full settings reset
invalidates the word through existing reset loops; held OK edits only this page.

Input uses a32-byte private frame, current-value resolution a12-byte frame,
and the reference a16-byte frame plus its caller-owned LUT. Current H/M/L comes
from native602b9f84 only for shared migration; canonical state ignores it.
No released image buffer or completed native frame is read.

Resident entry guards require sections6 and8. If unavailable, recognized COLOR
pages0..2 do not edit settings; binding refresh clears the custom selection
before native table access. Other editor families retain native behavior,
including the four-page table60f4c330. The manager rejects tagged tone requests
when section8 is absent. Stale selected-profile input/bind/reset clears the page
without setting mutation.

The INFO replacement uses370 code bytes at60c87670 and a separate14-byte
halfword table at60c877e2, within the existing385-byte replacement. Generated HSL UI/wheel
compaction preserves the pinned released recipe. The full candidate emits exact
placement sizes in `candidate/editor/placement.json`; GUI helpers occupy352
bytes beginning610f1e54, while the core/owner table and editor use section8.
Native hooks compare every displaced preimage before composition.

The native probes bind each page before exercising 72 arrow/dial prefixes,
nine page resets, selected
manager write/publication, current-state references, selected-axis boundaries,
78 native INFO classifications, actual92-byte parameter read/write, stale mode
and unmapped-section fallback. No function is modeled in these editor cases.
The input prefix stops at the unchanged GUI setter; the transaction begins at
its explicit-value branch and stops at native refresh entry. They do not claim
full asynchronous button-to-display completion.

The INFO handler initially publishes its native page number. The outer viewer
then publishes the authoritative custom readout/layout described in
[TONE_GRAPH.md](TONE_GRAPH.md); the actuator page remains the input authority.
