# OM-5 Mark II E148 firmware 1.1: HSL/WB brick-risk review

## 4 November 2026 camera incident — do not flash

**Do not flash `codex/om5ii-hsl` build `1bd6276` or its generated install
package (SHA-256 `35f0caac4b70f1e59e3d5311fdf74a8c021d720755a7441796b080707b79d434`).**
The owner reports that the update appeared to run, but the camera then showed
a black screen and repeatedly moved autofocus instead of booting. An attempted
stock-firmware reflash showed a sustained solid red light. The owner reports
that a second stock-firmware reflash attempt recovered the camera. This is one
observed recovery, not proof that other boot failures can be recovered. The
root cause has not been established. The static and emulator results
below did not predict this physical boot failure and must not be read as
evidence that this build is safe to install. The analysis below predates this
incident.

3 November 2026. Scope: `codex/om5ii-hsl` at `d80077e` and its stock E148 build 1100 input. This was a static and OM-Emu review before the camera incident above. At that time no package had been installed on an OM-5 Mark II. The install image is withheld by the builder by default. Addresses below are main-CPU runtime addresses. The [brick-risk handoff](HANDOFF-2026-11-03-brickrisk.md) records the disassembly, probes and scripts behind the findings.

## Decision

**Revised decision: do not use Probe B as a prerequisite or a safety check.** It changes a compressed section needed to run the card updater, so a failure could remove the proposed recovery route. A successful Probe B would show that one repacked stream booted, but would not establish that the full mod boots or that a failed section-7 load can be recovered. A stock same-version reflash on a working camera can check the OK+power entry; Probe A is an optional modified-image acceptance check. Neither proves recovery after a bad boot. Flashing the full mod remains a separate, high-risk camera experiment with untested off-CPU LZ4 decoding, boot with saved Color Profile settings, and capture behavior. No independent boot-level rescue has been demonstrated.

## Risk register

| Item | Evidence and verdict | Residual risk |
| --- | --- | --- |
| Recovery route and components | The official BIN contains `0x100` USR, `0x101` OSD, `0x106` RESCOM, `0x10e` LUKE, `0x102` PIC; kind dispatch is `0x60ce6aa5`. There is no BOOT (`0x10`) or SCPU (`7`) component, so this E-file does not rewrite the boot loader. FIRMUP_CLI `0x60ce5ce5` is in LZ4 section 7 and is started on every boot by task 92 `0x6081e273` after section 6; task 92 comes from base boot `0x6004628d`. **Conditional recovery route exists.** | The E148 OK+power activation is untraced. Field reports for other OM models do not prove it here. Recovery needs base and sections 1–7 to load and task 92 to run. |
| Package composition | The patch ships only `0x100` and `0x101`; updater kind bits are accumulated and validated per present block. `USER_NASHI` applies if USR is missing. Partial main packages have worked on PEN-F/E-P7; E148 support is established by code. **Acceptable by design.** | Physical E148 partial-package write and readback are untested. |
| Same-version restore | No version gate was found in E148 FIRMUP_CLI; `E1489999.BIN` is a card filename selector, while internal build remains `0x1100`. The stock restore subset matches stock byte for byte. **Expected to accept same-version stock.** | No E148 camera has demonstrated the OK trigger or same-version reflash. Use the complete official BIN for restoration. |
| Updater acceptance | The new 37,486,592-byte package keeps stock headers, trailer first 28 bytes and component lengths; each block's additive 32-bit sum is zero. Expanded base, updater `0x60ce5b00–0x60ce7c00` and task 92 are byte-identical to stock. Validator `0x60ce5b7d` checks the additive sum, `0x601102ad` compares header/trailer, and the updater has no observed cryptographic or version check. **Static acceptance checks pass.** | Flash backend, physical card path and power-loss behaviour remain camera-only. |
| LZ4 decoder | The former repack made 93,524- and 650,410-byte literal runs in sections 6/7. Opt-in `"repack": "split"` now caps the longest runs at 3,565/2,197 bytes, equal to stock; final five literals and match margin also match stock. Expanded main hash remains `0663660d…173d`, stored `0x100` hash was `f6d83c23…e114` at this review's source commit. **Known long-literal hazard fixed.** | Loader `0x6005b249` sends work via mailbox `0x8ff00b80`; the other CPU/hardware decoder is unavailable for inspection. A section-7 decode failure could prevent the updater from running. Probe B is not a safe prerequisite. |
| Boot path, guards and load order | Loader caller `0x60045a38` loads sections **1, 8, 2, 3, 4, 5, 6, 7, 9, 10** once each. Cross-section audit found no unguarded forward reference. The section-2 WB wrapper checks section-6 bit `0x20`; refresh checks section-8 bit `0x80`. Forced-guard OM-Emu boot and long UI/capture/playback flows had no fault. **Static and emulator path pass.** | OM-Emu HLEs boot and does not run E148's loader. It cannot establish a real boot with saved Color Profile settings. |
| Section-RAM stores | Stock E148 itself writes GUI data at `0x61110d0c` and `0x61111114` in section 7 during use. Sections load once. Patch state is `0x60ca7fc0`, busy `0x60ca7ff8` (uncached alias), refresh byte `0x605af575`, and ext8 dirty/reset state. **Section RAM is writable; no reload was found.** | Cross-core cache coherence for cached state and any unobserved writer remain unproven. |
| Frequent paths, recursion and stack | In a 10-second OM-Emu idle live view none of 15 hook sites fired; S1/S2 hit commit/read/write once each. Trigger IDs for `wb_profile` and IDs written by refresh and stock `pm_refresh` are disjoint, bounding refresh recursion at one. Four UI writes gave 83 commit entries and two refreshes. Commit SP was 356 bytes below idle; nearby task stacks were about 16 KB apart; paint frame is 80 bytes. **No runaway or per-frame hook observed.** | Real COLOR builder frequency and task stack margins are camera-only; builder does 12 reads and no stores. |
| Freed data | Full-image dword scan at any alignment found no remaining readers of freed record copies except repointed descriptors/new tables. Old availability table has no reader after `0x602ddb89` is repointed. Old carousel is still read by fallback `0x60e2d6a0` with its own stock count 41. **No dangling reader identified.** | Indirect reads not identified by the scan are a static-analysis limit. |
| Downgrade settings | Stock setters refuse out-of-range values; the mod stores CP1–3 as indices 41–43. With injected index 41 and representative part-1/effective values, stock getter returned last value 63. Stock image UI, ctx0/ctx1 refresh, capture, SCP, menu and playback ran without fault in OM-Emu. **Emulated downgrade works for tested values.** | A real NAND boot, ctx1 raw cells and custom-mode bank permutations are not fully tested. Before restoring stock on a working modded camera, set a stock picture mode in every C-mode or run Reset → Full. |
| Resource `0x101` | Only record 0 changes: 42 pointer-table dwords alias real stock images `0x190d`/`0x2bb6`. HC repack uses 764,666 of 764,928 bytes, with 230 bytes spare; longest literal and stream margins match stock. All other records are identical. **Bounded resource edit passes.** | Real camera artwork/GPU rendering remains untested. |
| Multicore cache and refresh concurrency | Main patch state/busy use uncached aliases. `refresh_profile` is one cached global byte noted by the case hook and read by refresh tail. **No crash mechanism established in reviewed flow.** | Cache coherence across cores is unproven. Two concurrent refreshes may overwrite that byte and apply the wrong profile's values; the expected failure is wrong values, not a demonstrated crash. |

### Hook and edit map

“Boot?” means the hook can execute before the shooting screen, based on the forced-guard emulator boot; other calls during real boot remain uncertain. Section numbers identify the **site**; extensions can live in a different section. Loaded-bit checks are the section-6 and section-8 guards above. Normal UI and pipeline triggers also require their stock callers to run.

| Site / edit | Section | Trigger | Boot? | Guard / state stores |
| --- | --- | --- | --- | --- |
| `0x602d19b6` WB commit | 2 | Setting commit | Yes, stock path observed | Section 6 loaded; busy at `0x60ca7ff8`; WB part-1 cells; may call profile refresh |
| `0x602e0826` refresh tail | 2 → 8 | Picture-mode refresh | Not observed | Section 8 loaded; `refresh_profile`, `refresh_dirty`; effective setting IDs |
| `0x604997f0` cases 54–56 | 2 | Refresh jump table | Not observed | Mode 54–56; `refresh_profile` at `0x605af575` |
| `0x602db531` custom reset | 2 → 8 | Reset another C-mode | No | Section 6 loaded; reset mode differs from current; scratch at `0xa0ca7e70–0xa0ca7fa0` (section 6 tail); restored part-1 cells |
| `0x602e0f82`, `0x602e1119`, `0x602e0fe8`, `0x602e11fc` mode-store copies | 2 → 8 | Mode change, custom-mode assign/recall | Possible | None needed (section 8 loads before 2); for ID 111 only, copies setting 903 between working copy and the same row |
| `0x6091c66d` read | 4 | Editor setting read | Yes, stock path observed | COLOR/H/L ID checks; no persistent store |
| `0x6091c6bd` write | 4 | Editor setting write | Yes, stock path observed | COLOR/H/L ID checks; part-1 H/L cell writes |
| `0x603e7eb0` builder | 2 → 8 | Capture record major `0xb` | No | COLOR record; reads 12 H/L cells, writes builder output records |
| `0x60a33eac` display | 5 | Wheel value request | No | COLOR/axis checks; writes caller's display buffer |
| `0x60e4ade9` label | 7 | Wheel value label | No | COLOR/axis checks; returns label value |
| `0x60e9e0f4` reset | 7 | Editor reset | No | Editor/axis checks; H/L cells via stock UI write |
| `0x60ea0180` parent | 7 | Editor child update | No | Editor pointer present; view state |
| `0x60dad5f5` pages | 7 | Direct-screen visibility update | No | COLOR and focused-item flags; view visibility/geometry |
| `0x61234464` Delete pointer | 7 | Delete in editor | No | Editor/axis checks; axis state and stock UI writes |
| `0x611a0c54` container pointer | 7 | Editor container call | No | Editor pointer; axis/view state |
| `0x610c1540` paint pointer | 7 | Visible wheel page paint | No | View/axis checks; saves/restores context +52/+76 |
| Data: `0x602ddb89/9b`, `0x604eec40`, `0x604997f0` | 2 | Availability lookup / refresh | Table read can occur at boot | Static pointer/count and case table; no runtime code store except case byte above |
| Data: `0x60472666`, `0x604729da/fc`, `0x6047c348–0x6047c590`, `0x604eeae0`, `0x604f1160–0x604f2130`, `0x6050de48/e050/e064` | 2 | Picture-mode descriptor/rule lookup | Possible | Static tables and pointers; runtime settings changed through stock setters |
| Data: `0x61199b5c`, `0x611a1a00/08` | 7 | Carousel / label lookup | No observed boot call | Static table/count edits |
| Extensions/state: `0x605af4b0`, `0x605af560`, `0x605af5cc`, `0x60ca7b00`, `0x60ca7fc0`, `0x612a4b98`, `0x613f2b80`, `0x613f2f40` | 2, 6, 7, 8 | Entered only from sites above | As their caller permits | Section guards as above; section-6 state uses uncached alias; ext8 refresh/reset state |
| Resource record 0 pointer aliases | `0x101` OSD | Artwork lookup | Possible | 42 static dwords; no runtime store |

## Staged camera checks

These are proposed checks, not proof that a failed boot is recoverable. None has been performed on E148. Stop on any failure.

1. **Stock same-version reflash.** Put the official `OLY_E_148_1100_0000_0000.BIN` at `DCOLYMP/E1489999.BIN` on a card in slot 1. With the camera off, hold OK and power on; release OK when the orange lamp is solid. The screen stays blank. Solid then blinking means success; fast blinking without a solid phase means rejection; a normal boot means the trigger was missed. Confirm a clean reboot. This establishes the E148 trigger and same-version route.
2. **Optional Probe A, then stock again.** Build `patches/hsl/om-5-ii-probe-a` with `--write-untested-package` outside the repo. It changes three inert bytes in section-2 padding and does not change LZ4. The LED sequence and clean reboot check acceptance of a modified image. This is an extra flash and does not establish recovery from a bad boot.
3. **Full mod only as a conscious high-risk experiment.** Probe B is not required or recommended. If proceeding, build `patches/hsl/om-5-ii` outside the repo after reviewing its current manifest and functional-assurance report. Check boot, SCP, CP1–3, capture, playback and power cycles. Before restoring stock, set a stock picture mode in every C-mode or run Reset → Full; then use the official stock BIN.

Probe B remains a research artifact. Although it changes only inert padding after decompression, it repacks sections 6 and 7, and section 7 contains FIRMUP_CLI. A failed section-7 load could prevent the updater from running. If a flash leaves the camera dead, removing the battery and trying OK+power with the full official stock file is unproven for an E148 that fails before the updater; service may be required.

## Reproduction and limits

Default build: `python3 tools/oly_patch.py patches/hsl/om-5-ii --stock <official BIN> --out <new directory> --decoded`. It withholds the install image. Stock SHA-256 is `9de5d77e1d290fa2ed4ebc7d75cee0ed490befbc89566722467d1d421d66d637`. The split package SHA-256 is recorded in `patch.json`; its decoded main remains `0663660dbcdca6e3e46ce0eaa4a64d17f9c6c5d788a97f5d9a6a638bc641173d`.

OM-Emu requires the E148 loaded bits to be set after boot because it does not execute that loader. Its no-fault results test the patched runtime paths, but do not prove E148 boot, flash acceptance, decoder behaviour or image quality on a camera.
