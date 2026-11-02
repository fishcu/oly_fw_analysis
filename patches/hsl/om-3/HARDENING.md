# WB/HSL hardening experiments

These checks execute OM-3 build 1100 instructions in private emulator copies.
They increase confidence in bounded software behaviour. They do not establish
camera boot safety, physical NAND atomicity, cache coherence, ISP output, or a
complete shutter-to-JPEG path. The patch remains camera-untested and a draft.

## Corrected ABI bugs

MN103 CALL uses the caller's SP+0 as a return-address slot. Values kept there
across another call are overwritten. The original extension did this in:

- WB commit: the stock commit's return value was replaced by a later helper's
  return address. It now occupies SP+4 in the wrapper's local frame.
- HSL display and Delete-action wrappers: saved D1 was overwritten.
- HSL builder wrapper: saved builder D0 was overwritten.
- HSL value label: saved D3 was overwritten while obtaining the profile.

The wrappers now reserve SP+0 and adjust their temporary frames/offsets. The
label's output offset follows the enlarged temporary frame. Save blocks that
finish before a call, and blocks without nested calls, were left unchanged.

The WB return-value and HSL display/Delete/builder ABI tests fail against the
previous recorded image and pass against the hardened image. The HSL label is
covered by inspection and the native GUI regression, rather than a separate
isolated ABI test. The tests check the synthetic caller's SP and callee-saved
registers through OM-Emu's call contract, and explicit expected volatile values.
Native GUI/WB/HSL integration also passes on the corrected image.

## Failed section reads and corrupted WB code

The native section loader sets section 4's loaded bit even when its underlying
read reports an error. The previous WB dispatcher could therefore jump into
missing or partial code. Injecting a failed read and a 16-byte partial WB-body
copy reproduced native faults.

The dispatcher now checks all 492 bytes of the WB body, including alignment
padding, through uncached alias `a0a8f100`. The linker records 123 words and
XOR `764232cb`; the probe independently recomputes this value from the pinned
candidate. It checks the body even when the loaded bit was already set. On a
mismatch, it clears that bit and continues through the stock commit prologue.
The ABI and ordinary WB recall remain intact.

Failed reads, partial copies, an already-marked-loaded invalid body, and a
single-bit change at the end of the body all pass the rejection tests. Storage
and the loader's diagnostic sink are explicit models. This is an accidental
corruption check, not cryptographic integrity, and it does not recover other
section data or establish physical instruction/data cache coherence. The
shared builder continues to verify exact cryptographic fingerprints separately.

## Interrupted record states and write footprint

The lifecycle probe injects all six boundaries around a five-write save:
old record, checksum invalidation, each of three payload words, and final
checksum. It performs a simulated power cycle, checks that the guard is reset,
and selects the destination profile. The old and complete new records recall
correctly; each incomplete record inherits the current WB. These are injected
RAM record states followed by a clean simulated power cycle, not power cuts
during actual NAND operations.

The recorded 1,000-step deterministic profile-switch run checks each recalled configuration and
the cleared recursion guard. A before/after dump of all 2,256 part-1 alternate
cells verifies that no cell outside IDs 904–923 changed. This checks this
storage surface; it is not a watchpoint over all camera RAM or an interleaving
proof for concurrent CPU tasks.

An additional attempt submitted all eight three-bit creative-switch input
states through the native producer. The picture mode remained COLOR4 in this
emulator state. This produced no qualifying transition evidence; it is not
reported as creative-dial coverage. The physical path remains open.

## Capture timing: a remaining limitation

The lifecycle probe sets COLOR1 to CWB 4000 K with A/B -2 and G/M +2, copies
its compact parameters, then selects COLOR2 at 5000 K with A/B -1 and G/M +1.
It enters unmodified processing slice `60457c44..60457c80` with the earlier
4000 K snapshot at context+37642. The result is:

| Processing destination | Observed value |
| --- | --- |
| context+5422 | 4000 K, from the earlier snapshot |
| context+37734 | A/B -1, from the current live record |
| context+37736 | G/M +1, from the current live record |

This demonstrates the mixed-input behaviour of that native branch under
controlled scheduling. It does not establish whether a real queued capture
can reach the branch after a profile edit; that ordering remains open. The
compact WB-copy integration test alone was insufficient to exclude this issue.

A complete fix needs a verified image-owned tint source and its lifetime across
capture preparation, processing, RAW development and metadata. Writing an
assumed spare field or suppressing profile changes using an untraced busy flag
would add unqualified ownership assumptions. The current patch therefore does
not claim image-owned WB or queued/burst correctness. The next capture task is
to bind the snapshot owner and processing object on live capture routes, then
carry or select the captured correction pair on every relevant WB branch.

## Reproduce

Build the recorded decoded image with `tools/oly_patch.py`, then run:

```sh
python3 tools/om3_wb_emulator_probe.py --emulator /path/to/om-emu \
  --node /path/to/node --image generated/om3-hsl/decoded/0100.bin
python3 tools/om3_wb_fault_probe.py --emulator /path/to/om-emu \
  --node /path/to/node --image generated/om3-hsl/decoded/0100.bin
python3 tools/om3_wb_lifecycle_probe.py --emulator /path/to/om-emu \
  --node /path/to/node --image generated/om3-hsl/decoded/0100.bin --steps 1000
```

The latter two reuse the integration probe's private source copy and exact
image checks. Fault tests model native commit completion for the ABI cases,
and section reads/diagnostics for loader cases. Lifecycle tests use actual
native UI writes and alternate-cell access; capture probes use explicit scratch
objects and bounded stops. None contacts a camera.

Factory reset, custom-mode assignment/save-policy variants, settings backup,
physical creative-dial operation, concurrent section reloads, real boot and
ISP/JPEG/RAW output remain unqualified. Existing native custom-bank recall
and default C1 discard policy are covered by the integration suite.
