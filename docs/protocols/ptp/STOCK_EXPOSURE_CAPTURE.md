# Stock PTP exposure readback and capture

Physical observations on two unmodified cameras establish different results for
one standard ExposureTime request. E-M5 III in MTP rejected the property; E-M1 III
in its computer-control mode returned four bytes. Both rejected standard capture.
**Both model and USB mode differ:** this does not isolate the cause of the difference.

These observations complement the [OM-3 tethering research](../om-3/TETHERING.md);
they do not test its patch, private operations or initialization sequence. No custom
firmware or native emulator was involved. Preparation of this contribution was
AI-assisted; packet outcomes come from hardware logs, not generated test responses.

## Identity and mode

| Field | E-M5 III | E-M1 III |
| --- | --- | --- |
| On-body firmware | Owner reports 1.7 | Not obtained |
| PTP manufacturer/model | OLYMPUS / E-M5MarkIII | OLYMPUS / E-M1MarkIII |
| PTP DeviceVersion | 1.00 | 1.00 |
| Tested USB mode | MTP | Computer-and-camera control icon |
| USB VID:PID | 07b4:012f | 07b4:0130 |
| Advertised operations / properties | 20 / 5 | 43 / 301 |
| ExposureTime 0x500D advertised | No | No |
| InitiateCapture 0x100E advertised | No | No |

DeviceVersion is a protocol string, not an independently verified installed firmware
release. Internal build and installed-image hash were **not obtained** for either
body. No firmware-file hash is substituted for a camera's installed-image identity.
The evidence uses PTP wire fields, not firmware file offsets or runtime addresses.

The E-M1 III initially enumerated as 07b4:0135 with PC RAW selected; no PTP experiment
was performed in that mode. The owner then selected the separate computer-and-camera
icon, below PC RAW and above USB PD, and fresh descriptors showed 07b4:0130. See the
[exact-model manual](https://download.omsystem.com/pages/inst/em1m3/manual_em1m3_ENU.pdf),
printed pages 231 and 275–276. PC RAW must not be assumed to mean camera control.
Use the camera's OK button to confirm the selection; stop if the menu differs.

Both tested interfaces were configuration1/interface0/alternate0, class6/subclass1/
protocol1, bulk OUT05 and IN86 (512-byte maximum packets), interrupt IN83 (64 bytes,
interval6). These are decoded descriptor observations, not an independent raw
USB-descriptor capture. A reproducer must inspect its device rather than assume them.

## Session, property and capture results

Three separate runs were made on 8 November 2026. Hexadecimal operation/response
codes and parameters below correspond to the retained packet excerpts.

| Run | Exact outgoing PTP sequence (transaction ID; parameters) | Outcome |
| --- | --- | --- |
| E-M5 MTP session/capture | GetDeviceInfo1001 (0; none), OpenSession1002 (0;20261108), InitiateCapture100E (1;0,0), CloseSession1003 (2;none) | DeviceInfo189-byte dataset/2001; open2001; capture2005; close2001 |
| E-M5 MTP ExposureTime | OpenSession1002 (0;20261109), GetDevicePropValue1015 (1;500D), CloseSession1003 (2;none) | open2001; empty data then200A; close2001 |
| E-M1 control comparison | GetDeviceInfo1001 (0;none), OpenSession1002 (0;2026110A), GetDevicePropValue1015 (1;500D), InitiateCapture100E (2;0,0), CloseSession1003 (3;none) | DeviceInfo847-byte dataset/2001; open2001; data28000000/2001; capture2005; close2001 |

Session identifiers above are arbitrary nonzero test values. GetDeviceInfo was not
repeated in the separate E-M5 property run. No other PTP operations were sent: no
property descriptor query, SET, event polling, autofocus, vendor/debug/memory command,
object enumeration/transfer/deletion or firmware update. Standard USB descriptor
requests were used for selection; they are separate from this PTP operation list.

The identical ExposureTime command in both property runs was:

```text
1000000001001510010000000d500000
```

E-M5 data/response:

```text
0c0000000200151001000000
0c00000003000a2001000000
```

E-M1 data/response:

```text
10000000020015100100000028000000
0c0000000300012001000000
```

200A is DevicePropNotSupported; 2005 is OperationNotSupported; 2001 is OK. E-M5's
empty data is not a zero shutter value. E-M1's four payload bytes decode as
little-endian uint32 **40**. No property descriptor or on-body shutter-speed comparison
was obtained, so this report assigns no verified duration or physical exposure units.

All three runs had confirmed successful CloseSession and interface release(return0),
with no timeout, uncertain transfer, retry, device reset or driver detachment. Normal
program exit meant transport/cleanup completed, not GET or capture success. No process
was killed and no service/configuration changes were made. In the E-M5 baseline the
owner quit Photos before acquisition; later claims succeeded without an observed
ownership conflict. No proof of every background application's inactivity is claimed.

## Manual observations and their limits

E-M5 MTP: before and during the session, the owner reported a black screen with a
battery indicator. After closure, the owner reported that buttons did nothing;
individual buttons/MENU were not enumerated. No SD-card inspection was performed
for that run. There were no new control observations for the separate brief GET run.

E-M1 control: initially a black screen with “One moment”; that text cleared during
the experiment, but the final screen remained black. No shutter action was heard or
seen. The owner later checked silent mode was off and found no new pictures on the
SD card. This is owner-reported inspection, not host-side enumeration or an exhaustive
file audit. Ordinary-control responsiveness and displayed shutter speed were not
separately confirmed. Manual mode was reported; exact speed/flash state was not verified.

Neither session success nor the display observations establish useful live view or
concurrent shooting. Capture was explicitly rejected, not merely inaudible. Standard
capture rejection does not disprove Olympus-specific tethering support. Unadvertised
E-M1 property success does not imply E-M5 compatibility, safe concurrent settings
access, SET support, custom firmware acceptance or recovery safety.

## Evidence and redaction

[Packet excerpts](../../../analysis/ptp-stock-hardware.json) retain all command and
response containers and the ExposureTime data containers unchanged. Complete serial-
bearing DeviceInfo data containers are omitted and explicitly marked, not rewritten.
Selected decoded identity/version/advertisement fields are retained separately.
No edited packet is represented as byte-for-byte raw; these are host-log excerpts,
not a complete USB bus capture. [Provenance](../../../provenance/stock-usb-hardware.json)
describes redaction and gives the sanitized artifact hash. Original logs, serials,
UTF-16 identity datasets, private paths/hostnames, OS/process inventories and images
are not submitted. Original-source hashes are retained privately, not published as
potential identifier oracles. The raw40 value is the deliberately scoped GET result.

## Reproduction procedure (hardware opt-in)

The original host transport was compiled C11 with Apple clang21.0.0 and existing
libusb1.0.29 on macOS27.0.1/arm64. It used libusb directly; no auto-discovery routine
that sends extra PTP commands was used. No vendor library or modified firmware is
required for the tested protocol operations. The private runners are not included:
they contain device-specific identifiers and operator orchestration. This first
contribution supplies packet-level instructions, not a new general-purpose driver.

Implement/run this sequence only through a separately reviewed host transport, with
explicit human opt-in. Session changes are transient camera state changes; optional
capture can expose the sensor, fire flash or write the card on a device that accepts
it. This is **not an entirely passive experiment**. For capture, first verify a short
ordinary exposure, flash off, single-shot drive, no bracket/interval/Bulb/Time sequence,
and a safely aimed camera. Do not rely on the earlier operator's uncertainty.

1. Record on-body firmware and mode manually. Choose MTP on E-M5 III or the separate
   computer-control icon on E-M1 III; do not switch modes automatically. Record display,
   MENU/control response and displayed shutter if available without changing settings.
2. Check for imports/transfers and interface ownership. Stop on a conflict; ask the
   operator to release the owning app. Do not kill/suppress services, detach drivers,
   reset USB, clear endpoint halts or change system configuration automatically.
3. Select by the expected VID/PID and a privately supplied expected serial, requiring
   exactly one matching camera. Verify identity before claim; never reuse a saved bus
   address or another model's serial. Keep serials/local logs private. Read standard
   descriptors, validate current interface/alternate and discover endpoints. Unexpected
   layout or claim failure means stop, not force acquisition/configuration changes.
4. Send exactly the chosen row's sequence. Use nonzero OpenSession ID and track whether
   this process received2001. A pre-existing/session-already-open response does not grant
   ownership. For the E-M1 comparison, send the single500D GET even if unadvertised.
   Capture is separately opt-in and at most once; omit it for a GET-only run and record
   the resulting sequence change. Do not enumerate images to confirm capture.
5. Use 3-second write timeouts and a 5-second total deadline per complete response
   phase, a64KiB buffer cap and at most32 receive fragments. Handle fragmented/combined
   containers; validate declared length, container type, operation for data, transaction
   ID and response parameters. Successful DeviceInfo/GET requires its data container.
   Log complete raw containers and decoded responses; sanitize before sharing.
6. After OpenSession, coordinate a bounded observation window with the operator:
   original E-M5 capture run used30 seconds; E-M1 used20 seconds before capture.
   No commands run during the window. If capture is accepted, distinguish acceptance,
   observed action and confirmed file creation; original runner allowed10 seconds to
   observe acceptance. Never automatically retry capture or an uncertain session change.
7. On a known protocol rejection with synchronized transport, close only the session
   successfully opened by this process. On timeout, partial write, mismatched transaction
   or other uncertain stream, stop further commands (including unsafe closure), release
   the interface/handle and report closure unconfirmed. Always attempt interface release.
   Never issue a reset to manufacture a clean result. Record observations after release.

Expected outcomes for these exact observations are in the table; different firmware,
mode or state may differ. Do not broaden requests on a rejection. Existing fake-
transport tests exercised framing and failure handling before the recorded experiments;
they are host-code tests, not hardware readback evidence. This contribution has been
checked offline against retained logs; preparation did not repeat either camera test.

## Contribution terms

All contributor-held rights in this original contribution are dedicated under
[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/legalcode), without an
attribution requirement for our original material. The [scope notice](../../../provenance/stock-usb-hardware.json)
covers this original writing, our index addition, explanatory provenance and
sanitized evidence only. Existing upstream/community credits and AI-assistance
disclosure are retained. Pre-existing upstream and Olympus/third-party material
are not relicensed, and no rights over factual protocol values are asserted.
