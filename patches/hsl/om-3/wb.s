.section .wb_hook,"ax"
 jmp wb_load
.section .wb_loader,"ax"
wb_load:
 cmp 901,d0
 beq wb_load_section
 cmp 1578,d0
 beq wb_load_section
 cmp 1632,d0
 beq wb_load_section
 cmp 1580,d0
 blt wb_passthrough
 cmp 1605,d0
 ble wb_load_section
wb_passthrough:
 mov d1,a2
 mov d0,d3
 exthu d3
 mov d3,d0
 jmp commit_resume
wb_load_section:
 add -20,sp
 mov d0,(4,sp)
 mov d1,(8,sp)
 mov a0,(12,sp)
 mov a1,(16,sp)
 mov (0xa32de590),d0
 btst 3,d0
 bne wb_loaded
 mov 4,d0
 call section_load,[d2,d3,a2,a3],20
wb_loaded:
 /* Check the entire WB body through its uncached alias, including padding.
  * The native loader sets its loaded bit even when the read reports failure. */
 mov 0xa0a8f100,a0
 mov wb_code_words,d3
 clr d2
wb_verify_loop:
 mov (a0),d0
 xor d0,d2
 inc4 a0
 add -1,d3
 bne wb_verify_loop
 mov (4,sp),d0
 mov (8,sp),d1
 mov (12,sp),a0
 mov (16,sp),a1
 add 20,sp
 cmp wb_code_xor,d2
 beq wb_verified
 /* Do not execute a missing/partial body or retain a false loaded flag. */
 mov (0xa32de590),d2
 and 0xfffffff7,d2
 mov d2,(0xa32de590)
 jmp wb_passthrough
wb_verified:
 jmp wb_commit
.section .wb_extension,"ax"
/* Replaces the first five bytes of the native commit routine. Its caller
 * already saved d2,d3,a2,a3 in a 20-byte frame. Nested commits use stock. */
wb_commit:
 movbu (busy),d2
 cmp 0,d2
 bne wb_original
 mov d0,d2
 mov d1,d3
 mov 1,d0
 movbu d0,(busy)
 add -8,sp
 cmp 901,d2
 bne wb_do_commit
 call wb_current,[d2,d3,a2,a3],20
 mov d0,a2
 call wb_save,[d2,d3,a2,a3],44
wb_do_commit:
 mov d2,d0
 mov d3,d1
 call wb_original,[d2,d3,a2,a3],20
 mov d0,(4,sp)
 cmp 901,d2
 bne wb_edit
 call wb_current,[d2,d3,a2,a3],20
 cmp a2,d0
 beq wb_done
 call wb_recall,[d2,d3,a2,a3],40
 bra wb_done
wb_edit:
 cmp 1578,d2
 beq wb_store_edit
 cmp 1632,d2
 beq wb_store_edit
 mov d2,d0
 sub 1580,d0
 cmp 26,d0
 bcc wb_done
wb_store_edit:
 call wb_current,[d2,d3,a2,a3],20
 call wb_save,[d2,d3,a2,a3],44
wb_done:
 clr d0
 movbu d0,(busy)
 mov (4,sp),d0
 add 8,sp
 ret [d2,d3,a2,a3],20
wb_original:
 mov d1,a2
 mov d0,d3
 exthu d3
 mov d3,d0
 jmp commit_resume
/* Return base: COLOR1..4 => 904,908,912,916; every other mode => 920.
 * No cached bank/profile pointer: native alternate access follows current bank. */
wb_current:
 mov 901,d0
 call stock_get,[],4
 cmp 64,d0
 bne wb_current_linear
 mov 57,d0
wb_current_linear:
 sub 54,d0
 cmp 4,d0
 bcs wb_current_color
 mov 4,d0
wb_current_color:
 asl 2,d0
 add 904,d0
 ret [d2,d3,a2,a3],20
/* d0 base, frame has 24 local bytes. Checksum is written last. */
wb_save:
 mov d0,d2
 add 3,d0
 mov 1,d1
 mov 0,a0
 call active_write,[d2],8
 mov 1578,d0
 call stock_get,[],4
 mov d0,(4,sp)
 mov 1632,d0
 call stock_get,[],4
 mov d0,(8,sp)
 mov 39,d0
 call stock_get,[],4
 and 255,d0
 mov d0,d3
 mov 132,d0
 call stock_get,[],4
 and 255,d0
 asl 8,d0
 or d3,d0
 mov d0,(12,sp)
 mov (4,sp),d1
 xor d1,d0
 mov (8,sp),d1
 xor d1,d0
 xor 0x57420101,d0
 mov d0,(16,sp)
 mov sp,a2
 add 4,a2
 mov 4,d3
wb_save_loop:
 mov (a2),a0
 mov d2,d0
 mov 1,d1
 call active_write,[d2],8
 inc d2
 inc4 a2
 add -1,d3
 bne wb_save_loop
 ret [d2,d3,a2,a3],44
/* d0 base; invalid/uninitialised words inherit the current WB. */
wb_recall:
 mov d0,d2
 mov d0,a3
 mov sp,a2
 add 4,a2
 mov 4,d3
wb_read_loop:
 mov d2,d0
 mov 1,d1
 call active_read,[d2],8
 mov d0,(a2)
 inc d2
 inc4 a2
 add -1,d3
 bne wb_read_loop
 mov (4,sp),d0
 mov (8,sp),d1
 xor d1,d0
 mov (12,sp),d1
 xor d1,d0
 xor 0x57420101,d0
 mov (16,sp),d1
 cmp d1,d0
 bne wb_inherit
 mov (4,sp),d0
 mov wb_modes,a0
 clr d3
wb_find_mode:
 movbu (d3,a0),d1
 cmp d1,d0
 beq wb_mode_valid
 inc d3
 cmp 13,d3
 bne wb_find_mode
 bra wb_inherit
wb_mode_valid:
 mov (8,sp),d0
 cmp 2000,d0
 blt wb_inherit
 cmp 14000,d0
 bgt wb_inherit
 mov (12,sp),d0
 mov d0,d1
 lsr 16,d1
 cmp 0,d1
 bne wb_inherit
 extb d0
 cmp -7,d0
 blt wb_inherit
 cmp 7,d0
 bgt wb_inherit
 mov (12,sp),d0
 asr 8,d0
 extb d0
 cmp -7,d0
 blt wb_inherit
 cmp 7,d0
 bgt wb_inherit
 mov (4,sp),d1
 mov 1578,d0
 mov 1,a0
 call stock_ui_write,[d2,d3,a2,a3],20
 mov (8,sp),d1
 mov 1632,d0
 mov 1,a0
 call stock_ui_write,[d2,d3,a2,a3],20
 mov (12,sp),d1
 extb d1
 mov d3,d0
 add 1580,d0
 mov 1,a0
 call stock_ui_write,[d2,d3,a2,a3],20
 mov (12,sp),d1
 asr 8,d1
 extb d1
 mov d3,d0
 add 1593,d0
 mov 1,a0
 call stock_ui_write,[d2,d3,a2,a3],20
 ret [d2,d3,a2,a3],40
wb_inherit:
 mov a3,d0
 call wb_save,[d2,d3,a2,a3],44
 ret [d2,d3,a2,a3],40
wb_modes:
 .byte 0,18,3,1,6,17,7,8,13,14,15,16,9

 .balign 4,0xcb
