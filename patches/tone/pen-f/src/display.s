/* Display-local curve and drawing state. Entry guards remain resident. */
.section .tone_display_entry_gates,"ax"
.global tone_paint_gate, tone_update_gate, tone_filter_gate
tone_paint_gate:
 movbu (0xa1c58404),d0
 xor 160,d0
 and 160,d0
 bne tone_paint_stock
 jmp tone_paint
tone_paint_stock:
 jmp native_tone_paint
tone_update_gate:
 movbu (0xa1c58404),d0
 xor 160,d0
 and 160,d0
 bne tone_update_stock
 jmp tone_update
tone_update_stock:
 jmp native_tone_update
.section .tone_display_filter_gate,"ax"
tone_filter_gate:
 movbu (0xa1c58404),d0
 xor 160,d0
 and 160,d0
 bne tone_filter_stock
 jmp tone_filter
tone_filter_stock:
 mov (204,sp),a0
 mov (a0),a1
 mov (80,a1),a1
 jmp native_filter_resume

.section .tone_display_active,"ax"
.global tone_display_active, tone_update, tone_filter
tone_display_active:
 mov (a0),d0
 cmp 0x60ec4cac,d0
 bne tone_display_no
 mov (0x6161b810),a0
 cmp 0,a0
 beq tone_display_no
 mov (a0),a0
 mov a0,a2
 call tone_profile,[d2],8
 cmp 0,d0
 beq tone_display_no
 call tone_selected_id,[d2],8
 movhu (194,a2),d1
 bra tone_display_return
tone_display_no:
 clr d0
tone_display_return:
 cmp 0,d0
 ret [d2,d3,a2,a3],20

.section .tone_display_update,"ax"
tone_update:
 movm [d3,a2],(sp)
 add -4,sp
 mov a0,a2
 call native_tone_update,[],0
 mov d0,d3
 mov a2,a0
 call tone_display_active,[d2,d3,a2,a3],20
 beq tone_update_done
 mov a2,a0
 mov 1,d0
 mov 0,a1
 call stock_invalidate,[],4
tone_update_done:
 mov d3,d0
 add 4,sp
 ret [d3,a2],8

.section .tone_display_filter,"ax"
tone_filter:
 mov (116,sp),a0
 call tone_display_active,[d2,d3,a2,a3],20
 beq tone_filter_original
 cmp 2,d1
 mov 0xfc000000,d1
 bne tone_filter_mask
 mov 0xff3fffe0,d1
tone_filter_mask:
 mov (116,sp),a1
 add 792,a1
 mov (204,sp),d0
tone_filter_find:
 btst 1,d1
 beq tone_filter_next
 mov (a1),a0
 cmp a0,d0
 beq tone_filter_hide
tone_filter_next:
 inc4 a1
 lsr 1,d1
 bne tone_filter_find
tone_filter_original:
 jmp tone_filter_stock
tone_filter_hide:
 clr d0
 jmp native_filter_skip

.section .tone_display_paint,"ax"
.global tone_paint
tone_paint:
 movm [d2,d3,a2,a3],(sp)
 add -24,sp
 mov a0,a2
 mov a1,(20,sp)
 call native_tone_paint,[],0
tone_paint_after_native:
 mov (20,sp),a1
 add -1256,sp
 mov a1,(20,sp)
 mov d0,(16,sp)
 mov a2,a0
 call tone_display_active,[d2,d3,a2,a3],20
 beq tone_paint_done
 mov d0,d2
 mov (20,sp),a0
 cmp 0,a0
 beq tone_paint_done
 movhu (4,a0),d0
 cmp 2,d0
 bne tone_paint_done
 mov (8,a0),a0
 cmp 0,a0
 beq tone_paint_done
 mov sp,a3
 add 48,a3
 mov a3,a1
 mov 171,d1
tone_paint_copy:
 mov (a0),d0
 mov d0,(a1)
 inc4 a0
 inc4 a1
 add -1,d1
 bne tone_paint_copy
 mov (916,a2),a0
 cmp 0,a0
 beq tone_paint_done
 movhu (8,a0),d0
 add 3,d0
 mov d0,(4,sp)
 movhu (10,a0),d0
 add 260,d0
 mov d0,(8,sp)
 mov sp,a2
 add 732,a2
 mov a2,a0
 mov d2,d0
 call tone_reference,[d2,d3,a2,a3],16
 cmp 0,d0
 bne tone_paint_reference_ready
tone_paint_done:
 mov (16,sp),d0
 add 1280,sp
 ret [d2,d3,a2,a3],16
tone_paint_reference_ready:
 mov d0,(32,sp)
 mov d1,d3
 mov d2,d0
 mov 1,d1
 call stock_active_get,[d2],8
 mov d3,a1
 clr d1
 mov 0,a0
 call tone_step,[d2,d3,a2,a3],16
 mov d0,(28,sp)
 mov d0,d1
 and 1023,d0
 movhu d0,(1272,sp)
 lsr 10,d1
 and 1023,d1
 movhu d1,(1274,sp)
 mov (32,sp),d0
 mov d0,d1
 and 255,d0
 movhu d0,(1276,sp)
 lsr 8,d1
 movhu d1,(1278,sp)
 mov a2,a0
 mov sp,a1
 add 1272,a1
 call tone_endpoints,[d2,d3,a2,a3],16
 mov a3,a0
 mov -1,d0
 call stock_pen,[d2,d3,a2,a3],16
 mov 5,a1
 call tone_brush,[],4
 clr d2
 movhu (a2),d0
 lsr 2,d0
 mov (8,sp),d3
 sub d0,d3
tone_curve_loop:
 mov (4,sp),d0
 add d2,d0
 movhu d0,(40,sp)
 movhu d0,(44,sp)
 movhu d3,(46,sp)
 mov d2,d0
 add d0,d0
 movhu (d0,a2),d0
 lsr 2,d0
 mov (8,sp),d3
 sub d0,d3
 movhu d3,(42,sp)
 call tone_rectangle,[],4
 cmp 0,d2
 beq tone_curve_marker
 cmp 30,d2
 beq tone_curve_marker
 cmp 118,d2
 beq tone_curve_marker
 cmp 210,d2
 beq tone_curve_marker
 cmp 255,d2
 bne tone_curve_next
tone_curve_marker:
 movhu (40,sp),d0
 add -2,d0
 movhu d0,(40,sp)
 add 4,d0
 movhu d0,(44,sp)
 mov d3,d0
 add -2,d0
 movhu d0,(42,sp)
 add 4,d0
 movhu d0,(46,sp)
 call tone_rectangle,[],4
tone_curve_next:
 inc d2
 cmp 256,d2
 bcs tone_curve_loop
 jmp tone_paint_text

.section .tone_display_text,"ax"
tone_paint_text:
 mov a3,a0
 mov 1,d0
 call stock_font,[a2],8
 cmp 0,a0
 beq tone_paint_text_done
 mov a0,(24,sp)
 mov 2,d0
 movhu d0,(52,a3)
 mov sp,a0
 add 1244,a0
 mov 0x002b0042,d0
 mov d0,(a0)
 mov 0x00570020,d0
 mov d0,(12,a0)
 mov 45,d0
 movhu d0,(16,a0)
 clr d0
 movhu d0,(26,a0)
 movhu (1272,sp),d0
 mov a0,a1
 add 10,a1
 call tone_digits,[],4
 mov 1023,d0
 movhu (1274,sp),d1
 sub d1,d0
 mov a0,a1
 add 24,a1
 call tone_digits,[],4
 mov (4,sp),d0
 movhu d0,(40,sp)
 add 255,d0
 movhu d0,(44,sp)
 mov (8,sp),d0
 add 33,d0
 movhu d0,(42,sp)
 add 31,d0
 movhu d0,(46,sp)
 mov sp,a1
 mov a1,d1
 add 1244,d1
 call hsl_text,[],4
 mov (24,sp),a0
 call stock_font_release,[],4
tone_paint_text_done:
 jmp tone_paint_done

.section .tone_display_brush,"ax"
tone_brush:
 mov a3,a0
 mov -2,d0
 mov -1,d1
 call stock_brush,[d2,d3,a2],16
 ret [],4
.section .tone_display_rectangle,"ax"
tone_rectangle:
 mov a3,a0
 mov sp,a1
 add 44,a1
 call stock_rectangle,[d2,a2,a3],52
 ret [],4
.section .tone_display_digits,"ax"
tone_digits:
 mov 4,d1
tone_digit_loop:
 mov 10,d2
 ext d0
 div d2,d0
 mov mdr,d2
 add 48,d2
 movhu d2,(a1)
 add -2,a1
 add -1,d1
 bne tone_digit_loop
 ret [],4
