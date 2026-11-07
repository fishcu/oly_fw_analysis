# AF acceptance-gate closure assessment — 7 November 2026

This review covers the four acceptance gates in
[FEATURE-SPEC.md](analysis/button-af/FEATURE-SPEC.md#current-evidence-and-limits).
It began with static reading of the existing decompilation and byte searches of
the decoded main payload. Four supplemental emulator probes followed, each
extending the previous one; they are listed in the probe index below. No firmware
image was changed or written, and no camera was accessed.
**No gate is closed by this review. The readiness decision stays NO-GO.**

## Summary

- **Gate 1 (successful capture request/reply), software side.** The conditional
  event-114 backend connection now runs natively from the real caller, through the
  stock task-207 RPC loop, the inter-task transport and the stock port-2 link task.
  It stops at the hardware link to the **SCPU** (component 0107). The SCPU's reply
  would arrive on event flag 225. That exchange appears to be a power or USB-state
  query, not AF itself.
- **SCPU modelled as silent.** With the SCPU treated as not answering, the stock
  code handles the timeout and continues. It then stops at a mode lookup whose key
  comes from a record byte the harness never sets. That byte is derived from camera
  settings; where it is written is still open (see the last section).
- **Where focus is actually driven.** AF-ON's `setAflState` only produces a GUI
  lock-state notification and a live-view power-saving restriction. Focus is driven
  by the AF worker's `LOCK_START`, which comes only from AF-command queue 95,
  entries 42 and 44. No fixed-command production sender of those entries exists, so
  the AF start request is computed at runtime.
- **Not started:** gates 2–4 (orientation, synchronisation, install and recovery).

## Probe index

All probes are supplemental. None is part of `scripts/run_om3_live_offline.ps1` or
of the 7 November full run. Each extends the one before it.

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

## Unchanged position

Every acceptance gate stays open. The safe camera work is still stock-firmware
observation and characterising the recovery path. The research image must not be
installed.
