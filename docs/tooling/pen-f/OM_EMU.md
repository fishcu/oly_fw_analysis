# PEN-F UI development with om-emu

The PEN-F port runs build **E122 3101**, displayed version 3.1. Use
[the general om-emu reference](../OM_EMU.md) for its architecture and limits.
The observations here use upstream commit
`d24ff9dd20b98304541494d0199a5e6415eebdba`.

## Inputs and setup

| Input | SHA-256 |
| --- | --- |
| `OLY_E_122_3101_0000_0000.BIN` | `77398610b379f80238117f31a6d5bbf65d608b49ec563666c64d84367e969f2c` |
| Decoded main payload | `a2eb1d1f1afe47cce148e9aae0a04dfb82547d9de9437d342e012341140913f4` |

From a separately obtained om-emu checkout, with Node.js 26+:

```sh
OM_BIN=/path/to/OLY_E_122_3101_0000_0000.BIN node emu/bin/fetch-fw.mjs --model E122
node emu/bin/play.mjs --model E122 --nvram off --no-browser --debug-api
```

Open the localhost URL printed by the player. The first screen may show an
unset-clock warning; half-press the simulated shutter to dismiss it. Node can
also launch a browser automatically if `--no-browser` is omitted. The browser-only
site offers E122 in its model selector and reads the same stock BIN locally.

PEN-F's saved-settings flash posting site is not ported. The model starts blank;
explicitly requesting persistent NVRAM is refused. This does not test the HSL
extension's physical persistence, backup/restore or custom-mode lifecycle.

## Checked behavior

| Check | Result |
| --- | --- |
| Stock `modelcheck.mjs E122 --no-port` | TFT and EVF passed shooting, simulated capture, playback, INFO, menu open/move/close. |
| Display sizes | TFT 720×480; EVF 1024×768. |
| Virtual SD | Native firmware formatted an 8 GiB card as FAT32 and wrote one simulated image, read back independently by the test. |
| Live debugging | Register reads, task listing and named stand-in inspection worked. |
| Browser Worker | Stock BIN loaded locally and native menu rendered in headless Chrome. |
| Released HSL overlay | Both changed components loaded; normal menus and COLOR editor reached; `Value` replaced `Vivid`. |
| Complete COLOR rendering | **Incomplete:** stock wheel/polygon absent; added HSL headings also absent. |
| Overall visual fidelity | **Incomplete:** screenshot review also identified missing menu background graphics. Navigation checks do not establish a faithful reproduction of the camera screen. |

The TFT/EVF smoke test took about 20 seconds and peaked near 747 MiB RSS on one
Linux host. This is an example measurement, not a general performance guarantee.

## Reaching the COLOR editor

The port's generic controls omit two entries already present in PEN-F's UI_IN
table:

| Raw code | Group / byte / bit | Type / active polarity | Native events observed |
| --- | --- | --- | --- |
| `122b` | 1 / 1 / 2 | 2 / 0 | `EV_PRESS_PICFUNCTION_LEFT`, `EV_RELEASE_PICFUNCTION_LEFT` |
| `122c` | 1 / 1 / 3 | 2 / 0 | `EV_PRESS_PICFUNCTION_RIGHT`, `EV_RELEASE_PICFUNCTION_RIGHT` |

The [editor probe](../../../tools/om_emu_penf_editor.mjs) adds only those input
descriptions to the harness. It supplies press/release bits through the existing
input producer. Firmware UI_IN, application handling and GUI transitions then
run; the probe does not fabricate a direct-editor GUI event.

In the blank COLOR1 session, releasing the left input entered
`0x0202 SS_REC/ID_ST_SETVAL`. Main-dial `+1` wrote saturation property 931 with
value 1. Sub-dial input wrote cursor properties 1095 and 1102. This connects
input delivery to a real setting write, beyond a static menu screenshot.

Run from this repository, after provisioning upstream:

```sh
node tools/om_emu_penf_editor.mjs /path/to/om-emu --out /path/to/new-stock-results
```

The probe checks the expected table entries and refuses an upstream version
that already exposes those keys. Its adaptation does not implement a complete
front creative-dial control.

## Running the HSL release

From this repository, supply the stock BIN and the patched BIN from the
`alpha-20261017` release:

```sh
python3 tools/om_emu_overlay.py /path/to/stock.BIN /path/to/patched.BIN /path/to/new-overlay.json
node tools/om_emu_penf_editor.mjs /path/to/om-emu --patch /path/to/new-overlay.json --out /path/to/new-hsl-results
```

The release has **5,145 changed main-payload bytes** and **725 changed resource
bytes**. Its two four-byte container checksum changes are excluded from the
overlay. The converter emits 395 maximal differing byte runs; these are not
395 code allocations or hooks.

PEN-F loads a 19,767,776-byte resource prefix; the last resource change ends at
19,430,903, so the Value edit is inside it. Main and resource preimages are
checked before applying the overlay.

The native editor displayed `Value` correctly. Delete inputs were delivered,
but the HSL headings and wheel were not visible; axis switching and H/L edits
were therefore **not validated** by this probe. A successful overlay load or
unchanged GUI state alone is insufficient evidence of those behaviors.

## Address conventions

For a main-payload byte at offset `o`:

- This repository's PEN-F runtime code address is `0x60021020 + o`.
- om-emu's disassembly notation is `0x50000000 + o`.
- Overlay offsets are just `o`, with no component-header bytes included.

For example, runtime `0x601a70cc` is disassembly notation `0x501860ac`.
The difference `0x10021020` applies to this main-code mapping, **not arbitrary
RAM or peripheral addresses**. Use the emulator's `runtime`/`disasm` helpers and
the command's documented address convention.

Upstream's `analysis/oly-fw-analysis/README.md` cross-checks this repository's
container, startup, input, settings and HSL findings against the same stock
payload. Its early description of PEN-F support predates the working port;
use `models.mjs` and current executable tests for present capabilities.
