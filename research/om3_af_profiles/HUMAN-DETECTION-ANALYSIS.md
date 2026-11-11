# OM-3 1.1 Human detection: recovered pipeline and remaining gaps

31 October 2026. Static analysis of the exact OM-3 1.1 image retained in this project. No camera connection, inference execution or firmware modification was performed.

**Result:** I recovered the Human-mode selection and learned-data lookup, the image-submission and worker paths, result decoding and filtering, temporal stabilization, a dedicated face/body/eye combination path, and the application-level handoff toward autofocus. This is substantially more than a list of settings strings. It is not a complete reconstruction of the neural network, image-signal processor or lens-control algorithm.

**Most relevant to small people:** the software interface explicitly handles 640-wide YC images, and there are score/size-dependent candidate persistence and registration counters. Those are concrete investigation points. There is no demonstrated single minimum-person-size switch that will solve initial recognition.

## Method and evidence quality

The image SHA-256 is `8c133084414533159f587bf46bfb4152714c4074312a47c8d8503e33d605696d`. Main-application addresses below use the verified `0x60021020` mapping. Resource logical storage addresses are a different address space and must not be used as main-code addresses.

I reconstructed a 36-byte-stride logging metadata table with 844 entries, then matched numeric log IDs in actual code to the associated internal names. This is necessary because an address beside a name can be a **log formatter**, not the named implementation. For example, `0x6083bb69` formats the `dml_start` log; the actual examined implementation is `0x60842e1c`.

The resulting [log-ID map](analysis/human-detection/log-id-map.json) retains candidate implementation addresses, wrappers and formatter addresses separately. Multiple IDs can occur inside one routine, and wrappers may inherit a callee's decompiled body; this is a naming aid, not a perfect recovered symbol table. I checked key paths in assembly and followed the resource bytes independently.

I also found an incorrect `CALL_RETURN` flow override at `0x6086b627`. It made Ghidra stop the original result-reader function after a call to a settings accessor, hiding the remaining instructions. I cleared it **in memory only**, extended the bounded function through its real return at `0x6086b8ba`, and exported [a repaired analysis view](analysis/human-detection/result-read-repaired.c). The original saved project and firmware remain unchanged. This is a concrete example of why the original bulk C cannot be treated as complete source.

[Seventeen reproducible static checks](analysis/human-detection/verified-evidence.json) pass: enum values, resource mapping, bank bounds/hash, resize-table dimensions, parameter bytes, selected log names, and bounded instruction decoding. These checks validate the artifacts and selected observations, not camera performance. Decompiled stack/register recovery and chip-specific UDF arithmetic remain provisional. Files in `reading-aids` omit logger guard blocks for readability and are explicitly not faithful executable programs; original C and assembly are the evidence.

## 1. Human mode selects a distinct learned-data bank

The resource labels have numeric values immediately **before** their names. I checked the bytes rather than inferring values from menu order:

- 0: Off; 1: Motor Sports; 2: Airplane; 3: Train; 4: Bird; 5: Animal; 6: Human.

`get_index_mode_subject_detect` at `0x60847300` converts modes 1–6 to resource indices 0–5. `learning_data_load` at `0x60842cf1` requests resource type `0x800f` using that index. The resource-selector byte table at `0x602cb253` maps type `0x800f` to directory index 10.

The resource-directory initialization at `0x601d6a79` reads the directory from logical storage `0x458c0000` and loads eleven subordinate directories. Directory 10 points to `0x49680000`; its six data entries are each `0x8f3000` bytes. This independently connects the code's lookup to actual bytes in decoded component 0106.

**Human selects entry 5:** logical address `0x4c33f800`, decoded-component offset `0x6a7f7e0`, length **9,383,936 bytes**. I extracted it as [human-selected-learning-bank.bin](analysis/human-detection/human-selected-learning-bank.bin), SHA-256 `80f8477268bfed5e4576d5b8c12cecf9a14c45d34a5dbb4463c64c5ac8b2cdcb`.

This is the stored learned-data bank selected by the static Human-mode path. Its internal operator/weight layout has not been reconstructed. It is not an ONNX model we can currently load, retrain and export. The six equal storage sizes also do not prove six identical network architectures or equal amounts of useful model data.

`learning_data_select` at `0x60842f15` separately assigns class-number bases: 1, 11, 21, 31, 41 and 51 for modes 1–6. Thus Human uses the base `0x33` (51). This is a class-label namespace, not a confidence threshold. `mdet_laf_dl_get_dl_kind_from_conv_mode_value` at `0x60872f89` maps application mode 6 to a downstream kind value 13. These are different enums.

Sources: [mode/bank byte checks](analysis/human-detection/verified-evidence.json), [resource initialization assembly](analysis/human-detection/resource-directory-init.asm), [learning loader assembly](analysis/human-detection/learning-loader.asm), [mode-to-index assembly](analysis/human-detection/assembly/652-get_index_mode_subject_detect.asm), [class-base selector assembly](analysis/human-detection/assembly/635-learning_data_select.asm).

## 2. Images are submitted through a queued worker interface

An upstream camera routine at `0x603cf390` assembles image-related metadata and submits it to `mdet_dl_offer_yc_data` at `0x608404eb`. The latter handles an image/buffer-related identifier, copies the request and calls the CPU3 request path.

`mdet_dl_cpu3_dispatch` at `0x608418fe` queues supported operations and signals a request event. `mdet_dl_cpu3_task_subject_detect` at `0x60841a6b` waits for requests and dispatches start, end, mode change, still notification, YC-image submission, autofocus-lock notifications and a face-still operation. Opcode 5 selects the examined image-submission worker `0x6084204d`. A separate learned-data-loading task at `0x60842bde` coordinates mode changes with inference activity.

This is asynchronous camera firmware work. CPU0/CPU3 are the firmware's own labels; this trace does not establish physical chip boundaries, processor topology or a relationship to the separate Linux processes.

The sensor readout and complete ISP path that produces the submitted YC buffer are **not yet mapped**. The earliest strong boundary here is the image-submission interface, not the sensor's pixel array.

Sources: [upstream submission](analysis/human-detection/image-submit-upstream.asm), [public submission](analysis/human-detection/assembly/610-mdet_dl_offer_yc_data.asm), [worker dispatch](analysis/human-detection/assembly/620-mdet_dl_cpu3_task_subject_detect.asm).

## 3. The examined interface uses reduced-resolution images

`get_index_yc_aspect` at `0x608469f6` explicitly checks width **640**, and recognizes heights **480, 360 and 340**. Unsupported width has a distinct error path. The associated table at `0x60a05b28` has three 48-byte records whose first words match those dimension pairs. The resize setup at `0x608461cc` copies these records into the DML control structure.

This is strong static evidence for the dimensions expected at this interface. It is **not** proof that the neural network itself has a 640×480 tensor. Additional resizing, feature maps or multi-stage processing can occur inside the configured engine. Nor does it establish that every detection path or shooting mode uses identical inputs.

For the user's small-person issue, the distinction matters. As an illustration, a face spanning 1% of the submitted image width occupies only 6.4 pixels at a 640-wide interface. That is a geometric example, not a measured OM-3 detection cutoff. If detail has already been discarded before inference, relaxing downstream thresholds cannot recreate it.

There are also explicit aspect, digital-zoom and stabilization-coordinate conversion routines. Their presence does not prove that changing the AF target makes the detector receive a fresh high-resolution crop.

Sources: [aspect checks](analysis/human-detection/assembly/640-get_index_yc_aspect.asm), [resize setup](analysis/human-detection/assembly/706-dml_set_sp_resize_reg_from_tbl.asm), [table bytes](analysis/human-detection/verified-evidence.json).

## 4. DML configuration and execution are separate from candidate selection

The worker calls `dml_start` at `0x60842e1c`. That path selects the subject-mode index and class base, builds DML configuration through `0x6084313c`, prepares result-buffer information and enters a device-start wrapper. Configuration is split into control, common, subject-kind, resize, bias and normalization routines. A completion callback at `0x608464da` signals the DML completion event; the worker waits for completion before processing results.

The learned-data loader passes a destination value `0x9511ca00` into the resource-loading call. This is part of the engine's address/configuration path, not evidence that those bytes are ordinary main-CPU executable code. The start wrapper at `0x6082e1e7` enters the generic device dispatcher `0x60072c53`.

**Interpretation:** this is consistent with a hardware-oriented inference engine configured by tables and learned data. The complete hardware contract is unresolved. I have not reconstructed its network graph, quantization, internal resolution, suppression rules, anchor design or execution budget. The internal name “bias” must not be mistaken for a user-adjustable detection confidence setting.

Sources: [start routine](analysis/human-detection/assembly/634-dml_start.asm), [configuration dispatch](analysis/human-detection/assembly/700-dml_set_reg_from_tbl.asm), [loader](analysis/human-detection/learning-loader.asm), [device dispatcher](analysis/human-detection/device-start-dispatch.asm).

## 5. Raw results are decoded and filtered

`get_dml_data_set` at `0x608468cf` reads fixed-size raw records. It masks four geometry fields to 10 bits and a score-like field to 13 bits. `get_dml_result` at `0x608465ac` organizes results into class/part groups and software candidate records. The start path sets a group count of nine; the reader has bounds checks for at most twenty groups and thirty-two result entries in the examined layout. These are local structure limits, not a proved maximum number of detectable people.

The score-processing path includes a chip-specific arithmetic operation with constant 255 and a right shift of 12. A normalized score interpretation is plausible, but the opaque arithmetic must be validated before treating these values as probabilities or percentages.

`change_class_data` calls part remapping and a per-mode class-deletion mask. `judge_dml_result` at `0x60846d1b` calls two separate filters: `delete_result_ip_area` at `0x60846ec7` and `delete_result_detect_area` at `0x60847054`. The latter tests candidate coordinates against bounds and compacts accepted records. It is not simply a “small people off” switch.

These routines show places where a detector-produced candidate can be removed. They do not establish the cause of the reported failure without observing raw candidates and subsequent lists on the same image.

Sources: [raw record reader](analysis/human-detection/assembly/639-get_dml_data_set.asm), [result decoding](analysis/human-detection/assembly/638-get_dml_result.asm), [filter dispatch](analysis/human-detection/assembly/643-judge_dml_result.asm), [class filter](analysis/human-detection/class-filter.asm), [bounds filter](analysis/human-detection/assembly/646-delete_result_detect_area.asm).

## 6. Temporal stabilization has concrete tuning parameters

`stabilization` at `0x608473d6` invokes per-group matching, update, deletion, registration, normalization and sorting. Matching uses position, relative geometry, score and overlap/correlation-related tests. Candidate state includes counters for matched observations, missed observations and establishment status. This stabilization concerns **detection results**, not sensor-shift image stabilization.

Two particularly relevant routines are:

- `regist_judge_update`, `0x60848be4`: assigns a registration threshold. The reviewed table supplies default 6 and low-score values 10 in the selected branches. The update routine increments a match counter and sets an establishment flag when the threshold is reached.
- `lost_judge_update`, `0x608488f5`: selects loss thresholds from values 2, 3, 4, 6 and 8, depending on score/geometry and an existing-state flag. The deletion routine increments a missed counter and clears entries when the configured limit is reached.

The geometry-derived quantity is compared to **500** and **37,200**, with score comparisons against **100, 180 and 200**. Its inputs are width/height-like fields and a chip-specific UDF operation, making an area interpretation strongly suggestive, but not independently executed. These constants must not be advertised as verified pixel-area or percentage cutoffs.

The exact bytes at `0x60a06a44` onward are retained in the evidence JSON. Crucially, this is not a simple rule saying “reject all boxes below 500.” Different branches choose counter thresholds. I have not converted the counters into milliseconds or fixed camera frames; that requires measuring the worker's processing cadence and skipped requests.

**Implication:** a weak, intermittent small-person candidate might be slow to become established or might disappear quickly. These policies are plausible improvement targets. They cannot make a completely absent raw candidate appear, and changing them may increase false detections, stale targets or identity swaps. They also appear to be shared code, so a Human-only experiment must avoid changing other subject modes accidentally.

Sources: [matching/update](analysis/human-detection/assembly/661-stb_list_update.asm), [registration thresholds](analysis/human-detection/assembly/664-regist_judge_update.asm), [loss thresholds](analysis/human-detection/assembly/662-lost_judge_update.asm), [deletion](analysis/human-detection/assembly/665-stb_list_delete.asm), [verified parameter bytes](analysis/human-detection/verified-evidence.json).

## 7. Human mode has a dedicated face/body/eye combination path

After result decoding, filtering, display-coordinate calculations and stabilization, the worker tests mode 6. Human mode calls `face_combination` at `0x6084a693`; other modes call the generic combination routine.

The Human-specific routine initializes part slots, registers faces, searches for corresponding previous faces, combines parts, registers bodies, selects a front eye and converts the combined list. Named implementations include `face_combination_regist_face` (`0x6084aad1`), `face_combination_regist_body` (`0x6084b204`), and `face_combination_select_front_eye` (`0x6084b38f`). Eye selection compares relative horizontal/vertical geometry and uses separate normal-position, vertical-position and previous-choice routines.

Several loops operate on eight combined slots. There are larger intermediate arrays elsewhere; eight is a verified local bound, not a demonstrated universal “eight humans maximum.” I have not assigned a complete semantic label to every model class/part ID.

This establishes that Human mode is not merely the generic detector with a different display icon. It performs additional association and eye-selection work. It also does not establish biometric identity recognition: “same face” here is associated with tracking continuity, not proof of an enrolled-person identity system.

Sources: [worker branch and stage order](analysis/human-detection/assembly/625-subject_detect_offer_yc_data.asm), [Human combination](analysis/human-detection/assembly/708-face_combination.asm), [eye selection](analysis/human-detection/assembly/715-face_combination_select_front_eye.asm).

## 8. Results reach subject selection and AF coordinates

The worker calls `calc_offer_data` at `0x6084bcdc` and publishes the result through the application path `0x6087215e` / `0x6087197d`. Combined results use eight records with a `0x2a` stride in the examined interface.

The repaired result reader at `0x6086b5b9` unpacks four part records for each slot. It contains special handling for application modes 4, 5 and 6: if one primary part is unavailable but a secondary part is available, it promotes that secondary geometry into the primary result and marks a fallback flag. This is important evidence that the software already has fallback behavior. It would be premature to propose adding “body fallback” as though none existed, or to name the exact promoted part without finishing the part-type map.

Downstream routines include `mdet_laf_dl_main_subject_detect` (`0x6086b8c2`), candidate selection, touch-candidate selection, and detection selection (`0x6086eaec`). The examined code considers eligible slots, reference regions/points, previous state and switching counters. Recognizing a person and choosing that person for focus are separate stages.

`mdet_laf_get_fcs_coordinates` at `0x60864c75` exports the selected coordinate/state information. A focus-side caller at `0x609dbeb9` consumes it and continues into the focus subsystem. This traces the application-level handoff. The full phase-detection measurement, distance estimation, prediction and lens-motor loop are not reconstructed here. Nor have I traced every UI rectangle-drawing path, so visible boxes alone cannot be assumed to expose every internal candidate.

Sources: [repaired result reader](analysis/human-detection/result-read-repaired.c), [bounded assembly including the previously hidden continuation](analysis/human-detection/result-read-full-window.asm), [publication](analysis/human-detection/assembly/239-mdet_laf_dl_set_subject_detect_result_cpu3.asm), [main-subject selection](analysis/human-detection/assembly/201-mdet_laf_dl_main_subject_detect.asm), [AF coordinate export](analysis/human-detection/assembly/151-mdet_laf_get_fcs_coordinates.asm), [focus-side caller](analysis/human-detection/focus-handoff.asm).

## What this means for recognizing small people

There are now three concrete hypotheses, with different remedies:

1. **The inference stage produces no usable person/face candidate.** The reduced-resolution interface or learned detector may be the limiting factor. Higher-detail crops, different preprocessing or learned-data changes would be relevant. None is an established drop-in change; enlarging an already reduced image does not recover lost detail.
2. **A candidate exists but is unstable or filtered.** The recovered bounds checks, class masks, association tests and registration/loss counters are specific places to investigate. A carefully scoped policy change might improve acquisition or persistence without retraining.
3. **A combined person exists but the selection stage chooses something else.** Candidate eligibility, AF priority and switching logic are the appropriate targets. This can improve practical focusing without changing detection sensitivity.

The highest-value next measurement is a per-image trace of **raw result → filtered result → established candidate → combined Human result → selected AF target** while the subject shrinks in the frame. It should distinguish body, face and eye outcomes, false positives and time to acquisition. I have not established a ready-to-use remote telemetry channel for all of those internal lists; recovering that instrumentation is part of the next hardware phase.

The official manual separately describes subject detection, subject/AF-target priority, and eye-frame display. Those documented controls support keeping recognition, selection and visualization separate in tests. See the [official Human/subject-detection page](https://learning.omsystem.com/OM-3/zz_html_manual/en/subject_detection_53.html).

## Limits and conclusion

The neural network architecture and operator graph, internal tensor sizes, training set, accelerator suppression/confidence rules, full sensor-to-YC preprocessing, exact detection cadence, complete part-ID map and final lens-control loop remain unresolved. No runtime detection improvement has been demonstrated. The extracted bank does not by itself let us train a replacement, and this investigation has not established modified-firmware boot acceptance or recovery.

Nevertheless, the findings materially improve the feasibility assessment: **Human mode has identifiable learned data, reduced-resolution interface tables, explicit temporal policy parameters, specialized face/body/eye association, existing fallback behavior and a traceable AF handoff.** The best first modification to investigate is a Human-only candidate-establishment/persistence policy, provided measurements show that small-person candidates already exist. If raw candidates are absent, the research needs to move upstream into image sampling and the detector itself.
