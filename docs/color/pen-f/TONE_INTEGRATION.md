# PEN-F ordinary tone adapter

This offline unit connects the endpoint kernel to the native ordinary COLOR tone builder. It does not add camera controls, persistent endpoint acquisition, or an installable image.

The user can eventually move black and white vertically while the native shadow, middle, and highlight heights remain unchanged. This adapter preserves the entire final LUT interval around those inner controls. It clamps each requested endpoint independently when an inner control reduces the available range.

## Native boundary

The five-byte call at `0x604f85ea` invokes the ordinary builder `0x604f7c76`. The probe checks those original bytes before substituting a jump to `tone_ordinary_call`. That trampoline invokes `tone_native_builder` with the original saved-register mask and 28-byte frame, then resumes at `0x604f85ef`. The ordinary outer builder `0x604f8543` still makes its native bypass decision. The separate paths through `0x604f7d22` remain outside this unit.

The new builder reads an endpoint word only for the exact ordinary COLOR request header `0x000b0000` at request+8. It requires callback `0x604c4011`, an exact pointer to one of the 16 native 52-byte operation records, and the matching parent job. These checks establish the native layout relationship before reading job+14944. They are not general validation of an arbitrary pointer.

A word is valid when its upper 12 bits equal `0xa5d`. Bits 0..9 hold black and bits 10..19 hold white. Zero and every other tag are invalid. Invalid words and the valid neutral pair 0/1023 tail-call the unchanged stock builder. The producer must qualify COLOR1, COLOR2, or COLOR3 when it acquires the image. That producer is not implemented in this unit.

For a nonneutral word, the adapter retains stock base selection and the stock inner-overlay gate. A selection that requests an early native return retains that return. Endpoint-only edits run even when all five native raw fields are zero. The original raw fields and coefficient record remain unchanged.

## Signal bounds and lifetime

The native pre-control table contains 27 values at indices 0, 10, through 250, and 255. These values follow the first native contrast spline. The inner transfer coordinates 130 and 832 bracket the shadow and highlight controls. They are not fixed indices in a 256-entry LUT.

`tone_signal_bounds` repeats that prepass through native spline functions `0x604bdea7` and `0x604bdfe1`. Its temporary knots and coefficients belong to its stack frame. It rejects out-of-range or decreasing samples and missing crossings. The returned lower shadow neighbor and upper highlight neighbor stay in the builder's private stack until the final LUT is complete. No code reads a released native frame or an undocumented context field.

Two designs were compared. A hook at `0x604be107` could copy the native samples, but it would need a caller-frame contract and would not execute for neutral inner controls. The selected-base adapter gives every supported request the same synchronous prepass and keeps the ownership boundary explicit. This follows the Model the Domain principle by representing the endpoint pair and its bounds as one local parameter block.

The prepass deliberately retains whole 27-knot brackets. A steep source can produce shadow index zero, in which case black clamps to zero. Narrower inferred bounds would claim precision not established by the native interpolation evidence.

## Validation and output ownership

Before it calls the endpoint kernel, the adapter checks all 256 final samples. Every value must be at most 1023, samples must be monotone, and endpoints must equal 0 and 1023. The shadow index must be lower than the highlight index. Unsupported values leave the stock result and selected pointer unchanged.

Black becomes `min(requested_black, final_shadow_height)`. White becomes `max(requested_white, final_highlight_height)`. The two clamps are independent. If both effective endpoints are neutral, the adapter keeps the native pointer and bytes. Otherwise it copies a shared curve into output+4660 before editing, or reuses that scratch when the native builder already owns it. The pointer at output+4656 then names that context-owned scratch.

The future UI must distinguish requested strength from effective height. A seven-step editor cannot round an effective clamped height back into a different request. This unit stores the requested 10-bit coordinates and calculates the effective endpoints per curve. The graph must show those effective values.

## Reproduction and evidence

Run the audit with the exact firmware and toolchain used by the native baseline.

```sh
python3 tools/penf_tone_integration_probe.py --out generated/tone-integration
python3 -m unittest discover -s tests -p 'test_penf_tone*.py' -v
```

The output directory must be new. The assembly is linked at synthetic address `0x19080000`. The audit records the compiled size, native symbols, tool hashes, firmware and engine hashes, complete pre-control samples, signal bounds, output hashes, and ABI checks. It creates no firmware container.

The audit compares 27 source/contrast fixtures against native pre-control samples. Identity, square, and square-root curves are synthetic input fixtures. The first two raw slots use -7, 0, and 7 as stress values, not established UI settings. It compares endpoint output with the independent integer oracle for all 27 tested inner-control triples and each of the 16 operation records. Additional cases execute native-selected bases, variant mode, the actual ordinary call-site trampoline, unsupported sources, invalid job relationships, and native bypasses.

Four native uploader calls cover both banks with the same cache tag and dirty zero. Each call checks all 256 expanded 32-bit tone entries. The two cache-lock helpers use the existing single-thread model. These are separate bounded upload fixtures. They do not simulate concurrent jobs, cache scheduling, ISP pixels, or a camera.

## Remaining integration

The packed endpoint source, 45 owner snapshots, constructor extension, acquisition and conversion hooks, and native reset scopes remain required. External backup and ORF metadata support are outside this first feature and do not preserve endpoint settings through new extension records. The body page cycle, getter, setter, default action, and graph callback also remain required. No firmware cavity or loaded-section lifetime is assigned by this synthetic unit.
