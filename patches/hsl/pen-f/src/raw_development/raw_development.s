/* Copyright 2026 fishku (original contributions)
 * SPDX-License-Identifier: Apache-2.0
 * Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
 */
/* PEN-F 3101 HSL: raw development. */
/* Snapshot current-profile H/L after RAW Data Edit prepares its parameters.
 * Same capture-owner pool and transport as normal recording; no allocation.
 * Hook is in play_edit_raw_set_exif_default, not the general RAW loader.
 */
.section .raw_acquire_hook,"ax"
 jmp hl_raw_acquire
 nop

.section .raw_acquire,"ax"
.global hl_raw_acquire
hl_raw_acquire:
 movm [d2,d3,a2,a3,other],(sp)
 mov psw,d2
 add -4,sp
 mov d2,(4,sp)
 mov (48,sp),d2
 mov (0x61c58404),d0
 and 4,d0
 beq hl_raw_done
 mov (a2),a0
 movbu (18595,a0),d0
 cmp 11,d0
 bne hl_raw_neutral
 call hl_source_to_owner,[],4
 bra hl_raw_done
hl_raw_neutral:
 call hl_owner_row,[],4
 cmp 0,a0
 beq hl_raw_done
 clr d0
 .irp offset,0,4,8
 mov d0,(\offset,a0)
 .endr
hl_raw_done:
 mov (4,sp),d2
 add 4,sp
 mov d2,psw
 movm (sp),[d2,d3,a2,a3,other]
 /* Displaced instructions, including their original PSW effects. */
 mov (a2),a2
 movbu (18595,a2),d0
 jmp raw_acquire_resume
