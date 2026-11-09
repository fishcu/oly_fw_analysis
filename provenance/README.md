# Inputs and sources

Use hashes to identify firmware. A displayed version, filename or mirror label
can refer to different internal builds.

- [Firmware inventory](firmware-inventory.json): complete container identities,
  component metadata and available public source URLs.
- [Other binary identities](noncontainer-binary-inventory.json): decoded or
  unclassified inputs; these are not all installable firmware.
- [Disassembly windows](disassembly-windows.json): address ranges and input hashes
  for local regeneration. Equivalent windows are grouped; aliases preserve
  original reference names.
- [Topic sources](knowledge-sources.json): source-document identities behind the
  reference pages. Source names identify research records, not required local
  files or links to downloadable artifacts.
- [Tool source manifest](../tools/manifest.json) and [input contracts](../tools/inputs.json).
- [Historical patch comparisons](historical-patches.json): exact stock/hack
  identities and component-level differences where available.
- [PEN-F release history](penf-release-history.json): published versions, internal
  filenames and documented changes, including versions without a retrieved file.
- [External references](SOURCES.md): manuals, processor documentation and prior
  camera research.
- [Community reports](community-reports.json): attributed contributions, publication
  dates, source identities and the scope of independent verification.
- [Aperture-ring release inventory](azqeurio-release.json): azqeurio's model/feature
  database and PEN-F patch locations, summarized without executable payloads.

Container metadata checks establish structure, not authenticity or safe camera
execution. A historical mirror's availability can change. Public download URLs
are source attribution; temporary signed query credentials are not retained.

The small files under `analysis/` are factual inputs used by probes, not complete
captured execution logs. Their source hashes identify the original observations;
regenerated runs have their own source and output hashes.
