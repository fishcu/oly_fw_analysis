# OM-5 Mark II Live ND32/ND64 experiment

Model E148, displayed firmware 1.1, internal build 1100. Official stock
update SHA-256: `9de5d77e1d290fa2ed4ebc7d75cee0ed490befbc89566722467d1d421d66d637`.
This definition changes only the main component `0x100`: the allowed values
for setting 1710 and the bounded ND-step selector. It is independent of the
experimental HSL/Monochrome/WB patch.

`nd64.py` checks the exact expanded stock main, the original bytes and
descriptor, and 768 selector cases (steps 0–255 times three EV units). It
compares unchanged stock behavior for steps 0–4 and 7–255. These are offline
instruction-model checks, not a native capture or camera test. The selected
1–6 range follows the corresponding OM-3 allowed list; actual E148 sensor,
ISP, display labels, EXIF and image output are unknown.

The patch builder rechecks the stock container, original and target ranges,
expanded and stored main hashes, and package hash. It withholds the install
file by default because `camera_tested` is false:

```sh
python3 patches/live-nd/om-5-ii/nd64.py /path/to/expanded-E148-main.bin
python3 tools/oly_patch.py patches/live-nd/om-5-ii \
  --stock /path/to/OLY_E_148_1100_0000_0000.BIN \
  --out generated/om5ii-live-nd
```

The recorded main-only package hash is
`033976171feb9a7ab89fc6edf01802447e74d240f23eb8f735a82e62d71c9fac`.
The build changes 37 stored main bytes; both stored and expanded spans of
compressed sections 6 and 7 remain stock byte for byte. This host check does
not establish boot behavior or a safe updater/recovery path. A separate E148
HSL build [failed to boot on a physical camera](https://github.com/xulfr/oly_fw_analysis/blob/codex/om5ii-hsl/patches/hsl/om-5-ii/BRICK-RISK.md)
on 4 November 2026; its cause is unknown. Do not infer that this standalone
definition is camera-qualified from its smaller edit set.
