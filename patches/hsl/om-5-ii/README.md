# OM-5 Mark II HSL and per-profile white balance (experimental)

This port targets the official E148 firmware 1.1 build 1100. It restores Color
Profile 1–3 in the picture-mode selector and adds Hue and Lightness beside the
stock saturation axis. Each Color Profile also recalls its own white balance.
It follows the [OM-3 patch](../om-3/README.md) but uses E148-specific hooks and
settings IDs.

**Emulator only.** Nothing has been installed on a camera. The builder keeps the
install package withheld by default. The COLOR carousel slots use an existing
stock picture-mode icon as a fallback, with their own text labels.

## Build from your official BIN

```sh
python3 tools/oly_patch.py patches/hsl/om-5-ii \
  --stock /path/to/OLY_E_148_1100_0000_0000.BIN \
  --out generated/om5ii-hsl --decoded
```

The stock SHA-256 is
`9de5d77e1d290fa2ed4ebc7d75cee0ed490befbc89566722467d1d421d66d637`.
GNU `mn10300-elf` binutils 2.43 and `liblz4` 1.9.4 were used. The generated directory contains an
expanded `decoded/0100.bin`, a stock restore file and `build.json`. The decoded
main image is for analysis; E148's emulator also relocates boot preload regions,
so use the emulator's normal image-patch interface for a live session. No
firmware binary belongs in the source tree.

The builder checks the source BIN, every edited range, the expanded main image,
both recompressed `olycompress` spans, the stored component, and the complete
update container against the recorded hashes. The resource block's compressed
record is also repacked with LZ4 HC and checked to fit its fixed span. The
builder preserves both component lengths and writes updated additive checksums.

## Emulator result

- Color Profile 1–3 are selectable and their native sector editor works.
- Delete cycles Saturation → Hue → Lightness; a main-dial edit wrote a valid
  part-1 H/L word for ID 928. The H/L builder output was exercised by a direct
  firmware call.
- White balance recall passed 9/9 scripted emulator checks. A part-1 diff over
  all 2265 IDs found changes only in the intended WB cells (904–907, 920–923)
  and H/L cell 928 during the exercised flow.
- E148 boot, display, and S2 capture passed the emulator's TFT and EVF model
  checks. Each capture produced one JPEG on the emulated card, which the check
  read back independently. A separate live COLOR1 S2 capture also wrote a card
  image, but did not reach the H/L builder hook in this emulator path.
- All three COLOR carousel slots render their fallback icons and labels with
  the repacked resource component in a live emulator session.
- The display hook, axis-title paint wrapper and builder during a real capture
  have not been exercised. Emulator power-off resets stock settings as well, so
  it cannot establish persistence across power cycles.

E148 resolves the COLOR picture-mode artwork IDs to a placeholder resource
record, whereas E147 has dedicated bitmaps. The patch aliases the three
profiles' carousel IDs to E148's existing Color Vivid icon and their compact
display IDs to existing Color Vivid artwork. The profile names in the interface
still distinguish COLOR1–3. No E147 artwork or firmware binary is distributed.

## Source layout

`color_profiles.py` documents the 51 data edits that restore the picture-mode
tables, rule masks, group membership, carousel and labels. `hsl.s` and `wb.s`
contain the 16 assembled E148 sections. `patch.json` declares the exact ranges
and hashes, including the 0x101 resource aliases. Sections 6 and 7 are stored
in LZ4 `olycompress` spans; the shared builder repacks them while keeping each
section's original file span.

See [white balance details](WHITE_BALANCE.md) and the [OM-3 implementation](../om-3/README.md)
for the control scheme and storage format.
