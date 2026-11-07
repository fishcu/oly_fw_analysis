# AF profile prototype: current milestone

OM-3 firmware 1.1, 31 October 2026. This is an **offline integration harness**, not an installable extension or a complete button controller.

The [current feature specification](analysis/button-af/FEATURE-SPEC.md) now uses two independent profiles drawn from stock target/zone choices. Half-press follows the SCP Subject Detect selection; AF-ON uses stock Subject Detect Off behavior. Both share the current S-AF/C-AF setting. The geometry fixtures below do not yet implement or verify that complete behavior.

Later investigation: [effective Off versus selection suppression](AF-DETECT-OFF-PROOF.md), with 26 additional bounded fixtures and a concrete request-path difference. The 62-fixture count below describes this earlier milestone.

## What now executes

[OM3ProfilePrototype.java](scripts/OM3ProfilePrototype.java) executes selected original firmware instructions in Ghidra:

1. A supplied profile's ten-byte target record is copied by `0x60903e55` into the active cache at `0xa33ca384`.
2. Native geometry builder `0x609dc311` reads that cache and converts its grid position and dimensions to an image rectangle.
3. The harness supplies that rectangle to the native first candidate-region gate at `0x6086c089`.

Two fixtures pass through the same instructions:

- Narrow geometry: grid position 526, vertical/horizontal dimensions 1/1. Resulting rectangle: **[295, 213, 345, 267]**, expressed as xmin, ymin, xmax, ymax.
- Wide geometry: grid position 526, dimensions 27/39. Resulting rectangle: **[0, 0, 639, 479]**.

A candidate rectangle at x=500..520, y=100..120 fails the first gate for the narrow fixture and passes it for the wide fixture.

These are synthetic geometry records. They are not captured stock Single/All target presets, and the harness does not claim final subject selection or lens focus. Accessor return pointers are explicit models; the transfer from rectangle output to the selection rectangle is also modeled. No button hook or code injection was generated.

## Runtime setting names recovered

The earlier warning remains valid: shifting a runtime key right by four does not produce its UI name index. The actual translation is table `0x6062555c`, containing a 16-bit runtime key and 16-bit array index per UI setting in the ordinary 0..0x8cf range.

Native routines `0x60419446` and `0x60419696` implement the key and array-index lookup. Thirteen key/index pairs were executed with lazy cache initialization disabled. The setting names are associated separately using the same firmware's resource inventory.

The target record can now be described more precisely:

- +0: `MODE_AF_FRAME`, key `0x88b2`, index 0; unsigned 16-bit grid position.
- +2: `MODE_AF_AREA`, key `0x84d1`, index 0; internal area selection.
- +3: `MODE_AF_TARGET_SIZE`, key `0x9a41`, index 0.
- +4: `MODE_AF_AREA_SIZE_VERTICAL`, key `0x1dd1`, index 0.
- +6: `MODE_AF_AREA_SIZE_HORIZONTAL`, key `0x1dd1`, index 1.
- +8: `MODE_AF_CENTRAL_PRIORITY`, key `0x1df1`, index 0, with normalization by the target-refresh routine.
- +9: `MODE_CAF_CENTRAL_START`, key `0x1e01`, index 0.

Additional mappings relevant to the extension:

- `MODE_AF_AREA_TYPE`: UI ID 163 -> key `0x99a1`, index 0. This is distinct from the internal `MODE_AF_AREA` field. Its dropdown enum must not be copied directly into record +2 without establishing the conversion.
- `MODE_SUBJECT_DETECT`: ID 1712 -> `0x1e71`, index 0.
- `MODE_AF_SUBJECT_PRIORITY_RELEASE`: ID 2154 -> `0x90a1`, index 0.
- `MODE_AF_SUBJECT_PRIORITY_CUSTOM_SW`: ID 2155 -> `0x90a1`, index 1.
- `MODE_CAF_SUBJECT_TRACKING_STILL`: ID 2156 -> `0x90b1`, index 0.
- `MODE_CAF_SUBJECT_TRACKING_MOVIE`: ID 2157 -> `0x90b1`, index 1.

The last two entries are **still/movie tracking settings**, not a second shutter/AF-ON pair. This narrows the interpretation of context bytes `0xa33f2cae` and `0xa33f2caf` used in earlier rectangle analysis.

Key `0x85b1`, used by a previously tested rectangle helper, maps to `MODE_CONTINUE_TAKE`. Its value-5 rectangle remains verified, but calling that key an aspect-ratio setting would be unjustified. Likewise `0xe8d9` maps to `MODE_AF_LOCKON_LEVEL`, not Human detection. Human mode is separately selected by `0x1e71`.

Reproduce the focused map with [trace_af_controls.py](scripts/trace_af_controls.py). Output: [gui-property-key-map.json](analysis/button-af/gui-property-key-map.json).

## Shooting AF-ON handling found

Static event-table records include:

- AF-ON press `0x1050007` -> handler `0x610b962a` at table entry `0x6131c290`.
- AF-ON release `0x1050008` -> handler `0x610b9653` at `0x6131c2a0`.
- Another press handler, `0x610ae921`, appears in another state table.

The firmware contains multiple UI-state handlers for the same physical control. The earlier `0x610bf5b9` target-control path remains real, but is not sufficient to identify the normal shooting AF path.

The shooting press handler:

1. Calls `0x610b9828(1)`, setting the AF-ON held-state word at `0x6036ee34`.
2. Queries button assignment through `0x6108ad0a(11, 0)`.
3. Calls AF start-policy function `0x610a5620(1, 0)` only when that query returns one.

Native tests cover both assignment-query outcomes. The held state is set even when this branch does not start AF; it therefore is not itself proof that AF-ON owns the active focus operation.

The shooting release handler first calls `0x610a58c7(1, 0)`, then clears the held state, then issues state event 9 in the tested state. The native test verifies that AF release policy observes held=1 and the later state event observes held=0. Its special `0x900002b` UI branch is excluded.

This ordering means a downstream extension cannot infer every release transition merely by sampling the held flag. It needs explicit ownership transitions and assignment gating.

### AF request layer

The shooting policy reaches other slots of the same UI interface table:

- +0x5c -> `0x60b88e17` -> `0x60b14eb4`, with diagnostics identifying `setAflState`.
- +0x60 -> `0x60b8903f` -> `0x60b0e0d6`, a state query.
- +0x64 -> `0x60b893ee` -> `0x60b14c93`, another AF operation path.

`setAflState` builds a request through `0x60af64fd`: type `0x3bf`, interface table `0x60dff1c8`, arguments stored at +0x20 and +0x24. Execution passes through the generic transaction/request machinery. Its full connection to the low-level LOCK/RELEASE worker operations remains unresolved; the request interface and calling convention must not be inferred from a single generated-C virtual call.

Sources: [shooting handler assembly](analysis/button-af/shooting-afon-handlers.asm), [AF start policy](analysis/button-af/shooting-af-start-policy.asm), [request constructor](analysis/button-af/afl-request-constructor.asm), [shooting-control-map.json](analysis/button-af/shooting-control-map.json).

## Test status and remaining work

The new suite passes **18 tests**: 13 native setting translations, two shooting press cases, one shooting release sequence and two native geometry integration cases. Together with the previous suites, **62 bounded fixtures pass**. This is not 62 end-to-end camera tests.

Results: [profile-prototype-results.txt](analysis/button-af/profile-prototype-results.txt). Scope: [profile-prototype-scope.txt](analysis/button-af/profile-prototype-scope.txt). Event order: [shooting-event-order.txt](analysis/button-af/shooting-event-order.txt).

To become a camera extension, the prototype still needs:

- A complete shooting/request/worker ownership trace, including shutter half-press and full-press behavior.
- Correct conversion between UI target types and complete native profiles; preferably confirmed against captured stock configurations.
- A coordinated update protocol for active target cache, subject-search snapshot, selection invalidation and display. Current tests explicitly model a publication step.
- Correct behavior for overlapping controls, assignment changes, focus lock, moving the point, orientation, C-AF and bursts.
- Verified camera ABI, code/data placement, installation, boot and recovery.

The proposed AF-ON precedence policy remains a design choice, not established stock behavior. The test harness has not modified the saved Ghidra project, original firmware image or camera.
