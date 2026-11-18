# OM-5 colour-profile processing: bounded comparisons

Inputs: OM-5 1.2/1200 (E144), update SHA-256 `a0c91f3ac7caaf0925b2af609e711183cf3b5982b3333224bcef26c0c5943d11`, decoded main `cf4babeab5f516514e4a9b6032b0374e643830511e083b9cdd26bcb02980af88`; OM-5 Mark II 1.1/1100 (E148), update `9de5d77e1d290fa2ed4ebc7d75cee0ed490befbc89566722467d1d421d66d637`, decoded main `f9c6b0bb37675a2b031ccf09292796ab5793994b8ce2053dcfd7f9fe68035cd8`. Addresses are analysis addresses in decoded or expanded images, **not flash offsets**; the Mark II mapping is a candidate.

Evidence below combines static inspection with isolated MN103 execution on synthetic memory. The experimental GNU simulator was built from a verified source tree, but its binary was not reproduced from the upstream pinned archive. It does not model the camera ISP or real settings and hardware. No physical camera was tested. The lab probes are not included in this contribution, so the numerical results below are a research record rather than an independently rerunnable test suite here.

On 4 November 2026, a separate experimental E148 HSL build [failed to boot on a physical camera](https://github.com/xulfr/oly_fw_analysis/blob/codex/om5ii-hsl/patches/hsl/om-5-ii/BRICK-RISK.md); a later stock reflash recovered that camera. The cause is unknown. The bounded comparisons here do not establish that a modified E148 image will boot.

## Settings records and selection

| Build | Getter / category-1 target | Metadata | Effective saturation IDs (`f6ea`) | Stored saturation IDs (`f6fa`) |
| --- | --- | --- | --- | --- |
| E144 | `602d2eee` / `602f179d` | `60514fec` | 910–921 | 922–957 |
| E148 | `602d2fc2` / `602f4c58` | `605193e8` | 916–927 | 928–975 |

The inspected metadata maps these IDs to successive record elements. Executing each stock getter, resolver and typed read with synthetic records and mocked address translation returned the expected stored values. Expanded-image selection slices at `60a34d3a` (E144) and `60a33a96` (E148) selected three groups of twelve IDs: 922–933, 934–945, 946–957 and 928–939, 940–951, 952–963 respectively. Synthetic backend and stock-record fixtures were used. The six-ID difference applies to these groups only; it is not a general settings translation. Although E148 metadata contains a fourth group, these slices did not establish how or whether it is exposed.

The slices are case arms of indirect dispatchers (`60a34cb5` and `60a339e4`). A bounded scan found their addresses in code-pointer blocks, but no literal references to those blocks' starts. This does not rule out computed access or establish runtime reachability. Neither tested slice has a demonstrated native path to the builder or writer.

## Builder and writer

Isolated candidate builders `603e2f1c` (E144) and `603e7c3f` (E148) were compared with PEN-F and OM-3 using 171 synthetic inputs per model. The twelve normalized 24-byte records and four-byte control word matched for each input; other fields and physical output were not compared. One fixture supplied synthetic H/L values. The tested input range is not evidence of a supported UI range.

The builder call sites guard on a composite request value of 11 and use `descriptor+1816` for twelve input bytes. The writer calls are guarded by bit 3 of `*(*(descriptor+8))`. Candidate writer windows were separately executed on synthetic RAM. A further test manually transferred selected profile bytes to a fresh builder call, then its records to a fresh writer call. These host-mediated transfers are not native call paths or evidence of real MMIO behavior. A camera capture path, persistence, image rendering and a functioning HSL editor remain unverified.
