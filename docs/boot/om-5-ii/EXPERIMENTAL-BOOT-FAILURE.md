# OM-5 Mark II experimental patch boot failure

Model E148, displayed firmware 1.1, internal build 1100. The official stock
update file hashes SHA-256
`9de5d77e1d290fa2ed4ebc7d75cee0ed490befbc89566722467d1d421d66d637`.
This page records one physical incident involving the separate experimental
[HSL/WB branch](https://github.com/xulfr/oly_fw_analysis/tree/codex/om5ii-hsl).
It is not a recovery procedure or evidence that another modified image boots.

## Observed incident, 4 November 2026

The owner reports that installing the package built from commit `1bd6276`
appeared to run. The camera then cycled through a black screen and repeated
lens autofocus movement rather than reaching the shooting display. The first
attempt to reflash complete official stock firmware showed a sustained red
light. After removing the battery, a second stock reflash completed and the
camera booted. There are no camera logs or flash readback. The failed package
SHA-256 is
`35f0caac4b70f1e59e3d5311fdf74a8c021d720755a7441796b080707b79d434`.
**Do not install that build or a package derived from it.** This one recovery
does not establish a dependable recovery route.

## Offline observations

The hash-matched failed file and official stock file both parse and reconstruct
through the repository's container parser. Stock contains components `0x100`,
`0x101`, `0x106`, `0x10e`, `0x102`; the failed package contains main `0x100`
and OSD `0x101`. Package checksum and round-trip success establish file
structure, not what was written or loaded by the camera.

The failed main differs in expanded compressed sections 6 and 7, and its OSD
component also differs. Section 7 contains `FIRMUP_CLI`, the in-main card
updater. The E148 startup trace loads sections in order 1, 8, 2, 3, 4, 5, 6,
7, 9, 10 and sends decompression work through an off-CPU mailbox. The host
LZ4 decoder accepts both changed streams; the camera's decoder and saved-state
boot path have not been observed. OM-Emu starts after much of this work and
does not run the E148 section loader. Its earlier UI and JPEG passes therefore
did not test the failure.

An exact-image offline audit matched the historical source files at `1bd6276`
and all 86 recorded edit ranges to the failed main's 5,306 changed expanded
bytes. The analysis reports 799 changed bytes in section 6 and 876 in section
7, plus changes in OSD `0x101`. A reduced *non-installable* JSON recipe retains
only three Live ND edits and proves its hypothetical main leaves both entire
stored and expanded sections 6 and 7 equal to stock, with stock OSD. It is not
a repaired HSL build or a camera result. The detailed [fork incident review](https://github.com/xulfr/oly_fw_analysis/blob/codex/om5ii-hsl/patches/hsl/om-5-ii/BRICK-RISK.md)
contains the earlier static risk assessment and its post-incident correction.

## What remains unknown

The black-screen/autofocus cycle is consistent with repeated initialization,
but it does not identify a reset cause or faulting instruction. Changed section
6/7 decoding, an early hook or saved-setting path, OSD loading, package
composition, and incomplete writing remain separate hypotheses. The successful
second stock reflash does not show whether the failed image's section 7 loaded
or whether the camera used an earlier updater route.

Useful next evidence is a reset-to-live-view loader trace, section-load status,
diagnostic log or flash readback from a controlled service or spare-body setup.
An offline full-container comparison can isolate composition, but reproducing
the same failed main and OSD in all five components would not make it safe.
No further physical test of the failing build is proposed here.
