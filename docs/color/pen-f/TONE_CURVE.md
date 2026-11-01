# PEN-F tone curve work

This is historical native-math and endpoint-only groundwork. The current feature
uses equal-quarter points and a shared canonical state, documented in
[TONE_POINTS.md](TONE_POINTS.md) and the [feature README](../../../patches/tone/pen-f/README.md).
The old endpoint/signal kernels below remain isolated probes and are not linked
into the current candidate.

## Reproduce the native baseline

Provide the exact stock main block at `analysis/penf_3.1/00_0100_403a0020.decoded.bin` and the strict GNU engine at `toolchains/mn103-gnu-build/penf-mn103`. The probe rejects a different firmware hash.

```sh
python3 tools/penf_tone_probe.py --out generated/tone-native-baseline
python3 -m unittest discover -s tests -p test_penf_tone_probe.py -v
```

Run these probes with assertions enabled. Optimized Python execution with `-O`, `-OO`, or `PYTHONOPTIMIZE` is rejected at module import, including when another script imports the native helpers. The output directory must be new. `audit.json` records every one of the 256 LUT values for each case. It records firmware, engine, and execution-source SHA-256 hashes. The probe emits no installable firmware and performs no camera I/O.

## Stock native evidence

`NativeToneParameters` holds five opaque signed 16-bit slots in ten bytes. These slots have not been established as the five desired UI points.

| Native entry | Input | Call frame |
| --- | --- | --- |
| `0x604bddcc` | `a0` points to ten input bytes. `a1` points to a 16-byte coefficient buffer. | `CALL([],16)` |
| `0x604be08d` | `a0` points to 256 writable uint16 LUT entries. `a1` points to coefficients. `d0` is zero. | `CALL([d2,d3,a2,a3],16)` |

The identity table at `0x605fdd38` has 256 uint16 values between 0 and 1023. Its SHA-256 is `8ef45d7de8746b48e7b04fe690d045885cde1c1e62d03fefd3304f50281a538a`.

The baseline executes the original conversion and application routines through `ProbeState`. It retains native memory between calls with `reenter`. Both calls must return to the synthetic caller with the stack pointer and `d2`, `d3`, `a2`, and `a3` restored. Buffer and stack canaries must survive. The stack checks inspect two 32-byte sentinels at the initial stack pointer minus `0x1000` and plus `64`. These sentinels detect corruption at those locations. They do not establish exhaustive confinement of writes within the mapped stack. Conversion must preserve its input and the identity LUT. Application must preserve both raw input and coefficients. Unknown instructions and unmapped memory accesses retain the strict engine's stop behavior. No native function is replaced by a host model.

All-zero inputs produce 16 zero coefficient bytes. Forcing the native overlay with these coefficients changes eight identity samples by one unit. The changed indices are 43, 44, 45, 126, 127, 213, 214, and 215. The forced-neutral LUT hash is `1d3a4cf6980ceffd36027a9b8feef1c4401a97bcf4f75958de6ef3b1f5860e87`. The probe executes the stock gate at `0x604bdd21` directly for every case. The gate returns zero for five zero slots and one for every nonzero tested combination. Exact neutral behavior therefore depends on retaining that gate.

The probe also varies each opaque slot independently through -7 and +7. It tests all 27 combinations of -7, 0, and +7 in the last three slots with the first two slots zero. These are native input stress values, not verified legal UI settings. The nonzero tested cases change interior LUT values. The all-zero mixed case follows the native gate and retains the identity LUT. Every tested case retains endpoint values 0 and 1023. These results establish fixed endpoints for the tested inputs. They do not prove the behavior of all possible signed 16-bit slot combinations.

## Probe the endpoint kernel

`patches/tone/pen-f/src/endpoints.s` is a 140-byte MN103 kernel. This isolated probe links it at synthetic test address `0x19080000`. This address is not a firmware placement. The host oracle is `endpoint_oracle` in `tools/penf_tone_endpoints.py`.

```sh
python3 tools/penf_tone_endpoints.py --out generated/tone-endpoints \
  --black 50 --white 950 --shadow-index 64 --highlight-index 192
python3 -m unittest discover -s tests -p 'test_penf_tone*.py' -v
```

Both anchor indices are mandatory. Values 64 and 192 in this command are synthetic test anchors. They have not been established as the stock editor's shadow and highlight positions.

The kernel edits a 256-entry uint16 LUT in place. `a0` points to the writable LUT. `a1` points to four uint16 values in order, black height, white height, shadow index, and highlight index. Call with `CALL([d2,d3,a2,a3],16)`. The return value in `d0` is zero. The kernel restores the stack pointer and the four saved registers. The caller must supply a validated LUT and parameter block. Native integration must enforce this same contract before calling.

The source LUT must be monotone, bounded by 0 and 1023, with endpoints exactly 0 and 1023. Anchor indices satisfy `0 <= shadow_index < highlight_index < 256`. Black height `B` must satisfy `0 <= B <= C[shadow_index]`. White height `W` must satisfy `C[highlight_index] <= W <= 1023`. Host validation rejects invalid inputs before native execution.

Let `S = C[shadow_index]` and `H = C[highlight_index]`. The black tail uses `B + round(C[i] * (S - B) / S)`. The white tail uses `H + round((C[i] - H) * (W - H) / (1023 - H))`. Rounding is nearest with half ties upward. Every sample from the shadow index through the highlight index remains byte-for-byte unchanged. The multiplication and rounding addition are at most `1023 * 1023 + 511 = 1047040`, within signed 32-bit arithmetic.

Neutral endpoints, black 0 and white 1023, skip both tail loops and preserve every source byte. A shadow anchor of zero requires black zero and skips that tail. A highlight anchor of 1023 requires white 1023 and skips that tail. This prevents division by zero.

The native differential tests compare all 256 values with the host oracle. They cover explicit synthetic anchor pairs 32 and 208, 64 and 192, 0 and 255, and 1 and 254. They cover neutral endpoints, endpoint limits, flat curves, degenerate anchor heights, half ties, 16 deterministic monotone tables, and all 27 mixed stock native input combinations. Tests require exact endpoint heights, monotonicity, unchanged interior samples, unchanged parameter bytes, and preserved registers, stack, and canaries. The source is deliberately edited in place. The host source sequence remains unchanged.

Each CLI run creates a new report directory. The endpoint report includes the complete input and output LUTs, assembly, raw kernel bytes, and source, compiler-tool, kernel, engine, and firmware hashes. The GNU simulator source hashes are recorded when that source tree is available. These artifacts are offline probe inputs and evidence. They are not an installable firmware container.

## Integration gates remain open

The subsequent [ordinary tone adapter](TONE_INTEGRATION.md) executes native signal bounds, a job-word reader, the actual ordinary call-site trampoline, and native upload in offline fixtures. It still does not provide a body control or persistent owner transport.

The body editor still needs endpoint selection, labels, input routing, drawing, and refresh. Native shadow and highlight anchor indices need evidence before a tail mapping can use them. No property ID, storage offset, or firmware hook is assigned by this baseline.

Persistent settings need a proven versioned representation and reset behavior. Per-image copies must preserve the selected endpoints through capture, compact slots, queued jobs, and RAW development. LUT changes must use a writable buffer owned by that image. The stock output pointer at `output+0x1230` and 512-byte scratch at `output+0x1234` are evidence to trace, not authorization to reuse a buffer without ownership checks.

The strict probe establishes instruction execution and memory effects. It does not execute ISP pixels, display the body UI, perform a full capture, or qualify camera hardware. No camera was connected or written by this work.
