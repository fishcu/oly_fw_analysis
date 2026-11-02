# OM-5 and OM-5 Mark II menu compatibility

Compared builds: OM-5 1.2/1200 (E144), update SHA-256 `a0c91f3ac7caaf0925b2af609e711183cf3b5982b3333224bcef26c0c5943d11`, and OM-5 Mark II 1.1/1100 (E148), `9de5d77e1d290fa2ed4ebc7d75cee0ed490befbc89566722467d1d421d66d637`. Evidence is static inspection and modified OM-Emu execution, using upstream revision `96288adaa88af90c3134ae6326a49e09fb5cd34b` with local model-mapping corrections and host-side experiments. The private lab harness is not included here. No firmware was installed and no physical camera was tested.

The E144 application uses the older Menu_Viewer framework; E148 uses ListMenu. Both stock images reached shooting and playback in the high-level emulator, which supplies simulated devices and starts at application/kernel level. This does not demonstrate reset boot, updater acceptance, sensor/ISP behavior or compatibility with the other model's hardware. The two five-component update files have corresponding kinds in the same order but all corresponding decoded component hashes differ. Shared processor family or container layout is not evidence of interchangeable updates.

## Same ID does not imply the same value domain

In separate native menu sessions, Image Aspect used ID 269 on both models; the observed choices 4:3 and 16:9 read back as 1 and 3. A host transferred the integer 3 to an independent E144 session and called its native settings API. This did not execute E148 menu code in E144 or prove a general ABI.

Image Review is a counterexample. Both use ID 19, but the E144 descriptor includes value 60 while the E148 descriptor omits it. In a synthetic E148 RAM fixture seeded with `19=60`, opening the E148 selector highlighted Auto; confirming wrote `19=255`. A supported-value control remained unchanged. A host-side preflight detected the unsupported value and preserved it; it was not integrated into a camera menu.

E144's native menu also accepted REC-button assignment `48=1681` for Live ND. E148's REC assignment descriptor omits 1681. When synthetic E148 RAM was seeded with that value, opening its menu wrote `48=44` in four initial-tab fixtures, before the assignment screen was confirmed. A supported `48=44` control remained unchanged. A separate host guard preserved the E144 value by refusing the hypothetical handoff. The experiment models a foreign setting in a modified emulator; it is not an actual menu transplant or a physical-camera result.

These examples show why compatibility checks must cover value domains and initialization side effects, not only numeric IDs. Matching values still need semantic and persistence validation. The experiments tested a small selected set, not the complete menu.

## Existing functionality and remaining limits

On E144, a host-driven emulator experiment navigated the stock UI to switch Live ND on and off in M mode. The native menu already offers Live ND as a REC-button assignment; the tested REC event reached a filter but did not trigger the action in that emulator session. A multi-function shortcut or menu port was not implemented. Display composition required a host-only plane-order change; actual hardware priority is unknown.

A full transplant would need model-specific resources, callbacks, settings, events, hardware interfaces and camera-specific data reconciled. Update authentication, calibration preservation and recovery are not established. These observations do not prove either feasibility or impossibility of a port.
