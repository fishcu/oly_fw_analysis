# OM-3 Human detection pipeline

Static analysis recovered model-bank selection, image submission, candidate
decoding/filtering, temporal stabilization, Human-specific face/body/eye
association and the application handoff toward AF. It did not reconstruct a
trainable neural network, execute inference, establish lens control, or
benchmark recognition accuracy. The exact input and CPU mapping are identified
in [AF button profiles](AF_BUTTON_PROFILES.md#input-and-address-spaces).

## Learned data and image submission

The recovered enum is Off 0, Motor Sports 1, Airplane 2, Train 3, Bird 4,
Animal 5, Human 6. `0x60847300` maps enabled modes to banks 0–5. Human selects
bank 5 in resource component `0106`: logical storage `0x4c33f800`, decoded
component offset `0x6a7f7e0`, length 9,383,936, SHA-256
`80f8477268bfed5e4576d5b8c12cecf9a14c45d34a5dbb4463c64c5ac8b2cdcb`.
The bank is not distributed and its operator/weight format is unreconstructed.
There is no demonstrated ONNX export/retraining workflow.

`learning_data_select` at `0x60842f15` assigns Human class base 51 (`0x33`);
`0x60872f89` maps Human to downstream kind 13. These are distinct namespaces,
not confidence thresholds. Submission uses queued workers and a detector-device
interface. The examined software interface includes 640-wide YC images; that
does not establish sensor-resolution inference, every effective crop, or timing.

Log names require caution: a 36-byte-stride metadata table has 844 entries,
but the address near a name may be a formatter. `0x6083bb69` formats the
`dml_start` log; the examined implementation is `0x60842e1c`.

## Filtering and temporal persistence

Local parser bounds include twenty groups and thirty-two entries in one
layout; these are not a proved universal number-of-people limit. Result judge
`0x60846d1b` invokes IP-area filter `0x60846ec7` and detection-area filter
`0x60847054`; class conversion also applies deletion masks. A candidate can
disappear after inference, so display absence alone does not identify the cause.

Temporal stabilization at `0x608473d6` matches, updates, deletes, registers,
normalizes and sorts candidate results. It is not sensor-shift stabilization.
Registration policy `0x60848be4` uses recovered thresholds 6 and 10 in examined
branches; loss policy `0x608488f5` chooses among 2, 3, 4, 6 and 8. Related
comparisons include geometry-derived 500 and 37,200 and scores 100, 180, 200.
Opaque arithmetic and processing cadence prevent calling these verified
pixel-area/probability cutoffs or converting counters to fixed frame times.
In particular, 500 is not established as a universal minimum-person-size rule.

## Human association and application handoff

Human chooses `face_combination` at `0x6084a693`, with face registration
`0x6084aad1`, body registration `0x6084b204`, previous-result/part association,
and front-eye selection `0x6084b38f`. Eight slots appear in this interface,
with larger arrays elsewhere. This is not proof of a universal eight-human
limit or biometric identity recognition.

Publication includes `0x6084bcdc`, then `0x6087215e` / `0x6087197d`.
Reader `0x6086b5b9` has secondary-to-primary geometry fallback for modes 4/5/6;
fallback already exists, although exact semantic part labels are incomplete.
Downstream `0x6086b8c2` and selection `0x6086eaec` use eligible slots, reference
regions, previous state and switching counters. Detection and AF selection
are separate stages.

A false Ghidra `CALL_RETURN` override at `0x6086b627` truncated exported C.
The temporary repaired view extends to the real return at `0x6086b8ba`.
Exported C/register types therefore require bounded-assembly corroboration;
they are not recovered buildable vendor source.

## Small-person hypotheses and evidence limits

Investigation points are image scale/crop, filtering, registration/loss policy,
association and final selection. Relaxing persistence might expose intermittent
weak candidates sooner, with false detections/stale targets/identity switches.
It cannot create a raw candidate absent from inference. Shared routines could
affect other subject classes. There is no demonstrated one-constant fix or
measured accuracy improvement.

A useful experiment would observe the same image's submitted crop/scale, raw
candidate list, filtered/stabilized/combined lists and final selection. These
camera observations do not exist here. Seventeen recorded static checks cover
enums, bank bounds/hash, resize metadata, bytes/names and bounded decoding;
they do not measure inference, AF, timing or camera performance.

The [workspace](../../../research/om3_af_profiles/README.md) preserves authored
collection/analysis scripts, the historical detailed report and compact
`recorded-evidence/human-detection/verified-evidence.json` / `log-id-map.json`.
Full assembly/C exports, model data and extracted assets remain local outputs.
