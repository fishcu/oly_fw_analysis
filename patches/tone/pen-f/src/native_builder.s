/* Ordinary non-bypass tone builder; a0 is its context.
 * CALL([d2,d3,a2,a3],28), as in stock firmware.
 * The native selection and inner-overlay gates retain their original order.
 */
.section .text,"ax"
.global tone_native_builder, tone_ordinary_call
tone_ordinary_call:
 call tone_native_builder,[d2,d3,a2,a3],28
 jmp stock_tone_resume
tone_native_builder:
 add -32,sp
 mov a0,(12,sp)
 call tone_job_word,[d2],4
 cmp 0,d0
 beq builder_stock
 mov d0,(16,sp)
 mov (12,sp),a0
 mov (4,a0),d1
 mov d1,(4,sp)
 mov (12,a0),a3
 mov d1,a0
 mov (960,a0),d1
 clr d0
 cmp d0,d1
 beq builder_select
 mov d1,a0
 mov (8,a0),a0
 mov a0,(4656,a3)
 bra builder_selected
builder_stock:
 mov (12,sp),a0
 add 32,sp
 jmp stock_tone_builder
builder_select:
 movbu d0,(8,sp)
 mov (4,sp),a0
 mov sp,a1
 mov a1,d0
 add 8,d0
 mov 4660,a1
 add a3,a1
 call stock_tone_select,[d2,a2,a3],20
 mov a0,(4656,a3)
 movbu (8,sp),d0
 cmp 0,d0
 bne builder_return
builder_selected:
 mov (4656,a3),a0
 cmp 0,a0
 beq builder_stock
 mov (12,sp),a1
 add 60,a1
 call tone_signal_bounds,[d2,d3,a2,a3],16
 mov d0,d1
 and 255,d0
 movhu d0,(24,sp)
 lsr 8,d1
 movhu d1,(26,sp)
 mov (4,sp),a0
 mov (948,a0),a0
 call stock_tone_gate,[],0
 extbu d0
 cmp 0,d0
 beq builder_finish
 mov 4660,a2
 add a3,a2
 mov (4656,a3),a0
 cmp a2,a0
 beq builder_overlay
 call builder_copy,[d2,d3,a2,a3],16
builder_overlay:
 mov (4,sp),a0
 movbu (1065,a0),d0
 and 128,d0
 lsr 7,d0
 mov a2,a0
 mov (12,sp),a1
 add 60,a1
 call stock_tone_apply,[d2,d3,a2,a3],16
 mov a2,(4656,a3)
builder_finish:
 mov d0,(28,sp)
 movhu (24,sp),d0
 movhu (26,sp),d1
 cmp d0,d1
 bls builder_unchanged
 mov (4656,a3),a0
 movhu (a0),d0
 cmp 0,d0
 bne builder_unchanged
 movhu (510,a0),d0
 cmp 1023,d0
 bne builder_unchanged
 clr d1
 mov 256,d2
builder_validate:
 movhu (a0),d0
 cmp 1023,d0
 bhi builder_unchanged
 cmp d1,d0
 bcs builder_unchanged
 mov d0,d1
 add 2,a0
 add -1,d2
 bne builder_validate
 mov (4656,a3),a0
 mov (16,sp),d0
 and 1023,d0
 movhu (24,sp),d1
 add d1,d1
 movhu (d1,a0),d1
 cmp d1,d0
 bls builder_black_valid
 mov d1,d0
builder_black_valid:
 movhu d0,(20,sp)
 mov (16,sp),d0
 lsr 10,d0
 and 1023,d0
 movhu (26,sp),d1
 add d1,d1
 movhu (d1,a0),d1
 cmp d1,d0
 bcc builder_white_valid
 mov d1,d0
builder_white_valid:
 movhu d0,(22,sp)
 cmp 1023,d0
 bne builder_write
 movhu (20,sp),d0
 cmp 0,d0
 beq builder_unchanged
builder_write:
 mov 4660,a2
 add a3,a2
 cmp a2,a0
 beq builder_apply
 call builder_copy,[d2,d3,a2,a3],16
builder_apply:
 mov a2,a0
 mov sp,a1
 add 20,a1
 call tone_endpoints,[d2,d3,a2,a3],16
 mov a2,(4656,a3)
builder_unchanged:
 mov (28,sp),d0
builder_return:
 add 32,sp
 ret [d2,d3,a2,a3],28
builder_copy:
 mov a2,a1
 mov 256,d1
builder_copy_loop:
 movhu (a0),d0
 movhu d0,(a1)
 add 2,a0
 add 2,a1
 add -1,d1
 bne builder_copy_loop
 ret [d2,d3,a2,a3],16
