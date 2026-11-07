# Independent shutter / AF-ON configurations: feasibility audit

OM System OM-3, firmware 1.1. Examined 31 October 2026.

Follow-up: [three-question investigation](AF-BUTTON-FOLLOWUP.md) recovers the subject-search snapshot, resolves UI/worker dispatch further, and tests an actual application update validator. The combined native test suites now pass 44 bounded fixtures. The complete extension remains unproven. The original audit below records the initial 17-test stage.

## Verdict

**A credible software implementation path exists, but the complete extension is not yet proven possible on the camera. There is also no evidence establishing that it is impossible.**

The evidence supports a prototype investigation. It does not support a guaranteed working or installable firmware modification. Any earlier claim of definite feasibility would be too strong.

The required feature is independent AF acquisition/search area, AF target pattern and subject-selection policy for shutter half-press and AF-ON, assignable either way. The motivating configuration is whole-frame Human acquisition on one button and conventional single-point AF on the other. Per-button subject priority alone is insufficient. S-AF/C-AF separation is outside the requested scope.

## What the executable code establishes

### Separate control paths already exist

The AF worker at `0x609df84d` dispatches named operations. Firmware diagnostic strings associate `LOCK_START` with handler `0x609e05a6` and `RELEASE_READY_START` with `0x609e4232`. The dispatch mapping is saved in [worker-dispatch-map.json](analysis/button-af/worker-dispatch-map.json).

In examined branches:

- `LOCK_START` calls priority control B, `0x609024aa`, at `0x609e0701`.
- `RELEASE_READY_START` calls priority control A, `0x60902452`, at `0x609e43dc`.
- Both then call `0x609ed64c` and `0x608ffdf0` with the latter's D0 argument set to `0x1100`.

The A/B controls consult distinct context bytes at `0xa33f2cac` and `0xa33f2cad` in the simple branch tested. They can suppress subject selection via `0x609025aa`; the enabling counterpart is `0x609024d2`. This is a concrete point of separation before common AF processing, not proof that either hook alone implements different areas.

The UI function `0x610bf5b9` distinguishes AF-ON press/release events `0x1050007` and `0x1050008`, with corresponding diagnostics. Its virtual dispatch has not been followed completely into these worker operations. Consequently, LOCK/RELEASE names and distinct priority controls must not be treated as a completed end-to-end physical button ownership trace.

### AF target geometry is data the software can change

`0x609b3481` returns shared context `0xa33f2c9c`. Target accessor `0x609b3bb2` returns `0xa33f2ce0`. Routine `0x60903e55` copies ten bytes from this target record to its caller. Area initializer `0x609025cf` uses that copy and geometry routine `0x60903e88`.

This supports retaining two configurations and selecting an active one in software. The ten-byte record is not established as the entire acquisition/search configuration. Other context fields, settings reads and cached geometry paths exist; replacing only this record is not a complete solution.

### A simple temporary overwrite is insufficient

When the accessor's dirty byte at `0xa33f2cea` is one, it calls refresh routine `0x609b3c79`. That routine reads seven values through settings getter `0x60063380` and rebuilds the record:

- `0x88b2`, index 0: record +0, unsigned 16-bit.
- `0x84d1`, index 0: record +2, byte, pattern/type candidate.
- `0x9a41`, index 0: record +3, byte.
- `0x1dd1`, indices 0 and 1: record +4 and +6, unsigned 16-bit.
- `0x1df1`, index 0: record +8, byte after normalization.
- `0x1e01`, index 0: record +9, byte.

The routine also consults context +0x22, optionally invokes `0x609832f5`, and normalizes particular pattern values. For example, pattern value 2 forces the first field to `0x20e` and clears +8. The numeric keys and offsets are established; their full UI meanings are not. Label inventory indexes must not be substituted for runtime setting IDs.

An extension would need to manage refresh, profile ownership and downstream geometry together. Otherwise a legitimate settings refresh can replace its temporary target record.

## Executed validation

[OM3ButtonContracts.java](scripts/OM3ButtonContracts.java) executes bounded firmware instructions with Ghidra's community MN10300 Sleigh model. **17 tests passed:**

- Two exact ten-byte copy tests, with destination guards.
- Eight priority tests covering four A/B byte combinations in both controls.
- Two dirty-accessor tests verifying conditional refresh and the returned pointer.
- Five target-refresh tests using synthetic pattern values 0, 1, 2, 3 and 6, checking seven settings reads and exact normalized record bytes.

External calls have explicit modeled postconditions. Terminal returns and call-stack semantics are excluded. The refresh tests keep context +0x22 zero, so the optional helper is not tested. Records/settings are synthetic; they are not captured known-good single-point and all-area camera configurations. No detector, lens, interrupts, button arbitration or AF timing is emulated.

These tests validate selected native data/control mechanisms. They do not validate a complete extension. Results and scope are in [native-contract-results.txt](analysis/button-af/native-contract-results.txt) and [native-contract-scope.txt](analysis/button-af/native-contract-scope.txt).

## What prevents a definite yes

1. **Profile completeness:** identify all fields controlling initial Human acquisition and conventional single-point eligibility. Demonstrate full-frame initial acquisition, rather than only tracking after acquisition. Map actual stock configurations to their native values.
2. **Ownership and synchronization:** trace physical press/release through the worker, then demonstrate both-button overlap, full shutter press and release/resume without stale target state or a race. Existing selection may need invalidation/reacquisition when the owner changes.
3. **Active geometry and UI:** update all relevant caches, coordinates and displayed target together, including orientation and point movement. The separate geometry path used by `0x60905296` means an accessor-only hook may miss consumers.
4. **Execution and installation:** verify the camera ABI, usable persistent code/data space, modified-image acceptance and a recovery route. Reversible container encoding and checksums do not establish boot/update acceptance of an altered image.
5. **Hardware behavior:** run an instrumented prototype through AF-ON, half-press, both held in both orders, release/resume, no-Human fallback, orientation, C-AF and burst transitions. No camera has been connected for this work.

## Candidate implementation, not a completed patch

Keep two RAM profiles and a single active owner, select the appropriate profile in the AF worker, apply subject-selection policy, and rebuild/invalidate the active AF geometry through the normal path. Keep persistent user settings separate from temporary active state. This uses one active AF configuration at a time; it does not inherently require two simultaneous detection engines or a new Human recognition algorithm.

AF-ON precedence while both controls are held is a proposed policy, not a tested feature or a user-confirmed requirement. On release, return to the remaining held button's profile. Initial validation should use fixed known-good profiles before adding user assignment, saved configuration or UI controls.

**Decision:** continue as a bounded firmware prototype research project. Do not describe it as a confirmed feature or an installable patch. No modified firmware was produced or flashed in this audit.

## Evidence limitations

The bulk decompilation contains false CALL_RETURN overrides after returning settings getters. Some original C exports therefore omit real continuations. This audit uses bounded assembly decoding in `analysis/button-af`, with executable tests for the mechanisms above. Linear decoding itself does not prove that every decoded instruction is reachable. The community processor model and camera calling convention remain material limits.
