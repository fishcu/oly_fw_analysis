# E148 Color and Monochrome Profile experiment: bounded findings

OM-5 Mark II E148 1.1/build 1100, official update SHA-256
`9de5d77e1d290fa2ed4ebc7d75cee0ed490befbc89566722467d1d421d66d637`.
These results describe the experimental
[HSL/WB source at `1bd6276`](https://github.com/xulfr/oly_fw_analysis/tree/1bd6276/patches/hsl/om-5-ii),
not a stock feature or a camera-qualified patch. That exact build later
[failed to boot on a camera](../../boot/om-5-ii/EXPERIMENTAL-BOOT-FAILURE.md).
The private lab harness and logs are not in this repository, so the table is
a bounded research record rather than a rerunnable upstream test suite.

## E148-specific identities

The experiment restores Color Profile 1–3 as picture-mode values 54–56 and
Monochrome Profile 1–3 as 57–59. Profile numbers are held in setting IDs 903
(Color) and 989 (Monochrome). E148's signed effective Midtone is ID **691**;
the analogous E147/OM-3 field is **690**. E148's Color saturation groups
start at 928, 940 and 952, with twelve sectors each; Hue/Lightness are stored
in part 1 of the same per-sector IDs in the experiment. These identities came
from E148 disassembly and native setting/descriptor checks. They do not show
that the modified image boots or that the ISP uses every effective value.

| Question | Bounded result at `1bd6276` | Limit |
| --- | --- | --- |
| Stock picture modes | A 41-mode comparison of effective settings against stock found no difference after profile refresh fixes. | OM-Emu/native settings, not camera image output. |
| Color/Mono selection | Carousel, setting IDs 111/903/989 and property values followed the six restored profile slots in the emulator. | GPU artwork and physical dial paths are not fully modeled. |
| Profile edits and tone | UI and native checks covered Hue/Lightness clamps, tone pages, stock-mode tone restoration and both active settings contexts. | Color Profile Shading Effect remained inert because E148 lacks descriptors for IDs 912–915. |
| Custom modes and reset | Synthetic bank assignment/recall and reset cases passed after fixes for stale profile numbers and context-1 tone ownership. | Real NAND boot restore, backup and physical C-mode timing were not tested. |
| Builder/writer | Fabricated image-job fixtures reached native COLOR builder and writer instructions and compared twelve sector records; 41 stock-mode record hashes stayed unchanged. | The job object was fabricated. OM-Emu's ordinary S2 JPEG path bypasses this native recording chain and uses a lab encoder. |
| White balance | Per-profile UI/setting recall passed in the modeled environment. | Image-owned WB, one-touch measurement, queued/burst correctness and final JPEG/RAW behavior remain unknown. |

The current H/L hook reads from image-job properties after an earlier attempt
used a byte that was always the COLOR request key 11. The corrected synthetic
fixture does not prove that a real image job carries the intended profile or
that values are owned at shutter time. Hue/Lightness and WB timing can change
between UI edits, job construction and later processing. A native request to
the ISP, actual pixel output and physical persistence were not observed.

The lab's proposed portable regressions are stock-mode invariance, E148
Midtone 691, twelve-sector mapping, profile isolation, both settings contexts,
custom-mode bank recall/reset, load guards and deterministic UI/setting soaks.
Each needs exact source and stock hashes, fresh emulator state, and explicit
labels for UI input, native firmware execution and direct RAM injection. Those
tests would still not replace an E148 loader and boot test.
