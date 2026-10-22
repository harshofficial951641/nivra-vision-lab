# GitHub-first detector comparison

21 October 2026. Research and test alternatives before choosing another training
run. Preserve the live NIVRA service and current app while candidates are staged.

## Decision criteria

1. Confirm what is actually released: runnable inference code, downloadable
   checkpoint, exact architecture/class order/preprocessing and reproducible pin.
2. Audit code licence, checkpoint terms and training-data provenance separately.
   GitHub visibility, a code licence or a README accuracy number does not prove
   compatible model/footage rights or NIVRA detection quality.
3. Prefer fewer missed physical-fight events with no additional false alerts,
   then measure classifier latency and memory on the GTX 1660 Ti 6GB. Include
   Windows/Python compatibility and live-stream engineering maturity.
4. Run comparable candidates on identical source-time windows, using each
   checkpoint's required preprocessing. Fix policies before scoring; do not tune
   on the diagnostic clips and then label those clips an unseen test.
5. Build an isolated backend adapter for a winner. Adopt useful code independently
   of accuracy claims. Do not replace NIVRA's existing interface with a repo demo.
   If no candidate beats the baseline, retain it and choose a suitable training
   foundation. New training remains offline until its diagnostics pass.

## Required operating conditions

Harsh confirmed both IR/black-and-white CCTV and low-light colour footage, with
unknown camera resolution: assess native 1080p and 720p where available, plus
explicitly degraded 480p copies. Upscaling a smaller source is not a native
higher-resolution test. Record source dimensions, codec/compression, frame rate,
person pixel height, visible crowd size and occlusion for each real recording.

Target scenes contain 50-100 visible people. Measure scene-level alerts and
interaction localization separately. Inspect person limits, detection/tracking
coverage, region scheduling, dropped regions and time-to-alert under load; a
whole-frame binary score or raising a configured limit does not establish crowd
coverage. Evaluate physical fights alongside ordinary crowded interactions.

Synthetic degradation tests measure sensitivity, not real-camera accuracy.
Grayscale/darkened daytime video is not genuine IR/night validation; thermal
long-wave IR is also distinct from typical near-IR CCTV. Synthetic tiled crowds
may support compute-load tests only. Report absent representative/licensed
footage as an unverified operating condition. Do not claim these requirements
are met from the existing few-person diagnostic recordings.

## Current evidence boundary

The live baseline is a community fight-tuned **X3D-M**, with pinned safe loading
and a fixed >.5 backbone-score threshold. MC3-18 from MohamedSebaie's repository
was already tested: both matched 2/3 original diagnostic events; MC3 added a
shadowboxing false alert. See `../../evaluation/FIGHT-MODEL-COMPARISON.md`.

The existing corpus contains four original recordings totalling 39.221 seconds,
plus a synthetic crop of one recording. All have influenced development. They
are diagnostics, not evidence of production accuracy or an independent holdout.
Published percentages across different datasets/splits are not directly ranked.

Our latest CUDA final-stage/head experiment used 96 VID training recordings and
156 windows. It fitted training data but underperformed the existing wrestling
diagnostics; it was not promoted. VID remains one unresolved training cohort,
with no calibration/holdout. Do not reuse it as a claimed independent evaluation.
See `../../training/ROUND2-RESULTS.md`.

## Execution

Use primary GitHub/model-author/paper sources. Pin shortlisted revisions and
checkpoint bytes, inspect source before execution, disable remote custom code,
and avoid unsafe pickle loading. Download only selected public assets; no account
creation, purchase, agreement acceptance or author contact. Keep external repos,
environments, large weights and raw reports ignored. Parent coordinates all GPU
jobs and checks/yields to the live demo. No automatic live promotion.
