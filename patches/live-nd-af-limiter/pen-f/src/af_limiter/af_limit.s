# PEN-F 3.1 build 3101 on HSL alpha-20261017: contrast-AF range limiter.
# Reached by "call af_limit,[],4" at 0x6047ef38, the join point of
# fcs_sub_iaf_set_lens_pos_info (0x6047eeab); a3 = ctx+12, (a3) = I-AF
# context with POS_FAR at +100 and POS_NEAR at +104 (lens drive pulses,
# either sign). Setting 448 (menu "AF Limiter"): 0 Off, 1 = 3/4, 2 = 1/2,
# 3 = 1/4. NEAR = FAR + (NEAR - FAR) * (4 - v) / 4; v = 0 rewrites NEAR
# unchanged and v >= 4 is left alone. Then redoes the two displaced stock
# instructions; ret leaves PSW alone, so the stock "beq 0x6047ef81" after
# the call sees the btst result.
	.section .af_limit,"ax"
	.global	af_limit
af_limit:
	mov	448,d0
	call	setting_get,[],4
	cmp	4,d0
	bcc	1f
	mov	4,d1
	sub	d0,d1
	mov	(a3),a0
	mov	(104,a0),d0
	mov	(100,a0),a1
	sub	a1,d0
	mul	d1,d0
	asr	2,d0
	add	a1,d0
	mov	d0,(104,a0)
1:	mov	(0x618a36a0),d0
	btst	2048,d0
	ret	[],4
