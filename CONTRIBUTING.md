# Contributing

Contributions for any Olympus or OM System camera are welcome: format details,
function maps, hardware observations, tools, or corrections to existing findings.

A useful finding states:

1. Camera model, displayed firmware version, internal build and input hash.
2. The address space used: file offset, logical flash address or runtime address.
3. What the code does, and how to reproduce the observation.
4. Whether the evidence comes from disassembly, emulation, a desktop renderer
   or a physical camera. List modeled hardware responses and unresolved limits.

Organize explanations by function. Add new facts to the relevant topic instead
of appending a dated progress report. Keep firmware-specific constants separate
from general tooling, and preserve source attribution and applicable licenses.

Submit source and findings without vendor binaries, private photos/settings or
forum archives. Link to public references. Prefer reproducible probes over large
copied disassemblies; include the input hash and instruction boundaries.

Original contributions are accepted under Apache-2.0, except contributions to
the identified GPL components, which use GPL-3.0-or-later. Preserve third-party
notices and identify any material offered under different terms. Only contribute
material you have the right to submit under those terms. See
[licenses and attribution](RIGHTS-AND-PROVENANCE.md).

A successful checksum, emulator run or test on another model is not proof that
a modification is safe to flash. Describe the tested behavior precisely.
