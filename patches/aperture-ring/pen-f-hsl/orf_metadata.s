/* PEN-F 3101 HSL: orf metadata. */
/* At the one stock rec_raw_make_header call to export CMIO T.
 * Preserve its original call convention. The captured owner is a caller
 * local at original SP+20, hence SP+28 on entry with CALL [a2],8.
 */
.section .native_orf_hook,"ax"
 call cmio_export_guard,[a2],8

.section .native_orf_export,"ax"
.global cmio_capture_export
cmio_capture_export:
 movm [d2,d3,a3],(sp)
 add -20,sp
 mov a0,(4,sp)
 mov (60,sp),a0             /* entry SP+28 = outer owner */
 mov a0,(8,sp)
 mov (4,sp),a0
 call native_cmio_copy,[a2],8 /* stock transfer and completion */
.global cmio_after_copy
cmio_after_copy:
 exthu d0
 cmp 0,d0
 bne cmio_export_done
 mov (8,sp),a0
 movhu (18492,a0),d1
 cmp 2,d1
 bne cmio_export_neutral
 movbu (18595,a0),d1
 cmp 11,d1
 bne cmio_export_neutral
 movbu (18625,a0),d1
 add -1,d1
 cmp 3,d1
 bcc cmio_export_neutral
 call hl_owner_row,[],4
 cmp 0,a0
 beq cmio_export_neutral
 mov a0,(12,sp)
 mov (4,sp),a0
 add 0x2498,a0
 mov 0x60619f84,a1
 mov 0x60622d74,a2
 mov 3028,d0
 call cmio_patch_table,[d2,d3,a2,a3],60
 cmp 0,d0
 bne cmio_export_done
 mov (4,sp),a0
 add 0x306c,a0
 mov 0x6061ab58,a1
 mov 0x60622d74,a2
 mov 3028,d0
 call cmio_patch_table,[d2,d3,a2,a3],60
 cmp 0,d0
 bne cmio_export_done
 /* All stock P serialization precedes this call; final header copying
  * follows. These two image-owned metadata slots are not live ISP tables. */
 mov (8,sp),a0
 mov a0,d0
 add 18600,d0
 add 13448,a0              /* owner+12528+P398 */
 mov (12,sp),a1
 call cmio_capture_weights,[d2,d3,a2,a3],36
 mov (8,sp),a0
 mov a0,d0
 add 18600,d0
 add 13520,a0              /* owner+12528+P3e0 */
 mov (12,sp),a1
 call cmio_capture_weights,[d2,d3,a2,a3],36
cmio_export_neutral:
 clr d0
cmio_export_done:
 add 20,sp
 movm (sp),[d2,d3,a3]
 exthu d0
 ret [a2],8
