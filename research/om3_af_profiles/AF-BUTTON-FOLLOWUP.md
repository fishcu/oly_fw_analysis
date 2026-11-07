# Follow-up: three AF extension feasibility questions

OM System OM-3 firmware 1.1, 31 October 2026. Source update SHA-256: `8c133084414533159f587bf46bfb4152714c4074312a47c8d8503e33d605696d`.

Later milestone: [offline profile prototype](AF-PROFILE-PROTOTYPE.md) adds 18 passing fixtures (62 total), recovers the UI-to-runtime setting map, identifies shooting-specific AF-ON handlers, and executes a native target-cache/geometry/candidate-gate integration. It also clarifies that the two `0x90b1` entries select still/movie tracking, and that `0x85b1` is named `MODE_CONTINUE_TAKE`.

## Result

The extension now has a more concrete implementation basis: separate priority controls, a target record and active target cache, a subject-search configuration with multiple rectangles, and separate AF worker operations. Native instruction tests also establish that one application-level update checkpoint accepts altered contents with a repaired checksum.

**This remains an unproven complete camera extension.** Neither an end-to-end two-button implementation nor the complete installation/boot/recovery chain has been demonstrated. The follow-up narrows the uncertainties; it does not replace them with a guarantee.

## 1. Complete AF acquisition configuration

### Newly recovered data path

The target record at `0xa33f2ce0` is not the sole control of acquisition. The following path connects AF geometry to subject candidate eligibility:

1. `0x609025cf` copies the ten-byte target record into active cache `0xa33ca384` and builds adjacent area geometry. Its copy call is at `0x6090260a`; geometry call is at `0x60902616`.
2. `0x609dc311` reads this active target cache through `0x60902c64`, derives grid positions and dimensions, clamps them and looks up image coordinates.
3. `0x609dc2ea` supplies full-image bounds from firmware tables: x=0..639 and y=0..479. These values were executed and verified with the native instruction model.
4. `0x609dc1b4` writes three rectangles into the structure referenced by `0xa33f3618`: target-derived at +0x18, full-image at +0x20, and a policy-dependent choice of those at +0x28. Its decision reads context fields and current selection state. It is not simply a single global “All” flag.
5. `0x608ff478` updates that structure and exports **50 bytes**. It also invokes `0x609dc3c3`, which builds a rectangle from setting `0x85b1`: tested value 5 gives x=0..639, y=36..443; tested value 0 gives x=0..639, y=0..479. The setting's exact UI meaning remains unverified.
6. `0x6087197d` conditionally copies the 50-byte snapshot to `0xa33ac49e`. The native copy loop at `0x60871b50` was tested with an exact record and surrounding guards.
7. The three rectangles arrive at `0xa33ac4b6`, `0xa33ac4be` and `0xa33ac4c6`. `0x6086b8c2` selects one into `0xa33ac494..0xa33ac49a`, depending on selection state.
8. Candidate routine `0x6086bd8a` consults these bounds. The fragment beginning `0x6086c089` was executed: a candidate away from a small central region fails its first region gate, while the same candidate passes that gate with full-frame bounds. A candidate inside the small region also passes.

The first region test uses candidate rectangle overlap; passing it is not equivalent to final selection. Later gates include proximity and selection-state conditions. The test does not establish detection accuracy, final acquisition, or that forcing only one rectangle is sufficient.

Sources: [rectangle builders](analysis/button-af/subject-search-rectangle-builders.asm), [configuration export](analysis/button-af/subject-configuration-export.asm), [configuration latch](analysis/button-af/subject-configuration-latch.asm), [candidate assembly](analysis/human-detection/assembly/202-mdet_laf_dl_main_subject_select_candidate.asm).

### Implication for the extension

A profile switch must update at least the target pattern/position/dimensions, active geometry cache, subject-versus-target priority, search rectangles and current selection state. Changing the visible pattern or returning a different target-record pointer alone can leave acquisition operating on old data.

There are native update routines as well as initialization. `0x609029f1` uses change-mask bits to refresh the cached target record and geometry; `0x60902ac0` provides another state-dependent update path. Some paths limit geometry updates to particular AF states. These are candidate integration points, not a confirmed callable profile-switch API.

**Status:** data flow to initial candidate eligibility substantially recovered. Exact stock single-point/all-area profile values, every relevant policy branch, cache lifetime and orientation behavior remain to be established. Runtime setting IDs are not interchangeable with indexes in the extracted name inventory.

## 2. Button ownership and overlapping presses

### UI calls resolved further

The UI handler `0x610bf5b9` distinguishes AF-ON press/release events `0x1050007` and `0x1050008`. Accessor `0x610c888a` reaches `0x60b8868b`; its lazy constructor installs function table `0x60e57668` in an object at `0x62b503c8`.

Relevant table slots read directly from this firmware:

- +0x3c8 -> `0x60b8d6e1` -> `0x60b19a03`, which constructs a request and invokes `0x604235ea` with operation 9.
- +0x3cc -> `0x60b8d6f7` -> `0x60b19a24`. Native tests verify this helper maps Boolean 0 to command `0x041b0038` and 1 to `0x041b0062`, through `0x60421572`.
- +0x3e8 -> `0x60b8d8a3`, which reaches the separate transaction/request path through `0x60b19ba2`.

The AF-ON handler chooses different slots according to camera state. Its +0x3c8 branch is distinct from the +0x3cc helper tested above; the command mapping must not be described as a complete AF-ON-to-worker trace. In particular, `0x60b19a03` does not visibly propagate its incoming Boolean into the constructed request, so its press/release semantics need further tracing.

### Worker messages resolved and tested

AF worker `0x609df84d` receives a message, looks it up in table `0x60a83454..0x60a83654`, dispatches an operation, and returns to its receive loop. Table keys store message+1. Native tests verify:

- Message `0x100`: LOCK_START, dispatch `0x609df95b`, handler `0x609e05a6`.
- Message `0x101`: LOCK_END, dispatch `0x609df9c1`, handler `0x609e2384`.
- Message `0x300`: RELEASE_READY_START, dispatch `0x609dfa0e`, handler `0x609e4232`.
- Message `0x301`: RELEASE_READY_END, dispatch `0x609dfa29`, handler `0x609e4f6a`.

The examined LOCK_START and RELEASE_READY_START branches invoke different priority controls, B and A respectively, before common AF processing. The complete table mapping is in [worker-message-map.json](analysis/button-af/worker-message-map.json).

### What this says about overlap

The single worker loop is a promising place to manage an active owner and apply a profile coherently relative to its own messages. It does **not** make the whole pipeline atomic: the subject subsystem consumes snapshots separately, and the 50-byte latch is a sequence of writes. An extension must coordinate publication and selection invalidation rather than let UI callbacks overwrite shared state directly.

Both-button handling is still a design requirement. Proposed behavior: AF-ON owns AF while both are held; releasing AF-ON resumes the shutter profile if half-press remains held; full shutter press captures without stealing AF ownership. This proposal has not been validated against physical button events, cancellation, focus lock or burst behavior.

**Status:** UI indirection and worker operations recovered further. End-to-end ownership through the transaction layer, both held in both orders, and synchronization across consumers remain open. No claim of race-free switching is warranted.

## 3. Modified-image acceptance and execution

### Actual OM-3 component checker found

Update wrapper `0x6106d231` optionally calls descrambler `0x6106b7db`, then component validator `0x6106b712`. The examined descriptor-mode-1 validator compares the first five header/trailer words and calls additive checksum routine `0x60155816`. There is no cryptographic verification operation in that examined path. This is a bounded statement about this checkpoint, not about every update or boot stage.

Native tests use an 80-byte synthetic component carrying the stock container header format with a reduced payload length:

- Valid fixture: return 0.
- Altered payload with repaired checksum: return 0.
- Same payload alteration without repair: return `0x3211`.
- Header/trailer mismatch: return `0x3202`.
- Invalid descriptor mode 2: return `0x3204`.

The checksum and header helper instructions execute natively. Diagnostic output is modeled. The implicit saved-D2 postcondition of the checksum call is modeled explicitly; call/return frames and terminal returns are not executed. Descriptor mode 0, whole-size camera images and the full update chain are not covered by these fixtures.

The native descrambler also produced the exact permutation/inversion used by our offline decoder for an 80-byte fixture, preserving its header/trailer. Sizes 64 and 79 were rejected without modifying the buffer.

Sources: [validator and descrambler](analysis/button-af/update-validator-and-descrambler.asm), [wrapper](analysis/button-af/update-check-wrapper.asm), [checksum core](analysis/button-af/update-checksum-core.asm).

### Added code has plausible loaded locations

The firmware descriptor table and executed end selector confirm the same section bounds documented by the prior OM-3 V22 research. The stock loaded sections contain FF tails of 1,776 bytes in section 1, 1,912 bytes in section 4 and 404 bytes in section 9.

Partial native loader tests verify exact storage requests and successful loaded-bit updates for these sections, with changed tail markers retained under modeled storage. They enter after an opaque descriptor-index instruction with an explicit index fixture; alias conversion and successful storage are modeled. They do not prove executable permissions, cache coherence, later ownership, reload safety or unused RAM for profile state.

Separately, three in-memory experiments changed markers inside those tails in the full-size main component. Unrepaired components failed the offline checksum check; repaired components decoded correctly with metadata preserved. No installable image was saved. Results: [packaging-experiments.json](analysis/button-af/packaging-experiments.json).

The published V22 OM-3 tethering work reports real added-code operation on this exact stock image and a recovery case. Its local source audit is useful precedent; its hardware outcome has not been reproduced here. See [published modification research](https://github.com/fishcu/oly_fw_analysis/blob/main/docs/features/HISTORICAL_HACKS.md) and [local code-space analysis](reference/docs/safety/CODE_SPACE.md).

**Status:** encoding, one actual application validation path and candidate section loading have concrete positive evidence. Full-image acceptance, boot authentication, execution on this camera, early recovery and permanent state allocation remain unverified. Absence of a signature check in one routine does not establish absence throughout the camera.

## Validation and next proof

[OM3AFGapContracts.java](scripts/OM3AFGapContracts.java) passes **27 new bounded native tests**, alongside the earlier **17** in [OM3ButtonContracts.java](scripts/OM3ButtonContracts.java): **44 total**. These are separate fixtures, not end-to-end tests. The new scope and results are [gap-native-scope.txt](analysis/button-af/gap-native-scope.txt) and [gap-native-results.txt](analysis/button-af/gap-native-results.txt).

An initial test fixture incorrectly used bytes from the decoded executable as its container header. That fixture was corrected to read the stock update header; the final 27-test run passes. No camera result was inferred from that harness correction.

The next implementation milestone is an instrumented, fixed two-profile prototype that traces ownership, applies the normal cache/rectangle updates, and records publication and selection changes. UI assignment and saved profiles should follow that proof. A hardware installation test also needs an established recovery procedure. None of these experiments has connected to, written to or flashed the camera.
