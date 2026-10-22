# Independent postfreeze audit of the final comparison

22 October 2026, India time; raw comparison timestamps are 21 October UTC. **The reported metrics and model identities reproduce; no numerical, pairing or checkpoint-identity error was found in this bounded audit. Retaining the baseline is supported by the observed comparison.** Epoch 20 adds nine flagged proxy windows, adds no matched proxy episode observations and adds one flagged provisionally normal window. These are small curated diagnostic counts, not evidence of a production accuracy improvement.

This audit was explicitly authorized **after the final choice and reserved comparison were complete**. Actual raw/summaries were read for verification only. No reannotation, alternative-checkpoint selection, tuning, model/decoder execution, GPU work, fitting or live change occurred. The only file written by this audit is this report.

## Recomputed reserved result

| Observation | Unchanged baseline | Frozen epoch 20 |
| --- | ---: | ---: |
| Exactly paired raw windows | 593 | 593 |
| Eligible proxy windows flagged | 58 / 82 | 67 / 82 |
| Eligible proxy windows unflagged | 24 / 82 | 15 / 82 |
| Compatible recording-level proxy episode observations matched | 6 / 6 | 6 / 6 |
| Additional compatible flags after episode credit | 52 | 61 |
| Fully annotated normal windows flagged | 14 / 40 | 15 / 40 |
| Fully annotated normal windows unflagged | 26 / 40 | 25 / 40 |
| Unknown windows excluded from eligible comparisons | 471 | 471 |
| Flags on unknown windows, reported separately | 143 | 180 |

Both stored reserved summaries were recomputed in memory with the pinned audited JSON postprocessor and matched **every field**, including window-level eligibility, episode matching and group counts. Independently implemented exact-rational interval unions/overlaps, using `Fraction(str(value))`, reproduced eligibility for all 593 windows per model and reproduced all event/flag totals. There was no added epsilon, label extension, nominal four-second denominator or three-second event forgiveness.

All changed strict decisions are gains: **9 proxy + 1 normal + 37 unknown**, with no lost flags. The unknown gains are not counted as false positives or successes. All provisional normal flags occur in `online-normal-03`, the admitted solo-dancing source: baseline 14/30, epoch 20 15/30. The additional window is index 11, actual span **4579–8524 ms**; raw fight scores are 0.4606873095035553 and 0.6072617173194885, respectively, under the unchanged strict >.5 rule. This is one additional overlapping window flag, not a demonstrated additional operational alert after cooldown/episode policy.

The six proxy observations span **six recordings but only three source groups**. Sports/drill contact does not establish hostile fights, intent, crime, injury or independent human ground truth. Matching all six observations is not six independent hostile-fight detections or a general incident-recall estimate.

| Proxy recording | Eligible windows | Baseline flagged | Epoch 20 flagged | Episode matches, baseline / epoch 20 |
| --- | ---: | ---: | ---: | ---: |
| wave1-positive-tokyo-judo | 19 | 15 | 18 | 1 / 1 |
| wave1-positive-buganda-wrestling | 12 | 12 | 12 | 1 / 1 |
| wave1-positive-buganda-ekigwo | 17 | 14 | 16 | 1 / 1 |
| wave1-positive-buganda-ekigwo1 | 11 | 1 | 3 | 1 / 1 |
| wave1-positive-kata-juji-jime | 15 | 9 | 10 | 1 / 1 |
| wave1-positive-hon-kesa-gatame | 8 | 7 | 8 | 1 / 1 |

The three Buganda uploads retain one source group; the two instructional judo recordings retain one source group. Tokyo is the third positive group. No additional source/incident independence was invented from filenames.

## Normal annotation is not fully evaluated camera time

The corpus has **44 seconds of explicit normal annotation in 11 original intervals across five normal recordings/groups**. Same-label touching intervals merge for coverage, not to manufacture independent examples. Only three normal recordings/groups contribute eligible fully normal prediction windows.

| Normal recording | Explicit annotation | Eligible normal windows | Union of actual eligible-window spans | Baseline / epoch-20 normal flags |
| --- | ---: | ---: | ---: | ---: |
| online-normal-01, embrace source | 8 s | 9 | 7.800 s | 0 / 0 |
| online-normal-03, solo-dance source | 20 s | 30 | 19.587 s | 14 / 15 |
| online-normal-07, easier animal/handler controls | 8 s | **0** | **0 s** | Not evaluated as eligible normal |
| wave2-normal-01, drum-performance control | 4 s | 1 | 3.840 s | 0 / 0 |
| wave3-government-125927, exercise control | 4 s | **0** | **0 s** | Not evaluated as eligible normal |
| Total | **44 s** | **40** | **31.227 s** | **14 / 15** |

The actual normal-window union is **31.227 seconds**, independently computed by merging actual eligible prediction spans within each recording, then summing across recordings. The 40 overlapping windows are not 160 independent seconds. **12.773 annotated seconds are outside that eligible-span union**, including all 12 annotated seconds in the two zero-opportunity recordings plus smaller edge margins elsewhere.

Those two recordings are not missing decoder outputs: they have 26 and 205 raw predictions respectively, all unknown under the fixed full-normal coverage rule. Their isolated four-second annotation spans do not contain an emitted full-context window at the fixed sampling/400 ms prediction phase. They are coverage gaps, not demonstrated normal negatives with zero false flags. Bounds/windowing were not expanded in this audit to change that result.

Neither 44 seconds nor 31.227 curated seconds is an operational false-alert-rate denominator here. Flags are overlapping classifier-window observations, not a complete emitted-alert policy with cooldown, episode consolidation, unknown-time accounting and representative camera-hours. No FAR, camera-hour rate, aggregate accuracy percentage or confidence bound is justified by these data.

## Pairing, corpus, grouping and identity checks

Reserved corpus SHA-256 is exactly `05b3593c1d927bbcd60e765fda4082335a40053e92cce29ce609e26778a83e79`. It has **11 recordings, eight source groups, 39 seconds of positive-proxy annotation and 44 seconds of explicit normal annotation**. The postprocessor validated events, role/originalRole and source-group hash mapping, media/group/crop/duration identity, dimensions, sample PTS, selected frames, probability/class order, strict flags, annotation overlaps and counts. Opposite-label conflicts are absent.

For **every one of 593 rows**, baseline and candidate agree on every ordered runner identity field: clip ID, source group, media SHA, normalized crop, actual start/end PTS, source/view dimensions, pixel crop, all source sample PTS and selected frame PTS. The recomputed ordered identity hash equals both raw/summary hashes:

`db0ec4acfe85c1bb6d52e2af9204002d72796a6ea6b4b4e9874dcea35251618f`.

The fixed paired policy hash is `c974d6f61ab429335cd6a1d917687c6671370a6a0c0edc54633e5a869cd74ac4`. No model-specific replacement windows were admitted. Actual media were not decoded or reannotated; their raw media hashes agree with corpus declarations. Their physical bytes/rights/evidence were parent admission work, not repeated visual review by this audit.

The selected epoch-20 identity was compared with actual local artifact bytes using SHA only:

| Identity | SHA-256 / value |
| --- | --- |
| Selected candidate checkpoint | `7c58a0f2e6ffc63ebdc4ab2df7b15882d90c3a14e0bc892f55f4e2760471e30f` |
| Epoch-20 report | `4cda52975126f4e00887cf58f9527db55c6cbfdcd1386b1c444daaa8fb668319` |
| Full training run seal | `0584dec4936ea5c7b1461974985adbf405b8825eb633b037ac4f8ef1e3e7c509` |
| Clean training manifest | `68cf0c4048dcc9d4d10e5553bf5bcf9be6cd6ab36bd7aeaff23208f2b55e0970` |
| Baseline checkpoint | `e833f69d110f167cad4a6c38d385564bdb2f6de63d246e45cb03ff9aa17f0349` |
| Selected export epoch | 20 |

Raw assets, adaptationIdentity, selected receipt and summary agree. The candidate's complete 53-entry trained-source map equals its assets map and the actual training started receipt's snapshot map. Baseline assets identify the actual same pinned checkpoint. Raw implementation hashes agree with local runner/helper bytes. The final comparison receipt's raw/summary hashes, selected identity, counts and zero-eligible-normal IDs all agree with the files audited.

Additional identity checks covered all eight candidate reports used here: three new-development runs, three old-development milestones, selected reserved candidate and quality candidate. All epoch/checkpoint/report/seal/manifest/source maps agree with their actual epoch 3/10/20 bytes. Four baseline reports identify the same baseline checkpoint. No model was loaded or executed for these identity checks.

## Frozen choice and development reconstruction

Selected receipt SHA is `104426e0a81cf04997dfc03f8408cd58d8d7d98914bb68148e66332efa93a7e9`; selection policy SHA is `75d66a706d55a4e0646fee272f9f5644356eadb3b6ff97f456cde6d1ff59d649`. The reserved admission receipt binds that selection receipt and corpus before scoring. All four development-normal raw/summary hashes and four historical-development raw hashes match the selected receipt.

Four new development summaries recompute exactly against corpus `8b2dec120c1eca991e4621c8441996546b92b5f518112b8205345648ce18012f`: one recording/group, **16 paired predictions: one eligible normal, fifteen unknown**. The eligible normal flag count is zero for baseline and every milestone. No new development positive source is supplied by that corpus.

All four old-development raw reports also have identical 67 ordered window identities and pairing hash `d42745b6512c14d2854e3a7eacb6a2adcaff58d324d2ee86b94db358b8c2c408`, against unchanged old corpus SHA `33d04d15bc4a6911face456fff7488320906505cc344f863042e4cae304bfb34`. Flags recomputed directly from raw scores are:

| Control | Raw windows | Baseline | Epoch 3 | Epoch 10 | Epoch 20 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Boxing context | 12 | 0 | 0 | 0 | 0 |
| Original grappling | 17 | 13 | 13 | 14 | 15 |
| Short kick sensitivity | 2 | 2 | 2 | 2 | 2 |
| Squat context | 19 | 0 | 0 | 0 | 0 |
| Dependent grappling crop | 17 | 10 | 10 | 11 | 11 |

All 17 original grappling windows meet the existing annotation half-span rule. Both kick windows fail it: annotated episodes total only 1.6 seconds, so raw flags are sensitivity observations, not eligible-positive event recall. Boxing and squat events are empty, so their 31 raw context windows are not explicit normal-interval evidence. The crop is the same source and gets no independent source vote.

Under the final documented rule, all candidates tie on the one newly admitted normal window and preserve the raw context/kick guards. The grappling flag fractions rank 13/17, 13/17, 14/17, 15/17, which mechanically yields the frozen epoch-20 development choice. This audit reproduces that choice as history; it does not reselect a checkpoint using reserved results.

### Protocol limitations must remain visible

The policy is **not a pristine unchanged preregistration before all development outcomes**. It explicitly records two clarifications:

1. Kick was changed from an incorrectly described eligible-positive control to short-action sensitivity after inspecting frozen annotations. Policy states this preceded inspection of new milestone scores, although epoch-3 raw output had already been generated. This audit can verify the annotation reason, not independently reconstruct unrecorded score-access history.
2. Boxing/squat empty events were correctly separated from formal normal-window fractions **after development scores**, before reserved scoring. All four models' zero raw flags and zero flags on the one new normal window confirm that the clarification changes neither the guard outcomes nor the ranking here. It remains a protocol deviation, not retroactively fully predeclared normal evidence.

The intended three-new-development-group acquisition target was not achieved. The frozen choice rests on **one new normal source group and one eligible prediction**, with one old eligible contact source. That is extremely weak selection evidence even though the final rule's numerical ranking reproduces. Do not describe the unmet target as completed or the ranking as robust generalization.

Local metadata corroborates the declared freeze sequence: policy last-write 18:19:41.759983 UTC, choice receipt 18:19:42.399875, reserved admission 18:20:13.835384; baseline reserved report records start 18:20:31.205040 and candidate start 18:21:43.283962. These ordinary local timestamps and receipts are not authenticated timestamps or proof of all historical access. They support the documented sequence but cannot certify blinding independently.

## Quality sensitivity and comprehensive result document

The 187 quality-variant rows were also compared field-by-field across baseline/epoch 20, with exact per-record raw counts matching `round3-epoch20-quality-comparison-v1.json`. Pairing SHA is `cb8a1f7efc776aee0eedc6411fb7d4fd8f5e2bf678d90c36bf927c325d8b7399`.

The reported grappling 480p CRF23 13→15/17, grappling CRF35 16→17/17, kick CRF23 2→2/2, kick CRF35 1→2/2, cropped grappling CRF23 11→11/17 and CRF35 12→13/17 all reproduce. Boxing remains zero in five 12-window variants, squat context zero in 19 original windows. These are dependent compression/resolution transformations of known development sources, not new camera-quality accuracy or independent event detections. They were not another independent vote in milestone selection.

`training/ROUND3-RESULTS.md` was checked against training receipts/prior independent run audit, raw development/quality/reserved reports and the final receipt. Reported training counts, head-only 4,098 parameters, epoch steps/losses/resource figures, diagnostic flags, identities and no-promotion decision agree. Prior completed actual-run audit already established unchanged non-head state at all three epochs; this final metric audit did not repeat model-state loading or training.

A minor stale current-tense sentence initially said reserved scores were still unopened inside the historical acquisition section. Parent corrected it to historical tense and added the independently computed **31.227-second** union. Final document SHA reviewed after correction is `7231c4ec6fa0633c0f3d06dd275c46f8e413de33d45e830c1c3c667ad17e57e1`. No numerical/model-identity issue was found. Parent-reported 795 passed / 5 skipped in 59.64 seconds and public baseline CUDA-ready health are explicitly separate parent validations; this audit did not rerun the whole suite or independently query the live service.

## File pins and verification boundaries

| File relative to service/research | SHA-256 |
| --- | --- |
| runs/round3-selected-candidate-v1.json | `104426e0a81cf04997dfc03f8408cd58d8d7d98914bb68148e66332efa93a7e9` |
| github/MODEL-SELECTION-WAVE1.md | `75d66a706d55a4e0646fee272f9f5644356eadb3b6ff97f456cde6d1ff59d649` |
| evaluation/reserved-final-corpus-v1.json | `05b3593c1d927bbcd60e765fda4082335a40053e92cce29ce609e26778a83e79` |
| runs/reserved-final-admission-v1.json | `7201fb1a54551dddf0e99fe02a002a48a927dc10eb6f961b90aa4bf4d683999f` |
| runs/reserved-baseline-v1.json | `0fc5135c0008a898d040bae4a81895ec608d05ebd12f95bcaba9803c47045170` |
| runs/reserved-epoch020-v1.json | `8e1851a1a4ed46fc112968741314c6d6e046eddc73ef8d4bd3f68c3d3bf36eea` |
| runs/reserved-baseline-summary-v1.json | `cc848b5d24ed6bb95061ba0e5eb2f06eecb7edd6c7556733acbd7880e3de4152` |
| runs/reserved-epoch020-summary-v1.json | `f32a7c3fe6d4866f7b9d3f6736eb31ebc9e614efaddd343cc8efadea26e32495` |
| runs/round3-final-comparison-v1.json | `d2eb8c2e95803b23711556660485ffb9a1cff3eb1f85da7184a40245dd64b119` |
| runs/wave3-development-baseline-summary-v1.json | `3514543b19c2737df8ea71aae9fdfdb3e2bd9837a3da9c596696e34cab4a5df5` |
| runs/wave3-development-003-summary-v1.json | `78c828dde02602ff143f197e3132bad6c27ef470c2c845e58d9d15c743ee7bb1` |
| runs/wave3-development-010-summary-v1.json | `ff8f5db8f96e0a03106af4af18965f165902751728c1e102357159454f9c72d8` |
| runs/wave3-development-020-summary-v1.json | `2ae406a630babf7d1269ffe38cbeec1655a8546e0409cba587cfb86c3334c7ba` |
| runs/quality-x3d-cuda-v1.json | `8145895714e1e534150195064620d7112407adc73d601e121e66370e2d42e3f1` |
| runs/quality-community-v2-round3-e020-v1.json | `1d05fba0b04cc8c8311e1c221f4d20680f329270e9158ca6491e6528a677f496` |
| runs/round3-epoch20-quality-comparison-v1.json | `008b179909a955f76ca44e6a6020d6ab37f6911a852520eb0f53a15e03345046` |

Postprocessor source remained `6cead54bf4595a88819ac1cd151ae88276adbd5d4de3952783cc37b5a5b2fb58`; runner source remained `35f95c8134ead0c496b344f221cef3cc524467d002bf5c81217cb1fbd2859ad4`. Existing Python was used with bytecode disabled. Postprocessor execution was guarded against Torch/NumPy/OpenCV/model/runner imports. Calculations used standard-library JSON, hashing, counters and exact fractions. Additional artifact checks read checkpoint bytes for SHA only; no checkpoint deserialization, decoder or model execution was performed in this final comparison task.

Executed verification: two exact reserved-summary recomputations, four exact new-development-summary recomputations, all reserved cross-model identity fields, independent actual-span union/eligibility/episode accounting, old/new development pairing and rule reconstruction, 187 quality-pair identities/counts, final receipt links, all selected model/seal/manifest hashes and raw source-map identities. Assertions passed. This is actual-output metric verification, not a new model experiment or additional test-set outcome.

## Disposition and remaining uncertainty

**Retain the pinned live baseline; do not promote epoch 20 on these results.** The final receipt makes that decision and matches the underlying observations. More flagged proxy windows without another matched episode, together with an additional provisional normal flag, does not demonstrate the requested reliability upgrade. No alternative checkpoint is selected based on reserved outcomes in this audit.

The reserved groups are now observed and must be treated as spent for future tuning/model selection. Any later model/threshold/alert-policy iteration informed by these results needs fresh conservatively grouped evaluation material. Do not re-label these same groups as a fresh audit.

All annotation remains provisional assistant still-image review, with unknown margins, selective acquisition and source/author dependence. Pretraining overlap, actor/session independence and participant rights are not established by role hashes or licenses. Training remains one unresolved VID cohort with no independent calibration/holdout. The target conditions—50–100 visible people, real near-IR CCTV, low-light colour and representative compressed CCTV—are not demonstrated by six sports/drill proxy observations and brief easier normal controls. No production accuracy, camera-hour false-alert rate, general crowd/night performance or live-capacity claim follows.
