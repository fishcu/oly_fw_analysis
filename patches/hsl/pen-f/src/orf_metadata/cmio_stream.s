/* Copyright 2026 fishku (original contributions)
 * SPDX-License-Identifier: Apache-2.0
 * Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
 */
/* PEN-F 3101 HSL: orf metadata. */
/* Carry-preserving encoded delta, with exactly n writable bytes.
 * a0 destination, a1 old plaintext, a2 new plaintext, d0 count,
 * d1 preceding plaintext XOR delta. Returns the new carry in d0.
 * CALL [d2,d3,a2,a3],20. Caller handles the final carry byte separately.
 * This permits a CMIO table replacement to cross a mapping-window boundary.
 */
.section .cmio_stream,"ax"
.global cmio_delta_stream
cmio_delta_stream:
 mov d0,a3
 cmp 0,a3
 beq cmio_stream_done
cmio_stream_loop:
 movbu (a1),d2
 movbu (a2),d3
 xor d3,d2
 movbu (a0),d3
 xor d1,d3
 xor d2,d3
 movbu d3,(a0)
 mov d2,d1
 inc a0
 inc a1
 inc a2
 add -1,a3
 bne cmio_stream_loop
cmio_stream_done:
 mov d1,d0
 ret [d2,d3,a2,a3],20

/* Replace one encoded template, including its trailing carry byte.
 * a0 logical destination, a1 old plain, a2 new plain, d0 plain length.
 * CALL [d2,d3,a2,a3],60. No allocation or global scratch storage.
 * Logical B0000000..DFFFFFFF buffers use the native mapping/locking wrapper;
 * other addresses use the native uncached-address converter. A mapping never
 * spans a 128 MiB boundary and each acquired mapping is released.
 * Returns 0 on success or native-style transfer error 40648 on map failure.
 */
.section .cmio_table,"ax"
.global cmio_patch_table
cmio_patch_table:
 mov a0,(4,sp)              /* logical cursor */
 mov a1,(8,sp)              /* original template cursor */
 mov a2,(12,sp)             /* creative template cursor */
 mov d0,(16,sp)             /* remaining plain bytes */
 clr d0
 mov d0,(20,sp)             /* preceding delta */
cmio_table_window:
 mov (4,sp),d0
 mov (16,sp),d2
 inc d2                    /* includes trailing encoded carry byte */
 clr d3                    /* whether a native mapping was acquired */
 cmp 0xb0000000,d0
 bcs cmio_table_direct
 cmp 0xe0000000,d0
 bcc cmio_table_direct
 mov d0,d1
 and 0x07ffffff,d1
 mov 0x08000000,d2
 sub d1,d2
 mov (16,sp),d1
 inc d1
 cmp d1,d2
 bls cmio_table_map
 mov d1,d2
cmio_table_map:
 clr d1
 call native_buffer_map,[d2,d3,a2,a3],44
 cmp 0,d0
 bne cmio_table_mapped
 jmp cmio_table_error
cmio_table_mapped:
 mov 1,d3
 jmp cmio_table_address
cmio_table_direct:
 call native_uncached,[d2],4
 jmp cmio_table_address
.section .cmio_table_tail,"ax"
cmio_table_address:
 mov d0,(24,sp)             /* address returned by mapper */
 mov d2,(28,sp)             /* whole encoded span length */
 mov d3,(32,sp)
 mov (16,sp),d3
 cmp d3,d2
 bls cmio_table_count
 mov d3,d2                 /* do not read past plaintext templates */
cmio_table_count:
 mov d2,(36,sp)
 mov d0,a0
 mov (8,sp),a1
 mov (12,sp),a2
 mov d2,d0
 mov (20,sp),d1
 call cmio_delta_stream,[d2,d3,a2,a3],20
 mov d0,(20,sp)
 /* a0 advanced by the stream; append carry if this window contains it. */
 mov (28,sp),d1
 cmp d2,d1
 beq cmio_table_release
 movbu (a0),d1
 xor d0,d1
 movbu d1,(a0)
cmio_table_release:
 mov (32,sp),d0
 cmp 0,d0
 beq cmio_table_advance
 mov (24,sp),d0
 call native_buffer_unmap,[d2,d3,a2,a3],48
 cmp 0,d0
 beq cmio_table_error
cmio_table_advance:
 mov (28,sp),d1
 mov (16,sp),d0
 cmp d0,d1
 bhi cmio_table_success
 sub d2,d0
 mov d0,(16,sp)
 mov (4,sp),d0
 add d1,d0
 mov d0,(4,sp)
 mov (8,sp),d0
 add d2,d0
 mov d0,(8,sp)
 mov (12,sp),d0
 add d2,d0
 mov d0,(12,sp)
 jmp cmio_table_window
cmio_table_error:
 mov 40648,d0
 bra cmio_table_return
cmio_table_success:
 clr d0
cmio_table_return:
 ret [d2,d3,a2,a3],60
