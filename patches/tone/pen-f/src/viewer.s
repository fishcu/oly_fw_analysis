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
 query 1,48,24
 query 0,52,32
 query 2,56,36
 mov 2778,d0
 call stock_string,[d2],8
 cmp 0,a0
 beq tone_hint_ascii
 movhu (a0),d0
 cmp 0x660e,d0
 mov tone_hint_japanese,a1
 beq tone_hint_copy
tone_hint_ascii:
 mov tone_hint_english,a1
tone_hint_copy:
 mov (16,sp),a0
 add 10,a0
 mov 5,d0
 movhu d0,(a0)
 add 8,a0
tone_hint_next:
 movhu (a1),d0
 movhu d0,(a0)
 add 2,a0
 add 2,a1
 cmp 0,d0
 bne tone_hint_next
 mov 0x60f8bbf0,d2
 jmp stock_viewer_tail
tone_viewer_other:
 mov (68,sp),d0
 jmp stock_middle_mono
tone_hint_japanese:
 .short 0x9ed2,0x70b9,0x30fb,0x767d,0x70b9,0x40,0x41,0x30,0x32,0x38,0x40,0
tone_hint_english:
 .short 0x42,0x4c,0x41,0x43,0x4b,0x20,0x2f,0x20,0x57,0x48,0x49,0x54,0x45,0x20,0x40,0x41,0x30,0x32,0x38,0x40,0
