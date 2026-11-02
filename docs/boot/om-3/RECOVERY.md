# OM-3 SD update client

Model OM-3, displayed firmware 1.1, internal build 1100. Update file SHA-256
`8c133084414533159f587bf46bfb4152714c4074312a47c8d8503e33d605696d`; decoded main
SHA-256 `5e8d376e9111a44ac0352f26030d7c1b17026d42c45f3600cfa02a0e8c5b7d59`.
Runtime addresses. Evidence: static disassembly only. No physical OM-3 update,
OK + power entry or recovery has been tested.

## Update file

The 1.1 update file has six `OE` components (see [containers](../../format/CONTAINERS.md)):

| Kind | Container address | Decoded size | Notes |
| --- | --- | ---: | --- |
| `0100` | `50000000` | 33,554,368 | main program; contains the SD client below |
| `0101` | `41ec0000` | 60,817,344 | resources (UTF-16 strings, `@Axxx@` icon escapes) |
| `0106` | `458c0000` | 143,523,776 | |
| `010e` | `00000000` | 262,080 | |
| `0102` | `4e1a0000` | 2,097,088 | |
| `0107` | `08000000` | 262,080 | sub-CPU firmware (`firmup_comp.c`, `ID_TSK_FIRMUP_COMP_EXEC`) |

Replacing the main payload and repairing its additive checksum reproduces a
valid container in memory with the other five components unchanged. That says
nothing about updater acceptance.

## SD client

The main component contains an SD update client equivalent to PEN-F's:

| OM-3 1100 landmark | Role |
| --- | --- |
| `600399ac` | Task descriptor: task `51` (FIRMUP_CLI), entry `6106b87a`, priority 45, stack 2048 |
| `6106b87a` | Client: mounts the card, searches `DCOLYMP`, reads a match, hands it to the update service, then idles |
| `612ea120..612ea1b0` | File patterns `S147`, `E147`, `G147`, `H147`, `W147`, `A147`, `M147`, `V147`, `D147`, `T147`, `I147`, `K147` `????BIN`, and `DATE????BIN` |
| `612ea1ec` | Eleven 20-byte search entries referencing those patterns |
| `60030899` | `act_tsk` (address from OM-Emu's kernel map); the client starts a helper task through id word `60042dc2` |

`E1479999.BIN` in `DCOLYMP` therefore matches the main update pattern, by
analogy with PEN-F's `E1229999.BIN`. The update service strings (`[firmup]`
DeScramble, checksum, per-component write and verify, `SUCCESS_REBOOT`,
`ERROR_REBOOT`, `TYPE_FIRMUP_DATE`) are at `612ea108..612eb000`.

As on PEN-F, no static activation of the client was found. Its id word
(`60042d70` = `51`) has no literal reference, and none of the 29 direct `act_tsk`
call sites loads task 51. The wake-up judgement (boot key word `a32d9c98` from
the sub-CPU wake factor; `API_WUI_*` names) did not lead to it either. The
physical "hold OK while powering on" entry used by service procedures is
presumably selected before or outside the normal main start path.

## What is not established

- How OK + power starts the client, and whether that selection code is outside
  the main component (which would matter if a main write is interrupted).
- Whether the update service rejects a file with the same or an older version,
  or checks `DATE` data.
- Recovery after an interrupted main write. The client is itself part of the
  main component.
