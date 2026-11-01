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
The correction separates data from the odd-address pair entry without moving
that native entry. Both UTF-16 prefixes now use halfword stores, matching the
string buffer's guaranteed two-byte alignment. No new firmware region or RAM
allocation is introduced.

| Data | Corrected address | Width | Elements |
|---|---|---|---|
| Pair diagnostic line numbers | `0x60cf9e34` | 2 | 3 |
| INFO pair property IDs | `0x60c877e2` | 2 | 7 |
| English footer pointers | `0x60cfa1dc` | 4 | 3 |
| Japanese footer pointers | `0x60cfa1e8` | 4 | 3 |

The builder rejects unaligned linked table symbols and moved native entry
symbols. The regression checks every element of all four tables and the seven UTF-16
string starts, covering 23 addresses. Native query,
footer, INFO and editor tests retain their existing behavioral assertions and
service boundaries.

```sh
PYTHONPATH=tools python3 -m unittest \
  tests.test_penf_tone_viewer.ToneViewerTests.test_native_data_tables_align_every_halfword_and_word
```

The initial alignment check failed for all 16 table elements before the
production correction.
It supplements, rather than replaces, strict runtime verification. Making data
alignment mandatory in the shared emulator is a separate follow-up because that
shared harness has unrelated ongoing changes.

Generated evidence in the primary checkout is under
`generated/tone-curve/entry-crash/`, including `strict-runner.c` and
`strict-native-getter.json`. These are offline execution results; there is no
physical-camera confirmation of the correction.
