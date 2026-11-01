# PEN-F endpoint transport candidate

This offline candidate joins the verified tone adapter to committed settings, acquired owners and image jobs. It composes over the exact released HSL main payload. This document covers the transport unit; the [feature README](../../../patches/tone/pen-f/README.md) describes the composed editor, graph and container build. No camera or nonvolatile storage is accessed by these probes.

## Ownership and native hooks

One aligned u32 carries each endpoint pair: tag `0xa5d` in bits20..31, requested black in bits0..9 and requested white in bits10..19. The late reader treats an invalid tag as neutral. The neutral tagged word is `0xa5dffc00`; zero-initialized memory is also neutral. Requested values remain stable in storage while processing independently clamps black to the final shadow height and white to the final highlight height.

Native ACTIVE part1 IDs967,970,973 hold COLOR1,2,3 respectively. The existing HSL publisher now ends by copying those three complete words into a 12-byte source in section2. It uses the native ACTIVE getter, not LIVE or staged settings. Existing HSL boot, commit and context0 refresh hooks continue to own publication; context1 staging remains excluded. The probe executes the publisher and native bank APIs, not a complete boot or flash commit.

The existing 40 large capture owners and five compact owners have one corresponding endpoint word each. The existing HSL owner lookup accepts only exact pool slot bases and their established cached/uncached aliases. The tone extension maps that qualified HSL row to its endpoint row. Each acquisition replaces the complete word from the captured profile; invalid profile values replace it with zero. No owner padding, extra ring, or UI pointer is used.

| Boundary | Composed behavior |
|---|---|
| Capture acquisition60253c7f | Existing HSL source helper also copies the selected endpoint word. |
| Compact acquisition605576ec | Same source helper, selecting compact owner profile byte381. |
| Preview conversion605205f9 | Existing HSL job helper appends the acquired endpoint word. |
| Recording conversion605323f8 | Same job helper and preserved displaced instructions. |
| Compact conversion6055a28a | Existing successful-call continuation appends the endpoint word; failed calls leave the destination unchanged. |
| Selected RAW edit60af2f56 | COLOR acquisition uses the common helper; non-COLOR reuse clears both HSL and endpoint rows. |

All job writes come from the acquired owner rather than the current source. Invalid owner addresses write a zero endpoint word. The destination is job+14944, following the unchanged24-byte HSL trailer. The constructor allocation argument becomes14948; its final native memset covers40bytes beginning at14908, including all HSL and endpoint bytes. This remains within the established16KiB allocation class, but a full native allocator/constructor execution is not claimed: the saved boot/heap checkpoint required by that older probe is absent.

## Placement and residency

`penf_tone_candidate.py` rebuilds every released HSL assembly group, checks its exact size and before/after hashes, and checks the full reference main hash `850936e7fa5d9c089f054385dd0bbcc310b64285c784a5da3ab347173730d12e`. The released recipe is unchanged. A separate manifest describes each tone-relative edit and rejects overlapping spans. It does not save a firmware container.

The early publisher/source and stock-builder fallback occupy the measured section2 gap beginning60427e78. The job gate occupies60427fa8. Small section3 bridges use6069b580 and6069b7ac; the late code and45-word row table begin6115b060 in section8. The RAW extension stays within the measured112-byte range at60fdc750. Exact linked sizes and hashes are emitted into `candidate/manifest.json` rather than assumed from source length.

All calls from early hooks into section8 test loaded-mask bit0x80 at `a1c58404`. If section8 is absent, acquisition does not touch its rows, conversion writes zero, and tone processing follows the original builder. The probe removes the entire late code/data range from the emulator map for these tests. Publication still works because its code and three-word source remain in section2. This guard does not establish that arbitrary runtime reloads are impossible; reload resets embedded rows, so a fresh acquisition is required afterwards.

## Processing entry

The candidate replaces the first five bytes of ordinary builder604f7c76 with a jump to the early residency gate. Its stock fallback replays exactly the displaced `mov(4,a0),d1` and `mov a0,d3`, then resumes604f7c7b with the original CALL frame. The sole found direct caller is604f85ea. The alternative604f7d22 calls selector604f7ae0 and either stores a selected table pointer or calls identity helper604f7c66; it does not enter604f7c76. The probe checks both alternative outcomes remain byte-identical.

The tagged-job adapter retains exact header, callback, record-alignment and parent checks from [TONE_INTEGRATION.md](TONE_INTEGRATION.md). Neutral, invalid, wrong-producer and bypass cases retain native output and return values. A non-null override descriptor may contain a null LUT pointer: the adapter now returns to the original builder before reading samples, preserving the native neutral-inner null-pointer result. The selected-base early-return path also remains stock. Unsupported custom LUT shapes retain the native result after full validation; the feature does not reinterpret them as endpoint-capable curves.

## Reproduction and limits

Run from the worktree with its pinned analysis/toolchain inputs:

```
python3 tools/penf_tone_transport_probe.py /tmp/penf-tone-transport-audit
python3 -m unittest discover -s tests -p 'test_penf_tone*.py' -v
```

The audit executes all45 native owner acquisitions, invalid-owner and invalid-profile reuse, nine native bank store/load/publication cycles, nonzero HSL preservation, native capture/compact acquisition and preview/recording hook context comparisons, selected RAW COLOR/neutral/unloaded paths, and16 operation-record pipelines through the actual ordinary outer builder and native warm-cache upload. It also executes the real constructor allocation prefix and relocated native memset with canaries. The compact proof starts at the actual post-call continuation and injects the prior call's result; it does not model or claim successful execution of the entire displaced compact setter. No hook or processing function is modeled; native upload retains the previously documented two single-thread cache-lock models.

Body endpoint input, page/default/reset routing, profile-switch UI cleanup and dynamic graph painting remain to be integrated. Portable external backup/export and ORF metadata extensions are outside this first feature and are not promised to preserve endpoint settings. Native bank roundtrips are verified; persistence after power cycling, screen appearance, live view and saved JPEG behavior require separate hardware qualification.

The placed native editor request/page unit is documented in [TONE_EDITOR.md](TONE_EDITOR.md).
