/* Copyright 2026 fishku (original contributions)
 * SPDX-License-Identifier: Apache-2.0
 * Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
 */
/* PEN-F 3101 HSL: image parameters. */
/* PEN-F 3101 image-owned H/L reader: all 16 native operation records.
 * The corresponding constructor edits allocate/zero the 24-byte trailer.
 * Do not package this without qualifying the upstream producers/reuse path.
 */
.section .color_hook,"ax"
 jmp hl_override

.section .extension,"ax"
hl_override:
 call color_builder,[d2,d3,a2,a3],96
 /* Inline scratch frame preserves the builder's MDR as well as the GPRs.
  * A second CALL would replace MDR. Peak extra stack is 24 bytes, below
  * the preceding builder's now-released 96-byte frame.
  */
 add -24,sp
 mov d0,(0,sp)
 mov a0,(4,sp)
 mov a1,(8,sp)
 mov a2,(12,sp)
 mov a3,(16,sp)
 mov d2,(20,sp)
 mov (4,a2),a1
 mov (a1),d0
 cmp job_callback,d0
 bne hl_done
 /* Check the native embedded-request/owner relationship before dereference.
  * This is a type/layout check, not validation of an arbitrary pointer.
  */
 mov (4,a1),d0
 mov a1,a0
 add 1848,a0
 /* Native job has 16 records of 52 bytes. Match the address before reading.
  * These are operation bookkeeping slots, not sixteen parameter copies.
  */
 mov 16,d2
hl_find_record:
 cmp a0,d0
 beq hl_record_found
 add 52,a0
 add -1,d2
 bne hl_find_record
 bra hl_done
hl_record_found:
 mov (a0),d0
 mov a1,a0
 add -12228,a0
 cmp a0,d0
 bne hl_done
 mov (12,a2),a3
 add 0x2b6,a3
 mov a0,a2
 add 14920,a2
 clr d2
hl_loop:
 /* Native records are even OES indices first, then odd indices. Signed
  * bytes outside -7..7 become neutral before any table lookup.
  */
 movbu (a2),d0
 extb d0
 add 7,d0
 cmp 14,d0
 bls hue_valid
 mov 7,d0
hue_valid:
 add d0,d0
 mov hue_lut,a1
 movhu (d0,a1),d0
 movhu d0,(a3)
 movbu (12,a2),d0
 extb d0
 add 7,d0
 cmp 14,d0
 bls lightness_valid
 mov 7,d0
lightness_valid:
 add d0,d0
 mov lightness_lut,a1
 movhu (d0,a1),d0
 movhu d0,(4,a3)
 add 2,a2
 add 24,a3
 inc d2
 cmp 6,d2
 bne next_record
 add -11,a2
next_record:
 cmp 12,d2
 bne hl_loop
hl_done:
 mov (0,sp),d0
 mov (4,sp),a0
 mov (8,sp),a1
 mov (12,sp),a2
 mov (16,sp),a3
 mov (20,sp),d2
 add 24,sp
 jmp color_resume

.balign 2
hue_lut:
 .hword 7000,6000,5000,4000,3000,2000,1000,0,-1000,-2000,-3000,-4000,-5000,-6000,-7000
lightness_lut:
 .hword -300,-250,-200,-150,-100,-50,-25,0,25,50,100,150,200,250,300
