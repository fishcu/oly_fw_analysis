/* Copyright 2026 fishku (original contributions)
 * SPDX-License-Identifier: Apache-2.0
 * Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
 */
/* PEN-F 3101 HSL: editor storage. */
/* Persistent COLOR1/2/3 publication. All helpers and the live source reside
 * in settings section2, alongside the stock APIs/callers they extend.
 * No allocation, private write-to-flash path or consistency counter.
 */
.macro preserve
 movm [d2,d3,a2,a3,other],(sp)
 mov psw,d2
 add -4,sp
 mov d2,(4,sp)
 mov (48,sp),d2
.endm
.macro restore
 mov (4,sp),d2
 add 4,sp
 mov d2,psw
 movm (sp),[d2,d3,a2,a3,other]
.endm

.section .persist_boot_hook,"ax"
 jmp hl_boot_publish
.section .persist_commit_hook,"ax"
 jmp hl_commit_publish
 nop
.section .persist_refresh_hook,"ax"
 jmp hl_refresh_publish
.section .hsl_persist,"ax"
.global hl_publish,hl_boot_publish,hl_commit_publish,hl_refresh_publish
/* Publish all profiles, independent of currently selected picture mode.
 * Acquisition chooses its own captured profile. CALL [],4; scratch only. */
hl_publish:
 .irp profile,1,2,3
 mov \profile,d0
 mov source_uncached+(\profile-1)*12,a0
 call hl_active_snapshot,[d2,d3,a2],20
 .endr
 ret [],4

/* Displaced stock startup-reset CALL is executed first. */
hl_boot_publish:
 call stock_boot_reset,[],4
 call hl_publish,[],4
 jmp stock_boot_resume

/* Stock transaction has committed current records at this point. Preserve
 * the original changed-ID count in a2 and the complete native return ABI. */
hl_commit_publish:
 preserve
 call hl_publish,[],4
 restore
 mov a2,d0
 exthu d0
 ret [d2,d3,a2,a3],36

/* Current parameter refreshes also cover direct reset/selection routes.
 * Staged context1 must never publish destination H/L before commit. */
hl_refresh_publish:
 preserve
 cmp 0,d0
 bne hl_refresh_staged
 call hl_publish,[],4
hl_refresh_staged:
 restore
 mov d0,d2
 extbu d2
 mov d2,d0
 mov sp,a0
 inc4 a0
 jmp stock_refresh_resume


/* Stock backup enum conversion for extended saturation. */
.global range_backup_enum
range_backup_enum:
 mov d0,d1
 sub 931,d1
 cmp 36,d1
 bcc range_backup_lookup
 mov 967,d0
range_backup_lookup:
 call stock_backup_descriptor,[d2,d3,a2,a3],16
 cmp 0,a0
 ret [d2,d3,a2,a3],20
 .fill 34-(.-range_backup_enum),1,0xcb


/* Same per-profile refresh callbacks used by stock saturation edits.
 * d2 is the absolute setting ID. Tail jumps preserve their CALL [],0 ABI. */
.global hl_refresh_profile
hl_refresh_profile:
 cmp 943,d2
 bcs hl_refresh1
 cmp 955,d2
 bcs hl_refresh2
 jmp stock_color3_refresh
hl_refresh1:
 jmp stock_color1_refresh
hl_refresh2:
 jmp stock_color2_refresh

.section .persist_source,"aw"
.global hl_profile_source
hl_profile_source:
 .zero 36
