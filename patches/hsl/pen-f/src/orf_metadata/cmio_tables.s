/* Copyright 2026 fishku (original contributions)
 * SPDX-License-Identifier: Apache-2.0
 * Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
 */
/* PEN-F 3101 HSL: orf metadata. */
/* Captured HSL -> native CMIO P coefficients; called by the metadata hook.
 * a0: 72-byte destination, a1: captured 12 packed H/L bytes,
 * d0: captured twelve signed-short S values, OES/wheel order.
 * CALL [d2,d3,a2,a3],36. Existing installed H/L lightness LUT is reused.
 * Invalid S outside -7..7 and reserved H/L nibble -8 become neutral.
 */
.text
.global cmio_capture_weights
cmio_capture_weights:
 mov a0,a2
 mov a1,(4,sp)
 mov d0,(8,sp)
 mov 0x60622d74,a3
 clr d3
cmio_weight_loop:
 /* Native record order -> wheel index, without a new mapping table. */
 mov d3,d2
 asl 1,d2
 cmp 12,d2
 bcs cmio_sector_ready
 add -11,d2
cmio_sector_ready:
 mov (8,sp),a0
 asl 1,d2
 movhu (d2,a0),d0
 exth d0
 mov d0,d1
 add 7,d1
 cmp 14,d1
 bls cmio_s_valid
 clr d0
cmio_s_valid:
 mov d0,(12,sp)
 mov d3,d1
 asl 2,d1
 mov 0x6062fef8,a0
 mov (d1,a0),a0
 cmp 0,d0
 bge cmio_positive_s
 add 2,a0
cmio_positive_s:
 movhu (a0),d1
 movhu (14,a3),d0
 exth d0
 mul d1,d0
 mov (12,sp),d1
 mul d1,d0
 mov 5,d1
 ext d0
 div d1,d0
 mov 256,d1
 ext d0
 div d1,d0
 movhu d0,(2,a2)

 asr 1,d2
 mov (4,sp),a0
 movbu (d2,a0),d0
 mov d0,d1
 asl 28,d0
 asr 28,d0
 cmp -8,d0
 bne cmio_h_valid
 clr d0
cmio_h_valid:
 mov -1000,d2
 mul d2,d0
 movhu d0,(a2)
 asl 24,d1
 asr 28,d1
 add 7,d1
 cmp 14,d1
 bls cmio_l_valid
 mov 7,d1
cmio_l_valid:
 asl 1,d1
 mov captured_lightness_lut,a0
 movhu (d1,a0),d0
 movhu d0,(4,a2)
 add 6,a2
 add 28,a3
 inc d3
 cmp 12,d3
 blt cmio_weight_loop
 ret [d2,d3,a2,a3],36
