# Equal-quarter five-point state

`points.s` and `penf_tone_points.py` define the same five-point state. X is fixed
at0,1/4,1/2,3/4,1. Y is nondecreasing B≤S≤M≤H≤W. There are no per-consumer
neighbor clamps when decoding a canonical word.

## Canonical word

| Bits | Meaning |
|---|---|
|28..31|Tag0xb|
|24..27|Middle code0..14; signed value code−7; height288+32×code|
|18..23|White code|
|12..17|Highlight code|
|6..11|Shadow code|
|0..5|Black code|

Each six-bit codeq0..62 means16q; q63 means1023. Middle code15, a wrong tag or
unordered heights is invalid. Default `(0,256,512,768,1023)` packs as
`0xb7ff0400`. The word is committed atomically in native ACTIVE part1 of high
IDs967/970/973, so middle edits cannot cross separately stored S/H coordinates.

`decode` validates only. `edit` changes one chosen axis and clamps that axis
between unchanged neighbors. B/S/H/W move by one representable code; middle
moves one signed step. Reset changes only the selected page's coordinates.
Every public native core routine uses CALL([d2,d3,a2,a3],16). Heights are five
u16 values in caller-owned memory. No function retains its pointer.

## Integer transfer

For inputx∈[0,1023], let t=4x, k=min(3,floor(t/1023)), u=t−1023k. Output is
`Y[k] + floor(u * (Y[k+1]−Y[k]) / 1023)`. Floor interpolation with default
integer heights preserves every input exactly. It is nondecreasing and bounded
by B/W for every canonical state. This is a piecewise linear transfer, not a
spline. Graph markers use exact Y values at the fractional quarter positions;
their rounded display indices are0,64,128,191,255.

## Legacy resolution and first use

A valid canonical word ignores legacy H/M/L. Otherwise, a valid old0xa5d word
supplies its10-bit endpoints; any other word starts with B0/W1023. If any legacy
H/M/L value is outside−7..7, all consumers use full canonical neutral, including
B/W. For valid legacy H/M/L:

- M=512+32×middle.
- S=min(256+16×low,M); H=max(768+16×high,M).
- Quantize old B/W to nearest six-bit height, ties toward the lower height.
  Values≥1008 map1023; otherwise use min(992,16×floor((value+7)/16)).
- Project B down to S and W up to H if necessary.

Quantization alone can change an endpoint by15 codes near the final31-code
interval; neighbor projection can change it more. This migration intentionally
changes former native inner positions/curves. It does not claim old-image
pixel equivalence.

The early source publication copies words opaquely. Only after an acquisition
qualifies a COLOR1–3 profile, an unrecognized source tag becomes old-neutral
`0xa5dffc00`, allowing the job's captured H/M/L tuple to resolve consistently.
Non-COLOR owners remain zero and therefore retain stock processing. The first
actual edit commits canonical state; migration itself does not rewrite settings.

`penf_tone_points_probe.py` checks48 canonical states,720 selected-axis edits,
all1024 input samples per state, and44 legacy/invalid-state cases with actual
MN103 execution and no function models. The default state is also checked at
all1024 inputs by the host regression.
