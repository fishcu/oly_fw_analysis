/* Probe-only kernel. The caller validates the full LUT and endpoint contract.
 * a0 is a writable 256*u16 LUT. a1 is {black,white,shadow_index,highlight_index},
 * four u16 values. CALL([d2,d3,a2,a3],16). No firmware placement is assigned.
 */
.section .text,"ax"
.global tone_endpoints
tone_endpoints:
 add -24,sp
 mov a0,(8,sp)
 mov a1,(12,sp)
 movhu (a1),d0
 mov d0,(0,sp)
 movhu (2,a1),d0
 mov d0,(4,sp)
 mov (0,sp),d0
 cmp 0,d0
 beq white_setup
 mov a0,a2
 movhu (4,a1),d0
 add d0,d0
 mov a2,a3
 add d0,a3
 movhu (a3),d1
 mov d1,d2
 mov (0,sp),d0
 sub d0,d2
 mov d1,d3
 lsr 1,d3
black_loop:
 cmp a3,a2
 bcc white_setup
 movhu (a2),d0
 mul d2,d0
 add d3,d0
 ext d0
 div d1,d0
 mov (0,sp),a0
 add a0,d0
 movhu d0,(a2)
 add 2,a2
 bra black_loop
white_setup:
 mov (4,sp),d0
 cmp 1023,d0
 beq endpoint_done
 mov (8,sp),a2
 mov (12,sp),a1
 movhu (6,a1),d0
 add d0,d0
 add d0,a2
 movhu (a2),d0
 mov d0,(16,sp)
 mov 1023,d1
 sub d0,d1
 mov (4,sp),d2
 sub d0,d2
 mov d1,d3
 lsr 1,d3
 add 2,a2
 mov (8,sp),a3
 add 512,a3
white_loop:
 cmp a3,a2
 bcc endpoint_done
 movhu (a2),d0
 mov (16,sp),a0
 sub a0,d0
 mul d2,d0
 add d3,d0
 ext d0
 div d1,d0
 mov (16,sp),a0
 add a0,d0
 movhu d0,(a2)
 add 2,a2
 bra white_loop
endpoint_done:
 mov 0,d0
 add 24,sp
 ret [d2,d3,a2,a3],16
