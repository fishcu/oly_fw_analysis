# OM System OM-3 1.1: firmware findings and feature opportunities

Research snapshot: 31 October 2026. This is static analysis of the downloaded update, not a test on a connected camera. No modified image has been installed. The most promising findings are a twelve-sector color-processing path, a substantial remote-control interface, and an architecture that separates the camera application from Linux services through an interprocessor messaging interface.

Follow-up: [the focused Human-detection analysis](HUMAN-DETECTION-ANALYSIS.md) now traces the Human-selected learned-data bank, image interface, candidate processing and AF handoff, with explicit remaining gaps.

## Scope and strength of the evidence

The original image is `OLY_E_147_1100_0000_0000.BIN`, 240,517,120 bytes, SHA-256 `8c133084414533159f587bf46bfb4152714c4074312a47c8d8503e33d605696d`. The vendor catalog identifies it as the OM-3 1.1 update. The `E1479999.BIN` name discussed earlier is an alternate installation filename; a filename alone does not establish different contents.

All six decoded components passed their checksums, matched the pinned reference inventory, and survived a byte-identical decode/re-encode round trip. This establishes that we can understand and reproduce this update container. It does **not** establish that an altered image will pass every boot or update check.

The authoritative inventory contains 244 exported programs: the main camera application, a small secondary firmware, the Linux kernel, and 241 Linux ELF inputs including the vDSO. Ghidra identified 187,717 function candidates and emitted C for 187,179; 538 failed and 42,322 completed with warnings or diagnostics. These are decompiler outcomes, not counts of understood or verified functions.

For this review I scanned all 244 authoritative C exports and the decoded string corpus, then manually followed selected startup, CGI, IPC, remote-control, numerical-processing, power and color paths. I did **not** manually verify all 187,179 C outputs. The scan covers roughly 228 MB of generated C; 60,098 candidates have bodies of 16 bytes or less. Tiny helpers, import thunks, mistaken boundaries and ordinary small functions all contribute to that number.

The main MN10300-family application is the weakest part of the decompilation. Of 98,885 candidates, 98,356 produced C, but 53,312 contain unrecovered register inputs, 6,577 contain opaque user-defined operations and 5,960 contain bad stack-base indicators. Those flags overlap. The community processor module gives us useful disassembly, but its default calling convention is not a verified match for this camera.

A concrete example is the COLOR1 routine at `0x604037f9`: the assembly loads setting IDs `0x38c` and `0x388` into A0 before calling the getter at `0x603f34ec`. The C loses these arguments and includes implausible state/register expressions. Editing based only on that C would be unreliable. Assembly and original bytes must arbitrate.

Sources: [authoritative export inventory](analysis/decompilation-index.json), [corpus review](analysis/review/corpus-review.json), [COLOR1 C](analysis/decompiled-main/functions/604037f9.c), [main assembly](analysis/decompiled-main/all-functions.asm). Topic keyword hits were used to find leads, not to measure feature prevalence.

## 1. The camera contains several cooperating execution environments

**Observed:** the main application decodes as MN10300-family code, with the examined image mapped at `0x60021020`. That differs from its update-container payload address `0x50000020`; confusing the two would invalidate cross-references. The secondary 0107 component contains Cortex-M code and battery/power-related source-path strings. The resource component contains an AArch64 Linux kernel, a SquashFS root filesystem and a vDSO. Linux userspace includes 32-bit ARM executables and shared libraries.

The embedded kernel identifies itself as Linux 4.14.222, built with GCC 7.5 in February 2025. I recovered 17,987 kallsyms entries into a symbolized ELF. The recovered `stext` address agrees with the ARM64 Image header's entry branch, which is a useful independent mapping check. This makes much of Linux easier to navigate than the stripped camera application. A version banner alone is not proof that a particular upstream bug is reachable or unpatched.

**Observed:** boot scripts load `iscdrv.ko`, create `/dev/isc`, and launch `sccore`, `dbgterm_server` and `hhhr`. Wi-Fi startup launches lighttpd and multiple ISC/network bridge processes. Bluetooth uses a BSA stack and a separate `blebridge` process.

**Interpretation:** there are useful boundaries between Linux services, camera control and secondary power-related firmware. These may be different cores inside a system-on-chip; the files do not by themselves prove separate physical chips. Linux is more than a file server, but it would also be wrong to assume that all image processing or camera state lives there.

This matters because adding a Linux daemon would not automatically give it shutter, autofocus or image-pipeline access. We would need to understand the existing message protocol and state ownership. Conversely, a host-side program can reuse existing services without first replacing the camera application.

Sources: [ISC startup](analysis/embedded/rootfs/etc/init.d/S20isc), [camera service startup](analysis/embedded/rootfs/etc/init.d/S99oly), [Wi-Fi startup](analysis/embedded/rootfs/etc/init.d/wifi), [kernel mapping validation](analysis/embedded/kernel-symbol-validation.json), [secondary reset handler](analysis/decompiled-scpu/functions/080253d8.c).

## 2. Network control crosses a real message bridge

The web-server configuration maps CGI requests to `isc_cgi` and supported media extensions to `isc_file`. This is backed by executable behavior, not just suggestive filenames.

The CGI main loop reads the request URI, method, length, content type and remote address. A helper allocates a `0x3444` request structure, attaches shared memory, copies request information, performs cache operations and sends an ISC message. Diagnostic strings describe asking the application manager and receiving its reply. The bridge uses a request channel and a separate reply channel.

That gives us a concrete architecture: **HTTP request → Linux CGI frontend → shared memory / ISC → camera application → response**. Reimplementing only the HTTP side does not reveal all the rules enforced deeper in the camera. Authentication, pairing, current mode, recording state and allowed parameter ranges remain runtime questions.

The extracted OI.Share description advertises version 5.30 and 61 CGI commands. It includes remote control, GPS, movie streaming, firmware-related operations, settings backup and camera logs. The writable `set_camprop` list is much narrower than the full settings-name corpus: it advertises eight names, including exposure mode, drive mode, aperture, exposure compensation, shutter speed, ISO, white balance and movie exposure. It does not advertise arbitrary numeric setting writes or a generic way to change every COLOR coefficient.

Other advertised requests cover autofocus points, still/movie start and stop, live-view start and stop, image review, zoom and near/far focus movement. `wifi_remocon` also contains UDP sending and packetization logic, with sequence handling and bounded packet sizes. This is useful for reconstructing transport. It is not proof of RTSP, a particular freely selectable bitrate or a new video mode.

`sccore` has startup handshakes, service-control dispatch and an ARM survival-inquiry heartbeat. That suggests a remote application needs careful session and reconnect handling, not merely a list of URLs.

Sources: [CGI request loop](analysis/decompiled-linux/var__www__fcgi-bin__isc_cgi/functions/00011988.c), [shared-memory request bridge](analysis/decompiled-linux/var__www__fcgi-bin__isc_cgi/functions/0001119c.c), [web routing](analysis/embedded/rootfs/etc/lighttpd/conf.d/fastcgi.conf), [advertised command description](analysis/observations/oishare-description.xml), [remote UDP sender](analysis/decompiled-linux/usr__bin__wifi_remocon/functions/00011370.c), [service heartbeat](analysis/decompiled-linux/usr__bin__sccore/functions/00010d88.c).

## 3. Color processing is the strongest firmware-extension lead

The existing interface already has four COLOR profiles, per-color saturation, shading and highlight/shadow controls. These are documented features, not discoveries of hidden functionality. The interesting question is whether the underlying per-sector processing can do more than the menu exposes.

The examined OM-3 path has four profile-specific settings branches, a common settings getter, a coefficient builder and a writer that copies twelve records of 24 bytes toward image-processing register banks. The builder has nested 2-by-6 loops and per-sector gain data. It forwards additional coefficient fields alongside the saturation-related data. The decoded OM-3 bytes contain those records and tables; this is not merely a transplant of a PEN-F address map.

Important landmarks are the getter at `0x603f34ec`, profile branches beginning at `0x604037f9`, `0x6040391a`, `0x60403a3b`, and `0x60403b5c`, coefficient builder `0x60518381`, selector `0x60518573`, gains table `0x606d413c`, and writer `0x604a3e73`. The writer handles a 288-byte twelve-record span and a control field. A gate bit controls whether the full span is copied.

The reference research provides a hue/saturation/lightness-like interpretation for parts of these records, developed partly through PEN-F work. Our OM-3 tracing strengthens the case that related plumbing exists here. It does **not** yet establish the visual meaning, units, signedness, safe range, or complete activation conditions of every OM-3 field. Some multiply operations still have opaque decompiler semantics.

**Best theory:** independent hue and lightness adjustments for each of twelve color sectors may be possible by extending the existing processing path. That would offer more precise film recipes, selective skin-tone handling, foliage changes and separation of neighboring colors than global color adjustment alone.

Making that a usable feature requires more than changing a coefficient: persistent storage, UI controls, live-view and capture consistency, profile recall, initialization and reload handling, and output validation all need work. We must test neutral settings, ramps and color targets to check clipping, discontinuities and interactions with contrast, white balance and other picture controls.

There is **no established arbitrary 3D-LUT or .cube import path**. A table or pointer called a LUT is not enough to prove a general-purpose 3D-LUT engine. Twelve-sector controls and arbitrary 3D transforms are different capabilities.

Sources: [OM-3 byte-level color evidence](analysis/review/color-byte-evidence.json), [coefficient builder](analysis/decompiled-main/functions/60518381.c), [record writer](analysis/decompiled-main/functions/604a3e73.c), [writer caller](analysis/decompiled-main/functions/604a3525.c). The caller has stack-recovery problems; consult its assembly before interpreting operands.

## 4. Settings labels reveal a shared platform, not 2,915 unlocked settings

I identified 2,915 contiguous fixed-width setting-label slots in the resource component. They cover color, focus, bracketing, subject tracking, battery and other subsystems. Earlier work cross-checked 48 saturation label/ID slots and the four profile defaults.

This is a valuable vocabulary for locating handlers and reconstructing structures. It is not a complete setting API or a proof that all entries are active on the OM-3. For example, a battery-use-order label exists even though this model's battery arrangement does not make that a new user feature. Shared firmware families retain labels and dormant infrastructure for other products.

An interesting next step is a settings schema with verified types, ranges, defaults, persistence locations and model-specific availability. Until then, automatically writing values based on these labels would be guesswork.

Source: [setting-name candidates and provenance](analysis/review/setting-name-candidates.json).

## 5. Other leads and their limits

**Numerical processing:** `hhhr` starts at boot and contains matrix operations, double-precision math and ISC communication. The name suggests a possible high-resolution relationship, but I have not established the algorithm's identity or its role in the full capture pipeline. This is a lead for investigating offloaded numerical work, not proof that changing one limit will enable a higher-resolution shooting mode.

**Power and diagnostics:** the secondary image contains battery-information, battery-temperature and power-supply task strings. This supports a battery/power responsibility. I have not traced a safe user-facing telemetry API or the camera's full thermal protection logic. Wireless calibration files named `thermal.txt` are not evidence of sensor overheating thresholds. Battery diagnostics and sensor temperature must be kept distinct.

**Bluetooth:** BSA/GATT calls confirm a structured BLE service implementation. They do not show that arbitrary Bluetooth profiles or audio support can be added. Service definitions, application messages and hardware capability still need investigation.

**Boot/debug configuration:** a console shell and debug-related services appear in the extracted environment. That is useful architecture evidence; it is not evidence of an accessible remote shell. No network exposure or exploitability has been demonstrated.

Sources: [numerical routine](analysis/decompiled-linux/usr__bin__hhhr/functions/00010988.c), [BLE bridge export](analysis/decompiled-linux/usr__bin__blebridge/all-functions.c), [init configuration](analysis/embedded/rootfs/etc/inittab), [wireless firmware/configuration references](analysis/decompiled-linux/usr__bin__isc_olnet/functions/000137f4.c).

## 6. What we could build, in a practical order

### A. A desktop recipe library and settings comparison tool

This is the best first deliverable. It could organize named recipes, show what differs between backups, keep descriptions and example images, and maintain an external library larger than the camera's onboard profile count. The firmware advertises chunked settings-backup and restore operations, including names and size/state requests.

The first version should inspect backups offline. We still need the actual backup format, version compatibility, checksums and camera-specific fields before proposing a safe editor or restore workflow. An advertised backup interface does not establish selective COLOR-profile import. Existing C1–C5 modes and COLOR1–4 should be represented accurately rather than advertised as newly added features.

### B. A desktop Wi-Fi remote and capture-workflow application

The existing protocol makes a desktop interface with live view, capture controls, image review and clearer reconnect behavior plausible. A sequencer could coordinate exposure changes, timed capture and supported focus movements, attach metadata and organize resulting files.

The benefit would be workflow and orchestration: the camera already has interval shooting, focus bracketing and focus stacking. More ambitious sequences depend on which controls work together in each state. Focus-step repeatability, autofocus transitions, error responses, command timing and image-transfer behavior need stock-camera measurements.

### C. Twelve-sector hue and lightness controls

This is my preferred actual firmware research target. It has a traced coefficient path, rather than only a suggestive string. Start with a single controlled coefficient experiment after repairing the calling convention and establishing recovery. Confirm its pixel effect before designing a menu.

The potential payoff is high; implementation readiness is still limited. It might require changes at several layers, and some fields may have different meanings or activation requirements than we currently infer.

### D. More convenient profile switching and customization

Richer profile names, faster recipe switching and additional assignable actions are plausible ideas. External recipe storage is easier to justify than increasing the internal number of slots. Internal slot counts may be embedded in allocation sizes, menus, serialization and validation. A shared settings label does not prove the relevant control exists on this body.

### E. USB still tethering and expanded USB controls

The stock manual documents storage, MTP, webcam and USB RAW processing. It does not document the desktop still-tether workflow we would want. The reference repository records a community OM-3 tethering patch and contributor reports of USB live view. That makes this a credible research direction, but we have not reproduced it locally and do not have a complete independently tested recovery history.

The useful task is to identify the USB mode selection, descriptors, handshake, application dispatch and state restrictions in our exact image. A community patch is evidence of possibility, not a ready-to-install recommendation.

### F. Better diagnostics and status handling

A host tool could collect supported logs, explain connection failures and expose verified status fields. Existing log commands and IPC heartbeats provide starting points. Additional battery or temperature displays require identification of actual telemetry and units. We should not infer a sensor-temperature API from unrelated thermal files.

### G. Webcam improvements

The official manual specifies 1280×720 webcam output at 30p or 25p and lists restrictions, including computer-side exposure changes. Studying whether a restriction is a mode guard or a deeper pipeline limit is worthwhile. Higher resolution needs a suitable USB descriptor, encoder path, throughput, buffering and operating-state support. The ability to record high-resolution video to a card does not establish that the USB webcam path can carry it.

### H. Focus-stack and high-resolution processing experiments

Potential investigations include stack controls, lens compatibility rules, merge parameters and numerical offload behavior. These are substantial projects. No verified OM-3 lens allowlist branch, full merge pipeline or extra computational budget has been established. They should follow the more tractable protocol and color work.

## 7. Claims the evidence does not support

I cannot currently promise RAW video, 4K120, 16-bit RAW, new subject-recognition classes, unlimited burst depth, faster autofocus, arbitrary 3D-LUT import, or a new high-resolution mode. These may depend on sensor readout, image-processing hardware, memory bandwidth, accelerator interfaces, trained models and timing constraints that the current analysis does not resolve.

Nor do we have the original source project. Generated C is a reverse-engineering aid; it cannot simply be compiled into a replacement firmware. A small verified patch is a different engineering task from rebuilding the complete camera operating environment.

## 8. Recommended next research sequence

1. **Improve the main application's analysis foundation.** Model the camera calling convention, verify selected function boundaries, decode relevant opaque instructions and define settings/ISC structures. Re-decompile the focused color and control paths rather than blindly trusting the current bulk output.
2. **Specify the protocol and backup formats.** Turn the advertised command list into a stateful protocol map. Document proven read/write fields separately from label candidates. Build an offline backup inspector and recipe catalog first.
3. **Establish stock-camera baselines in a separate authorized hardware phase.** Capture capabilities, backup files and normal responses. Compare controlled images using the existing COLOR settings; USB RAW processing may help with repeatable supported-image comparisons. No such camera interaction occurred in this review.
4. **Investigate the full-sector color path.** Trace initialization, activation gates, preview/capture branches and persistence. Establish a recovery method and boot/update checks before attempting a modified image.
5. **Consider USB and deeper processing work after those results.** Keep each experiment small enough that its visual or behavioral effect can be isolated.

The image's reversible encoding and additive checksums make container experiments straightforward, but they do not settle boot authentication. Similarly, runs of `0xff` are not automatically safe executable space: overlays or runtime reloads can overwrite code and state. These are concrete unresolved engineering requirements, not reasons to stop researching.

## Sources and reproducibility

Local findings refer to the original image and artifacts under `C:\Dev\OM3-research`. The bulk export inventory excludes superseded case-collision exports; eighteen affected Linux files were extracted to unique paths and reanalyzed. Their original paths and hashes are retained in the extraction manifests.

The reference research is [fishcu/oly_fw_analysis](https://github.com/fishcu/oly_fw_analysis), pinned locally at commit `539fcf1fa9eda5fdef8ede4deeab94a4691d94c3`. Its PEN-F findings and contributor-reported OM-3 patches are prior work, not local runtime confirmations. See [historical patch notes](reference/docs/features/HISTORICAL_HACKS.md), [code-space notes](reference/docs/safety/CODE_SPACE.md), and [container notes](reference/docs/format/CONTAINERS.md).

Existing camera features and webcam restrictions were checked against the [official OM-3 manual](https://download.omsystem.com/pages/inst/om3/manual_om3_ENU.pdf): printed pages 225, 254–255, 264 onward, 282, and 442–444 are particularly relevant. A local copy and extracted text are retained in `reference`. Feature assessments are also provided as [structured data](analysis/review/feature-assessment.json) and an interactive findings view.
