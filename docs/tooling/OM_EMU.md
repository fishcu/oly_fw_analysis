# Interactive firmware emulation with om-emu

[om-emu](https://github.com/flatpanda/om-emu), by flatpanda with contributions
from xulfr, runs camera firmware with a modeled display, inputs and surrounding
services. Its main benefit is testing menus and UI changes without repeatedly
flashing a camera. It complements this repository's
[bounded native-call harness](EMULATOR.md).

This reference covers commit
`d24ff9dd20b98304541494d0199a5e6415eebdba`. Model support changes; consult that
revision's `emu/src/fw/models.mjs` and [upstream documentation](https://github.com/flatpanda/om-emu/blob/d24ff9dd20b98304541494d0199a5e6415eebdba/emu/README.md)
for exact builds. [PEN-F setup and independently checked behavior](pen-f/OM_EMU.md)
are documented separately.

## How it works

The CPU interpreter is JavaScript, using ES modules and a decoded-instruction
cache. It executes MN10300/AM33 instructions from the supplied firmware.
Firmware UI code sends drawing commands to modeled OSD and display hardware;
the host presents the resulting screen. This is more useful for UI development
than a manually recreated camera menu.

Selected kernel, input, settings, camera-application and GUI code run natively.
An execution harness starts the required services and supplies named stand-ins
for missing hardware and unexecuted firmware. Other CPU cores' services are
largely substituted. It does **not** run the complete camera from reset.

The reference camera is the OM-1, E143. Other models use address maps, facts
extracted from their firmware, board-family models and explicit overrides.
Shared architecture does not make one model's addresses or patches portable.

| Host | Operation | Useful tools |
| --- | --- | --- |
| [Static browser player](https://flatpanda.github.io/om-emu/web/index.html) | Module Web Worker runs the emulator; the user selects a local BIN. Firmware can be cached in browser storage. | Buttons, screen, session log, patch-file input. No installation needed. |
| Node.js 26+ | Local HTTP interface and emulator worker. No npm dependencies. | The same interactive player, scripted navigation, richer live debugging. |
| Node command-line debugger | Selected instruction entry or a running player's debug API. | Registers, memory, breakpoints, watchpoints, traces and task inspection. |

The browser and Node hosts share the emulator and API implementation. A local
Chrome check loaded PEN-F firmware, navigated menus and observed only GET
requests for static files, with no firmware upload. That observation covers
the tested revision and session, not every future deployment.

## Working with patches

Supply stock firmware matching the model's hashes, then apply an overlay.
`--patch FILE` is supported by the player, menu navigator and debugger; the
browser has a Patch file input. Changes apply to copies in emulator memory.

The JSON format is a list, or an object with a `patches` list. Each entry has
`block`, `offset`, `old` and `new`; byte strings are base64 and must have equal
lengths. Offsets address the **decoded component payload**, before the
emulator expands its runtime layout. `main` and `resource` name the supported
components. Resource changes must lie within the prefix that the model loads.

The emulator checks stock hashes, old bytes, ranges and overlaps. An arbitrary
modified BIN cannot simply replace the stock input: its hash would fail.
[om_emu_overlay.py](../../tools/om_emu_overlay.py) converts the difference between
two same-build OE update files to this JSON format. It validates container
checksums and matching headers, and refuses changes outside main/resources.
Container headers and updater checksums are not executed by the overlay.

Useful upstream entry points:

- `emu/bin/play.mjs`: interactive session; `--debug-api` enables live debugging.
- `emu/bin/nav.mjs`: repeatable menu inputs and screenshots.
- `emu/bin/debug.mjs --attach URL`: debug an existing local player.
- `emu/bin/modelcheck.mjs E122 --no-port`: stock model smoke checks.
- `emu/bin/fwmap.mjs`, `port.mjs`, `xto.mjs`, `xwhere.mjs`: static/coverage maps
  and cross-build address placement; check each command's model scope.

The standalone debugger defaults to an OM-1 ND128 candidate. Explicitly select
the intended model and image, or attach to an already selected player.

## What a successful test establishes

Rendered text, bitmap resources, menu transitions and observed setting writes
are valuable evidence about the executed path. Screenshots and input logs make
regressions reproducible, but successful navigation does not establish visual
fidelity. Review of the PEN-F screenshots also identified missing menu
background graphics, beyond the COLOR editor's missing elements. The CPU model
checks natural data alignment, a gap
in this repository's GNU-based harness that previously mattered for a UI patch.

Important limits remain:

- Startup is assembled by the harness. Passing a session does not establish
  the reset boot path, physical OK+power recovery, updater acceptance or safety
  after flashing.
- Timing, interrupts, heap allocation and other cores include models. A
  working session does not prove real-time behavior or absence of races.
- Synthetic sensor/capture content does not reproduce the camera ISP. A JPEG
  on the simulated card is not a test of HSL, grain or vignette pixel output.
- Graphics remain incomplete, including menu backgrounds and COLOR elements.
  The emulator is not yet a visually faithful reference for the entire UI.
  Upstream identifies the OM-3 color wheel as a
  GPU/C3D/OpenVG path that is not drawn. PEN-F's wheel is also absent in the
  tested session; the same cause is plausible but not independently traced.
  This does not explain every missing menu graphic or text element.
- Saved settings and peripheral support differ by model. PEN-F persistent
  settings are not supported at this revision.

The upstream pure tests passed locally, including 5,311 instruction vectors
on each execution tier. These include comparisons with other emulators and
manual-derived expectations; they are not a silicon conformance certificate.

Some older upstream notes describe a fully substituted camera application or
call the project a full-system emulator. Current `camapp.mjs` executes CA_MAIN
with substantial stand-ins; current architecture and code take precedence over
those older descriptions. Read [fidelity notes](https://github.com/flatpanda/om-emu/blob/d24ff9dd20b98304541494d0199a5e6415eebdba/emu/FIDELITY-NOTES.md)
alongside the implementation.

## Source and attribution

See [community source records](../../provenance/community-reports.json) for the
revision, authorship and verification scope. The upstream repository has no
repository-wide license file at the inspected revision, and GitHub reports no
detected license. Public availability alone should not be treated as permission
to redistribute or relicense its code. The integration helpers here are
independently authored; obtain upstream and firmware separately.
