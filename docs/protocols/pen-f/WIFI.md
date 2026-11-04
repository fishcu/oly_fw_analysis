# Wi-Fi settings and recipe transfer

PEN-F hosts its own Wi-Fi network. A client joins through the normal SSID/password
or QR-code workflow. Private connection supports remote operation; One-Time
connection is more limited. The camera's HTTP service is ordinarily at
`192.168.0.10`. The [camera manual](https://learning.omsystem.com/PEN-F/zz_pdf/pen-f_eng.pdf)
describes connection setup.

Stock firmware also has a separate [SD parameter override and port-23 debug
shell](WIFI_DEBUG.md). That route is distinct from the HTTP recipe interface
below and has different access and lifetime implications.

## Stock protocol

PEN-F 3100/3101 contain the same OI.Share 2.60 command description: 23 listed CGI
commands and nine writable named properties. It does not advertise a twelve-sector
recipe import. OM-3 1.1 has a larger description with named settings-backup and
partial-transfer commands; their presence does not establish the route used by
every app profile-loading feature.

PEN-F also implements unadvertised `get_mcon.cgi`, `get_mcon_list.cgi` and
`set_mcon.cgi`. Numeric readback works on the physical camera. The stock raw
setter can change stored records without refreshing the live and image-processing
copies. HTTP 200 from that route is not evidence of an applied recipe.

## HSL1 extension

The extension reuses the existing parser and normal application-event/setter
machinery. It does not perform a raw write followed by a guessed save request.
A capability query is required before any marked write:

```text
get_mcon.cgi?mode=FFFF  →  48534C31  (ASCII HSL1)
```

The parser's numbers are hexadecimal. Stock returns zero for this unknown ID.

| Operation | Encoding |
| --- | --- |
| Read stock value | `mode=ID` |
| Read H | `mode=8000 OR ID` |
| Read L | `mode=C000 OR ID` |
| Write S / ordinary scalar | Value high halfword `4850` |
| Write H | Value high halfword `4851` |
| Write L | Value high halfword `4852` |

Writes use the native setting ID and a signed 16-bit value in the low halfword.
For COLOR2 sector 0, ID 943 = `03af`; L+7 is `48520007`. Invalid combinations
in the reserved `485x` family are rejected rather than passed to the raw writer.
Unavailable H/L reads return `80000000`, outside the valid range.

The supported recipe has 40 values: 36 H/S/L at −7…+7, contrast at −2…+2,
and highlights/midtones/shadows at −7…+7. Uploads target COLOR1–3 in PASM bank 0.
They do not select a front-dial mode, change WB mode or exposure compensation,
or directly overwrite saved C1–C4 banks. WB offsets are not in this receiver's
qualified write set.

## Application and persistence

Parser `60aa2656` forwards marked writes through the pending ID/type/value record.
`60aa4e7b` posts event `041b0011`; application receiver `608061b8` reaches normal
setting machinery, including `607ab8fd`. H/L uses the same persistent cells,
publication and profile refresh as the editor.

Physical tests verify readback, normal capture, persistence after reboot and
restoration of a previous recipe. Other COLOR profiles remain unchanged in the
tested workflow. Session `rec`/`play` changes remote application state; the QR
connection screen may remain visible. Neither command is a demonstrated generic
save/commit instruction. Immediate readback alone is not a reboot test.

## Requests are serialized, but timeouts are ambiguous

The HTTP worker processes one request at a time. The application wait has a
timeout but no demonstrated cancellation of an already queued edit. Losing a
reply can therefore leave a value changed or a later edit pending. Blind retry
or automatic rollback can compound that uncertainty.

The [research client](../../../camera_client/README.md) snapshots values, writes only
differences, verifies the complete profile and stops on uncertain outcomes.
Its 50 ms request gap worked in the recorded hardware workflow. It requires
manual reconnection and readback reconciliation after an ambiguous write.

A native Android client can use this HTTP interface after joining camera Wi-Fi.
A public HTTPS webpage also faces cross-origin permissions, mixed-content and
private-network restrictions; the camera does not provide the browser response
headers needed for straightforward direct access. Firmware protocol reuse does
not remove those browser constraints.
