/* Tagged endpoint requests retain the registered high ID throughout the
 * native GUI transaction. Legal stock -7..7 values cannot match this tag. */
.section .tone_manager_gate,"ax"
.global tone_manager_gate, tone_manager, tone_profile, tone_bind
.global tone_info, tone_reference, tone_step

tone_manager_gate:
 movbu (0xa1c58404),d2
 btst 128,d2
 bne tone_manager_loaded
 jmp tone_manager_unavailable
tone_manager_loaded:
 jmp tone_manager
.section .tone_manager_unavailable,"ax"
tone_manager_unavailable:
 mov d1,d2
 lsr 20,d2
 cmp 0xa5d,d2
 bne tone_unavailable_stock
 mov d0,d2
 add -967,d2
 cmp 9,d2
 bcc tone_unavailable_stock
 clr d0
 ret [d2,d3,a2],16
tone_unavailable_stock:
 jmp stock_manager
.section .tone_editor,"ax"
tone_manager:
 mov d1,d2
 lsr 20,d2
 cmp 0xa5d,d2
 bne tone_manager_stock
 cmp 967,d0
 beq tone_manager_commit
 cmp 970,d0
 beq tone_manager_commit
 cmp 973,d0
 bne tone_manager_stock
tone_manager_commit:
 mov d0,d2
 mov a0,a2
 mov d1,a0
 mov 1,d1
 call stock_active_set,[d2],8
 call hl_publish,[],4
 cmp 967,d2
 beq tone_refresh1
 cmp 970,d2
 beq tone_refresh2
 call stock_color3_refresh,[],0
 bra tone_manager_finish
tone_refresh1:
 call stock_color1_refresh,[],0
 bra tone_manager_finish
tone_refresh2:
 call stock_color2_refresh,[],0
tone_manager_finish:
 jmp stock_manager_finish
tone_manager_stock:
 jmp stock_manager

/* a0:208-byte native tone actuator. d0:high ID or0. CALL([d2],8).
 * The immutable native table is the profile identity, independently of page. */
tone_profile:
 cmp 0,a0
 beq tone_profile_no
 mov (a0),d0
 cmp 0x60f4d350,d0
 bne tone_profile_no
 mov (188,a0),d0
 mov 967,d2
 cmp 0x60f4cd08,d0
 beq tone_profile_yes
 add 3,d2
 cmp 0x60f4cd40,d0
 beq tone_profile_yes
 add 3,d2
 cmp 0x60f4cd78,d0
 bne tone_profile_no
tone_profile_yes:
 mov d2,d0
 ret [d2],8
tone_profile_no:
 clr d0
 ret [d2],8

/* Exact COLOR records need no property24 branch: their first ID is never904
 * and their optional property is2000. Keep the two original records/stride. */
tone_bind:
 mov a0,a3
 call tone_profile,[d2],8
 cmp 0,d0
 beq tone_bind_stock
 movhu (194,a3),d1
 cmp 2,d1
 bhi tone_bind_stock
 mov d0,d2
 cmp 2,d1
 bne tone_bind_selected
 call tone_selected_id,[d2],8
 cmp 0,d0
 bne tone_bind_selected
 movhu d0,(194,a3)
tone_bind_selected:
 movhu (194,a3),d1
 mov d2,d0
 add 2,d0
 cmp 1,d1
 bne tone_bind_pair
 add -1,d0
 mov d0,d2
tone_bind_pair:
 mov d0,(160,a3)
 mov d0,(164,a3)
 mov d2,(168,a3)
 mov d0,(180,a3)
 mov d2,(184,a3)
 mov 2000,d0
 ret [d2,d3,a2,a3],28
tone_bind_stock:
 movhu (194,a3),d0
 cmp 2,d0
 bne tone_bind_native
 clr d0
 movhu d0,(194,a3)
tone_bind_native:
 mov a3,a0
 mov a0,d3
 mov 188,a3
 add d3,a3
 jmp stock_bind_resume

/* Entry at native INFO branch, inside its existing264-byte local frame.
 * Offset4 is the actuator;172..263 is the native92-byte parameter buffer. */
.macro near_jump target
 .byte 0xcc
 .short \target-(.-1)
.endm
.section .tone_resident,"ax"
tone_info:
 movbu (0xa1c58404),d0
 and 160,d0
 cmp 160,d0
 bne tone_info_native
 call tone_next_page,[],4
 cmp -1,d0
 bne tone_info_page
tone_info_native:
 mov (4,sp),a0
 mov (180,a0),d3
 mov d3,d0
 call tone_pair_id,[],4
 cmp 0,d0
 beq tone_info_middle
 mov d3,d0
 add -2,d0
 mov (4,sp),a0
 mov (184,a0),d1
 cmp d1,d0
 bne tone_info_middle
 mov 1,d0
 bra tone_info_page
tone_info_middle:
 mov d3,d0
 inc d0
 call tone_pair_id,[],4
 cmp 0,d0
 beq tone_info_generic
 mov (4,sp),a0
 mov (188,a0),a0
 mov (a0),d0
 call tone_pair_id,[],4
 cmp 0,d0
 beq tone_info_generic
 clr d0
tone_info_page:
 mov (4,sp),a0
 movhu d0,(194,a0)
 call tone_bind_gate,[d2,d3,a2,a3],28
 mov (4,sp),a0
 call stock_axis_eligibility,[a2,a3],12
.global tone_info_publish
tone_info_publish:
 mov sp,a2
 add 172,a2
 mov a2,a0
 mov 118,d0
 mov 92,d1
 call stock_parameter_get,[],4
 mov (4,sp),a0
 movhu (194,a0),d0
 inc d0
 movbu d0,(177,sp)
 mov a2,a0
 mov a3,a1
 mov 118,d0
 mov 92,d1
 call stock_parameter_set,[d2,a2],16
 mov (4,sp),a0
 mov (200,a0),d1
 cmp 1,d1
 beq tone_info_timer
 near_jump stock_event_finish
tone_info_timer:
 near_jump stock_info_timer
tone_info_generic:
 near_jump stock_info_generic
tone_pair_id:
 mov tone_pair_ids,a1
 mov 7,d1
tone_pair_scan:
 movhu (a1),d2
 cmp d2,d0
 beq tone_pair_yes
 add 2,a1
 add -1,d1
 bne tone_pair_scan
 clr d0
 ret [],4
tone_pair_yes:
 mov 1,d0
 ret [],4
tone_pair_ids:
 .short 897,969,972,975,1004,1007,1010

.section .tone_reference,"ax"
/* Current H/M/L, identity input and zero legacy contrast. Caller owns512B.
 * d0:profile high ID,a0:LUT. Return d0:signal bounds,d1:S|H<<10, or0.
 * CALL([d2,d3,a2,a3],16);48 local bytes, including raw12 and coefficients16. */
tone_reference:
 add -48,sp
 mov a0,a2
 mov d0,d2
 clr d3
 clr d0
 mov d0,(4,sp)
tone_reference_controls:
 mov d2,d0
 call stock_raw_get,[],4
 cmp -7,d0
 blt tone_reference_no
 cmp 7,d0
 bgt tone_reference_no
 mov sp,a0
 add 8,a0
 movhu d0,(d3,a0)
 add 2,d3
 inc d2
 cmp 6,d3
 bcs tone_reference_controls
 mov sp,a0
 add 4,a0
 mov sp,a1
 add 16,a1
 call stock_convert,[],16
 mov 0x605fdd38,a0
 mov a2,a1
 mov 256,d1
tone_reference_copy:
 movhu (a0),d0
 movhu d0,(a1)
 add 2,a0
 add 2,a1
 add -1,d1
 bne tone_reference_copy
 mov a2,a0
 mov sp,a1
 add 16,a1
 call tone_signal_bounds,[d2,d3,a2,a3],16
 mov d0,(36,sp)
 mov sp,a0
 add 4,a0
 call stock_tone_gate,[],0
 extbu d0
 cmp 0,d0
 beq tone_reference_done
 clr d0
 mov a2,a0
 mov sp,a1
 add 16,a1
 call stock_tone_apply,[d2,d3,a2,a3],16
tone_reference_done:
 mov (36,sp),d0
 mov d0,d1
 lsr 8,d1
 add d1,d1
 movhu (d1,a2),d1
 asl 10,d1
 and 255,d0
 add d0,d0
 movhu (d0,a2),d0
 or d0,d1
 mov (36,sp),d0
 bra tone_reference_return
tone_reference_no:
 clr d0
tone_reference_return:
 add 48,sp
 ret [d2,d3,a2,a3],16

/* d0:stored word,d1:signed code delta,a0:axis(0black/1white),a1:S|H<<10.
 * Clamp both effective heights before one relative edit. CALL(f0,16). */
tone_step:
 mov d1,a3
 mov a1,d2
 and 1023,d2
 mov a1,d3
 lsr 10,d3
 mov d0,d1
 lsr 20,d1
 cmp 0xa5d,d1
 beq tone_step_tagged
 mov 0xa5dffc00,d0
tone_step_tagged:
 mov d0,d1
 and 1023,d0
 lsr 10,d1
 and 1023,d1
 cmp d2,d0
 bls tone_step_black
 mov d2,d0
tone_step_black:
 cmp d3,d1
 bcc tone_step_white
 mov d3,d1
tone_step_white:
 cmp 0,a0
 bne tone_step_w
 add a3,d0
 cmp 0,d0
 bge tone_step_b_nonnegative
 clr d0
tone_step_b_nonnegative:
 cmp d2,d0
 bls tone_step_pack
 mov d2,d0
 bra tone_step_pack
tone_step_w:
 add a3,d1
 cmp 1023,d1
 ble tone_step_w_upper
 mov 1023,d1
tone_step_w_upper:
 cmp d3,d1
 bge tone_step_pack
 mov d3,d1
tone_step_pack:
 asl 10,d1
 or d1,d0
 or 0xa5d00000,d0
 ret [d2,d3,a2,a3],16

.section .tone_editor,"ax"

/* Concrete input callback adapter; a1 is its actuator, a2 native setter.
 * CALL([],0), self-saves. Tail to the unchanged setter with either the
 * original relative operation or an explicit tagged endpoint request. */
.global tone_input, tone_reset
tone_input:
 movm [d2,d3,a2,a3],(sp)
 add -532,sp
 mov d0,(12,sp)
 mov d1,(8,sp)
 mov a1,a2
 mov a0,a3
 mov a1,a0
 call tone_profile,[d2],8
 cmp 0,d0
 beq tone_input_stock
 movhu (194,a2),d1
 cmp 2,d1
 bne tone_input_stock
 mov d0,d2
 call tone_selected_id,[d2],8
 cmp 0,d0
 beq tone_input_stale
 mov (12,sp),d0
 sub d2,d0
 cmp 0,d0
 beq tone_input_white
 cmp 2,d0
 bne tone_input_cancel
 clr d3
 bra tone_input_curve
tone_input_white:
 mov 1,d3
tone_input_curve:
 mov d2,d0
 mov sp,a0
 add 16,a0
 call tone_reference,[d2,d3,a2,a3],16
 cmp 0,d0
 beq tone_input_cancel
 mov d1,(4,sp)
 mov d2,d0
 mov 1,d1
 call stock_active_get,[d2],8
 mov d3,a0
 mov (4,sp),a1
 mov (8,sp),d1
 cmp 1,d1
 beq tone_input_increase
 mov -16,d1
 bra tone_input_step
tone_input_increase:
 mov 16,d1
tone_input_step:
 call tone_step,[d2,d3,a2,a3],16
 mov d0,a1
 mov d2,d0
 clr d1
 bra tone_input_submit
tone_input_stock:
 mov (12,sp),d0
 mov (8,sp),d1
 mov 0,a1
tone_input_submit:
 mov a3,a0
 add 532,sp
 movm (sp),[d2,d3,a2,a3]
 jmp stock_gui_set
tone_input_stale:
 clr d0
 movhu d0,(194,a2)
tone_input_cancel:
 clr d0
 add 532,sp
 ret [d2,d3,a2,a3],16

/* Native held-OK reset event, in the existing event-handler frame. */
tone_reset:
 mov (4,sp),a0
 call tone_profile,[d2],8
 cmp 0,d0
 beq tone_reset_stock
 mov d0,d2
 mov (4,sp),a0
 movhu (194,a0),d0
 cmp 2,d0
 bne tone_reset_stock
 mov (20,sp),d0
 add -54,d0
 cmp 3,d0
 bcc tone_reset_stale
 mov d0,d1
 add d0,d0
 add d1,d0
 add 967,d0
 cmp d2,d0
 bne tone_reset_stale
 call stock_gui_service,[],4
 mov d2,d0
 clr d1
 mov 0xa5dffc00,a1
 call stock_gui_set,[],0
 mov (4,sp),a0
 mov (200,a0),d0
 cmp 1,d0
 bne tone_reset_done
 mov 500,d0
 mov 8000,d1
 call stock_timer,[d2,d3],12
 bra tone_reset_done
tone_reset_stale:
 mov (4,sp),a0
 clr d0
 movhu d0,(194,a0)
tone_reset_done:
 jmp stock_event_changed
tone_reset_stock:
.global tone_reset_original
tone_reset_original:
 mov (4,sp),a0
 clr d0
 mov d0,d2
 mov (180,a0),a0
 jmp stock_reset_resume

.section .tone_resident,"ax"
.global tone_input_gate, tone_reset_gate, tone_bind_gate
tone_input_gate:
 movm [d2],(sp)
 movbu (0xa1c58404),d2
 and 160,d2
 cmp 160,d2
 movm (sp),[d2]
 beq tone_input_loaded
 movhu (194,a1),d0
 cmp 2,d0
 beq tone_input_unavailable
 mov (a3),d0
 exthu d0
 mov 0,a1
 jmp stock_gui_set
tone_input_unavailable:
 clr d0
 ret [],0
tone_input_loaded:
 jmp tone_input

tone_bind_gate:
 movbu (0xa1c58404),d0
 and 160,d0
 cmp 160,d0
 beq tone_bind_loaded
 movhu (194,a0),d0
 cmp 2,d0
 bne tone_bind_original
 clr d0
 movhu d0,(194,a0)
tone_bind_original:
 mov a0,d3
 mov 188,a3
 add d3,a3
 near_jump stock_bind_resume
tone_bind_loaded:
 jmp tone_bind

tone_reset_gate:
 movbu (0xa1c58404),d0
 and 160,d0
 cmp 160,d0
 beq tone_reset_loaded
 mov (4,sp),a0
 movhu (194,a0),d0
 cmp 2,d0
 beq tone_reset_unavailable
 mov (4,sp),a0
 clr d0
 mov d0,d2
 mov (180,a0),a0
 near_jump stock_reset_resume
tone_reset_unavailable:
 near_jump stock_event_changed
tone_reset_loaded:
 jmp tone_reset

.global tone_input_arrow, tone_input_dial
tone_input_arrow:
 mov d3,a1
 call tone_input_gate,[],0
 mov (a3),d0
 ret [],4
tone_input_dial:
 mov (8,sp),a1
 call tone_input_gate,[],0
 mov (a3),d0
 mov (8,sp),a0
 ret [],4

.section .tone_editor,"ax"
tone_next_page:
 mov (8,sp),a0
 call tone_profile,[d2],8
 cmp 0,d0
 beq tone_next_native
 mov (24,sp),d1
 add -54,d1
 cmp 3,d1
 bcc tone_next_native
 mov d1,d2
 add d1,d1
 add d2,d1
 add 967,d1
 cmp d1,d0
 bne tone_next_native
 mov (8,sp),a0
 movhu (194,a0),d0
 inc d0
 cmp 3,d0
 bcs tone_next_return
 clr d0
 bra tone_next_return
tone_next_native:
 mov -1,d0
tone_next_return:
 ret [],4

.global tone_selected_id
tone_selected_id:
 mov d0,d2
 mov 111,d0
 call stock_raw_get,[],4
 add -54,d0
 cmp 3,d0
 bcc tone_selected_no
 mov d0,d1
 add d0,d0
 add d1,d0
 add 967,d0
 cmp d2,d0
 beq tone_selected_return
tone_selected_no:
 clr d0
tone_selected_return:
 ret [d2],8
