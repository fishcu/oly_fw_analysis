 .macro query delta, value, destination
 call stock_gui_service,[],4
 mov (a0),a2
 mov (8,a2),a2
 mov sp,a1
 add \value,a1
 mov d2,d0
 add \delta,d0
 calls (a2)
 mov (\destination,sp),d0
 mov d3,a0
 mov d0,(4,sp)
 mov (\value,sp),d0
 mov a3,a1
 mov 15,d1
 call stock_variant,[d2,d3],8
 .endm

.section .tone_viewer_pair,"ax"
.global tone_viewer_pair
tone_viewer_pair:
 mov (68,sp),d0
 add -54,d0
 cmp 3,d0
 bcc tone_pair_other
 mov d2,(4,sp)
 mov tone_pair_lines,a0
 add d0,d0
 movhu (d0,a0),d0
 mov d0,(8,sp)
 call stock_viewer_log,[a2,a3],8
 mov (68,sp),d0
 add -54,d0
 mov d0,d2
 add d0,d0
 add d2,d0
 add 967,d0
 mov d0,d2
 mov 0x60f8badc,a3
 query 0,40,16
 query 2,44,28
 query 1,60,20
 mov 0x60f8bbf0,d2
tone_pair_other:
 mov (68,sp),d0
 cmp 56,d0
 jmp stock_pair_mono
.section .tone_pair_lines,"ax"
.balign 2
tone_pair_lines:
 .short 358,369,381
.section .tone_viewer_middle,"ax"
.global tone_viewer_middle
tone_viewer_middle:
 mov (68,sp),d0
 add -54,d0
 cmp 3,d0
 bcc tone_viewer_other
 mov d0,d2
 add d0,d0
 add d2,d0
 add 967,d0
 mov d0,d2
 mov 0x60f8badc,a3
 query 1,48,24
 query 0,52,32
 query 2,56,36
 mov 0x60f8bbf0,d2
 jmp stock_viewer_pair_hint
tone_viewer_other:
 mov (68,sp),d0
 jmp stock_middle_mono
.section .tone_viewer_gate,"ax"
.global tone_viewer_publish
tone_viewer_publish:
 movm [d2,d3,a2,a3],(sp)
 add -4,sp
 movbu (0xa1c58404),d0
 and 160,d0
 cmp 160,d0
 bne tone_viewer_publish_done
 mov (24,sp),a0
 call tone_footer,[],0
tone_viewer_publish_done:
 add 4,sp
 movm (sp),[d2,d3,a2,a3]
 mov d3,d2
 exth d2
 mov (4,sp),a0
 mov d2,a1
 jmp stock_viewer_publish_resume

.section .tone_footer,"ax"
.global tone_footer
tone_footer:
 add -24,sp
 mov a0,a3
 mov (0x6161b810),a0
 cmp 0,a0
 beq tone_footer_reject
 mov (a0),a2
 mov a2,a0
 call tone_profile,[d2],8
 cmp 0,d0
 beq tone_footer_reject
 call tone_selected_id,[d2],8
 cmp 0,d0
 beq tone_footer_reject
 movhu (194,a2),d3
 cmp 2,d3
 bls tone_footer_ready
tone_footer_reject:
 add 24,sp
 ret [],0
tone_footer_ready:
 mov sp,a0
 add 4,a0
 call tone_current,[d2,d3,a2,a3],16
 mov 1,d1
 cmp 0xb7ff0400,d0
 bne tone_footer_modified
 clr d1
tone_footer_modified:
 movbu d1,(3,a3)
 mov d3,d0
 inc d0
 cmp 3,d0
 bne tone_footer_layout
 mov 1,d0
tone_footer_layout:
 movbu d0,(5,a3)
 mov 5,d0
 movhu d0,(10,a3)
 mov 2778,d0
 call stock_string,[d2],8
 mov tone_footer_english,a1
 cmp 0,a0
 beq tone_footer_language
 movhu (a0),d0
 cmp 0x660e,d0
 bne tone_footer_language
 mov tone_footer_japanese,a1
tone_footer_language:
 mov d3,d0
 asl 2,d0
 mov (d0,a1),a0
 mov a3,a2
 add 18,a2
tone_footer_copy:
 movhu (a0),d0
 cmp 0,d0
 beq tone_footer_values
 movhu d0,(a2)
 add 2,a0
 add 2,a2
 bra tone_footer_copy
tone_footer_values:
 cmp 1,d3
 beq tone_footer_middle
 movhu (6,sp),d0
 mov 83,d1
 cmp 0,d3
 beq tone_footer_first
 movhu (4,sp),d0
 mov 66,d1
tone_footer_first:
 call tone_footer_number,[],4
 movhu (10,sp),d0
 mov 72,d1
 cmp 0,d3
 beq tone_footer_second
 movhu (12,sp),d0
 mov 87,d1
tone_footer_second:
 call tone_footer_number,[],4
 jmp tone_footer_icon
tone_footer_middle:
 mov 32,d0
 movhu d0,(a2)
 mov 77,d0
 movhu d0,(2,a2)
 movhu (8,sp),d0
 add -512,d0
 asr 5,d0
 mov 43,d1
 cmp 0,d0
 blt tone_footer_negative
 jmp tone_footer_sign
tone_footer_negative:
 clr d1
 sub d0,d1
 mov d1,d0
 mov 45,d1
 jmp tone_footer_sign
.section .tone_footer_tail,"ax"
tone_footer_sign:
 movhu d1,(4,a2)
 add 48,d0
 movhu d0,(6,a2)
 add 8,a2
tone_footer_icon:
 mov tone_footer_info,a0
tone_footer_icon_copy:
 movhu (a0),d0
 movhu d0,(a2)
 add 2,a0
 add 2,a2
 cmp 0,d0
 bne tone_footer_icon_copy
tone_footer_return:
 add 24,sp
 ret [],0

tone_footer_number:
 movhu d1,(2,a2)
 mov 32,d1
 movhu d1,(a2)
 mov a2,a1
 add 10,a1
 call tone_digits,[],4
 add 12,a2
 ret [],4

.section .tone_footer_tables,"ax"
.balign 4
tone_footer_english:
 .long footer_pair_en,footer_middle_en,footer_endpoints_en
tone_footer_japanese:
 .long footer_pair_jp,footer_middle_jp,footer_endpoints_jp
 .section .tone_footer_small_strings,"ax"
footer_middle_en:
 .short 77,73,68,68,76,69,0
 .section .tone_footer_strings,"ax"
footer_endpoints_en:
 .short 66,76,65,67,75,47,87,72,73,84,69,0
footer_pair_en:
 .short 83,72,65,68,79,87,47,72,73,71,72,0
footer_middle_jp:
 .short 0x4e2d,0x9593,0x90e8,0
footer_endpoints_jp:
 .short 0x9ed2,0x70b9,0x30fb,0x767d,0x70b9,0
footer_pair_jp:
 .short 0x660e,0x90e8,0x30fb,0x6697,0x90e8,0
tone_footer_info:
 .short 64,65,48,50,56,64,0
