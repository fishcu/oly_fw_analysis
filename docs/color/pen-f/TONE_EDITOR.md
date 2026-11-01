# Native COLOR tone editor integration

The offline candidate adds an endpoint page to the PEN-F COLOR1–3 tone
actuator. INFO cycles shadow/highlight → middle → endpoints → shadow/highlight.
The two existing axis bindings remain native property IDs; their stride, table
count and ordinary getter/default behavior are unchanged. Only the concrete
endpoint-page input callbacks create endpoint requests.

This unit is executable and placed in the pinned main image. The composed graph and labels are documented in [TONE_GRAPH.md](TONE_GRAPH.md).
This isolated unit does not create an installable firmware container. No camera, firmware upload or flash operation is part of these probes.

## Endpoint controls

Black lift and white reduction use exact 10-bit output coordinates. Arrow and
dial input moves the selected coordinate by 16 codes. The final step can be
shorter: black is bounded by the reference shadow height, and white by the
reference highlight height. Both effective coordinates are clamped before each
relative edit. There is no rounded step getter or separate widget cursor.
Held OK on the endpoint page requests black 0 / white 1023 through the same setter.

The reference uses the native identity LUT at `0x605fdd38`, zero values for the
two legacy contrast slots, and the current native high/middle/low properties.
The raw order is `(0,0,H,M,L)`. These current values come from the native public
getter, not ACTIVE part0. The reference executes the same native conversion,
signal-anchor prepass and inner overlay as image processing. Its purpose is a
control graph; it does not claim to reproduce every per-image selected base.
The composed graph and labels use this exact reference and these coordinate units.

## Request and lifetime boundaries

The concrete actuator vtable `0x60f4d350` and one of its three immutable COLOR
tables identify the profile. Public picture-mode property 111 must match that
profile before endpoint input is accepted. A stale endpoint page is cleared by
input, binding refresh or held reset without changing any setting. New native
actuator construction still initializes an ordinary page.

Endpoint input sends an explicit operation 0 to the original GUI setter with the
registered profile high IDs 967, 970 or 973 and the full tagged endpoint word.
The native setter preserves its busy guards and asynchronous transaction.
The existing HSL manager fallback recognizes only that ID/tag combination,
writes part1 through the native ACTIVE API, publishes all three source words,
and selects the correct native COLOR refresh callback. The high ID is retained
for the unchanged manager completion path. Ordinary legal tone values −7..7
cannot match the endpoint tag.

No global proxy flag is live across a setter wait. Input owns its 512-byte
reference LUT and temporary values on the stack. The reference helper owns its
raw slots, coefficients and signal bounds. Neither reads a released image job
or a native function's completed stack frame.

Resident guards require sections 6 and 8 before entering late UI code. When
unavailable, ordinary input keeps the stock setter, endpoint-page input/reset
performs no edit, and binding refresh clears the third page before native table
access. The separate resident manager gate rejects tagged tone values if 8 is
absent, so a packed word cannot reach the stock scalar tone setter.

## Composition and space

`tools/penf_tone_editor_candidate.py` composes this unit over the exact verified
transport candidate. Released HSL sources and hashes stay pinned. A generated
HSL UI/wheel source uses shorter equivalent ADD instructions and removes one
redundant ID reconstruction. Its getter/default pointers are relinked; every
other emitted section is compared with the pinned baseline.

| Region | Start | Used / available bytes |
|---|---:|---:|
| Late editor |`0x6115b4dc`|573 /740|
| Native reference and step |`0x610f1ea0`|238 /288|
| INFO replacement and resident guards |`0x60c87670`|384 /385|
| Resident manager gate |`0x60a4ff8d`|21 /25|
| Tagged unavailable rejection |`0x6081b8af`|28 /32|

The INFO replacement preserves native non-COLOR pair/middle recognition and
its generic fallback. Two shared CALL adapters replace six separate jump
trampolines and return to the original callback continuations. Each input and
binding hook checks the exact displaced bytes before installation. The
candidate builder records source/image hashes, section sizes and symbols.

## Executable verification

Run from the repository root:

```sh
PYTHONPATH=tools python3 -m unittest discover -s tests -p test_penf_tone_editor.py -v
PYTHONPATH=tools python3 tools/penf_tone_editor_probe.py --out /tmp/tone-editor-audit
```

The native probes cover:

- The actual GUI explicit-value branch, composed HSL manager fallback, selected
  part1 write/publication and correct native per-profile refresh entry.
- 72 real arrow/dial callback prefixes across three profiles and three pages.
- The native reference curve compared byte-for-byte with the stock builder,
  and 96 relative-step/clamping cases.
- Nine page/binding cases, three held-reset requests and 78 native INFO
  classification cases including malformed and cross-table values.
- Native 92-byte parameter 118 read/write, preserving every byte except the
  selected page byte. This suffix starts after unchanged axis eligibility.
- Physically unmapped sections 6/8 code, tagged-write rejection, ordinary input
  fallback, endpoint-page no-op and preserved native callback stack position.
- Stale-profile input, rebinding and held reset, with no setting mutation.

No function models are used in this unit. The suites use explicitly initialized
native schema/callback tables, current typed records, a compound-mode ring,
ACTIVE settings and a native display parameter store. They do not invent a
whole-camera checkpoint. GUI busy-guard passage, asynchronous completion,
queue delivery and full renderer traversal remain separate contracts. The
input prefix stops at the unchanged GUI setter; the transaction proof starts
at its unchanged explicit-value branch; refresh is stopped at the correct
native per-profile callback. These boundaries must not be described as a
completed physical button-to-LCD transaction.

The existing per-image endpoint transport/kernel contract is documented in
[TONE_TRANSPORT.md](TONE_TRANSPORT.md). The composed graph drawing and whole-receiver invalidation are documented in
[TONE_GRAPH.md](TONE_GRAPH.md).

The resident unavailable-section fallback recognizes endpoint page2 only with one of the three exact COLOR tables. Other actuator families retain their native page2. A differential fixture uses the stock four-page table `60f4c330`: binding remains property896, all eight arrow/dial request prefixes and held-reset replay match stock with sections6/8 present or individually absent. Rejected non-COLOR tables are never reset by the late binder.
