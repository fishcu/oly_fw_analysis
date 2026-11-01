# Five-point graph and native readout

The graph applies the same canonical transfer as image processing to the native
identity LUT. It is an explicit control reference with zero legacy contrast,
not a live image-job view. Its quarter markers use exact anchor heights at
rounded screen indices0,64,128,191,255. Geometry follows native child31's current
rectangle: layout1 shifts70px from layout0. The graph maps10-bit heights onto256
vertical pixels.

## Ownership and rendering

The callback first invokes the entire original paint method. Its new drawing
uses a private684-byte context copy and512-byte LUT. Caller context after native
paint, shared backend, receiver, return value and callee registers are preserved.
The graph receiver vtable, current actuator vtable/COLOR table and public picture
mode must agree. No image-buffer pointer is retained.

The native visibility join60bf7c40 filters children5–9,13–21 and26–31 on all
custom pages. These are old H/M/L widgets and graph artwork. Native RESET10–12
and footer24–25 remain available. Every other child replays all displaced loads;
no visibility bits are mutated, so renderer reuse cannot retain hidden state.
Resident paint/update/filter gates require sections6/8 and preserve stock paths
when unavailable. The update wrapper retains whole-receiver invalidation.

The painter no longer draws or allocates numeric text. Its complete-return
fixture models only rectangle raster submission; native clipping and backend
paths execute. The original paint fixture has an explicitly empty child list;
the actual traversal join is separately checked for all33 children, all pages
and profiles. These are raster requests, not physical pixels.

## Current page and published values

A wrapper at60cf9be6 runs after native viewer construction and before its118
publication. It preserves d2/d3/a2/a3, SP and the first-publication notification
flag. It resolves the canonical state and fills the existing74-byte label
variant at parameter118+10 with format5 and an inline string at+18.
Selected S/H or B/W are absolute four-digit heights; M is the signed−7..+7 step.
The current page name and native `@A028@` INFO token share this one row.
Japanese is identified through the actual resource2778 lookup; other languages
use short ASCII page names. All six JP/EN variants fit33UTF16 code units,
including terminator, and the native footer font/layout fixture.

Parameter118 byte3 reflects canonical state differing from neutral. Bytes4/6/7
remain native bitmap enum indices; expanded heights are never placed in them.
Actuator page2 remains the endpoint input page. For that page only, the published
display-layout byte5 is1, selecting the native pair footer layout; native page3
would skip the inline formatter. This is a display-layout remap, not a change to
input page state. Middle publishes layout2, pair layout1.

Actual edits now change meaningful published text. Native observer/event and
whole-receiver invalidation boundaries remain as before. This does not establish
physical queue completion or claim a camera LCD timing fix.

## Space and evidence

Two bounded native COLOR query regions are compressed without deleting queries:
pair60cf9d81..60cf9f2e and middle60cfa110..60cfa28a. Their exact preimage hashes
are checked. Shared queries preserve order, destination slots, raw temporaries,
variant conversion, diagnostic call/line and non-COLOR continuation. Reclaimed
bytes hold the footer publisher and strings. No native MONO branch is rewritten.
The full manifest records every section4/5/6/8 range and the two replacements.
A scan of the pinned main and known relocated section found no qualified direct
transfer or literal reference into the replaced pair interior. Two raw branch
matches were operand bytes in continuous native disassembly. Computed targets,
split addresses and unknown relocations remain outside that bounded scan.

Core/graph tests compare each new rectangle with an independent integer oracle,
including exact anchor height versus rounded LUT index. Native footer tests
cover all profiles/pages/languages, neutral/negative-middle migration, first
publication, wrong profile/actuator/page and physically unmapped late sections.
Pair/middle differentials use a declared GUI getter-envelope adapter around
actual602b9f84; pair logging return is modeled with exact arguments checked.
The pair comparison preserves all registers except MDR, which CALL sets to its
return address. Both MDR values are checked against the actual last variant CALL.
The unchanged COLOR suffix never reads MDR and returns through the stack PC;
the parent reaches its next CALL without reading MDR.
Footer construction and formatter-to-text-setter prefixes model no functions.
Native footer font parsing, metrics/clipping/backend use explicit line-storage
allocation/free and raster models. Update invalidation reaches the real event
queue boundary; queue delivery and full camera boot are not simulated.

```sh
PYTHONPATH=tools python3 tools/penf_tone_graph_probe.py --out /tmp/tone-graph
PYTHONPATH=tools python3 tools/penf_tone_viewer_probe.py --out /tmp/tone-viewer
```

The GUI worker allocates8704 stack bytes. The complete-return graph fixture
reached1840 bytes below its callback caller while executing the private context,
LUT, native clipping and backend paths. Only rectangle raster submission was
modeled. This is conditional path usage, not full-boot stack safety.
Tail ownership evidence establishes native boundaries and bounded load/reload,
not every possible later computed/DMA write or physical permission.
