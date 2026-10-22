# VID pilot results - 21 October 2026

## Decision

**Do not promote this pilot.** Both CPU- and GPU-trained heads fit their VID training
windows but flag none of the existing wrestling diagnostic windows. The deployed
community X3D-M remains active. No improved detection or independent accuracy has
been established.

## Data and experiment

554 videos were imported from the creators' CC0 VID V2 deposit. Of 48 clips
screened through 16 timestamped frames, 36 entered the provisional train-only
manifest: 8 positives and 28 normals. This yields 76 four-second windows: 14
positive and 62 normal. Unclear spans and unreviewed clips are excluded.

All VID material is kept in one unresolved session cohort. Calibration and
holdout are empty. These are assistant-screened, provisional training labels,
without continuous-motion or human review. See [DATA-RIGHTS.md](DATA-RIGHTS.md).

The candidate uses official Kinetics X3D-M frozen features and a fresh linear
head, not full-backbone fine-tuning. Fixed settings: seed 17, 100 epochs, AdamW
learning rate .01, weight decay .01, batch size 32, training-only class weights,
FP32, and an uncalibrated >.5 decision threshold. No diagnostic scores were used
to tune the threshold.

Manifest SHA-256:
`fc742397e912a22f8a7d32f893c2d105b87e4d68a2ad9ffe803a184dece5c0fd`.

The CPU fit took 141.488 seconds. Both training classes were fitted without an
error; this describes memorisation/fit, not evaluation. Its artifact is
`runs/vid-pilot-v1/candidate-head.pt`, SHA-256
`e0bffe3de41d3adf8525ac0589466c9abfac66862132d1d0dd789de02ca740c8`.
The exact executed implementation snapshots match the hashes in its report.

The CUDA rerun on the **GTX 1660 Ti** completed in **101.360 seconds**, with both
feature extraction and head backpropagation on CUDA. Peak PyTorch allocation was
127.757 MiB and peak reservation 156 MiB, excluding the driver, live service and
other processes. Its allocator cap was 40% of GPU memory; it checked the live
demo's busy state before feature jobs and fitting. This is cooperative scheduling,
not an exclusive cross-process GPU lock. The public health endpoint remained ready.

GPU artifact: `runs/vid-pilot-gpu-v1/candidate-head.pt`, SHA-256
`e71f269432078ec61ab37c4ed9f20f7c908c59c572d48181a9a1e2d82dcca4d8`.
All three implementation snapshots match its report. The completed pilot-tool
suite passed 218 tests, including real CUDA feature extraction/head gradients;
two Windows symlink tests were skipped. Later fine-tuning additions require their
own validation.

## Existing diagnostic footage

All clips below have previously influenced development. They are diagnostic,
regardless of historical corpus split names. Counts are review decisions on
identical causal four-second windows; they are not incident counts or accuracy.

| Recording | Windows | Current community model >.5 | CPU pilot >.5 | GPU pilot >.5 |
| --- | ---: | ---: | ---: | ---: |
| Shadowboxing | 12 | 0 | 0 | 0 |
| Grappling | 17 | 13 | 0 | 0 |
| Staged wrestling kick | 2 | 2 | 0 | 0 |
| Squats | 19 | 0 | 0 | 0 |
| Grappling crop | 17 | 10 | 0 | 0 |

The crop reuses the grappling recording and is not independent. Brief kick
content also differs from the majority-positive training-window definition;
context overlaps are logged without inventing binary ground truth.

The CPU diagnostic report is `runs/vid-pilot-v1/diagnostics.json`, SHA-256
`814d2e8601077ddde7c39a8cc822902dac3801cc383e6d21bac781be4d93a8fc`.

The GPU-trained candidate's diagnostic report is
`runs/vid-pilot-gpu-v1/diagnostics.json`, SHA-256
`f43f5698a2afd46a84f175005c463f9a8577683161ca840fbb03fe9b94d3f54b`.

## Next experiment requirements

Expand continuously reviewed physical-interaction labels and hard normal
interactions in matching settings before further model selection. Reserve a
separate, original-recording/session-disjoint camera evaluation. Improvements
must reduce missed events without increasing false alerts under a fixed policy,
then pass live latency and human-review checks. The current small pilot does not
meet those requirements.
