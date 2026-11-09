/* Copyright 2026 fishku (original contributions)
 * SPDX-License-Identifier: Apache-2.0
 * Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
 */
/* PEN-F 3101 HSL: wifi. */
/* Remote profile edits through the native application event path.
 * set_mcon mode = native ID, value = 0x485Axxxx, A=0/S,1/H,2/L.
 * xxxx is a signed 16-bit native value. Reserve the entire 485x family;
 * invalid marked requests must never fall through to the raw writer.
 * No new shared state: reuse the native pending triple/event/reply path.
 */
.section .wifi_ingress_hook,"ax"
 call wifi_recipe_ingress,[d2,d3,a2,a3],24
 nop
 nop
 nop

.section .wifi_receiver_hook,"ax"
 jmp wifi_recipe_bridge

.section .wifi_reader_hook,"ax"
 call wifi_recipe_read,[d2,d3],12

.section .wifi_bridge,"ax"
.global wifi_recipe_ingress, wifi_recipe_receive, wifi_recipe_validate
.global wifi_recipe_allowed
.global wifi_recipe_read

/* Replace the five-byte CALL with JMP. Return to its native EXTH/RET. */
wifi_recipe_bridge:
 call wifi_recipe_receive,[d2,d3,a2,a3],24
 jmp stock_receiver_return

/* Read-only capability discovery and H/L readback, via get_mcon.
 * FFFF -> HSL1 (48534c31); stock returns zero for this unmapped ID.
 * 8000|key -> H; C000|key -> L. Ordinary IDs retain stock behavior.
 * Unavailable/invalid extension reads -> 80000000, outside valid +/-7.
 * This discovery must precede ANY marked write from a future client.
 */
.section .wifi_read_head,"ax"
wifi_recipe_read:
 cmp 65535,d0
 bne wifi_read_value
 mov 0x48534c31,d0
 ret [d2,d3],12
wifi_read_value:
 mov d0,d2
 and 0x8000,d0
 beq 1f
 jmp wifi_read_hl
1:
 jmp wifi_read_stock
.section .wifi_read_tail,"ax"
wifi_read_hl:
 mov d2,d3
 and 0x4000,d3
 and 0x3fff,d2
 mov d2,d0
 sub 931,d0
 cmp 36,d0
 bcc wifi_read_bad
 call wifi_recipe_allowed,[],4
 cmp 1,d0
 bne wifi_read_bad
 mov d2,d0
 mov 1,d1
 call stock_active_get,[d2],8
 call hl_decode_cell,[],4
 cmp 0,d3
 beq wifi_read_hue
 asl 24,d0
 bra wifi_read_signed
wifi_read_hue:
 asl 28,d0
wifi_read_signed:
 asr 28,d0
 ret [d2,d3],12
wifi_read_bad:
 mov 0x80000000,d0
 ret [d2,d3],12

/* d0 ID, d1 marked value -> d0 bool. CALL [],4.
 * COLOR1..3 S/H/L +/-7; contrast +/-2; three tones/profile +/-7.
 * Deliberately no arbitrary setting IDs, WB, exposure, or profile recall.
 */
.section .wifi_validate,"ax"
wifi_recipe_validate:
 mov d0,a1
 mov d1,a0
 lsr 16,d1
 sub 0x4850,d1
 cmp 3,d1
 bcc wifi_validate_bad
 sub 931,d0
 cmp 36,d0
 bcs wifi_validate_seven
 cmp 0,d1
 bne wifi_validate_bad
 mov a1,d0
 sub 967,d0
 cmp 9,d0
 bcs wifi_validate_seven
 mov a1,d0
 sub 916,d0
 cmp 3,d0
 bcc wifi_validate_bad
 mov a0,d0
 exth d0
 cmp -2,d0
 blt wifi_validate_bad
 cmp 2,d0
 bgt wifi_validate_bad
 bra wifi_validate_good
wifi_validate_seven:
 mov a0,d0
 exth d0
 cmp -7,d0
 blt wifi_validate_bad
 cmp 7,d0
 bgt wifi_validate_bad
wifi_validate_good:
 mov 1,d0
 ret [],4
wifi_validate_bad:
 clr d0
 ret [],4

/* Current PASM bank only, no mode transaction, processing section loaded.
 * These are admission checks, NOT locks or a new atomic transaction.
 * CALL [],4. Only called in the application context before mutation.
 */
.section .wifi_allowed,"ax"
wifi_recipe_allowed:
 movbu (0x6189a4b0),d0
 cmp 0,d0
 bne wifi_allowed_bad
 mov (0xa1c58404),d0
 and 4,d0
 beq wifi_allowed_bad
 mov 41,d0
 call stock_get,[],4
 cmp 0,d0
 bne wifi_allowed_bad
 mov 1,d0
 ret [],4
wifi_allowed_bad:
 clr d0
 ret [],4

/* HTTP worker. d0 ID, d1 raw/marked value; return HTTP status.
 * Original unmarked raw behavior is preserved, including its weak ACK.
 * Marked writes use the same app event/wait as native set_camprop.
 */
wifi_ingress_raw:
 mov d2,d0
 call stock_raw_set,[d2,d3],12
 mov 200,d0
 ret [d2,d3,a2,a3],24
wifi_read_stock:
 mov d2,d0
 call stock_get,[],4
 ret [d2,d3],12
.section .wifi_body,"ax"
wifi_recipe_ingress:
 mov d0,d2
 mov d1,d3
 mov d1,d0
 and 0xfff00000,d0
 cmp 0x48500000,d0
 beq wifi_ingress_marked
 jmp wifi_ingress_raw
wifi_ingress_marked:
 mov d2,d0
 call wifi_recipe_validate,[],4
 cmp 1,d0
 bne wifi_ingress_bad
 mov d2,(0xa1c8a8b4)
 clr d0
 mov d0,(0xa1c8a8b8)
 mov d3,(0xa1c8a8bc)
 mov 0x041b0011,d0
 call stock_app_event,[d2,d3,a2,a3],36
 exth d0
 cmp 0,d0
 bne wifi_ingress_bad
 mov 200,d0
 ret [d2,d3,a2,a3],24
wifi_ingress_bad:
 mov 520,d0
 ret [d2,d3,a2,a3],24

/* Application helper CALL f0,24, same ABI as stock 607abd07.
 * Untagged -> original helper (including shutter/movie special cases).
 * Marked -> validated native setter or existing persistent H/L helpers.
 */
wifi_recipe_receive:
 mov d0,(4,sp)
 mov (a1),d0
 and 0xfff00000,d0
 cmp 0x48500000,d0
 beq wifi_receive_marked
 mov (4,sp),d0
 jmp stock_receive
wifi_receive_marked:
 cmp 1,d1
 bne wifi_receive_bad
 mov (4,sp),d2
 mov (a1),d3
 mov d2,d0
 mov d3,d1
 call wifi_recipe_validate,[],4
 cmp 1,d0
 bne wifi_receive_bad
 call wifi_recipe_allowed,[],4
 cmp 1,d0
 bne wifi_receive_bad
 mov d3,d1
 lsr 16,d1
 sub 0x4850,d1
 beq wifi_receive_scalar
 mov d3,d0
 exth d0
 mov d0,a0
 mov d2,d0
 call hl_active_set,[d2,d3,a2],20
 cmp 1,d0
 bne wifi_receive_bad
 call hl_publish,[],4
 call hl_refresh_profile,[],0
 clr d0
 ret [d2,d3,a2,a3],24
wifi_receive_scalar:
 mov d3,d1
 exth d1
 mov d2,d0
 call stock_public_set,[d2,d3],16
 cmp 0,d0
 bne wifi_receive_bad
 /* The public wrapper masks deeper errors. Verify its current value. */
 mov d2,d0
 call stock_get,[],4
 exth d3
 cmp d3,d0
 bne wifi_receive_bad
 clr d0
 ret [d2,d3,a2,a3],24
wifi_receive_bad:
 mov -1,d0
 ret [d2,d3,a2,a3],24
