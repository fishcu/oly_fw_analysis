# PEN-F electronic aperture-ring input

The [source builder](../../patches/aperture-ring/README.md) targets exact
PEN-F 3.1/build3101. It supports a standalone main and a variant compatible
with the repository's HSL alpha-20261017 release.

## Lens input and body handoff

Advertised lens capability bit `80` enables the optional ring field on compatible
`C1 80` ordinary or `81 E3` Panasonic-private status requests. Option `01` adds
the little-endian ring word; requests with IS-extra option `08` retain the
exclusion. Parsing consumes the word before the later focus/pulse fields.
Compatible requests are extended at the shared dispatcher and automatic poller.

An aligned publication word carries high-half magic `5247`. Missing publication,
ring A/auto `8000`, disconnected/non-capable lenses and modes outside native
A/M modes 4/6 retain the stock body input. Discovery reset clears publication.
The original body aperture point is never overwritten, preserving dial control
when the lens ring returns to A/auto. No manufacturer whitelist or aperture
lookup table is added.

## Official limits and the f/1.7 endpoint

Original cache producer `6015a895` copies these words:

| Runtime RAM | Meaning and source |
| --- | --- |
| `6184d704` | Live effective aperture from lens status, device `+10` |
| `6184d706` | Official minimum from selected zoom row `+2` |
| `6184d708` | Official maximum from selected zoom row `+4` |

Firmware diagnostics call these fields `av_effect` and `av_official[0/1]`.
Ring selection uses the signed official minimum/maximum and rejects a reversed
range. Stock AE retains its remaining zoom/mode policy.

For the 15 mm, ring word `0187`, official minimum `0188` and effective minimum
`0194` differ slightly. Clamping to effective Av produces `0194`; stock formatter
`605c596d` then selects the ordinary f/1.8 label. Clamping to the official
minimum produces `0188`, matching the special wide-open endpoint and displaying
f/1.7. The next ring word `01b2` continues to show f/1.8. These values are probe
fixtures and observed lens data, not constants in the patch's selection policy.

## Hooks and loaded code

| Function | Standalone / combined entry site |
| --- | --- |
| Automatic request options | `60171c16` |
| Shared request dispatch | `60175f48` |
| Status parser | `60165276` |
| AE aperture snapshot | `605ddb6c` |
| Discovery reset | `60158fee` |

Standalone helpers start at `601caa50`; publication is `601cafb0`, with uncached
alias `a01cafb0`. They lie in loaded section 1, `60142800..601cb000`.
Those placements overlap the existing HSL ORF/Wi-Fi code, so the combined
profile splits helpers into reclaimed ORF slots and moves publication to
`601caa40`. The original ORF helper group moves to section-8 padding starting
`6115b060`, with a section-1 readiness guard checking loaded-mask bit `80`.
Every non-ORF HSL modification and the OSD are checked against the original release.

The linker scripts assert section bounds and exact hook sizes. Manifests pin
the original bytes, compiled sections, whole main and encoded updates. Builds
reject mismatches and preserve the exact original restore components.

## Evidence

The contributor reports A/M ring control and DOF preview, and confirms HSL and
aperture working together on the PEN-F. Correct f/1.7 values are camera-confirmed
on 15 mm, 10–25 mm and 25–50 mm lenses. Earlier displayed-value tests also passed
on 12 mm, 42.5 mm and 200 mm. Detailed exposure/iris measurements and separate
RAW/preview test records were not supplied; broad lens compatibility and recovery
are not inferred from these observations.

The [native probe](../../tools/aperture_ring_probe.py) executes the original
snapshot window `605ddb5f..605ddb78`, cache producer `6015a895` and formatter
`605c596d`, with explicit synthetic RAM and no successful service stubs.
It checks 18 snapshot controls, 24 signed/zoom-dependent cache cases and
the stock display's f/1.7/f/1.8 distinction. The
[HSL probe](../../tools/aperture_ring_hsl_probe.py) checks 15 guard/relocation
cases against the original HSL helpers. The metadata-copy function is a stop
boundary, not a modeled successful transfer. Cross-core scheduling, physical
cache/DMA, the lens bus and image-processing hardware remain outside these probes.
