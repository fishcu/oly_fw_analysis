# Verification audit of the remaining AF extension gaps

OM-3 1.1, 31 October 2026. **The remaining gaps are real limits of the current evidence. This audit does not close them.** It reruns the prior 28 integration fixtures and adds five targeted checks of reset eligibility, deferred command replacement and result-copy guarding.

The requested feature is unchanged: half-press uses its own stock zone and the current SCP Subject Detect choice, including Off; AF-ON uses its own stock zone with stock-equivalent detection Off behavior; S-AF/C-AF is shared.

## 1. Stop completion does not by itself verify complete reset

The earlier nested stop fixtures explicitly set reset eligibility byte `0xa33ac4d8` to one. That condition matters.

Two new fixtures execute the same native stop/reset chain with eligibility zero and one, stop option zero and in-flight state zero. Both seed the eleven known buffer ranges and twelve-byte selection snapshot before execution.

- Eligibility one: all eleven ranges and the selection snapshot clear.
- Eligibility zero: the first six ranges clear, but the other five ranges and selection snapshot retain their seeded contents. The reset routine takes its diagnostic branch. With the diagnostic service explicitly modeled as returning, the worker still reaches the completion-service call with mask 16.

This verifies that the prior clear-all observation was conditional. It does not prove the diagnostic returns on the real camera, that eligibility zero occurs in normal button use, or that the retained data necessarily influences focus. Those remain separate questions. It does prove that a proposed extension must establish the eligibility precondition or otherwise demonstrate the correct stock Off transition; a completion-service call alone is insufficient evidence.

The earlier result that stop option one can retain a selected coordinate snapshot also remains valid under eligibility one.

Sources: [native reset instructions](analysis/button-af/integration/selection-result-reset.asm), [prior integration harness](scripts/OM3IntegrationContracts.java), [new verification harness](scripts/OM3GapVerification.java).

## 2. Deferred command storage is not established as a FIFO

A new fixture executes native submit routine `0x60841102` three times while the scheduler model deliberately holds callbacks:

1. Kind 5 work is submitted with the pending/current byte initially zero. The routine stores current kind 5 and requests callback `0x608418fe`.
2. Kind 2 stop is submitted while current kind remains nonzero. The routine copies the complete 124-byte command into replacement storage at `0xa33a1c94` and requests callback `0x608412c5`.
3. Kind 1 restart is submitted before callbacks run. The same replacement storage now contains the restart command, replacing the stop record.

The test checks the actual native copies, current-kind byte, callback arguments and final replacement bytes. Lock services, timestamps and scheduling are explicit models. This is a controlled raw-submit schedule, not an execution of the stock synchronous stop/start wrappers or physical button overlap.

Consequently, an extension cannot assume that submitting stop and restart immediately will preserve both in a generic FIFO. The stock wrappers' completion waits may provide the necessary ordering; the audit has not executed those waits together with real command delivery or proved their behavior under overlapping callers. The fixture is not evidence that ordinary stock operation loses stop commands.

Source: [submission instructions](analysis/button-af/lifecycle/detection-command-submit.asm). The native test executes through the routine's return, including instructions beyond that bounded reading window.

## 3. Late result publication remains a caller/synchronization question

Two new bounded fixtures enter the result-copy block at `0x608719e7` with identical seeded source data and different running/reset flags. Original instructions copy 356 bytes from `0xa33a7de0` to `0xa33a7f44` in both cases, including when worker state and reset eligibility are zero.

This block itself does not reject the stopped-state fixture. However, the test deliberately begins inside the function. It does not prove that a real callback can reach this block after stop completion, that another CPU publishes late data, or that conventional AF consumes it. Verifying those possibilities requires following the producer, dispatcher and synchronization paths around the block. The copied region is not claimed to be a complete final AF result or a learned detection record format.

Source: [result-publication routine](analysis/human-detection/assembly/239-mdet_laf_dl_set_subject_detect_result_cpu3.asm), specifically the copy ending at `0x608719fc`.

## 4. Target activation/display gap remains open

The prior four target-update fixtures rerun successfully. They verify update-mask/state gating, the native ten-byte cache copy, and call order before a modeled geometry routine and finalizer. The earlier eleven converter fixtures separately verify a four-byte descriptor format. Neither test connects the two formats or executes the final display update.

The code therefore supports two useful observations, not a demonstrated complete stock-zone switch. Before claiming this gap is closed, a test must start from each supported stock target choice, pass through its actual conversion/refresh path, and verify active geometry, search snapshot and display consistently, including target movement and orientation.

## 5. Button ownership gap remains open

Existing shooting-handler tests cover assignment-gated AF-ON press and release ordering. Other tests cover low-level AF-worker operations. The intervening state-dependent transaction route has not been executed end to end, nor has a controller resolved simultaneous half-press, AF-ON and capture events.

The examined request interface's +8 slot is a type check, not an AF execution callback. Candidate request consumers do not establish which transaction path is active during normal shooting. A verified ownership transition must also survive stock setting refreshes, apply the correct zone/detection policy before focus starts, and return to the current SCP selection on release. That last requirement applies to every supported class and Off, not only Human.

## Verified status

The supporting instruction observations remain reproducible. The audit also demonstrates why they are not sufficient to approve a camera extension: reset eligibility, replacement-slot ordering and result-entry reachability are unresolved integration conditions. Complete stock Subject Detect Off equivalence, C-AF/burst transitions, firmware ABI, installation and recovery remain unverified.

No camera was connected, no firmware was flashed and no installable extension was generated.

## Evidence and reproduction

[OM3GapVerification.java](scripts/OM3GapVerification.java) passes five new fixtures: two reset-eligibility cases, one three-submission sequence and two bounded result-copy cases. [Results](analysis/button-af/integration/gap-verification-results.txt), [traces](analysis/button-af/integration/gap-verification-traces.txt), [scope](analysis/button-af/integration/gap-verification-scope.txt) and [audit log](analysis/button-af/integration/audit-final-run.log) retain the models and outcomes. The same audit run also passes all 28 prior integration fixtures. The [manifest](analysis/button-af/integration/gap-verification-validation.json) pins the firmware and artifact hashes.

Run the saved read-only Ghidra project with `-noanalysis -readOnly`, script path `scripts`, and post-scripts `OM3IntegrationContracts.java` followed by `OM3GapVerification.java`, each receiving the absolute `analysis/button-af/integration` output directory. Terminal returns, nested call frames and callee-register postconditions remain modeled under the community MN10300 instruction model.
