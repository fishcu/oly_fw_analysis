/* a0 is a native processing context. CALL([d2],4).
 * The callback, one of 16 exact operation records, and its parent identify
 * the job before the trailer is read. Zero is the invalid neutral result.
 */
.section .text,"ax"
.global tone_job_word,tone_job_parent
tone_job_word:
 call tone_job_parent,[d2],4
 cmp 0,a0
 beq word_invalid
 mov (14944,a0),d0
 mov d0,d1
 lsr 28,d1
 cmp 11,d1
 beq word_return
 mov d0,d1
 and 0xfff00000,d1
 cmp 0xa5d00000,d1
 beq word_return
word_invalid:
 clr d0
word_return:
 ret [d2],4

tone_job_parent:
 mov (4,a0),a1
 mov (8,a1),d0
 cmp 0x000b0000,d0
 bne parent_invalid
 mov (a1),d0
 cmp 0x604c4011,d0
 bne parent_invalid
 mov (4,a1),d0
 mov a1,a0
 add 1848,a0
 mov 16,d2
word_find_record:
 cmp a0,d0
 beq word_record_found
 add 52,a0
 add -1,d2
 bne word_find_record
 bra parent_invalid
word_record_found:
 mov (a0),d0
 mov a1,a0
 add -12228,a0
 cmp a0,d0
 bne parent_invalid
 ret [d2],4
parent_invalid:
 mov 0,a0
 ret [d2],4
