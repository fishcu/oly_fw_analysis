/* Tagged five-point requests retain the registered high ID throughout the
 * native GUI transaction. Legal stock -7..7 values cannot match this tag. */
.section .tone_manager_gate,"ax"
.global tone_manager_gate, tone_manager, tone_profile, tone_bind
.global tone_info, tone_reference

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
 lsr 28,d2
 add -11,d2
 cmp 4,d2
 bcc tone_unavailable_stock
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
 lsr 28,d2
 add -11,d2
 cmp 4,d2
 bcc tone_manager_stock
 cmp 967,d0
 beq tone_manager_commit
 cmp 970,d0
 beq tone_manager_commit
 cmp 973,d0
 bne tone_manager_stock
tone_manager_commit:
 add -16,sp
 mov d2,d3
 mov d0,d2
 mov a0,a2
 mov d1,d0
 and 0x0fffffff,d0
 or 0xb0000000,d0
 mov sp,a0
 add 4,a0
 call tone_decode,[d2,d3,a2,a3],16
 cmp 0,d0
 beq tone_manager_reject
 mov d0,(4,sp)
 mov d2,d0
 mov d3,d1
 call tone_storage_id,[d2],8
 mov (4,sp),a0
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
 add 16,sp
 jmp stock_manager_finish
tone_manager_reject:
 add 16,sp
 ret [d2,d3,a2],16
tone_manager_stock:
 jmp stock_manager

/* a0:208-byte native tone actuator. d0:high ID or0. CALL([d2],8).
 * The immutable native table is the profile identity, independently of page. */
.section .tone_reference,"ax"
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
.section .tone_editor,"ax"
tone_bind:
 mov a0,a3
 call tone_profile,[d2],8
 cmp 0,d0
 beq tone_bind_stock
 movhu (194,a3),d1
 cmp 11,d1
 bls tone_bind_valid
 clr d1
 movhu d1,(194,a3)
tone_bind_valid:
 mov d0,d2
 call tone_selected_id,[d2],8
 cmp 0,d0
 bne tone_bind_selected
 movhu d0,(194,a3)
tone_bind_selected:
 movhu (194,a3),d0
 call tone_page_only,[],4
 mov d0,d1
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
 call tone_late_available,[],4
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
 call tone_page_only,[],4
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
.section .tone_pair_ids,"ax"
.balign 2
tone_pair_ids:
 .short 897,969,972,975,1004,1007,1010

.section .tone_reference,"ax"
.global tone_current,tone_channel_current,tone_channel_reference,tone_storage_id,tone_decode_selection
tone_current:
 clr d1
tone_channel_current:
 add -12,sp
 cmp 0,d1
 bne tone_current_rgb
 mov a0,a2
 mov d0,d2
 clr d3
point_current_raw:
 mov d2,d0
 call stock_raw_get,[],4
 mov sp,a0
 add 4,a0
 movhu d0,(d3,a0)
 add 2,d3
 inc d2
 cmp 6,d3
 bcs point_current_raw
 mov d2,d0
 add -3,d0
 mov 1,d1
 call stock_active_get,[d2],8
 mov sp,a0
 add 4,a0
 mov a2,a1
 call tone_resolve,[d2,d3,a2,a3],16
 add 12,sp
 ret [d2,d3,a2,a3],16

tone_current_rgb:
 mov a0,a2
 call tone_storage_id,[d2],8
 mov 1,d1
 call stock_active_get,[d2],8
 mov a2,a0
 call tone_decode,[d2,d3,a2,a3],16
 cmp 0,d0
 bne tone_current_rgb_done
 mov 0xb7ff0400,d0
 mov a2,a0
 call tone_decode,[d2,d3,a2,a3],16
tone_current_rgb_done:
 add 12,sp
 ret [d2,d3,a2,a3],16

tone_storage_id:
 mov d1,a0
 add -967,d0
 clr d1
 mov d1,mdr
 mov 3,d2
 divu d2,d0
 asl 3,d0
 mov a0,d1
 add d1,d1
 add d1,d0
 mov tone_storage_ids,a0
 movhu (d0,a0),d0
 ret [d2],8

tone_decode_selection:
 cmp 12,d0
 bcs tone_selection_valid
 clr d0
tone_selection_valid:
 clr d1
 mov d1,mdr
 mov 3,d1
 divu d1,d0
 mov d0,d1
 mov mdr,d0
 ret [],4

tone_reference:
 clr d1
tone_channel_reference:
 add -16,sp
 mov a0,a2
 mov sp,a0
 add 4,a0
 call tone_channel_current,[d2,d3,a2,a3],16
 mov d0,d3
 mov 0x605fdd38,a0
 mov a2,a1
 mov 256,d1
point_reference_copy:
 movhu (a0),d0
 movhu d0,(a1)
 add 2,a0
 add 2,a1
 add -1,d1
 bne point_reference_copy
 mov a2,a0
 mov d3,d0
 call tone_apply,[d2,d3,a2,a3],16
 mov d3,d0
 add 16,sp
 ret [d2,d3,a2,a3],16

.section .tone_reference,"ax"
.global tone_input,tone_reset
tone_input:
 movm [d2,d3,a2,a3],(sp)
 add -32,sp
 mov d0,(12,sp)
 mov d1,(8,sp)
 mov a1,a2
 mov a0,a3
 mov a1,a0
 call tone_profile,[d2],8
 cmp 0,d0
 beq tone_input_stock
 mov d0,d2
 movhu (194,a2),d1
 cmp 11,d1
 bhi tone_input_stale
 call tone_selected_id,[d2],8
 cmp 0,d0
 beq tone_input_stale
 movhu (194,a2),d0
 call tone_decode_selection,[],4
 mov d1,(28,sp)
 mov d0,d1
 cmp 1,d1
 beq tone_input_middle
 clr d3
 cmp 0,d1
 bne tone_input_outer
 mov 1,d3
tone_input_outer:
 mov (12,sp),d0
 sub d2,d0
 cmp 2,d0
 beq tone_input_state
 cmp 0,d0
 bne tone_input_cancel
 mov 4,d0
 sub d3,d0
 mov d0,d3
 bra tone_input_state
tone_input_middle:
 mov 2,d3
tone_input_state:
 mov (28,sp),d1
 mov d2,d0
 mov sp,a0
 add 16,a0
 call tone_channel_current,[d2,d3,a2,a3],16
 mov d3,a0
 mov (8,sp),d1
 cmp 1,d1
 beq tone_input_increase
 mov -1,d1
 bra tone_input_step
tone_input_increase:
 mov 1,d1
tone_input_step:
 call tone_edit,[d2,d3,a2,a3],16
 mov (28,sp),d1
 asl 28,d1
 add d1,d0
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
 add 32,sp
 movm (sp),[d2,d3,a2,a3]
 jmp stock_gui_set
tone_input_stale:
 clr d0
 movhu d0,(194,a2)
tone_input_cancel:
 clr d0
 add 32,sp
 ret [d2,d3,a2,a3],16

.section .tone_editor,"ax"
tone_reset:
 mov (4,sp),a0
 call tone_profile,[d2],8
 cmp 0,d0
 beq tone_reset_stock
 mov d0,d2
 mov (4,sp),a0
 movhu (194,a0),d3
 cmp 11,d3
 bhi tone_reset_stale
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
 add -20,sp
 mov d3,d0
 call tone_decode_selection,[],4
 mov d0,d3
 mov d1,(4,sp)
 mov d2,d0
 mov sp,a0
 add 8,a0
 call tone_channel_current,[d2,d3,a2,a3],16
 mov 2,a0
 cmp 1,d3
 beq tone_reset_axis
 mov 1,a0
 cmp 0,d3
 beq tone_reset_axis
 mov 0,a0
tone_reset_axis:
 clr d1
 call tone_edit,[d2,d3,a2,a3],16
 cmp 1,d3
 beq tone_reset_submit
 mov 3,a0
 cmp 0,d3
 beq tone_reset_second
 mov 4,a0
tone_reset_second:
 clr d1
 call tone_edit,[d2,d3,a2,a3],16
tone_reset_submit:
 mov (4,sp),d1
 asl 28,d1
 add d1,d0
 mov d0,(4,sp)
 call stock_gui_service,[],4
 mov d2,d0
 clr d1
 mov (4,sp),a1
 call stock_gui_set,[],0
 add 20,sp
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
 add -4,sp
 call tone_late_available,[],4
 beq tone_input_loaded
 call tone_color_page,[],4
 beq tone_input_unavailable
 mov (a3),d0
 exthu d0
 mov 0,a1
 add 4,sp
 jmp stock_gui_set
tone_input_unavailable:
 clr d0
 add 4,sp
 ret [],0
tone_input_loaded:
 mov (a3),d0
 exthu d0
 add 4,sp
 jmp tone_input

tone_bind_gate:
 call tone_late_available,[],4
 beq tone_bind_loaded
 mov a0,a1
 call tone_color_page,[],4
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
 call tone_late_available,[],4
 beq tone_reset_loaded
 mov (4,sp),a0
 mov a0,a1
 call tone_color_page,[],4
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

.section .tone_reference,"ax"
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
 call tone_decode_selection,[],4
 inc d0
 cmp 3,d0
 bcs tone_next_recombine
 clr d0
tone_next_recombine:
 mov d1,d2
 add d1,d1
 add d2,d1
 add d1,d0
 bra tone_next_return
tone_next_native:
 mov -1,d0
tone_next_return:
 ret [],4

.section .tone_selected,"ax"
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

.section .tone_resident,"ax"
/* Flags-only resident checks; do not consult any unavailable late helper. */
tone_late_available:
 movbu (0xa1c58404),d0
 and 160,d0
 cmp 160,d0
 ret [],4
tone_color_page:
 mov (188,a1),d0
 add -0x60f4cd08,d0
 beq tone_color_page_return
 cmp 56,d0
 beq tone_color_page_return
 cmp 112,d0
tone_color_page_return:
 ret [],4

.section .tone_page,"ax"
.global tone_page_only
tone_page_only:
 cmp 12,d0
 bcs tone_page_reduce
 clr d0
tone_page_reduce:
 cmp 3,d0
 bcs tone_page_done
 add -3,d0
 bra tone_page_reduce
tone_page_done:
 ret [],4

.section .tone_dispatch_gate,"ax"
.global tone_dispatch_gate
tone_dispatch_gate:
 movbu (0xa1c58404),d0
 and 160,d0
 cmp 160,d0
 bne tone_dispatch_stock
 jmp tone_dispatch
tone_dispatch_stock:
 jmp hsl_dispatch

.section .tone_editor,"ax"
tone_dispatch:
 mov (16,sp),d0
 cmp 0x9016,d0
 beq tone_dispatch_tone
 jmp hsl_dispatch
tone_dispatch_tone:
 add -4,sp
 mov a0,(sp)
 call tone_cycle,[d2,d3,a2,a3],40
 mov (sp),a0
 add 4,sp
 cmp 0,d0
 bne tone_dispatch_done
 jmp hsl_dispatch
tone_dispatch_done:
 clr d0
 ret [d2,d3,a2,a3],48
.global tone_cycle
tone_cycle:
 cmp 0,a0
 beq tone_cycle_no
 movbu (a0),d0
 cmp 2,d0
 bne tone_cycle_no
 movbu (1,a0),d0
 cmp 2,d0
 bne tone_cycle_no
 .irp address,0x61618eb0,0x6161ad04
 mov (\address),d0
 cmp 0,d0
 bne tone_cycle_no
 .endr
 mov (0x6161b810),a0
 cmp 0,a0
 beq tone_cycle_no
 mov (4,a0),d0
 cmp 0,d0
 beq tone_cycle_no
 mov d0,(16,sp)
 mov (a0),a2
 mov a2,a0
 call tone_profile,[d2],8
 cmp 0,d0
 beq tone_cycle_no
 call tone_selected_id,[d2],8
 cmp 0,d0
 beq tone_cycle_no
 .irp offset,16,44
 mov (\offset,a2),d0
 cmp 0,d0
 bne tone_cycle_no
 .endr
 movhu (194,a2),d0
 cmp 12,d0
 bcc tone_cycle_no
 add 3,d0
 cmp 12,d0
 bcs tone_cycle_commit
 add -12,d0
tone_cycle_commit:
 movhu d0,(194,a2)
 clr d0
 mov d0,(0x6161bf84)
 mov (16,sp),a0
 mov (a0),a1
 mov (a1),a1
 calls (a1)
 mov 65516,d0
 mov 1,d1
 mov 0,a0
 mov 2,a1
 call stock_draw_request,[d2,d3,a2],16
 mov 1,d0
 ret [d2,d3,a2,a3],40
tone_cycle_no:
 clr d0
 ret [d2,d3,a2,a3],40
