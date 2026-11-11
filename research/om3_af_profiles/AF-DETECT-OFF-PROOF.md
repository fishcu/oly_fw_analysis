# AF-ON detection bypass: evidence and proof boundary

OM-3 firmware 1.1, 31 October 2026. **The effective detection mode can be changed separately from its settings accessor in the examined code. Selection suppression alone is not equivalent to Off in an examined detection-request path. The complete two-button extension remains unproven.**

This investigation executes selected original instructions offline in Ghidra. It does not execute a camera, the complete AF engine or a modified image. The [feature specification](analysis/button-af/FEATURE-SPEC.md) remains half-press with its stock zone and SCP detection choice, AF-ON with its own stock zone and effective detection Off, sharing S-AF/C-AF.

## 1. The saved setting and effective mode have distinct paths

The native sequence at `0x603c6454` requests key `0x1e71`, index zero, through settings accessor `0x60063380`, then stores the returned byte at configuration offset `+0xce`. Seven native fixtures verify values 0 through 6 are copied unchanged; the accessor return is modeled. Prior resource analysis identifies zero as Off and six as Human.

The configuration application at `0x603c697d` loads `config+0xce` and calls `0x603cedfe`. A second bounded application path at `0x606ffe6c` does the same after a success check. The bulk C had hidden the configuration continuation behind a false non-returning settings call; the bounded assembly includes it.

`0x603cedfe` reads the old effective-mode byte at `0x62a6a0eb`, invokes services `0x60075f73(2)` and `0x60075fbc(token)` around its write of the new mode, then calls `0x603cee28` with the old mode. The paired services are modeled as lock/unlock operations; their implementations are not executed here.

Two native setter fixtures verify Human-to-Off and Off-to-Human writes and the notification call. Neither examined setter path calls the settings setter. This establishes a concrete software mechanism for changing effective mode independently of a saved-setting write. It does **not** establish that a later stock configuration refresh will preserve a per-button override, nor prove camera-visible SCP preservation over a complete button sequence.

Sources: [configuration translation](analysis/button-af/detect-off/detect-config-translation.asm), [second application path](analysis/button-af/detect-off/detection-config-apply3.asm), [effective-mode setter](analysis/button-af/detect-off/subject-mode-apply.asm).

## 2. A native counterexample to suppression being the same as Off

Decision routine `0x60703dde` checks an eligibility flag at input offset `+0x59c`, then reads effective mode `0x62a6a0eb`. If the mode is zero it exits early with false. With Human selected and the other fixture conditions satisfied, it continues through state checks and a divisibility/cadence calculation at `0x60703dcb`.

The caller at `0x607039b2` invokes this decision and, when true, calls request builder `0x607045b1`. That builder allocates a record through `0x60707730`, populates fields and ORs bit `0x800` into the enclosing request word at `+0x0c`. This is one detection-related request path; the experiment does not establish the meaning of every downstream consumer of that bit.

Four bounded integration fixtures execute the original decision, divisibility helper, caller branch and request flag construction. With cadence input 8 and eligible flags:

- Human, selection enabled: one allocation and request bit `0x800` set.
- Human, selection suppressed: the same allocation and request bit set.
- Off, selection enabled: no allocation and the bit remains clear.
- Off, selection suppressed: no allocation and the bit remains clear.

The allocator and one field-selection helper are modeled. Saved registers are explicitly restored at modeled call boundaries; terminal returns/call frames are excluded. The decision/caller and request-bit instructions themselves execute natively.

This is a concrete difference under controlled inputs. Toggling the selection-suppression flag does not substitute for effective Off in this path. It does **not** prove that stopping every detection request is necessary for standard AF: recognition could potentially continue in the background while focus selection bypasses it. A focus-only implementation would need its own equivalence evidence.

Sources: [native mode decision](analysis/button-af/detect-off/detection-mode-query.asm), [caller](analysis/button-af/detect-off/detection-decision-caller.asm), [request construction](analysis/button-af/detect-off/detection-request-build.asm).

## 3. Mode transitions have lifecycle work outside this setter

The notification gate at `0x603cee28` calls class-change routine `0x6084036f` only when the active byte `0x62a6a523` is one, the class changes, and both old and new values are nonzero. Eight fixtures cover active/inactive state for Human-to-Off, Off-to-Human, Human-to-Bird and unchanged Human.

Transitions involving Off do not send that class-change notification. Consequently, calling the effective-mode setter alone is not a demonstrated detector stop/start sequence.

An examined start path at `0x60701b04` separately checks a configuration flag before calling `0x608401af` with the effective mode and marking the active byte. The start wrapper accepts classes 1 through 6; zero takes its invalid-class path rather than constructing a normal start command. These start-path findings are static instruction evidence, not additional native lifecycle tests. An extension must reproduce the appropriate stock eligibility and start/stop transitions rather than passing zero into a class-only start/change operation.

Selection-disable execution at `0x60873e6d` is another separate operation. One native fixture verifies that it sets `0xa33ac4f4` to one, leaves effective Human mode intact, and calls reset/publication helpers in order. Those callees are modeled, so the result does not prove all downstream result buffers are invalidated.

Sources: [notification gate](analysis/button-af/detect-off/subject-mode-apply.asm), [start path](analysis/button-af/detect-off/detection-start-stop.asm), [start wrapper](analysis/button-af/detect-off/detection-start-wrapper.asm), [selection disable](analysis/button-af/detect-off/selection-enable-disable.asm).

## What this proves for the proposed feature

There is a credible implementation route: retain the SCP choice, give each button a stock target profile, and apply effective Off behavior while AF-ON owns focus. The firmware already separates configuration storage, effective mode, detection-related request eligibility and subject selection. These findings remove the need to assume that all of those behaviors are one inseparable global setting.

The remaining proof requires a complete ownership transition: stock target conversion and cache refresh, effective-mode policy, detector lifecycle or demonstrated focus-only bypass equivalence, existing-result invalidation, display updates and release/resume handling. The same sequence must remain correct during overlapping buttons, C-AF, capture and bursts. Installation, ABI and recovery also remain open.

**Verdict: a mechanism has been demonstrated offline; an operational camera extension has not.** No firmware patch or installable modified image was generated, and no camera was connected or flashed.

## Validation and reproduction

[OM3DetectOffContracts.java](scripts/OM3DetectOffContracts.java) passes **26 new bounded fixtures**: seven configuration copies, eight notification cases, two setter cases, four early decision comparisons, four decision/caller/request integrations and one selection-disable comparison. The earlier 62 fixtures remain historical passing results, for 88 across these suites; they are not 88 end-to-end tests and were not rerun in this investigation.

Run Ghidra headless against project `OM3_main_full` with `-process '*' -noanalysis -readOnly`, script path `scripts`, and `-postScript OM3DetectOffContracts.java` with the absolute `analysis/button-af/detect-off` output directory. `JAVA_HOME` must select the bundled JDK. The final run reports 26 PASS without uninitialized-memory warnings. An earlier exploratory run exposed an uninitialized auxiliary state byte; it was initialized explicitly before the final runs.

[Results](analysis/button-af/detect-off/detect-off-results.txt), [scope](analysis/button-af/detect-off/detect-off-scope.txt), [final log](analysis/button-af/detect-off/verified-run.log) and [artifact hashes](analysis/button-af/detect-off/validation.json) preserve the experiment. All execution uses the community MN10300 instruction model, with the models and exclusions listed above. The saved Ghidra project and source firmware remain unchanged.
