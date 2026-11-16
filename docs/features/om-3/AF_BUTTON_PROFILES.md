# OM-3 autofocus button profiles

Research for **OM-3 E147, version 1.1, main build 1100**. The current design
would let half press keep the normal AF target and give AF-ON a separate zone,
size and position configured from the per-button AF page. Both would keep the
shared S-AF/C-AF setting. AF Home stays independent. This design has no
working menu or persistent profile implementation and is not a firmware patch
for installation.

## Inputs and static reproduction

Obtain the exact stock container separately and decode it with
[oly_container.py](../../../tools/oly_container.py). The
[firmware inventory](../../../provenance/firmware-inventory.json) lists the other
components. Run from the repository root; use a new local output directory.

| Input | Bytes | SHA-256 |
| --- | ---: | --- |
| `OLY_E_147_1100_0000_0000.BIN`, model bytes `1470` | 240,517,120 | `8c133084414533159f587bf46bfb4152714c4074312a47c8d8503e33d605696d` |
| Decoded main `0100`, build `1100` | 33,554,368 | `5e8d376e9111a44ac0352f26030d7c1b17026d42c45f3600cfa02a0e8c5b7d59` |
| Decoded resource `0106`, build `0100` | 143,523,776 | `3d9fd4426b45fbe4b715599422af38c6d22392c08543a69f63c28291c5a0b059` |

```sh
python tools/oly_container.py /path/to/OLY_E_147_1100_0000_0000.BIN --out /path/to/decoded
python tools/om3_af_probe.py /path/to/decoded/00_0100_50000020.decoded.bin
OM3_MAIN=/path/to/decoded/00_0100_50000020.decoded.bin python -m unittest tests/test_om3_af_probe.py
```

The unit tests check envelope decoding and input pinning without firmware.
With `OM3_MAIN` set, they also assert the page-27/28 rows and queue-95 AF
handlers listed below for this exact image.

Main addresses below use the CPU mapping `0x60021020 + decoded offset` for
this image. They are distinct from logical flash and container addresses.
For code observations, import decoded main at that base with the pinned
MN10300 language in the [archived setup](https://github.com/tsmkirby/oly_fw_analysis/blob/04df764a6a2c4c3eb0882ba67241bb91246f3721/research/om3_af_profiles/README.md#reproduce-native-execution).
Disassemble from the listed function entries and follow branch and call
targets; the Python probe reads data and does not emulate instructions.

## Menu and settings

- **Observed in stock data:** Multi-row page 27 points to two 36-byte rows at
  `0x6158dc44`, UI IDs 2154 and 2155, each with values 1 and 0. They map to
  `MODE_AF_SUBJECT_PRIORITY_RELEASE` and `MODE_AF_SUBJECT_PRIORITY_CUSTOM_SW`,
  key `0x90a1`, indices 0 and 1. Page 28 has AF Home area lists; page 29 has
  AF Home rows without inline choices. The probe prints the row IDs, labels,
  option values and all four UI-ID maps' coverage for the selected AF keys.
- **Observed in code:** Viewer constructor `0x61203696` looks up a page
  descriptor; `0x61203a81` matches setting IDs to its rows. The viewer also
  reads a runtime list model, so adding to the descriptor alone is not known
  to make a row appear. AEL/AFL operation settings use a different viewer.
- **Unproven:** Page 27 is the proposed home for the new AF-ON zone row. Names
  suggest stock per-button Subject Detect behavior, but its behavior for AF-ON
  and the setting values' meanings are unconfirmed. The selected AF target
  arrays have a UI mapping for every allocated cell. Neither that scan nor the
  absence of a UI ID proves spare storage. Editor routing, persistent storage
  ownership, reset/custom-mode behavior and the active EVF/monitor overlay
  remain open.

Normal area UI enum `0x99a1` is distinct from internal area kind `0x84d1`.
Stock type conversion `0x609b3ecd` and target building `0x609b3c79` are
reuse candidates. SCP Subject Detect uses `0x1e71[0]`; focus mode is
`0xc021`. These are separate from target data.

## Button dispatch and bounded execution

The stock handlers are `0x610b9197` (half press), `0x610b96f0` (half
release), `0x610b962a` (AF-ON press) and `0x610b9653` (AF-ON release).
Queue 95 has 93 dispatch slots starting at `0x6031e224`. Commands
`0x2a/0x2b/0x2c` map to `0x603c86d7/0x603c8af3/0x603c8d14`; start/end
payload flags are separate from the 16-byte envelope. The common 12-byte reply
contains a low-halfword status plus correlation and pointer words. To check
the format, run the same probe with this **synthetic** envelope and payload:

```sh
python tools/om3_af_probe.py /path/to/decoded/00_0100_50000020.decoded.bin --request 06000000000000002a00000000100070 --payload 0500000004000000 --reply 000000000000000000100070
```

Expect command `0x2a`, handler `0x603c86d7`, kind 5 and flags `0x4`.
A reply status or start acknowledgement alone is not a focus result.

**Emulator observation (earlier AF Home prototype):** The engine-routed
press/release matrix passed 28/28 profile checks across seven SCP values.
AF-ON took precedence while both buttons were held, used the AF Home target
and suppressed detection; release restored the half-press profile. Only the
first AF-ON press submitted LOCK_START and reached its native acknowledgement.
Later starts were blocked after a display-output transition; its completion
was not supplied. This uses stock-reset and shooting-context fixtures, a
silent SCPU, supplied startup inputs and modeled OS/device services. It says
nothing about the new menu, storage, physical focusing or update safety.

To repeat the archived matrix, use the [pinned research checkout](https://github.com/tsmkirby/oly_fw_analysis/tree/04df764a6a2c4c3eb0882ba67241bb91246f3721/research/om3_af_profiles),
its Ghidra setup and [MN10300 carry correction](https://github.com/tsmkirby/oly_fw_analysis/blob/04df764a6a2c4c3eb0882ba67241bb91246f3721/research/om3_af_profiles/recorded-evidence/review/carry-fix/README.md).
From that checkout's research directory, generate the local assembly
export as described in `DECOMPILATION.md` (used by the access audit), set
`JAVA_HOME`, create a fresh output directory, and run:

```sh
analyzeHeadless /path/to/projects OM3_main_full -process 00_0100_50000020.decoded.bin -noanalysis -readOnly -scriptPath scripts -postScript OM3TaskContextMutexProof.java /path/to/output
```

Compare `original-button-matrix.txt`, `af-consumer-evidence.txt` and
`task-context-mutex-summary.txt` with the [recorded run and source hashes](https://github.com/tsmkirby/oly_fw_analysis/tree/04df764a6a2c4c3eb0882ba67241bb91246f3721/research/om3_af_profiles/recorded-evidence/task-context-mutex2).
The expected result includes exactly one feature mutex create in task context
(modeled) and one LOCK_START submission. No AF or device completion was
injected. Headless exit status alone is not a pass.

**Live OM-Emu observation (2026-11-16):** A separate player-driven test on
E147 1.1, OM-Emu commit `4e4ec4ef084542a7e30eecce56970c7e09c123c9` plus
archived local changes, passes 12 button-handoff edges in each of S-AF and
C-AF with Subject Detect Off. Native AF initialization and a central
application-task hook restore the expected target records for both release
orders. Native enum conversion fixes the earlier C-AF setup error (raw value
1 was MF). This remains the AF Home prototype, without a separate editor.

Full live acceptance is **0/14**: neither Off case demonstrates the complete
queue-95/queue-94 AF worker chain, and all 12 nonzero-SCP cases stop before
completing their first measured edge. Native callback `0x608418fe` returns
but posts an unserved CPU3 event-flag request. Disassembly identifies flag
`0x3003` at `0x6004367a`, receiving task `0x60841a6b`, and a subsequent loader
at `0x60842bde` waiting on flag `0x3004`. Callback return is not proof of
Subject Detect completion. Porting and validating E147's CPU3 task/flag
service and native TAKE boot prerequisites remain necessary.

The [reproduction bundle](https://github.com/tsmkirby/oly_fw_analysis/tree/a2b6d446783f85af67a1582618014d9ffdd5b1fc/research/om3_af_profiles/analysis/button-af/readiness/om-emu-af-native1/reproduction)
contains exact-build requirements, tested sources, emulator patch, hashes and
commands. The [14-case report](https://github.com/tsmkirby/oly_fw_analysis/blob/a2b6d446783f85af67a1582618014d9ffdd5b1fc/research/om3_af_profiles/analysis/button-af/readiness/om-emu-af-native1/matrix-cpu3-final/report.json)
separates handoff from full acceptance. These live results do not extend the
earlier fixture-based 28/28 result to physical focusing or update safety.
The new section-7 hook has no packaging/placement proof; no flashable image
is supplied.

Detailed [menu/storage notes](https://github.com/tsmkirby/oly_fw_analysis/blob/a2b6d446783f85af67a1582618014d9ffdd5b1fc/research/om3_af_profiles/analysis/button-af/AFON-MENU-RESEARCH.md)
and the historical reports and hardware-planning logs stay in the fork.
