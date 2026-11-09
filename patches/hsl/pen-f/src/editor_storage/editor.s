/* Copyright 2026 fishku (original contributions)
 * SPDX-License-Identifier: Apache-2.0
 * Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
 */
/* PEN-F 3101 HSL: editor storage. */
/* Alignment correction: word-aligned native text style.
 * White labels above the wheel; shared sector selection.
 * Persistent COLOR1/2/3 H/S/L editor; follows native settings-bank saves.
 * Axis 0 = stock saturation, 1 = hue, 2 = lightness. The source's signed
 * low/high nibbles retain the physically tested H/L transport contract.
 * Qualification and packaging are separate from assembly.
 */
.section .hsl_set_hook,"ax"
 call hsl_set,[d2,d3,a2],16
.section .hsl_get_pointer,"a"
 .long hsl_get
.section .hsl_default_pointer,"a"
 .long hsl_default
.section .hsl_axis,"aw"
 .byte 0

.section .hsl_ui,"ax"
.global hsl_set, hsl_get, hsl_default, hsl_commit, hsl_after_commit
hsl_set:
 mov d0,d2
 sub 931,d2
 cmp 36,d2
 bcc hsl_stock_set
 mov (0xa1c58404),d3
 and 4,d3
 beq hsl_stock_set
 movbu (axis_uncached),d3
 sub 1,d3
 cmp 2,d3
 bcc hsl_stock_set
 cmp -7,d1
 blt hsl_reject
 cmp 7,d1
 bgt hsl_reject
 mov a0,a2
 mov d1,a0
 mov d3,d1
 inc d1
 mov d2,d0
 add 931,d0
hsl_commit:
 call hl_active_set,[d2,d3,a2],20
 cmp 1,d0
 bne hsl_reject
 call hl_publish,[],4
hsl_after_commit:
 add 931,d2
 call hl_refresh_profile,[],0
 jmp stock_manager_finish
hsl_reject:
 clr d0
 ret [d2,d3,a2],16
hsl_stock_set:
 jmp stock_manager

/* Keep stock inputs intact until the fallback decision. These vtable
 * methods have the original CALLS/RETF convention, with no extra frame. */
hsl_get:
 mov d0,d1
 exthu d1
 sub 931,d1
 cmp 36,d1
 bcc hsl_stock_get
 cmp 0,a1
 beq hsl_stock_get
 mov (0xa1c58404),d1
 and 4,d1
 beq hsl_stock_get
 movbu (axis_uncached),d1
 sub 1,d1
 cmp 2,d1
 bcc hsl_stock_get
 exthu d0
 sub 931,d0
 mov source_uncached,a0
 add d0,a0
 movbu (a0),d0
 cmp 0,d1
 beq hsl_get_hue
 asl 24,d0
 bra hsl_get_signed
hsl_get_hue:
 asl 28,d0
hsl_get_signed:
 asr 28,d0
 cmp -7,d0
 blt hsl_get_zero
 cmp 7,d0
 ble hsl_get_store
hsl_get_zero:
 clr d0
hsl_get_store:
 mov d0,(a1)
 clr d0
 retf [],0
hsl_stock_get:
 jmp stock_get

hsl_default:
 mov d0,d1
 exthu d1
 sub 931,d1
 cmp 36,d1
 bcc hsl_stock_default
 cmp 0,a1
 beq hsl_stock_default
 mov (0xa1c58404),d1
 and 4,d1
 beq hsl_stock_default
 movbu (axis_uncached),d1
 sub 1,d1
 cmp 2,d1
 bcc hsl_stock_default
 clr d0
 mov d0,(a1)
 retf [],0
hsl_stock_default:
 jmp stock_default

/* All three native request branches retain their cursor acquisition. Two
 * 3-byte jumps replace the first MOV in COLOR1/3; COLOR2 uses its existing
 * 149-byte replacement span. d2 holds the profile's first setting ID. */
.section .hsl_wheel1_hook,"ax"
 .byte 0xcc
 .short hsl_wheel1 - (.-1)
.section .hsl_wheel3_hook,"ax"
 .byte 0xcc
 .short hsl_wheel3 - (.-1)
.section .hsl_wheel,"ax"
.global hsl_wheel,hsl_wheel1,hsl_wheel3
hsl_wheel:
 mov 943,d2
 bra hsl_wheel_common
hsl_wheel1:
 mov 931,d2
 bra hsl_wheel_common
hsl_wheel3:
 mov 955,d2
hsl_wheel_common:
 mov (0xa1c58404),d0
 and 4,d0
 beq hsl_wheel_saturation
 movbu (axis_uncached),d1
 sub 1,d1
 cmp 2,d1
 bcc hsl_wheel_saturation
 mov d2,d0
 sub 931,d0
 mov source_uncached,a0
 add d0,a0
 mov d1,d2
 mov a2,a1
 mov 12,d1
hsl_wheel_loop:
 movbu (a0),d0
 cmp 0,d2
 beq hsl_wheel_hue
 asl 24,d0
 bra hsl_wheel_signed
hsl_wheel_hue:
 asl 28,d0
hsl_wheel_signed:
 asr 28,d0
 cmp -7,d0
 blt hsl_wheel_zero
 cmp 7,d0
 ble hsl_wheel_store
hsl_wheel_zero:
 clr d0
hsl_wheel_store:
 movbu d0,(a1)
 inc a0
 inc a1
 add -1,d1
 bne hsl_wheel_loop
 jmp wheel_resume
hsl_wheel_saturation:
hsl_wheel_saturation_loop:
 mov d2,d0
 call stock_raw_get,[],4
 movbu d0,(a2)
 inc d2
 inc a2
 mov sp,a0
 add 48,a0
 cmp a0,a2
 bne hsl_wheel_saturation_loop
 add -12,a2
 jmp wheel_resume
 .fill 149-(.-hsl_wheel),1,0xcb

/* Entry is the common dispatcher body, after its input registers are saved.
 * Both CALL and CALLS paths reach this site in stock firmware. */
.section .hsl_dispatch_hook,"ax"
 jmp hsl_dispatch
.section .hsl_cycle,"ax"
.global hsl_dispatch, hsl_cycle, hsl_cycle_commit, hsl_cycle_after_cache
hsl_dispatch:
 mov (16,sp),d0
 cmp 0x9016,d0
 bne hsl_dispatch_stock
 call hsl_cycle,[d2,d3,a2,a3],40
 cmp 0,d0
 beq hsl_dispatch_stock
 clr d0
 ret [d2,d3,a2,a3],48
hsl_dispatch_stock:
 mov (8,sp),a0
 call stock_fsm_descriptor,[],0
 jmp stock_dispatch_resume

/* ALL is a valid cursor/INFO state. Keep native INFO flags; refresh the
 * twelve children and invoke the stock viewer, including its ALL limits.
 * Modal and held-control guards remain.
 * CALL mask f0/frame40, locals: 4..15 staged indices; 16 viewer pointer; 20 first setting ID.
 * Validate every child before modifying any UI state. The count/value/
 * eligibility checks qualify our small no-allocation cache refresh, which
 * otherwise follows the stock +90 current-index representation.
 * Does not set image parameters or call the image-refresh service.
 */
hsl_cycle:
 cmp 0,a0
 beq hsl_cycle_no
 movbu (a0),d0
 cmp 2,d0
 bne hsl_cycle_no
 movbu (1,a0),d0
 cmp 2,d0
 bne hsl_cycle_no
 movhu (0x6161b81c),d0
 sub 0x13b2,d0
 cmp 3,d0
 bcc hsl_cycle_no
 mov d0,d1
 asl 1,d0
 add d1,d0
 asl 2,d0
 add 931,d0
 mov d0,(20,sp)
 mov (0xa1c58404),d0
 and 4,d0
 beq hsl_cycle_no
 .irp address,0x61618eb0,0x6161ad04
 mov (\address),d0
 cmp 0,d0
 bne hsl_cycle_no
 .endr
 mov (0x6161b810),a0
 cmp 0,a0
 beq hsl_cycle_no
 mov (4,a0),d0
 cmp 0,d0
 beq hsl_cycle_no
 mov d0,(16,sp)
 mov (a0),a2
 cmp 0,a2
 beq hsl_cycle_no
 movhu (100,a2),d0
 movhu (0x6161b81c),d1
 cmp d1,d0
 bne hsl_cycle_no
 movhu (120,a2),d0
 cmp 13,d0
 bne hsl_cycle_no
 /* Do not change axes midway through a held control/timer gesture. */
 mov (16,a2),d0
 cmp 0,d0
 bne hsl_cycle_no
 mov (44,a2),d0
 cmp 0,d0
 bne hsl_cycle_no
 mov (124,a2),a0
 cmp 0,a0
 beq hsl_cycle_no
 movhu (90,a0),d0
 cmp 13,d0
 bcc hsl_cycle_no
 add 128,a2
 movbu (axis_uncached),d3
 cmp 3,d3
 bcc hsl_cycle_no
 /* H -> S -> L -> H, starting with stock S at power-on. */
 add -1,d3
 cmp 0,d3
 bge hsl_cycle_axis
 mov 2,d3
hsl_cycle_axis:
 clr d2
hsl_cycle_child:
 mov (a2),a3
 cmp 0,a3
 beq hsl_cycle_no
 movhu (84,a3),d0
 mov (20,sp),d1
 sub d1,d0
 cmp d2,d0
 bne hsl_cycle_no
 movhu (88,a3),d0
 cmp 15,d0
 bne hsl_cycle_no
 mov (96,a3),a0
 mov (100,a3),a1
 cmp 0,a0
 beq hsl_cycle_no
 cmp 0,a1
 beq hsl_cycle_no
 mov 7,d1
hsl_cycle_validate_values:
 movhu (a0),d0
 cmp 0,d0
 bne hsl_cycle_no
 mov (a1),d0
 cmp d1,d0
 bne hsl_cycle_no
 add 2,a0
 add 4,a1
 add -1,d1
 cmp -8,d1
 bne hsl_cycle_validate_values
 cmp 0,d3
 beq hsl_cycle_saturation
 mov source_uncached-931,a0
 mov (20,sp),d0
 add d0,a0
 add d2,a0
 movbu (a0),d0
 cmp 1,d3
 beq hsl_cycle_hue
 asl 24,d0
 bra hsl_cycle_signed
hsl_cycle_hue:
 asl 28,d0
hsl_cycle_signed:
 asr 28,d0
 cmp -7,d0
 blt hsl_cycle_zero
 cmp 7,d0
 ble hsl_cycle_index
hsl_cycle_zero:
 clr d0
 bra hsl_cycle_index
hsl_cycle_saturation:
 mov (20,sp),d0
 add d2,d0
 call stock_raw_get,[],4
 cmp -7,d0
 blt hsl_cycle_no
 cmp 7,d0
 bgt hsl_cycle_no
hsl_cycle_index:
 mov 7,d1
 sub d0,d1
 mov sp,a0
 add 4,a0
 add d2,a0
 movbu d1,(a0)
 add 4,a2
 inc d2
 cmp 12,d2
 bne hsl_cycle_child
hsl_cycle_commit:
 /* Axis switching is not another notch of the last sector dial event.
  * The native screen observer has a draw-failure fallback which otherwise
  * repeats that notch and changes key1100 without its property-child cache.
  * This marker belongs to the existing GUI input state; no new cursor. */
 clr d0
 mov d0,(0x6161bf84)
 movbu d3,(axis_uncached)
 add -48,a2
 mov sp,a1
 add 4,a1
 mov 12,d2
hsl_cycle_write:
 mov (a2),a0
 movbu (a1),d0
 movhu d0,(90,a0)
 add 4,a2
 inc a1
 add -1,d2
 bne hsl_cycle_write
hsl_cycle_after_cache:
 mov (16,sp),a0
 call stock_viewer,[],0
 /* An identical selected value need not change display parameter179.
  * Request the wheel explicitly even for an all-zero axis switch. This
  * matches the selected COLOR screen observer's native request contract.
  * Rendering completes through the stock draw request path. */
 mov 65516,d0
 mov 1,d1
 mov 0,a0
 mov 2,a1
 call stock_draw_request,[d2,d3,a2],16
 mov 1,d0
 ret [d2,d3,a2,a3],40
hsl_cycle_no:
 clr d0
 ret [d2,d3,a2,a3],40

/* Stock editor construction now needs no hook: retaining the shared RAM
 * axis means simply leaving the stock entry instructions intact. */
.section .hsl_paint_pointer,"a"
 .long hsl_paint
.section .hsl_initial_update,"ax"
 jmp hsl_initial_adapter
.section .hsl_changed_update,"ax"
 jmp hsl_changed_adapter
.section .hsl_cycle,"ax"
.global hsl_update, hsl_paint
hsl_initial_adapter:
 call hsl_update,[d2,d3,a2,a3],60
 jmp stock_initial_resume
hsl_changed_adapter:
 call hsl_update,[d2,d3,a2,a3],60
 jmp stock_changed_resume
/* Keep the stock bitmap, sign and number geometry. Only the title/hint
 * need parent invalidation after the ordinary parameter observer update. */
hsl_update:
 mov a0,a3
 call stock_update,[d2,d3,a2,a3],60
 mov d0,(4,sp)
 call hsl_active,[],0
 cmp 0,d0
 beq hsl_update_done
 mov a3,a0
 mov 0,a1
 mov 1,d0
 call stock_invalidate,[],4
hsl_update_done:
 mov (4,sp),d0
 ret [d2,d3,a2,a3],60

/* Returns boolean in d0; does not touch the caller's object registers.
 * Only this screen's own vtable/update sites call the label routines. */
hsl_active:
 movhu (0x6161b81c),d0
 sub 0x13b2,d0
 cmp 3,d0
 bcc hsl_inactive
 mov (0xa1c58404),d0
 and 4,d0
 beq hsl_inactive
 mov 1,d0
 retf [],0
hsl_inactive:
 clr d0
 retf [],0

/* Clone the 684-byte drawing context on our stack,
 * keeping all brush/font/pen state private. Stock child paint runs first.
 * Layer1 owns backdrop, layer2 owns lettering; layer3 receives no additions.
 * The two layers prevent transparent glyph pixels punching into backdrop.
 * Small Switch uses existing24px bitmap letters; trash remains native32px.
 * No allocation beyond the stock text/font calls, no shared backend changes.
 * Frame: outgoing4..12, result16, job20, center24, layer28, font32,
 * rectangle40..47, private drawing context48..731. */
hsl_paint:
 movm [d2,d3,a2,a3],(sp)
 /* Keep the large private context out of stock recursive child paint. */
 add -24,sp
 mov a0,a2
 mov a1,(20,sp)
 call stock_paint,[a2,a3],16
 mov (20,sp),a1
 add -708,sp
 mov a1,(20,sp)
 mov d0,(16,sp)
 call hsl_active,[],0
 cmp 0,d0
 beq hsl_paint_done
 mov (20,sp),a0
 cmp 0,a0
 beq hsl_paint_done
 movhu (4,a0),d0
 sub 1,d0
 cmp 2,d0
 bcc hsl_paint_done
 mov d0,(28,sp)
 mov (8,a0),a0
 cmp 0,a0
 beq hsl_paint_done
 /* Stock Color heading child4: its selected-layout left edge is456/536.
  * Do not infer the wheel center from the800-wide outer container. */
 mov (808,a2),a1
 cmp 0,a1
 beq hsl_paint_done
 movhu (8,a1),d0
 add 24,d0
 mov d0,(24,sp)
 mov sp,a3
 add 48,a3
 mov a3,a1
 mov 171,d1
hsl_context_copy:
 mov (a0),d0
 mov d0,(a1)
 inc4 a0
 inc4 a1
 add -1,d1
 bne hsl_context_copy
 mov (24,sp),d0
 add -80,d0
 movhu d0,(40,sp)
 add 159,d0
 movhu d0,(44,sp)
 mov (28,sp),d0
 cmp 0,d0
 bne hsl_paint_text
 mov 12,d0
 movhu d0,(42,sp)
 mov 77,d0
 movhu d0,(46,sp)
 mov a3,a0
 mov -1,d0
 call stock_pen,[d2,d3,a2,a3],16
 mov a3,a0
 mov -2,d0
 mov -1,d1
 mov 2,a1
 call stock_brush,[d2,d3,a2],16
 mov a3,a0
 mov sp,a1
 add 40,a1
 call stock_rectangle,[d2,a2,a3],52
 bra hsl_paint_done
hsl_paint_text:
 mov a3,a0
 mov 1,d0
 call stock_font,[a2],8
 cmp 0,a0
 beq hsl_paint_done
 mov a0,(32,sp)
 mov 2,d0
 movhu d0,(52,a3)
 mov 16,d0
 movhu d0,(42,sp)
 mov 47,d0
 movhu d0,(46,sp)
 movbu (axis_uncached),d0
 mov hsl_saturation_text,d1
 cmp 1,d0
 bne hsl_title_not_hue
 mov hsl_hue_text,d1
 bra hsl_title_draw
hsl_title_not_hue:
 cmp 2,d0
 bne hsl_title_draw
 mov hsl_lightness_text,d1
hsl_title_draw:
 call hsl_text,[],4
 mov hsl_small_letters,a2
 mov (24,sp),d2
 add -54,d2
 mov 6,d3
hsl_small_loop:
 mov (a2),a1
 mov (16,a1),d0
 mov d0,(4,sp)
 clr d0
 mov d0,(8,sp)
 mov d0,(12,sp)
 mov d2,d0
 mov 50,d1
 mov a3,a0
 call stock_bitmap,[d2,d3,a2,a3],92
 add 12,d2
 inc4 a2
 add -1,d3
 bne hsl_small_loop
 mov (24,sp),d0
 add 17,d0
 movhu d0,(40,sp)
 add 47,d0
 movhu d0,(44,sp)
 mov 46,d0
 movhu d0,(42,sp)
 mov 77,d0
 movhu d0,(46,sp)
 mov hsl_switch_text,d1
 call hsl_text,[],4
hsl_paint_release:
 mov (32,sp),a0
 call stock_font_release,[],4
hsl_paint_done:
 mov (16,sp),d0
 add 732,sp
 ret [d2,d3,a2,a3],16
hsl_text:
 mov a3,a0
 mov sp,a1
 add 44,a1
 mov hsl_text_style,d0
 call stock_text,[d2,d3,a2,a3],252
 ret [],4
.balign 4
hsl_text_style:
 .long 4,15,15
 .byte 1,1
 .short 0,0,0,0,0
hsl_small_letters:
 .long 0xa2a95e00 /* bitmap2810 */
 .long 0xa2bc1984 /* bitmap4292 */
 .long 0xa2bc1108 /* bitmap4280 */
 .long 0xa2bc1730 /* bitmap4289 */
 .long 0xa2bc0cb0 /* bitmap4274 */
 .long 0xa2bc105c /* bitmap4279 */
hsl_saturation_text:
 .short 'S','a','t','u','r','a','t','i','o','n',0
hsl_hue_text:
 .short 'H','u','e',0
hsl_lightness_text:
 .short 'L','i','g','h','t','n','e','s','s',0
hsl_switch_text:
 .short '@','A','0','4','7','@',0
