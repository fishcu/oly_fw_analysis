/* OM-3 1.1 (build 1100) HSL editor and builder overlay. NOT tested on a camera.
 * State lives in the section-1 loaded tail; its lifetime across section reloads
 * is unqualified. See README.md and docs/color/om-3/. */
.section .state,"aw"
 .space 64,0
/* INFO keeps its native individual/all role. Delete (trash) switches axis:
 * the colour-direct screen forwards its native 0x9016 command to the focused
 * widget, and the colour page container consumes it for the colour editor. */
.section .delete_pointer,"a"
 .long hsl_delete_action
.section .label_hook,"ax"
 jmp label_get
 .fill 16,1,0xcb
.section .container_pointer,"a"
 .long hsl_container
.section .reset_hook,"ax"
 jmp reset_hook
 nop
.section .read_hook,"ax"
 jmp read_hook
 nop
 nop
.section .write_hook,"ax"
 jmp write_hook
 nop
 nop
.section .display_hook,"ax"
 jmp display_hook
.section .builder_hook,"ax"
 jmp builder_hook
.section .parent_hook,"ax"
 jmp parent_hook
.section .paint_pointer,"a"
 .long paint_axis

.section .extension,"ax"
/* Action-table entry of the SCP direct-setting screen for the Delete press
 * (0x9016). Stock ignores it unless setting 2163 is 1. Only in screen state
 * 0x0418 (colour/picture-mode direct page) forward it to the focused widget,
 * as the same screen already does for INFO. Elsewhere: stock. */
hsl_delete_action:
 mov d0,(axis+12)
 add -12,sp
 mov d1,(0,sp)
 mov a0,(4,sp)
 mov a1,(8,sp)
 clr d1
 movbu d1,(axis+9)
 movbu (a0),d0
 cmp 4,d0
 bne delete_restore
 movbu (1,a0),d0
 cmp 24,d0
 bne delete_restore
 mov 2163,d0
 call stock_get,[],4
 cmp 1,d0
 beq delete_restore
 mov 1,d0
 movbu d0,(axis+9)
delete_restore:
 mov (0,sp),d1
 mov (4,sp),a0
 mov (8,sp),a1
 add 12,sp
 movbu (axis+9),d0
 cmp 0,d0
 beq delete_stock
 mov (axis+12),d0
 jmp screen_forward
delete_stock:
 mov (axis+12),d0
 jmp stock_delete_action

/* Colour page container command method (vtable entry 0). Stock forwards INFO
 * to its focused child but drops 0x9016. Consume 0x9016 only when that child
 * is the 13-child colour editor whose cursor is a colour-selection setting. */
hsl_container:
 cmp 0x9016,d0
 bne container_stock
 add -4,sp
 mov a0,(sp)
 mov (76,a0),a0
 cmp 0,a0
 beq container_restore
 movhu (120,a0),d0
 cmp 13,d0
 bne container_restore
 mov (124,a0),a1
 cmp 0,a1
 beq container_restore
 movhu (80,a1),d0
 sub 2197,d0
 cmp 4,d0
 bcc container_restore
 add 4,sp
 movm [d2,d3,a2,a3],(sp)
 add -8,sp
 mov a0,a2
 mov a0,(axis+4)
 movbu (axis),d0
 inc d0
 cmp 3,d0
 bcs container_axis
 clr d0
container_axis:
 movbu d0,(axis)
 call refresh_children,[d2,d3,a2,a3],24
 mov (124,a2),a0
 mov 0x900c,d0
 clr d1
 mov (a0),a1
 mov (a1),a1
 calls (a1)
 mov 1,d0
 ret [d2,d3,a2,a3],24
container_restore:
 mov (sp),a0
 add 4,sp
 mov 0x9016,d0
container_stock:
 jmp stock_container

/* The native value label (stock "Vivid") reads the selected sector through
 * the generic settings getter, which is saturation-only. Re-run the stock read,
 * then substitute the active H/L value for colour IDs. Runs in the caller frame. */
label_get:
 call stock_settings,[],4
 mov (a0),a2
 mov (16,sp),d2
 mov (12,a2),a2
 exthu d2
 mov sp,a1
 add 32,a1
 mov d2,d0
 calls (a2)
 movbu (axis),d0
 cmp 0,d0
 beq label_get_done
 mov d2,d0
 sub 916,d0
 cmp 12,d0
 bcc label_get_done
 add -4,sp
 mov d3,(sp)
 mov d0,d3
 mov 903,d0
 call stock_get,[],4
 sub 1,d0
 cmp 4,d0
 bcc label_get_restore
 mov d0,d1
 asl 1,d0
 add d1,d0
 asl 2,d0
 add 928,d0
 add d3,d0
 call ui_read,[d2,d3,a2,a3],24
 mov d0,(36,sp)
label_get_restore:
 mov (sp),d3
 add 4,sp
label_get_done:
 jmp label_resume

/* During the native reset command, the stock saturation defaults are not
 * H/L defaults: reset the active experimental axis to zero instead. */
reset_hook:
 add -4,sp
 mov d0,(sp)
 mov 1,d0
 movbu d0,(axis+8)
 mov (sp),d0
 add 4,sp
 mov (a0),a1
 mov (a1),a1
 calls (a1)
 add -4,sp
 mov d0,(sp)
 clr d0
 movbu d0,(axis+8)
 mov (sp),d0
 add 4,sp
 jmp reset_resume

/* Capture only the 13-child colour editor parent; every pointer is checked
 * again before use. This replaces two stock setup instructions. */
parent_hook:
 add -8,sp
 mov d0,(0,sp)
 mov a1,(4,sp)
 movhu (120,a0),d0
 cmp 13,d0
 bne parent_restore
 mov (124,a0),a1
 cmp 0,a1
 beq parent_restore
 movhu (80,a1),d0
 sub 2197,d0
 cmp 4,d0
 bcc parent_restore
 mov a0,(axis+4)
parent_restore:
 mov (0,sp),d0
 mov (4,sp),a1
 add 8,sp
 mov a0,a2
 mov 0,a3
 mov 1,d3
 jmp parent_resume

/* Refresh the native enum indices so a new axis starts at its own value. */
refresh_children:
 mov (axis+4),a2
 cmp 0,a2
 beq refresh_done
 movhu (120,a2),d0
 cmp 13,d0
 bne refresh_done
 add 128,a2
 clr d3
refresh_loop:
 mov (a2),a3
 cmp 0,a3
 beq refresh_done
 movhu (80,a3),d0
 mov d0,d1
 sub 928,d1
 cmp 48,d1
 bcc refresh_done
 movhu (92,a3),d1
 cmp 11,d1
 bne refresh_done
 call ui_read,[d2,d3,a2,a3],24
 cmp -5,d0
 blt refresh_done
 cmp 5,d0
 bgt refresh_done
 mov 5,d1
 sub d0,d1
 movhu d1,(94,a3)
 add 4,a2
 inc d3
 cmp 12,d3
 bne refresh_loop
refresh_done:
 ret [d2,d3,a2,a3],24

read_hook:
 call ui_read,[d2,d3,a2,a3],24
 jmp read_resume
ui_read:
 mov d0,d2
 sub 928,d0
 cmp 48,d0
 bcc ui_read_stock
 movbu (axis),d3
 cmp 1,d3
 beq ui_read_alt
 cmp 2,d3
 bne ui_read_stock
ui_read_alt:
 mov d2,d0
 mov 1,d1
 call active_read,[d2],8
 call decode,[],4
 cmp 1,d3
 bne read_light
 asl 28,d0
 bra read_signed
read_light:
 asl 24,d0
read_signed:
 asr 28,d0
 ret [d2,d3,a2,a3],24
ui_read_stock:
 mov d2,d0
 call stock_get,[],4
 ret [d2,d3,a2,a3],24

write_hook:
 call ui_write,[d2,d3,a2,a3],24
 jmp write_resume
ui_write:
 mov d0,d2
 mov d1,d3
 mov a0,a2
 sub 928,d0
 cmp 48,d0
 bcc ui_write_stock
 movbu (axis),d0
 cmp 1,d0
 beq ui_write_alt
 cmp 2,d0
 bne ui_write_stock
ui_write_alt:
 movbu (axis+8),d0
 cmp 0,d0
 beq write_not_reset
 clr d3
write_not_reset:
 cmp -5,d3
 blt ui_write_end
 cmp 5,d3
 bgt ui_write_end
 mov d2,d0
 mov 1,d1
 call active_read,[d2],8
 call decode,[],4
 mov d3,d1
 and 15,d1
 movbu (axis),d3
 cmp 1,d3
 beq write_hue
 and 15,d0
 asl 4,d1
 bra write_merge
write_hue:
 and 240,d0
write_merge:
 or d1,d0
 mov d0,d1
 xor 255,d1
 asl 8,d1
 or d1,d0
 or 0x48310000,d0
 mov d0,a0
 mov d2,d0
 mov 1,d1
 call active_write,[d2],8
ui_write_end:
 mov 1,d0
 ret [d2,d3,a2,a3],24
ui_write_stock:
 mov d2,d0
 mov d3,d1
 mov a2,a0
 call stock_ui_write,[d2,d3,a2,a3],20
 ret [d2,d3,a2,a3],24

/* d0 packed cell -> validated H/L byte, or neutral */
decode:
 mov d0,d1
 lsr 16,d1
 cmp 0x4831,d1
 bne decode_zero
 mov d0,d1
 lsr 8,d1
 xor d0,d1
 and 255,d1
 cmp 255,d1
 bne decode_zero
 mov d0,d1
 asl 28,d1
 asr 28,d1
 cmp -5,d1
 blt decode_zero
 cmp 5,d1
 bgt decode_zero
 mov d0,d1
 asl 24,d1
 asr 28,d1
 cmp -5,d1
 blt decode_zero
 cmp 5,d1
 bgt decode_zero
 and 255,d0
 ret [],4
decode_zero:
 clr d0
 ret [],4

/* The stock descriptor points to 12 bytes at d2. */
display_hook:
 add -16,sp
 mov d1,(0,sp)
 mov a0,(4,sp)
 mov a1,(8,sp)
 mov d0,(12,sp)
 call display_values,[d2,d3,a2,a3],24
 mov (0,sp),d1
 mov (4,sp),a0
 mov (8,sp),a1
 mov (12,sp),d0
 add 16,sp
 mov 5,d0
 jmp display_resume
display_values:
 movbu (axis),d3
 cmp 1,d3
 beq display_active
 cmp 2,d3
 bne display_done
display_active:
 mov d2,a2
 mov 903,d0
 call stock_get,[],4
 sub 1,d0
 cmp 4,d0
 bcc display_done
 mov d0,d1
 asl 1,d0
 add d1,d0
 asl 2,d0
 add 928,d0
 mov d0,d2
 mov 12,a3
display_loop:
 mov d2,d0
 mov 1,d1
 call active_read,[d2],8
 call decode,[],4
 cmp 1,d3
 bne display_light
 asl 28,d0
 bra display_signed
display_light:
 asl 24,d0
display_signed:
 asr 28,d0
 movbu d0,(a2)
 inc a2
 inc d2
 add -1,a3
 cmp 0,a3
 bne display_loop
display_done:
 ret [d2,d3,a2,a3],24

/* Keep stock saturation input. Load current active profile's cells after
 * the builder. Per-image ownership remains unqualified. */
builder_hook:
 call color_builder,[d2,d3,a2,a3],96
 add -24,sp
 mov d0,(0,sp)
 mov d1,(4,sp)
 mov a0,(8,sp)
 mov a1,(12,sp)
 mov a2,(16,sp)
 mov a3,(20,sp)
 call apply_values,[d2,d3,a2,a3],24
 mov (0,sp),d0
 mov (4,sp),d1
 mov (8,sp),a0
 mov (12,sp),a1
 mov (16,sp),a2
 mov (20,sp),a3
 add 24,sp
 jmp builder_resume
apply_values:
 mov (12,a2),a2
 add 854,a2
 /* Only the four COLOR profile picture modes carry H/L: setting 901 is
  * 54, 55, 56 for COLOR1..3 and 64 for COLOR4 (observed in OM-Emu). Every
  * other picture mode keeps the stock builder output. */
 mov 901,d0
 call stock_get,[],4
 cmp 64,d0
 bne apply_not4
 mov 57,d0
apply_not4:
 sub 54,d0
 cmp 4,d0
 bcc apply_done
 mov d0,d1
 asl 1,d0
 add d1,d0
 asl 2,d0
 add 928,d0
 mov d0,d2
 mov 12,d3
apply_loop:
 mov d2,d0
 mov 1,d1
 call active_read,[d2],8
 call decode,[],4
 mov d0,a3
 asl 28,d0
 asr 28,d0
 add 7,d0
 add d0,d0
 mov hue_lut,a0
 movhu (d0,a0),d0
 movhu d0,(a2)
 mov a3,d0
 asl 24,d0
 asr 28,d0
 add 7,d0
 add d0,d0
 mov light_lut,a0
 movhu (d0,a0),d0
 movhu d0,(4,a2)
 add 24,a2
 inc d2
 add -1,d3
 bne apply_loop
apply_done:
 ret [d2,d3,a2,a3],24

/* This color-wheel view's paint method wraps the stock child painter.
 * Context layout is based on the matching OM-3 draw API, not PEN-F addresses. */
paint_axis:
 movm [d2,d3,a2,a3],(sp)
 add -24,sp
 mov a0,a2
 mov a1,(20,sp)
 call stock_paint,[a2,a3],16
 mov (20,sp),a1
 add -708,sp
 mov a1,(20,sp)
 mov d0,(16,sp)
 cmp 0,a1
 beq paint_done
 movhu (4,a1),d0
 cmp 2,d0
 bne paint_done
 mov (8,a1),a0
 cmp 0,a0
 beq paint_done
 mov (808,a2),a1
 cmp 0,a1
 beq paint_done
 movhu (8,a1),d0
 add 24,d0
 mov d0,(24,sp)
 mov sp,a3
 add 48,a3
 mov a3,a1
 mov 171,d1
paint_copy:
 mov (a0),d0
 mov d0,(a1)
 inc4 a0
 inc4 a1
 add -1,d1
 bne paint_copy
 mov a3,a0
 mov 1,d0
 call stock_font,[a2],8
 cmp 0,a0
 beq paint_done
 mov a0,(32,sp)
 mov 2,d0
 movhu d0,(52,a3)
 mov (24,sp),d0
 add -100,d0
 movhu d0,(40,sp)
 add 199,d0
 movhu d0,(44,sp)
 mov 16,d0
 movhu d0,(42,sp)
 mov 47,d0
 movhu d0,(46,sp)
 mov axis+16,a0
 call make_axis_label,[d2,d3,a2,a3],24
 mov axis+16,d1
 mov a3,a0
 mov sp,a1
 add 40,a1
 mov text_style,d0
 call stock_text,[d2,d3,a2,a3],16
 mov (24,sp),d0
 add -100,d0
 movhu d0,(40,sp)
 add 199,d0
 movhu d0,(44,sp)
 mov 50,d0
 movhu d0,(42,sp)
 mov 81,d0
 movhu d0,(46,sp)
 mov text_switch,d1
 mov a3,a0
 mov sp,a1
 add 40,a1
 mov text_style,d0
 call stock_text,[d2,d3,a2,a3],16
 mov (32,sp),a0
 call stock_font_release,[],4
paint_done:
 mov (16,sp),d0
 add 732,sp
 ret [d2,d3,a2,a3],16

/* Axis title: Saturation / Hue / Lightness. The selected value is shown by
 * the native value label, which follows the active axis. */
make_axis_label:
 mov a0,a2
 movbu (axis),d3
 mov text_saturation,a1
 cmp 1,d3
 bne label_not_hue
 mov text_hue,a1
 bra label_copy
label_not_hue:
 cmp 2,d3
 bne label_copy
 mov text_lightness,a1
label_copy:
 movhu (a1),d0
 movhu d0,(a2)
 add 2,a1
 add 2,a2
 cmp 0,d0
 bne label_copy
 ret [d2,d3,a2,a3],24
.balign 4
text_style:
 .long 10,15,15
 .byte 1,1
 .short 0,0,0,0,0
text_saturation:
 .short 'S','a','t','u','r','a','t','i','o','n',0
text_hue:
 .short 'H','u','e',0
text_lightness:
 .short 'L','i','g','h','t','n','e','s','s',0
text_switch:
 .short 'S','w','i','t','c','h',' ','@','A','0','3','3','@',0
.balign 2
hue_lut:
 .hword 7000,6000,5000,4000,3000,2000,1000,0,-1000,-2000,-3000,-4000,-5000,-6000,-7000
light_lut:
 .hword -300,-250,-200,-150,-100,-50,-25,0,25,50,100,150,200,250,300
