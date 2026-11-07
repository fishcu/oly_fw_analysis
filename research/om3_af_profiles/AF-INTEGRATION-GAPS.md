# AF profile extension: integration gaps investigated

OM-3 firmware 1.1, 31 October 2026. **Part of the result-reset gap is now verified across nested firmware routines. Target-update ordering is verified for bounded cases. Button ownership and the complete stock target activation bridge remain open.** This is progress toward a proof, not a working camera extension.

The required behavior remains class-independent: shutter half-press uses its own stock zone and whichever Subject Detect option is currently selected in the SCP, including Off. AF-ON uses its own stock zone and stock-equivalent detection Off behavior. S-AF/C-AF remains shared.

Verification follow-up: [AF-GAP-VERIFICATION.md](AF-GAP-VERIFICATION.md) checks the reset-eligibility branch and deferred command replacement. It confirms why the remaining gaps cannot be treated as closed.

## Stop and cached results: a nested software sequence now executes

Earlier tests exercised the stop worker and its helpers separately. [OM3IntegrationContracts.java](scripts/OM3IntegrationContracts.java) now starts at the original stop worker `0x60841ce6` and executes selected callees recursively:

1. `0x60842965` examines in-flight state `0xa33a1d12`. If one, it calls `0x6082e1d4`, which selects device callback `0x6082e204`; that calls device-stop implementation `0x6082ba97`. Native instructions clear the in-flight flag after the call.
2. The worker clears its running state and invokes `0x6084e7b8`. Original call instructions request six buffer clears.
3. The worker passes its reset option through `0x608714e9` to `0x608717b9`. The latter checks reset eligibility `0xa33ac4d8`, clears or saves the selection snapshot, requests five more buffer clears, and clears several state/counter fields.
4. The worker invokes the completion-signal service with mask 16 after those steps.

Twenty-four fixtures cover the six non-Off class tags, two reset options and in-flight values zero/one. The stop code does not select a class-specific branch in this sequence; class tags are retained fixture context, not six different detector implementations.

The eleven seeded ranges all clear in the controlled run:

- `0xa33a3010`, length `0x3fc`; `0x62f8d800`, length `0x3c2`.
- `0xa33a3550`, length `0xa4`; `0xa33a3648`, length `0x10`.
- `0xa33a3670`, length `0x52`; `0xa33a36c2`, length `0xa2`.
- `0xa33a7de0` and `0xa33a7f44`, each length `0x164`.
- `0xa33ac394`, length `0xf6`.
- `0xa33a7408` and `0xa33a6b64`, each length `0x878`.

The fill operation at imported `0x50002a15` is explicitly modeled with memset semantics. Native instructions choose the destinations, lengths and fill values. This verifies those clear requests and their effects under that contract; it is not native execution of the imported memory routine. The [traces](analysis/button-af/integration/stop-chain-traces.txt) preserve order through completion.

Sources: [in-flight stop](analysis/button-af/integration/inflight-stop.asm), [device wrapper](analysis/button-af/integration/device-stop-wrapper.asm), [device callback](analysis/button-af/integration/device-stop-dispatch.asm), [device implementation](analysis/button-af/integration/device-stop-implementation.asm), [six buffer clears](analysis/button-af/integration/result-buffers-clear.asm), [selection/result reset](analysis/button-af/integration/selection-result-reset.asm).

## Important result: a stop option deliberately retains selection

The reset at `0x608717b9` first clears twelve bytes at `0xa33ac4f8`. With reset option one and selection-valid byte `0xa33ac4e1` equal to one, it then copies a selection snapshot back into that region. The fixtures seed coordinates (400,120) and verify that both the snapshot markers and those coordinates survive with option one. With option zero, they remain cleared.

This resolves a practical ambiguity: detection stop does not imply that every remembered selection is discarded. A proposed AF-ON transition cannot simply call any stock stop variant and assume that stale subject state is gone. It must establish which retained state the standard Subject Detect Off path expects, or prove that retained data cannot influence conventional AF. The tests do not establish that manually forcing option zero everywhere is correct stock behavior.

## What completion still does not prove

The device-stop implementation writes peripheral addresses, including `0x9c180000`, and calls critical/delay services. In these tests peripheral addresses are emulator RAM; the device dispatcher chooses the observed callback through an explicit model. There is no physical detector behind the writes, and no claim that a real inference operation drained or that a delayed producer cannot publish another result afterward.

Other reset helpers, completion signaling, nested stack frames and saved-register postconditions are modeled. Reset eligibility is explicitly one. Top-level command queue scheduling, other eligibility states, concurrent producers, memory ordering and later stock refreshes remain outside the experiment. Eleven cleared ranges are not proof that every result store in the camera has been cleared.

## Active target update: ordering and state gates verified

Four fixtures now execute stock update routine `0x609029f1`, rather than calling the ten-byte copy in isolation. Its native instructions intersect requested update bits with allowed mask `0xa33ca314`, reject null contexts and state `0x3000`, then:

- Bit 1 copies the target record into active cache `0xa33ca384` through original routine `0x60903e55`.
- Bit 2 calls geometry recomputation `0x60903e88` afterward.
- A finalization call to `0x6090419d` follows in the examined normal path.

For fixture state `0x1700`, request mask 3 and allowed mask 3, native copy occurs before the geometry call. With allowed mask zero, the examined path only calls the finalizer. State `0x3000` exits before all three operations. Geometry and finalizer bodies are modeled; the accessor supplies a synthetic ten-byte record. Other update bits are excluded.

This identifies a state-gated stock update path that an extension might reuse. It does not connect the previously recovered four-byte UI descriptor to a complete ten-byte target record, execute final geometry/publication/display behavior, or show that invoking it during a button transition is safe. In particular, changing the accessor alone would not ensure an active update when these gates reject it.

Source: [active target update](analysis/button-af/integration/active-target-update.asm).

## Button ownership: misleading shortcuts ruled out, bridge still open

Inspection of request type `0x3bf` confirms that interface slot +8 points to `0x60af651c`, which checks the requested type and returns one for `0x3bf`; it is not an AF execution callback. Slot +0xc uses getter `0x60ae78c5` to read the request's 16-bit type at +4. Neither virtual slot establishes focus ownership.

Candidate consumers around `0x60ca2bc3` and `0x60ca3da0` obtain the current request, perform that type check and inspect request data, including payload offset +0x20 in the latter path. Multiple state tables contain the same numeric type, and one examined registry routes it to a common exit. These are candidate state-dependent transaction paths; this investigation has not verified which one connects the shooting AF-ON request to low-level LOCK/RELEASE operations. They are not evidence of an end-to-end bridge on their own.

Sources: [type-check instructions](analysis/button-af/integration/afl-request-execute.asm), [transaction submitter](analysis/button-af/integration/transaction-submit.asm), [candidate consumer](analysis/button-af/integration/afl-request-consumer-full.asm), [second candidate](analysis/button-af/integration/afl-release-consumer-full.asm). File labels identify investigation targets, not recovered official symbols.

## Current verdict and next proof requirements

There is more concrete software support for the proposed extension, including the stop/reset sequence and a conditional active-target update path. **The full feature remains unproven.** Remaining work is to resolve the active transaction/worker ownership path, establish which exact stock Off transition and reset option to use, connect target conversion to activation/display, and verify pending-result races and overlapping buttons through C-AF and bursts. ABI, installation and recovery also remain unresolved.

No modified firmware or installable extension was produced. No camera was connected or flashed. A successful offline sequence with explicit device/scheduler models cannot by itself prove physical camera behavior.

## Validation

Twenty-eight new bounded fixtures pass: 24 nested stop/reset cases and four active-target-update cases. [Results](analysis/button-af/integration/integration-results.txt), [scope](analysis/button-af/integration/integration-scope.txt), [final run](analysis/button-af/integration/final-run.log), [assembly ranges](analysis/button-af/integration/windows.tsv) and [hash manifest](analysis/button-af/integration/validation.json) retain the evidence. Earlier suites remain historical results and were not rerun here.

The harness initially used an unavailable memory-read API and then exposed an uninitialized peripheral-status fixture. Both harness issues were corrected before the final 28-pass run. The final run has no uninitialized-memory warnings. The saved Ghidra project and source firmware remain unchanged.
