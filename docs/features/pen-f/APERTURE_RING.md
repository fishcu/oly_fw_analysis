# Panasonic aperture-ring input

Azqeurio's firmware patch connects Panasonic lens aperture-ring input to the
camera's existing exposure controls. The PEN-F implementation requests an extra
field in lens-status replies, reads the ring value, and substitutes it for the
body aperture setting in A/M modes. It is a small code extension, not a single
feature flag.

The [announcement by u/jun0727](https://www.reddit.com/r/M43/comments/1xgqgwx/made_firmware_twick_tool_for_olyom_cameras/)
was published on October 27, 2026. The analysis below covers
[azqeurio's dbv0.3.2 release](https://github.com/azqeurio/om-c-firmware/releases/tag/dbv0.3.2),
published October 31, and **PEN-F E122 3101**. Other bodies use different hooks.

## How it works

1. **Check lens support.** The patch reads the existing lens descriptor through
   `a1c40090`. It requires bit `0x80` at offset `+0x23c`, plus stock availability
   and state checks. This is a capability-based gate, not a hardcoded list of
   Panasonic lens names.
2. **Ask for the ring value.** It sets an optional-field bit on three recognized
   lens-status command forms. The central dispatch hook modifies byte `+21`,
   bit 0, for command-byte pairs `c1/80`, `c1/00` or `81/e3` at offsets `+18/+19`.
3. **Read and remember the response.** An added parser reads a little-endian
   halfword and advances the cursor by two bytes. Stock code at this boundary
   handles the next optional field but not this one. The patch caches the value
   for status channels 0, 2 and 6, together with validity and lens identity/state.
4. **Use it as aperture input.** At the stock read of parameter `0x80ca`, a valid
   ring value replaces the body value in A/M. `0x8000` keeps body control,
   consistent with the ring's A position. C1–C4 also work when based on A/M.
   The patch passes the signed value through without a new f-number conversion
   table; its physical scale has not been independently calibrated.
5. **Fall back when unsuitable.** Other shooting modes, missing capability,
   invalid cache, changed lens identity or failed state checks retain the body
   aperture result. Initialization and several error paths invalidate the cache.

The existing firmware still performs lens communication and aperture control.
The patch extends the information that reaches those controls. This explains
why ordinary lens operation can remain unchanged while the ring becomes useful;
it does not establish Olympus' reason for omitting this input.

## Function and data map

All addresses below are for the exact 3101 main payload.

| Address | Role |
| --- | --- |
| `60160fb1`, `60160fdf` | Stock lens-object getters, with different availability checks |
| `601636db` | Stock state predicate: reject `0x0b0a`, otherwise test `word & 0x0a` |
| `60173dd5`, `60175f48` | Request-field and central dispatch hooks |
| `6016527e` | Parser hook; active added code at `60060510` |
| `605ddb6c` | Aperture input hook around getter `600750ee`, parameter `0x80ca` |
| `60060780` | Added mode helper: A/M enums 2/4, C1–C4 enums 53–56 |
| `60158fee`, `60160ed0` | Reset/init cache-clearing hooks |
| `a0060800` | 16-byte cache: value, padding, validity, six identity bytes, state halfword |
| Descriptor `+0x240` | Six bytes copied and compared as lens identity |
| `a1c492d0` | State halfword copied with the cache; complete physical meaning unresolved |

Five parser-call sites also acquire length guards. These account for the extra
halfword before invoking stock parsing and reject short replies with status
`0x6507`. Additional callback hooks prevent errors from leaving a stale ring
value active.

The patch changes **3,416 bytes in 16 main-component regions**: one 3,903-byte
allocation at `60060010..60060f4f`, plus 15 small hooks. The allocation was all
`ff` in stock and contains code, padding and cache state. One further supplied
patch record, named `loader_patch`, changes no bytes. It is not a bootloader
modification. Container checksums change as required.

## Verification and limits

Independent checks matched every supplied old-byte record against stock and
reproduced the release's advertised complete-container hash. **100 bounded
native execution cases** verified input selection, custom modes, cache mismatch
fallback, request-field bits, parser cursor advancement and short-reply rejection.
The models supply lens availability, body aperture and shooting modes; they do
not simulate a physical lens, boot, task timing or the full exposure pipeline.

There is a useful hardware report:
[47h9n5yj8d-arch, issue #7](https://github.com/azqeurio/om-c-firmware/issues/7),
November 1, confirms PEN-F with DG Nocticron 42.5 mm f/1.2. The same report says
Four Thirds D Summilux 25 mm and D Vario-Elmar 14–150 mm rings do not work through
MMF-3. On E-M5 II, [NekoSkwama's issue #4](https://github.com/azqeurio/om-c-firmware/issues/4)
reports aperture movement without updated exposure/DOF preview. Lens movement
alone therefore does not establish complete integration.

The current package's PEN-F metadata still labels it a test candidate with no
recorded physical verification. It also records a boot failure for a specific
**withdrawn 0.2.8 payload**, and says its dispatch return was subsequently repaired.
That is distinct from a failure demonstrated in dbv0.3.2. Hardware reports do not
identify exact payload hashes, so their scope should remain explicit.

No patch intervals overlap the published PEN-F HSL `alpha-20261017` main changes.
This is only an address comparison, not a tested combined firmware.

## Reproduce the inspection

The Windows EXE contains a JSON patch database despite the repository having no
patcher source. These tools read that database as data; they never run the EXE.

```sh
python3 tools/oly_release_inspect.py /path/to/db.firmware.0.3.2.exe --output /tmp/ring-inventory.json
python3 tools/penf_aperture_ring_probe.py /path/to/db.firmware.0.3.2.exe --output /tmp/ring-native.json
```

The second command also needs the stock main and emulator described in the
[tool guide](../../../tools/README.md) and [input contracts](../../../tools/inputs.json).
Release hashes, model inventory and source attribution are in
[the release inventory](../../../provenance/azqeurio-release.json) and
[community reports](../../../provenance/community-reports.json).
The inspection creates reports, not an installable firmware file.
