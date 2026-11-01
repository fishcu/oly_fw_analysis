/* Ordinary COLOR builder; CALL([d2,d3,a2,a3],28).
 * The private raw/coefficient buffers preserve the two legacy controls only.
 */
.section .text,"ax"
.global tone_native_builder,tone_ordinary_call
tone_ordinary_call:
 call tone_native_builder,[d2,d3,a2,a3],28
 jmp stock_tone_resume
tone_native_builder:
 add -68,sp
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
 add 68,sp
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
 movhu (a0),d0
 cmp 0,d0
 bne builder_stock
 movhu (510,a0),d0
 cmp 1023,d0
 bne builder_stock
 clr d1
 mov 256,d2
builder_validate:
 movhu (a0),d0
 cmp 1023,d0
 bhi builder_stock
 cmp d1,d0
 bcs builder_stock
 mov d0,d1
 add 2,a0
 add -1,d2
 bne builder_validate
 clr d0
 mov d0,(24,sp)
 mov d0,(28,sp)
 mov d0,(32,sp)
 mov (4,sp),a0
 mov (948,a0),a0
 cmp 0,a0
 beq builder_no_raw
 mov (a0),d0
 mov d0,(24,sp)
 add 4,a0
 bra builder_resolve
builder_no_raw:
 mov sp,a0
 add 28,a0
builder_resolve:
 mov (16,sp),d0
 mov sp,a1
 add 52,a1
 call tone_resolve,[d2,d3,a2,a3],16
 mov d0,(16,sp)
 mov sp,a0
 add 24,a0
 call stock_tone_gate,[],0
 extbu d0
 mov d0,(20,sp)
 cmp 0,d0
 beq builder_map
 call builder_writable,[d2,d3,a2,a3],16
 mov sp,a0
 add 24,a0
 mov sp,a1
 add 36,a1
 call stock_convert,[],16
 mov (4,sp),a0
 movbu (1065,a0),d0
 and 128,d0
 lsr 7,d0
 mov (4656,a3),a0
 mov sp,a1
 add 36,a1
 call stock_tone_apply,[d2,d3,a2,a3],16
 mov d0,(20,sp)
builder_map:
 mov (16,sp),d0
 cmp 0xb7ff0400,d0
 beq builder_done
 call builder_writable,[d2,d3,a2,a3],16
 mov (4656,a3),a0
 mov (16,sp),d0
 call tone_apply,[d2,d3,a2,a3],16
builder_done:
 mov (20,sp),d0
builder_return:
 add 68,sp
 ret [d2,d3,a2,a3],28
builder_writable:
 mov 4660,a2
 add a3,a2
 mov (4656,a3),a0
 cmp a2,a0
 beq builder_writable_done
 mov a2,a1
 mov 256,d1
builder_copy:
 movhu (a0),d0
 movhu d0,(a1)
 add 2,a0
 add 2,a1
 add -1,d1
 bne builder_copy
 mov a2,(4656,a3)
builder_writable_done:
 ret [d2,d3,a2,a3],16
