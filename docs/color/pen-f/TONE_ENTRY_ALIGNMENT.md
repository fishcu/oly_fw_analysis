# Tone entry data alignment regression

The equal-quarter build placed `tone_pair_lines` at `0x60cf9e33`.
The first COLOR pair descriptor query executes a halfword read at
`0x60cf9d95`, before logging or reading tone controls. Its effective addresses
are `0x60cf9e33`, `0x60cf9e35`, and `0x60cf9e37` for COLOR1–3.

A separate strict-alignment GNU simulator runner reproduces a read fault for
all three profiles while the stock query reaches its continuation. The normal
runner permits unaligned data and therefore did not detect this failure.
Strict instruction-buffer loading requires an exception for native `SETLB`,
whose operand stream may begin at any byte address. This runner change is an
independent experiment, not a change to the shared emulator.

The same audit finds four-byte pointer tables at `0x60cfa1da` and
`0x60cfa1e6`, an existing INFO halfword table at `0x60c87729`, and packed
four-byte UTF-16 stores whose destination may be only two-byte aligned.
The regression checks every linked element of the four lookup tables.
The ordinary native query and footer tests retain their existing boundaries.

Generated evidence in the primary checkout is under
`generated/tone-curve/entry-crash/`, including `strict-runner.c` and
`strict-native-getter.json`. These are offline execution results; there is no
physical-camera confirmation of the correction.
