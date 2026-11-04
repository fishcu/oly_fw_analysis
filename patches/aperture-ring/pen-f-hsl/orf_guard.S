/* PEN-F 3101: keep stock CMIO export until section 8 is fully loaded.
 * The guard remains in section 1, as did the original HSL entry point.
 * Both tail targets retain the caller's original CALL [a2],8 contract.
 */
.section .native_orf_guard,"ax"
.global cmio_export_guard
cmio_export_guard:
    add -4,sp
    mov d0,(sp)
    mov (0xa1c58404),d0
    btst 0x80,d0
    beq cmio_guard_stock
    mov (sp),d0
    add 4,sp
    jmp cmio_capture_export
cmio_guard_stock:
    mov (sp),d0
    add 4,sp
    jmp native_cmio_copy
