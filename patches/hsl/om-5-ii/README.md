# OM-5 Mark II HSL and per-profile white balance (experimental)

This port targets the official E148 firmware 1.1 build 1100. It restores Color
Profile 1–3 in the picture-mode selector and adds Hue and Lightness beside the
stock saturation axis. Each Color Profile also recalls its own white balance.
It follows the [OM-3 patch](../om-3/README.md) but uses E148-specific hooks and
settings IDs.

**Emulator only.** Nothing has been installed on a camera. The builder keeps the
install package withheld by default. The COLOR carousel icon is still blank;
E148's resource block lacks the corresponding bitmap IDs.

## Build from your official BIN

```sh
python3 tools/oly_patch.py patches/hsl/om-5-ii \
  --stock /path/to/OLY_E_148_1100_0000_0000.BIN \
  --out generated/om5ii-hsl --decoded
```

The stock SHA-256 is
`9de5d77e1d290fa2ed4ebc7d75cee0ed490befbc89566722467d1d421d66d637`.
GNU `mn10300-elf` binutils 2.43 were used. The generated directory contains an
expanded `decoded/0100.bin`, a stock restore file and `build.json`. The decoded
main image is for analysis; E148's emulator also relocates boot preload regions,
so use the emulator's normal image-patch interface for a live session. No
firmware binary belongs in the source tree.

The builder checks the source BIN, every edited range, the expanded main image,
both recompressed `olycompress` spans, the stored component, and the complete
update container against the recorded hashes. It preserves the original
component length and writes the updated additive checksum.

## Emulator result

- Color Profile 1–3 are selectable and their native sector editor works.
- Delete cycles Saturation → Hue → Lightness; a main-dial edit wrote a valid
  part-1 H/L word for ID 928. The H/L builder output was exercised by a direct
  firmware call.
- White balance recall passed 9/9 scripted emulator checks. A part-1 diff over
  all 2265 IDs found changes only in the intended WB cells (904–907, 920–923)
  and H/L cell 928 during the exercised flow.
- The display hook, axis-title paint wrapper and builder during a real capture
  have not been exercised. Emulator power-off resets stock settings as well, so
  it cannot establish persistence across power cycles.

The three missing COLOR icons remain a visible limitation. The two main-image
value-to-icon maps point at IDs `0xabd`–`0xabf`, which are absent from E148's
resource block. Replacing those maps with an existing Color Creator icon did
not make the carousel slot render. This patch leaves the stock icon references
alone rather than claiming a cosmetic fix that the emulator did not show.

## Source layout

`color_profiles.py` documents the 51 data edits that restore the picture-mode
tables, rule masks, group membership, carousel and labels. `hsl.s` and `wb.s`
contain the 16 assembled E148 sections. `patch.json` declares the exact ranges
and hashes. Sections 6 and 7 are stored in LZ4 `olycompress` spans; the shared
builder repacks them while keeping each section's original file span.

See [white balance details](WHITE_BALANCE.md) and the [OM-3 implementation](../om-3/README.md)
for the control scheme and storage format.
