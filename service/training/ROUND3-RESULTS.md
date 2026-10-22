# Round3 GPU training and development diagnostics

The audited continuous 20-epoch community X3D-M head adaptation completed on the GTX 1660 Ti. The live model remains unchanged. This is an offline research candidate, not a validated crowd/night fight detector.

## Completed training

- Clean manifest: 127 recordings, 163 four-second windows, 91 positive / 72 normal; SHA256 `68cf0c4048dcc9d4d10e5553bf5bcf9be6cd6ab36bd7aeaff23208f2b55e0970`.
- One continuous trajectory, seed 17, fixed weighted probability NLL, AdamW learning rate 1e-5, accumulation 8. Only the existing Linear weight/bias are trained: 4,098 parameters. The entire model stays eval, including BatchNorm and dropout.
- 20 epochs, 420 optimizer updates, 3,260 microbatches; 369.346 seconds. Weighted pre-update training NLL: epoch 1 = 0.482449, epoch 3 = 0.467883, epoch 10 = 0.422405, epoch 20 = 0.370260. This is training fit, not accuracy or independent validation loss.
- Torch allocator peaks: 192.634 MiB allocated / 240 MiB reserved. These exclude the live service, desktop, driver and decoder; the 35% allocator allowance is not a total-device limit. Decoded CPU cache: 930.091 MiB, 163 misses / 3,097 hits / zero evictions.
- Complete root seal: `0584dec4936ea5c7b1461974985adbf405b8825eb633b037ac4f8ef1e3e7c509`. All three safe artifact validators passed, including required runtime/dependency provenance and full-run/sibling checks.
- Before fitting, real CUDA zero-step outputs exactly matched the independent baseline on three old development windows (maximum absolute error zero). Strict CPU decoder preflight read 19,661 frames across all 163 training windows without requiring FPS timestamp reconstruction.

The completed [independent actual-run audit](../research/github/ROUND3-RUN-AUDIT.md) found no blocking artifact/source/runtime/provenance/state/accounting issue. It verified all 212 snapshot copies and all 561 non-head tensors exactly equal to baseline at each milestone, with head weight/bias changed between milestones. No random new classifier or new activation was introduced. The audit did not execute a trained forward pass or independently replay optimizer history; the paired parent GPU diagnostics below are separate empirical evidence.

## Existing development comparison

All three milestone reports match the baseline's exact 67-window pairing hash `d42745b6512c14d2854e3a7eacb6a2adcaff58d324d2ee86b94db358b8c2c408` and policy hash. Selected frame timestamps, media hashes and window bounds were compared individually.

| Source/view | Windows | Baseline flags | Epoch 3 | Epoch 10 | Epoch 20 |
|---|---:|---:|---:|---:|---:|
| Boxing / shadowboxing | 12 | 0 | 0 | 0 | 0 |
| Grappling | 17 | 13 | 13 | 14 | 15 |
| Short kick control | 2 | 2 | 2 | 2 | 2 |
| Squats | 19 | 0 | 0 | 0 | 0 |
| Cropped grappling | 17 | 10 | 10 | 11 | 11 |

These are strict >0.5 flagged windows, not independent events or an accuracy percentage. Cropped grappling is the same source footage. The short kick annotations do not cover half a four-second window; its two flags are a sensitivity control, not takedown/kick event recall. Epoch 3 changed no decisions. Epoch 20 adds two original-grappling and one dependent-crop flags. One original contact source cannot establish generalization.

Ignored raw reports and the paired summary remain under `service/research/runs/`, including `round3-existing-development-comparison-v1.json`. The three full CPU-state artifacts remain in `service/training/runs/community-head-nll-v2-round3-e20/epoch-003`, `epoch-010` and `epoch-020`.

## Epoch-20 compression/resolution sensitivity

The epoch-20 candidate completed all 187 paired quality-variant windows. Every media hash, selected frame timestamp and window bound matches the previously frozen baseline run; pairing SHA256 is `cb8a1f7efc776aee0eedc6411fb7d4fd8f5e2bf678d90c36bf927c325d8b7399`.

| Source/view | Baseline flags | Epoch-20 flags |
|---|---:|---:|
| Grappling, 480p CRF23 | 13/17 | 15/17 |
| Grappling, 480p CRF35 | 16/17 | 17/17 |
| Short kick, 480p CRF23 | 2/2 | 2/2 |
| Short kick, 480p CRF35 | 1/2 | 2/2 |
| Cropped grappling, 480p CRF23 | 11/17 | 11/17 |
| Cropped grappling, 480p CRF35 | 12/17 | 13/17 |

Boxing remains zero across all five original/720p/480p quality variants (12 windows each); squats remains zero across its 19 original windows. The heavily compressed kick changes one flag. These remain dependent derivatives of existing development footage, not additional independent sources, event recall or camera-quality accuracy. Quality variants do not enter milestone selection. Raw results and the comparison receipt are under `service/research/runs/quality-community-v2-round3-e020-v1.json` and `round3-epoch20-quality-comparison-v1.json`.

## Development admission and offline selection

Epoch 20 was selected as the offline candidate before any reserved predictions were opened. All four models had zero flags on the one eligible new exercise-normal window; 15 additional prediction windows in that clip remained unknown. Epoch 20 improved the original grappling control while preserving raw flags on the other historical controls. The [selection rule](../research/github/MODEL-SELECTION-WAVE1.md) excludes training loss. It documents both the short-kick annotation correction before milestone scores and the later clarification that historical empty-event boxing/squat corpora are raw context guards rather than explicit normal-interval evidence. That later clarification did not change the all-zero guard outcomes or model ranking, but remains a protocol deviation. The three-new-development-group acquisition target was not achieved; selection rests on one new normal source and one eligible prediction window.

Dense review of the first online normal pool retained only nine of 49 proposed windows: 36 seconds across three reserved-audit source groups. Forty windows became unknown, including all twelve proposed development windows. Parent independently checked all ten source hashes, 147 sheet hashes, 5,708 unique consecutive frame references, original interval matches and boundary coverage. These unknown windows are excluded from normal scoring; the earlier sampled-screening count of 49 is superseded for eligibility. Eight supported seconds are easier controls, including four animal-only seconds, and are not representative human-interaction evidence. Additional model-blind licensed normal acquisition was assigned to fill the development gap before selection. At that stage reserved scores remained unopened; the completed final comparison is reported below.

Wave2 froze eight new author groups, but acquired only two files (4,305,132 bytes) before HTTP 429 stopped acquisition. Dense review supplied one reserved four-second easier rhythmic-motion control and zero development windows. The development opening stayed unknown. Its review SHA256 is `f92be4c8cd5e4d623b701c8349ca4c7751c0e57994d4ac21cd5a155d165f9330`; both acquired media hashes were independently checked. That did not close the selection gap. A separate bounded search of official public-domain exercise sources was then assigned without retrying rate-limited Wikimedia downloads, changing roles or consulting reserved scores. Reuse terms and actual clear four-second coverage were required before admission.

Wave3 subsequently acquired eight official exercise sources and retained one development and one reserved four-second ordinary-motion interval. Six sources stayed unknown. Parent verified the development working/source/rights hashes, all 121 consecutive covering-frame indices, actual timestamp coverage through 4004 ms and zero decoder-to-annotation offset. The admitted development corpus SHA256 is `8b2dec120c1eca991e4621c8441996546b92b5f518112b8205345648ce18012f`. Baseline and all three milestone GPU reports paired exactly on 16 windows, one explicitly normal and fifteen unknown. All four models left that normal window unflagged. These are easier exercise controls, not CCTV/crowd/night evidence; government file-level public-domain claims and applicable restrictions are preserved without claiming worldwide copyright or participant-release clearance.

## Final reserved comparison and decision

The frozen audit corpus contains 11 recordings from eight source groups, with 39 seconds of sports/drill contact-proxy annotation and 44 seconds of ordinary-motion annotation. Corpus SHA256: `05b3593c1d927bbcd60e765fda4082335a40053e92cce29ce609e26778a83e79`. The chosen epoch-20 artifact was `7c58a0f2e6ffc63ebdc4ab2df7b15882d90c3a14e0bc892f55f4e2760471e30f`; its identity and threshold were frozen in `round3-selected-candidate-v1.json` before reserved scoring.

Only unchanged baseline and the selected epoch-20 candidate were run on this corpus. Both completed 593 exactly paired windows: pairing SHA256 `db0ec4acfe85c1bb6d52e2af9204002d72796a6ea6b4b4e9874dcea35251618f`. Parent compared every source hash, crop, actual window span, dimensions and selected timestamp list. The audited JSON postprocessor verified both reports and excluded 471 unknown windows from label-based results.

| Reserved diagnostic | Baseline | Epoch 20 |
|---|---:|---:|
| Flagged contact-proxy windows | 58/82 | 67/82 |
| Compatible recording proxy episodes matched | 6/6 | 6/6 |
| Flagged explicitly normal windows | 14/40 | 15/40 |
| Normal solo-dancing source | 14/30 | 15/30 |
| Normal embrace source | 0/9 | 0/9 |
| Normal drum-performance source | 0/1 | 0/1 |

The six episodes are sports/drill proxies in only three source groups, not six independent hostile fights. The 82 positive and 40 normal windows overlap and are dependent. Both models already match all six proxy episodes; the candidate adds nine positive-window flags but also one ordinary-dance flag. Increased sensitivity does not establish improved alert reliability.

Two admitted normal recordings (`online-normal-07` and `wave3-government-125927`) have zero compatible fully normal prediction windows: their isolated four-second labels do not align with the fixed prediction stride/context. They remain explicit coverage gaps, not negatives with zero false flags. The union of eligible normal prediction spans covers only 31.227 seconds of the 44 annotated seconds. Neither the annotated total nor this small curated covered duration establishes an operational false-alert rate. No bounds were extended or windowing changed after reserved scores.

**Decision: retain pinned baseline X3D-M in the live demo. Do not promote the epoch-20 research candidate.** It has not demonstrated the requested accuracy upgrade. Keep the complete trained run for reproducible offline use. Raw reports, summaries, admission/selection identities and the final comparison receipt remain under `service/research/runs/`. The reserved groups are now spent if their results inform further tuning; a later model requires fresh evaluation groups.

Final service validation: **795 passed, 5 skipped**, one existing Starlette/AnyIO deprecation warning, 59.64 seconds. The opt-in real-CUDA regression was disabled during the CPU suite; actual GPU fitting and comparisons are separately recorded above. Public health was checked and reported ready on CUDA with baseline X3D-M. No live model, public service, threshold, UI or deployment changed in this round.

## Remaining limits

The training cohort has no independent VID holdout/calibration. Twenty-seven retained older positive sources still have sampled-frame review uncertainty; other annotations remain provisional assistant judgments rather than human ground truth or full-motion interpretation. Additional public sports/drill clips are proxies, not hostile-fight labels. All online evaluation sources remain outside fitting.

Crowd observer GPU execution is verified, but its visual check found partial/nested duplicate observations and a visually unsupported detection; upstream preprocessing parity also remains unresolved. It stays offline. Real 50–100-person recall, near-IR night, low-light colour, camera-hour false-alert rate and production detection accuracy remain unverified. Grayscale/darkening, tiling and a 100-observation cap do not establish those capabilities.
