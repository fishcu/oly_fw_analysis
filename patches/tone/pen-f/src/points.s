/* Shared canonical state: tagb,M4,W6,H6,S6,B6. Heights are fiveu16 B/S/M/H/W.
 * Public routines use CALL([d2,d3,a2,a3],16).
 * decode(d0word,a0heights)->word or0; resolve(d0word,a0rawHML,a1heights)->word.
 * edit(d0word,a0axis0..4,d1-1/0/+1)->word (0 resets that axis).
 * apply(a0LUT256,d0word)->0. The caller validates input samples0..1023.
 */
.section .text,"ax"
.global tone_decode,tone_resolve,tone_edit,tone_apply,tone_pack
tone_decode:
 mov d0,a2
 mov d0,d1
 lsr 28,d1
 cmp 11,d1
 bne point_invalid
 mov d0,d1
 lsr 24,d1
 and 15,d1
 cmp 15,d1
 beq point_invalid
 asl 5,d1
 add 288,d1
 movhu d1,(4,a0)
 mov a0,a3
 mov d0,d2
 mov 4,d3
point_decode_axis:
 mov d2,d0
 and 63,d0
 asl 4,d0
 cmp 1008,d0
 bne point_decode_store
 mov 1023,d0
point_decode_store:
 movhu d0,(a0)
 add 2,a0
 add -1,d3
 cmp 2,d3
 bne point_decode_next
 add 2,a0
point_decode_next:
 lsr 6,d2
 cmp 0,d3
 bne point_decode_axis
 mov a3,a0
 clr d1
 mov 5,d3
point_order:
 movhu (a0),d0
 cmp d1,d0
 bcs point_invalid
 mov d0,d1
 add 2,a0
 add -1,d3
 bne point_order
 mov a2,d0
 ret [d2,d3,a2,a3],16
point_invalid:
 clr d0
 ret [d2,d3,a2,a3],16

tone_pack:
 movhu (8,a0),d0
 lsr 4,d0
 asl 6,d0
 movhu (6,a0),d1
 lsr 4,d1
 or d1,d0
 asl 6,d0
 movhu (2,a0),d1
 lsr 4,d1
 or d1,d0
 asl 6,d0
 movhu (a0),d1
 lsr 4,d1
 or d1,d0
 movhu (4,a0),d1
 add -288,d1
 lsr 5,d1
 asl 24,d1
 or d1,d0
 or 0xb0000000,d0
 ret [d2,d3,a2,a3],16

tone_resolve:
 add -16,sp
 mov d0,d2
 mov a0,a2
 mov a1,a3
 mov a1,a0
 call tone_decode,[d2,d3,a2,a3],16
 cmp 0,d0
 bne point_resolved
 mov a2,a0
 mov 3,d3
point_legacy_validate:
 movhu (a0),d0
 exth d0
 cmp -7,d0
 blt point_neutral
 cmp 7,d0
 bgt point_neutral
 add 2,a0
 add -1,d3
 bne point_legacy_validate
 movhu (2,a2),d0
 exth d0
 asl 5,d0
 add 512,d0
 movhu d0,(4,a3)
 mov d0,d3
 movhu (4,a2),d0
 exth d0
 asl 4,d0
 add 256,d0
 cmp d3,d0
 bls point_legacy_shadow
 mov d3,d0
point_legacy_shadow:
 movhu d0,(2,a3)
 movhu (a2),d0
 exth d0
 asl 4,d0
 add 768,d0
 cmp d3,d0
 bcc point_legacy_highlight
 mov d3,d0
point_legacy_highlight:
 movhu d0,(6,a3)
 mov d2,d0
 lsr 20,d0
 cmp 0xa5d,d0
 beq point_legacy_endpoints
 mov 0xa5dffc00,d2
point_legacy_endpoints:
 mov d2,d0
 and 1023,d0
 call point_quantize,[],4
 movhu (2,a3),d1
 cmp d1,d0
 bls point_legacy_black
 mov d1,d0
point_legacy_black:
 movhu d0,(a3)
 mov d2,d0
 lsr 10,d0
 and 1023,d0
 call point_quantize,[],4
 movhu (6,a3),d1
 cmp d1,d0
 bcc point_legacy_white
 mov d1,d0
point_legacy_white:
 movhu d0,(8,a3)
 bra point_resolve_pack
point_neutral:
 mov point_defaults,a0
 mov a3,a1
 mov 5,d1
point_default_copy:
 movhu (a0),d0
 movhu d0,(a1)
 add 2,a0
 add 2,a1
 add -1,d1
 bne point_default_copy
point_resolve_pack:
 mov a3,a0
 call tone_pack,[d2,d3,a2,a3],16
point_resolved:
 add 16,sp
 ret [d2,d3,a2,a3],16

point_quantize:
 cmp 1007,d0
 bls point_quantize_regular
 mov 1023,d0
 ret [],4
point_quantize_regular:
 add 7,d0
 and -16,d0
 cmp 992,d0
 bls point_quantize_return
 mov 992,d0
point_quantize_return:
 ret [],4

tone_edit:
 add -20,sp
 mov a0,a2
 mov d1,d3
 mov sp,a0
 add 4,a0
 call tone_decode,[d2,d3,a2,a3],16
 cmp 0,d0
 beq point_edit_done
 mov a2,d2
 add d2,d2
 mov sp,a3
 add 4,a3
 add d2,a3
 movhu (a3),d0
 cmp 0,d3
 bne point_edit_relative
 mov point_defaults,a0
 movhu (d2,a0),d0
 bra point_edit_bounds
point_edit_relative:
 asl 4,d3
 cmp 2,a2
 bne point_edit_delta
 add d3,d3
point_edit_delta:
 add d3,d0
point_edit_bounds:
 clr d1
 cmp 0,a2
 beq point_edit_lower
 movhu (-2,a3),d1
point_edit_lower:
 mov 1023,d2
 cmp 4,a2
 beq point_edit_upper
 movhu (2,a3),d2
point_edit_upper:
 cmp 2,a2
 bne point_edit_quantized
 add 31,d1
 and -32,d1
 cmp 288,d1
 bge point_edit_middle_high
 mov 288,d1
point_edit_middle_high:
 and -32,d2
 cmp 736,d2
 ble point_edit_clamp
 mov 736,d2
 bra point_edit_clamp
point_edit_quantized:
 cmp 0,d0
 bge point_edit_positive
 clr d0
point_edit_positive:
 call point_quantize,[],4
point_edit_clamp:
 cmp d1,d0
 bge point_edit_low_ok
 mov d1,d0
point_edit_low_ok:
 cmp d2,d0
 ble point_edit_high_ok
 mov d2,d0
point_edit_high_ok:
 movhu d0,(a3)
 mov sp,a0
 add 4,a0
 call tone_pack,[d2,d3,a2,a3],16
point_edit_done:
 add 20,sp
 ret [d2,d3,a2,a3],16

tone_apply:
 add -16,sp
 mov a0,a2
 mov sp,a0
 add 4,a0
 call tone_decode,[d2,d3,a2,a3],16
 cmp 0,d0
 beq point_apply_done
 mov a2,a3
 add 512,a3
point_apply_loop:
 movhu (a2),d0
 asl 2,d0
 clr d1
point_interval:
 cmp 6,d1
 beq point_interval_found
 cmp 1023,d0
 bcs point_interval_found
 add -1023,d0
 add 2,d1
 bra point_interval
point_interval_found:
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
 movhu d0,(a2)
 add 2,a2
 cmp a3,a2
 bcs point_apply_loop
point_apply_done:
 clr d0
 add 16,sp
 ret [d2,d3,a2,a3],16
point_defaults:
 .short 0,256,512,768,1023
