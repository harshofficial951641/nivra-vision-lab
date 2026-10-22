# Crowd observer CUDA smoke: visual coordinate and dedup diagnosis

21 October 2026. **CUDA compute and 17-joint runtime shapes are demonstrated by the parent's smoke run. Unique-person counting is not reliable.** The squat frames contain one apparent exerciser but five retained observations of that same body. Boxing contains obvious repeated/partial detections and at least one visually unsupported window/roof detection. The saved coordinates broadly align with the source imagery; no systematic translation/scale error was found in these eight frames. Exact official preprocessing/output parity remains unverified.

This helper performed **no model initialization, inference, GPU job or live-service interaction** for this diagnosis. Only this document and evidence under ignored `service/research/runs/crowd-observer-visual-v1/` were written. Observer implementation, tests, existing reports, source media and the live X3D baseline were preserved. Findings are static-frame assistant inspection, not continuous-motion review, human ground truth or a new fight evaluation.

## Immutable inputs and inspected code snapshot

All hashes below were computed from actual local bytes. The report/profile and current inspected code are preserved separately in [pins.json](../runs/crowd-observer-visual-v1/pins.json). The smoke report does not embed source-code hashes: these code pins identify the **current inspected snapshot**, not an independently proven historical run-time code revision. Plain-text snapshots of the three Python files and prior implementation document are retained in the evidence directory.

| Artifact | SHA-256 |
|---|---|
| [Parent report](../runs/crowd-observer-cuda-mixed-profile-v1.json) | `8080ab582f351e59aad22277caea161143f2e2029532fa5370cd9e208e755f59` |
| [Raw ORT profile](../runs/crowd-observer-cuda-mixed-profile-v1.operators/ort_2026-10-21_22-48-00.json) | `81a364816d5767fd9b2d12c3f68b9b293e6fd9b340091c33ffc9893877b7256c` |
| [Observer implementation](../../nivra/crowd_observer.py) | `06b3ffd71dd7cd57941f1bce4f50f5e0fb52ee30fc1fe6cf626d7df941f3706d` |
| [Research CLI](../../research_crowd_observer.py) | `de146a85292202f57e622615ce46d02a0e149865eb87f3c7e23f372f1ffbb9ea` |
| [Observer tests](../../tests/test_crowd_observer.py) | `6f3d96c2d7f5d484e77ec31e587d31df7c0d24fc30b8644d984555cb89b19e39` |
| [Prior observer document](CROWD-OBSERVER.md) | `148519d09b648f9a377cb72288e7c99677239b4b6b2e77044fe2c0ddbf5853d4` |
| Raw corpus JSON | `33d04d15bc4a6911face456fff7488320906505cc344f863042e4cae304bfb34` |
| Actual RTMO ONNX | `750d872151ff4652f02c738efc3a547e112ce9b688fe920bc17f948e8c3afdac` |
| Actual official SDK archive | `6b9d3be1323cc030444f731bbe593ea61f59b9481e23da2f8b60cb4b72136e16` |

The original media hashes also match the corpus: boxing `2dd4c6269c120978630b1a1e1fd3819b53d75b02dd1b9a6e34a5e9e9de966430`; grappling `1004027ef030303bef37144da30363aff7bdacda585d76d58b837d6db0272064`; kick `752181dd7417113744baf0337a0682fd10813575cb8d327057957a164246455f`; squats `ea9151e447b301985d5d65666551ef863b369a2e0f3a71ddd58abef2e722f96a`. No media was downloaded.

## Exact source frames and visual evidence

Each original was decoded sequentially with local OpenCV/FFmpeg, `cv2.setNumThreads(1)` and one decoder thread, stopping at the last selected frame index: **89 frames decoded, eight selected frames visually inspected**. Every decoded timestamp up to that index had to increase; each selected PTS matched the parent's saved PTS within **1e-6 ms**. Nominal FPS was never read. Eight lossless native source PNGs were saved, plus native-coordinate overlays generated exclusively from the report's already-retained outputs.

Every six-panel board was actually inspected with `view_image`: original source followed by global V0 and native-source V1–V4 crops. Four additional original/marked focus panels were inspected. Full-frame/per-view overlays are also retained. Skeleton joints/edges are drawn only for saved confidence >=0.3; this is a display threshold, not a revised model policy. `O0`, `O1`, etc. are observation-array indices **within that frame**, not identities or temporal tracks.

| Frame | Source index / actual PTS ms | Native dimensions | Eligible before dedup → retained | Retained by V0/V1/V2/V3/V4 | Inspected board |
|---|---|---|---:|---|---|
| Boxing A | 0 / 0.000 | 1920x1080 | 59 → 39 | 3/9/13/3/11 | [RGB/views](../runs/crowd-observer-visual-v1/00-boxing-idx0-pts0.000-views.jpg) |
| Boxing B | 31 / 1021.000 | 1920x1080 | 30 → 20 | 2/6/5/2/5 | [RGB/views](../runs/crowd-observer-visual-v1/01-boxing-idx31-pts1021.000-views.jpg) |
| Grappling A | 0 / 0.000 | 880x608 | 61 → 49 | 7/15/8/13/6 | [RGB/views](../runs/crowd-observer-visual-v1/02-grappling-idx0-pts0.000-views.jpg) |
| Grappling B | 25 / 1000.000 | 880x608 | 120 → 94 | 6/28/32/12/16 | [RGB/views](../runs/crowd-observer-visual-v1/03-grappling-idx25-pts1000.000-views.jpg) |
| Kick A | 0 / 0.000 | 1280x720 | 24 → 14 | 1/2/4/2/5 | [RGB/views](../runs/crowd-observer-visual-v1/04-kick-idx0-pts0.000-views.jpg) |
| Kick B | 24 / 1001.000 | 1280x720 | 29 → 16 | 4/2/1/5/4 | [RGB/views](../runs/crowd-observer-visual-v1/05-kick-idx24-pts1001.000-views.jpg) |
| Squats A | 0 / 0.000 | 720x1280 | 5 → 5 | 1/1/1/1/1 | [RGB/views](../runs/crowd-observer-visual-v1/06-squats-idx0-pts0.000-views.jpg) |
| Squats B | 5 / 1000.000 | 720x1280 | 5 → 5 | 1/1/1/1/1 | [RGB/views](../runs/crowd-observer-visual-v1/07-squats-idx5-pts1000.000-views.jpg) |

Across these eight frames: **373 raw slots, 333 eligible observations, 242 retained observations, 91 duplicate removals, zero cap omissions**. These totals sum repeated samples/views and are not counts of unique humans. Every reported call has one more raw slot than eligible observations; the discarded row's contents were not saved, so it is not independently classified as a padding/sentinel row here.

## Diagnosis: squats is a confirmed cross-view duplicate failure

Both RGB frames show one apparent exerciser. All five retained observations attach to that same visible body. The global box covers the full body; upper tile boxes omit feet/lower legs and side regions, while lower tile boxes omit the head/upper body. Shared anatomical points align after inverse scale and source-view translation.

| Squat frame | All ten retained-pair IoU range | Each tile vs global: intersection / smaller box area | Shared joints with confidence >=0.5 | Median shared-joint distance to global |
|---|---:|---:|---:|---:|
| A, 0 ms | 0.3021–0.6499 | 0.9744–0.9925 | 8–13 | 1.80–5.63 native pixels |
| B, 1000 ms | 0.3301–0.6208 | 0.9809–0.9841 | 8–13 | 1.83–3.13 native pixels |

The IoU>=0.7 suppression rule therefore does exactly what its implementation says: **none of the ten pairs qualifies for merging**. This is a design failure for complementary partial views, not an arithmetic failure of the threshold comparison. A near-contained smaller partial box can have very high intersection-over-smaller-area and low IoU with the full-body box.

Three of five observations in each squat frame have `clippedByView=true`. The other flags do not establish full-body visibility: for example Squats A O3/V3 has `clippedByView=false`, yet the crop visibly excludes the head. That flag reports whether the **predicted box** needed numeric clipping, not whether the physical person's body was truncated by the tile. All five scores are around 0.98–0.99, so simply raising the score threshold would not resolve this duplication.

The 1.8–5.6px common-joint agreement, correct left/right view translations and visual alignment strongly support mapping consistency for this subject. They do not establish exact upstream raw-output parity or correctness of hidden/inferred joints. No additional person is supported by the squat imagery; the five boxes should not be presented as five people.

## Boxing: duplicates plus visually unsupported detections

The first frame has three clear full foreground people and a fourth partial figure on the right; the second shows four foreground people more fully. No exhaustive independent person annotation was made. The report's 39/20 outputs materially overstate distinct supported foreground observations.

- **Partial and loose duplicates:** Boxing A O10/V0 is a full-body box on the left exerciser; O6/V1, O9/V1, O22/V1, O26/V1, O27/V1 and O34/V1 describe that same visible body at different extents. O34 is a very loose box containing much background while its joints attach to the exerciser: [native focus, original left/marked right](../runs/crowd-observer-visual-v1/focus-frame00-O34.jpg). Boxing B O2/V0 and O4/V1 similarly overlap the same left person; O0/V0 and O6/V1 depict the smaller central person; O3/V4 and O7/V2 depict the right person. A one-person-per-view assumption or inter-view-only suppression is insufficient because loose/nested detections also remain **within** a view.
- **Boundary fragments:** Boxing A has 23/39 retained observations numerically clipped by a view. Several thin boxes are attached to the left boundary x=672 of right-hand tiles, sampling a sliver of the same foreground body. Other boxes at the right source edge depict the partial right figure. This is not evidence of additional people.
- **Visually unsupported window detection:** Boxing B **O11/V2**, score 0.278, box `[1421.5,0.5,1647.3,91.4]`, lies on the bright upper window/roof region. Its [native focus](../runs/crowd-observer-visual-v1/focus-frame01-O11.jpg) has no visually supported human body. This is a provisional assistant false-positive diagnosis on that saved frame, not a systematic false-positive rate.
- **Human-shaped wall feature:** Boxing A **O38/V1**, score 0.159, and Boxing B **O17/V1**, score 0.194, repeatedly attach a pose to a dark human-shaped feature on the blue wall. [A focus](../runs/crowd-observer-visual-v1/focus-frame00-O38.jpg), [B focus](../runs/crowd-observer-visual-v1/focus-frame01-O17.jpg). Neither crop clearly supports a physical person there; whether the feature is paint, a depiction or another background artifact cannot be established from these two frames. Both have 12 joints above confidence 0.5, illustrating that high joint scores alone do not establish a real scene person. This remains an uncertain background/depiction case rather than an asserted identity or live-human count.

The clear window false positive is not removed by associating partial views of real people. Conversely, most nested/body-edge duplicates are not evidence of hallucinated extra bodies: their joints visibly attach to existing people. These error classes need separate treatment.

## Grappling and kick: contact/occlusion plus real spectators

The grappling sources contain **many real background spectators**, not merely the two foreground grapplers. The 49/94 retained observations include detections attached to actual spectator silhouettes and seated people as well as repeated foreground boxes, partial/head-only regions and uncertain extrapolated limbs under occlusion. Foreground joints broadly follow the grapplers; several limb assignments are ambiguous across overlapping bodies. The dark, small background does not support an exact human census from this review. It would be wrong to label all 94 observations hallucinations or to claim 94 unique humans were successfully detected. No per-observation background ground truth was fabricated.

Kick A shows a standing ring participant, another low/partly obscured figure, a striped official, ringside people and a spectator background. O0/V3 is a relatively full box on the central standing participant, while O3/V1 is a partial upper-body view of the same person. Kick B shows overlapping ring participants; O4/O5/O10/O12 in V3 cover their shared image region at different extents, and joint-to-person assignment can mix bodies. This is unsuitable for actor attribution without additional association and uncertainty handling. Broad coordinate placement is plausible, but neither pose quality nor contact interpretation is independently validated.

## What the coordinate and preprocessing checks establish

All 242 retained box/keypoint records passed independent checks against the saved frame dimensions and view geometries: pixel coordinates agree with saved normalized coordinates within 1e-9 absolute tolerance; all 17 joints and boxes remain inside their declared source view; report ratios match the intended 640-input scaling. All retained pairs have IoU<0.7, consistent with the declared suppression rule. These checks validate **internal numerical consistency**, not upstream model parity. The visually aligned squat and foreground sporting poses argue against a gross missing tile translation or systematic coordinate offset in these examples.

The official SDK ZIP was hash-verified and only its three small JSON files were read/copied: [pipeline.json](../runs/crowd-observer-visual-v1/sdk-pipeline.json), [detail.json](../runs/crowd-observer-visual-v1/sdk-detail.json), [deploy.json](../runs/crowd-observer-visual-v1/sdk-deploy.json). They confirm BGR (`to_rgb=false`), mean 0/std 1, pad value 114, 640 input and `BottomupResize`. Thus there is **no colour-swap or 0..1 normalization discrepancy identified** between the observer and this metadata. The archived export configuration records `keep_top_k=50`; that is export metadata, not measured visible-human recall or proof of the runtime graph's effective maximum.

**Placement parity is still an open issue:** the observer's [letterbox](../../nivra/crowd_observer.py#L76) resizes into the top-left corner. The archived package identifies MMPose 1.2.0; its pinned [BottomupResize implementation, lines 565–592](https://github.com/open-mmlab/mmpose/blob/6d10b2ec81da7e252016b3154c7fdb46c403ecd8/mmpose/datasets/transforms/bottomup_transforms.py#L565) constructs an image-centred affine resize, and its [warp helper explicitly maps to the output centre](https://github.com/open-mmlab/mmpose/blob/6d10b2ec81da7e252016b3154c7fdb46c403ecd8/mmpose/structures/bbox/transforms.py#L410). Source was fetched for inspection only, saved as text; the resize source SHA-256 is `595bbb5f3c74c8f9202d23f6b4a3fa15cae258b5da384f04d2a82c1e07b77e0d`, and both source pins are in pins.json. No upstream code was executed. The SDK transform implementation and a canonical reference forward pass were not run/verified. Therefore this is a concrete **reference-parity question**, not proof that padding placement caused the extra boxes. Switching preprocessing without adjusting inverse coordinates would itself create a mapping bug; these changes need a separate authorized parity experiment.

Raw per-view tensors, pre-clipping boxes and suppressed observations are absent from the parent JSON. They cannot be reconstructed faithfully from retained clipped outputs. Consequently this review cannot independently replay the full 333-candidate suppression sequence, inspect each discarded row or prove exact canonical preprocessing/output parity. The 91 reported removals are telemetry, not individually visually reviewed removals.

## Actual execution and profiled host-wall timing

The raw 10,289,131-byte / 24,882-event ORT trace was reread and its provider/operator execution counts independently recomputed. They match the report: **20,680 CUDA node executions**, including **20,280 non-memcpy CUDA executions**, **4,000 Conv executions** and 400 MemcpyFromHost executions; **4,120 CPU executions**. CPU types are Gather 1,480, Concat 1,040, Slice 680, Unsqueeze 520, Mul 120, Less/Reshape/Where 80 each and Div 40. These are executed-event counts, not independent inputs or accuracy samples. The report's unique executed node-name counts are CUDA 517 and CPU 103. CUDA computation is real, while intentional CPU operators remain material and disclosed.

All 40 saved calls returned detection `[1,S,5]` and pose `[1,S,17,3]`, with actual per-call S ranging **2–39**. The symbolic metadata limitation is resolved for these calls only; no call demonstrates a 100-person output or an unseen-scene capacity guarantee. Five-view aggregation reaches 94 retained boxes, but that is not a 94-person result.

| Recorded metric, all samples included | Minimum | Median | p95 | Maximum |
|---|---:|---:|---:|---:|
| 40 per-view ORT host-wall calls, ms | 33.10 | 39.81 | 50.38 | 784.33 |
| 8 complete observer-frame host-wall calls, ms | 212.57 | 253.61 | 778.28 | 1020.54 |

The first global ORT call is the 784.33ms outlier; no predeclared warmup was excluded. As a **post-hoc descriptive statistic only**, the remaining 39 calls have median 39.68ms and p95 48.68ms; this is not a controlled warm steady-state benchmark. Per-view ORT wall time sums to 2,345.03ms; full observer-frame wall time sums to 2,821.45ms. Whole processing before serialization is 10,530.14ms and includes other stages, so neither summed ORT time nor its inverse is end-to-end FPS. The health guard reports 41 checks and 0.265s guard wall time. Full frame timing includes that yielding, preprocessing, host/CPU output transfer and dedup; per-view ORT time excludes yielding. Profiling overhead remains enabled throughout.

No standalone GPU kernel latency, total device peak, process GPU peak, independent repeat variability, sustained throughput, multi-camera load or live-service interference measurement was supplied here. The 1GiB CUDA arena setting is not a total-device memory measurement. No memory-fit or 100-person capacity claim follows.

## Proposed next experiment, not an applied fix

1. Preserve this pinned smoke evidence and confirm canonical RTMO preprocessing/inverse mapping on the same fixed frames, retaining bounded **raw per-view tensors and pre-clipping boxes** for audit. Keep the live model unchanged. Any centered-padding comparison must transform coordinates consistently and be reported as a separate policy.
2. Test cross-view association using several mutually confident shared joints plus boundary/containment evidence, with a full-body/global anchor where supported. Do not let a slightly higher-confidence cropped fragment automatically define the unique-person extent. Make uncertain association explicit and keep work budgets bounded.
3. Handle same-view nested proposals separately. Pure IoU misses loose or heavily truncated semantic duplicates. Do not globally replace it with intersection-over-smaller-area alone: two distinct grapplers can strongly overlap, so that rule could merge actual people.
4. Evaluate unsupported background/depiction detections on a frozen negative set. Raising a score or joint-count gate on these eight frames is not a validated fix; the squat duplicates have very high scores, and the wall feature has many confident joints. Do not tune the source diagnostics and then call them unseen evaluation.
5. Use controlled unique-person annotations for count/localization assessment, including partial-view and overlapping-person cases. Keep detector observations, unique-person estimates and action coverage as separate quantities. Only then progress to licensed/representative real near-IR CCTV and low-light colour, with native HD and explicitly degraded 480p variants.

None of these recommendations was implemented here. This report does not compare fight classifiers or alter the decision to retain X3D-M.

## Evidence and verification limits

The ignored directory contains **8 source PNGs, 60 JPEGs** (8 complete overlays, 40 per-view overlays, 8 inspected boards, 4 inspected focus panels), sampling/analysis/visual-note JSON, SDK metadata, pinned source/code text snapshots and three local reproduction scripts. [frame-index.json](../runs/crowd-observer-visual-v1/frame-index.json), [analysis.json](../runs/crowd-observer-visual-v1/analysis.json) and [visual-review.json](../runs/crowd-observer-visual-v1/visual-review.json) separate decoded facts, numerical checks and assistant interpretation. [evidence-manifest.json](../runs/crowd-observer-visual-v1/evidence-manifest.json) pins generated evidence files.

Checks performed: exact report/profile/model/archive/corpus/media hashes; strict exact-index/PTS reconstruction; actual inspection of all eight RGB boards and four focus panels; normalized/pixel/view bounds and dedup-rule consistency; independent raw-profile count reconstruction; document links and unchanged inspected code hashes. No implementation change or inference was made, so model tests/GPU jobs were not rerun. Decode and analysis scripts are bounded CPU-only evidence work and never import the observer, ORT or Torch.

Eight static development frames do not establish continuous interaction quality, independent person recall, a camera-hour false-positive rate or a crowd/night holdout. Real spectators are visible in sporting backgrounds, but their exact count and visibility are unannotated. Dark sporting backgrounds are not evidence of near-IR CCTV or a validated low-light-colour surveillance domain. No thermal or genuine IR/night test was added. These limitations remain even though the smoke proves actual CUDA compute and observed 17-joint outputs.
