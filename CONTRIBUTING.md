# Contributing

Contributions for any Olympus or OM System camera are welcome: format details,
function maps, hardware observations, tools, or corrections to existing findings.

## Hardware testing for firmware patches

Before merging or publishing a flashable firmware modification, we need
confirmation from someone who installed it on the target camera and checked
that the modified feature works. The contributor's own firsthand report is
sufficient; photos or video are welcome but not required.

The report must identify:

- Camera model and base firmware version/build.
- Exact tested build or firmware SHA-256.
- Successful installation and boot, what behavior was checked, and the results.
- Known problems and limits of the test.

Emulator and static checks alone do not meet this requirement. It also applies
to source-only patch definitions that generate installable firmware. A successful
boot alone does not establish that the modified feature works.

A build-tool change may refer to an existing camera test if it reproduces the
tested firmware byte for byte; verify the output hash. Research notes, bounded
probes and general tools remain welcome without a camera flash, provided their
evidence and limitations are explicit. Do not present unverified findings as
working camera features.

Hardware confirmation is a minimum acceptance requirement, not a guarantee of
safety or a substitute for technical review.

## Research findings

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
