# OM-3 COLOR builder and per-image parameters

Model OM-3, displayed firmware 1.1, internal build 1100. Update file SHA-256
`8c133084414533159f587bf46bfb4152714c4074312a47c8d8503e33d605696d`; decoded main
SHA-256 `5e8d376e9111a44ac0352f26030d7c1b17026d42c45f3600cfa02a0e8c5b7d59`.
Runtime addresses. Evidence: static disassembly, isolated native execution of
stock slices on synthetic memory, and OM-Emu with a synthetic job. OM-Emu has no
ISP, and its simulated shutter does not reach the builder. No physical OM-3 test.

## Selector and builder

The selector at `60518573` is reached with an operation record `R` in `a0`
(entered through a register-saving `call`). `J = (4,R)` is the job; `(12,R)` is
the output; `(60,R)` holds flags. When `J+8..+11` encodes request type 11, it
calls the COLOR builder:

```text
60518615: call 60518381   ; a1 = J + 1739 (twelve signed saturation bytes)
6051861a: mov (60,a2),d0  ; resume
6051861d: btst 2,d0
```

The builder writes twelve 24-byte output records starting at `(12,R)+854`,
one per sector. The PEN-F HSL extension's technique applies: let the stock
builder run, then write hue and lightness halfwords at record offsets +0 and +4
using the PEN-F scales (hue ±1000 per step, lightness 25/50/… table). A
synthetic job through the real selector in OM-Emu confirms the record layout
and that only those halfwords change. What the OM-3 ISP does with them is
unverified.

## From settings to job

These stock slices are individually established:

```text
setting record f6ea (effective, IDs 916–927)
  → snapshot fill 603e7e3e: twelve halfwords at P+37694
  → conversion near 6054fd29: low bytes at context+252
  → job preparation 604b707d: copy of twelve bytes to P+1739 (604b71ff)
     where P = *(owner+10276) + 5408
  → selector 60518573 → builder 60518381
```

Executed in sequence on shared synthetic memory, they carry the saturation
bytes from the effective record to the builder input. Static tracing of one job-start route also binds the submitted descriptor’s `+4` pointer to this same `P` by construction. This establishes the pointer relationship on that route, not the identity or ordering of live runtime objects.

`P` is a shared scratch descriptor. Five accessor variants (`604b6092`,
`604b60a6`, `604b60ba`, `604b60ce`, `604b6108`) compute the same `P` but run
different initialisers. Only `604b707d` (via `604b6092`) writes `+1739`. The
traced job start at `604c848c` uses `604b60ba`, whose initialiser writes a
type-5 descriptor and does not touch `+1739`. Which capture path fills the
type-11 payload before submission is not established.

## Consequences for an extension

Saturation reaches the builder as an image-owned copy. An extension that reads
H/L from live settings at build time is simpler but not image-owned: an image
still in processing can take later edits. The same applies to in-camera RAW
development. PEN-F solved this with capture-pool rows and several converter
hooks (see [PEN-F per-image parameters](../pen-f/CAPTURE_PARAMETERS.md)); the
OM-3 equivalents have not been mapped.

A builder hook should also check the picture mode unless it is shown that
type-11 requests occur only for COLOR profiles. Setting 901 selects COLOR1–4 as
54, 55, 56 and 64, so a linear mapping of 901 would skip COLOR4.
