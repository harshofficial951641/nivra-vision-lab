# Diagnostic comparison — 28 September 2026

**Release gate: NOT PASSED.** The local engine is an experimental candidate, not a verified accuracy upgrade. This corpus does not validate crowded classrooms or even general two-person webcam accuracy.

## Reproducibility

The frozen `corpus.json` SHA-256 is `33d04d15bc4a6911face456fff7488320906505cc344f863042e4cae304bfb34`.
Sources, authors, licenses, recording groups, timestamps, and media hashes are in that manifest and `sources.json`. Labels are approximate manually inspected episode intervals, not contact-frame annotations.

The unchanged `ConflictEngine` rules were run on actual MediaPipe Full CPU poses captured through the browser's video review path, using original source timestamps and Standard sensitivity. The candidate used actual local CUDA YOLOX-S, RTMPose-M, ByteTrack, and SlowFast AVA with the checked-in engineering thresholds. The action model was not fine-tuned. The browser review sampled at 25 FPS; the candidate's offline reader sampled at approximately 12.5–15 FPS. Neither is a live end-to-end timing benchmark.

Local raw reports are `runs/baseline.json`, `runs/candidate.json`, and `runs/comparison.json`; generated media/traces remain gitignored. Reproduce with the commands in the service README. Both reports must match the manifest checksum. Any correctness changes made after inspecting the original holdout mean that split is now diagnostic: obtain a new untouched evaluation set before release.

## Observed counts

| Recording | Labelled events | Browser detected / missed | Candidate detected / missed | Browser / candidate unmatched alerts |
| --- | ---: | ---: | ---: | ---: |
| Shadowboxing, no contact | 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Grappling, genuine overlap | 1 | 0 / 1 | 0 / 1 | 0 / 0 |
| Staged wrestling takedown/kick | 2 | 0 / 2 | 1 / 1 | 0 / 1 |
| Squats, exercise negative | 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Artificially cropped grappling | 1 | 0 / 1 | 1 / 0 | 0 / 0 |

The original recordings total 39.221 seconds with three labelled positive events: the browser detected 0/3 and the candidate 1/3. The candidate added one unmatched alert, approximately 1.53 per minute across these original recordings, versus zero for the browser. This tiny denominator cannot estimate a deployment false-alert rate reliably. Scoring matches one prediction per labelled event within its interval plus a three-second tolerance; unmatched duplicates are counted as false alerts. The two labelled intervals in the short wrestling clip could form one operational incident, so better incident annotations are also required.

The synthetic crop is reported separately and shares its original recording's calibration split. Its one candidate alert appeared 8.4 seconds after the recording began; the grapple was already underway at frame zero. This is not proof of natural partial-body improvement or incident-onset delay. The single matched original-footage event had 1.368 seconds of source-time delay. With so few events, no meaningful live p95 alert delay can be reported.

## Hardware measurements

GTX 1660 Ti, 6 GB VRAM; i5-10400F; 32 GB RAM. Actual CUDA execution was confirmed for detector/pose and action inference.

| Clip | Offline processed frames/second | p95 inference per processed frame |
| --- | ---: | ---: |
| Shadowboxing | 9.93 | 279 ms |
| Grappling | 5.91 | 352 ms |
| Wrestling kick | 7.11 | 330 ms |
| Squats | 8.76 | 258 ms |
| Synthetic crop | 5.53 | 412 ms |

PyTorch peak allocated memory was approximately 444 MiB, excluding ONNX Runtime, decoder, and driver allocations. A separate `nvidia-smi` observation was about 3.1 GiB while service/evaluation workloads were present; it is not an isolated or sustained peak measurement. Do not use these values to claim four-stream capacity. The live simulated-camera browser test exercised actual models and lifecycle but did not establish alert accuracy or p95 alert delay.

## Remaining release gates

- No improvement on the genuine-overlap example and an increased unmatched-alert count: accuracy promotion fails.
- No representative classroom/webcam footage with 30–50 people; no validated back-row coverage.
- No natural partial-body subset sufficient for evaluation; the successful crop is synthetic.
- Missing slaps, shoves, hugs, handshakes, camera motion, classroom activity, and crossing negatives.
- Lost-track and identity-switch metrics unavailable: person-level ground truth is absent.
- No multi-camera throughput or sustained total GPU-memory benchmark; no measured live p95 source-to-alert delay.
- Existing unit/lifecycle tests validate software behavior, not violence-detection accuracy.

Retain the candidate behind its explicit experimental backend choice. Assemble independent labelled training/calibration recordings before targeted fine-tuning and reserve a new unseen evaluation set. Raising thresholds against this inspected holdout or overfitting one grapple would not satisfy the original goal.

## Updated classroom candidate (RTMO + regional AVA + X3D)

The final offline report `runs/crowd-x3d-final.json` uses the same frozen footage,
source times and event matching as above. It pins implementation hashes and model
artifacts. The optional Body7 RTMO-M removes the need for one pose invocation per
person; the community X3D checkpoint adds whole-scene temporal fight evidence.
Its scores are not calibrated probabilities and it cannot attribute an actor.

| Recording | Events | Browser detected | Earlier local detected | Classroom candidate detected | Candidate unmatched |
| --- | ---: | ---: | ---: | ---: | ---: |
| Shadowboxing | 0 | 0 | 0 | 0 | 0 |
| Genuine-overlap grappling | 1 | 0 | 0 | 1 | 0 |
| Wrestling takedown/kick | 2 | 0 | 1 | 1 | 1 |
| Squats | 0 | 0 | 0 | 0 | 0 |
| Synthetic cropped grapple (separate) | 1 | 0 | 1 | 1 | 0 |

Original recordings: **2/3 detected, 1/3 missed, one unmatched alert**, versus
browser 0/3 detected, three missed and zero unmatched; earlier local 1/3 detected,
two missed and one unmatched. The raw missed counts decrease, but the false-alert
gate versus the browser still fails. There are only three original-footage events
in 39.221 seconds; percentages are not reliable deployment estimates. The one
unmatched alert is approximately 1.53/minute on this tiny denominator. Hugs,
handshakes, slaps, shoves, crossings, camera motion and classroom conversations
remain inadequately covered or absent.

The genuine-overlap grapple triggers at source time 4.24 seconds; the clip begins
mid-event. The synthetic partial-body variant triggers at 7.52 seconds. No natural
partial-body subset or live p95 delay guarantee follows from those values. The
kick match remains 1.368 seconds after its labelled interval begins. The final
run produced 11.68, 13.29, 13.64, 10.12 and 15.10 processed frames/second respectively
across the five offline clips, with p95 processing times of 311, 312, 267, 379 and
315 ms. PyTorch peak allocated memory was 458 MiB, excluding ORT and driver memory.

This evaluation is diagnostic: the recordings and original holdout were already
inspected when the additional pretrained candidate was chosen. The overlap
example is in calibration. Do not tune against this holdout or call this a
validated accuracy upgrade. A clean, representative holdout is still required.

### Multi-camera GPU/transport smoke tests

The one-minute runs use repeated copies of the public two-person grappling clip,
not separate crowded classrooms. Localhost transport is not mobile data. The
12 FPS capture target and GPU detection throughput are separate measurements:
all accepted captured frames can enter the bounded temporal RGB history, while
obsolete detection jobs are replaced. Preview is approximately 4 FPS.

Final measurements are recorded in `runs/four-camera-final.json` and
`runs/two-camera-final.json`; see `CAPACITY.md` for the compact generated summary.
Earlier 6 FPS experiments (`four-camera-smoke.json`, `two-camera-smoke.json`)
measured about 1.78–1.90 FPS per camera for four sources and 3.48 FPS per camera
for two. Those runs motivated separating RGB capture history from the detection
queue; they do not describe the final capture path.

The four-source final run lasted 60.54 seconds. Per-camera detection throughput
was 1.67–1.73 FPS, with 101–105 completed jobs from 678–679 captured frames each.
Each source replaced 572–576 pending detection jobs. Sampled whole-GPU memory was
2379–2412 MiB and utilization 57–75%; this includes the desktop and is not an
isolated per-process peak. Local frame acknowledgements had p95 13.5–14.1 ms;
**that is transport acknowledgement, not alert delay**.

These measurements show bounded backlog and fair scheduling, not sufficient
fight coverage for four crowded rooms. More GPU capacity, a faster validated
model or distributed analysis may be needed. Do not silently reduce temporal
coverage and continue displaying a safety guarantee.

**Release status remains experimental / NOT PASSED.** Application tests and
visual QA are separate from the failed accuracy gate and unverified mobile pilot.

## Final source-hash verification run

The final diagnostic runner completed against the current implementation hashes. Counts were unchanged: 2/3 original events detected, one unmatched alert; synthetic crop 1/1. The service was idle/loading alongside this offline run, so timing is not an isolated resource measurement.

| Clip | Offline detection FPS | p95 processing ms |
| --- | ---: | ---: |
| boxing | 12.19 | 299.0 |
| grappling | 13.45 | 309.3 |
| kick | 13.89 | 259.8 |
| squats | 10.57 | 374.1 |
| grappling-cropped | 15.84 | 299.8 |
