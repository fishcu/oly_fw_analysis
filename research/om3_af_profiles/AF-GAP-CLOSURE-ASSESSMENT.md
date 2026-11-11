# AF acceptance-gate closure assessment — 9 November 2026

This review covers the four acceptance gates in
[FEATURE-SPEC.md](analysis/button-af/FEATURE-SPEC.md#current-evidence-and-limits).
It began with static reading and supplemental emulator probes; later follow-ups
retain the successive boundaries and corrections. The summary below and the
latest follow-ups contain the current interpretation. No camera-installable image
was built, and no camera was accessed.
**No complete acceptance gate is closed. The readiness decision stays NO-GO.**

## Summary

- **Direct-connection fixture gap: missing completion observers.**
  The direct event-114 connection leaves the router in state 12 with no active
  backend, but the capture backend itself completes its internal start. Its
  success handler calls its observer notifier with **zero start observers**,
  then enters stock `active` state (coarse 4, active 14). Stock category setup
  registers the router's completion callbacks; the direct fixture omits that
  setup. See the tenth follow-up and its two preserved observation runs.
- **Earlier boundaries have advanced.** Native settings reset resolves the mode
  lookup in this conditional scenario. The queue-95 task now runs stock command
  0x1d and produces its own reply. The stock silent-SCPU timeout path continues;
  it does not explain this particular empty-observer notification.
- **Native capture activation and original AF-ON press now observed.** Stock-constructed input 0x1a4
  makes native code construct and register the photo category, deliver a real
  0x1b to the main router, and promote its selected category to `0x62b76000`.
  The initial family input reaches router state 6 after 13 jobs. Native class-key
  initialization, preserved constructor-created objects, the queue-10 receiver
  and verified native missing-device callbacks then let the lower capture chain
  activate: **coarse 4 / active 14, one start observer**. An original AF-ON press
  returns with its owned-cache / Subject Detect checks intact. Bounded heap
  reuse and native queue-92/94/95 scheduling let the engine-routed original
  button/SCP matrix complete **28/28** under the declared fixtures. Normal boot, real hardware acquisition,
  input timing and the inherited OS/device fixtures remain unproved.
- **Where focus is driven.** AF-ON's `setAflState` produces GUI lock-state and
  live-view power-saving notifications. The AF worker's `LOCK_START` comes from
  AF-command queue 95 entries 42 and 44. Run 6 now observes an original
  AF-ON press enqueue **0x2a (42)**. Later probes execute the downstream
  **LOCK_START** chain and native acknowledgement with queue-92 scheduling and
  persistent blocked-task contexts. Only the first AF-ON press submits
  LOCK_START: later starts await a display-output completion in the fixture.
  These software results do not establish physical acquisition or synchronization.
- **Deployment follow-up:** the newer local installer, live alias audit and
  interrupt-context finding are in
  [HARDWARE-STAGE0-RECORD.md](HARDWARE-STAGE0-RECORD.md). The task-context
  mutex replacement is checked separately from the earlier 28/28 installer.
- **Still open:** acceptance gates 2–4 (orientation, synchronisation, installation
  and recovery), normal boot, physical AF acquisition and camera safety.

## Probe index

These are supplemental probes, outside `scripts/run_om3_live_offline.ps1` and
the original 7 November full run. The table lists the early probes; later
follow-ups name their additional scripts and evidence folders.

| Probe | Output folder (`analysis/button-af/readiness/`) | Outcome | Adds |
|---|---|---|---|
| [OM3CaptureKernelModelProof.java](scripts/OM3CaptureKernelModelProof.java) | `capture-kernel-model/` | BOUNDARY at transport `0x6007a7b5` | Kernel message-buffer, dispatch, event-flag and command-guard models; static ROM message buffers; stock task-207 loop run natively |
| [OM3CaptureLinkProof.java](scripts/OM3CaptureLinkProof.java) | `capture-link/` | BOUNDARY at interrupt-mask register `0x9b8831a0` | Native transport; data-queue and link spin-lock models; stock port-2 task run natively |
| [OM3CaptureTimeoutProof.java](scripts/OM3CaptureTimeoutProof.java) | `capture-timeout/` | BOUNDARY at mode lookup `0x605712de` (key 0) | Silent-SCPU timeout; message-buffer delete; damage-log sink; AF-queue and mode-record logging |
| [OM3Disasm.java](scripts/OM3Disasm.java) | (writes to a named file) | n/a | Read-only linear disassembly of ranges Ghidra never discovered as functions |

Each output folder has an `evidence-manifest.json` with SHA-256 hashes of the sources
and results. To rerun one, close any Ghidra GUI that uses the project, set `JAVA_HOME`
to `tooling/jdk-25.0.5+8`, and run from the project root:

```powershell
tooling/ghidra_12.2_PUBLIC/support/analyzeHeadless.bat ghidra-projects OM3_main_full -process '*' -noanalysis -readOnly -scriptPath scripts -postScript OM3CaptureTimeoutProof.java analysis/button-af/readiness/capture-timeout -log analysis/button-af/readiness/capture-timeout/run.log
```

Only one headless run can hold the project at a time. Another tool's runner
(`research/om3_af_profiles/run_offline.py`) also uses this project and caused lock
failures during this work.

## New static findings at the capture-connection boundary

The current conditional connection probe stops at `0x600303f5`, inside `0x600303db`,
when it reads `0x97f00004`. The decompiled kernel code explains this boundary:

- **`0x97f00004` is a per-core table of kernel control-block pointers.** All 40
  references to that immediate are in kernel services at `0x600302be`–`0x60031369`.
  Each reads `*(0x97f00004 + [0x8050]*4)` and dereferences the result. They do not
  read one global.
- **`[0x8050]` behaves as a core-ID register.** `0x60033387` sets bit
  `1 << [0x8050]` in the halfword at `0x97f00000`. It then spins until the mask
  equals `(1 << n) - 1`, where `n` is read from control-block offset `+0x17c`.
  This is a startup barrier where every core reports in. `0x60036abc` clears the
  same mask. The kernel is therefore a multi-core RTOS, not a single-core scheduler.
  This is inferred from code shape; no vendor name has been recovered.
- **`0x600303db` is an automatic-ID object-create service.** It accepts attribute
  values 0 and 1 and returns `-11` (`0xfffffff5`) for anything else. It returns
  `-25` (`0xffffffe7`) when the control-block context byte at `+0x1c` forbids the
  call. It returns `-17` (`0xffffffef`) when packet word +4 is zero. When allocation
  fails it returns `-33` (`0xffffffdf`). It allocates an ID through `0x600358a7` and
  copies a four-word creation packet. These codes match μITRON 4 conventions
  (`E_RSATR`, `E_CTX`, `E_PAR`, `E_NOMEM`). That is a strong analogy, not a
  confirmed API. The sibling `0x600302a9` is the same pattern with a three-word packet.
- **Startup zero-fills the kernel region and then hands off.** `om3_application_entry`
  (`0x60021020`) clears `0x97f00000`–`0x97f01ffc` through `0x60021694`. It then
  calls `0x600210c5`, which configures the `0x8000`–`0x8a80` control registers
  through `0x60030088` before continuing startup.
- **The command transport's peer is outside the main CPU.** `0x6007a7b5` checks
  that the length is ≤ 0x100. It picks a channel below 0x20 and copies the packet
  with the imported routine `0x50002909` into a 256-byte slot at
  `0xa32c65b0 + channel*0x100`. It then calls `0x60037413` and `0x6004dde5` and
  waits in `0x6007a921`. This looks like a shared-memory mailbox to another
  processor or hardware block. Which component answers on port 2 has not been
  established.

## Follow-up emulator run: capture connection advanced to the transport

Later the same day, the new probe [OM3CaptureKernelModelProof.java](scripts/OM3CaptureKernelModelProof.java)
extended the conditional event-114 connection past `0x600303db`. It treats the
kernel services as explicit models, in the same way the harness already models
semaphores, mutexes and event flags. It did not run the kernel natively with a
one-core override, as originally planned, because that would have departed from
the harness's established approach. Evidence:
[outcome](analysis/button-af/readiness/capture-kernel-model/kernel-model-outcome.txt),
[trace](analysis/button-af/readiness/capture-kernel-model/capture-connection-trace.txt)
and [manifest](analysis/button-af/readiness/capture-kernel-model/evidence-manifest.json).

**Result: BOUNDARY at native transport `0x6007a7b5`, port 2, timeout 5000, length 36.**
This time the path starts at the actual caller, not a supplied direct input:

1. **Caller creates a reply buffer.** `0x6004f3bd` → `0x6004d886` →
   `0x600303db` creates reply message buffer 1028 (maxmsz 16, mbfsz 16).
2. **Caller registers its name.** Stock code registers the buffer's name under
   dispatch disable.
3. **Caller sends the request to task 207.** `0x6004d171` → `0x60037598` sends
   16 bytes to static message buffer 207:
   `04040000 02000000 08000000 8cfe0470`. The words are the reply-buffer ID,
   the caller task ID, command 8 and the argument pointer.
4. **The stock task-207 loop picks it up.** The caller then waits on 1028 with an
   infinite timeout. At that point the **stock task-207 loop `0x610615f5`** runs
   natively in its own saved-register context and on its own stack. It receives
   the message from 207 and dispatches command 8 through its jump table at
   `0x612e7a28`, via `0x61061b4f` → `0x61061ba0` → `0x61061a6d` → `0x61061cdf`.
5. **The loop drains stale completions.** `0x61061c9f` polls static event
   flag 225 (from the ROM word at `0x600430de`; attribute 4, initial pattern 0)
   with timeout 0. It gets a timeout, as the stock retry loop expects.
6. **Native code builds the packet and calls the transport.** `0x61061c4c` →
   `0x6007a931` builds the 36-byte packet
   `0b007a00 00001c00 40000000 04000000 8cfe0470 00000000 00000000 a7190661 8cfe0470`.
   This is the same header, command 0x40 and callback `0x610619a7` as the earlier
   direct-input transport probe. The argument pointer now comes from the caller's
   real request instead of a supplied fixture.

Stock ROM findings this run depended on:

- **`0x6003bab4` holds the static message buffers.** It has 218 records of
  `{id, attr, maxmsz, mbfsz, buf}`, the same layout as the `0x600303db` create
  packet. All 218 pass structural checks. Record 207 has maxmsz 16 and mbfsz 80.
- **`0x6003ab34` holds the static event flags.** It has 283 records of
  `{id, attr, initial pattern}`.
- **`0x60037598` and `0x6003727e` are timed send and receive on message buffers.**
  `0x60038ea5` is a timed event-flag wait, called as (id, pattern, mode,
  pattern out, timeout on the stack). They use the same per-core ID encoding:
  core in bits 12–14 and index in bits 0–11.
- **Task 207 waits after submitting.** `0x61061cdf` submits the packet, then waits
  on flag 225 with pattern `0x80000000 | x` and a 5000 ms timeout. The camera's
  completion would arrive through that flag.
- **Startup routine `0x6004cfd9` publishes per-core message-hook tables.** It
  writes them to `0xa3258350`–`0x5c`. The send path dereferences them.

Explicit models and fixtures added: kernel message-buffer, dispatch,
event-flag-wait and command-guard models. A polling wait returns a timeout; a
positive-timeout wait is a boundary and never a success. Request bytes 6–7, which
the stock caller never writes, are copied as zero. Stock `0x6004cfd9` runs lazily
before the first RPC, and its boot ordering is not established.

**What this closes:** gate 1 no longer has to bypass the task-207 scheduling and RPC
layer. **What remains:** submission into the mailbox, the port-2 peer, the completion
on flag 225, the reply back to buffer 1028, and any real AF acquisition. The
normal producer and timing of event 0x114 are also still unproven.

## Second follow-up: transport run natively to the hardware link

The probe [OM3CaptureLinkProof.java](scripts/OM3CaptureLinkProof.java) extends the run
above. It lets transport `0x6007a7b5` execute natively instead of stopping at it.
Evidence: [outcome](analysis/button-af/readiness/capture-link/link-outcome.txt),
[trace](analysis/button-af/readiness/capture-link/capture-connection-trace.txt) and
[manifest](analysis/button-af/readiness/capture-link/evidence-manifest.json).

**Result: BOUNDARY at hardware.** The path is now native from the event-114
connection to an on-chip peripheral register.

- **The "port" is not a hardware mailbox.** Port 2 is kernel **data queue 2**.
  The transport takes a free slot from the 32-slot bitmap at `0xa32c8630` (slot 1
  here) and copies the 36-byte packet into `0xa32c66b0`. It records the length in
  the table at `0xa32c85b0`, then posts the slot pointer with data-queue send
  `0x60037413`.
- **The ROM configures five static data queues.** The table at `0x6003b908` gives
  queue 2 a capacity of 0x20 entries.
- **Port 2's receiver is stock task `0x6007908c`.** It reads port ID 2 from ROM
  `0x6004316c`, waits through `0x6007a72f` (data-queue receive `0x600370b6`),
  copies the packet out and frees the slot. For a type-0x0b packet, with link
  state `0xa32c5dc5` not 0 or 2, it queues `len+8` bytes into the transmit ring
  at `0xa32c60c0` through `0x60072754`.
- **That task's initialization enables an interrupt on a link peripheral.**
  Init helper `0x6007912c` enables logical interrupt 102, using ROM descriptor
  `0x60026900[191]`: peripheral base `0x9b881b80`, vector 0x77, handler
  `0x60074d3f`, status register `0x9b883060`, mask register `0x9b8831a0`. The
  first read of that mask register (at `0x60074890`) is where emulation stops.

Added models: the link spin-lock, data-queue send/receive, and static data queues
loaded with structural checks. When task 207 began its 5000 ms wait on flag 225,
the port-2 task was scheduled from its entry in its own saved context. No register
values, interrupts, peer bytes or completion events are supplied.

**What this means for gate 1:** the remaining software path ends at a physical link
controller. The 36-byte command-0x40 request leaves the main application through a
transmit ring driven by the interrupt-102 handler. The completion that would set flag
225 has to come back over that link from another device. Its identity has not been
established; the packet header type 0x0b is the lead. Offline, this boundary can only be
crossed by co-emulating the peer, if its firmware is one of the other image components,
or by observing the stock camera.

## Third follow-up: the peer is the SCPU (component 0107)

This pass was static reading only: no new emulator run.

**The port-2 link goes to the SCPU, the Cortex-M secondary MCU in component 0107.**
Its firmware is in the update image, mapped at `0x08000000`.

Evidence:

- **The link driver's kernel-object names.** The names passed to the
  error checker by `0x6007a72f`/`0x6007a7b5` are the ROM strings
  `PER_CMDM_DTQR` (`0x60125acc`) and `PER_CMDM_DTQS1` (`0x60125ada`).
  `PER_CMDM_DTQS2` sits beside them.
- **Neighbouring strings name the SCPU.** The same string block contains `SCPU RST!`,
  `PerScpuSysW`, `PerScpuMemW`, `PerScpuMemR`, `PerScpuFirmup`, `SCPU Build:` and the
  `per scpu mng/dbgall/lpdbg` debug commands.
- **Task 207's receive check also names it.** It passes the name `USB SCPU_CONN`
  (`0x612e7a1a`). The reply buffer's registered name is `MBF_QIFIMDF_RES1`
  (`0x600842e2`).
- **The SCPU firmware has the matching module.** 0107 contains
  `...\Scpu\dev_pack\source\communication\com_cmdm_task.c`, a "CMDM" command
  manager, with messages such as `[CMDM] Not recieved [POWER ON] Command <cmd> <subcmd>`.
  Its literal pool at `0x08012abc`–`0x08012ac8` points at those strings, which
  confirms the `0x08000000` mapping. Its other modules cover battery, charging,
  USB-PD, power management and `asic_req_info`.

**How the link works on the main side:**

- **Request and reset lines.** The handshake uses logical pins: `0x66` is an
  interrupt input (interrupt-controller channel 191, vector 0x77) and `0x67` is a
  request output. `0x6b` is an output pulsed with a long delay by `0x600795fb`,
  consistent with resetting the SCPU.
- **Transmit.** Frames go out from the ring at `0xa32c60c0` through the `0x60079dcb`
  and `0x60079e49` transfer routines.
- **Receive.** Incoming frames go to dispatcher `0x60078fbd`. Byte 1's high nibble
  selects one of five handler tables at `0x601255a0`, and the low nibble selects
  the entry.
- **Group 4, entry 0 is the reply to our request.** Handler `0x60025447` matches
  the frame against the outstanding-request table at `0x62b7f0d0` (through
  `0x60025493`). It copies the reply into the waiting request and sets flag 225
  (`0x6004cd21`, bit from `0x61061a5f`). That releases task 207's 5000 ms wait.
- **Failure path.** `0x61061953` instead sets flag 225 with `0x80000000`, which
  task 207 treats as failure.

The other small component, 010e (`luke_main`, cpu0/cpu1, `task_detect`,
`task_drive`, accelerometer and yaw/pitch/roll errors), looks like a motion-sensing
or drive controller with its own `MS`/UART link. Nothing tied it to port 2.

**This changes how gate 1 should be read.** The conditional event-114 connection
reaches the SCPU command manager, which by its strings handles power, battery and
USB. Together with the `USB SCPU_CONN` name, this suggests that the exchange the
probe follows is a power or USB-state query made while the capture backend
connects. It is not the AF acquisition itself; that is an inference from names, not
yet confirmed by reading the SCPU handler. A successful SCPU reply would get the
backend connected, but the AF request path would still have to be traced after that.

**Can it be run offline?** In principle, yes: both sides of the link are in the
image. Getting a genuine reply would need these pieces:

1. Find the SCPU's command-0x40 handler (group 4) under `com_cmdm_task.c`. The
   existing SCPU decompilation covers only 1,385 functions, and the CMDM region
   around `0x08012a..` needs function recovery.
2. Recover the physical framing between the transmit ring and the SCPU's serial
   receive, and the pin-0x66/0x67 handshake. The device behind the main side's
   transfer ops still has to be resolved.
3. Run the SCPU handler on the received frame, using a Cortex-M Ghidra emulator
   with its own peripheral models. Its reply then goes back through dispatcher
   `0x60078fbd` → `0x60025447` → flag 225. Any SCPU hardware reads, such as battery
   ADC or charger I²C, would themselves be new boundaries.

## Fourth follow-up: where AF is actually driven

This was mostly static reading, plus one emulator probe at the end.

### What the stock AF-ON route (`setAflState`, `0x60b14eb4`) produces

Neither of its two requests starts focusing:

- **`0x3bf` → a display notification.** It goes to the AE/AF-lock controller
  (`CmpSts_AEAFLockController.cpp`), whose handler at `0x60ca424d` (compare at
  `0x60ca4a20`) wraps it as request **`0x522`** (built by `0x60b28ca9`, vtable
  `0x60e199f8`, a subtype of `0x4f6`). It submits that to the event-bus singleton
  `0x62b4e834` (vtable `0x60e1d408`). The bus dispatcher `0x60b2f091` delivers it to
  each subscriber that accepts it. The subscribers that register `0x522` are in the
  record-view GUI (`Rec_Viewer.cpp`; `0x61244a67` and `0x61244f8c` register the
  `0x516`–`0x52e` range), so `0x522` is an AE/AF-lock display notification.
- **`0x5e9` → a power-saving restriction.** It is handled in `CmpCst_Function.cpp`
  (`0x60d2607b`, compare at `0x60d2674c`). That handler calls `0x60c176ed`,
  `ctrlRestrictStillStandbyLvSaving(factor, restrict)`, which sets or clears a bit
  in the mask at `+0x1280`. That stops live view going into standby power saving.

### Where focus is driven

The AF worker task `0x609df84d` (`LOCK_START`, `RELEASE_READY_START`, …) receives
on queue **94** (ROM `0x60043230`). Every send to that queue was mapped from its
message constant:

- **`LOCK_START` (0x100)** comes only from `0x603c86d7`, `0x603c886a` and
  `0x603c895e`. All three are reached only from the **AF-command task**
  `0x6031787e`, which reads 16-byte requests from queue **95** (ROM `0x60043232`)
  and dispatches on word +8 through the 93-entry table at `0x6031e224`:
  - Entry **42** (`0x603c86d7`) sends `LOCK_START`, `IAF_PAUSE`, `IAF_RESTART` or
    `TAKE_ONCE_START`.
  - Entry **44** (`0x603c8d14` → `0x603c895e`) also sends `LOCK_START`.
  - Entry **43** (`0x603c8af3` → `0x603c8b00`) sends `LOCK_END`, `IAF_*` or
    `TAKE_ONCE_END`.
- **Other worker messages have their own senders:** `LOCK_START_END` (`0x603e0d0a`,
  `0x609edbc6`, `0x609edce8`), `LOCK_START_END_FAST` and `LOCK_RESTART`
  (`0x60711ac1`, `0x60711b03`), and `RELEASE_READY_START` (`0x603dc7e7`,
  `0x603ee0ad`). The full map is saved in [worker-senders.json](analysis/button-af/worker-senders.json). It comes from a heuristic static scan, so register-computed messages are missing.
- **Only one function sends entries 42–44, and its known callers only stop AF.**
  The sole static sender is `api_rec.c` `0x6043f7c5`: mode 1 → 42, mode 4 → 44,
  anything else → 43. Its only direct callers are `0x60afa380`
  (`startShootingService`, power shutdown and wake) and `0x60b0da13`
  (`endShootingService`). Both pass mode 0, so they only send **43** (end AF). No
  static producer of 42 or 44 was found. It is likely an indirect or
  register-computed request, which needs a dynamic trace.

**Consequence for the extension:** the AF-ON profile switch should not rely on the
`0x3bf`/`0x5e9` path for focus timing. The focus start that matters goes through
queue 95 entry 42/44 to worker `LOCK_START`, and the earlier analysis already found
the target-priority controls inside that worker. The physical AF-ON producer of
that request is still unidentified.

### Emulator probe: the SCPU modelled as silent

[OM3CaptureTimeoutProof.java](scripts/OM3CaptureTimeoutProof.java) lets task 207's
5000 ms wait end in the stock timeout code (-50) instead of stopping. That models
an SCPU that doesn't answer; no reply bytes are invented. Evidence:
[outcome](analysis/button-af/readiness/capture-timeout/timeout-outcome.txt) and
[manifest](analysis/button-af/readiness/capture-timeout/evidence-manifest.json).

1. **The stock code handles the timeout.** Task 207 replies to the caller's buffer
   1028 with status `0xfffe`. The caller receives the reply and deletes the buffer.
   The damage-info logger `0x60024d0e` records the failure; it is logged here, not
   run.
2. **Connection processing then continues natively.** It runs until lookup
   `0x605712de` finds no entry and reports stock diagnostic `0x0e004504` (line 0x56b).
   The next section explains why: the table is complete, but the key requested is 0.
   This is a harness gap, not a hardware boundary.
3. **The run never reached the button handlers.** The original handlers were not
   reached, and no sends to queue 94 or 95 were observed.

## Fifth follow-up: why the run stops, and the hunt for the AF start request

**The registry is not empty; the key is missing.** The table at `0x606ea406` is
static ROM data: 65 entries of 0x46 bytes, keyed by the halfword at +0x44. The
lookup fails because the caller asks for key **0**. That key is byte +0x2a of a
record handed to the code at `0x60570f8e`, which Ghidra never discovered as a
function; its byte read is at `0x60570f98`. The valid keys appear to be imaging or
readout mode IDs, and the harness never set that byte. Picking a value would
mean inventing camera state, so the probe stops there. Disassembly helper:
[OM3Disasm.java](scripts/OM3Disasm.java).

**A fixed-command search for the AF start request finds no production sender.**
Raw-byte scans cover code outside Ghidra's discovered functions (results in
[worker-senders.json](analysis/button-af/worker-senders.json)):

- **Queue-ID loads outside discovered functions.** There are 11 for queue 95 and
  17 for queue 94. The queue-94 ones send mode, movie, release-idle/take, MF and
  `LOCK_START_END_FAST` messages; none sends `LOCK_START`.
- **The other undiscovered queue-95 sites are the debug shell.** `0x603ca36f`
  parses `argv[1]` and forwards any AF command index from 0 to 0x5c. It is a
  developer console, not the production route.
- **`0x6043f7c5` has exactly two callers in the whole image** (`0x60afa39f` and
  `0x60b0dad9`). Both select entry 43.
- **The generic request helper never sends 42 or 44.** Of all 128 calls to
  `0x60416fac`, 16 target queue 95, with commands {3, 4, 6, 15, 16, 22, 26, 29,
  39, 43, 48–51, 60}.
- **Nothing calls AF-command entry 42 directly.**

**Conclusion.** The production request for AF-command entry 42 or 44, and so the
worker's `LOCK_START`, is computed at runtime: the command arrives in a register
or comes from a table. Static constant search can't find it. The worker messages
that do have fixed senders are candidates for the ordinary half-press route:
`RELEASE_READY_START` (`0x603dc7e7`, `0x603ee0ad`), `LOCK_START_END`
(`0x603e0d0a`, `0x609edbc6`, `0x609edce8`) and `LOCK_START_END_FAST`
(`0x60711ac1`, `0x60711b03`). An earlier report found that `LOCK_START` and
`RELEASE_READY_START` invoke different target-priority controls (B and A). If
that holds, the two buttons may already use different worker entry points. This
is unconfirmed until a dynamic trace shows which one each button sends.

**What a dynamic trace needs.** The run has to get past the connection step
without invented state. That means a genuine value for the mode record's byte
+0x2a, captured from a stock camera or recovered from the code that fills that
record during normal startup. Alternatively, the original handlers could be run
against the AF-command task directly, bypassing the backend router; that has
to be recorded as a separate, weaker probe.

## Sixth follow-up: where the mode record comes from (partly resolved)

This work was stopped part-way, then partly resolved; see the update at the end
of this section.

**What the timeout probe logged at the lookup.** The probe now logs the record and
the caller when `0x60570f8e` is entered:

- **The record is a local structure on the caller's stack.** It was at
  `0x7004fcd8` in this run, and nearly all of its first 0x40 bytes are zero.
- **The return addresses on the stack give the call chain:**
  `0x60405206` → … → `0x605aa1de` → `0x60563043` → `0x605707f5` → (record
  translator) → `0x60570f8e` → `0x605712de`.
- **Log lines:** `AF-MODE-RECORD` and `AF-MODE-RECORD-STACK-CODEPTRS` in
  `capture-timeout/timeout-trace.txt`.

**How the record is built (static reading):**

- **`0x605aa1de` allocates and zeroes it.** It zeroes several stack structures,
  among them a 0x5c-byte record at `sp+0x28`, plus a 0x290-byte working block. It
  then calls `0x605aa37d` to fill the record.
- **`0x605aa37d` fills it from getters and settings.** Byte 0 comes from
  `0x605ac848()`, byte 1 from `0x605ac89c()` and byte 2 from `0x6031c0eb()`.
  Later bytes come from stock setting reads through `0x60063380`, the settings
  getter the harness answers with factory defaults. The filler runs from
  `0x605aa37d` to its return at `0x605aaa35`. Ghidra's exported listing for it has
  gaps, so [OM3Disasm.java](scripts/OM3Disasm.java) is needed to read it whole.
- **A translator turns record byte 2 into a lookup key.** Record byte 2 is a raw
  mode code. Code at `0x60570947`–`0x60570a8f` checks that it lies between 3 and
  0xdc, translates it through the hash/jump table at `0x606eb638` into a key (for
  example 4, 5, 6, 0x45–0x4a, 0x55, 0x56, 0x5b, 0x91, 0xc6), and stores the key
  at +0x49 of the working block. All of those keys appear in the 65-entry table at
  `0x606ea406`.
- **The failing lookup reads a different byte.** `0x60570f8e` reads byte **+0x2a**
  of the record passed in D1. That byte was 0 in this run.

**Not yet established:**

- **Where byte +0x2a is written.** It isn't known whether it comes from a stock
  setting, a getter or a copy from another structure, and no instruction storing to
  record offset +0x2a inside the filler had been identified when work stopped.
- **Whether the zero is genuine.** It may be a real consequence of the harness's
  factory-default settings, or of a value the earlier SCPU timeout left unset.
- **What value a stock camera would have there**, for the current shooting mode.

**Update, resolved later on 7 November.** This used the reviewer disassembly in
`analysis/review/disassembly-20261107/`, which another session produced, plus
logging-only additions to the timeout probe:

- **The record isn't from the filler.** The record passed to `0x60570f8e` is not the
  `0x605aa1de` record. It is a 0x2c-byte local that `0x605707f5` zeroes at its
  `sp+0x28` and passes as D1, at the call at **`0x60570adc`**. The return address
  logged earlier was a stale MDR value.
- **Byte +0x2a is the translated mode key.** It is written by
  `movbu D2,(0x52,sp)` at `0x60570a8a`. When the raw mode code is below 3 or above
  0xdc, the translator copies it through unchanged (`0x60570a5d`).
- **The raw mode code came back 0.** `0x6031c0eb` read setting `0x4501`, took its
  default branch at `0x6031c159`, and returned the value of setting `0xc011`[0],
  which was **0**. Log lines: `AF-RAW-MODE-GETTER`, `AF-MODE-SETTING-READ` and
  `AF-RAW-MODE-CODE` in `capture-timeout/timeout-trace.txt`.
- **The native settings store supplied it.** Those reads went to the native
  settings store in the harness, not to the factory-default model, which logged
  nothing for them.

So the stop is caused by a settings value that the harness's settings store holds
as 0. The getter itself runs natively, but that does not establish that its input
represents a normally initialized camera. The initialization distinction was
investigated in the next update.

### Further disassembly, 7 November: two default layers explain the zero

**Result:** the source of the harness's zero is established, and a stock reset
path supplying **3** is established. Three is a firmware-derived reset default;
it is not a measurement of the camera's current shooting state. The timeout
probe was not rerun in this disassembly-only follow-up.

Evidence is in [sixth-followup-settings](analysis/review/sixth-followup-settings/).
Its [manifest](analysis/review/sixth-followup-settings/evidence-manifest.json)
pins the decoded payload and relevant harness sources. Fourteen bounded Ghidra
listings contain 1,108 instructions / 2,975 bytes, checked for continuity and
byte-for-byte equality against that payload. This verifies decoding provenance,
not reachability of every instruction in the windows. Reproduce the ROM-table
checks and listing checks with
`python analysis/review/sixth-followup-settings/verify_evidence.py` from the
research root. The Ghidra project was opened read-only.

**1. The low-level bank template really contains zero.** Native setting
`0xc011[0]` is a one-byte value. Its bank-7 ROM record is at `0x6011efd4`, with
payload **00** at `0x6011efd8`. Setting `0x4501[0]` likewise contains **00**, at
`0x600e51dc`. The bank spans `0x600e4bec`–`0x6011fe20` and contains 1,215 records.
These are low-level bank-template values, not the separate UI reset defaults.
The decoded tables and calculated RAM locations are saved in
[rom-facts.json](analysis/review/sixth-followup-settings/rom-facts.json).

**2. The harness deliberately copies those template bytes into mutable RAM.**
`OM3CoreRAMSettingsProof.initializeRAM()` registers the settings through native
`0x60062536`, then its Java loop copies each ROM value to the registered RAM
pointer and uncached alias. The bank-7 RAM base is `0x62920708`; walking native
width/alignment rules places `0xc011[0]` at `0x6295951e` (alias `0xa295951e`).
The copy therefore supplies zero without a fallback getter or SCPU response.
`nativeRead=true` then lets `0x60063380` read that value natively. Native pointer
registration itself does not apply the UI defaults: `0x60062536` builds metadata
and assigns data pointers, rather than copying the UI reset table.

The live fixture calls this initializer. `OM3FullShooting.shootingRun()` then
invokes selected constructors, including `0x603f215a`, but does not execute the
whole UI initialization entry `0x603f0db6`. Disassembly of `0x603f215a` shows a
hash-index constructor for ROM records at `0x605b5ba0`; it does not reset
`0xc011[0]`. Thus native reads are working, while initialization remains partial.

**3. The stock UI reset default for this same setting is three.** UI setting
**24** maps through row `0x606255bc` of the primary key/index table to
`0xc011`, index **0**. Its factory-default row is `0x605f6df0` in table
`0x605f6d90`, containing LE32 **3**. Native default reader `0x60404f35` selects
that table and returns the value; this is not a constant chosen to pass the test.

The reset routine at `0x604047d9` iterates the primary UI IDs, calls the default
reader at `0x604047db`, and passes the result to `0x60419368` at `0x604047e5`.
That wrapper calls `0x6041937f` unless byte `0x62a96920` equals 1. The bridge
maps the UI ID through `0x60419446` / `0x60419696`, puts the default in A1, and
calls native scalar setter `0x60063431` at **`0x604193c0`**. This establishes a
stock code path from ROM default 3 to the native `0xc011[0]` store, conditional
on reset being invoked and writes not being suppressed. None of the six
model-specific override rows, or their sentinel row, at `0x60600978` changes
UI 24.

**4. Reset is conditional, not evidence of every boot's final value.** In UI
initialization `0x603f0db6`, a nonzero status returned through `0x60419f65`
leads to the reset call `0x604048c3` at `0x603f0de3`. That reset wrapper calls
`0x604047d9`. The underlying status reader `0x60063aec` reads and clears
halfword `0xa32bfb30`. This does not establish the status's producer or prove
that every ordinary boot resets the setting. Persisted settings and later mode
changes must still be distinguished from the reset scenario. The current
camera's value cannot be inferred just from either default table.

**5. Three is a legitimate registry input under the traced branch.** With
`0x4501[0]=0`, getter `0x6031c0eb` returns `0xc011[0]` through `0x6031c159`.
For raw mode 3, the translator searches hash key `3-2=1`; slot `0x606eb640`
points to `0x60570992`, which branches to the raw-value pass-through at
`0x60570a5d`. The resulting key is **3**, before the optional record-flag
overrides at `0x60570a5f`–`0x60570a88`. Registry `0x606ea406` contains key 3
in zero-based slot 4. This establishes a valid stock reset-derived input for
this lookup; it does not prove the remainder of connection processing succeeds.

**Remaining runtime work, outside this disassembly follow-up:** exercise an
explicitly labelled stock-reset initialization scenario, obtain UI 24's value
from native `0x60404f35`, apply it through the recovered native UI-to-core path,
and verify native readback before rerunning the timeout probe. Preserve the
original template-only run as a separate baseline. Such a run can test the
reset scenario without hardcoding 3; it must not be described as a normal boot,
successful SCPU handshake, or proof of either button's AF producer. Full
initialization / persisted-state provenance and the physical button trace remain
open.

## Seventh follow-up: labelled stock-reset scenario probe

**This is a reset scenario, not a normal boot.** The probe
[OM3CaptureResetProof.java](scripts/OM3CaptureResetProof.java) extends the timeout
probe. Output is in `analysis/button-af/readiness/capture-reset/`. The template-only
timeout run in `capture-timeout/` remains the baseline. The SCPU is still modelled
as silent.

**What it does before the event-114 connection:**

- **Runs the stock UI settings reset natively.** It calls wrapper `0x604048c3`
  (→ `0x604047d9`) with the same call form as UI initialization uses at
  `0x603f0de3`, in its own saved register context. The harness instruction cap is
  raised to 200 million for this call only. The reset completed in about seven
  minutes of emulation.
- **Hardcodes nothing.** The probe still contains a narrow fallback (native
  `0x60404f35`(UI 24), then native `0x60419368`). It runs only if the full reset
  hits a boundary; it was not needed in the final run.
- **Takes its check value from the firmware.** The value comes from the native
  consumer: `0x6031c0eb` now returns raw mode code **3** (`AF-RAW-MODE-CODE`), and
  the lookup at `0x605712de` finds key **3**.
- **Dropped an earlier readback.** A direct call to `0x60063380` reported `02`
  before and after the reset, which contradicts what the consumer saw, so that
  readback was removed as unreliable.

**Further models added in this probe only.** The shared harness files are
unchanged:

1. **Severity-1 diagnostic reports return.** Reports through `0x60068a54` with
   D1=1 are recorded and allowed to return, capped at 50. The stock routine returns
   normally on its common paths. Reports of severity 2 or above still stop the run.
   The report seen was `0x24000615` (line 0x15c) at `0x601f0030`, emitted after a
   cache miss in the per-setting pointer cache at `0x6035a038`.
2. **Full multiply semantics.** The `mulq`/`mulqu` extension instructions get full
   32×32→64 semantics (GNU sim `mn10300.igen`) when an operand is outside the shared
   model's non-negative scope. The first such case was signed `-1 × 0` at
   `0x601e8224`.
3. **Event-flag delete.** `0x60031027` is modelled as an event-flag delete, with
   the same `+0x3c+0xa` limit field as wait `0x60038ea5`; it releases waiters with
   -51. It was called from a framework destructor at `0x60dd8c6d`.

**Result: BOUNDARY at the harness instruction cap** (2,000,000 instructions for one
native call). The stop came during connection message processing, after
24 native connection messages. The original button handlers were still not reached,
and no sends to AF queues 94 or 95 were observed. This session did not establish
whether the stop is a retry loop caused by the silent SCPU or simply a long
computation; the investigation was paused here.

**This probe establishes:** with a stock reset applied, the mode-key boundary is
gone, and connection processing runs much further natively. **It does not
establish:** a normal-boot state, a successful SCPU exchange, the button handlers'
AF messages, or any AF acquisition.

## Disassembly handoff for the revised offline plan

Read-only Ghidra work after the seventh follow-up recovered the getter ABI,
numeric conversion, report and event-deletion paths needed for the next bounded
runs. Evidence: [offline-plan-disassembly](analysis/review/offline-plan-disassembly/),
[manifest](analysis/review/offline-plan-disassembly/evidence-manifest.json),
[p-code](analysis/review/offline-plan-disassembly/pcode.txt). Fifteen listings
contain 1,405 instructions / 3,787 bytes verified against the pinned stock
payload. Bounded windows can include adjacent instructions; byte verification
does not establish reachability. No capture probe was rerun, no emulator fix was
installed, and no firmware image was changed. Reproduce checks with
`python analysis/review/offline-plan-disassembly/verify_evidence.py`.

### 1. Readback: A0 is an optional data pointer, not a metadata pointer

At `0x60063380`, D0 is the setting key and D1 the element index. The entry saves
them in D2/D3. **A0=0 requests lookup; A0!=0 bypasses lookup and is used as the
data pointer.** At `0x60063387`, lookup `0x600624d3` returns a metadata record in
A0; `0x60063393` loads that record's data pointer at +4. The paths converge at
`0x60063396`, then call `0x60063a20`. The actual return is `0x6006339f`, with
call form `[d2,d3],0xc`. A missing metadata record returns zero.

For `0xc011`, the value dispatcher takes the unsigned-byte path and reads
`data_pointer + index` at `0x60063a63`. A nonzero stale A0 could read another byte
without looking up c011. This is a concrete hypothesis for the reported 02/03
discrepancy, **not a proven diagnosis of the removed probe**.

There are also two metadata namespaces: `0x600624d3` checks flag `0xa32a9908`,
optionally tries table `0xa32b190c`, then falls back to `0xa32a990c`. Each entry
is eight bytes at `table + 8*(key>>4)`. The c011 slots are `0xa32b7914` and
`0xa32af914`; log the selected entry and its data pointer, not just a presumed
bank address. `0x6006150a` applies a core-specific address conversion through
table `0x600950c8`; core 0 selects the identity return at `0x60061507`.

The consumer has its own cached **data** pointer: `0x6031b333`–`0x6031b340`
calls `0x60063356(c011)` and stores A0 at `0x62b10204`. Getter `0x6031c159`
loads that pointer and calls `0x60063380` at `0x6031c166`. Compare its selected
pointer with an independent read made using D0=c011, D1=0, A0=0. Capture D0
before restoring the saved register context. This tests both stale-pointer and
call-context explanations without forcing a value.

### 2. A confirmed p-code carry defect can make the suspected helper loop forever

`0x6004c266` converts an unsigned 32-bit integer in D0 to a double represented
by D1:D0. It contains no peripheral reads, scheduler waits or SCPU queries.
For nonzero input it splits the integer between D1 and D0, normalizes until
D1 bit 20 is set, and builds the exponent. Its loop is:

- `0x6004c27e`: test D1 bit 20; branch to completion when set.
- `0x6004c286`: decrement exponent in D2.
- `0x6004c28c`: `add D0,D0`, shifting the low word and producing carry.
- `0x6004c28d`: `rol D1`, moving that carry into the high word.
- `0x6004c28f`: branch back to the test.

**The installed language emits incorrect flags for the aliased add.** Its
`mn103_base.sinc` register-add constructor snapshots the destination but not the
source before assigning the result. The emitted p-code at `0x6004c28c` is
effectively `old=D0; D0=old+D0; CF=carry(old,D0)`. Thus CF uses old+result,
instead of old+old. For old D0=80000000, result=0, it incorrectly clears carry.
`rol D1` then loses the bit needed to normalize. VF has the same operand-aliasing
problem. This is present in the compiled language's actual p-code, not merely
an inference from its source text.

[carry-reproduction.json](analysis/review/offline-plan-disassembly/carry-reproduction.json)
records a mathematical reproduction of that p-code order. Inputs 1 and 4 fail
to terminate within 65 iterations with the emitted carry. With correct carry,
they terminate in 31 and 29 iterations respectively and produce the IEEE double
representations of those inputs. Correct arithmetic requires at most 31 loop
iterations for any nonzero u32. This is not a new firmware execution run.

The last saved trace contains three calls to this helper after `0x60c0d365`.
Disassembly identifies its four conversion calls at `0x60c0d379`, `0x60c0d387`,
`0x60c0d393` and `0x60c0d3a1`; inputs come from A2[0], A2[1], A3[0], A3[1].
This makes the defect a strong cap-stop candidate, but the trace does not prove
the exact stopping PC or input. Next, capture that PC/input and verify an
isolated add/rotate sequence, then fix both-source snapshots in the language
constructor (and audit equivalent aliased arithmetic) before rebuilding the
language / clearing decode caches and rerunning. Do not increase the instruction
cap to compensate for this defect. Prior results that depend on these flags
need targeted revalidation; the finding alone does not invalidate every run.
**Fixed and verified on 7 November — see "Carry defect fix (7 November)" below.**

### 3. Multiply and report models: what the reached instructions actually require

The observed extension at `0x601e8224` is bytes **f9 00 ff**, decoded
`udf00 -1,D0`. It follows a signed extension of the halfword at `0x62a5248c`
and stores the low halfword back at `0x601e8227`; this is a sign reversal on
that path. The saved trace shows -1 times 0, with low/high both zero. That
observation does not validate all operand combinations or extension-register
consumers.

The GNU simulator reference identifies this encoding as signed immediate
`mulq`, with a high result in MDRQ; it uses the low result for Z/N and clears
C/V. Register `getx` reads MDRQ. This supports the probe's observed low-result
case; retaining the high result only in Java's `mulHigh` is not a complete
implementation if `getx` is reached. Reference:
[GNU MN10300 simulator](https://raw.githubusercontent.com/RTEMS/sourceware-mirror-binutils-gdb/master/sim/mn10300/mn10300.igen).

`0x601efff9` is the setting-cache consumer behind report **24000615**. It
indexes eight-byte records at `0x6035a038`; that address is **data**, not a
function. On a zero cached pointer it calls `0x60063356`, stores the returned
pointer, then emits the report at `0x601f0030`, D1=1. It resumes at
`0x601f0037`, reloads the cached data pointer and invokes the native setting
getter. There is an actual return at `0x601f0045`, beyond Ghidra's false
CALL_RETURN annotation. The report therefore marks lazy pointer population in
this path; it is not evidence by itself of an invalid setting value.

Reporter `0x60068a54` really can return, but D1=1 alone is not a complete
contract. It saves D1 at SP+28 and tests global state `0xa31936c8`: state 0
takes the short logging-return path to `0x60068f44` / `0x60068f49`; state 9
calls `0x6004f309` before returning. Other states run setting/logging/callback
paths, including tests of the byte at SP+30 and globals `0xa31936c0/c4`.
The caller at `0x601f0030` does not use the reporter's returned D0 before
reloading the setting, but suppressing the reporter still omits its side
effects. Record the global state and callback preconditions before broadening
the return model beyond this caller. There is no basis for treating all
severity-1 diagnostics as equivalent no-ops.

### 4. Event-flag deletion has a larger contract than dictionary removal

`0x60031027` checks caller context via the per-core block's +1c pointer,
decodes core `(id & 7000)>>12` and index `id & fff`, verifies the core count
at +17c and the target core's flag limit at `[+3c]+0a`. Invalid IDs return
**-18**; disallowed context returns **-25**. A valid but inactive object returns
**-42**. The active flag object comes from the target core's +d4 table.

For an active object the routine enters the kernel critical section, walks the
wait list at object+4 and calls `0x6003480e` with **-51** for each waiter
(`0x600310e5`–`0x600310ef`). The release helper writes the wait result at
waiter+40, unlinks it, and updates its local ready/suspended state or the
remote-core path. Deletion may decrement the dynamic-object count, clears the
object's first halfword at `0x60031138`, calls `0x60035dc8`, exits the critical
section, and returns **0**. The current dictionary model establishes only its
declared existing-object / no-waiter case; waiter wakeup, invalid IDs, context,
cross-core behavior and native object bookkeeping remain separate checks.

**Handoff boundary:** these findings supply the immediate disassembly needed
for plan steps 1–4. Button routing, successful SCPU exchange, the physical
orientation producer and cross-core lifetime proof remain open. The latter
work is not established by these bounded settings/kernel/numeric windows.

## Carry defect fix (7 November)

The p-code carry defect in handoff section 2 is now **fixed in the installed
MN10300 SLEIGH language and verified through the compiled emulator**. Evidence:
[carry-fix](analysis/review/carry-fix/),
[diff](analysis/review/carry-fix/mn103_base.sinc.diff),
[manifest](analysis/review/carry-fix/evidence-manifest.json),
[before](analysis/review/carry-fix/before/carry-test-result.txt) /
[after](analysis/review/carry-fix/after/carry-test-result.txt). No firmware
image was changed; the original language files are backed up under
`analysis/review/carry-fix/backup-language/`.

**Root cause.** Four register-register constructors in `mn103_base.sinc` assigned
the destination *before* passing the **source register symbol** to `addFlags` /
`subFlags`. Those macros compute `CF`/`VF` from `carry(a,b)`/`scarry(a,b)` (add)
or `a<b`/`sborrow(a,b)` (sub), so they re-read the source operand *after* it was
overwritten. When source and destination are the same register (`add D0,D0`,
`sub D0,D0`, `add A0,A0`, `sub A0,A0`) the macro read the **result** instead of
the original source, giving wrong carry and overflow. The arithmetic result,
`ZF` and `NF` were always correct.

**Fix.** Snapshot the source into a local before writing the destination
(`local s:4 = <src>; … ; …Flags(o, s, …)`), matching the already-correct AM33
extended-register forms at `mn103_gen.sinc:198–202`. The four constructors are
the only register-register forms that write the destination and then re-read a
register source in a flag macro (cross-file A/D forms cannot alias; `cmp` does
not write; `addc`/`subc` already snapshot; `inc dn1_0` uses an immediate). All
three variant `.sla` files were recompiled.

**Verification.** [OM3CarryDefectTest.java](scripts/OM3CarryDefectTest.java)
emulates the real `add D0,D0` (`0x6004c28c`) and `rol D1` (`0x6004c28d`) of the
`0x6004c266` normalize loop through `EmulatorHelper`, which decodes with the
compiled `.sla`. Before: `add D0,D0` of `0x80000000` gave `CF=0 VF=0`, of
`0x40000000` gave `VF=0`, and the normalize loop never terminated. After:
`CF=1 VF=1` and `VF=1` respectively, and the loop terminates at iteration 21.
Sanity inputs `0xffffffff` and `0x00000001` are identical before and after, and
the `D0` result is identical in every case — a pure flag correction.

**Consequence and limits.** This removes a confirmed non-termination mechanism
behind the 2,000,000-instruction cap-stop in capture-reset connection
processing, **without** raising the instruction cap. It does not by itself prove
the cap-stop had no other cause, establish a normal boot, a successful SCPU
exchange or any AF acquisition. Prior emulator runs that branched on `CF`/`VF`
after an aliased same-register add/sub need targeted revalidation; runs not
sensitive to those flags on such an instruction are unaffected.

**Rerun of the blocked probe with the fixed language.** The capture-reset probe
was rerun unchanged (same 2,000,000-instruction cap, **not** raised; SCPU still
silent) into
[capture-reset-carryfixed](analysis/button-af/readiness/capture-reset-carryfixed/)
([rerun-outcome.txt](analysis/button-af/readiness/capture-reset-carryfixed/rerun-outcome.txt)),
with the baseline preserved at `capture-reset/`. The baseline's last three trace
lines are three consecutive `native-call:6004c266` before the boundary — it was
stuck inside the carry-defective converter at the instruction cap, with **zero**
queue-95 sends. With the fix, `0x6004c266` terminates and the connection runs
past it: it receives on buffers 207 and 1028, creates reply buffer 1032, **sends
a 16-byte command to queue 95** (bytes `08040000 02000000 1d000000 4c70a962`;
word 0 = `0x0408` = 1032, the reply-buffer id), then issues a blocking receive on
buffer 1032 with an infinite timeout. No `Native bound exceeded` this run; the
terminating boundary is `Message-buffer receive would block id=1032`, and the
final connection log is `state=12 backend=00000000` (backend not connected).

This **confirms** the cap-stop was the carry-defective non-termination in
`0x6004c266`, and it is the **first queue-95 send observed** in any of these
probes. Decoding the captured envelope against the queue-95 dispatch map (below)
shows **command index `0x1d` / 29 → handler `0x603c641a`, a "specialized-handler"
that is NOT the AF start/end family** (`0x2a`/`0x2b`/`0x2c`). So this send is part
of the connection/capture handshake, **not** an AF focus request, and it carries
the reply-buffer id rather than a LOCK_START. What handler `0x603c641a` does is
not disassembled here. The new stop is a genuine blocking IPC receive that only a
serviced queue-95 handler or the SCPU reply chain would satisfy — the harness
refused to fabricate a reply. Normal boot, a successful SCPU exchange, the button handlers,
backend connection and AF acquisition remain unestablished. This relocates the
gate-1 boundary from a tooling artifact to a real peer dependency; it does not
close it. **NO-GO unchanged.**

## Gate-by-gate status

| Gate | Can it be closed offline? | What is actually missing |
|---|---|---|
| 1. Real capture-backend connection and a successful request/reply | **Software path: done up to the hardware link. Reply: not offline.** The path runs natively through task 207, the transport and the port-2 task, then stops at the link peripheral `0x9b881b80` (interrupt 102). | (a) The normal producer of event 0x114. (b) The SCPU link framing and handshake (pins 0x66/0x67). (c) The SCPU (0107) command-0x40 handler's reply, which would set flag 225 through `0x60025447` and lead to a reply to buffer 1028. This exchange appears to be a power/USB query, so the AF request path after the backend connects remains to be traced. |
| 2. Physical orientation producer, target edit and display | **Partly.** The producer can be traced statically. Exercising it needs the stock UI task running. | The sensor-driver → orientation-code path, plus stock target-edit and display events under a running GUI task. |
| 3. Synchronisation and lifetime of staged target records | **Design work, yes. Proof, no.** | The kernel is multi-core. So cross-core visibility, not just interleaving within one thread, has to be argued from the core memory model and the kernel's lock primitives. A single-thread emulator can't demonstrate it. |
| 4. Full init, settings reload, updater acceptance, recovery | **No.** | Only real hardware shows whether the updater accepts the image and whether recovery works after a failed modified boot. Static work can only narrow the risk. |

## Queue 95 decoded: request, dispatch, AF operations and replies

Queue 95 is the **AF-command task's message buffer**, not the AF worker itself.
ROM halfword `0x60043232` contains decimal 95; task `0x6031787e` receives
16-byte requests through `0x60318d0a` with an infinite timeout. Its state/context
base is `0x62a67e20`. This is a static decode; no camera or new full connection
run was used.

Evidence: [queue95](analysis/review/queue95/),
[complete dispatch map](analysis/review/queue95/dispatch-map.json),
[manifest](analysis/review/queue95/evidence-manifest.json). Thirteen read-only
bounded listings contain **1,641 instructions / 4,338 bytes** checked against
the pinned decoded payload. The map extracts all **93 command slots and 52
distinct handler addresses** from ROM. This decodes the whole dispatch table;
individual payload semantics are established here for the AF start/end family,
not all 93 commands. Adjacent bytes in bounded listings are not necessarily
reachable instructions.
Recheck with `python analysis/review/queue95/verify_evidence.py`.

### Request and reply format

All fields are little-endian. The 16-byte request contains:

- **+00 u32:** reply message-buffer ID; zero suppresses the common reply.
- **+04 u32:** correlation word echoed in replies. The ordinary synchronous
  builder writes the caller task ID into its low halfword through `0x6003193e`;
  do not assume its upper halfword is initialized or that every caller uses a
  task ID. The worker uses this position for completion bits on relevant paths.
- **+08 u32:** command index, valid range **0..92 (0x00..0x5c)**.
- **+0c u32:** pointer to command-specific payload in camera/emulator RAM.

`0x603178e4` stores the current request pointer at context+154, loads the
command at `0x6031790e`, checks unsigned `<0x5d`, and calls
`LE32[0x6031e224 + command*4]` at `0x6031792c`, with **A0=request,
A1=context**. Out-of-range commands retain status **0x4b01**. Thirty-four
slots point to the same unsupported-status stub `0x603c5206`; four point to
the zero-status stub `0x603c520c`. Commands 5, 6, 68 and 69 instead forward
the original 16-byte request to **queue 96** through `0x60317a35/0x60317a3a`.
After forwarding, `0x60317a50` clears the original envelope's reply ID, suppressing
the queue-95 common reply for that request. Do not assume every slot is a
separately implemented command or that queue 95 itself replies to forwarded work.

The low 16 bits of the handler result pass through `0x60317bec`: nonzero
global `0x62a67f14` overrides the result. The dispatcher clears context+154
and calls `0x60318ce2`. When request+0 is nonzero, that helper sends a
**12-byte reply**: status u16 at +0, unspecified bytes +2..3, original
correlation word at +4, and original payload pointer at +8. It does not put
the command ID in that reply. Match the reply using its destination and
correlation/payload, and record the status override. A zero reply status alone
does not establish focus acquisition.

The ordinary synchronous producer `0x6004f3bd` allocates a 16-byte envelope,
a 12-byte reply buffer and a reply message buffer; fills command and payload
at `0x6004f41a/0x6004f41d`; sends the request; waits for a reply; then deletes
the reply buffer object and returns its status halfword. The payload is passed
by pointer, not serialized/copied by this envelope builder. An emulator must
therefore preserve its lifetime while the receiver or worker uses it.

### AF start/end command family

IDs below are both hexadecimal and decimal to avoid mixing queue IDs with
command IDs:

- **0x2a / 42 → `0x603c86d7`: bit-selected operation start.** The payload
  begins with a kind/mode word at +0 and flags at +4. These are copied into
  context+a4 and +a8. Selection has precedence **flag 4, then 8, then 10 hex**.
  Flag **0x4** requires context bit 0x2000 clear, sets it, and selects
  `0x603c886a` or `0x603c895e` using byte `0x62a68054`. Both build a
  **queue-94 command 0x100 (LOCK_START)**. Flag **0x8** requires context bit
  0x4000 clear and sends queue 94 **0x901 (IAF_PAUSE)**, queue 92 **0x100**,
  then queue 94 **0x900 (IAF_RESTART)**, subject to intermediate status checks.
  Flag **0x10** requires context bit 0x20000000 clear and starts queue 94
  **0xb00 (TAKE_ONCE_START)**. Missing operation bits or rejected state can
  return **0x4b00** after a diagnostic. The kind word also selects fields in
  the constructed worker payload; it is not itself the queue command ID.
- **0x2b / 43 → `0x603c8af3` → `0x603c8b00(D0=0)`: operation end.** The
  same operation bits choose the matching stop path and require the matching
  active-state bit. The ordinary lock branch sends queue 94 **0x101
  (LOCK_END)** after its preparation succeeds. Payload high bit 0x80000000
  chooses a different lock-end path through queue 96 command 0x51 and callback
  `0x603c8cec`; it must not be flattened into an unconditional LOCK_END send.
  The other branches perform IAF pause/restart sequencing or queue 94 **0xb01
  (TAKE_ONCE_END)**. Stop requests are stateful, not unconditional success.
- **0x2c / 44 → `0x603c8d14`: kind-5 end-then-start transition.** Requires
  payload kind **5**, overwrites payload flags with **4**, calls the end helper
  with D0=1, and, if it succeeds and context bit 0x2000 is clear, sets that bit
  and enters `0x603c895e`. Other kinds produce diagnostic 25000a28 and 4b00.
  This command mutates the supplied payload.

LOCK_START is not just submitted and forgotten: the constructed queue-94
envelope names **queue 99** as reply destination and uses correlation bit
**0x80000**. `0x603c886a` waits for 12-byte replies and reads their status;
`0x603c895e` also uses event-wait helper `0x6004cdf8`, then waits until its
outstanding completion mask clears. Thus scheduling queue 95 alone is not a
successful AF proof: queue 94, the queue-99 completion path, callbacks and
the reached event-wait contract must also execute or reach an explicit boundary.

### Producer ABI and the pre-dispatch guard

Public request function `0x6043f7c5` uses **D0 for the operation selector**:
1 selects command 0x2a, 4 selects 0x2c, all other values select 0x2b
(`0x6043f935`–`0x6043f96e`). A0 supplies the kind selector: 1 maps to kind 1,
2 to 3, 0x0e to 2, and 3 to 5; other kinds take its diagnostic return path.
D1 contributes payload flags. The command is finally in D1 at the call to
`0x60416fac`; that helper forwards to the synchronous envelope builder.
Do not read the initial D1 flag argument as the final queue-95 command. This
recovers the producer ABI, but does not identify a physical button caller.

Before dispatch, `0x60317994` checks **context+94 bit 0x8000**. While it is
set, only commands **4a, 4b, 50, 51, 53, 54, 55, 5a hex** pass this guard.
Other requests are offered to the ring at context+fc through `0x60318676`,
and the task returns to receive without running the handler/common reply on
that iteration. The ring helper copies the record and updates its counters;
when full, it emits diagnostic 25000501. Its eventual drain is not established
by this window. Log guard state and ring enqueue/drain when diagnosing a missing
reply; do not turn a deferred request into an immediate success.

### Decoder for the next trace

[decode_om3_queue95.py](scripts/decode_om3_queue95.py) accepts `--request` with
16 captured bytes in hex, optional separate `--payload` bytes, and optional
`--reply` with 12 bytes in hex. It decodes the envelope against the extracted
93-slot map and annotates the AF-family branch. It never connects to a camera
or dereferences the recorded RAM pointer. Validation covers operation precedence,
alternate start, an invalid command, reply layout and malformed request length.

Next runtime logging points: **0x6031789b** (receive call), **0x603178c6**
(guard), **0x6031792c** (selected handler), **0x6031792e** (handler result),
**0x60318ce2** (common reply), and queue-94/99 sends and receives. Record the
16-byte envelope plus pointed-to payload, selected function, context state bits,
unmodified and overridden status, and completion correlation. This can locate
whether an AF request is deferred, rejected, forwarded, waiting on the worker,
or completed. Static decoding alone does not prove either button sends it.

## Recommended next offline steps, in order

### Current starting point: carry correction complete

The installed language fix and isolated before/after execution tests are complete;
see [carry-fix](analysis/review/carry-fix/). The corrected test gives CF=1/VF=1
for `80000000 + 80000000`, VF=1 for `40000000 + 40000000`, and the seeded
normalization loop terminates after 21 iterations. Do not repeat the fix as a
pending task or raise the instruction budget to work around the old defect.

At this plan revision, `capture-reset-carryfixed/` contains only initial emitted
fixtures and empty console/run logs, with no completed connection trace or
outcome. No Java process was observed. That directory is an incomplete attempt,
not evidence that connection processing passed with the fix. The completed
`capture-reset/` and template-only `capture-timeout/` runs remain historical
baselines under their recorded models.

The immediate objective is **complete a reset-scenario run with corrected CPU
semantics, resolve its settings inputs, and identify the next actual dependency**.
This section is a continuation plan only; revising it did not execute the probe.

1. **Pin the corrected toolchain and start a fresh bounded run.** Verify the
   carry-fix manifest, record the installed `.sla` and source hashes, and launch
   a fresh read-only headless process so old compiled semantics/decode caches
   cannot be reused. Use a new output directory; preserve the incomplete attempt.
   Keep the established connection budget and record its actual value, rather
   than assuming the reported two-million limit equals the runtime setting.
   The full-reset-only budget may remain separately declared. Run one process
   against the project at a time. Completion: an unambiguous RETURNED, BOUNDARY
   or FAILED outcome with source/tool hashes and the actual stopping location.
2. **Add decisive instrumentation before the long reset/connection run.**
   At native-budget exhaustion record root entry, PC/instruction, SP, D0-D3,
   A0-A3, flags, configured budget and recent PC/branch history. Record the
   caller/input and exit of `0x6004c266`, connection message count and state,
   outstanding queue/event activity, and whether the original handlers ran.
   Retain bounded recent history instead of unbounded per-instruction logs.
   Preserve diagnostics on every exit, including initialization failures.
   Completion: a cap stop or unsupported operation can be attributed to a
   specific loop/dependency without reconstructing it from the final call names.
3. **Resolve the c011 readback discrepancy in that same reset scenario.**
   Before and after full reset, log both metadata namespaces, selected data
   pointer, backing byte/alias and cached consumer pointer `0x62b10204`.
   Compare native `0x60063380` with D0=c011, D1=0, **A0=0** against the native
   consumer `0x6031c0eb`, capturing results before register restoration. Nonzero
   A0 is a direct data pointer, not metadata. Record core ID, selector
   `0xa32a9908` and write-suppression state. Trace writes if the values diverge.
   Completion: either consistent pointer/value evidence or a diagnosed reason
   for 02 versus 03; deleting the contradictory read is not closure.
4. **Run the stock full-reset scenario through connection processing.**
   Keep the SCPU silent and the stock timeout outcome; do not invent a successful
   reply. Confirm raw mode and translated key at their consumers, then continue
   beyond the old normalization-loop boundary. Preserve template-only and
   reset runs separately. Disable automatic narrow fallback for this comparison:
   a full-reset failure should stop and retain its evidence. A narrow-reset
   experiment, if needed, must begin from newly initialized state. Completion:
   connection quiescence or the next precisely recorded dependency. A reset
   scenario is not evidence of persisted settings or a complete normal boot.
5. **Investigate the next dependency and validate models actually exercised.**
   If execution advances, follow its new boundary instead of assuming that a
   successful SCPU exchange is required. If a loop remains, establish its exit
   condition and progress/time/scheduling inputs before changing the budget.
   Validate reached multiply results/flags and MDRQ/getx consumers, reporter
   state/callback effects, and event-deletion context/ID/object/waiter contracts
   using the recovered disassembly. A diagnostic with D1=1 is not universally
   a no-op; dictionary deletion does not prove native waiter release. Keep
   strict memory faults and audit when they become active, including reset;
   separately identify supplied zeros and other fixtures. Completion: each
   consequential model has a stated contract, targeted evidence and limitations,
   or an explicit boundary where its behavior is not provided.
6. **Trace the real firmware button paths once reachable.** For half-press,
   AF-ON press and both release edges, record supplied event, stock handler,
   router disposition, requests to queues 95/94 (including computed commands),
   receiving dispatch, response status and cleanup. Verify that an error-path
   return is not reported as successful AF. Then compare ordinary area plus
   current SCP Subject Detect on half-press with AF Home area plus detection Off
   on AF-ON, retaining shared S-AF/C-AF and testing all supported SCP classes.
   Keep direct-handler probes distinct from stock-router traces and supplied
   events distinct from a proven physical producer. Completion: command/worker
   mapping and profile behavior for each exercised edge with no fabricated reply.
7. **Recover SCPU code only if the reached success path depends on it.**
   Recover SCPU (0107)'s CMDM command-0x40 handler and link framing, then assess
   bounded Cortex-M execution or an implementation-derived model. Keep this
   success-path work separate from the existing silent-peer failure experiment.
   Completion: a response derived from recovered execution/contract, with any
   remaining physical dependencies stated; an arbitrary success response cannot
   close the handshake gap.
8. **Finish independent orientation and synchronization research.** Trace the
   physical pose producer to the AF setting consumers and stock target-edit /
   display events. Recover reader locks, per-core cache mappings, publication
   and pointer-retirement behavior for staged records. Exercise UI flows only
   when their tasks and inputs are available. Completion: a documented static
   chain/design argument plus bounded execution evidence where possible;
   supplied pose codes and single-thread interleavings do not establish sensor
   mapping or real cross-core behavior.
9. **Revalidate affected results and publish a consolidated evidence status.**
   Identify earlier paths whose CF/VF-dependent branches follow changed aliased
   arithmetic; rerun those targeted checks and the relevant profile regression
   suite with the corrected language. Broaden testing when a new defect or
   changed result justifies it. Pin sources, compiled language, models, compact
   outcomes and inspected trace hashes, and state which findings supersede old
   baselines. Update the acceptance gates from actual results, not from the
   fact that a probe returned or a task was attempted.

**Execution order:** prepare instrumentation and corrected-language provenance,
then perform one full-reset run with readback checks. Follow each evidenced
boundary through diagnosis and bounded verification before claiming progress.
Do not stop at a passing lookup or numeric helper while reachable authorized
work remains; conversely, do not bypass an unsupported dependency with invented
camera state.

**Limits:** this plan can close specific offline initialization, CPU-semantics
and control-flow gaps under stated inputs. Modified-image acceptance, recovery
after a failed modified boot, and actual cross-core timing/visibility still
require hardware evidence. No firmware installation is part of this plan.

## Eighth follow-up: AF-command task scheduled; connection completes (7 November, evening)

**Still a labelled stock-reset scenario with a silent SCPU, not a normal boot.**
The carry-fixed rerun (`readiness/capture-reset-carryfixed/`) stopped when the
connection sent queue-95 command 0x1d and waited forever on reply buffer 1032.
The new probe [OM3CaptureAfTaskProof.java](scripts/OM3CaptureAfTaskProof.java)
extends `OM3CaptureResetProof`. When a caller would block, it runs the stock task
loop serving a queue with pending work, natively from its entry, in its own saved
context. This is the same pattern already used for task 207 and the port-2 task.
Queue 95 is served by the AF-command task at `0x6031787e`, and queue 94 by the AF
worker at `0x609df84d`. The probe never fabricates a reply.

Six runs, each removing one diagnosed harness gap. All are kept under
`analysis/button-af/readiness/capture-aftask*/`, with hashes in
`capture-aftask-run6/evidence-manifest.json`:

1. **AF-command task served command 0x1d natively.** The request was
   `08040000 02000000 1d000000 4c70a962`, routed to handler `0x603c641a`. It
   returned status 0, and the stock common reply sent 12 bytes to buffer 1032.
   The caller then received the reply. Next stop: a read of address 0x10 at
   `0x60542447`.
2. **Missing stock constructor group.** `0x605423e3` queries free space in the
   memory-pool registry at `0x606e21a0`: 119 slots of {id<<8, object}, with
   objects at `0xa31f5xxx`/`0x97f00xxx`. Those objects are built by
   static-constructor group `0x602153e6`, which runs the 13 entries of ROM table
   `0x60718770` and is called from section loader `0x60045f44` at
   `0x60046020`. The harness had only ever run the patched group `0x602153fb`.
   The probe now runs `0x602153e6` natively before the reset. Every registered
   pool then has a vtable (`0x606e291c`/`0x606e28e0`/`0x606e282c`).
3. **Zero-length memcpy.** Vector-grow `0x60b2e8bf` copies an empty old array.
   The shared model of imported memcpy `0x50002909` rejected n=0, so the probe
   treats n=0 as a no-op (standard semantics). With that change the
   **connection reaches quiescence for the first time** (30 jobs).
4. **Lock primitive semantics.** `0x60075f73`/`0x60075fbc` (649 callers) were
   modelled as one non-nesting "link spin-lock". Disassembly shows otherwise.
   The take disables dispatch only if it is not already disabled (and then sets
   bit 31 of its result), and calls `0x6004f63f`. That routine raises the PSW
   interrupt-mask level (bits 8–10) to D0 only if the current level is lower,
   and returns the old PSW. The release restores the PSW through `0x6004f660`
   and re-enables dispatch only when bit 31 is set. Nesting, including
   re-taking the same level, is therefore legitimate. The probe now uses a LIFO
   model that checks the bit-31 flag against nesting depth.
5. **Model state carried over between handler iterations.** The parent probes
   never cleared their kernel and link model state between the four
   fresh-emulator handler iterations, so iteration 1 skipped hook-table
   publisher `0x6004cfd9`. The probe resets that state in `init()`. No earlier
   probe got past iteration 0, so this had never been exercised.

**Current result (run 6):** in all four iterations the connection runs to
completion (`RETURNED`) after the stock reset, the pool constructors and a
served command 0x1d. The four original handlers then give:

| Handler | Result |
|---|---|
| `610b9197` (shutter half press) | RETURNED, mutex released, 0 native dispatches |
| `610b962a` (AF-ON press) | BOUNDARY: waits on response semaphore 1037 at `0x60dd896d` (1000 ms) |
| `610b9653` (AF-ON release) | BOUNDARY: waits on response semaphore 1040 at `0x60dd896d` |
| `610b96f0` (shutter release) | RETURNED, mutex released |

**No handler sent anything to queues 94 or 95.** The half-press body returns
without starting AF directly, so its AF start goes through some other route that
has not been traced. AF-ON's request is buffered by the capture router at
`0x62b7315c`, which is still in **state 12, "newCapabilityStart"**, with the
requested backend `0x62b71778` set and the active backend null.

**Where backend activation happens (static).** In state 12, router event handler
`0x60db3dca` takes the current message (`0x60dd9d65`) and tests it through
vtable+8. A 0x17 result takes the "next transition notstart" failure path
(`0x60db3048`, `0x60db3c2a`). A 0x1b result calls `0x60db3d96`, which copies
+0xbc to +0xb8 (activating the backend) and starts the object at +0xd8. Native
messages with ID 0x1b occur 21 times during the connection, but the backend is
never activated. So either the vtable+8 test is a class or type check rather
than the message ID, or the relevant message comes from the backend's start
acknowledgement, which may depend on the silent SCPU exchange (task 207 command 8
returned 0xfffe). This has not been established yet.

**What this establishes:** under the stated scenario and models, stock code
completes the capture connection, serves an AF-command-task request natively, and
runs all four original handlers in that connected context. **It does not
establish:** backend activation, an AF-ON response, any AF start command
(0x2a/0x2c) or worker `LOCK_START`, AF acquisition, or normal boot.

**Next step:** instrument `0x60db3dca` to record each message's vtable+8 result
in state 12. Then trace what sends the message that would yield 0x1b, and
whether it depends on the SCPU reply.

## Ninth follow-up: why the router stays in state 12 (7 November, night)

Run 7 (`analysis/button-af/readiness/capture-aftask-run7/`) is run 6 plus
observation-only logging at the state-12 handler `0x60db3dca`. Nothing is written
by the instrumentation.

**The vtable+8 call is a class test, not an ID compare.** For example, the
AF-ON press event's test `0x60af651c` returns 1 only when the queried type is
0x3bf (its own type) or 0x269 (its base type, tested in `0x60aed071`). Each
event's type is the halfword at +4, set by its constructor. Types 0x17–0x1b are a
family of generic result events built by `0x60bbbb40` (0x17), `0x60bbbb65`,
`0x60bbbb8a` (0x19), `0x60bbbbaf` and `0x60bbbbd4` (0x1b). About 75 call sites
across many state machines construct them.

**What state 12 actually sees.** In the AF-ON press and AF-ON release handlers,
`0x60db3dca` runs exactly once. The event it sees is the button event itself
(type 0x3bf, then 0x5dd). Both class tests (0x17 and 0x1b) return 0, so the
default path `0x60db3b09` runs. State 12 is never reached during the connection
phase.

**How state 12 is entered and what it waits for.** During the connection, a type
0x19 event drives state 11 (`0x60db3d22`). That handler calls `0x60db30ec` and
then enters state 12 (`0x60db3d70` → `0x60db3d78`). `0x60db30ec` branches on
whether a backend was requested:

- **Requested backend (+0xbc) is non-null:** build a start request
  (`0x60aebe2a`) and hand it to that backend through the backend's vtable+4.
- **No backend requested:** build a 0x1b itself and post it to the router
  (`0x60dbd132`).

In this run the requested backend is `0x62b71778`. So the router is waiting in
state 12 for that backend to answer with 0x1b (started) or 0x17 (failed).

**Tally of every event enqueued on the shared event queue `0x62b7659c` during
the connection** (type at +4, target at +0x18):

| Target | Events received |
|---|---|
| Router `0x62b7315c` | 0x19, 0x19a, 0x19d, 0x19f — **no 0x1b and no 0x17** |
| Backend `0x62b71778` | 0x19a, 0x19f, 0x1f0, 0x1f4 ×2, 0x1b ×7 |
| `0x62b732b8` / `0x62b73490` / `0x62b73870` | 0x1b ×1 / ×7 / ×6 |

The backend gets its start request and seven child "done" events, but never
posts a result to the router. Its dispatcher `0x60cb8f68` first offers each event
to its own handler `0x60c6a0eb`. That handler class-tests the event against the
type in global `0x62b74d54` and walks a component list. Any event it doesn't take
goes on to its two children at +0x3a0 and +0x3a4 (`0x62b71f9c`, vtable
`0x60ebc334`; `0x62b72f2c`, vtable `0x60ebda38`). Both children report component
state 4 for the whole run.

**Narrowed gap.** AF-ON is held because the backend under the router never
completes its start. That composite backend (`0x62b71778`) and its two children
are now the frontier (the partial decode below shifts the focus to the backend
itself): they would have to reach the state that posts 0x1b to
`0x62b7315c`. Two things are not established yet:
- what component state 4 means;
- whether leaving it depends on the silent-SCPU exchange (task 207 command 8 →
  0xfffe).

**Next step:** decode `0x60c6a0eb`'s type key (`0x62b74d54`) and the state
handlers behind vtables `0x60ebc334` and `0x60ebda38`. Find the call site among
the 0x1b constructors that targets the router. Then record which input the
children are missing.

**Still not established:** backend activation, an AF-ON response, an AF start
command (0x2a/0x2c), AF acquisition, normal boot.

### Partial decode of the sub-components (in progress)

**Component state.** The "component state" in the receiver trace is the word at
+0xb0 (`OM3LiveReceiverTrace.java`). Three base classes share a five-step
lifecycle for it. Each has one stock setter per step, and each setter writes the
same value to +0xb0 and +0xb4:

| Base class | States 1 / 2 / 3 / 4 |
|---|---|
| A | `0x60db0fb5` / `0x60db0fd1` / `0x60db10be` / `0x60db113d` |
| B | — / `0x60dba54a` / `0x60dba64f` / `0x60dba6ca` |
| C | `0x60dbafee` / `0x60dbb008` / `0x60dbb110` / `0x60dbb18e` |

The setters `0x60db0e7e`, `0x60dba45b` and `0x60dbaebf` write a value passed in
D0 rather than a constant.

**State 4 is the last step.** All three state-4 setters do the same thing: write
4, then call `0x60dbd56c`. Because 4 is the last value in the sequence, both
sub-components (`0x62b71f9c` and `0x62b72f2c`) have reached the end of their own
lifecycle. They are not stuck partway through it. So the missing piece is more
likely in the composite backend `0x62b71778` itself: it receives seven child 0x1b
events but never turns them into a 0x1b for the router. That is an inference and
has not been verified.

**Router state names.** These come from the stock name strings passed to
`0x60dbd44c` and to the logger `0x60ae7412`:

| Address | Name |
|---|---|
| state 9 / `0x60f11664` | `wait_restart` |
| state 10 / `0x60f11689` | `previousCapabilityRestart` |
| state 11 / `0x60f116ba` | `previousCapabilityEnd` |
| state 12 / `0x60f116e1` | `newCapabilityStart` |
| `0x60f116d0` | `TransitionStoped` (stock spelling) |
| `0x60f116f4` | `next transition started` (the 0x1b branch) |
| `0x60f1170c` | `next transition notstart` (the 0x17 branch) |

### Backend decode, continued (8 November)

**State 4 has no further action.** `0x60dbd56c` only checks the log level and
writes a trace line. Nothing else is attached to state 4.

**Composite layout.** The stock singleton getter `0x60dae512` builds the capture
composite once at `0x62b712b8` (constructor `0x60dae53d`, vtable `0x60f10744`).
It returns the public interface at +0x4c0, which is `0x62b71778` (class
`0x60f10f50`, derived from `0x60ec1f2c`). Members include:

| Offset | Address | Class / role |
|---|---|---|
| +0x4c0 | `0x62b71778` | interface (dispatcher `0x60cb8f68`) |
| +0xce4 | `0x62b71f9c` | vtable `0x60ebc334` |
| +0x1c74 | `0x62b72f2c` | vtable `0x60ebda38`, the AE/AF lock controller checked by `OM3CaptureFactoryProof` |
| +0x1d4c | `0x62b73004` | class `0x60f10824` (constructor `0x60dae8c8`) |

**A sequencer that reports start results.** The +0x1d4c member's state
dispatcher `0x60dae92b` (vtable slot `0x60f108a8`) handles four states:
- **state 1:** waits for 0x19d;
- **state 2:** `0x60daea4b` posts 0x1b ("started") to the object at its +0xa8 on
  event 0x19a, after calling `0x60dbae2f`, or 0x17 ("failed") on event 0x19b;
- **state 3:** handled by `0x60daeb54`;
- **state 4:** waits for 0x1a6.

In run 7, nothing addresses `0x62b73004` and its dispatcher never runs.

**Composite start is never called.** Composite virtual slot +0x10
(`0x60dae867`, at `0x60f10754`) calls `0x60dd94b7` on every member, including
+0x1d4c. Neither has a direct caller, and neither runs in any phase of run 7.

**Stock attach routine is skipped (the strongest lead so far).** The only stock
caller of the factory is `0x60dd4ad2`, called from `0x60dd4a4f` (vtable slot
`0x60f18ea0`, apparently slot +0xc8 of owner class `0x60f18dd8` with constructor
`0x60dd499b`). That routine does five things:
1. gets the interface;
2. calls its vtable+0xb8 with the owner;
3. takes the router from owner+0x148;
4. calls `0x60dbcc7f` twice to connect router channels (getters `0x60db3230` →
   +0x100 and `0x60db323e`) to backend channels (`0x60dbf08d` → +0x9c and
   `0x60dbf0a2`), then calls `0x60db3237`/`0x60dbefd4`;
5. calls `0x60dcaf5b`.

None of `0x60dd4a4f`, `0x60dd4ad2`, `0x60dd94b7` or the owner constructor ran.
`OM3CaptureFactoryProof` calls the factory directly with a supplied parent, and
`OM3CaptureConnectedProof` supplies event 114 naming backend `0x62b71778`. So in
the emulation:
- the router–backend channel connections are never made;
- the composite's members are never started.

**Revised reading of the state-12 stall.** The stall is most likely a gap in the
harness's set-up of the scenario, not missing firmware behaviour or an SCPU
dependency. The router waits for a result on a channel the stock attach routine
would have connected, and the sequencer that produces start results was never
started. This is a static reading and has not been confirmed by a run. It
supersedes the earlier inference that the composite's handling of child events is
the blocker.

**Next step:** a labelled probe that runs the stock owner path natively instead
of the bare factory:
1. construct owner class `0x60dd499b` (or identify the stock object that already
   holds one);
2. invoke its slot +0xc8 (`0x60dd4a4f`);
3. confirm that the router is at owner+0x148;
4. rerun the four handlers.

Pass condition: a 0x1b or 0x17 addressed to `0x62b7315c` arrives from stock code.

### Cross-check in OM-Emu (8 November)

**Search.** I checked the related GitHub projects for a better emulator:
- the upstream (fishcu/oly_fw_analysis) and its 18 forks;
- Ghidra-Rare and the pinned MN10300 extension (no change since our pinned
  version);
- a repository search.

The upstream ships a GNU-simulator MN103 harness built for the PEN-F. Ax72864's
fork adds an OM-3 boot harness on top of it, but that harness auto-stubs
unmodelled accesses and parks in a synthetic idle loop. Neither touches the
capture code.

The useful find is **OM-Emu** (`flatpanda/om-emu`, commit `15d407e`, no
license). It is a JavaScript MN10300 lab that runs the firmware's own µITRON
kernel, GUI and camera application natively. Its OM-3 (E147 v1.1) main block
is byte-identical to ours (`5e8d376e…`).

**How it was run.** Locally only:
- portable Node v26.12.1 under `tooling/`, checked against the published
  SHA-256;
- blocks unpacked from our local `.BIN`, with no vendor download;
- a local-only patch to its `import.meta.url` path handling so it runs on
  Windows (50 sites; OM-Emu itself unchanged);
- the player on 127.0.0.1 with its debug API.

OM-Emu's stand-ins are labelled. Several of them fabricate results; S-MODACK,
for example, answers every module request with status 0. So its observations
below are corroboration, not gate evidence.

**Results:**

| Session | Composite (`0x6036d470` / `0x62b712b8`) | Router `0x62b7315c` |
|---|---|---|
| default (camapp 1) | not built (0 / 0) | vtable `0x60f11758`, state 3 |
| HLS components on (camapp 2) | **built by stock code**: flag 1, vtable `0x60f10744`, interface `0x62b71778` vtable `0x60f10f50` | state 6, active and requested backend both `0x62b76000` (vtable `0x60f18aa8`) |

- **Layout confirmed.** The components session confirms the static composite
  layout, and confirms that building the composite is part of the stock
  component bring-up.
- **The harness supplies a different backend.** At idle, stock bring-up leaves
  the router in state 6 with backend `0x62b76000`. `OM3CaptureConnectedProof`
  instead requests `0x62b71778` through supplied event 114. That supplied
  request is a scenario choice, not the stock idle state.
- **The button path cannot be tested there yet.** The OM-3 port comes up in
  movie mode (4K 30p, movie-P), and its stills/movie switch is not wired. Half
  press and AF-ON were accepted but executed none of: the four original
  handlers, router dispatch `0x60db3289`, state 12, `0x60dd4a4f`, `0x60dae512`
  or the queue-95 task (filtered exec trace, both sessions). OM-Emu's AF,
  release and capture modules are stand-ins on every body.

**Consequence.** OM-Emu cannot exercise this AF path today. The next step
remains our own probe, with one adjustment. It should start from the
stock-built state (composite built by the bring-up, router backend
`0x62b76000`) rather than from a supplied request for `0x62b71778`. Then it
should find which stock event requests a backend change on half-press or
AF-ON.

**Superseded (8 November, afternoon).** The stock-mode probes
(`OM3StockMode*`; eighteenth follow-up onward) produce the category and capture
connection natively from stock-constructed mode inputs 0x1a4 and 0x1a1. That
covers the next step proposed above. A parallel direct-call probe,
`OM3CaptureAttachProof` (runs `capture-attach-run1` and `capture-attach-run2`),
did the following:
- built the container `0x62b76180` and owner `0x62b7637c` natively, with
  owner+0x148 = router `0x62b761f0`;
- ran the attach routine's three channel connections and its registration;
- stopped at a return-address setup error in the probe itself: an
  explicit-prologue routine was entered as a `call` target.

It was not continued and is not evidence for any gate. The OM-Emu observation
remains a corroborating cross-check: in its components session, router
`0x62b761f0` holds `0x62b71778` as active and requested backend in state 6.

**Still open:**
- the owner object's stock producer and its constructor arguments;
- what `0x60dd94b7` sends to each member;
- what `0x60dbd56c` does after state 4 (resolved above: logging only);
- the type key at `0x62b74d54` that the backend's handler `0x60c6a0eb` tests
  against;
- which 0x1b construction site is meant to target the router `0x62b7315c`;
- whether any of these depends on the silent-SCPU exchange.

## Tenth follow-up: backend layout and completion notification (8 Nov UTC)

This follow-up supersedes the ninth follow-up's suggestion that the two simple
children must leave lifecycle state 4. The children are dispatch-ready at 4;
the public capture backend has a different layout and state machine.

**New evidence.** `OM3BackendStartTrace.java` observed one complete conditional
stock-reset connection and deliberately stopped before the original buttons.
The run is in `analysis/button-af/readiness/backend-start-trace1/`. The outcome
file distinguishes this intentional observation stop from an execution failure.
No additional input/reply/state was supplied by that observation subclass;
the inherited direct event-114 input, reset and silent-SCPU models still apply.

**Closed static questions.**

- Global type key `0x62b74d54` is **0x269**, initialized by the stock request-base
  constructor and copy path. `0x60c6a0eb` handles that request class, rather than
  aggregating every child-start completion. All 12 observed class tests returned
  zero for the connection's bare-event family, including start/done events.
- `0x60dbabe4` explicitly requires simple-component lifecycle +0xb0 == 4 before
  testing its registered event classes. Therefore 4 permits event dispatch.
- `0x60dbd56c` records a diagnostic state through `0x60dbd63b` and conditionally
  logs it. It does not itself construct or enqueue a start acknowledgement.

**Layout correction.** For backend `0x62b71778` (vtable `0x60f10f50`), the coarse
state is at +0xfc and the active state is at +0x100. The final snapshot is
**4 / 14**. The backend's +0xb0 and +0xb4 belong to observer/vector storage;
interpreting these as lifecycle/state produces meaningless large values.
The generic `state()` labels in the original observation text are retained as
historical output, but must not be used for this backend. The inherited
`NATIVE-RECEIVER` logger also prints fixed offsets across different classes;
its state labels require the same class-specific interpretation. Raw snapshot bytes
are the evidence. The two children still use +0xb0/+0xb4 and finish at 4 / 4.

**Completion path.** Backend handler `0x60daf121` recognizes successful internal
start event 0x19a and enters `0x60daf108`. That routine calls `0x60cb6779`,
which calls `0x60c6abfb`: notify the observer list embedded at backend+0x9c,
then store the backend itself at +0x94. Afterwards `0x60daf7a5` enters coarse
state 4 (stock name `active`) and active state 14. State 14's handler
`0x60db08cc` recognizes class 0x118 for observer registration before entering
a shooting-end sequence; reaching 14 alone is not evidence of failed startup.
The retained native-call trace reaches this success path and state-14 setter.

**New concrete lead.** The final backend snapshot has zero start observers
(count at +0xa8). Stock still-image construction has an explicit wiring path:
`0x60dd4a4f` creates/gets the capture backend, obtains the owning router's
callback through `0x60db3230`, obtains the backend's observer list through
`0x60dbf08d`, then registers the callback with `0x60dbcc7f`. The started callback
`0x60dbb321` constructs event 0x1b and posts it to its target at +0x14.
The current `OM3CaptureConnectedProof` fixture directly supplies event 0x114
with the public capture interface. It does not reproduce this stock category
construction and registration sequence. An omitted observer, or an omitted
category layer, is therefore a specific harness explanation to test before
attributing the missing router reply to hardware/SCPU.

**Confirmed at the actual notification call.** The second observation run,
`analysis/button-af/readiness/backend-notify-trace1/`, records the backend's
success handler `0x60daf108`, bridge `0x60cb6779`, notifier `0x60c6abfb` and
observer dispatch `0x60dbcd5b` on the same path. At the last call A0 is
`0x62b71814` (backend+0x9c), and the observer count is **zero**. No registration
of a start observer on that list occurs in this run. The ordinary connection
trace is byte-for-byte identical to the first observation run. Thus the lack of
a router acknowledgement in this fixture is explained by the omitted observer
wiring; it is not evidence that the backend failed to finish its internal start
or that a positive SCPU reply is required for this particular notification.

`backend-class-aware-summary.json` in each run corrects the generic layout
labels without rewriting the original observations. Each
`class-aware-evidence-manifest.json` pins the raw observations, decoded stock
payload, compiled processor definition, bounded disassembly and an archived
copy of the complete Java inheritance chain. All **41 bounded windows** were
checked for contiguous decoding and exact byte agreement with the stock
payload. These checks validate the inspected bytes, not all possible paths or
all processor semantics.

**Native comparison result.** `OM3CaptureConnectedProof` now exposes
`enqueueConnectionInput()`; its default body preserves the original direct
input exactly, excluding comments/whitespace. `OM3StockModeConnectionProof`
replaces that input with a stock-constructed event 0x1a4 to the native mode
controller in its observed state 11. Sources for the earlier run are archived
separately; notification instrumentation also avoids an unnecessary register
read on unrelated instructions without changing emulated state.

The run `analysis/button-af/readiness/stock-mode-connection1/` completes its
connection observation. Native `0x60db1753` registers the main router's started
callback on the newly constructed category `0x62b76000` (vtable `0x60f18aa8`).
Its notification list at `0x62b7609c` has **one** observer. `0x60dbb321` executes
with callback `0x62b7325c`, target `0x62b7315c`, constructs a genuine 0x1b and
posts it. The router's state-12 0x1b class test returns 1, its native promotion
path runs, and the queue drains after **13 jobs** with:

- main router state **6**, active/requested category **0x62b76000**;
- capture backend `0x62b71778` still **3 / 3**;
- capture children still **3 / 3**;
- no queue-95 task run and no original button execution in this observation.

This proves native registration, callback delivery and promotion at the first
category layer. It does not prove that the physical capture component has been
selected. The generic inherited outcome files describe the deliberate
observation stop as a `BOUNDARY`; `backend-start-outcome.txt` and the retained
trace distinguish that instrumentation stop from a failed connection.

## Eleventh follow-up: staged photo-mode input reaches an initialization gap

The stock producer is an iterator, not a single event:

- `0x60afd647` advances stages 0, 1 and 2 and returns each produced request.
- Stage 0, `0x60afd577`, compares mode family bits and constructs 0x1a4 for
  family `0x10000` through `0x60aebee9`.
- Stage 1, `0x60afce68`, constructs **0x1a1** through `0x60aebe7d` for packed
  photo modes `0x10100` or `0x10200`.
- Stage 2, `0x60afcf22`, has a separate guarded table; its changed-mode path
  requires a packed value at least `0x20101`, so these two photo values do not
  produce another request there.

The selected category's active-state handler `0x60dd4740` recognizes 0x1a1,
then calls `0x60dd3ae9`. That path asks stock category logic to obtain the
sub-component and produce the next connection. Native factory/wiring
`0x60dd39c2` connects its callbacks; `0x60dd4a4f` is the lower still-image path
that obtains and wires the capture backend. The stock ROM vtables confirm
that `0x60f18aa8` dispatches the former factory through +0xcc, while the lower
still-image vtable `0x60f18dd8` dispatches the capture factory through +0xc8;
those slots must not be assumed identical across the classes. Ten additional bounded windows
(**484 instructions**) in `analysis/review/mode-sequence/` agree exactly with
the decoded stock bytes and cover these producer/consumer paths.

`OM3StockModeSequenceProof` therefore supplies the two stock-constructed inputs
in order, drains the native queue after family selection, and addresses the
subtype input to the category that native code actually selected. Routing and
input timing remain fixtures; it does not write any active/requested backend
field or fabricate a completion event. It will attempt original AF-ON press
and release through the existing resident/context fixture only if native code
has actually made the capture backend active.

**Observed result:** `analysis/button-af/readiness/stock-mode-sequence1/` again
activates the first photo category. The subtype request then reaches the inner
router `0x62b75e5c` with no selected backend; `0x60db8ad3` buffers it. There are
no additional queued jobs, the capture backend remains 3 / 3, and the AF-ON
guard stops before executing either button. The button-only trace is empty;
its result is a failed capture-active precondition, not a firmware AF-ON fault.
The preserved class-aware summary and source manifest distinguish these facts
from the inherited intentional-stop `BOUNDARY` messages.

## Twelfth follow-up: native protocol initialization advances subtype routing

The category's request-routing function `0x60dcc872` reads its class key from
`0x62b756bc`, calls the request's isA method, and returns the category itself
when the class matches. Otherwise it can send the request to the inner router,
which explains the observed buffering path.

The stock initializer is `0x60dcd228`. It constructs a temporary subtype base
through `0x60aed0d5` (class **0x26c**) and copies it into the global object at
`0x62b756b8`. Its pointer is at ROM table slot `0x60f1a770`. The harness had not
called it. `OM3StockModeInitializedProof` now runs the six omitted protocol
constructors in the table's suffix, preserving registers around their native
execution. It records the actual type key before/after and the category's
subsequent class-test results. It never writes an expected key directly. The
run is `analysis/button-af/readiness/stock-mode-initialized1/`. The observed
key changes from **0x0000 to 0x026c**, and the category's native class test
returns **1**. Stock `0x60dd39c2` creates the still-image category at
`0x62b7637c` (vtable `0x60f18dd8`), registers its completion callback, and
produces the next connection/start inputs. This closes the specific missing
class-key explanation of the earlier subtype buffering.
Nine more bounded windows in `analysis/review/mode-key-init/` cover the key,
routing, copy constructor and these protocol constructors (**142 instructions**).

**Broader startup audit.** Stock loader `0x60045f44` calls `0x60215410` for
section 6. That group runs **49 constructors** from table `0x60f1a6b4`, byte
count 0xc4. The previous explicit harness list called six of those constructors;
no calls to the other 43 were found in the inspected trace. This is a coverage
audit, not a normal-boot assertion; `constructor-coverage.json` records the
trace hash, each table slot and the distinction between source-invoked roots
and logged native calls.

Some omitted constructors populate member-function descriptors that are zero
in the decoded initial data. Examples are `0x6036c024` / `0x6036c548` /
`0x6036d17c`, initialized by `0x60c6b6a3` / `0x60c6c120` / `0x60d20abf`.
The associated stock function values are `0x60c7100a`, `0x60c70675` and
`0x60d28814`. Therefore a selective constructor model is insufficient to
interpret all future button-dispatch failures as device dependencies.

The complete-group comparison in `OM3ProtocolConstructorGroupProof` has
executed the stock section-2 pool group followed by **all 49 section-6
constructors, each observed once**. `constructor-group-proof.txt` in
`analysis/button-af/readiness/constructor-group-queue10-1/` records the visits,
class keys 0x26c / 0x269 and verified representative descriptors. The later shooting/connection path exposed the singleton-reset conflict
described in the fourteenth follow-up. The six legacy manual framework/
receiver constructor calls are skipped in this variant, avoiding duplicate
initialization; the legacy default bodies are preserved behind explicit seams.
No reply or active/requested backend field is supplied. This covers these
constructor groups, not the complete camera startup sequence.


## Thirteenth follow-up: native queue-10 service and corrected header layout

The initialized subtype run stops at empty reply buffer **1028**, after this
16-byte request is queued to **MBF 10**:
`04040000020000000100000038ff0470`. The worker's raw loads and native execution
establish the header: **+0 reply buffer 0x404 (1028), +4 sender task ID 2,
+8 command 1, +12 payload pointer 0x7004ff38**. Earlier working notes called
this command 2 by mistaking the sender-task field for the command. That
interpretation is superseded. 0x404 is not a component ID.

The stock task table identifies task 10's entry as **0x60065881**. It registers
a queue-10 send hook that sets event flag 11 bit 2, waits on flag 11, references
the queue, receives requests, calls **0x60065afb**, and constructs a reply
through **0x6004d171**. Command **1** dispatches through **0x60065c35** to the
property-write handler **0x60065781**. Descriptor key **0x8101** selects **one
byte at 0x6298d500**; this command copies the payload's byte at +1 there. The
30 stock descriptors and corrected header interpretation are retained in
`analysis/review/queue10/property-descriptors-v2.json`. The earlier JSON is
retained for historical manifests; its command-number metadata is incorrect.

`OM3Queue10TaskProbe`, repeated in
`analysis/button-af/readiness/task10-startup2/`, executes the native publisher,
send-hook registration and worker entry, including timer registration, and
reaches its own unsatisfied flag-11 wait. No timer expiry is generated.
`OM3Queue10WorkerProof` preserves that task's registers and stack, initializes
it before the send, and resumes the saved context when the caller blocks. Its
scoped `ref_mbf` model reports the existing queue contents; command dispatch,
property copying and response construction execute stock code.

**Isolated exchange result:** `queue10-exchange3/` replays the captured header
twice with one worker entry and two subsequent resumes. Each native worker
reply is **`000000000200000038ff0470`**, and the caller's correctly supplied
receive descriptor obtains these exact 12 bytes with wrapper status zero.
The reply buffer is poisoned before each call to detect a missing copy. This
proves a reusable native software receiver for this request under the fixture.
It does not prove capture activation or a camera response. An earlier replay
used a raw output pointer where the receive wrapper requires a descriptor;
`queue10-exchange2/` therefore is not caller-delivery proof despite its original
RETURNED label. The focused probe also requires explicit no-active-loop LIR /
LAR register initialization; `queue10-exchange1/` stopped on that omission.

The old trace captured the header, not its pointed-to payload. The corrected
`queue10-exchange4/` explicitly supplies a two-byte zero payload fixture at the
captured pointer and labels **command 1 / sender task 2** correctly. Both
exchanges return the exact native reply to the poisoned caller buffer. This value
is not claimed as observed camera data. Its result is retained with the explicit input fixture.
No response, backend pointer, lifecycle transition or timer expiry is supplied.

The 52 constructor-group windows (**10,005 instructions**) and seven queue-10
windows (**523 instructions**) agree byte-for-byte with the stock payload.
Across the five new analysis folders, **119 windows / 13,236 instructions**
have now been checked for byte identity and contiguous decoding. This is not
a whole-program reachability proof. Default harness initialization and the
emulator execution loop were checked unchanged after expanding extracted
methods.

## Fourteenth follow-up: preserving the natively initialized main thread

The first complete-constructor comparison,
`analysis/button-af/readiness/constructor-group-queue10-1/`, initializes all
49 constructors and verifies keys and descriptors, but **does not reach the
queue-10 exchange**. Its supplied 0x19f startup event is released, zero startup
jobs run, and the mode controller remains state **3**, so the mode-input idle
guard stops. No mode selection or original button executes in this run.

The retained trace identifies the cause: the native constructor group calls
**0x60dd7bb4** and **0x60dd7aff**, initializing main-thread object
**0x62b76554** and guard byte **0x6036d700**. Later, the legacy shooting fixture
zeros **0xb50 bytes starting at that object**, also erasing the native default
event context at **0x62b76a14**. The guard remains set, so the subsequent singleton getter
does not reconstruct it. This is a destructive fixture operation after stock
initialization, not evidence that the real camera stalls at startup.

The second comparison, `constructor-group-queue10-2/`, preserves the object
instead. Its override checks the native guard and vtable **0x60f19b98** and
omits the later zeroing; it does not write a desired field or clear a guard to
force reconstruction. The default harness keeps its old storage setup through
an explicit seam. **Observed result:** the second run reaches **38 startup jobs / controller
state 11**, makes the native category connection, and uses the real queue-10
worker to obtain command 1's own reply (dynamic reply buffer 1030). It then
queues **command 3**, which reaches an unprovided read of **0x97f00090**
through getter `0x600216f2`, called at `0x600644f0` in the property builder.
No original AF-ON input executes before that boundary. The source/result
manifest preserves this run separately from the isolated replay.

## Fifteenth follow-up: bounded independence proof for one MMIO read

Raw getter **0x600216f2** consists of a four-byte read from **0x97f00090** and
a return. Its physical register meaning is not established here. In the
observed caller **0x600644d5**, the returned value is used only in a zero versus
nonzero test. When the preceding source result in **D2.low is zero**, both
branches reach **0x600644fe**, write the same output, and return **0xff**.
This is a local dataflow statement, not a claim about the real register.

`OM3StatusPropertyProbe` executes the entire native builder with the declared
reset source flag **0x6299555e = 0** and separately supplied register values
**0x00000000** and **0xffffffff**. Both runs return **0xff** and overwrite a
poisoned three-byte buffer with **00 00 01**. These cover the only two value
classes distinguished by the verified raw code. Results, traces and archived
sources are in `analysis/button-af/readiness/status-property1/`.

`OM3Queue10StatusIndependentProof` therefore continues only this getter call,
only inside task 10 at **0x600644f0**, and only while **D2.low = 0** and the
source flag is still zero. It uses zero as a representative value of the two
equivalent classes, records every such abstraction, and rejects any other
call site or condition. It does not set a backend state, invent a property
reply, or assert a physical register value. The full comparison is
`analysis/button-af/readiness/constructor-group-queue10-3/`. It uses the
guarded abstraction once and progresses into additional native property
refresh logic. The next stop is the legacy dispatcher's **Unexpected device
callback** guard, not another MMIO read or a successful camera response.

Fourteen further windows (**371 instructions**) cover the singleton getter,
constructor, event-submit gates, receive wrapper and this status path. All
new evidence now covers **133 bounded windows / 13,607 instructions**, checked
against stock bytes. Decoding validates byte identity and continuity, not
whole-program correctness or camera safety.

## Sixteenth follow-up: native missing-device completion and sparse flag IDs

The new callback is **0x600701ec**. Raw submitter **0x6006fd32** looks up the
request endpoint through **0x6006fe4d**. With the declared registry empty
(`0xa32bff14 = 0`), it selects that callback, queues it through **0x60072c53**,
and returns native **failure result 1**. The old `OM3NativeLifecycle` model
accepted only callback 0x6082e204, so its guard rejects this new path.

The request is the native 56-byte packet at 0x7002b900 with original
completion function **0x60064085**. Raw builder `0x60063f0c` stores an input
byte as the endpoint; ROM `0x6012000c` lists **1, 4, 5, 2, 3**, all class 1.
The C projection appeared to use literal 0x53, but that is contradicted by the
raw load/store at `0x60063f7f` / `0x60063f83`. The original endpoint-0x53
guard was therefore incorrect. The selected failure callback
only invokes that original completion function if present. That function
signals the caller's completion bit through **0x60066977**; it does not return
a sensor sample or register a device. The software dispatcher itself stores
callbacks in a ring through **0x60072d87** and requests service through an
interrupt register. Immediate callback delivery remains an explicit scheduler
fixture, not a claim about hardware interrupt timing.

`OM3MissingDeviceCallbackProbe` in `missing-device2/` executes the submitter,
failure callback and original completion function natively under that delivery
model. It verifies **submit result 1**, the native flag notification, and an
unchanged empty registry. No device success or sample is supplied. The first
attempt, `missing-device1/`, stopped because the inherited static flag loader
omitted flag 295.

The ROM table contains **294 descriptors** with IDs **1..283 and 287..297**,
then a zero terminator at **0x6003b8fc**. It is not a 283-record table: the
last 11 IDs form a sparse tail. The new experiment loads those tail descriptors
from their actual ROM records, preserving attributes and initial patterns.
`analysis/review/device-dispatch/core0-flag-descriptors.json` records the full
table and payload hash. The default legacy loader is retained for comparison.

`OM3Queue10MissingDeviceProof` adds only this guarded missing-endpoint callback
case and the ROM-backed tail flags. Run `constructor-group-queue10-4/`
stops at the over-specific endpoint guard before delivering a callback.
`missing-device3/` now tests **all five ROM-listed IDs**, clearing the input
flag pattern before each test and preserving submit result 1, callback
notification and an empty registry for every ID. The corrected full comparison
is `analysis/button-af/readiness/constructor-group-queue10-5/`. It delivers
the native missing-device callback but stops on **Unknown event flag 295**
at its first set, before any later wait could lazily load that ROM descriptor.
The flag must exist before a callback signals it, as in the native OS startup.
No native failure result, device registry, backend state or sample is replaced.
Ten additional byte-validated windows (**343 instructions**) cover the
submitter, dispatcher, callback, completion signaling and request builder. The
accumulated static audit is **143 windows / 13,950 instructions**.

Evidence indexes now freeze mutable static analyses inside each run. Earlier
indexes affected by an appended window-list row retain their original index
plus an explicit migration record, with every expected content hash unchanged.
Execution traces and source snapshots were not modified. All migrated indexes
were revalidated after the path correction.

## Seventeenth follow-up: complete native missing-device request path

The next software initialization gap is the request-bit allocator at
**0xa32bfb34**. Reset-only zeroing leaves it zero, and the request builder doubles
it, still yielding zero. Native initializer **0x60063eda** seeds it to **1**
and initializes the related software descriptor. It is called by larger
property initializer **0x6006635a**, whose pointer is in ROM at **0x6012051c**.
This identifies a missing native setup routine; it does not establish all
property-service startup order or initialize an actual hardware endpoint.

`OM3PropertyFailurePathProof` loads static flag 295 from its ROM descriptor
before the first signal, runs **0x60063eda natively**, and preserves registers
around setup. It never writes a desired completion bit or backend field.
`OM3PropertyFailurePathProbe`, run in **property-failure4/**, then calls the
complete native builder **0x60063f0c** for each of the five ROM-listed IDs.
For each request it observes native allocation, missing-device submission,
native failure callback, completion-bit notification, satisfied native wait,
flag clearing and packet freeing. Native allocator progression is
**2, 4, 8, 0x10, 0x20**. Each builder returns its native **fallback zero**;
this is explicitly **not a sampled hardware measurement**. The device
registry remains empty.

The three earlier isolated attempts, `property-failure1/` through
`property-failure3/`, stopped while preserving an incompletely specified root
CPU context (SP, condition flags, then the SLEIGH scratch register). The final
isolated probe declares a zero base-register CPU fixture and a valid stack
before installing strict read checks. These are test setup corrections, not
camera state evidence.

The full comparison using this verified setup is
`analysis/button-af/readiness/constructor-group-queue10-6/`. The native
connection queue becomes quiescent after **45 jobs**, the capture backend
reaches **coarse 4 / active 14** with **one start observer**, and the original
**AF-ON press returns**. Release then stops at the bounded heap model, as
detailed in the eighteenth follow-up. This is conditional software integration,
not a camera AF acquisition result.
The stock constructor groups, preserved main-thread/default context, native
queue-10 worker and guarded MMIO-independent branch remain as documented.
No device is registered and no successful device completion is supplied.

Two further byte-validated initialization windows (**100 instructions**) bring
the accumulated static audit to **145 windows / 14,050 instructions**.

## Eighteenth follow-up: active capture, original press and bounded heap reuse

Run **constructor-group-queue10-6/** completes the native category/capture
connection and original AF-ON press. The backend receives the original path's
**0x3bf** request and its stock class test recognizes the request. Its capture
state remains **4 / 14**, with its completion observer registered. The press
passes the inherited owned-target/cache and Subject Detect bypass checks.
Its native path also queues **AF command 0x2a (42)** with bytes
`06000000000001f02a00000040f30370`. The queue-95 task has serviced only the
earlier setup command 0x1d in that run; the new asynchronous 0x2a remains
pending because no later caller blocks before the release allocator boundary.
This is evidence of native AF submission, not execution of LOCK_START or
correct binding of the target profile when the asynchronous consumer runs.

The release fails allocating another **896-byte vector** at the old model's
high-water mark **0x7003fcb0**. That bump allocator never reused native frees.
Reconstructing allocations from the connection and button traces finds
**1,124 live allocations / 116,060 payload bytes**, **272 native frees**, and
free gaps of **33,552**, **32,960** and **2,240** bytes. This demonstrates model
capacity exhaustion despite reclaimable space, not camera heap exhaustion.
`analysis/review/property-init/heap-capacity-run6.json` records the trace hashes
and reconstruction.

`OM3ReusingHeapProof` preserves the original arena **0x70010000..0x70040000**,
64-KiB maximum request, bump behavior and native frees. At the old bump limit
it allocates only from gaps absent from the live-allocation map; it does not
expand into task stacks. **heap-reuse2/** verifies the 896-byte request,
preservation of live canaries and unused tail bytes, free/reuse, and rejection
of a genuinely full arena. The first test used an inconsistent synthetic
high-water mark and was corrected before this result. This remains an OS heap
model, not a proof of the camera allocator implementation.

## Nineteenth follow-up: original button/SCP matrix and registered-device boundary

The new **OM3OriginalButtonMatrixProof** comparison supplies native SCP setting
values **0..6** through existing setter **0x60063431**. For each value it runs
original **half press, AF-ON press, AF-ON release, half release** through the
resident wrappers, checks expected profile owners **1, 2, 1, 0**, checks Subject
Detect follows SCP except during AF-ON, and retains the inherited cache checks.
The default probe still runs its original two AF-ON edges; the new input seam
changes the matrix variant only. Its output is
`analysis/button-af/readiness/original-button-matrix1/`. It passes **2 / 28**
checks: original half press and AF-ON press for **SCP=0**. On AF-ON release,
queue 95 processes the pending **0x2a** and submits **0x100 (LOCK_START)** to
queue 94. The old timeout model then incorrectly times out an **infinite**
flag-68 wait before scheduling queue 94, and the diagnostic path reaches
unprovided kernel state at **0x97f00004**. This is a scheduler/timeout-model
limitation; it is not a completed matrix or a camera release failure.
Handler returns and ownership/cache checks do not assert focus acquisition,
healthy device initialization or installation safety.

The normal device-registry initializer is **0x6006fc01**, called by stock
startup **0x60044f5f** at **0x60044fea**. Its ROM table contains endpoints
**1, 2, 4, 12, 13, 14, 15, 16**; property IDs **3 and 5** legitimately miss
that table. The initializer sets pointer **0x6012387c** and count **8**, then
registers service/interrupt handling through **0x6006f515 / 0x6007602b /
0x6004f86e**. The isolated registered-path probe selects the inherited board
selector-0 fixture and supplies no hardware response or interrupt. It reaches
an unprovided **0x97f00000** read at **0x6004f99b** during interrupt registration.
The raw registration code shows that the loaded D0 value is discarded before
use. In **device-registry2/** a zero representative for that discarded value
lets native registration finish, retaining the eight ROM endpoints. This does
not model physical bus ordering. The registered endpoint-1 request then stops
at an unprovided read of **0x98c00028**, at **0x6006f53b**. Here bit 0 selects
different native paths (`0x6006f715` versus `0x6006f80a`), so its control-flow
dependence is real. No register response, measurement or interrupt is supplied.
The registered-path probe preserves infinite waits as waits. Its remaining
hardware state and interrupt behavior are separate from the verified native
missing-device failure path.

## Twentieth follow-up: native AF consumer scheduling without impossible timeouts

The original-button trace establishes a longer native chain than earlier
probes: **AF-ON press -> queue95 command0x2a -> handler0x603c86d7 -> queue94
command0x100 (LOCK_START)**. Queue 94's real worker was not scheduled at the
flag wait. The inherited silent-device timeout model accepted all nonzero
timeouts, including **0xffffffff**, which is an infinite wait. Converting that
wait to -50 is invalid for this scenario and exposes a diagnostic kernel path
instead of the pending worker's actual behavior.

**OM3OriginalButtonConsumerProof** therefore services pending AF tasks after
original button edges and before AF flag waits. The task at the top of the
nested execution stack is not reentered; native worker and command handlers
run on their existing separate stacks. Task identity service results for
queues94/95 use verified stock ROM task IDs **105/106**. If an infinite AF wait
remains unsatisfied after available producers run, the probe stops at that
wait, with its actual flag, mask, PC and task recorded. It supplies no AF
completion and does not manufacture a timeout.

The consumer run records queue94 payloads and any profile-cache accessor reads
from AF tasks, alongside the original button/SCP ownership checks. Its output
is `analysis/button-af/readiness/original-button-consumer2/`. The first
consumer attempt did not execute because of a Java trace-helper compilation
error, retained separately as NOT EXECUTED. The corrected run services queue94
natively and reaches **LOCK_START** before stopping on a clear of valid static
**flag 197**, which had not been created by the lazy object loader. Native task
IDs105/106 and the worker payload were recorded; this still completes only the
first two profile checks for SCP=0. No infinite AF timeout is fabricated in
this corrected run.
This is an explicit bounded schedule, not a proof of all camera interleavings,
AF convergence, physical lens movement or race freedom.

Seven registered-device windows (**249 instructions**) bring the accumulated
static audit to **152 windows / 14,299 instructions**, all checked against the
stock payload. The C projection's omitted/discarded volatile reads are checked
against these raw windows before interpreting them as hardware dependencies.

## Twenty-first follow-up: complete ROM tables and persistent AF workers

The missing flag197 was a general object-provisioning defect. Core0's four
relevant ROM tables contain **142 semaphores**, **294 event flags**, **5 data
queues**, and **242 message buffers**. Semaphore IDs are 1..133 and 138..146;
flag IDs are 1..283 and 287..297; message-buffer IDs have a contiguous prefix
1..218 followed by 224..244, 253, 254 and 257. Table terminators and every
record are captured in `analysis/review/static-os/core0-resource-tables.json`.
These are four audited object types, not a claim of complete RTOS boot.

**OM3CompleteStaticOSConsumerProof** provisions those objects from their ROM
attributes, initial counts/patterns and capacities before constructors/tasks
use them. Existing objects are preserved, not reset. It also retains native
AF-task register/stack contexts at own-queue idle waits, so resuming a worker
does not rerun its initialization. The new model does not populate a device
registry, submit images, set an AF acknowledgement or manufacture a completion.

**af-worker-startup1/** tests that setup without the long shooting reset.
Native worker94 initialization completes, reaches its own empty queue, and
resumes that same idle context. Its metadata initializer **0x609eff6b** is
observed exactly once across both runs. No AF command or frame is supplied.

The full comparison is **original-button-consumer3/**, using class
`OM3CompleteStaticOSConsumerProof`; result pending. Its progress file confirms
entry into the native settings reset/framework stage. The native lock/start
hash table maps command **0x100** to normalized key **0x101**, table slot **6**
at **0x60a83484**, handler **0x609df95b**, then **0x609e05a6**. These addresses
are verified against ROM table bytes and bounded raw disassembly.

Eight additional byte-validated windows (**832 instruction rows**) cover the
worker dispatch, initialization, lock/start path, flag-clear wrapper and
peripheral status branch. The accumulated audit is **160 windows / 15,131
decoded instruction rows**; ranges overlap, so this is not a unique-instruction
coverage count or a whole-program correctness claim.

## Twenty-second follow-up: native AF mode start from stock startup steps

`native-af-mode1/` (`OM3NativeAFModeProbe`) stopped on the shared
**Task-ID output contract**. `OM3NativeAFModeDiagProbe` diagnoses each stop in
turn (`native-af-mode-diag1..11/`); every fix is labelled in the source.

| Run | Stop | Cause and labelled change |
|---|---|---|
| diag1–3 | task-ID output `0xa3456e84` | `0x60700fb4` is the AF-command API. Owner task ID (ROM `0x60042da2`) is **106**, the queue-95 task. Other callers take the cross-task path `0x6004f3bd`, which stores the caller's task ID into a native pool request. The inherited model allowed only stack outputs. **Model:** the same task-1 value may also be written to word +4 of a request whose header was just written. |
| diag3 | null+0x8b4 at `0x609dbd6b` | Worker context `0xa33f3614` is set only by `0x609db6ab`, a sub-init of AF module init `0x608fe1b0`. That init is called only by startup task `0x602188f1` (task table `0x60039584`) at `0x6021897f`, which the harness never runs. **Supplied:** run `0x608fe1b0` directly. |
| diag4 | "Diagnostic path `0x609dcddd`" | `0x609dcddd` is the AF module's trace logger (→ `0x609479ef`, ring-buffer record; 721 callers), not an error path. **Change:** run it natively and record each call. |
| diag5–7 | memset bound | Init clears a 0x11800-byte AF buffer at `0xa5ee5000` (`0x60947242`). **Model:** same memset semantics with a 2-MiB bound for RAM destinations, logged. |
| diag7 | null+0x28 at `0x6098b140` | Object `0xa32c9c24` is set by `0x602f61a2`, a sub-init of module init `0x602ef888`. That is called by stock startup sequence `0x60045907` at `0x60045b09` (← `0x60044f5f`), which the harness never runs. **Supplied:** run `0x602ef888` first. |
| diag8 | read `0x97f00000` at `0x6004f99b` | The same discarded IRQ-registration read as the nineteenth follow-up. **Reuses** `OM3DeviceRegistryProbe`'s zero representative. |
| diag9 | probe's LOCK_START guard | MODE_START (0x3f9) and MODE_UPDATE (0x3fa, param 2) round-trip natively: forwarded request → worker 94 → replies on buffers 1017/1018 → result 0. Guard byte `0xa33f3674` has one writer, the AF worker defaults `0x609df7e4`, which the same startup task runs at `0x6021898d` after `0x608fe1b0` and the empty `0x609001ec`. **Supplied:** run those two steps in stock order. |

**diag10/diag11 result: RETURNED.** With the labelled startup steps:
- module init `0x602ef888` completes, and `0xa32c9c24` becomes `0xa3193780`;
- AF module init completes, and the worker context becomes `0xa33f2d5c`;
- the AF worker defaults set `0xa33f3674` = 1 and `0xa33f3640` = 1;
- native **MODE_START** and **MODE_UPDATE** are accepted, and LOCK_START's
  baseline mode guard is met by stock-written state.

The probe writes no worker readiness byte, acknowledgement or AF result.
diag11 runs the same steps after the refactor into `OM3AFStartupConsumerProof`
and reproduces diag10's evidence exactly.

**Limits:**
- The three supplied steps are direct calls of stock startup code. Their
  callers (startup sequence `0x60045907` and startup task `0x602188f1`) are
  not run, and neither are those callers' other steps (section loads 3/4,
  `0x60181a38`, `0x6004d566`, `0x605629cd`, and the remaining `0x60045907`
  steps).
- The discarded-read representative and the two model widenings are
  harness models.
- This is not normal boot, AF execution or a hardware result.

**Full comparison.** `OM3AFStartupConsumerProof` adds these startup steps
and the mode commands to the consumer chain, then runs the original buttons.

- **`af-startup-consumer1/`:** the steps and modes ran (`Prepared=true`). Half
  press, which now enters the initialized AF module (`0x603cedfe` →
  `0x609029f1` → status dispatcher `0x60903e88`), stopped on
  `OM3NativeFlow`'s "diagnostic path" `0x60068a54` (code `0x0f804001`).
- **Fix:** `0x60068a54` is the firmware's general **errlog writer** (4,928
  callers; the caller continues afterwards). OM-Emu records errlog entries
  during ordinary S1 presses. The consumer class now runs it natively and
  records each call: 13 in consumer2, with codes `0x24000615`, `0x0f803003` and
  `0x0f804001`.
- **`af-startup-consumer2/`:**
  - **Half press:** returns (SCP=0).
  - **AF-ON press:** queue 95 → **LOCK_START (0x100)** to worker 94 with
    owner 2 and subject 0, as in consumer3.
  - **New:** the now-initialized worker reads the **AF-ON target profile
    cache** (`AF-CACHE-ACCESS task=94 owner=2 active-cache=a031ea00
    subject=0`, twice). This is the first observation of the AF worker itself
    consuming the AF-ON profile with Subject Detect bypassed. consumer3 had no
    worker cache access.
  - **Stop:** the worker then sends request **0x5d** (parameter 0x0b00)
    through `0x607117ac` to message buffer **92** and waits on buffer **93**
    for the reply (`0x6004d115`). Queue 95 waits on the same buffer.
  - **Checks:** profile-matrix checks remain 2 / 28.

**Queue-92 task (`af-startup-consumer3/`).**
- **The server:** the ROM task table (records at `0x600390e0 + (id-1)*28`)
  shows that **task 104, entry `0x605a370a`**, reads its queue ID from halfword
  `0x6004322c` (= 92). Tasks 105 and 106 read `0x60043230` (94) and
  `0x60043232` (95) the same way.
- **Scheduling:** it is scheduled like the 94/95 tasks: persistent context,
  own-queue idle, ROM task identity 104, its own stack.
- **The exchange:**
  1. Task 104 receives request 0x5d, replies on buffer 93 with an all-zero
     status block, and goes idle, all natively.
  2. The worker continues into `0x609ec5e9`. That routine builds a request with
     completion callback **`0x609ec651`** and calls the request's function
     pointer, **`0x603c8d71`**.
  3. That function **sets flag 68 bit 0x100000** (via `0x60318eec`). This is
     the event the AF-command task waited on forever in
     `original-button-consumer3`.
  4. The worker then waits at `0x609ec622` for **flag 67 bit 1** (ROM halfword
     `0x60042fa2`). Only callback `0x609ec651` sets it.
- **The stop:** the run stops there. The worker was running nested inside task
  95's flag-68 wait (task stack `[94, 95]`), so the nested scheduler model
  could not return to task 95 even though its flag had just been set.
- **Fix (scheduler model):** an AF task whose infinite wait is unsatisfied is
  parked with its native context. It is resumed when its flag condition holds,
  and the stock wait is re-executed. This is labelled
  `-Dom3.noTaskParking`, and nothing is set or supplied. Run:
  `af-startup-consumer4/`.

**Result (`af-startup-consumer4/`): original button/SCP matrix 28 / 28.**
All four original edges (half press, AF-ON press, AF-ON release, half release)
return for each SCP setting 0..6. Each matches the feature's expected profile
owner (**1, 2, 1, 0**) and the expected effective Subject Detect:
- half press and AF-ON release follow SCP;
- AF-ON press is 0 for every SCP value.

The first AF-ON press drives the complete AF command chain natively:

1. Queue 95 handles command 0x2a and submits **LOCK_START (0x100)** to worker
   94 (owner 2, subject 0).
2. The worker reads the **AF-ON target-profile cache** (`0xa031ea00`, owner 2,
   subject 0).
3. Task 104 serves request 0x5d (buffers 92/93).
4. The worker's request function `0x603c8d71` sets flag 68 bit 0x100000. It
   then parks at `0x609ec622` on flag 67.
5. Task 95's flag-68 wait is satisfied. It continues through `0x60700bdf` and
   **calls the worker's callback `0x609ec651`**, which sets flag 67 bit 1.
6. The worker resumes (one park and one resume in total). It finishes
   LOCK_START and replies on buffer 99.
7. Task 95 sends its common reply (status 0) on buffer 6 and goes idle.

Every flag and reply in that chain is produced by stock code, and no task is
left parked at the end.

**Scope and open points:**
- **One submission only (investigated below).** There is one worker
  submission in the whole matrix: the SCP=0 AF-ON press. Later AF-ON presses
  update ownership and Subject Detect correctly but do not submit another
  LOCK_START.
- **Silent status block.** Task 104's status block is all zeros under the
  silent-SCPU and device models. No lens drive, image, phase-detect data or
  focus measurement is involved or claimed.
- **Labelled inputs.** The three supplied startup steps, the scheduler, heap
  and task-ID models, the reset scenario and the button and SCP fixtures all
  remain labelled inputs.
- This is not normal boot, AF convergence or a camera result. **Readiness
  stays NO-GO.**

**Why later AF-ON presses do not resubmit (static decode plus consumer4
traces).** I aligned the call sequences of the SCP=0 and SCP=1 AF-ON presses,
discounting one-time singleton construction. The chain is:

1. **The handler's permission check.** Original handler `0x610b962a` enters
   the AF path (`0x610a5620` → `0x610a5f10` → `0x610a5a14` → shooting-sequence
   vtable +0x5c `0x60b88e17` → 0x3bf → command 0x2a) only if
   `0x6108ad0a(0xb, 0)` returns 1. That function is the generic "is control
   action allowed in the current state" check.
2. **Where it fails.** On the second press the check fails at `0x6108b9c6`,
   which requires the word **`0x62b7f7b4` == 0**.
3. **Who sets that word.** It is set during the SCP=0 **AF-ON release** by
   `0x61088066`. The only clear that runs, `0x610883a3`, executes during the
   same release.
4. **What should clear it.** In the same step, `0x61088066` writes follow-up
   event **`0x0400001c`** (plus an argument) into the handler context's
   **pending-event slot +0xb0/+0xb4**. Handlers for that event clear the word
   through `0x61087044`: `0x610bb310`, `0x6109d8ad`, `0x6109dd6d` and
   `0x610a2067` (handler-table records `0x61312a80`, `0x61319f40`,
   `0x6131abf0` and `0x6131ba88`).
5. **Other clearers.** Handlers for `0x03000023` (`0x610b92da`,
   `0x610ac45a`; probably a timer-service event) and `0x09000022`
   (`0x610bb53b`, `0x610bbe60`; producer `0x610876ae`, not run) also clear it.
   None of these runs in consumer4.

**Reading.** The original edges are invoked directly through the resident
wrapper with a supplied context. The GUI state-machine engine, which in stock
code would dispatch the pending follow-up event, does not run, so the
release's state is never cleared.

This is most likely a **harness gap** in how original handlers are driven,
not stock behaviour that forbids repeated AF-ON. That is inferred and not yet
verified: neither the engine that consumes +0xb0 nor the run-time value left
there has been confirmed. Candidate readers of +0xb0 (`0x61087965` ran;
`0x610a322a` and `0x610cc43e` did not) are listed for the next step.

**The stock GUI engine (static decode, not yet run).**
- **The class.** The GUI state-machine class has its vtable at **`0x6133a46c`**
  (constructors reference it at `0x610beaef` and `0x610bfe68`). Slot +0x8 is
  the event engine **`0x610beb04`** (A0 = machine, A1 = context, current event
  at context+0).
- **What the engine does.** It runs a state hook through `0x610bfba3`, then
  dispatches on the machine's two state words, +0xb8 and +0xac. These are the
  same `0x5a05` and `0x5100` the harness writes into its machine object. The
  dispatch goes through the **state dispatcher `0x610bfc0a`**, which hashes
  state 0x5000–0x5e00 into `0x6133a26c` and reaches a per-state function. For
  0x5101 that function loads the descriptor array **`0x6131e7f0`** ({state,
  handler table, count}; state 0x5100 → table **`0x6131bd50`**, which holds the
  88 records including half press, AF-ON press and AF-ON release). The engine
  then handles class events through `0x6133a16c`, and its tail calls
  `0x610bf5b9` → `0x61094ed9`, which reads the context's +0xc0.
- **The pending-event writers.** Pending-event writers such as `0x6108a007`
  (33 callers), `0x6108a234` and `0x61088066` store an event at +0xb0 and a
  kind (2) at +0xc0.
- **Not established:** which stock code consumes +0xb0/+0xc0 and redispatches
  it. Neither `0x610beb04` nor `0x610bfc0a` runs in any probe.

**Consequence for the harness.** The feature is designed as **handler-table
wrappers** (`OFFLINE-AF-PROOF.md`): table entries `0x6131c290`/`0x6131c2a0`
and the half-press pair are redirected to native wrappers that run the profile
transaction and continue into the unchanged original handler. The harness calls
those wrappers directly, so the stock engine and its follow-up processing are
skipped.

**Next step:** a probe that does three things:
1. applies the feature's four table redirects in emulator memory (the intended
   modification itself);
2. delivers each button event through the stock engine `0x610beb04` with the
   harness's existing machine and context;
3. records context +0xb0/+0xc0 and `0x62b7f7b4` after each edge.

No clear may be supplied. If the stock flow clears `0x62b7f7b4`, the next
AF-ON press should resubmit LOCK_START natively.

**Engine-routed runs (`OM3EngineRoutedConsumerProof`, `engine-routed1..5/`).**
- **routed1–2:** stopped on the probe's own record check. At run time the four
  shooting-table handler fields already hold the resident wrappers
  `0x6031eb80`, `0x6031ec98`, `0x6031edb0` and `0x6031eec8`. The inherited
  `prepareResident` installs the feature's table redirect, so the harness was
  already in the designed modified-firmware state. The check now accepts that
  and writes nothing.
- **routed3:** each edge is delivered to the stock engine `0x610beb04`. The
  engine consults the machine's secondary state +0xb8 before the shooting state
  +0xac. The inherited fixture value **0x5a05** (written by
  `OM3ShootingRuntime`; provenance undocumented) selects table `0x61333858`.
  Its first record handles half press with `0x610b10b6`, and it has no AF-ON or
  half-release records, which looks like an overlay state. Half press was
  consumed there, and the shooting table was never consulted (profile check
  failed on edge 0).
- **routed4:** labelled fixture: secondary state **0** (none; stock
  `0x610bfc0a` returns no table below 0x5000 and the engine skips null
  tables), with shooting state 0x5100 kept.
  - **All 28 edges go through the stock engine → feature wrapper → original
    handler.** All return, and the original button/SCP matrix passes
    **28 / 28**.
  - There is still **one** LOCK_START submission (first AF-ON press, owner 2,
    subject 0).
  - The state word `0x62b7f7b4` becomes 1 at the first AF-ON release and stays
    1. The clearing handlers (`0x61087044` and its event handlers) never run.
  - The engine pre-filter `0x610bf5b9` runs on every edge, but `0x61094ed9`
    (the +0xc0 reader) does not.
- **routed5:** observation only; 28/28 again. `0x61088066` does **not** reach
  either follow-up store (`0x610880c1`/`0x61088180`), so the "unprocessed
  pending event" reading does not apply here. It takes this path instead:
  1. set the word to 1 at `0x61088126`;
  2. query the object from `0x610c8702` (vtable +0x2c, trace label
     **"isMoveEditActive"**) and clear the word immediately only if that
     returns non-zero; it returns 0;
  3. post the follow-up only if `0x6108856e` returns 0 and `0x6036e870` is 0;
     neither condition holds.

**What the state word is (firmware trace labels).** `0x62b7f7b4` is a
**display-output change in progress** flag, not AF state:

| Function | Role | Trace labels |
|---|---|---|
| `0x61088066` | setter | "Playback on EVF:Go to stby" and the output-line paths |
| `0x610883a3` | conditional clear | "CA->GUI CHG_OUT_LINE : TFT / VIDEO / EVF / INTERNAL_EVF" |
| `0x6108846d` | HDMI variants | "CA->GUI CHG_OUT_LINE : HDMI&…" |
| `0x61087044` | clearer | "setChangeStateDisplayCompleteSubAppMdlDispDevice()" |
| `0x6108ad0a` | permission check | "CHECK_IS_NOT_TAKING_PICTURE" |

The original AF-ON release issues its state event 9 (`0x61090e0a`), which
reaches this display output-line logic and starts a display-device change. The
camera clears the flag when the display module reports the change complete.
The harness has no display-module completion, so the flag stays set, and the
shooting permission check refuses later AF-ON starts.

**Conclusion.** The single LOCK_START in the matrix is caused by a missing
**display-change completion** in the emulation, not by AF profile or worker
behaviour. Why AF-ON release starts a display-output change at all in this
fixture is not established. It may come from the inherited
display/eye-sensor/output fixtures rather than camera behaviour.

**Not done (deliberately):** supplying a display-complete event or clearing
the flag. Either would fabricate a completion. Further options:
1. find the stock producer of the display-complete notification (the
   display-manager path that calls `0x61087044` through events
   `0x03000023`/`0x0400001c`/`0x09000022`) and model only its trigger as a
   labelled display completion;
2. find which fixture makes release choose an output-line change and correct
   it from stock state.

Neither affects the established AF-ON command chain or the 28/28 profile
results.

**Earlier next step (done above):** buffers 91–96 form the AF task family (ROM
halfwords from `0x6004322a`). Identify the task that serves buffer **92**: queue-95 handlers
`0x603c524c`, `0x603c531b` and `0x603c5378` send to it, and its loop likely
receives through the generic helper `0x6004d087`. Then schedule it like the
94/95 tasks. Its reply is produced by stock code or not at all. Nothing in
these runs fabricates an AF reply, acknowledgement or focus result.

## Unchanged position

Every acceptance gate stays open. The safe camera work is still stock-firmware
observation and characterising the recovery path. The research image must not be
installed.


## 9 November continuation: interrupt installer repaired

The actual local updates and PR head were reviewed before continuing. The newer
stage-0 work identified an interrupt-context mutex-create defect. Its revised
wrapper/installer now passes **28/28** engine-routed profile edges with one
feature mutex created in task context (`task-context-mutex2`). An isolated native
kernel probe confirms the E_CTX refusal (`native-mutex-context1`), and a native
loader/proposed-diff probe verifies all three uncompressed section loads and
3,612 proposed changed bytes with section 7 unchanged (`task-context-placement1`).
See [the stage-0 record](HARDWARE-STAGE0-RECORD.md#completed-verification) for exact
scope, source snapshots, hashes and the revised next work. The 28/28 result still
has one LOCK_START submission and the display-completion limitation. No camera
was accessed and no installable image was emitted. Every complete gate remains
open; **NO-GO** is unchanged.
