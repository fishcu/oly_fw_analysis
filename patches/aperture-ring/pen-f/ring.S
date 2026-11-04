/* PEN-F 3101 / capability-based aperture-ring experimental implementation.
 * Original section 1 is loaded at 60142800..601cb000. State uses an
 * aligned uncached alias; it is never a persistent setting or a semaphore.
 */
.equ state_word, 0xa01cafb0
.equ ring_magic, 0x52470000
.text
.global poll_hook, parser_hook, ae_aperture_hook, disconnect_hook

poll_hook:
    add -8,sp
    mov d0,(sp)
    mov a1,(4,sp)
    btst 0x800,d2
    bne poll_disable
    mov (0xa1c40090),a1
    cmp 0,a1
    beq poll_disable
    mov (0x23c,a1),d0
    btst 0x80,d0
    beq poll_disable
poll_command:
    movbu (0x12,a2),d0
    cmp 0xc1,d0
    beq poll_ordinary
    cmp 0x81,d0
    bne poll_disable
    movbu (0x13,a2),d0
    cmp 0xe3,d0
    bne poll_disable
    bra poll_enable
poll_ordinary:
    movbu (0x13,a2),d0
    cmp 0x80,d0
    bne poll_disable
poll_enable:
    or 0x100,d2
    bra poll_replay
poll_disable:
    clr d0
    mov d0,(state_word)
poll_replay:
    mov 0x14,a0
    add a2,a0
    movbu d2,(a0)
    asr 8,d2
    mov (sp),d0
    mov (4,sp),a1
    add 8,sp
    retf [],0

parser_hook:
    add -8,sp
    mov d0,(sp)
    mov d1,(4,sp)
    /* Replay displaced focus-distance read/store. Entry SP differs by 8. */
    movbu (a3),d0
    mov (16,sp),a0
    inc a3
    movbu d0,(15,a0)
    clr d1
    btst 1,d3
    beq parser_done
    mov d2,d1
    and 6,d1
    cmp 0,d1
    beq parser_read
    cmp 6,d1
    bne parser_done
parser_read:
    movbu (1,a3),d1
    asl 8,d1
    movbu (a3),d0
    or d0,d1
    or ring_magic,d1
    /* One aligned publication store; A/auto is published, then rejected
     * by the consumer's sentinel check. No callback in this path. */
    add 2,a3
parser_done:
    mov d1,(state_word)
    movbu (15,a0),d0
    mov (4,sp),d1
    add 8,sp
    retf [],0

ae_aperture_hook:
    /* Replace precisely one CALL of InfoGet(80ca) in the AE snapshot.
     * Keep its native getter and outer [D2,D3],12 call/return contract. */
    call stock_info_get,[d2,d3],12
    mov d0,d2
    movhu (0x6184d730),d0
    cmp 1,d0
    bne ae_body
    mov (0xa1c40090),a0
    cmp 0,a0
    beq ae_body
    mov (0x23c,a0),d0
    btst 0x80,d0
    beq ae_body
ae_state:
    mov (state_word),d3
    mov d3,d0
    and 0xffff0000,d0
    cmp ring_magic,d0
    bne ae_body
    exthu d3
    /* The cache is [live effective Av, official minimum, official maximum].
     * Use the zoom-dependent official bounds, as stock AE does. The first
     * word is a measured/status value, not a wide-open limit. */
    cmp 0x8000,d3
    beq ae_body
    exth d3
    movhu (0x6184d706),d0
    exth d0
    movhu (0x6184d708),d1
    exth d1
    cmp d1,d0
    bgt ae_body
    cmp d0,d3
    bge ae_upper_bound
    mov d0,d3
ae_upper_bound:
    cmp d1,d3
    ble ae_mode
    mov d1,d3
ae_mode:
    /* 605dd715 stored its selected AE configuration at caller SP+4.
     * The outer CALL frame is 12 bytes, so this is callee SP+16.
     * Use the actual AE mode, including recording-context selection. */
    mov (16,sp),a0
    movbu (2,a0),d0
    cmp 4,d0
    beq ae_ring
    cmp 6,d0
    bne ae_body
ae_ring:
    mov d3,d0
    bra ae_return
ae_body:
    mov d2,d0
ae_return:
    ret [d3,d2],12

disconnect_hook:
    /* Original discovery-reset entry: clear extension state, then replay
     * its first eight bytes and continue its original loop and RETF. */
    clr d0
    mov d0,(state_word)
    clr d1
    mov 0xa1c3fdec,a0
    jmp stock_discovery_resume

.section .poll,"ax"
    call poll_hook,[],0
    nop
    nop
.section .parser,"ax"
    call parser_hook,[],0
    nop
.section .ae,"ax"
    call ae_aperture_hook,[d2,d3],12
.section .disconnect,"ax"
    jmp disconnect_hook
    nop
    nop
    nop
.section .state,"aw"
    .long 0

/* All status producers converge here. Keep the original automatic-poll
 * extension and qualify the additional query/focus/generic request paths. */
.text
.global dispatch_hook
dispatch_hook:
    add -16,sp
    mov d0,(sp)
    mov d1,(4,sp)
    mov a0,(8,sp)
    mov a1,(12,sp)
    cmp 0,a0
    beq dispatch_return
    mov a0,a1
    movhu (12,a1),d0
    cmp 0,d0
    bne dispatch_return
    movbu (18,a1),d0
    cmp 0xc1,d0
    beq dispatch_c1
    cmp 0x81,d0
    bne dispatch_return
    movbu (19,a1),d0
    cmp 0xe3,d0
    bne dispatch_return
    bra dispatch_check
dispatch_c1:
    movbu (19,a1),d0
    cmp 0x80,d0
    bne dispatch_return
dispatch_check:
    movbu (21,a1),d1
    btst 8,d1
    bne dispatch_disable
    movhu (0x6184d730),d0
    cmp 1,d0
    bne dispatch_disable
    mov (0xa1c40090),a0
    cmp 0,a0
    beq dispatch_disable
    mov (0x23c,a0),d0
    btst 0x80,d0
    beq dispatch_disable
    or 1,d1
    movbu d1,(21,a1)
    bra dispatch_return
dispatch_disable:
    clr d0
    mov d0,(state_word)
dispatch_return:
    mov (sp),d0
    mov (4,sp),d1
    mov (8,sp),a0
    mov (12,sp),a1
    add 16,sp
    /* Replay the displaced entry, including its NULL branch. */
    mov a0,a3
    clr d2
    cmp 0,a3
    beq dispatch_null
    jmp stock_dispatch_resume
dispatch_null:
    jmp stock_dispatch_null

.section .dispatch,"ax"
    jmp dispatch_hook
    nop
    nop
    nop
    nop
