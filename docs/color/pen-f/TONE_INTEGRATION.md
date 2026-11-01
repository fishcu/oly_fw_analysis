# Native five-point image adapter

The composed ordinary COLOR builder applies the shared equal-quarter transfer
after native selected-base and legacy-only processing. The state and migration
rules are in [TONE_POINTS.md](TONE_POINTS.md). The previous signal-bracketing and
endpoint-only kernels remain historical probes; they are not linked into this
candidate.

## Boundary and ownership

The production hook replaces five bytes at604f7c76 and preserves its CALL frame.
The early stock fallback replays those bytes and resumes604f7c7b. The ordinary
outer604f8543 retains its native bypass decisions. Separate604f7d22 does not
enter this builder and remains unchanged.

Before reading job+14944, `tone_job_word` requires exact COLOR header000b0000,
callback604c4011, an exact one-of16 operation-record pointer, and matching
parent job. It accepts canonical0xb and migration0xa5d tags. Invalid producer or
unrecognized tag tails stock. The producer independently qualifies COLOR1–3.

The selected source must be nonnull, monotone, bounded0..1023, with exact0/1023
endpoints; all256 samples are checked. Unsupported sources and native selection
early returns follow stock. The adapter owns a68-byte local frame. It copies
native raw slots as `(raw0,raw1,0,0,0)` and converts them into private coefficients.
Original request raw values and context coefficients remain unchanged.

Native604bdd21 gates that legacy-only tuple. When nonzero, the full native
convert/apply sequence runs, including its27-sample reconstruction and variant
bit. Isolating only the first spline would drop part of raw1's native behavior.
When both legacy slots are zero the overlay is skipped; forcing a zero overlay
would change eight identity samples by one code.

The resolved five-point transfer then maps all256 resulting values. A neutral
canonical state skips this final mapping but still selects/rebuilds the base,
so reset cannot retain a previously edited LUT. Any needed writable copy belongs
to output+4660, with pointer output+4656. Shared source memory is unchanged.
All supported tagged requests rebuild irrespective of the stock change mask;
no padding, retained cache state or forged dirty flag is introduced.

## Verification

`penf_tone_integration_probe.py` compares the adapter with an independent shared
state oracle applied to a fresh native legacy-only baseline. Coverage includes
identity/square/square-root inputs, selected native bases, both variants,
zero/nonzero legacy values, migration tuples, all16 records, null/unsupported
sources, malformed producer relationships and outer bypasses.

The retained-request regression executes604b3034 and604b2d78, changes all-five
canonical state twice, then resets to neutral while the native mask contains no
tone-change bits. It checks24 sequential transitions over zero/nonzero captured
H/M/L, selected/override bases and both variants, including the placed entry.
Neutral state equals a fresh native legacy-only build in LUT, pointer and return.
These builder cases model no functions.

Native upload fixtures check every expanded32-bit LUT entry in both banks with
a warm tag and dirty0. Only the two established cache-lock helpers use a
single-thread model. This verifies the upload boundary, not ISP pixel execution.
The source/owner/job lifecycle is in [TONE_TRANSPORT.md](TONE_TRANSPORT.md).
