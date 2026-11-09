# Licenses and attribution

Except as identified below or in per-file notices, original code,
documentation and research metadata contributed to this project are licensed
under the [Apache License, Version 2.0](LICENSE). This grant covers only rights
held by the contributors. Third-party material and vendor firmware are not
relicensed.

## Exceptions and attribution

- [tools/mn103_runner.c](tools/mn103_runner.c),
  [tools/mn103_strict.patch](tools/mn103_strict.patch) and
  [tools/prepare_mn103_sim.py](tools/prepare_mn103_sim.py) are
  [GPL-3.0-or-later](LICENSES/GPL-3.0.txt). The runner links against GNU libsim;
  the patch and preparation script modify the GNU simulator. GNU source
  context retains its upstream attribution. A distributed built engine must
  satisfy the applicable GPL source and license requirements.
- [Value lettering](patches/hsl/pen-f/value-pixels.txt) derives from DejaVu
  Sans Condensed. Its existing [DejaVu/Bitstream notice](LICENSES/DejaVu.txt)
  is retained with the artwork; it does not license the surrounding firmware.
- External research and firmware identities retain their attribution in
  [provenance](provenance/README.md). Source links do not place the linked
  work under this repository's license.

The HSL source includes short displaced stock instructions at hook boundaries
and small before/after byte edits. It does not include a firmware image or
bulk disassembly. Those vendor-derived fragments are outside the Apache grant,
including when they appear beside original code carrying an Apache notice.
The separately obtained IDA processor module, emulators and other external
dependencies retain their own terms.

A license for these tools does not grant rights to vendor firmware, Workspace,
third-party patchers or extracted resources. In particular, stock and patched
firmware BINs in release archives are not Apache-licensed firmware. Obtain
required inputs separately under their applicable terms. Source hashes identify
material; they do not establish redistribution permission.
