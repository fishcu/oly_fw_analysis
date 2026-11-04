# E-M10 I image-processing extensions

These findings come from [cmdada's E-M10 I 1.4 work](https://www.mu-43.com/threads/modified-firmware-looking-for-users.99804/post-1886273)
and [pinned plugin source](https://github.com/cmdada/em10-fw/tree/6adb3bef36239859ae3fcd94b0dbb7db6de6ffa1/plugins).
Source inspection supports the design; physical effect and performance results
remain the author's reports.

## Getting an editable image buffer

The author reports that ordinary stills normally use a direct Bayer-to-JPEG
job, without a complete YCC image in CPU-accessible memory. Their software
plugins borrow the e-Portrait route to obtain that intermediate image.

The source hooks the route selector at `7DE46534`, forces the intermediate
only when a software plugin is active, and skips face detection and skin
correction for that forced route. Ordinary e-Portrait retains its own behavior.
Hooks around `rec_ImgPro_Bayer2Ycc` (`7DE40DFB`) and `rec_ImgPro_Ycc2Jpeg`
(`7DE40EF9`) then run raw/YCC callbacks before encoding.

The YCC source descriptor identifies interleaved format `0302`:
`Y0 Cb Y1 Cr`, with pitch `2 × MemHw`. The loader checks format and word
alignment and flushes caches around software processing. The source also
supports distributing row work across the three CPU cores.

The author reports roughly 3.2 seconds for raw monochrome and up to 16 seconds
for heavier effects on a full-resolution image. This supports intermediate
buffer processing as a possibility, but not its suitability for live view or
fast continuous shooting.

## Hardware colour key

An unused art-filter entry, number 114, led to five words in the YC register
image. The `HWKEY` experiment and `HWCOL` plugin use them for selective colour:

| Word index | Reported meaning |
| --- | --- |
| `4B` | Y range, low and high bounds |
| `4C` | Cb range |
| `4D` | Cr range |
| `4E` | Replacement Y/Cb/Cr value |
| `4F` | Enable `4`, invert selection `2`, preserve luma `1` |

Mode `7` replaces chroma outside the selected window while retaining luma.
The author reports this working in live view and captured images. Source
confirms those writes and handles disabling the previously applied key; exact
ISP semantics have not been independently measured here. This is a rectangular
YCbCr selection, not a twelve-sector HSL editor or a spatial brightness combiner.

## Other limits

No equivalent of PEN-F's COLOR application path has been demonstrated on this
model. Missing UI strings do not prove that its ISP lacks related capabilities.

The focus-bracketing plugin reaches a low-level lens request in the emulator,
but the author reports that the real lens does not move. It is not working
focus stacking. The movie-limit operand is independently confirmed, but the
longer remaining-time display does not establish file splitting or recording
beyond storage limits.

The useful general technique is to reuse a stock path that already allocates
an intermediate image, then establish its lifetime, format and cache handling.
This is relevant to [PEN-F's processing jobs](../pen-f/CREATIVE_PROCESSING_JOBS.md),
without establishing identical buffers or hook locations.
