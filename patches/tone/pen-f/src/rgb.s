.section .tone_rgb_gate,"ax"
.global tone_rgb_gate,tone_rgb_stock
tone_rgb_gate:
 movbu (0xa1c58404),d0
 btst 128,d0
 bne tone_rgb_loaded
 jmp tone_rgb_stock
tone_rgb_loaded:
 jmp tone_rgb_call
.section .tone_rgb_stock,"ax"
tone_rgb_stock:
 call stock_rgb_builder,[d2,d3,a2,a3],216
 jmp stock_rgb_resume

.section .text,"ax"
.global tone_rgb_call,tone_rgb_map
tone_rgb_call:
 movm [d2,d3,a2,a3],(sp)
 add -28,sp
 mov a0,a2
 call tone_job_word,[d2],4
 cmp 0,d0
 beq tone_rgb_fallback
 mov a0,a3
 mov 14948,d3
tone_rgb_qualify:
 mov (d3,a3),d0
 mov sp,a0
 add 4,a0
 call tone_decode,[d2,d3,a2,a3],16
 cmp 0,d0
 bne tone_rgb_acquired
 add 4,d3
 cmp 14960,d3
 bcs tone_rgb_qualify
 bra tone_rgb_fallback
tone_rgb_acquired:
 mov (56,a2),d0
 mov d0,(4,sp)
 or 2,d0
 mov d0,(56,a2)
 mov a2,a0
 call stock_rgb_builder,[d2,d3,a2,a3],216
.global tone_rgb_after_native
tone_rgb_after_native:
 mov d0,(8,sp)
 mov (4,sp),d0
 mov d0,(56,a2)
 mov (12,a2),a0
 mov (1052,a0),a1
 cmp 0,a1
 beq tone_rgb_bank1
 add 1060,a0
 cmp a0,a1
 bne tone_rgb_return
 mov a0,(12,sp)
 mov 1,d0
 mov d0,(16,sp)
 mov (12,a2),a0
 mov (8,a0),d0
 btst 1,d0
 beq tone_rgb_return
 mov (1056,a0),a1
 cmp 0,a1
 beq tone_rgb_selected
 add 2084,a0
 cmp a0,a1
 bne tone_rgb_return
 mov 0x605fdd38,a1
 mov 256,d2
tone_rgb_companion:
 movhu (a1),d0
 mov d0,d1
 asl 10,d1
 or d0,d1
 asl 20,d0
 or d0,d1
 mov (a0),d0
 cmp d1,d0
 bne tone_rgb_return
 inc4 a0
 add 2,a1
 add -1,d2
 bne tone_rgb_companion
 mov 3,d0
 mov d0,(16,sp)
 bra tone_rgb_selected
tone_rgb_bank1:
 mov (1056,a0),a1
 add 2084,a0
 cmp a0,a1
 bne tone_rgb_return
 mov a0,(12,sp)
 mov 2,d0
 mov d0,(16,sp)
 mov (12,a2),a0
 mov (4,a0),d0
 btst 65536,d0
 beq tone_rgb_return
tone_rgb_selected:
 clr d3
tone_rgb_channel:
 mov d3,d0
 asl 2,d0
 add 14948,d0
 mov (d0,a3),d0
 mov tone_rgb_lane_shifts,a0
 movbu (d3,a0),d1
 mov (12,sp),a0
 call tone_rgb_map,[d2,d3,a2,a3],16
 inc d3
 cmp 3,d3
 bcs tone_rgb_channel
 mov (100,a2),d0
 mov (16,sp),d1
 or d1,d0
 mov d0,(100,a2)
tone_rgb_return:
 mov (8,sp),d0
 add 28,sp
 movm (sp),[d2,d3,a2,a3]
 jmp stock_rgb_resume
tone_rgb_fallback:
 mov a2,a0
 add 28,sp
 movm (sp),[d2,d3,a2,a3]
 jmp tone_rgb_stock

tone_rgb_map:
 cmp 0xb7ff0400,d0
 beq tone_rgb_map_return
 add -28,sp
 mov a0,a2
 mov d1,(20,sp)
 mov sp,a0
 add 4,a0
 call tone_decode,[d2,d3,a2,a3],16
 cmp 0,d0
 beq tone_rgb_map_done
 mov a2,a3
 add 1024,a3
tone_rgb_sample:
 mov (a2),d0
 mov d0,(24,sp)
 mov (20,sp),d1
 lsr d1,d0
 and 1023,d0
 asl 2,d0
 clr d1
tone_rgb_interval:
 cmp 6,d1
 beq tone_rgb_interval_found
 cmp 1023,d0
 bcs tone_rgb_interval_found
 add -1023,d0
 add 2,d1
 bra tone_rgb_interval
tone_rgb_interval_found:
 mov sp,a0
 add 4,a0
 add d1,a0
 movhu (a0),d2
 movhu (2,a0),d3
 sub d2,d3
 mul d3,d0
 mov 1023,d1
 ext d0
 div d1,d0
 add d2,d0
 mov (20,sp),d1
 asl d1,d0
 mov 1023,d2
 asl d1,d2
 xor -1,d2
 mov (24,sp),d1
 and d2,d1
 or d1,d0
 mov d0,(a2)
 inc4 a2
 cmp a3,a2
 bcs tone_rgb_sample
tone_rgb_map_done:
 add 28,sp
tone_rgb_map_return:
 ret [d2,d3,a2,a3],16

tone_rgb_lane_shifts:
 .byte 0,10,20
