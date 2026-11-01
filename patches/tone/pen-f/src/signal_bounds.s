/* a0 is the selected source LUT, a1 the native 16-byte coefficients.
 * Return d0 = shadow_index | highlight_index<<8, or zero if unsupported.
 * CALL([d2,d3,a2,a3],16). All temporary spline data belongs to this call.
 */
.section .text,"ax"
.global tone_signal_bounds
tone_signal_bounds:
 add -64,sp
 mov a0,(8,sp)
 mov a1,(12,sp)
 mov -1,d0
 mov d0,(16,sp)
 mov 0x605fa3b6,a1
 mov sp,a3
 add 20,a3
 mov a3,a0
 mov 5,d2
signal_copy_knots:
 movhu (a1),d0
 movhu d0,(a0)
 add 2,a1
 add 2,a0
 add -1,d2
 bne signal_copy_knots
 mov (12,sp),a0
 movhu (4,a0),d1
 movhu (22,sp),d0
 sub d1,d0
 movhu d0,(22,sp)
 movhu (26,sp),d0
 add d1,d0
 movhu d0,(26,sp)
 mov sp,a2
 add 32,a2
 mov a2,d1
 mov a3,a1
 mov 0x605fa3b6,a0
 mov 5,d0
 call stock_spline_coefficients,[d2,d3,a2,a3],16
 clr d2
 clr d3
signal_sample:
 mov 0x605fa380,a0
 movhu (d2,a0),d0
 add d0,d0
 mov (8,sp),a0
 movhu (d0,a0),d0
 mov a2,(4,sp)
 mov a3,a1
 mov 0x605fa3b6,a0
 mov 5,d1
 call stock_spline_evaluate,[d2,d3,a2,a3],40
 cmp 1023,d0
 bhi signal_invalid
 cmp d3,d0
 bcs signal_invalid
 mov d0,d3
 cmp 130,d0
 bcs signal_next
 movbu (16,sp),d1
 cmp 255,d1
 bne signal_highlight
 cmp 0,d2
 beq signal_invalid
 mov 0x605fa37e,a0
 movhu (d2,a0),d1
 movbu d1,(16,sp)
signal_highlight:
 cmp 832,d0
 bcs signal_next
 movbu (17,sp),d1
 cmp 255,d1
 bne signal_next
 mov 0x605fa380,a0
 movhu (d2,a0),d1
 movbu d1,(17,sp)
signal_next:
 add 2,d2
 cmp 54,d2
 bcs signal_sample
 cmp 832,d3
 bcs signal_invalid
 movhu (16,sp),d0
 movbu (16,sp),d1
 cmp 255,d1
 beq signal_invalid
 movbu (17,sp),d2
 cmp d1,d2
 bls signal_invalid
 bra signal_return
signal_invalid:
 clr d0
signal_return:
 add 64,sp
 ret [d2,d3,a2,a3],16
