/* Copyright 2026 fishku (original contributions)
 * SPDX-License-Identifier: Apache-2.0
 * Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
 */
/* PEN-F 3101 HSL: editor storage. */
/* PEN-F 3101 all-profile H/L snapshot transport.
 * Consolidated snapshot transport and recording copy; one serialized GUI
 * writer, no new counter/lock/persistence. All 36 packed source bytes
 * start at zero. Retained COLOR reader is linked separately, byte-identical.
 */
.macro save_context
 /* Stock MOVM's "other" group saves d0/d1/a0/a1/MDR/LIR/LAR and
  * reserves a blank word. Together with d2/d3/a2/a3 this is 48 bytes.
  * Put PSW in that blank word, with a separate outgoing CALL word below it.
  */
 movm [d2,d3,a2,a3,other],(sp)
 mov psw,d2
 add -4,sp
 mov d2,(4,sp)
 mov (48,sp),d2
.endm
.macro restore_context
 mov (4,sp),d2
 add 4,sp
 mov d2,psw
 movm (sp),[d2,d3,a2,a3,other]
.endm

.section .capture_acquire,"ax"
 jmp hl_capture_acquire
 nop
.section .compact_acquire,"ax"
 jmp hl_compact_acquire
 nop
.section .capture_to_job,"ax"
 jmp hl_capture_to_job
 nop
.section .compact_to_job,"ax"
 jmp hl_compact_to_job
 nop
 nop

.section .transport,"ax"
.global hl_owner_row, hl_source_to_owner, hl_owner_to_job
hl_capture_acquire:
 save_context
 mov d2,a0
 call hl_source_to_owner,[],4
 restore_context
 mov 63401,d0
 jmp capture_acquire_resume

hl_compact_acquire:
 save_context
 mov a3,a0
 add -382,a0
 call hl_source_to_owner,[],4
 restore_context
 mov (4,sp),a0
 clr d0
 movbu d0,(122,a0)
 jmp compact_acquire_resume

hl_capture_to_job:
 save_context
 mov (a0),a0
 mov (56,sp),a2
 add 14884,a2                 /* converter destination is job+36 */
 call hl_owner_to_job,[],4
 restore_context
 mov (a0),a0
 movbu (18624,a0),d0
 jmp capture_job_resume

hl_compact_to_job:
 call compact_setter,[d2,d3,a2,a3],52
hl_after_compact_call:
 save_context
 /* The displaced call's return value and MDR belong to the native caller. */
 mov (16,sp),d1
 cmp hl_after_compact_call,d1
 bne hl_compact_mdr_saved
 mov compact_job_resume,d1
 mov d1,(16,sp)
hl_compact_mdr_saved:
 cmp 0,d0
 bne hl_compact_job_done
 mov (64,sp),a0               /* caller's acquired snapshot at sp+12 */
 mov (1920,sp),a2             /* caller's processing job at sp+1868 */
 add 14920,a2
 call hl_owner_to_job,[],4
hl_compact_job_done:
 restore_context
 jmp compact_job_resume

hl_source_to_owner:
 mov a0,a3
 call hl_owner_row,[],4
 cmp 0,a0
 beq hl_source_done
 mov a0,a1
 mov a3,a0
 cmp hl_compact_rows,a1
 bcc hl_source_compact
 movbu (18625,a0),d0
 bra hl_source_profile
hl_source_compact:
 movbu (381,a0),d0
hl_source_profile:
 mov hl_source_uncached,a0
 add -1,d0
 cmp 3,d0
 bcc hl_source_neutral
 mov d0,d1
 asl 1,d0
 add d1,d0
 asl 2,d0
 add d0,a0
 bra hl_source_copy
hl_source_neutral:
 mov hl_zero_source,a0
hl_source_copy:
hl_copy12:
 .irp off,0,4,8
 mov (\off,a0),d0
 mov d0,(\off,a1)
 .endr

hl_source_done:
 ret [],4

hl_owner_to_job:
 call hl_owner_row,[],4
 cmp 0,a0
 bne hl_have_owner
 /* Every update writes all 24 bytes, including the neutral fallback. */
 mov hl_zero_source,a0
hl_have_owner:
 mov a2,a1
hl_unpack12:
 mov 12,d2
hl_unpack_loop:
 movbu (a0),d0
 mov d0,d1
 asl 28,d0
 asr 28,d0
 movbu d0,(a1)
 asl 24,d1
 asr 28,d1
 movbu d1,(12,a1)
 inc a0
 inc a1
 add -1,d2
 bne hl_unpack_loop
 ret [],4

hl_owner_row:
 /* O(1) owner lookup. Normalize only the established cached/uncached
  * aliases, then require an exact native block/slot base within bounds.
  */
 mov a0,d0
 mov d0,d1
 and 0xe0000000,d1
 cmp 0x60000000,d1
 beq hl_alias_valid
 cmp 0xa0000000,d1
 bne hl_no_owner
hl_alias_valid:
 and 0x1fffffff,d0
 or 0xa0000000,d0
 cmp 0xadafa3c0,d0
 bcs hl_try_compact
 sub 0xadafa3c0,d0
 cmp 1679360,d0
 bcc hl_no_owner
 mov 41984,d1
 clr d2
 bra hl_divide_owner
hl_try_compact:
 sub 0xa1c6cab8,d0
 cmp 3160,d0
 bcc hl_no_owner
 mov 632,d1
 mov 40,d2
hl_divide_owner:
 clr d3
 mov d3,mdr
 divu d1,d0
 mov mdr,d1
 cmp 0,d1
 bne hl_no_owner
 add d2,d0
 /* x12 without the emulator's uncorrected unsigned-immediate multiply. */
 mov d0,d1
 asl 1,d0
 add d1,d0
 asl 2,d0
 mov hl_rows_uncached,a0
 add d0,a0
 ret [],4
hl_no_owner:
 mov 0,a0
 ret [],4

/* Copy the mutable packed source without whole-table atomicity. Nibble0 is H, nibble1 is L.
 * Signed nibble -8 is reserved; the existing consumer neutralizes it.
 */

.balign 4
hl_zero_source:
 .space 12,0

.section .recording_to_job,"ax"
 jmp hl_recording_to_job
 nop

.section .transport,"ax"
hl_recording_to_job:
 /* Identical save/restore convention to the qualified snapshot hooks.
  * 48 saved bytes plus the outgoing call word = 52 bytes below old SP.
  */
 movm [d2,d3,a2,a3,other],(sp)
 mov psw,d2
 add -4,sp
 mov d2,(4,sp)
 mov (48,sp),d2
 mov (76,sp),a0             /* old SP+24: acquired capture pointer */
 mov (72,sp),a2             /* old SP+20: destination job+36 */
 add 14884,a2              /* destination job+14920 */
 call hl_owner_to_job,[],4
 mov (4,sp),d2
 add 4,sp
 mov d2,psw
 movm (sp),[d2,d3,a2,a3,other]
 /* Replay both displaced instructions, then resume their original branch. */
 mov (24,sp),a0
 movbu (18588,a0),d0
 jmp recording_job_resume

.section .transport_rows,"aw"
.global hl_rows
hl_rows:
 .space 540,0
