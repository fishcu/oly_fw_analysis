# External references

These sources provide historical tools, specifications and independent reports.
A forum report is attributed evidence, not a substitute for a reproducible trace.
Archived links identify the cited snapshot; they are not a claim of continued
availability at the original host.

## Firmware and prior research

- [OM System firmware catalog](https://fw01.om-digitalsolutions.net/ww_inform/fcache.do):
  Workspace XML endpoint; see `tools/om_firmware_catalog.py` for request structure.
- [Firmware model/name spreadsheet](https://docs.google.com/spreadsheets/d/10vaBZZrfVLeotlAjfGy5Vo_qtelXevRkdPMBd-VN53k/edit):
  camera codes and update filenames. Michael Selig's download script uses the same
  public catalog; its installed-version field is not a historical-version selector.
- [Altsoph/mx3 container research](https://chdk.setepontos.com/d/2471-olympus-emjustylus-series-fw-analysis):
  Olympus payload transform and component analysis.
- [E-P1/E-P2/E-PL1 research](https://www.dvxuser.com/threads/e-p1-e-p2-e-pl1-hack-research.217453/).
- [Personal View Olympus thread, archived](https://web.archive.org/web/20240612213726/https://www.personal-view.com/talks/discussion/2789/olympus-hacks/p2/1000).
- [Jove's Olympus files, archived](https://web.archive.org/web/20200924133915/https://linda.karlov.mff.cuni.cz/~jove/oly/):
  historical tools and USB capture reference.
- [LightSnowDev camera documentation, archived](https://web.archive.org/web/20190818064449/https://lightsnowdev.com/blog/olympus-camera-documentation/#more-210).
- [xdel Olympus collection](http://xdel.ru/downloads/olympus-firmware/): stock,
  modified firmware and historical tools. Hashes distinguish duplicate mirrors.
- [OM-3 V22 patcher by kred](https://mega.nz/folder/XXoFAJzY#CJLgZ0b_NDBfFnOjJVDbQQ):
  USB live-view/tethering source and patch manifest. The inspected archive SHA-256 is
  `8f2fbaca454bca581e4e9e6561ac2341590bf7be4301ac7351660f1e00647131`;
  manifest SHA-256 is
  `8f520edb97995c7b5de3b43da725b33bff9a5f1ddb52d31d439a01609369505e`.
- [kred's OM-3 tethering explanation, October 20, 2026](https://www.mu-43.com/threads/modified-firmware-looking-for-users.99804/page-34#post-1886195):
  V22 startup, live-view and transfer explanation. The supplied README SHA-256 is
  `0e5c238cebc23b1f5d1f01ddd54c6122a8b70a2e99d142ee86fbc85b39408440`.
  See the [verified protocol reference](../docs/protocols/om-3/TETHERING.md) and
  [source/date qualifications](community-reports.json).

## Manuals and interfaces

- [PEN-F manual and firmware supplements](https://download.omsystem.com/pages/inst/penf/manual_penf_ENU.pdf).
- [OM System flash compatibility](https://support.jp.omsystem.com/en/support/imsg/digicamera/compati/pen_flashes.html).
- [E-P7 uncovered hotshoe photograph](https://i.ebayimg.com/images/g/THAAAeSwumFoiLRm/s-l1600.jpg),
  from [the associated listing](https://www.ebay.com/itm/286736797711): visual
  contact-layout evidence, not electrical measurements.
- [Independent Olympus Wi-Fi client](https://github.com/hotchpotch/olympus-camera):
  includes a PEN-F command-response example.
- [Microsoft SCSI pass-through interface](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntddscsi/ni-ntddscsi-ioctl_scsi_pass_through):
  host transport used by the inspected Windows update implementation.
- [HOS MN103 RTOS port, archived](https://web.archive.org/web/20161224050444/https://ja.osdn.net/projects/hos/scm/git/hos-v4a/tree/master/kernel/build/mn103/mn103s/):
  architecture context; not evidence that the camera runs this exact kernel.

## Reported recovery cases

- [cmdada's E-M10 I report](https://www.mu-43.com/threads/modified-firmware-looking-for-users.99804/post-1886273)
  and [later simulated bootloader overwrite](https://www.mu-43.com/threads/modified-firmware-looking-for-users.99804/post-1886391),
  October 21, 2026. [Source snapshot](https://github.com/cmdada/em10-fw/tree/6adb3bef36239859ae3fcd94b0dbb7db6de6ffa1)
  contains the plugin loader and main-entry system emulator, but not the later
  preboot simulator or original boot dumps. See the [qualified summary](../docs/boot/e-m10/RECOVERY.md)
  and [source identities](community-reports.json).
- [E-M1X recovery discussion](https://www.dpreview.com/forums/threads/how-to-fix-bricked-om-d-e-m1x.4707099/).
- [E-M5 recovery discussion](https://cameraderie.org/threads/e-m5-bricked-and-now-unbricked.60619/).

These reports describe successful recovery in particular failure states. They do
not identify PEN-F's reset code or prove that every failed main-image update is
recoverable. The [recovery reference](../docs/boot/pen-f/RECOVERY.md) separates those
reports from native updater evidence.

## Stock Wi-Fi debug access

- [Enduity's SD-file method](https://www.mu-43.com/threads/modified-firmware-looking-for-users.99804/post-1888641),
  November 1, 2026: reports an open Wi-Fi network and debug console on stock
  E-M5 III 1.7 using `PARAMDT/CP000001.CSV` and parameter `F971`.
- [Cmdada's startup-gate finding](https://www.mu-43.com/threads/modified-firmware-looking-for-users.99804/post-1886911),
  October 24, 2026: E-M10 debug parameter, stored network credentials and port-23
  shell; proposes forcing the getter with a one-byte firmware patch.
- [PhotoDmiK's F981 observation](https://www.mu-43.com/threads/modified-firmware-looking-for-users.99804/post-1888681),
  November 2, 2026: identifies a second nearby parameter. PEN-F code independently
  maps it to RAM diagnostic capture.

These posts were read from a supplied saved page, whose identity and exact
timestamps are recorded in [community-reports.json](community-reports.json).
The [debug reference](../docs/protocols/pen-f/WIFI_DEBUG.md) separates contributor
hardware reports from the stock-image and native-emulation checks.
