# PEN-F 3.1 build 3101 on HSL alpha-20261017: Multiple Exposure Frame
# Off/2f/4f/8f, one held press for 4f/8f, frame count in the maker note.
# One output section per helper; layout.ld places them in loaded section
# tails that HSL leaves erased, and defines the stock call targets.

# Release kind: replaces the target of "call 0x608351d6,[],0" at 0x608489de
# in entryTAKE_PICTURE_CONT; a0 = sequence, (212,a0) = Frame.
# Frame >= 4 -> 4 (the release source that chains takes), else the stock
# release source (byte-identical tail of 0x608351d6).
	.section .release_kind,"ax"
	.global	release_kind
release_kind:
	mov	(212,a0),d0
	cmp	4,d0
	bcs	1f
	mov	4,d0
	retf	[],0
1:	mov	(0x61604888),d0
	retf	[],0

# Take-done tail of rcvTakePictureDoneIn_TAKE_PICTURE_CONT, reached by
# "call take_done_tail,[d2,a2],20" at 0x608496fd; a0 = sequence.
# Redoes the displaced flag operation, then, for Frame >= 4, requests the
# next take while takes (+1 for an overlay base) < Frame. The stock
# requestMesCombine also stops at its own handle count < Frame.
	.section .take_done_tail,"ax"
	.global	take_done_tail
take_done_tail:
	mov	a0,a2
	mov	0x48000000,d0
	call	flag_op,[d2],4
	mov	(212,a2),d2
	cmp	4,d2
	bcs	1f
	mov	a2,a0
	call	take_count,[a2],12
	exthu	d0
	mov	(768,a2),d1
	cmp	1,d1
	bne	2f
	inc	d0
2:	cmp	d2,d0
	bcc	1f
	mov	a2,a0
	call	request_mes_combine,[d2,d3,a2,a3],20
1:	ret	[d2,a2],20

# Bayer_MultiExp: replaces "mov (16,a2),d0; mov 16,a2; add a0,a2;
# mov d0,(a2)" at 0x60307d3f; a2 = handle array, a0 = msg+4.
# Copies handle 4 as stock; handles 5..8 only when the take count (stored
# at (28,sp)) is above 4, because Bayer is also reached through its CALLS
# entry 0x60307cc8 (a registered callback) with a stock-sized 5-slot array.
# Leaves a2 = msg+20; clobbers d1 (dead here).
	.section .bayer_handles,"ax"
	.global	bayer_handles
bayer_handles:
	mov	(16,a2),d0
	mov	d0,(16,a0)
	movhu	(28,sp),d1
	cmp	4,d1
	bls	1f
	mov	(20,a2),d0
	mov	d0,(20,a0)
	mov	(24,a2),d0
	mov	d0,(24,a0)
	mov	(28,a2),d0
	mov	d0,(28,a0)
	mov	(32,a2),d0
	mov	d0,(32,a0)
1:	mov	a0,a2
	add	16,a2
	retf	[],0

# makePlayScaleHandle entry (0x607baf11): replaces "mov a0,(28,sp);
# mov d1,(12,sp); mov a1,a2; mov d0,d2; mov 0x609dc448,d0". Caps the take
# count at 4 so its 5-slot stack array and RecView_MultiExp's 5 handles hold.
	.section .scale_entry_cap,"ax"
	.global	scale_entry_cap
scale_entry_cap:
	mov	a0,(28,sp)
	mov	d1,(12,sp)
	mov	a1,a2
	exthu	d0
	cmp	4,d0
	bls	1f
	mov	4,d0
1:	mov	d0,d2
	mov	1620952136,d0
	retf	[],0

# Review path entry (0x607ad61e): replaces "mov d1,(44,sp); mov a0,(32,sp);
# mov (100,sp),a2; mov sp,a0". Same cap at 4 for its 5-slot stack array.
	.section .review_entry_cap,"ax"
	.global	review_entry_cap
review_entry_cap:
	mov	d1,(44,sp)
	mov	a0,(32,sp)
	mov	(100,sp),a2
	exthu	d0
	cmp	4,d0
	bls	1f
	mov	4,d0
1:	mov	sp,a0
	retf	[],0

# Capture-time maker-note writer: replaces "movhu (a3),d0; or 2,d0;
# movhu d0,(a3)" at 0x60254850, reached only when Multiple Exposure is on;
# a3 = image info + 0x13fa = the ImageProcessing tag 0x101c pair. Keeps the
# stock flag (first value |= 2) and stores Frame (setting 267: 2/4/8) in the
# second value, which stock firmware always writes as 1. Entered by
# "call exif_frame_count,[],4"; clobbers d0/d1/a0/a1, which are dead there.
	.section .exif_frame_count,"ax"
	.global	exif_frame_count
exif_frame_count:
	movhu	(a3),d0
	or	2,d0
	movhu	d0,(a3)
	mov	267,d0
	call	setting_get,[],4
	movhu	d0,(2,a3)
	ret	[],4
