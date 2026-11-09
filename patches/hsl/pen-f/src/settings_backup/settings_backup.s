/* Copyright 2026 fishku (original contributions)
 * SPDX-License-Identifier: Apache-2.0
 * Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
 */
/* PEN-F 3101 HSL: settings backup. */
/* Named settings backup and restore extension.
 * Camera named-record extension: 2,PENF_HSL_V1,<36 packed bytes as hex>\r\n.
 * Restore state belongs to the existing operation allocation, enlarged by
 * 64 bytes. No global persistent state, new flash writer or UI callback.
 * Offsets +2048: accepted bank mask; +2052: 0 missing/1 valid/2 invalid;
 * +2056: 36 decoded pairs. Nothing is applied until a bank terminator.
 */
.section .backup_export_hook,"ax"
 jmp hl_backup_export_hook
 nop
.section .backup_header_hook,"ax"
 jmp hl_backup_header_hook
 nop
.section .backup_line_hook,"ax"
 jmp hl_backup_line_hook
 nop
.section .backup_footer_hook,"ax"
 jmp hl_backup_footer_hook
 nop

.section .backup_export,"ax"
.global hl_backup_export_hook,hl_backup_header_hook,hl_backup_line_hook
.global hl_backup_footer_hook,hl_backup_export,hl_backup_parse,hl_backup_apply

/* Parent export frame and registers are unchanged on either continuation. */
hl_backup_export_hook:
 mov (20,sp),d0
 cmp 2,d0
 bne hl_backup_export_resume
 mov d2,d0
 mov a2,d1
 mov (16,sp),a0
 call hl_backup_export,[d2,d3,a2,a3],32
 cmp 0,d0
 bne hl_backup_export_fail
 add 88,a2
hl_backup_export_resume:
 mov (16,sp),a0
 mov a2,d0
 mov (12,sp),a1
 jmp native_602c182f
hl_backup_export_fail:
 jmp native_602c183f

/* d0 bank mask, d1 output offset, a0 {base,capacity}; return 0/1.
 * CALL [d2,d3,a2,a3],32. Only the caller-owned output buffer is written.
 */
hl_backup_export:
 mov d0,d3
 mov d1,d2
 mov a0,a3
 mov (a0),d0
 add d2,d0
 mov d0,a2
 mov 88,d1
 call native_602c176b,[d2,d3],8
 cmp 0,d0
 bne hl_backup_export_bad
 mov a2,a0
 mov hl_backup_prefix,a1
 mov 14,d0
 call native_602c2651,[],4
 add 14,a2
 cmp 256,d3
 beq hl_backup_export_current
 mov d3,d0
 mov 8,d1
 mov 0x615fd478,a0
 call native_602c2734,[d2,d3,a2],12
 mov d0,d3
 bra hl_backup_export_start
hl_backup_export_current:
 clr d3
hl_backup_export_start:
 mov 931,d2
hl_backup_export_loop:
 mov d2,d0
 cmp 0,d3
 beq hl_backup_export_live
 mov d3,d1
 mov 1,a0
 call native_602f06b6,[d2,d3],12
 bra hl_backup_export_decode
hl_backup_export_live:
 mov 1,d1
 call native_602f06e7,[d2],8
hl_backup_export_decode:
 call hl_decode_cell,[],4
 mov hl_backup_hex,a0
 mov d0,d1
 lsr 4,d1
 movbu (d1,a0),d1
 movbu d1,(a2)
 inc a2
 and 15,d0
 movbu (d0,a0),d0
 movbu d0,(a2)
 inc a2
 inc d2
 cmp 967,d2
 bne hl_backup_export_loop
 mov 13,d0
 movbu d0,(a2)
 inc a2
 mov 10,d0
 movbu d0,(a2)
 clr d0
 ret [d2,d3,a2,a3],32
hl_backup_export_bad:
 mov 1,d0
 ret [d2,d3,a2,a3],32

/* This point is reached only after the native bank header was accepted. */
.section .backup_lifecycle,"ax"
hl_backup_header_hook:
 mov (72,sp),d0
 mov (0x615fd4e0),a0
 mov d0,(2048,a0)
 clr d1
 mov d1,(2052,a0)
 cmp 256,d0
 jmp native_602c1e95

/* Intercept only our names; preserve native handling of every stock line.
 * Result 0 = unrecognized, 1 = handled, 2 = malformed/duplicate extension.
 */
.section .backup_import,"ax"
hl_backup_line_hook:
 mov a2,a0
 movhu (86,sp),d0
 call hl_backup_parse,[d2,d3,a2,a3],24
 cmp 1,d0
 beq hl_backup_line_done
 cmp 2,d0
 beq hl_backup_line_bad
 mov a2,a0
 movhu (86,sp),d0
 mov (28,sp),a1
 jmp native_602c1ed8
hl_backup_line_done:
 jmp native_602c1f83
hl_backup_line_bad:
 jmp native_602c1f2e

/* d0 length, a0 line; CALL [d2,d3,a2,a3],24.
 * A malformed/duplicate own record invalidates this bank's entire extension.
 */
hl_backup_parse:
 mov d0,d3
 mov a0,a2
 cmp 11,d3
 bcs hl_backup_unrecognized
 mov hl_backup_prefix,a1
 clr d2
hl_backup_family:
 movbu (d2,a2),d0
 movbu (d2,a1),d1
 cmp d1,d0
 bne hl_backup_unrecognized
 inc d2
 cmp 11,d2
 bne hl_backup_family
 mov (0x615fd4e0),a3
 add 2048,a3
 mov (4,a3),d1
 mov 2,d0
 mov d0,(4,a3)
 cmp 0,d1
 bne hl_backup_invalid
 mov (a3),d0
 cmp 0,d0
 beq hl_backup_invalid
 cmp 88,d3
 bne hl_backup_invalid
hl_backup_version:
 movbu (d2,a2),d0
 movbu (d2,a1),d1
 cmp d1,d0
 bne hl_backup_invalid
 inc d2
 cmp 14,d2
 bne hl_backup_version
 movbu (86,a2),d0
 cmp 13,d0
 bne hl_backup_invalid
 movbu (87,a2),d0
 cmp 10,d0
 bne hl_backup_invalid
 add 14,a2
 clr d2
hl_backup_parse_pair:
 movbu (a2),d0
 inc a2
 call hl_backup_unhex,[],4
 cmp 15,d0
 bhi hl_backup_invalid
 asl 4,d0
 mov d0,d3
 movbu (a2),d0
 inc a2
 call hl_backup_unhex,[],4
 cmp 15,d0
 bhi hl_backup_invalid
 or d0,d3
 mov d3,d0
 xor 255,d0
 asl 8,d0
 or d3,d0
 or 0x48310000,d0
 call hl_decode_cell,[],4
 cmp d3,d0
 bne hl_backup_invalid
 mov a3,a0
 add 8,a0
 movbu d0,(d2,a0)
 inc d2
 cmp 36,d2
 bne hl_backup_parse_pair
 mov 1,d0
 mov d0,(4,a3)
 ret [d2,d3,a2,a3],24
hl_backup_unrecognized:
 clr d0
 ret [d2,d3,a2,a3],24
hl_backup_invalid:
 mov 2,d0
 ret [d2,d3,a2,a3],24

hl_backup_unhex:
 cmp 48,d0
 bcs hl_backup_not_hex
 cmp 57,d0
 bhi hl_backup_hex_letter
 sub 48,d0
 ret [],4
hl_backup_hex_letter:
 or 32,d0
 sub 97,d0
 cmp 5,d0
 bhi hl_backup_not_hex
 add 10,d0
 ret [],4
hl_backup_not_hex:
 mov 256,d0
 ret [],4

/* A complete native type-3 record has been checked at this point. */
.section .backup_lifecycle,"ax"
hl_backup_footer_hook:
 mov (72,sp),d0
 call hl_backup_apply,[d2,d3,a2,a3],24
 mov (72,sp),d0
 cmp 256,d0
 jmp native_602c1f79

/* d0 native bank mask; CALL [d2,d3,a2,a3],24.
 * Custom: active part1 -> stock footer/filter/save. Current: bank0 part1
 * -> stock final bank0 load -> native transaction commit/publication.
 */
.section .backup_import,"ax"
hl_backup_apply:
 mov d0,d3
 mov (0x615fd4e0),a3
 add 2048,a3
 mov (a3),d1
 cmp d1,d0
 bne hl_backup_apply_done
 cmp 0,d0
 beq hl_backup_apply_done
 mov 931,d2
 mov a3,a2
 add 8,a2
hl_backup_apply_loop:
 clr d0
 mov (4,a3),d1
 cmp 1,d1
 bne hl_backup_apply_neutral
 movbu (a2),d0
hl_backup_apply_neutral:
 mov d0,d1
 xor 255,d1
 asl 8,d1
 or d1,d0
 or 0x48310000,d0
 cmp 256,d3
 beq hl_backup_apply_current
 mov d0,a0
 mov d2,d0
 mov 1,d1
 call native_602f0710,[d2],8
 bra hl_backup_apply_next
hl_backup_apply_current:
 mov d0,a1
 mov d2,d1
 add 1274,d1
 mov 0x85d4,d0
 mov (0x61896ed4),a0
 call native_600751c5,[d2],28
hl_backup_apply_next:
 inc a2
 inc d2
 cmp 967,d2
 bne hl_backup_apply_loop
 clr d0
 mov d0,(a3)
hl_backup_apply_done:
 ret [d2,d3,a2,a3],24

.section .backup_export,"ax"
hl_backup_prefix:
 .ascii "2,PENF_HSL_V1,"
hl_backup_hex:
 .ascii "0123456789ABCDEF"
