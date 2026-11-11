# Research reference

Start with the file format and address spaces. Then choose the subsystem relevant
to your camera or modification. Addresses refer to the stated build, not every
camera with the same processor.

| Topic | Reference |
| --- | --- |
| Update files | [Components, decoding and checksums](format/CONTAINERS.md) · [Address spaces and section loading](format/pen-f/ADDRESS_SPACES.md) · [E-M5 III sections and boot order](format/e-m5-iii/ADDRESS_SPACES.md) |
| Startup and recovery | [Startup structure](boot/pen-f/STARTUP.md) · [SD update and recovery limits](boot/pen-f/RECOVERY.md) · [Flash readers](boot/pen-f/FLASH_READERS.md) · [Buttons and dials](boot/pen-f/INPUTS.md) · [E-M5 III update and recovery](boot/e-m5-iii/RECOVERY.md) |
| Camera interfaces | [USB firmware update](protocols/pen-f/USB_UPDATE.md) · [Settings backup](protocols/pen-f/SETTINGS_BACKUP.md) · [Wi-Fi settings](protocols/pen-f/WIFI.md) · [Stock SD debug switch and shell](protocols/pen-f/WIFI_DEBUG.md) |
| OM-3 tethering | [USB startup selectors, live view and image transfer](protocols/om-3/TETHERING.md) |
| E-M10 I research | [Boot and recovery](boot/e-m10/RECOVERY.md) · [SD plugins and system emulator](tooling/e-m10/PLUGINS.md) · [Image-processing extensions](color/e-m10/PROCESSING.md) |
| Color processing | [Modes and generations](color/MODES.md) · [HSL tables and scales](color/pen-f/HSL_TABLES.md) · [Processing jobs](color/pen-f/CREATIVE_PROCESSING_JOBS.md) |
| Profile integration | [Editor and display](color/pen-f/EDITOR.md) · [Saved settings](color/pen-f/SETTINGS_STORAGE.md) · [Per-image parameters](color/pen-f/CAPTURE_PARAMETERS.md) · [ORF metadata](color/pen-f/ORF_METADATA.md) |
| Other image effects | [Grain](color/pen-f/GRAIN.md) · [Sharpening](color/pen-f/SHARPENING.md) · [Creative shading](color/pen-f/SHADING.md) |
| Other camera features | [Silent burst and Pro Capture](features/om-5/BURST.md) · [Panasonic aperture rings](features/pen-f/APERTURE_RING.md) · [External flash](features/FLASH.md) · [Published firmware hacks](features/HISTORICAL_HACKS.md) · [E-M5 III Live ND (OM-5 merge)](features/e-m5-iii/LIVE_ND.md) |
| Image engine | [E-M5 III jobs, records and job tables by body](imaging/e-m5-iii/IMAGE_ENGINE_JOBS.md) |
| Modification techniques | [Code placement](safety/CODE_SPACE.md) · [Validation](safety/VALIDATION.md) · [Resource graphics](tooling/pen-f/RESOURCES.md) · [MN103 native-call harness](tooling/EMULATOR.md) · [Interactive om-emu](tooling/OM_EMU.md) · [PEN-F editor probe](tooling/pen-f/OM_EMU.md) |
| Source builds | [PEN-F HSL](../patches/hsl/pen-f/README.md) · [IDA/MN103 setup and automation](tooling/ida/README.md) · [Ghidra MN103 module](tooling/ghidra/README.md) |

For address-level PEN-F 3101 work, use the [startup function map](boot/pen-f/FUNCTION_MAP.md),
[settings and structure reference](color/pen-f/STRUCTURES.md), and
[edit-to-capture execution map](color/pen-f/EDIT_AND_CAPTURE_MAP.md).
These expand the shorter topic summaries with field offsets, calling contracts,
ownership and the limits of the execution evidence.

PEN-F build 3101 supplies most detailed function maps. E-M1 II and III, E-M5 II
and III, E-P7, OM-3 and OM-5 provide comparisons for particular subsystems.
Coverage is a set of bounded observations, not a complete firmware decompilation.

**Reading evidence:** “native execution” means original instructions executed in
an emulator, with the listed memory and hardware models. It does not mean a
physical camera ran that experiment. A desktop renderer can explain parameters
and pixel arithmetic without proving the camera ISP uses the same implementation.

Input identities are in [provenance](../provenance/README.md). The
[tool guide](../tools/README.md) identifies reproducible entry points and their
dependencies.
