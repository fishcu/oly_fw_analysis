# OM-3 Human detection

Static research for the exact OM-3 E147 1.1 input and address mapping in
[AF button profiles](AF_BUTTON_PROFILES.md#inputs-and-static-reproduction).
The main software path separates raw detection, candidate filtering and
stabilization, Human-specific association, and AF target selection. No
inference run, recognition benchmark or physical AF result is reported.

## Model selection and submission

The stock resource stores Off (0), Motor Sports (1), Airplane (2), Train (3),
Bird (4), Animal (5) and Human (6). Main routine `0x60847300` maps enabled
modes to banks 0–5. Human selects bank 5, at logical address `0x4c33f800`
in component `0106` (decoded offset `0x6a7f7e0`, 9,383,936 bytes,
SHA-256 `80f8477268bfed5e4576d5b8c12cecf9a14c45d34a5dbb4463c64c5ac8b2cdcb`).
`0x60842f15` assigns class base 51; `0x60872f89` maps Human to downstream
kind 13. These are IDs, not confidence thresholds. The examined submission
interface includes 640-wide YC inputs. Effective sensor crop and cadence
were not established; the learned data format is unreconstructed.

Run the [same stock probe](../../../tools/om3_af_probe.py) with both components
to recover the enum and hash the Human bank locally:

```sh
python tools/om3_af_probe.py /path/to/decoded/00_0100_50000020.decoded.bin --resources /path/to/decoded/02_0106_458c0020.decoded.bin
```

## Result processing

- **Filtering:** Result judge `0x60846d1b` calls the IP-area filter
  `0x60846ec7` and detection-area filter `0x60847054`. Class conversion
  also applies deletion masks. A candidate may disappear after inference.
- **Temporal stabilization:** `0x608473d6` matches, registers and removes
  candidates. Policy functions `0x60848be4` and `0x608488f5` compare counters
  and geometry. Recovered values such as 500 and 37,200 are not verified
  pixel-size limits; neither the units nor cadence are established.
- **Human association:** `0x6084a693` combines parts using face and body
  registration (`0x6084aad1`, `0x6084b204`) and front-eye selection
  (`0x6084b38f`). Eight slots occur in this interface; a universal person
  limit or biometric identity is not established.
- **Application handoff:** Publication includes `0x6084bcdc`,
  `0x6087215e` and `0x6087197d`. Reader `0x6086b5b9` has a
  secondary-to-primary geometry fallback; AF selection at `0x6086eaec`
  further applies reference region and prior state. Inspect assembly through
  the return at `0x6086b8ba`: an earlier Ghidra flow override at `0x6086b627`
  truncated that reader's exported C.

To reproduce the code observations, disassemble from the listed boundaries
using the main-component import above and compare branch/call targets. The
[pinned Human analysis](https://github.com/tsmkirby/oly_fw_analysis/blob/9d320dc1e74c4e5de987f3776664057190e85c22/research/om3_af_profiles/HUMAN-DETECTION-ANALYSIS.md)
contains the fuller call map. The fork's `scripts/OM3HumanWindows.java` and
`trace_human_detection.py` provide bounded windows, and its
[static evidence](https://github.com/tsmkirby/oly_fw_analysis/blob/9d320dc1e74c4e5de987f3776664057190e85c22/research/om3_af_profiles/recorded-evidence/human-detection/verified-evidence.json)
records the data checks. Model bytes and bulk listings are not included.

For small subjects, a useful experiment would compare raw candidates with
the filtered, stabilized, associated and selected results for the same scene.
Relaxing persistence might change visibility of intermittent candidates; it
cannot create a result missing from inference. No accuracy improvement or
single-constant fix has been demonstrated.
