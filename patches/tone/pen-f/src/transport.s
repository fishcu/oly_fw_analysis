.section .tone_early,"ax"
.global tone_publish, tone_build_gate, tone_stock_builder, tone_source
tone_publish:
 movm [d2,a2,a3],(sp)
 add -4,sp
 mov 12,d2
 mov tone_source_uncached,a2
 mov tone_storage_ids,a3
tone_publish_loop:
 movhu (a3),d0
 mov 1,d1
 call stock_active_get,[d2],8
 mov d0,(a2)
 inc4 a2
 add 2,a3
 add -1,d2
 bne tone_publish_loop
 add 4,sp
 movm (sp),[d2,a2,a3]
 ret [],4

tone_build_gate:
 movbu (0xa1c58404),d0
 btst 128,d0
 beq tone_stock_builder
 jmp tone_native_builder
tone_stock_builder:
 mov (4,a0),d1
 mov a0,d3
 jmp stock_builder_after_entry
.section .tone_source,"aw"
.balign 4
tone_source:
 .zero 48

.section .tone_source_gate,"ax"
.global tone_source_gate
tone_source_gate:
 movbu (0xa1c58404),d0
 btst 128,d0
 beq hl_return
 jmp tone_source_copy

.section .tone_job_bridge,"ax"
.global tone_job_bridge
tone_job_bridge:
 jmp tone_job_gate

.section .tone_job_gate,"ax"
.global tone_job_gate
tone_job_gate:
 movbu (0xa1c58404),d0
 btst 128,d0
 bne tone_job_loaded
 jmp tone_job_unloaded
tone_job_loaded:
 jmp tone_job_copy
.section .tone_early,"ax"
tone_job_unloaded:
 clr d0
 .irp offset,24,28,32,36
 mov d0,(\offset,a2)
 .endr
 ret [],4

.section .text,"ax"
.global tone_source_copy, tone_job_copy, tone_clear_hl_row
tone_source_copy:
 mov a3,a0
 call hl_owner_row,[],4
 call tone_hl_row,[],4
 cmp 0,a0
 beq tone_copy_return
 mov a0,a1
 mov a3,a0
 cmp tone_compact_rows,a1
 bcc tone_source_compact
 movbu (18625,a0),d0
 bra tone_source_profile
tone_source_compact:
 movbu (381,a0),d0
tone_source_profile:
 add -1,d0
 cmp 3,d0
 bcc tone_source_neutral
 asl 4,d0
 mov tone_source_uncached,a0
 add d0,a0
 mov (a0),d0
 mov d0,d1
 lsr 28,d1
 cmp 11,d1
 beq tone_source_all
 mov d0,d1
 lsr 20,d1
 cmp 0xa5d,d1
 beq tone_source_all
 mov 0xa5dffc00,d0
tone_source_all:
 mov d0,(a1)
 movm [d2,a2,a3],(sp)
 add -16,sp
 mov a0,a2
 mov a1,a3
 mov 3,d2
tone_source_rgb:
 inc4 a2
 inc4 a3
 mov (a2),d0
 mov sp,a0
 add 4,a0
 call tone_decode,[d2,d3,a2,a3],16
 cmp 0,d0
 bne tone_source_rgb_valid
 mov 0xb7ff0400,d0
tone_source_rgb_valid:
 mov d0,(a3)
 add -1,d2
 bne tone_source_rgb
 add 16,sp
 movm (sp),[d2,a2,a3]
 ret [],4
tone_source_neutral:
 clr d0
 .irp offset,0,4,8,12
 mov d0,(\offset,a1)
 .endr
tone_copy_return:
 ret [],4

tone_job_copy:
 add -12,a0
 call tone_hl_row,[],4
 cmp 0,a0
 beq tone_job_zero
 .irp offset,0,4,8,12
 mov (\offset,a0),d0
 mov d0,(24+\offset,a2)
 .endr
 ret [],4
tone_job_zero:
 clr d0
 .irp offset,24,28,32,36
 mov d0,(\offset,a2)
 .endr
 ret [],4

tone_clear_hl_row:
 call tone_hl_row,[],4
 cmp 0,a0
 beq tone_clear_return
 clr d0
 .irp offset,0,4,8,12
 mov d0,(\offset,a0)
 .endr
tone_clear_return:
 ret [],4

tone_hl_row:
 mov a0,d0
 sub 0xa069b590,d0
 cmp 540,d0
 bcc tone_no_row
 mov 12,d1
 clr d3
 mov d3,mdr
 divu d1,d0
 mov mdr,d1
 cmp 0,d1
 bne tone_no_row
 asl 4,d0
 mov tone_rows_uncached,a0
 add d0,a0
 ret [],4
tone_no_row:
 mov 0,a0
 ret [],4

.section .tone_rows,"aw"
.balign 4
.global tone_rows
tone_rows:
 .zero 720

.section .tone_storage_ids,"a"
.balign 2
.global tone_storage_ids
tone_storage_ids:
 .short 967,968,969,919,970,971,972,920,973,974,975,921
