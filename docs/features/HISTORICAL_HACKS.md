# Published firmware modifications

Stock/hack pairs show which bytes changed and whether repacking preserves the
container. They provide precedent for modification techniques, not a guarantee
of recovery on another model or with arbitrary changes.

## Changes understood in native context

| Model / internal build | Decoded main bytes changed | Whole encoded file bytes changed | Effect |
| --- | ---: | ---: | --- |
| PEN-F / 3100 | 4 | 8 | Two duration operands become 32,400 |
| E-M1 II / 3001 | 14 | 18 | Duration-return replacement and stacking allowlist bypass |
| E-M5 II / 4100 | 6 | 10 | Two duration operands and stacking allowlist bypass |

These pairs preserve component metadata and all non-main payloads. Applying
the edits and repairing the additive checksum reproduces the distributed files
exactly. “Main” means the application component, not one C function.

PEN-F routine `60566309` returns 1740 for modes 3/6 and 7200 for mode 4. The
patch changes operands at decoded offsets `5452ff` and `545305` to 32400;
unsupported modes retain their failure path. The routine also matches stock
3101. Separate file/chapter/storage limits can remain after this duration change.

E-M1 II replaces twelve bytes at decoded offset `3333b8` (`603543d8`) with an
early successful return of `70000010` through the output pointer. It therefore
also succeeds for previously unsupported mode inputs. Two bytes at `631d6f`
(`60652d8f`) remove the stacking allowlist-failure branch. Earlier prerequisite
and null-lens checks remain; the patch does not add a missing stacking engine.

E-M5 II uses the PEN-F-style duration operands at decoded offsets `534866` and
`53486c`, and the stacking branch at `3f2ad5` (`60413af5`). Its lens-object field
is +576 rather than E-M1 II's +1092: matching patch shapes do not imply matching
object layouts.

## Wider comparison set

The xdel collection contains twelve complete stock/hack pairs, covering E-M1,
E-M1 II, E-M1 III, E-M5 II/III, E-M10 II/III, E-PL9 and PEN-F. A textual E-M1 III
1.5 recipe is a separate source, not a downloaded patched BIN. Exact identities
and source paths are in the [firmware inventory](../../provenance/firmware-inventory.json).
Not every branch in this wider set has the deeper native-context tests above.

The independently reconstructed OM-3 V22 tethering patch changes 3,555 decoded
main bytes in 35 guarded edits, including 3,380 changed bytes in three padded
regions. It is substantial added code, with a reported OM-1 II porting origin.
The contributor reports working USB live view and recovery from a failed
experiment. Those reports do not supply the failed image or a complete recovery
trace. Its [code-space layout](../safety/CODE_SPACE.md) is independently analyzed.
The [OM-3 tethering reference](../protocols/om-3/TETHERING.md) explains the
startup selectors and protocol pieces, with attributed reports and native checks.

## E-M1 III 1.2 header defect

One mirrored E-M1 III 1.2 package has malformed metadata in its fifth component:
kind `0107` becomes `ccd8` while the component payload remains unchanged.
The file still passes its additive checksums.

The historical packer's documented error writes six `unknown3` bytes into
`zeroPadding2` instead of `zeroPadding3`. Reproducing that mistake yields the
observed header and trailer exactly. This is evidence of a repacking bug, not
proof that a camera bricked or safely ignored it. A checksum check must therefore
be accompanied by exact metadata and unchanged-component comparisons.

Tools: [historical_hack_audit.py](../../tools/historical_hack_audit.py) and
[om3_code_space_audit.py](../../tools/om3_code_space_audit.py).
Public source collection: [xdel Olympus firmware](http://xdel.ru/downloads/olympus-firmware/).
