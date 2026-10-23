# Video classifier: held-out alert-policy evaluation

Result: **PASS** on the owner’s test point-estimate gate. **Default ON**. Alerts require human review. This does not establish violence accuracy or Mac M5 performance.

Test recall is **11/53 (20.75%; group-bootstrap 95% CI 5.66–35.05%)**, with **0 false alerts in 0.223794 actionable normal camera-hours**. The false-alert bootstrap interval is degenerate at `[0,0]`; the additional exact Poisson 97.5% upper rate is **16.48/h**. The point-estimate gate passes, but this exposure does not establish a confidence-bound rate of <=2/h.

## Frozen data and leakage checks

Split SHA-256: `50e8ba7fa09e6c26e28651096fc82d3439c6751548a8c67630c0616d0fbbf568`. Model SHA-256: `78e372a5ec6ad97925c3cdac2e0de0f5e9315ebd38fb151fa429d69304aaef87`.

A0 trained only on frozen round-1 train `bf2942793bbdfc51281c8e9c47afe1a4c566c1b0beba0fb34b5cccd8b6d4fec7`; round-1 dev is `dd215f1a8569ab7e78ae27cf94b3d6165ec21d1aef461405c1ddf4e58cc9c00e`. Those exact files were recovered from the probe inputs, not replaced with the later browser-evaluation publication.

Pool: explicit labels from round-1 dev plus unanimously normal, densely reviewed `nv_b_04/05/07` imports. Connected components join original/current T1 groups, recording IDs and exact media SHA-256 values; every component touching round-1 train is excluded. Duplicate hashes are evaluated once. Every retained file was hashed before freezing and rechecked at replay. No train recording is evaluated.

Exclusions: `{"post-round1-normal:duplicate_sha": 14, "post-round1-normal:train_component": 145, "round1-dev:no_explicit_labels": 8}`. All 846 retained media hashes verified; zero retained train hash/group/ID overlap. Labels-only seed 20261023 search balances recordings, events and normal exposure within contexts, never model scores. Whole groups and hashes are disjoint between calibration and test. Frozen before inference; selection sealed before test replay.

| Split | Recordings | Groups | Events | Explicit normal h | Actionable normal h |
|---|---:|---:|---:|---:|---:|
| calibration | 425 | 219 | 62 | 0.687292 | 0.276707 |
| test | 421 | 220 | 53 | 0.627775 | 0.223794 |

Actionable exposure begins 4 s after the first actual decoded PTS and ends at the last actual PTS, intersected with explicit normal intervals. The model never emits partial-window predictions or an EOF flush. All events, including early/short events that cannot be detected, remain in the recall denominator. Unknown gaps and unlabelled tails never become normal. Total explicit normal exposure is also reported above; split-summary’s predecode actionable estimate uses container bounds.

## Exact causal replay and policy

Sequential OpenCV decoding uses actual `CAP_PROP_POS_MSEC`, strictly increasing and finite; no nominal-FPS fallback. Scoring is anchored to the first actual PTS at +4,+5,+6… s and admitted only after an actual decoded frame reaches the score time, matching C1’s frame-driven scheduler. Container duration never supplies a final score. Use `[t−4,t)` only. Training first samples 16 equally spaced targets, endpoint excluded, then indexes `np.linspace(0,15,8).astype(int)`: `[0,2,4,6,8,10,12,15]`. The eight target offsets are `[0,.5,1,1.5,2,2.5,3,3.75]` s. Choose nearest actual in-window PTS, earlier ties. Resize full-frame BGR to 224 square, convert RGB, resize to 172 square with OpenCV linear interpolation; float32 `/255`, no mean/std. Input is `[B,8,3,172,172]`, clip reset, softmax class 1. The live 250 ms sample-coverage guard is checked, and source gaps requiring epoch reset fail closed.

Before any test metrics were computed or inspected, live-scheduler review found that an initial container-duration replay could admit one final score beyond the last decoded PTS. The superseded calibration seal and replay receipts are retained privately in `audit-container-duration-v1/`; raw scores remain in the private cache. Admission was corrected using timestamps only on both splits; unchanged windows reuse probabilities only after exact selected-PTS equality checks. Calibration selection was repeated on corrected calibration data and sealed again before corrected test replay. The single test evaluation uses only the corrected protocol. No test outcomes informed this correction or policy selection.

Frozen training-input cache parity: max pixel difference 0 across 8 frames. CPU/CUDA probability parity on four calibration windows: max absolute difference 2.38418579e-07; tolerance 1e-4. Batch-1/batch-4 independence and repeated-forward reset checks passed.

Export portability defect: `.cuda()` alone fails because this trace pins 27 tensor-factory device constants to CPU. Replay loads a fresh graph per device and remaps those constants to CUDA in RAM. The original model file, weights, operations and sampling are unchanged; the output parity checks above cover this remap. C1 must account for this on non-CPU TorchScript devices; MPS is unverified.

Chosen qualifying threshold **0.999**, strong threshold **1.0** (inclusive); **2** consecutive qualifying windows at <=1 s gap, or one strong window. Per-camera cooldown **8 s**. One incident per continuous qualifying episode, merging gaps <=2 s; a longer gap rearms, but does not override cooldown. Any nonqualifying/invalid window breaks confirmation. State resets per camera/source generation. No offline people count is available, so the two-person requirement is dropped.

Calibration searched 219 declared grid policies. Selection rule: **point_estimate_fallback_insufficient_exposure**. Maximize recall, then minimize false count and median delay, then prefer stricter thresholds and more confirmations. Conservative selection requires both group-bootstrap upper95 and exact Poisson upper97.5 <=2/h. Even zero calibration false alerts has Poisson upper 13.33/h; exposure cannot support that rule, so the explicitly permitted point-estimate fallback was used. Test did not influence selection.

Legacy `Decisions.scene_update` hard-codes .4/.7 and at least two observed people, and can alert again after cooldown. C1’s runtime scene path must apply `policy.json` and the simulator’s episode merging; this evaluation does not itself modify the backend. Interactions with other detector alerts were not simulated.

## Results

Values in brackets are 95% whole-group percentile bootstrap intervals, 5,000 draws, seed 20261023. Whole groups are sampled with replacement; draws without the relevant denominator are omitted and counted in JSON. Fewer than two eligible groups yields no interval. Rates use actionable explicit normal time.

| Split | Event hits / total | Recall % [CI] | False alerts | False alerts/h [CI] | Median delay s [CI] |
|---|---:|---:|---:|---:|---:|
| calibration | 4/62 | 6.45 [0.00–17.50] | 0 | 0.00 [0.00–0.00] | 5.00 [5.00–6.00] |
| test | 11/53 | 20.75 [5.66–35.05] | 0 | 0.00 [0.00–0.00] | 5.00 [4.73–5.00] |

Test p90 time-to-alert: 6.00 [4.95–8.00] s, conditional on detected events. Delays use annotated onset and source scoring time, excluding compute/transport; events starting at zero may already be in progress. Unknown-time alerts: 0; all alerts: 11. Zero-count bootstrap intervals are degenerate and are not evidence of a zero underlying rate. Test exact Poisson upper97.5: **16.48 false alerts/h** (additional exposure diagnostic, assuming independent Poisson counts; not a replacement for the group CI).

| Test context | Hits/events | Recall % [CI] | Normal h | False alerts | False alerts/h [CI] | Median delay s [CI] |
|---|---:|---:|---:|---:|---:|---:|
| classroom | 6/12 | 50.00 [0.00–55.56] | 0.005762 | 0 | 0.00 [0.00–0.00] | 5.00 [5.00–5.00] |
| corridor | 2/8 | 25.00 [unavailable] | 0.051403 | 0 | 0.00 [0.00–0.00] | 3.62 [unavailable] |
| domestic | 0/12 | 0.00 [0.00–0.00] | 0.127416 | 0 | 0.00 [0.00–0.00] | n/a [unavailable] |
| other | 2/15 | 13.33 [0.00–22.22] | 0.035398 | 0 | 0.00 [0.00–0.00] | 5.50 [unavailable] |
| sports | 0/0 | n/a [unavailable] | 0.001602 | 0 | 0.00 [0.00–0.00] | n/a [unavailable] |
| street | 1/6 | 16.67 [0.00–75.00] | 0.002212 | 0 | 0.00 [0.00–0.00] | 5.00 [unavailable] |

Classroom remains sparse/confounded: limited normal exposure, few independent positive groups, assistant labels and related settings. Per-context rates, especially street/sports/classroom, have too little exposure to establish a <=2/h operating guarantee. Missing positive classes are reported as n/a, not zero recall.

Gate is passed by the owner’s **test point estimate <=2/h**. `policy.json` sets `defaultEnabled` to `true`. Recommend default ON under the owner’s rule, with human review; confidence-bound performance remains unproven.

## Latency

NVIDIA GeForce GTX 1660 Ti; Windows CPU `Intel64 Family 6 Model 165 Stepping 3, GenuineIntel` with two PyTorch threads. FP32 preallocated tensor to logits; synchronized CUDA wall time. Excludes decode, preprocessing, transfers, camera transport and policy. Warmups: CPU 5 / CUDA 10; repeats: CPU 30 / CUDA 60. These are measured here, not inherited benchmark numbers.

| Device | Batch | p50 batch ms | p95 batch ms | p50 ms/window |
|---|---:|---:|---:|---:|
| cpu | 1 | 53.07 | 62.42 | 53.07 |
| cpu | 4 | 202.92 | 263.24 | 50.73 |
| cuda | 1 | 18.83 | 22.54 | 18.83 |
| cuda | 4 | 17.82 | 24.37 | 4.45 |

**Mac M5, CoreML/ANE execution, live device behavior and C1 integration are unverified.** MIT port / Apache-2.0 pretrained weights provenance follows the pinned export report. Scores are model outputs, not calibrated probabilities of violence.

## Reproduction and files

From repository root using the provided torch 2.5.1+cu124 Python environment:

```powershell
python -B -m unittest scripts.evaluation.classifier.test_policy_metrics scripts.evaluation.classifier.test_replay -v
python -B -m scripts.evaluation.classifier.freeze
python -B -m scripts.evaluation.classifier.replay --split calibration --benchmark
python -B -m scripts.evaluation.classifier.evaluate calibrate
python -B -m scripts.evaluation.classifier.replay --split test
python -B -m scripts.evaluation.classifier.evaluate test
```

Freeze, selection and test commands deliberately refuse to overwrite their seals. Do not delete them to obtain a different test result. GPU replay/benchmark uses the existing `training_v4.gpu_lock` FIFO queue and never preempts another job.

Repository outputs: this README, `policy.json`, `results.json`, `split-summary.json`, `calibration.json`, `calibration-candidates.json`, `latency.json`, plus scripts/tests under `scripts/evaluation/classifier/`. All repository JSON is aggregate-only. Private split/intervals, per-window probabilities and timestamps live in `D:\nivra-work\classifier\` (scores in `cache/`). No footage, decoded frame, person observation or landmark is written to the repository or persisted by this replay. No services, ports, downloads, commits, pushes or branch changes.

## Limitations

- Assistant dense labels, not independent human-adjudicated ground truth.
- Heuristic scene/duplicate groups do not establish actor/session independence.
- Round-1 dev was previously inspected in fixed-epoch model comparisons; this is a new policy holdout, not a pristine external model test.
- Short independent clips reset policy state; long-running camera behavior and cross-clip incidents are unverified.
- Zero-count group-bootstrap CI is degenerate; the exact Poisson upper bound exposes inadequate normal exposure.
- No browser people-count rule: those observations are unavailable offline.
- Mac M5, live-device latency and backend integration are unverified.

Validation: policy/metrics unit tests, actual-PTS coverage assertions, all media hashes, exact training-cache pixel parity, CPU/CUDA probability parity, batch independence, frozen split disjointness and one-shot policy/test seals. Long uninterrupted negative camera footage is the next evidence needed to narrow the false-alert bound.

Final checks: **22 unit tests passed**; source syntax/whitespace and aggregate-only JSON checks passed. C1's loader accepted this exact `policy.json`; 10,000 synthetic episode updates matched the offline simulator. C1's frame-ring sampling and preprocessing matched the reference exactly, including a scoring grid trailing the latest decoded PTS by 777.78 ms. The tested backend source hash and aggregate validation evidence are recorded in `validation.json`. These checks do not verify the full backend flow or Mac execution.
