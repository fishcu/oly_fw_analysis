# Patch definitions

Each patch is a directory built by [`tools/oly_patch.py`](../tools/oly_patch.py)
from a stock update file that you supply. The directory contains assembly
sources, linker scripts, any authored resources and a `patch.json` in the
`oly-patch/1` format. No firmware image is stored here; `patch.json` holds only
hashes of the original bytes and of the expected results, plus small data edits.

```bash
python3 tools/oly_patch.py patches/hsl/pen-f --stock OLY_E_122_3101_0000_0000.BIN --out generated/pen-f
```

The output directory must be new. It receives `build.json`, `restore-stock/`,
the per-section assembly outputs, `decoded/` with `--decoded`, and `install/`.
A definition with `"camera_tested": false` withholds `install/` unless
`--write-untested-package` is given.

| Patch | Model / build | Camera tested |
| --- | --- | --- |
| [hsl/pen-f](hsl/pen-f/README.md) | PEN-F 3.1 (3101) | Yes (alpha releases) |

## `oly-patch/1`

| Key | Meaning |
| --- | --- |
| `schema` | `"oly-patch/1"` |
| `name`, `model`, `firmware`, `release` | Identification; `release` is optional |
| `camera_tested` | Whether the exact package has been installed and exercised on a camera |
| `stock.sha256` | SHA-256 of the complete stock update file |
| `components` | Keyed by component kind (`"0x100"`): `before_sha256` and `after_sha256` of the decoded payload, and `cpu_base` when ranges use CPU addresses |
| `ranges` | Every changed span: `component`, `name`, `address` (CPU) or `offset` (decoded payload), `bytes`, `before_sha256`, `after_sha256` |
| `assembly` | Groups of `sources` linked with `linker`; each output section in `sections` (name → address) must be a declared range of `component` |
| `data_edits` | Literal replacement bytes (`after`, hex) for a declared range |
| `bitmaps` | Format-3 OSD bitmaps re-encoded from `source` (`width`, `height`, `pixel_symbols`, `pixels_sha256`) into a declared range of fixed size |
| `package` | `components` (`"all"` or a list of kinds, in stock order), `file` (e.g. `DCOLYMP/E1229999.BIN`), and optional recorded `sha256`, `bytes`, `restore_sha256` |

The builder checks the stock hash, each component and each original range
before changing anything; rejects overlapping, undeclared, repeated or missing
ranges; requires every built range, component and recorded package hash to
match; repairs each changed component's additive checksum while preserving
its header and trailer metadata; and parses the package again. These checks
establish that the bytes are the intended ones. They do not show that a change
is safe to install — see [validation](../docs/safety/VALIDATION.md) and
[update and recovery limits](../docs/boot/pen-f/RECOVERY.md).
