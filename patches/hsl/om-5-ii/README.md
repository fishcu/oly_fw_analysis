# OM-5 Mark II HSL, per-profile white balance, Monochrome Profiles and Live ND32/ND64 (experimental)

> **DO NOT FLASH THIS BUILD.** On 4 November 2026, the owner reported that
> package SHA-256 `35f0caac4b70f1e59e3d5311fdf74a8c021d720755a7441796b080707b79d434`
> appeared to flash but the OM-5 Mark II then failed to boot: black screen and
> repeated autofocus movement. The first stock-firmware reflash attempt showed
> a sustained solid red light; a second attempt recovered the camera.
> The cause is unknown. Treat this patch and its generated install package as
> unsafe for camera use pending investigation. This recovery does not establish
> that other failures would be recoverable. See [brick-risk review](BRICK-RISK.md).

This port targets the official E148 firmware 1.1 build 1100. It restores Color
Profile 1–3 in the picture-mode selector and adds Hue and Lightness beside the
stock saturation axis. Each Color Profile also recalls its own white balance.
It follows the [OM-3 patch](../om-3/README.md) but uses E148-specific hooks and
settings IDs.

**Physical camera boot failure reported.** The builder keeps
the install package withheld by default. The COLOR carousel slots use an
existing stock picture-mode icon as a fallback, with their own text labels.
`apply_values` takes the profile from the picture-mode properties the capture
snapshot reads (see "H/L profile selection"), and the Color Profile number now
travels with the picture mode through custom modes (see "Custom modes"). The
ISP request and JPEG pixels remain untested. See
`phase4-om5ii-hsl/FUNCTIONAL-ASSURANCE.md` before any trial.

The update package contains only `0x100` (USR/main) and `0x101` (OSD/resources).
The main image uses opt-in `"repack": "split"` for its two LZ4 sections. This
keeps their longest literal runs at stock lengths, avoiding the former 93 KB
and 650 KB runs. Split repacking changes the stored representation without
changing the decoded edits; the current hashes are in `patch.json`. Other
camera patches do not enable this repack.

The [brick-risk review](BRICK-RISK.md) now **withdraws Probe B as a prerequisite**.
It repacks section 7, which contains the card updater; a failed load could
prevent recovery. `om-5-ii-probe-a` is an optional modified-image acceptance
check outside LZ4. Neither a same-version stock reflash nor Probe A proves
recovery from a bad boot. A full-mod camera trial remains high risk.
The E148 OK+power entry, off-CPU LZ4 decoder, boot with saved Color Profile
settings, and real capture pipeline remain camera-only tests. A failed early
boot may prevent the in-main card updater from running.

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
both split-repacked `olycompress` spans, the stored component, and the partial
update container against the recorded hashes. The resource block's compressed
record is also repacked with LZ4 HC and checked to fit its fixed span. The
builder preserves both component lengths and writes updated additive checksums.

The offline functional-assurance review traces the job dispatch and the
emulator's JPEG shortcut. Commit `bab4641` read the dispatch key (job record
`+10`, always 11 on the COLOR path) as a profile number, so H/L was never
applied. That is fixed (see "H/L profile selection"). A bounded synthetic
dispatcher/builder/writer fixture now applies H/L; a normal capture job and
the real ISP/JPEG result remain untested. The current package SHA-256 is
`817131a81bd309bc55fe3f12d8a77bf4a02574180eec33ca3443d3d008f2e05e`.

## H/L profile selection

The job record carries no profile number. The capture snapshot does: its
builder reads picture-mode property `0x948` (key 38017) into `+28735` and, when
that is 11, property `0xf6b` (key 63153) into `+28765` (`0x602c8821`,
`0x602c8855`). `apply_values` reads the same two properties through the same
accessor (`0x602bbed5`) and applies H/L only when they are 11 and 1–3. OM-Emu
gave 11/1, 11/2, 11/3 for Color Profile 1–3; every other picture mode it
accepted gave a mode other than 11 and `0xf6b` = 0. Like the H/L cells, these are read
when the COLOR block is built, not at the snapshot, so a profile change between
the two is not covered. `wb_profile` sits at `0x613f2f40` (section 8 ends at
`0x613f3000`).

## Custom modes (setting 903)

Setting 111 stores Color Profile 1–3 as picture-mode family 11; setting 903
holds the profile number. E147's mode-recall lists (`0x605f6c7c`) carry 903 in
the same row as 111; E148's (`0x604daf4c`) do not, because E148 hides the
profiles. Without 903, a custom-mode recall restores family 11 with whatever 903
holds. OM-Emu, previous build: Color Profile 2 assigned to C1 came back as
Color Profile 3 with Color Profile 3's effective settings, and a Vivid C1
recalled from a Color Profile in P read back as 111 = 56 with a stale profile
number and wrong effective saturation.

The patch replaces the per-entry copy call in the four list routines
(`0x602e0f82` in `0x602e0f40`, `0x602e1119` in `0x602e1071`: rows → working copy;
`0x602e0fe8` in `0x602e0fa5`, `0x602e11fc` in `0x602e1153`: working copy →
rows). The wrappers (section 8) make the stock call and, for 111 only, copy 903
in the same row (values above 3 are not copied). Section 8 loads before
section 2, so the hooks can run at any time. The routines that write defaults
into the rows are unchanged.

To make room in section 8, the custom-reset scratch (`creset_kind/ptr/ret/buf`,
300 bytes) moved to section 6's unused tail (`0xa0ca7e70–0xa0ca7fa0`, stock
`ff`, unreferenced; uncached alias as for `axis`), and that hook now takes
the stock path until section 6 is loaded.

## Emulator result

- Color Profile 1–3 are selectable and their native sector editor works.
- Delete cycles Saturation → Hue → Lightness; a main-dial edit wrote a valid
  part-1 H/L word for ID 928.
- Native synthetic key-11 fixture (real dispatcher, builder, hook and writer;
  fabricated job record): with 36 distinct CP1–3 H/L cells, Color Profile 1, 2
  and 3 each produced their own 12 sectors' hue and lightness, 36/36 as
  expected, and the writer copied each block exactly. Picture modes 2, 3 and
  6 (setting 111) gave the stock block unchanged.
- Picture-mode refresh: entering Color Profile 1 wrote the profile's
  Sharpness and Contrast to 7 and 8, its 12 sectors to 916–927, Shading to
  1016 and the tone curve to 383/690/382; a direct native call of the refresh
  (context 0, mode 54) rewrote them from the profile after they were
  overwritten. Editing a profile setting while in that profile updated them at
  once; editing another profile's did not. Leaving COLOR restored the stock
  zeros.
- White balance recall passed 9/9 scripted emulator checks. A part-1 diff over
  all 2265 IDs found changes only in the intended WB cells (904–907, 920–923)
  and H/L cell 928 during the exercised flow.
- E148 boot, display, and S2 capture passed the emulator's TFT and EVF model
  checks. Each capture produced one JPEG on the emulated card, which the check
  read back independently. A separate live COLOR1 S2 capture also wrote a card
  image, but did not reach the H/L builder hook in this emulator path.
- All three COLOR carousel slots render their fallback icons and labels with
  the repacked resource component in a live emulator session.
- **Near-native capture chain** (`phase4-om5ii-hsl/scripts/chain.py`): live
  settings → native capture snapshot `0x602c8139` → native snapshot-to-job copy
  `0x6041eeea` → the whole native job-record filler `0x6038aac0` → dispatcher,
  builder and H/L hook → writer. Only the job source buffer (zeroed apart from
  the block key) and the dispatcher object are fabricated. Color Profile 2:
  the record carries the profile's 12 saturations and the block carries its
  hue and lightness; Vivid with the same H/L cells stored gives the stock
  block.
- Sharpness, contrast, shading and the tone curve's highlight and shadow
  reach the capture snapshot (`+28694`, `+28700`, `+28768`, `+29469/29470`) as
  they do for stock modes; midtone (690) is not in the snapshot in either.
- **Custom modes** (stock mode dial C1, native assign `0x602db235`): Color
  Profile 2 → C1 → P changed → C1: profile, saturation, H/L cells, WB and WB
  records, effective settings and the capture snapshot all restored (7/7).
  Color Profile 3 in C1 while P holds Color Profile 1: 5/5. Vivid in C1 while
  P holds a profile: Vivid, no profile, stock block (3/3).
- **Custom-mode reset** of C1 (kinds 1 and 2) from P keeps P's H/L, WB
  records, profile and effective saturation (6/6).
- **Power cycle (approximation):** the whole settings store
  (`0x62428d80–0x62468d80`, which holds the rows, banks, working copy and
  properties) copied into a fresh session, then a mode-dial recall: Color
  Profile 1, 2 and 3 each came back with the same profile, cells, WB,
  effective settings and capture snapshot (5/5 each). The real NAND save and
  boot restore were not run.

## Colour wheel and tone-curve pages

The E148 picture-mode direct screen still builds the Color Profile detail
pages (children 2–5; the colour wheel is child 4, the tone curve child 2), but
its visibility updater (`0x60dad4eb`) never shows them. E147 does, from its
screen data (`0x611358eb..0x61135a23`). E148's data still flags the focused
item: byte +245 for the colour editor, +247 for the tone item.

`pages_hook` (`0x60dad5f5`, the updater's last call) shows child 4 or child 2
from those flags, for Color Profile 1–3 only. The pages carry the OM-1/OM-3
900x600 layout; E148's panels are 720x480, exactly 4/5 of it. On first show the
hook scales the page and its view by 4/5 and moves each label so its centre
scales, keeping text size. A page at most 720 wide is not scaled again.

In OM-Emu, on both TFT and EVF and without debugger writes:

- focusing the colour item shows the colour page: the axis title, the
  `Switch [Delete]` hint, the selected-colour swatch, the stock value label
  (which follows the H/L axis) and the `All / INFO` and reset hints, all inside
  the screen; the tone item shows Shadow / Mid / Highlight with their hints;
- the axis-title paint wrapper and the value-label hook now run natively;
- leaving and re-entering the screen shows the same layout.

The colour wheel itself, and the tone curve, are drawn by the camera's GPU
(C3D/OpenVG), which OM-Emu does not model. Whether they appear, and where, after
the 4/5 rescale is untested; it needs a camera. The display hook (wheel values
for the H/L axes) was still not called with the page visible.

## Native controls on Color Profile 1–3

Restoring the modes also restores their native per-profile controls:
Sharpness (IDs 904–907), Contrast (908–911), Shading Effect (912–915) and the
tone curve (Shadow / Mid / Highlight, three IDs per profile from 976; INFO
switches the part). Sharpness, Contrast and Shading use the stock slider; the
tone curve uses the restored page above. The per-profile white balance stores
its records in part 1 of 904–907 and 920–923; part 0 of 904–907 is native
Sharpness and is not touched.

E148 resolves the COLOR picture-mode artwork IDs to a placeholder resource
record, whereas E147 has dedicated bitmaps. The patch aliases the three
profiles' carousel IDs to E148's existing Color Vivid icon and their compact
display IDs to existing Color Vivid artwork. The profile names in the interface
still distinguish COLOR1–3. No E147 artwork or firmware binary is distributed.

## Profile settings reach the image (picture-mode refresh)

On E148 nothing applied a Color Profile's own settings. Its picture-mode
refresh (`0x602e00bf`, jump table `0x60499718`) sends 54–56 to the neutral
default, and its caller (`0x602e082f`) never writes the effective IDs the image
pipeline reads. The patch replays OM-3 (E147) refresh cases 54–56
(`0x604032a4`) and its caller (`0x604040ff`):

- jump-table entries 54–56 note the profile and take the stock default path;
- at the end of the refresh (`0x602e0826`) the profile's Contrast (908+p) and
  Sharpness (904+p) go to effective IDs 8 and 7, with 59 = 0, 105 = 1 and
  1806 = 0; the 12 sectors (928+12p…) go to effective saturation 916–927 in
  sector order; Shading (912+p) to 1016, 1011 = 998 = 0; and the tone curve
  (976+3p…, read from store 2 as E147 does) to 383, 690 and 382;
- other picture modes get E147's zeros for those extra IDs, written only after
  a Color Profile may have set them;
- E147 also refreshes when a profile setting changes (descriptor handlers
  `0x60400fc0` / `0x6040466d`… on 904–906, 908–910, 912–914, 928–963 and
  976–984). E148 has no such descriptors, so the patch does this after the
  stock commit (`0x602d19b1`) for contexts 0 and 1.

The refresh code sits in section 8's loaded tail (`0x613f2b80`): section 2,
where the hook is, has 36 free bytes, and boot loads section 8 before section
2. A short guard in section 2 still checks section 8's loaded bit.

## Picture-mode availability

The availability lookup `0x602ddb79` (table `0x604991f8`, 53 rows) had no
rows for 54–56 and returned ID 3200 (0). With setting 24 at 3, 4, 5, 6, 76,
77, 89, 90 or 115, `0x602df14f` then resets setting 111 to 1 (i-Enhance).
In OM-Emu, with setting 24 = 3, calling `0x602df14f` in Color Profile 1
dropped to i-Enhance with the stock table. The patch copies the table with
E147's rows (54 → 1072, 55 → 1073, 56 → 1074; E148 keeps those IDs and sets
them beside the other modes' at `0x6162dab4`) and repoints the lookup. The
same call then keeps 54. E147's nine-entry Creative-dial list
(`0x605e0238`) has no E148 counterpart and is not needed (E148 has no
Creative dial).

## Other robustness fixes

- **Custom-mode reset.** `0x602db531` clears both parts of the live cells and
  reloads them only for the current mode. Resetting another mode wiped the
  live H/L and WB (part 1 of 904–975). The patch keeps that part when the
  reset mode is not current (after section 6 has loaded). OM-Emu: stock wiped
  the test values, patched kept them.
- **WB before section 6 loads.** The WB wrapper uses section-6 code and state,
  so it takes the stock path until section 6's loaded bit (`0x20` of
  `0xa26e2698`) is set.
- **Axis title paint.** `paint_axis` draws with the caller's context in place
  and restores the two fields it changes (+52 style, +76 font set by
  `stock_font` at `0x60d51fa2`), instead of copying 684 bytes of context to
  the stack. Its frame drops from 748 to 80 bytes.
- **Delete forward.** `hsl_delete_action` passes command `0x9016` explicitly.
- **Sector order.** The builder's record r holds sector 2·(r mod 6) + ⌊r/6⌋
  (`0x603e7ca6`). `apply_values` uses that mapping.

OM-Emu does not run E148's section loader, so its loaded bits stay 0 there
and every guarded path takes the stock route. The checks above set the bits
(sections 1–10) to model a booted camera.

## Monochrome Profile 1–3

The same build also restores Monochrome Profile 1–3 (picture modes 57–59, family 12, profile number in
setting 989), which E148 keeps but hides as it did Color Profile. They appear in the carousel after
Color Profile 3. Rule masks follow Monotone, except E147's Focus Stacking rule, which sends them to Natural as
E147 does. 989 is copied with 111 in custom modes, like 903. The refresh tail writes each profile's sharpness,
contrast, filter, toning, level, shading, grain and tone (SET1–3 of 990–1029). Edits refresh at once, and the
detail pages use children 5 and 3. `MONO=0 python3 color_profiles.py` builds the Color Profile edits alone.

Emulator (3 Nov 2026): selection and refresh for 57–59; live edits of every field, with no change from another
profile's edits; C-mode matrix 6/6 including CP↔MONO; snapshot carries the mono number and filter/toning per
profile; stock modes unchanged across a full picture-mode cycle; section guards hold. Whether filter, toning and
grain reach the JPEG is not proven (OM-Emu has no image pipeline). Not tried on a camera.

## Live ND32/ND64

The build also carries the three Live ND edits from [`live-nd/om-5-ii`](../../live-nd/om-5-ii/nd64.py). Setting 1710
allows ND2–ND64, and the ND step selector handles steps 1–6 with E147's values. `nd64.py` checks 768 selector cases
on every build. Live ND doesn't run in OM-Emu, so whether the camera completes 32- and 64-frame shots is unproven.
ND2–16 run the same values as stock. Regenerate with `ND=0` to leave it out.

## Source layout

`color_profiles.py` documents the 54 data edits that restore the picture-mode
tables, rule masks, group membership, carousel, labels and availability rows.
`hsl.s` and `wb.s` contain the 23 assembled E148 sections. `patch.json` declares the exact ranges
and hashes, including the 0x101 resource aliases. Sections 6 and 7 are stored
in LZ4 `olycompress` spans; the shared builder repacks them while keeping each
section's original file span.

See [white balance details](WHITE_BALANCE.md) and the [OM-3 implementation](../om-3/README.md)
for the control scheme and storage format.
