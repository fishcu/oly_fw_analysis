# Hardware phase: stage 0 record

Stage 0 of [HARDWARE-PHASE-PLAN.md](HARDWARE-PHASE-PLAN.md). Nothing has been
flashed, and no installable image has been built. Readiness stays **NO-GO**.

## 1. Owner decisions (to be completed by the camera owner)

| Decision | Owner's entry |
|---|---|
| Accepts the risk of a camera that will not boot and may not be recoverable | **Accepted for stages 1–3 only** (10 November 2026). Stages 4 onward need a separate decision. |
| A second, expendable OM-3 body is available | **No: one body only** (10 November 2026). Every stage runs on the owner's only camera. |
| Settings backed up (OM Workspace or OI.Share) before stage 1 | _pending: record in section C of the stage-1 log_ |
| Go/no-go for stage 1 (stock re-flash rehearsal) | **Go** (10 November 2026), using [HARDWARE-STAGE1-2-LOG.md](HARDWARE-STAGE1-2-LOG.md). |

## 2. Stock inputs (verified 8 November 2026)

| Item | SHA-256 |
|---|---|
| Container `firmware/catalog/OLY_E_147_1100_0000_0000.BIN` (240,517,120 bytes; catalog model 1470, version 1100, published 2025/07/01) | `8c133084414533159f587bf46bfb4152714c4074312a47c8d8503e33d605696d` |
| Component `0x0100` main | `5e8d376e9111a44ac0352f26030d7c1b17026d42c45f3600cfa02a0e8c5b7d59` |
| Component `0x0101` | `6d2bef74b4b2fa089f271529482f96505a170b91e79ab9b1a13f3ce8f7918226` |
| Component `0x0106` | `3d9fd4426b45fbe4b715599422af38c6d22392c08543a69f63c28291c5a0b059` |
| Component `0x010e` | `b9200daf346a53aaae9fd2908740f5f17d867309ba958e703e70169cb114ca87` |
| Component `0x0102` | `494cd9ef134a91503a12e852e56fc6c42b7c94c07116b889991b38c0fcf74c09` |
| Component `0x0107` (SCPU) | `9a9e7abef58daf72da495f8e18140043ecf2632b0ae5ea820e83be2ae2d0e377` |

The container hash matches this repository's import manifest. All six
component hashes match OM-Emu's independent `BLOBS.sha256` pins.

**Owner action:** keep at least two off-camera copies of the container and
confirm each copy against the container hash above.

## 3. Update and recovery routes (offline research)

**Firmware evidence (verified in our decoded main).** The stock main contains
the SD update client and service strings:

| String | Addresses |
|---|---|
| `DCOLYMP` | `0x606253b5`, `0x612ea303`, `0x612ea41a` |
| `E147????BIN` | `0x612ea12c`, `0x612eaeab` |
| `S147????BIN` | `0x612ea120` (purpose unknown) |
| `FIRMUP_SRV` | `0x602ee307` |
| `Execute_FirmwareUpdate` / `Check_FirmwareUpdate` | from `0x60ef7726` |
| `[firmup]mount_ok` | `0x612ea2f1` |
| USB `GetFirmwareUpdateMode` | from `0x61996182` |

These match the addresses in the OM-3 recovery notes of Ax72864's fork of the
upstream repository.

**Manual SD route** (community guide `iKenndac/om-1-manual-firmware-install`,
which lists the OM-3 explicitly):
1. Create folder `DCOLYMP` at the card root and put the firmware there named
   **`E1479999.BIN`**.
2. Card in slot 1, camera off. Hold **OK** while powering on.
3. The screen stays blank; a **solid orange** front lamp means installing.
   Release OK, and never cut power during this phase.
4. After a few minutes the lamp **blinks**, meaning done. Power-cycle, then
   delete the file from the card.

The guide also:
- says the camera re-installs the same version if the file is present, so a
  same-version rehearsal is possible by this route;
- says the method is unofficial and at the user's own risk;
- says settings are not preserved;
- has download links that stopped working in late 2025 (irrelevant here: the
  container is archived locally).

**Official routes:** OM Workspace over USB (MTP for the OM-3), and OI.Share over
Wi-Fi. Both are reported as not allowing downgrades.

**Not established anywhere:**
- recovery of a camera that does not boot;
- the meaning of other lamp states, such as the solid red seen on the OM-5 II;
- an immutable rescue ROM.

The only recovery evidence on the same firmware generation is the OM-5 II
owner's report: the stock SD reflash recovered the camera after two
boot-looping modified images, once on the second attempt.

## 4. Exit criteria before any image with new code

| Criterion | Status | Evidence / next step |
|---|---|---|
| **Runtime loading** of the code area | **Established statically; needs hardware confirmation** | See below. |
| **Placement** in the FF tail | Partly | All 1,912 bytes from `0x60a8f088` to `0x60a8f800` are `0xFF` in stock. In the older variant, the 1,780 packed bytes left 132. The live layout places 1,869 B (`0x60a8f088`–`0x60a8f7d5`), which leaves **43**. Whether anything at run time uses section-4 padding is not established; next, search for references into the tail range and for writes at run time. |
| **Owned data RAM** | **Largely established offline; hardware and cache confirmation remain** | See "Owned RAM analysis" below. |
| **Alignment and access** of new code | **Live layout audited (9 November): aligned, with every state access through the uncached alias; one open cache question** | See "Alignment and access audit" and "Live-variant re-audit" below. Open: the section-7 handler-field stores go through the cached alias; this depends on the task/core of `0x6017a5fc`. |
| **Narrow diff** | Proposed full-feature layout enumerated offline | `task-context-placement1/proposed-changed-bytes.csv`: 3,612 changed bytes, all in uncompressed sections 1/2/4; section 7 identical to stock. This is a scenario-specific in-memory proposal with unrepaired checksums, not an installable or stage-specific image. |

**Runtime loading, in detail:**
- **Uncompressed storage.** Section 4's descriptor (`0x60029b28` + 3×12) is:
  destination `0x60828000`, source `0x50807000` (main component offset
  `0x807000`), compression flag **0**. Only sections 6 and 7 are flagged
  compressed.
- **Range.** The stock loader `0x60045ed5` copies section 4 to
  `0x60828000`–`0x60a8f800` (end from the selector `0x60045e6c`). The planned
  code tail ends exactly at the section end.
- **Emulator check.** The harness's `load(4)` check confirms that the native
  loader reproduces every byte of the range.
- **Consequence.** The code is placed by editing plain main-component bytes,
  with no recompression. This avoids the compressed-stream risk class seen in
  the OM-5 II incidents, but not the risk of new code running at boot.

## Owned RAM analysis (8 November)

**What the feature uses.** The resident design does not use the compact
test's `0x700c…` addresses. It uses padding at the ends of three sections:

| Area | Range | Size | Use |
|---|---|---|---|
| Section 1 tail | `0x6031e920`–`0x6031f000` | 1,760 B | profile state `DATA = 0x6031e920` (accessed through the uncached alias `OWN = 0xa031e920`) and wrappers from `0x6031eb80` |
| Section 2 tail | `0x607187a4`–`0x60718800` | 92 B | mode block `MODE_DEST` |
| Section 4 tail | `0x60a8f088`–`0x60a8f800` | 1,912 B | packed code |

**Findings:**
1. **No overlap between sections.** The ten sections have disjoint
   destinations (from the descriptors at `0x60029b28` and the end selector
   `0x60045e6c`). The three areas lie inside sections 1, 2 and 4, none of
   which is compressed.
2. **Loaded once, at boot.** The only caller of the section loader is boot task
   `0x600455c5` (creation record at `0x6003e8c0`; priority 0x38, stack 0x300),
   which loads sections 1 to 10 once each, in order. The loaded-bit word
   `0xa32de590` is only ever OR-ed, inside the loader. Nothing in the main
   firmware unloads or reloads a section. A power cycle reruns boot, and the
   feature reinitialises then.
3. **Stock bytes are padding.** Every byte of all three areas is `0xFF` in
   stock.
4. **No stock references.** A whole-image scan for 32-bit values inside any of
   the areas, at any byte alignment and through both the cached and uncached
   aliases, finds 12 candidates. Eleven are coincidental byte patterns inside
   unrelated instructions or data. One is real: `0x60215405`
   `mov 0x60a8f088,A2` in **section-4 static-constructor group `0x602153fb`**,
   whose count is **0**, so the table is never read. It is the linker's empty
   constructor table at the end of section 4.
   - *Caution:* making that count non-zero would make the area run as
     constructors at boot.
   - *Design note:* using this group as a boot-initialisation hook would add
     new code that runs at boot, the riskier category in the OM-5 II
     incidents. Prefer first-use initialisation from the wrappers.
5. **Dynamic check (OM-Emu, native OM-3 E147 v1.1, components session).**
   Log-only read/write watchpoints on all three areas, through both aliases,
   recorded **no access** while the session was exercised with half press,
   AF-ON and other inputs. All three areas were still entirely `0xFF` after
   OM-Emu's native kernel, GUI and camera-application start-up.
   *Limit:* OM-Emu does not run the physical section loader or the ISP, AF and
   release modules.

**Still open for this criterion:**
- **Cache coherence.** The state is written and read through the uncached
  alias, but the wrapper code runs from the cached alias of section 1. Every
  data access in the packed code must use the uncached alias; this belongs in
  the alignment and access audit.
- **Code, not just data.** Show that nothing in the secondary CPUs or DMA
  writes to these physical pages. Only a static and OM-Emu argument exists so
  far.
- **Hardware read-back.** Confirm on hardware at stage 5 that the placed bytes
  remain intact after boot, sleep/wake and mode changes.

## Alignment and access audit (8 November)

**Method.** `scripts/OM3ResidentAccessAudit.java` (run
`analysis/button-af/readiness/resident-access-audit2/`) performs the stock
resident preparation (`OM3ResidentProof.prepareResident`) in the emulator,
then disassembles every placed block at its final address:

| Block | Address | Size |
|---|---|---|
| packed code | `0x60a8f088` | 1,869 B |
| patched accessor | `0x609b3bb2` | 9 B |
| patched entry | `0x603cedfe` | 5 B |
| table redirects | four entries | — |

Nothing is written to any image.

**Clean results:**
- every byte decodes; there are no undefined opcodes and no instruction spans
  a block end;
- every absolute word and halfword access is naturally aligned, as is the one
  register-relative access whose base is known;
- the code never writes into its own code areas;
- of the call and jump targets, 91 are inside placed code and 12 are stock
  function starts;
- the one remaining target, `0x603cee05`, is the trampoline's intended return
  point: the 5-byte patch at `0x603cedfe` displaces `mov D0,D3` and
  `movbu (0x62a6a0eb),D2`, which the trampoline at `0x60a8f644` reproduces
  byte-for-byte after a one-byte guard. Stock reads are made through the stock
  uncached addresses (`0xa33a1d10`, `0xa33ca2b8` and others) and two stock
  cached addresses (`0x62f757d0`, `0x62a6a0eb`).

**Finding 1: mixed cache aliases for feature state (material).**
- **Cached side.** All 40 resolved state accesses use the **cached** alias
  `0x6031e920`–`0x6031e940` (header bytes, the active-cache pointer at +8, and
  bank +0x20). So does the patched stock accessor `0x609b3bb2`
  (`mov (0x6031e928),A0`).
- **Uncached side.** In the consumer runs, the AF worker read the active
  profile bank through the **uncached** alias (`active-cache=a031ea00`, i.e.
  DATA+0xe0).
- **Unresolved.** 29 register-relative accesses have a base the static pass
  cannot resolve; the bank writes are probably among them.
- **Risk.** If the main CPU's data cache is write-back, data written through
  one alias and read through the other can be stale. The emulator has no cache
  model, so it cannot reveal this.
- **Needed before stage 5:**
  - choose one alias for all feature state (uncached is the simplest choice),
    or add explicit cache write-back/invalidate at the hand-off points;
  - confirm the cache type from stock code (how stock shares data with the AF
    tasks);
  - add a runtime alias and alignment checker to the 28-edge emulator run, to
    resolve the 29 unknown-base and 48 stack accesses.

**Finding 2: table redirects are in a compressed section (material).**
- **Where they are.** The four shooting-table handler fields (`0x6131bd5c`,
  `0x6131bd6c`, `0x6131c29c`, `0x6131c2ac`) lie in **section 7**
  (`0x6103f000`–`0x6164b000`), which is stored **compressed** (descriptor flag
  1).
- **Why it matters.** Writing them into an update image means re-encoding
  section 7. That is the risk class in the OM-5 II incidents (changed
  compressed streams).
- **The other patches are uncompressed.** The accessor (`0x609b3bb2`) is in
  section 4 and the entry patch (`0x603cedfe`) in section 2; neither needs
  recompression.
- **Alternatives to evaluate:**
  - **(a) Runtime redirect.** Section 7 is decompressed into RAM at boot, so
    the table could be redirected at run time by already-placed code, leaving
    section 7 byte-identical. That needs a hook that runs before the first
    button dispatch, and it must not be the section-4 constructor group, which
    would be new code running at boot.
  - **(b) Recompression.** Re-encode section 7 with stock's encoder parameters,
    and prove a byte-identical round trip of the unmodified stream first.
  - (a) keeps the image's compressed sections stock-identical, which the OM-5 II
    evidence favours.

**Runtime redirect: where could the installer run? (8 November)**

The redirect must be installed in RAM after section 7 is decompressed and
before the GUI engine dispatches the first button event. The findings so far:

- **The existing hooks are too late.** The entry patch `0x603cedfe` runs only
  inside button handling (consumer traces: first hit after the first edge
  began), after the engine has chosen the handler. The accessor `0x609b3bb2`
  runs in the AF worker, later still.
- **The GUI dispatch path is compressed.** In OM-Emu's native OM-3 session, a
  breakpoint on the engine `0x610beb04` stops for real events: timer-class
  `0x0300002f` and `0x03000030`, and the half press `0x01000002` itself. The
  return address is `0x61081bd7`, in function `0x6108166e`, which has no
  static caller (it is reached through the framework), in section 7. The
  framework frames visible on the stack (`0x60aed738`) are in section 6. So the
  dispatch path is entirely compressed code.
- **The section-2 producers are not on this path.** Eight functions in
  uncompressed section 2 build event `0x01000002` (`0x604b3cf8` …
  `0x604cb341`), but none of them ran before the engine received the half press
  in OM-Emu.
- **The raw key-input layer looks uncompressed.** OM-Emu places UI_IN's port
  initialisation and decoder in base or section-1 code (disassembly
  `0x5014…`/`0x5005…`, i.e. runtime `0x6016…`/`0x6007…`), but its notes are
  for the OM-1; the OM-3 addresses are not yet pinned.

**Installer options:**

| Option | Runs | Failure surfaces | Compressed sections | Status |
|---|---|---|---|---|
| (1) Hook in the raw key-input (UI_IN) publish path, uncompressed | on every key, before the camera application maps it to a GUI event | at the first key press; the camera still boots | untouched | OM-3 hook site to be identified and checked to precede GUI dispatch |
| (2) Tail of boot task `0x600455c5` after section 10 loads (base, uncompressed) | once at boot | **at boot**: the OM-5 II failure mode | untouched | site known; the risk class is the one to avoid |
| (3) Recompress section 7 with the redirect written in | n/a | at boot if the encoding is wrong | **modified** | needs a byte-identical round trip of stock first |

**Hook site located (8 November): option (1) is feasible.**

**Method.** In OM-Emu's native OM-3 session I traced every instruction
executed in uncompressed code (base and sections 1–5) from an injected half
press until the engine received `0x01000002`: 22,130 instructions and 146
functions. I compared that against an idle sample: 89 functions appear only
with the key. The key path runs through:
1. base port and interrupt helpers (`0x600709dc`, `0x6007071e`, `0x60070793`);
2. the **section-1 UI_IN key decoder** (`0x6017a5fc`, `0x60178695`,
   `0x601789xx` …);
3. section-2 handling (`0x6041…`, `0x6044…`);
4. only then the compressed camera application and the engine.

**Chosen entry: `0x6017a5fc`,** the key-port callback (section 1,
uncompressed; registered through the pointer at `0x6017a5d8`).
- **Prologue.** Its prologue is exactly **5 bytes of whole,
  non-PC-relative instructions**: `cf20` `movm [a2],(sp)` and `f8fef8`
  `add -0x8,sp`. A 5-byte `jmp` can replace them, and a trampoline can replay
  them and resume at `0x6017a601`, the same pattern as the verified
  `0x603cedfe` hook.
- **Behaviour.** It reads the key ports through `0x6007071e`/`0x60070793` and
  returns early when nothing changed.
- **Ordering.** With breakpoints on both the hook and the engine, the hook ran
  **before** the engine received the key events it decoded: half-press release
  `0x01000003`, and AF-ON down (`0x01020001` in this movie-mode session).
- **Context.** At the hit, SP was `0x62f075e0`, a RAM task stack, which
  suggests task context rather than an interrupt. The exact task is not pinned.

**Installer design** (not yet built):
1. **Entry.** Replace `0x6017a5fc`'s 5-byte prologue with `jmp` to the placed
   trampoline.
2. **Fast path.** If the feature's "installed" byte is set, replay the prologue
   and `jmp 0x6017a601`.
3. **Install path, only if section 7 is loaded** (`0xa32de590` bit 6). Save the
   registers it uses. For each of the four records (`0x6131bd5c`, `0x6131bd6c`,
   `0x6131c29c`, `0x6131c2ac`; all 4-byte aligned): if the field still holds
   its **stock** handler (`0x610b9197`, `0x610b96f0`, `0x610b962a`,
   `0x610b9653`), store the wrapper address. Otherwise leave it and record why.
   Set "installed" only if all four are consistent. Restore the registers,
   replay the prologue, and resume.
4. **What stays untouched.** Section 7 stays byte-identical to stock, and no
   code is added to the boot path. If the callback is ever invoked during boot
   before section 7 loads, the loaded-bit guard defers installation.

**Open before building it:**
- **The task.** Pin the task or core that runs `0x6017a5fc`. If the GUI reads
  the table from a different core, the store needs the same cache treatment as
  Finding 1.
- **AF-ON event mapping.** Confirm the stills-mode AF-ON event mapping:
  OM-Emu's OM-3 runs in movie mode, so the stills event codes
  (`0x01050007`/`0x01050008`) were not observed there.
- **Emulator proof.** Prototype it in the Ghidra harness (installer via the
  hook, then the engine-routed 28-edge matrix with the table entries initially
  stock).

**Prototype result (`OM3RuntimeRedirectProof`, run
`analysis/button-af/readiness/runtime-redirect1/`).**
- **Setup.** The engine-routed consumer chain starts with the four section-7
  handler fields **restored to their stock handlers**, as the camera image
  ships. A native installer is assembled, and the 5-byte prologue at
  `0x6017a5fc` is replaced with `jmp` to it. The disassembly in
  `installer-disasm.txt` matches the design instruction for instruction: 266
  bytes, using only D0 (saved and restored) and flags.
- **Fixtures (labelled).**
  - The key-port reads return "no change", so the stock callback leaves
    through its own early exit (`0x6017a61a`).
  - The section-7 loaded bit is set explicitly for the install case; the
    harness image holds section 7's bytes but does not run its loader.
- **Controls.**
  - Loaded bit clear: the installer **deferred**; all four fields stayed stock
    and it was not marked installed.
  - One field set to a foreign value: the installer **did not mark itself
    installed** and **did not overwrite that field**. However, it had already
    redirected the two fields before it (see refinement 1).
  - Normal case: all four fields hold the wrappers (`0x6031eb80`,
    `0x6031ec98`, `0x6031edb0`, `0x6031eec8`), and installed = 1.
  - D0 preservation was checked at the resume point `0x6017a601` on every
    hook run.
- **Matrix.** The hook's fast path then ran before each of the 28 edges. The
  stock engine called the wrappers 28 times, and the original button/SCP
  matrix passed **28 / 28**, with the same single LOCK_START submission as
  before. Section 7's bytes are never written by any image: the redirect
  exists only in RAM.

**Refinements required before stage 4:**
1. **Validate all four, then write.** The control shows that a foreign value in
   a later field leaves earlier fields already redirected (half press wrapped,
   AF-ON stock). The installer must first check that every field holds its
   stock handler (or already holds the wrapper), and only then write all four.
2. **Size and placement.** 266 bytes does not fit in the free space of the
   current layout (43 bytes left in the section-4 tail, 32 in the section-1
   tail). Options:
   - choose the section-4 wrapper variant, which frees the section-1 wrapper
     area `0x6031eb80`–`0x6031f000` (1,152 bytes);
   - make the installer table-driven (four {field, stock, wrapper} triples
     plus a loop; roughly 100 bytes of code and 48 of data).

   This decision also settles Finding 3 (one final layout).
3. **Task/core and cache.** As above, pin the task that runs the callback, and
   apply the Finding 1 cache policy to the table stores if the GUI reads them
   from another core.
4. **Stills-mode event codes.** Confirm the stills-mode AF-ON event codes on
   the camera at stage 2.

**Refined installer (v2), run `runtime-redirect3/`.**
- **Encodings.** All new encodings were confirmed against stock instructions
  first (`cff0`/`cef0`, `7a`, `f1eb`, `73`, `f80a04`/`f80a08`, `a8`, `6b`,
  `220c`, `2bff`, `8f04`).
- **Design.** It is table-driven: four {field, stock, wrapper} entries.
  - **Pass 1** checks every field (each must be stock, or already the wrapper)
    and writes nothing if any field is foreign.
  - **Pass 2** writes all four.
  - It saves and restores D2, D3, A2 and A3 on the stack and D0 in scratch;
    the disassembly matches the design.
- **Size.** **111 bytes of code + 48 bytes of table = 160 bytes** (v1 was 266).
- **Controls.**
  - Section 7 not loaded: deferred.
  - **One foreign field: no field written at all**, and not marked installed.
    Refinement 1 is fixed.
  - Normal case: all four installed. D0 preserved on every run.
- **Matrix.** The fast path ran before all 28 edges, the engine called the
  wrappers 28 times, and the matrix passed **28 / 28** (one LOCK_START).
- **Placement still open.** v2 was run from emulator scratch memory (labelled
  in the probe). The intended gap `0x6031ead0`–`0x6031eb80` is already used up
  to `0x6031eb4a` by the boot initializer (Finding 4); 52 aligned bytes remain.
  See the consolidation recommendation below.

**Finding 4 (8 November): the current design already runs new code at boot.**

`OM3BootMutexProof`, part of the tested resident chain, changes three things:
- it places a 122-byte **boot initializer at `0x6031ead0`–`0x6031eb4a`**,
  which creates the feature's dedicated mutex through `0x60030659`;
- it places a one-entry constructor table at `0x6031e910`;
- it patches the **section-4 static-constructor group** at `0x602153fd`
  (count 0 → 4) and `0x60215407` (table → `0x6031e910`). Both are in section 1,
  uncompressed.

So the initializer runs from the stock constructor loop **at boot**. This is
the boot-path category in the OM-5 II incidents. Its offline tests pass
(creation success, modelled failure, idempotent re-run), but a fault there
would show as a boot failure rather than a fault at the first key press.

**Recommendation:** consolidate the mutex creation into the first-use runtime
installer. Both are one-time initialisations, and the installer already runs
before the first button dispatch.
- This removes the constructor-group patch, so no new code runs at boot.
- It frees 122 bytes plus the table entry.
- **Placement after consolidation.** The section-1 gap
  `0x6031ead0`–`0x6031eb80` (176 bytes) would then hold the combined installer
  and its table, if the combined size fits; this has to be measured. If not,
  the wrapper layout must be revisited: the section-1 wrappers use 4 × 280 bytes.

**Consolidated first-use installer (v3): Finding 4 resolved in the emulator.**
`OM3ConsolidatedInstallerProof` (runs `consolidated-installer1`…`5`; the
final run is `consolidated-installer5/`).

- **Boot hook reverted.** In the emulated image, `OM3BootMutexProof`'s boot
  hook is reverted to stock (constructor count `0x602153fd` = 0, table pointer
  `0x60215407` = `0x60a8f088`, initializer and table entry back to `0xFF`), so
  the section-4 constructor loop is a stock no-op. After boot there is **no
  feature mutex** (S+17 = 0, S+20 = 0): **no new code runs at boot**.
- **One routine does both jobs.** The first-use installer at the key-port hook
  creates the mutex through `0x60030659`, using the same packet as the boot
  initializer, and then installs the redirect.
  - **Register safety.** D1, A0 and A1 are preserved around the OS call; D0
    and A0 for the whole routine; D2, D3, A2 and A3 by `movm`.
  - **Failure handling.** If creation fails, the feature is disabled
    (S+6 = 0, S+17 = 2) and no redirect is written. A later key press retries.
  - **Encodings.** All new encodings are confirmed against stock instructions.
- **Placement.** **174 of 176 bytes** in the freed section-1 gap
  `0x6031ead0`–`0x6031eb7e`, and the 48-byte table in section-2 padding
  `0x607187d0`–`0x60718800` (after the mode block). Both sections are
  uncompressed. Only `0x6017a5fc` (5 bytes, section 1) changes in stock code
  for this purpose. Section 7 is unchanged.
- **Two bugs found and fixed while building it:**
  1. The "installed" byte is section-1 padding, so on the camera it starts as
     **0xFF**. A test of "≠ 0" would never have installed anything. The
     installer now treats only 1 as installed; the run checks the real initial
     value (0xFF) without pre-zeroing it.
  2. Branch distances: an exit block in the middle of the routine keeps every
     branch within the short range.
- **Controls, all passed:**
  1. Section 7 not loaded: no mutex, no redirect.
  2. Modelled mutex-create failure: S+6 = 0, S+17 = 2, S+20 = 0, no redirect.
  3. Retry with one foreign field: mutex `0x40e` created, **no field
     written**, not installed.
  4. Install: no second mutex, all four wrappers written, installed = 1.
- **Matrix.** The hook ran before all 28 edges, the stock engine called the
  wrappers 28 times, every edge **locked and unlocked the runtime-created
  mutex** (28 takes, 28 gives), and the matrix passed **28 / 28** (one
  LOCK_START, as before).
- **Fixtures (labelled).**
  - Key ports report "no change".
  - The section-7 loaded bit is set.
  - The mutex-create failure is modelled.
  - The feature-enable byte is restored to its profile value after the failure
    control.

**Correction to Finding 1 (cache aliases).** The alignment audit extended
`OM3ResidentProof` directly, which maps state to the **cached** alias. The
tested live chain (`OM3LiveProfiles`) overrides `dataAddress` to map all state
to the **uncached** alias `0xa031e9xx`. The installer uses the uncached alias
too. Finding 1 may therefore apply only to the older variant. The audit must be
rerun on the live variant before the cache-policy question is closed.

**Live-variant re-audit (9 November): Finding 1 closed for the feature state.**

`OM3LiveAccessAudit` (extends `OM3ConsolidatedInstallerProof`; run
`analysis/button-af/readiness/live-access-audit2/`) audits the tested layout
from emulator memory, right after the installer has been installed. It covers:
- the nine live blocks: the section-4 tail `0x60a8f088`–`0x60a8f7d5`, the mode
  block `0x607187a4` and the wrappers `0x6031eb80`–`0x6031efe0`;
- the installer (174 B at `0x6031ead0`);
- the hook `0x6017a5fc`;
- the accessor and entry patches;
- the installer table at `0x607187d0`.

**Fixes to the old audit's method.**
- **Signed constants.** The disassembler prints `0xa031e920` as `-0x5fce16e0`,
  and the old pattern missed every such constant. They are now resolved.
- **Register copies.** Constants are followed through register-to-register
  moves.
- **Fixed base registers.** A callee-saved register written exactly once, by
  an immediate move, keeps its value across branches and calls. This holds the
  installer's state base A3.
- The same 28/28 matrix ran in the same run, with the same intentional
  boundaries as `consolidated-installer5`.

**Result (one pass).**

| Check | Count |
|---|---|
| Feature-state accesses through the **cached** alias | **0** |
| Misaligned absolute or resolved accesses | **0** |
| Writes into code areas | **0** |
| Decode failures or undefined opcodes | **0** |
| State accesses through the uncached alias `0xa031e920`–`0xa031eacf` (absolute R/W, resolved register-relative R/W) | 45 / 28, 6 / 12 |
| Stock RAM reads, uncached | 11 + 2 |
| Stock RAM reads, cached | 2 |
| Section-7 handler-field stores (installer) | 4 |
| Unresolved register base (resolved by hand, below) | 42 |

**Remaining items, resolved by hand from the listing:**
- **Section-4 halfword copies and compares (26).**
  - **Copy loops.** A0 is the stock record `0xa33f2ce0` or the Home bank
    `0xa031eaa0` + 16·n. A1 is one of `0xa031e9e0`, `e9f0`, `ea00` or `ea10`,
    chosen by comparison with the active pointer and saved at `0xa031e94c` or
    `0xa031e95c`.
  - **Compare loop.** A0 is one of those saved pointers, and A1 is stock
    `0xa33ca384`.
  - **Alignment.** Every base is even, and the steps are +2, so all accesses
    are aligned halfwords through uncached aliases.
- **Home builder (11).** A3 is one of `0xa031eaa0`, `eab0` or `eac0`, depending
  on the orientation (0/1/2); these are uncached state. Bytes are written at
  +2, +3, +8 and +9, and halfwords at +0, +4 and +6, so all are aligned.
- **Installer loops (5).** A2 is `0x607187d0` + 12·k, which is word-aligned. A0
  takes the table's field values, all four of which are word-aligned and inside
  section 7 (checked by the script).
- **Cached stock reads.** The feature reads `0x62a6a0eb` (the SCP mode byte,
  replayed from the displaced stock instruction in the mode block) and
  `0x62f757d0` through the cached alias, as stock code does. It only reads
  them.
- **Jump and call targets that are not function starts (3).**
  - `0x603cee05` and `0x609b3bb8` are the stock instruction boundaries after
    the displaced instructions (entry: `mov D0,D3` + `movbu`, 7 B; accessor:
    `movbu`, 6 B).
  - `0x609b3ecd` is the stock target-type conversion routine, already used
    natively in the lifecycle proofs. It has no Ghidra function record.
- **Block-end span (1).** The 9-byte audit window at the accessor runs past
  the 5-byte jump into unchanged stock bytes. This is a property of the audit
  window, not of the code.

**Conclusion.** In the live layout, every feature-state access goes through
the uncached alias, so Finding 1 (mixed aliases) does not apply. It was an
artifact of the older `OM3ResidentProof` variant.

**One cache question remains (Finding 1b): the installer's four section-7
handler-field stores** (`0x6131bd5c`, `0x6131bd6c`, `0x6131c29c`,
`0x6131c2ac`).
- They go through the **cached** alias, which is the alias the GUI engine
  reads them through.
- That is coherent if the key-port callback `0x6017a5fc` runs on the same core
  as the GUI dispatch. If it runs on another core, the stores need a
  write-back (or an uncached store plus invalidation on the reader) before the
  reader's cached copy can be trusted.
- This joins the open "task/core of `0x6017a5fc`" item. The fields are data,
  so no instruction-cache maintenance is involved.

**Recommendation:** pursue (1).
- **The installer.** It is a few aligned word stores, each guarded by a
  stock-value check (each handler field must still hold its original handler).
  It runs once, and only when the section-7 loaded bit (`0xa32de590` bit 6) is
  set.
- **Fallback.** If no suitable UI_IN site precedes GUI dispatch, (3) with a
  proven round trip is preferable to (2).

**Finding 3: two placement variants exist.** `OM3ResidentProof` redirects the
tables to wrappers inside the section-4 code (`0x60a8f650`, `0x60a8f69b`,
`0x60a8f6e6`, `0x60a8f731`). The live/consumer chain uses wrappers at
`0x6031eb80`–`0x6031efe0` in section 1. The narrow diff must name one final
layout.

## Hook task and core (9 November)

Evidence: `analysis/button-af/readiness/hook-core1/observations.txt`.

**How the hook is reached (static).**
- **Registration.** `0x6017a5fc` is put in a 4-slot callback table
  (`0xa32bff50`) by `0x600706b0`.
- **Caller.** The table's only caller is `0x600709dc`. It reads and clears the
  sub-CPU window's pending word `0x98e00098`, then calls each slot.
- **Interrupt.** `0x600709dc` is the handler for **IRQ 0x140 (320)** at level 5.
  It is attached through `0x6007602b`, which attaches on the core that calls it
  (`(0x8050)`), and attachment is exclusive. The calling path is
  `0x60070482`, called once from the boot core's init chain in
  `om3_application_entry` (`0x60021249`). No other attachment of IRQ 0x140
  exists.
- **Name table.** UI_IN, CA_MAIN and HIGHLEVEL_MAIN are core-0 objects.

**Observed in OM-Emu** (breakpoints on the hook and the engine, half press
down and up).
- **The engine** received `0x01000002` in **task 165** (ID `0xa5`, core field
  0), on a task stack.
- **The hook** ran with **no task running**:
  - the interrupt-nesting byte was 1;
  - SP `0x62f075e0` was inside core 0's interrupt stack
    (`0x62f05600`–`0x62f07600`);
  - it was called from the slot dispatcher (`0x60070a13`).
- **Lab limit.** OM-Emu runs only CPU 0, and it makes the IRQ 320 attachment
  itself in place of the firmware's init.

**Conclusion 1: same core. Finding 1b is closed (offline).** The hook and the
GUI engine both run on **core 0**. The installer's four section-7 stores go
through the cached alias and are read through the same core's data cache, so
no cross-core cache maintenance is needed. The remaining assumption, that the
boot core is core 0, matches the OM-1 core analysis; hardware still has to
confirm it.

**Conclusion 2: new material finding (Finding 5). The installer runs in
interrupt context, and the mutex creation in it would fail on the camera.**
- **The failure.** `0x60030659` returns **-25 (E_CTX)** when the
  interrupt-nesting byte is non-zero (`0x60030691`). The consolidated
  installer would take its failure path on every key press: it clears S+6 and
  sets S+17=2, and it never redirects the buttons.
- **Effect.** The camera would stay stock. That is safe, but the feature would
  never switch on.
- **Why the emulator missed it.** The Ghidra harness ran the hook with the
  nesting byte at 0, so `consolidated-installer5`'s success does not carry over
  to the camera.
- **What is not affected.** The redirect itself (plain stores, no OS calls) is
  safe in interrupt context.

**Fix direction (implemented locally; verification below).**
- **Installer.** Keep only the redirect in the interrupt hook.
- **Mutex.** Create the mutex in **task context** on first use, from the
  wrapper path (GUI task 165, core 0), with the same failure rule: on failure,
  pass through to stock and leave the feature off.
- **Space.** Removing the create sequence from the installer frees room in
  the section-1 gap for a shared "ensure mutex" routine.
- **Harness.** It must run the hook with the nesting byte set, and add a
  control showing that a create from the interrupt fails.

## Equipment and log template (10 November)

The written log template for stages 1 and 2 (plan item 4) is
[HARDWARE-STAGE1-2-LOG.md](HARDWARE-STAGE1-2-LOG.md). It covers the session
header, hash check of the file on the card, baseline settings, the SD re-flash
steps with expected lamp states and stop conditions, the official routes, the
post-flash checks and the stage-2 stock observations. The equipment itself
(batteries, cards, cable) is the owner's to prepare and record in it.

## Status

Items 2 and 3 are done offline. Item 1 needs the owner. In item 4:
- runtime loading is established;
- owned data RAM is largely established;
- placement is partly established;
- alignment is statically clean;
- the compressed-section-7 problem is resolved by the runtime redirect;
- boot-time code is removed by the consolidated first-use installer (both
  prototyped, 28/28);
- the live layout is re-audited (`live-access-audit2`):
  - every feature-state access goes through the uncached alias, so Finding 1
    is closed;
  - the installer's section-7 field stores (Finding 1b) are closed offline:
    the hook (IRQ 320 handler) and the GUI engine (task 165) both run on core 0;
  - **Finding 5 repaired and re-proved offline:** the IRQ installer performs
    no OS creation; the task wrapper creates the mutex once. The revised
    engine-routed matrix passes 28/28 (`task-context-mutex2`). Native context
    rejection is independently exercised in `native-mutex-context1`;
  - the live layout uses the section-4 tail up to `0x60a8f7d5`, leaving
    43 B (not 132 B, which applied to the older variant);
- the proposed full-feature diff is recorded (`task-context-placement1`):
  - wrappers at `0x6031eb80`, `0x6031ec99`, `0x6031edb2`, `0x6031eecb`;
  - task ENSURE at `0x6031ead0`; IRQ installer at `0x6031eb12`;
  - table at `0x607187d0`; hook at `0x6017a5fc`;
  - accessor and entry patches; every changed byte is listed;
  - stage-specific packaging/checksum changes and image verification remain.

These must close before stage 4 or later images. Stages 1–3 need no new code.
Stages 1 to 3 use no new code and depend only on item 1 and the recovery
procedure above.

## Resumption audit and task-context repair (9 November)

The current files and PR #19 were checked, including the installer, alias audit,
hook/core observations and unfinished `OM3TaskContextMutexProof`. The checkout
and remote PR both name `3e6edfb82c9cf28d5a182934d7ccd199d5a8e50a`. The installer
and hardware-plan work is newer local research. The earlier AF-startup frontier
is superseded by the native LOCK_START acknowledgement and engine-routed 28/28
results. The single-start/display-completion limitation remains.

**Why `task-context-mutex1` stopped (0/28).** Its c3 failure-injection control
entered the inherited GUI-engine router, which created an unrelated framework
mutex before the wrapper. That consumed the injected failure and reached the
stock diagnostic path (`0x97f00004`). It did not test the intended first-wrapper
failure. The counter also included unrelated startup creates. Its original
source hierarchy is preserved under that run's `source-snapshot/`.

**Repair.** c3 now calls the wrapper directly with the original body modeled;
GUI routing is disabled only for this ABI control, then restored. The ordinary
matrix retains the stock engine and original native handlers. Successful creates
are counted only inside ENSURE. Failure-injection state is restored after c3.

**Isolated result:** `task-context-mutex-probe3/mutex-probe-outcome.txt` passes:
- old interrupt installer refused with modeled E_CTX;
- revised installer defers before section 7, rejects a foreign field without
  partial writes, and installs all four redirects without an OS call;
- first-wrapper create failure calls the original ABI boundary once and disables
  the feature without creating a mutex;
- task-context ENSURE creates once and reuses the mutex on a second call;
- callee-saved registers and root stack survive both ENSURE paths;
- installed interrupt fast path makes no create attempt.

ENSURE is **66 B** at `0x6031ead0`; the interrupt installer is **105 B** at
`0x6031eb12`: **171/176 B**, leaving **5 B**. Wrapper starts are now
`0x6031eb80`, `0x6031ec99`, `0x6031edb2`, `0x6031eecb`, superseding the older
layout. ENSURE uses the save frame established by `call ...,[d2,d3,a2,a3],0x14`;
it must not push that register list again.

OS creation and the interrupt-context refusal remain explicit models. This is
not a native kernel-allocation or physical IRQ test. Probe1/2 are debugging runs,
not acceptance evidence; probe2 included a temporary extra push removed after
tracing its stack imbalance. Probe3 archives its actual source hierarchy,
processor semantics, hook observations and outputs with SHA-256 hashes.

The full revised matrix and native-loader/diff results are recorded below.
No installable image is emitted and no camera is accessed.

**Packaged evidence correction.** The contribution's `--check-recorded` initially
failed because historical source hashes were compared with three later-refactored
files. All 69 original sources were recovered from `a00f1be` and checked against
the original manifest before archiving in `recorded-evidence/live-source-snapshot/`.
The corrected checker independently verifies imported current files and the
historical snapshot. It passes and explicitly states that historical results do
not establish results for revised scripts. Changes remain local; nothing pushed.

### Completed verification

**Full consumer run: `task-context-mutex2`.** All **28/28** profile edges pass
through the stock engine, the revised wrappers and original native handlers
across SCP Off and all six detection classes. The old-installer control produces
one modeled E_CTX refusal; the feature then creates **one** task-context mutex,
ending enabled with status 1 and installed marker 1. The live access audit reports
no undefined opcode, misaligned resolved access, cached feature-state access or
write into code. Its 42 unresolved register-relative bases and 137 stack accesses
remain static-audit limitations; the earlier manual analysis is not a complete
new runtime address checker. The three non-function-start targets are the
previously documented displaced-instruction resumes and stock conversion entry.

The AF consumer reads the uncached owned AF-ON record with subject detection 0.
As before, only the first AF-ON press submits LOCK_START; later presses are
refused while the display-change fixture awaits completion. The AF worker also
parks on flag 67 bit 1; no producer or acquisition result is invented. Thus 28/28
is a profile/handler result, not 28 successful AF acquisitions.

**Native context refusal: `native-mutex-context1`.** Stock `0x60030659` itself
returns `0xffffffe7` (-25) both for supplied nesting bytes {1,0} and context bytes
{0,1}, with a valid attribute-2 packet. No create call is intercepted and no
allocation result is supplied. Core ID 0, kernel-control-block pointer and context
bytes are explicit unit fixtures. Both root calls restore their stacks. Successful
native kernel allocation and the physical IRQ context remain untested.

**Native loading and exact proposal: `task-context-placement1`.** The new helper,
installer, descriptor table and hook are included in an in-memory component
before loading. Native section loads 1, 2 and 4 replace poisoned whole sections;
every loaded byte equals that proposal. No mutex exists after those loads. The
IRQ hook first defers, then installs all four redirects after the explicitly
supplied section-7-ready bit. Task ENSURE creates once and reuses the mutex.
The compressed section-7 loader is not exercised by this fixture.

`proposed-changed-bytes.csv` contains **3,612 distinct changed-byte rows**, with
component offset, runtime address, old byte, proposed byte and purpose. Every
change lies in uncompressed sections 1/2/4; placement spans are disjoint; section
7 is stock-identical. The 66+105-byte helper/installer fits its 176-byte gap.
The in-memory decoded proposal hashes to
`4a988c57d1a15d2465292a296bfd60dd690cc0c76dd60ae8165848f847c5b325`.
This describes the tested scenario's initial state; it is not a finalized
production configuration, repaired-checksum component, outer container or
flashable file. No image was emitted. The loader fixture uses the declared
storage/cache alias models; it does not prove physical cache or DMA behavior.

All three runs and the isolated probe have `task-context-evidence-manifest.json`
files freezing the actual source hierarchy, processor semantics, hook observations
and outputs. `scripts/record_task_context_evidence.py` verifies those hashes.

### Next work after this repair

1. Resolve the display/eye-sensor/output fixture from stock state so repeated
   AF-ON presses can be investigated without fabricating a completion. Keep
   physical acquisition separate from profile/handler success.
2. Add the runtime address/alignment checker for the revised layout's unresolved
   bases and stack accesses; exercise interrupt arrival during task-side work.
3. Continue the static secondary-CPU/DMA ownership review for the reserved tails.
   Loader identity and absence of observed writes do not prove exclusive ownership.
4. Before any owner-authorized stage image, select that stage's exact code and
   initial-state configuration, regenerate its diff including checksum changes,
   and verify packaging separately. The proposed full-feature diff is not a
   substitute for those stage-specific records.
5. Physical update/recovery decisions and observations remain with the owner.
   Every complete acceptance gate remains open; readiness stays **NO-GO**.
