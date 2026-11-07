# AF acceptance-gate closure assessment — 7 November 2026

This review covers the four acceptance gates in
[FEATURE-SPEC.md](analysis/button-af/FEATURE-SPEC.md#current-evidence-and-limits).
It used static reading of the existing decompilation and byte searches of the
decoded main payload. No emulator run, firmware change or camera access took place.
**No gate is closed by this review. The readiness decision stays NO-GO.**

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

## Gate-by-gate status

| Gate | Can it be closed offline? | What is actually missing |
|---|---|---|
| 1. Real capture-backend connection and a successful request/reply | **Partly.** The kernel boundary can be pushed further. A genuine *reply* cannot be produced without the mailbox peer. | (a) Per-core kernel control blocks, which only the stock kernel startup creates, and that startup needs a multi-core barrier. (b) The normal producer of event 0x114. (c) A real port-2 completion from the peer behind the `0xa32c65b0` mailbox. |
| 2. Physical orientation producer, target edit and display | **Partly.** The producer can be traced statically. Exercising it needs the stock UI task running. | The sensor-driver → orientation-code path, plus stock target-edit and display events under a running GUI task. |
| 3. Synchronisation and lifetime of staged target records | **Design work, yes. Proof, no.** | The kernel is multi-core. So cross-core visibility, not just interleaving within one thread, has to be argued from the core memory model and the kernel's lock primitives. A single-thread emulator can't demonstrate it. |
| 4. Full init, settings reload, updater acceptance, recovery | **No.** | Only real hardware shows whether the updater accepts the image and whether recovery works after a failed modified boot. Static work can only narrow the risk. |

## Recommended next offline steps, in order

1. **Model the per-core control block from stock code, not from invented values.**
   Run the kernel init path natively up to the barrier at `0x60033387`, with
   the core count forced to 1 (`+0x17c`). Record that override as an explicit
   model. Then rerun `OM3CaptureConnectedProof` to find the next boundary. Expected
   outcome: progress into task/object creation, then a stop at the mailbox wait.
2. **Identify the port-2 peer.** Trace who writes and reads `0xa32c65b0` and the
   signal routine `0x60037413`. Check whether the peer is code in another image
   component (0101 at `0x41ec0020`, 0102, 010e). If its code is in the image,
   running both sides together is the only way to get a real reply offline. If it
   is fixed hardware, gate 1 cannot be passed offline, and the honest end point is
   the mailbox boundary.
3. **Trace the orientation producer statically.** Start from the pose codes the
   profile suite already uses, and walk backwards to the sensor driver.
4. **Write the gate-3 design argument.** Cover which kernel lock the readers take,
   whether the staged records sit in uncached memory on every core, and how an old
   pointer is retired.

## Unchanged position

Every acceptance gate stays open. The safe camera work is still stock-firmware
observation and characterising the recovery path. The research image must not be
installed.
