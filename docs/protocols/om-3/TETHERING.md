# OM-3 USB tethering

kred's V22 patch adds USB live view and captured-image transfer to **OM-3 1.1
(E147/1100)** using OM-1 Mark II 1.3 as a donor. It combines native OM-3 services,
adapted donor code and replacement wrappers. It is more than a capability flag.

Source: [kred, mu-43.com, October 20, 2026](https://www.mu-43.com/threads/modified-firmware-looking-for-users.99804/page-34#post-1886195).
The author's hardware reports are separate from the independent byte checks and
bounded native execution below. Attachment identity and date provenance are in
[community reports](../../../provenance/community-reports.json).

## Why USB startup matters

Application mode, connect kind, stored API selector and transport number are
different values. A menu label does not determine all four.

| Selection | Application | Connect kind | Selected API | Transport |
| --- | ---: | ---: | ---: | ---: |
| Stock RAW startup | 10 | 7 | 10 | 11 |
| Native Control startup, before transport remap | 12 | 8 | 11 | 12 |
| V22 RAW entry, routed through Control | 12 | 8 | 11 | 11 |

V22 changes popup RAW index3 from action26 to action27. The application dispatcher
maps those actions to modes10 and12. The saved USB setting follows a separate
path: setting82 value10 is remapped from application10 to12.

PC control is enabled through property **`0xD052`**. In V22, transport11 selects
event `0x041B0084`, whose native predicate requires API11 and query status0.
The other enable route, `0x041B0022`, requires API10 and status0 for enable
input1. Selecting the right transport number while retaining the wrong API
therefore leaves the session unable to start.

The independent probe executes these mappings and predicates in **58 bounded
stock/V22 cases**. It confirms the mismatch explanation without forcing either
predicate to return success. It does not replay the complete application
transition, API installation, event queue or USB acknowledgement wait.

## Protocol pieces restored

PTP codes below are hexadecimal. V22 advertises 48 operations, 12 events and
299 properties. Its property registration uses 291 existing descriptor pointers
plus one additional descriptor; registration and advertised-ID counts differ.

| Function | Protocol and implementation |
| --- | --- |
| Capture | `9481`; the added 277-byte handler matches the OM-1 II routine except for four call operands. |
| Preview | `9484`; a JPEG wrapper reads a three-entry descriptor ring, checks buffers/length/SOI and uses the native sender. Its registration specifies data phase1. |
| Preview size | `D06D`; kred reports activation with packed value `050003C0` (1280×960). The native descriptor and setter are present. |
| Property access | `9489/948B` subscriptions and `9486/948A` grouped getters, alongside property-change and session-end notifications. |
| Image transfer | `9493/9494/9495` direct-store operations and `C104` notification. kred reports this made PC transfer work; restoring `C102` alone did not. |
| Autofocus completion | Restored `C103/C111` notifications. The report does not establish correct behavior for every AF mode. |

A successful response code does not establish a completed data transfer. The
author reports an earlier preview attempt returned success with zero image
bytes until its registration phase was fixed. The available V22 bytes support
the final phase setting; the earlier trace was not supplied.

The preview wrapper and ring reader also pass **19 bounded native checks**.
They accept all three allowed buffers and lengths from 2 through 153,600 bytes,
and reject disabled preview, invalid descriptor status, short/oversized data,
unknown buffer addresses and a missing JPEG SOI. Stack and saved registers are
restored on every tested path. This checks the header, not the JPEG's contents.

The reader copies a 40-byte descriptor and rotates its three-entry ring under
the mutex, then releases it before validation and sending. These changes happen
even when later validation rejects the frame. No concurrent producer is modeled,
so this does not prove ownership of the buffer throughout transmission.

After calling the native sender, V22 unconditionally returns PTP success
`2001`. Supplying a modeled sender result of `-1` still produces that response.
This confirms that the wrapper does not inspect the return value; it does not
establish the real sender's error convention or explain every failed transfer.

## Useful addresses and corrections

Runtime addresses use main base `60021020` for this exact build.

| Function or data | Address |
| --- | --- |
| Popup index dispatch | `612BDE8B` |
| Action/application hashed dispatch table | `61305954`, consumed in `6109AF44` |
| Application/connect-kind selector | `6108E36D` |
| Connect-kind/API selector | **Function `60B0630D`, jump table `60E0A9DC`** |
| API/transport table | `60621988`; edited result operand at `60409089` |
| API/status query | `60409387`; byte at `62A884EE`, halfword at `6035FBEC` |
| API11/API10 enable predicates | `60C1C42F` / `60C18D67` |
| D052 event selection | `618C3118` |
| Preview ring / ready flag / mutex identifier | `A320FD28` / `A320FDA0` / `600435E6` |

The report's two connect/API addresses are complementary: one is the function,
the other its jump table. They are not conflicting locations.

The persistent-mode instruction starts at `6108E2FD`: `80 0A` becomes `80 0C`.
The changed byte is at **`6108E2FE`**, or **decoded-container offset `0106D2FE`**.
Offset `0106D2FD` identifies the instruction start, not the changed byte.

“35 guarded components” in the source means **35 guarded edits**. All change
one firmware component, main `0100`, with 3,555 changed decoded payload bytes.
The three injected regions are covered by the [code-placement analysis](../../safety/CODE_SPACE.md).

## Evidence limits and reproduction

Use [om3_tethering_probe.py](../../../tools/om3_tethering_probe.py) with decoded
stock/V22 main payloads and the [MN103 runner](../../tooling/EMULATOR.md):

```sh
python3 tools/om3_tethering_probe.py \
  --stock-main /path/to/om3-1100-main.bin \
  --patched-main /path/to/om3-v22-main.bin \
  --out generated/om3-tethering.json
```

The probe checks exact input hashes. It supplies synthetic stack and API/status
RAM, suppresses two trace-output services, and models the transport setup call
as successful. Other code slices stop before external services. It needs no
PEN-F firmware and makes no camera connection.

The separate [preview probe](../../../tools/om3_preview_probe.py) executes the
wrapper and reader together:

```sh
python3 tools/om3_preview_probe.py \
  --patched-main /path/to/om3-v22-main.bin \
  --out generated/om3-preview.json
```

It models the mutex services, descriptor copy and sender. The ring has exactly
one selected descriptor and at least one free descriptor. Producer scheduling,
DMA and actual USB traffic remain outside the test.

kred reports working popup and saved-RAW live view and captured-image transfer.
Combined USB RAW development, complete AF behavior and the live callback/observer
chain remain unvalidated. The report's early alignment/copy failures lack the
failed images and fault traces needed for independent reproduction.

The known section loader is in main firmware; its copy bounds do not identify
an immutable reset bootloader. The earlier recovery report still lacks exact
failure symptoms and recovery steps. These findings do not establish PEN-F
recovery or make arbitrary FF-filled memory safe to use.
