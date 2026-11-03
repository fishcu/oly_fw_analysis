/* OM-5 Mark II 1.1 (E148, build 1100) HSL editor and builder overlay, ported
 * from the OM-3 patch. NOT tested on a camera; exercised in OM-Emu only.
 * Code and state live in the FF tails inside the loaded extents of sections 2,
 * 6, 7 and 8. E148 loads all ten sections once at boot (8 before 2) and never clears their
 * loaded bits (loader 0x60046418, bits 0xa26e2698). See README.md. */
.section .state,"aw"
 .space 64,0
/* INFO keeps its native individual/all role. Delete (trash) switches axis:
 * the colour-direct screen forwards its native 0x9016 command to the focused
 * widget, and the colour page container consumes it for the colour editor. */
.section .delete_pointer,"a"
 .long hsl_delete_action
.section .label_hook,"ax"
 jmp label_get
 .fill 5,1,0xcb
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
 nop
 nop
.section .builder_hook,"ax"
 jmp builder_hook
.section .parent_hook,"ax"
 jmp parent_hook
.section .paint_pointer,"a"
 .long paint_axis
.section .pages_hook,"ax"
 jmp pages_hook
 nop
 nop

.section .ext7,"ax"
/* Action-table entry of the SCP direct-setting screen for the Delete press
 * (0x9016). Stock ignores it unless setting 2163 is 1. Only in screen state
 * 0x0418 (colour/picture-mode direct page) forward it to the focused widget,
 * as the same screen already does for INFO. Elsewhere: stock. */
hsl_delete_action:
 mov d0,(axis+12)
 add -16,sp
 mov d1,(4,sp)
 mov a0,(8,sp)
 mov a1,(12,sp)
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
 mov (4,sp),d1
 mov (8,sp),a0
 mov (12,sp),a1
 add 16,sp
 movbu (axis+9),d0
 cmp 0,d0
 beq delete_stock
 mov 0x9016,d0
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
 cmp 8,d0
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

/* The native value label (stock "Vivid +n", 0x60e4ad08..0x60e4ae5e) reads the
 * selected sector's stored profile cell (IDs 928-975) through the settings
 * object's getter into (36,sp). Re-run that call, then substitute the active
 * H/L value. Runs in the caller frame; replaces calls (a2) + the next two
 * instructions, which are replayed. */
label_get:
 calls (a2)
 movbu (axis),d0
 cmp 0,d0
 beq label_get_done
 mov d2,d0
 exthu d0
 sub 928,d0
 cmp 48,d0
 bcc label_get_done
 mov d2,d0
 exthu d0
 call ui_read,[d2,d3,a2,a3],24
 mov d0,(36,sp)
label_get_done:
 mov (12,sp),d0
 mov label_format,a1
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
 cmp 8,d0
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

/* This color-wheel view's paint method wraps the stock child painter.
 * Context layout is based on the matching OM-3 draw API, not PEN-F addresses. */
paint_axis:
 movm [d2,d3,a2,a3],(sp)
 add -24,sp
 mov a0,a2
 mov a1,(20,sp)
 call stock_paint,[a2,a3],16
 mov (20,sp),a1
 add -40,sp
 mov a1,(20,sp)
 mov d0,(16,sp)
 cmp 0,a1
 beq paint_done
 movhu (4,a1),d0
 cmp 2,d0
 bne paint_done
 mov (8,a1),a3
 cmp 0,a3
 beq paint_done
 mov (808,a2),a1
 cmp 0,a1
 beq paint_done
 movhu (8,a1),d0
 add 24,d0
 mov d0,(24,sp)
 /* Draw with the caller's paint context in place. stock_font only sets its
  * font at +76 (0x60d51fa2) and the style below changes +52; both are put
  * back afterwards. (OM-3 copied 684 bytes of context to the stack.) */
 movhu (52,a3),d0
 mov d0,(48,sp)
 mov (76,a3),d0
 mov d0,(52,sp)
 mov a3,a0
 mov 1,d0
 call stock_font,[a2],8
 cmp 0,a0
 beq paint_restore
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
paint_restore:
 mov (48,sp),d0
 movhu d0,(52,a3)
 mov (52,sp),d0
 mov d0,(76,a3)
paint_done:
 mov (16,sp),d0
 add 64,sp
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
 .short 'S','w','i','t','c','h',' ','@','A','0','3','4','@',0

.section .ext6,"ax"
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

/* Wheel values: the reader 0x60a339e4, descriptor kind 6 (Color Profile),
 * leaves 12 sector bytes at a2 = sp+88 and the profile (setting 903) in d2.
 * Replaces the 7-byte call at the shared tail 0x60a33eac. */
display_hook:
 movbu (axis),d0
 cmp 0,d0
 beq display_stock
 mov (a3),d0
 cmp 6,d0
 bne display_stock
 mov sp,a0
 add 88,a0
 cmp a2,a0
 bne display_stock
 call display_values,[d2,d3,a2,a3],24
display_stock:
 call stock_display_next,[],4
 jmp display_resume
display_values:
 movbu (axis),d3
 mov d2,d0
 exthu d0
 sub 1,d0
 cmp 3,d0
 bcs display_profile
 clr d0
display_profile:
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
 ret [d2,d3,a2,a3],24


/* E148 keeps the Color Profile detail pages but no longer shows them: the
 * picture-mode direct screen creates children 2-5 and its visibility updater
 * (0x60dad4eb) never touches them. E147 shows them from its data-275 flags
 * (0x611358eb..0x61135a23). E148's data-277 struct still carries the focus
 * flags: +245 colour item, +247 tone item (E147 offsets - 32). This replaces
 * the updater's last call (0x60dad5f5) and then shows child 4 (colour wheel)
 * or child 2 (tone curve) for Color Profile 1-3 only. Registers: d2 = data
 * struct, a3 = direct-screen controller; the stock ret restores them. */
pages_hook:
 call direct_layout,[d2,d3,a2,a3],160
 mov 111,d0
 call stock_get,[],4
 sub 54,d0
 cmp 3,d0
 bcc pages_off
 mov d2,a0
 movbu (245,a0),d0
 mov 4,d1
 call show_page,[d2,d3,a2,a3],24
 mov d2,a0
 movbu (247,a0),d0
 mov 2,d1
 call show_page,[d2,d3,a2,a3],24
 jmp direct_ret
pages_off:
 clr d0
 mov 4,d1
 call show_page,[d2,d3,a2,a3],24
 clr d0
 mov 2,d1
 call show_page,[d2,d3,a2,a3],24
 jmp direct_ret

/* d0 = flag byte, d1 = child index, a3 = controller */
show_page:
 mov d0,d2
 cmp 1,d2
 beq show_on
 clr d2
show_on:
 mov a3,a0
 mov d1,d0
 call child_get,[],0
 cmp 0,a0
 beq show_done
 mov a0,a2
 cmp 0,d2
 beq show_set
 call page_layout,[d2,d3,a2,a3],24
show_set:
 mov a2,a0
 mov d2,d0
 call set_visible,[d2,d3,a2],16
show_done:
 ret [d2,d3,a2,a3],24

/* The pages carry the OM-1/OM-3 layout (900x600 content on an 800x600 page).
 * E148's panels are 720x480, exactly 4/5 of it: scale the page and its view,
 * and move each label so its centre scales (its size and font stay). Runs once
 * per page: a scaled page is at most 720 wide. a0 = page. */
page_layout:
 mov a0,a2
 mov (36,a2),a3
 cmp 0,a3
 beq layout_done
 mov 12,d2
 mov (a3),d0
 cmp 0x610c14a0,d0
 beq layout_view
 mov 18,d2
 cmp 0x610d6560,d0
 bne layout_done
layout_view:
 movhu (12,a2),d0
 cmp 720,d0
 bls layout_done
 movhu (12,a3),d1
 cmp d1,d0
 bcc layout_w
 mov d1,d0
layout_w:
 call scale,[],4
 movhu d0,(12,a2)
 movhu (14,a2),d0
 movhu (14,a3),d1
 cmp d1,d0
 bcc layout_h
 mov d1,d0
layout_h:
 call scale,[],4
 movhu d0,(14,a2)
 mov a2,a1
 call scale_pos,[],4
 mov a3,a1
 call scale_pos,[],4
 movhu (12,a3),d0
 call scale,[],4
 movhu d0,(12,a3)
 movhu (14,a3),d0
 call scale,[],4
 movhu d0,(14,a3)
 clr d3
layout_child:
 mov a3,a0
 add 792,a0
 mov d3,d0
 asl2 d0
 mov (d0,a0),a1
 cmp 0,a1
 beq layout_next
 call centre1,[],4
 add 2,a1
 call centre1,[],4
layout_next:
 inc d3
 cmp d2,d3
 bcs layout_child
layout_done:
 ret [d2,d3,a2,a3],24

/* a1 = view: scale x, y */
scale_pos:
 movhu (8,a1),d0
 call scale,[],4
 movhu d0,(8,a1)
 movhu (10,a1),d0
 call scale,[],4
 movhu d0,(10,a1)
 ret [],4

/* a1 -> position at (8,a1), size at (12,a1): keep size, scale the centre */
centre1:
 movhu (8,a1),d0
 exth d0
 add d0,d0
 movhu (12,a1),d1
 add d1,d0
 call scale,[],4
 movhu (12,a1),d1
 sub d1,d0
 asr 1,d0
 movhu d0,(8,a1)
 ret [],4

/* d0 = d0 * 4/5 (signed halfword in, 0xccd/4096) */
scale:
 exth d0
 mov 0xccd,d1
 mul d1,d0
 asr 12,d0
 ret [],4

.section .ext2,"ax"
/* Keep stock saturation input. Load current active profile's cells after
 * the builder. Per-image ownership remains unqualified. */
builder_hook:
 call color_builder,[d2,d3,a2,a3],96
 add -28,sp
 mov d0,(4,sp)
 mov d1,(8,sp)
 mov a0,(12,sp)
 mov a1,(16,sp)
 mov a2,(20,sp)
 mov a3,(24,sp)
 call apply_values,[d2,d3,a2,a3],24
 mov (4,sp),d0
 mov (8,sp),d1
 mov (12,sp),a0
 mov (16,sp),a1
 mov (20,sp),a2
 mov (24,sp),a3
 add 28,sp
 jmp builder_resume
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

.balign 2
hue_lut:
 .hword 7000,6000,5000,4000,3000,2000,1000,0,-1000,-2000,-3000,-4000,-5000,-6000,-7000
light_lut:
 .hword -300,-250,-200,-150,-100,-50,-25,0,25,50,100,150,200,250,300

/* E148's picture-mode refresh (0x602e00bf, jump table 0x60499718) has no case
 * for 111 = 54..56: Color Profile 1..3 fall to its default, so the profile's
 * own Sharpness, Contrast, per-sector saturation, Shading and tone curve never
 * reach the effective settings the image pipeline reads. E147 handles them in
 * its refresh 0x604032a4 (cases 54..56) and its caller 0x604040ff. This
 * replays that at the end of E148's refresh (0x602e0826), in the same frame:
 *   struct +0 contrast  = 908+p  (caller writes ID 8)
 *   struct +4 sharpness = 904+p  (ID 7)
 *   struct +8 = 0 (ID 59), +20 = 1 (ID 105), +24 = 0 (ID 1806)
 *   effective 916..927 = 928+12p .. 939+12p  (store 1 -> store 2)
 *   effective 1016 = shading 912+p, 1011 = 0, 998 = 0
 *   effective 383 / 690 / 382 = 976+3p / 977+3p / 978+3p (store 2)
 * Other picture modes get E147's zeros for the extra IDs, written only after a
 * Color Profile may have set them (flag starts set: effective settings survive
 * power-off). The code sits in section 8, which E148 loads before section 2. */
.section .refresh_hook,"ax"
 jmp refresh_guard
 nop
/* Section 2 tail: run the section-8 code only once section 8 is loaded (bit 7
 * of the loader's bits; boot loads it before section 2, so this is a guard). */
/* Jump-table cases 54..56 (stock: the default 0x602e06ca). Note the profile
 * for the tail, then take the stock default path unchanged. */
.section .refresh_cases,"a"
 .long refresh_case,refresh_case,refresh_case
.section .refresh_guard,"ax"
refresh_case:
 mov d2,d0
 lsr 2,d0
 sub 54,d0
 movbu d0,(refresh_profile)
 jmp refresh_default
refresh_profile:
 .byte 0xff
refresh_guard:
 movbu (loaded_bits),d0
 btst 0x80,d0
 beq refresh_stock
 jmp refresh_tail
refresh_stock:
 mov (12,sp),a0
 clr d0
 mov d3,(76,a0)
 ret [d2,d3,a2,a3],96
.section .creset_hook,"ax"
 jmp creset
.section .ext8,"ax"
refresh_tail:
 mov (12,sp),a0
 clr d0
 mov d3,(76,a0)
 movbu (refresh_profile),d0
 mov 0xff,d1
 movbu d1,(refresh_profile)
 cmp 3,d0
 bcs refresh_color
 movbu (refresh_dirty),d0
 cmp 0,d0
 beq refresh_ret
 clr d0
 movbu d0,(refresh_dirty)
 mov refresh_zero_ids,a3
refresh_zero_loop:
 movhu (a3),d0
 cmp 0,d0
 beq refresh_ret
 mov d0,a0
 clr d0
 mov d0,a1
 call refresh_put2,[],4
 add 2,a3
 bra refresh_zero_loop
refresh_ret:
 ret [d2,d3,a2,a3],96

/* d0 = profile p (0..2) from refresh_case, a2 = settings context */
refresh_color:
 mov d0,d3
 mov 1,d0
 movbu d0,(refresh_dirty)
 mov (12,sp),a3
 mov 908,d0
 add d3,d0
 mov d0,a0
 call refresh_get1,[],4
 mov d0,(a3)
 mov 904,d0
 add d3,d0
 mov d0,a0
 call refresh_get1,[],4
 mov d0,(4,a3)
 clr d0
 mov d0,(8,a3)
 mov d0,(24,a3)
 mov 1,d0
 mov d0,(20,a3)
 /* 916..927 <- profile sectors, in sector order (E147 caller 0x60404228) */
 mov d3,d0
 asl 1,d0
 add d3,d0
 asl 2,d0
 add 928,d0
 mov d0,d2
 mov 916,a3
refresh_sector_loop:
 mov d2,a0
 call refresh_get1,[],4
 mov d0,a1
 mov a3,a0
 call refresh_put2,[],4
 inc d2
 inc a3
 cmp 928,a3
 bne refresh_sector_loop
 mov 912,d0
 add d3,d0
 mov d0,a0
 call refresh_get1,[],4
 mov d0,a1
 mov 1016,a0
 call refresh_put2,[],4
 clr d0
 mov d0,a1
 mov 1011,a0
 call refresh_put2,[],4
 clr d0
 mov d0,a1
 mov 998,a0
 call refresh_put2,[],4
 /* tone curve: three values per profile, read from store 2 as E147 does */
 mov d3,d2
 asl 1,d2
 add d3,d2
 add 976,d2
 mov refresh_tone_ids,a3
refresh_tone_loop:
 mov a2,d0
 mov 2,d1
 mov d2,a0
 call refresh_get,[d2],8
 mov d0,a1
 movhu (a3),d0
 mov d0,a0
 call refresh_put2,[],4
 inc d2
 add 2,a3
 movhu (a3),d0
 cmp 0,d0
 bne refresh_tone_loop
 bra refresh_ret

/* a0 = ID -> d0 = store-1 value of context a2 */
refresh_get1:
 mov a2,d0
 mov 1,d1
 call refresh_get,[d2],8
 ret [],4
/* a0 = ID, a1 = value -> effective (store 2) of context a2 */
refresh_put2:
 mov a2,d0
 mov 2,d1
 call refresh_set,[d2,a2],12
 ret [],4
.align 2
refresh_tone_ids:
 .hword 383,690,382,0
refresh_zero_ids:
 .hword 916,917,918,919,920,921,922,923,924,925,926,927,1011,1016,998,383,690,382,0
refresh_dirty:
 .byte 1

/* Builder output: H/L of the profile recorded in this image job. */
apply_values:
 /* Profile 1..3 from the properties the capture snapshot itself reads
  * (0x602c8821/0x602c8855): picture-mode property 0x948 is 11 for Color
  * Profile 1-3 and property 0xf6b is then the profile number (stored at
  * snapshot +28735 / +28765). Job record +10 is the dispatcher's block
  * key (always 11 here), not a profile. These are read when the block is
  * built, like the H/L cells, so a profile change between the snapshot
  * and the build is not covered. */
 mov 38017,d0
 clr d1
 mov 0,a0
 call prop_byte,[d2,d3,a2],32
 cmp 11,d0
 bne apply_done
 mov 63153,d0
 clr d1
 mov 0,a0
 call prop_byte,[d2,d3,a2],32
 sub 1,d0
 cmp 3,d0
 bcc apply_done
 mov (12,a2),a2
 add 706,a2
 mov d0,d1
 asl 1,d0
 add d1,d0
 asl 2,d0
 add 928,d0
 mov d0,d2
 mov 12,d3
apply_loop:
 /* Builder record r = 12 - d3 holds sector 2*(r%6) + r/6 (E148 builder
  * 0x603e7ca6: outer 0/1, inner 0..5, sector byte 2*inner + outer). */
 mov 12,d0
 sub d3,d0
 mov sector_of_record,a0
 movbu (d0,a0),d0
 add d2,d0
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
 add -1,d3
 bne apply_loop
apply_done:
 ret [d2,d3,a2,a3],24
sector_of_record:
 .byte 0,2,4,6,8,10,1,3,5,7,9,11

/* Custom-mode reset 0x602db531 (d0 = mode, d1 = kind; menus 0x6091c242 and
 * 0x6091c3a2) clears both parts of the live cells and reloads them only when
 * the reset mode is the current one (setting 41). Part 1 of 904..975 holds the
 * live H/L and per-profile WB, so resetting another mode would wipe them.
 * When the reset mode is not current, keep that part as it was. */
creset:
 mov d0,d2
 mov d1,d3
 mov d1,(creset_kind)
 mov 41,d0
 call raw_get,[],4
 extbu d0
 extbu d2
 cmp d0,d2
 beq creset_stock
 mov 904,d3
 mov creset_buf,a1
creset_save:
 mov d3,d0
 mov 1,d1
 mov a1,(creset_ptr)
 call active_read,[d2],8
 mov (creset_ptr),a1
 mov d0,(a1)
 inc4 a1
 inc d3
 cmp 976,d3
 bne creset_save
 mov d2,d0
 mov (creset_kind),d1
 call creset_orig,[d2,d3],12
 mov d0,(creset_ret)
 mov 904,d3
 mov creset_buf,a1
creset_restore:
 mov a1,(creset_ptr)
 mov (a1),a0
 mov d3,d0
 mov 1,d1
 call active_write,[d2],8
 mov (creset_ptr),a1
 inc4 a1
 inc d3
 cmp 976,d3
 bne creset_restore
 mov (creset_ret),d0
 ret [d2,d3],12
creset_stock:
 mov d2,d0
 mov d3,d1
creset_orig:
 mov d0,d2
 mov d1,d3
 extbu d3
 cmp 1,d3
 jmp creset_resume
.align 4
creset_kind:
 .long 0
creset_ptr:
 .long 0
creset_ret:
 .long 0
creset_buf:
 .space 288,0
