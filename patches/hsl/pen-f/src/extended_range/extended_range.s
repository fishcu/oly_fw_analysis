/* Copyright 2026 fishku (original contributions)
 * SPDX-License-Identifier: Apache-2.0
 * Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
 */
/* PEN-F 3101 HSL: extended range. */
/* Bounded in-place replacements for the fifteen-position COLOR editor.
 * Linked spans must remain exactly their original size. Other COLOR/CRT
 * dispatch, invalid-input reporting and selected-sector handling stay stock.
 */
.section .range_wheel_encode,"ax"
.global range_wheel_encode
range_wheel_encode:
 cmp -7,d0
 blt range_wheel_invalid
 cmp 7,d0
 bgt range_wheel_invalid
 add 7,d0
 jmp range_wheel_store
range_wheel_invalid:
 jmp stock_wheel_invalid
 .fill 27-(.-range_wheel_encode),1,0xcb

.section .range_value_label,"ax"
.global range_value_label
range_value_label:
 mov (16,sp),d0
 add 7,d0
 cmp 14,d0
 bls range_value_valid
 mov 7,d0
range_value_valid:
 add -7,d0
 mov 1,d1
 cmp 0,d0
 beq range_value_ready
 mov 2,d1
 bgt range_value_ready
 mov 3,d1
 not d0
 inc d0
range_value_ready:
 mov d2,a0
 movbu d1,(1,a0)
 inc d0
 movbu d0,(2,a0)
 .fill 38-(.-range_value_label),1,0xcb


.section .range_backup_enum_export,"ax"
 call range_backup_enum,[d2,d3,a2,a3],20
/* The replaced seven bytes include CMP 0,a0, now done by the helper. */
.section .range_backup_enum_import,"ax"
 call range_backup_enum,[d2,d3,a2,a3],20
 mov a0,a3
/* The replaced eight bytes include CMP 0,a3. MOV preserves helper flags. */
