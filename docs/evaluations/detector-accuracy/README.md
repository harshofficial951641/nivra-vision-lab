# Browser detector accuracy evaluation

Result: the train-selected candidate failed the held-out false-alert gate. The baseline remains the default; all experiments are OFF. The complete local evaluation and required checks passed.

## Scope and data freeze

This evaluates the website publisher's actual `DeviceVision` crowd profile: MediaPipe Full VIDEO, confidence 0.5 and at most four poses, alongside the pinned RTMO-t Body7 CPU/WASM worker (at most 32 admitted observations). The publisher uses `originalConflictEngine.ts` with per-pair cooldown for fast motion. `conflictEngine.ts` is not the active publisher motion engine and was left unchanged. RTMO observation reports remain alert-free.

The task owner explicitly approved the current READY publication on 23 October 2026. Exact copies, READY and checksum sidecars are frozen in `D:\nivra-work\detector\frozen\`:

- Train: `b69c02316ad4ca1872d93116e0692e6ae4fc5409c759047440df42c3d18ee2fc`.
- Dev: `2750e04e88bf63c3639a1ea91275fc8a4ac40bc1a86581aa38c57954da088514`.

The brief's `bf294279...` / `dd215f1a...` hashes identified an earlier publication used by the abandoned model track; they are not the approved snapshots for this rule evaluation. No labels or split assignments were edited. The harness checks recording groups and exact video hashes across train/dev, media hashes, interval bounds and overlap. These groups are heuristic scene/duplicate groups, not verified actor/session identities.

The labelled population is 1,182 train videos in 347 groups and 227 dev videos in 85 groups. Fourteen train and eight dev manifest recordings have no explicit event or normal interval and contribute no scored exposure. To meet the deadline, tuning uses a predeclared deterministic subset: the first 40 train groups sorted by SHA-256 of the group string, 132 videos, 86 labelled events and 329.636 seconds of explicit normal time. Dev uses all 227 labelled videos, 116 events and 819.672 seconds of explicit normal time. The complete train set was not tuned/evaluated.

## Faithful replay and private caches

`run.mjs` launches installed headless Chromium via Playwright, serves only loopback port 5199, blocks non-loopback browser requests and calls no app/session/server API. It plays the original MP4s at 1x. Actual `requestVideoFrameCallback` media timestamps drive the actual production capture methods, original resizing, independent busy/drop admission and CPU workers. Full-frame motion is limited to 960 px and crowd capture to 1280 px, as in `DeviceVision`. Neither frames nor timestamp sequences are manufactured. Two fresh model workers and fresh rule state are created per video; model initialization precedes playback, while cold inference is included.

A transparent Worker wrapper records unrounded output poses, source timestamps, inference/elapsed time, crowd boxes and completion order. Replay uses the pre-resize source video aspect ratio, exactly like production, rather than the rounded bitmap ratio. During pre-dev-scoring review, the latter was corrected from stored source dimensions (maximum difference 0.000812); train-only selection was repeated at 03:57:40 IST and retained the same profile and all train metrics. No dev candidate outcomes had been scored or inspected. The earlier freeze is retained privately for audit. The production client still owns inference and decisions. Caches and per-recording scores stay exclusively in `D:\nivra-work\detector\`; Git receives aggregate metrics only. Cached Node replay calls the same original engine and `DeviceAnalysis`, normalizes the random run-ID prefix, and must reproduce live alert IDs, source timestamps and detail exactly. A recording cannot be scored if either lane failed, the cache diverged, media checksums differ, or capture is incomplete. No video, frame, landmark or per-person result is written into the repository.

Full model SHA-256: `5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1`; RTMO SHA-256: `20aad6e2e42359cac1c5b4a0b2da00e29bfe91a72a782fdcf287d273a04c1b24`. Pinned installed runtimes are MediaPipe Tasks Vision 1.0.1 and ONNX Runtime Web 1.30.0, CPU/WASM only. The local runtime preparation script copies installed assets; no downloads, installs or public hosts are used.

## Metrics and gate

Intervals are half-open milliseconds. Each labelled event can match one unique alert in its interval or the following 500 ms. Grace never extends into explicit normal time or another labelled event. Matching maximizes one-to-one event recall. False alerts are counted only within explicit normal intervals; unknown gaps and tails never become negative exposure. Time-to-alert is the alert's source decision timestamp minus event start, conditional on recalled events; misses are not silently imputed. It is not phone/network response latency.

CIs are 10,000 seeded percentile bootstrap replicates resampling source groups, with paired identical group draws for candidate-minus-baseline differences. Null-denominator replicates are omitted and their count is reported. A metric supported by fewer than two relevant groups gets no CI. Zero observed false alerts yield a degenerate empirical bootstrap CI and do not establish a zero population false-alert rate. Classroom has extremely little independent normal footage and must be read separately.

Eight configurations are declared in `replayEngine.ts`. Train selects the highest event recall among candidates with no increase in train false alerts; ties prefer fewer false alerts and then the fixed configuration order. If none qualifies, the best recall candidate is descriptive only. The selected configuration, rule, shared coordinator, candidate and metric hashes are frozen before dev scoring. Dev refuses changes to those hashes. Other frozen dev configurations are descriptive comparisons, not another tuning round.

Promotion requires strictly higher dev recall, no higher dev false-alert rate, a paired recall-difference CI entirely above zero and a false-alert-difference CI whose upper bound is at most zero, plus passing behavior/runtime checks. Anything else remains off. The current constructor enables none of the new options.

## Experimental changes

- Crowd rules use actual RTMO samples and elapsed-time velocity, with independent temporal state, a flagged 1,000 ms continuity budget and the existing jump/visibility/size controls. The fast lane retains its 600 ms budget. Pairs covered by fresh fast-lane body boxes are excluded; spatial pair cooldown suppresses duplicate cross-lane candidates. No interpolation or cross-lane velocity is used. The live publisher and cached replay share `DualLaneConflictAnalysis`; experiments are available only through the explicit eighth `DeviceVision` argument, e.g. `{experimentalProfile:'crowd-contact-sensitive'}`. The default is null. Enabled crowd experiments emit only uncovered-pair candidates through the independent crowd result stream; cross-lane suppression prevents duplicate incidents and each report keeps its own source-matched poses and timestamp.
- The contact candidate requires at least 600 ms of a one-sided observed upper-body reach, visible torsos, relative torso displacement (0.45 torso scales conservative / 0.30 sensitive) and peak relative speed (0.8 / 0.6 scales per second). Symmetric reaches, static proximity, missing wrists, implausible speed and discontinuous tracks are rejected. This is 2D evidence requiring review; it cannot establish a physical grab, intent or injury and intentionally misses some reciprocal grapples.
- Explicit profiles compare two versus three arm episodes and a 0.8 arm-speed multiplier. The baseline standard sensitivity is unchanged. The tiny learned classifier was skipped under the task deadline.

## Train-only findings

The frozen selected candidate is `crowd-contact-sensitive`: 7/86 events, 8.1% recall (group-bootstrap 95% CI 0.0-18.0%), versus baseline 0/86 (0.0-0.0%). Both emitted zero alerts in 329.636 seconds of explicit normal time. Two-episode crowd rules reached 2/86; conservative crowd contact reached 1/86; changing only the fast-lane episode count or adding conservative fast-lane contact reached 0/86. These are train results, not held-out evidence.

Within labelled train event intervals, [original-rule diagnostics](train-diagnostics.json) found fewer than two usable bodies in 2,371/2,536 motion samples (93.5%). Only 128 samples had a nearby usable pair, and maximum pulse progress was one of three. The fast model never returned four poses in this subset. These are observed model/rule limitations, not evidence that only one person was present.

Every selected-profile train payload also passed the actual server `DeviceResult` / `DeviceMotion` Pydantic schemas: [6,055 reports, zero rejections](train-schema-validation.json), maximum JSON report 8,720 bytes versus the 65,536-byte limit. Payload validation streams privately through the existing Python environment and publishes counts only; no service or API is started.

## Held-out dev results and gate

**No default was changed.** The preselected `crowd-contact-sensitive` configuration increased recall but produced three false alerts in 819.672 seconds (13.661 minutes) of explicit normal time. It failed the required non-increasing false-alert gate. The original standard rules remain the default; `DEFAULT_DETECTOR_EXPERIMENT` remains null. All experimental profiles stay OFF.

Brackets are marginal group-bootstrap 95% CIs. These measure agreement with AI-labelled VID intervals, not deployment accuracy. All eight configurations were fixed before dev scoring; only the train-selected configuration was eligible for promotion under the predeclared protocol.

| Configuration | Event recall | False alerts/hour | Median source time-to-alert | Decision |
|---|---:|---:|---:|---|
| baseline | 0/116: 0.0 [0.0-0.0]% | 0.00 [0.00-0.00] | n/a s | Retained default |
| motion-early | 0/116: 0.0 [0.0-0.0]% | 0.00 [0.00-0.00] | n/a s | OFF: descriptive alternative |
| crowd-standard | 1/116: 0.9 [0.0-3.3]% | 0.00 [0.00-0.00] | 3.27 [n/a] s | OFF: descriptive alternative |
| crowd-early | 2/116: 1.7 [0.0-4.7]% | 0.00 [0.00-0.00] | 3.68 [2.40-4.97] s | OFF: descriptive alternative |
| crowd-low-speed | 3/116: 2.6 [0.0-6.0]% | 0.00 [0.00-0.00] | 2.40 [2.37-4.97] s | OFF: descriptive alternative |
| motion-contact | 0/116: 0.0 [0.0-0.0]% | 0.00 [0.00-0.00] | n/a s | OFF: descriptive alternative |
| crowd-contact-conservative | 5/116: 4.3 [1.0-9.2]% | 0.00 [0.00-0.00] | 3.33 [1.73-7.10] s | OFF: descriptive alternative |
| crowd-contact-sensitive | 8/116: 6.9 [2.5-12.6]% | 13.18 [0.00-28.92] | 3.32 [2.07-6.17] s | OFF: false-alert gate failed |

The preselected candidate's paired recall change was +6.90 percentage points [2.52-12.64]; paired false-alert change was +13.18/hour [0.00-28.92]. Its median source time-to-alert was 3.32 [2.07-6.17] s, conditional on eight recalled events; p90 was 6.34 s. The baseline recalled no events, so its time-to-alert and any paired median difference are undefined.

The frozen conservative contact alternative reached 5/116 (4.3 [1.0-9.2]%) with zero observed false alerts. Its paired recall CI was [1.03-9.18] percentage points; false-alert difference was 0 [0-0]/hour. It was not train-selected and remains OFF. Promoting it after inspecting this held-out comparison would change the predeclared selection policy. Its apparent gain needs a fresh confirmatory evaluation; alternative CIs are not corrected for multiple comparisons. The report does **not** claim that no configuration numerically improved on baseline.

### Per-context dev results

| Context | Events | Explicit normal seconds | Baseline recall | Preselected recall | Preselected false alerts/hour | Conservative recall (OFF) |
|---|---:|---:|---:|---:|---:|---:|
| classroom | 23 | 11.97 | 0.0 [0.0-0.0]% | 8.7 [0.0-18.8]% | 0.00 [0.00-0.00] | 8.7 [0.0-18.8]% |
| corridor | 16 | 152.67 | 0.0 [0.0-0.0]% | 18.8 [0.0-25.0]% | 23.58 [0.00-78.31] | 6.3 [0.0-20.0]% |
| domestic | 26 | 92.30 | 0.0 [0.0-0.0]% | 3.8 [0.0-27.9]% | 0.00 [0.00-0.00] | 3.8 [0.0-27.9]% |
| other | 39 | 522.68 | 0.0 [0.0-0.0]% | 0.0 [0.0-0.0]% | 13.78 [0.00-34.55] | 0.0 [0.0-0.0]% |
| street | 12 | 40.05 | 0.0 [0.0-0.0]% | 16.7 [0.0-50.0]% | 0.00 [0.00-0.00] | 8.3 [0.0-50.0]% |

Baseline and conservative false-alert rates are 0 [0-0]/hour in every context. The preselected false alerts were one in corridor and two in other. Classroom has only 11.97 seconds of explicit normal exposure across 6 groups, so zero observed classroom alerts cannot establish false-alert safety. [dev-aggregate.json](dev-aggregate.json) also contains per-context time-to-alert, group counts and bootstrap valid-replicate counts.

### Coverage and timing

RTMO admitted more than four observations in 1272/5256 crowd samples (24.2%), with a maximum of 14. This is model-observed coverage, not a verified census or proof that the actors were detected. MediaPipe returned four poses in only 3/10597 admitted motion samples; a cap of four does not guarantee four usable bodies.

| Context | Crowd samples over four | Fraction | Maximum observations |
|---|---:|---:|---:|
| classroom | 249/530 | 47.0% | 13 |
| corridor | 335/896 | 37.4% | 11 |
| domestic | 126/747 | 16.9% | 9 |
| other | 469/2698 | 17.4% | 14 |
| street | 93/385 | 24.2% | 12 |

Median source intervals were 270.3 ms for crowd (~3.70 Hz) and 133.3 ms for motion (~7.50 Hz). Median model inference was 233.1 / 90.4 ms respectively. The machine was an Intel i5-10400F (12 logical cores), Node 24.12.0 and headless Chromium 151.0.7922.34. These are desktop measurements, not phone throughput or network alert latency.

[Dev diagnostics](dev-diagnostics.json) show that within labelled event intervals, 3,468/3,941 motion samples (88.0%) had fewer than two usable bodies; none accumulated a directed pulse. This is consistent with substantial coverage/rule limitations on this domain.

### Validation

- 359/359 labelled train-subset/dev recordings reproduced their live baseline alerts exactly from cached poses. All baseline alert streams were empty; nonempty positive paths are separately exercised by synthetic live wiring/replay tests. One fresh opted-in train model replay also matched its cached alerts (zero on that fresh sample). Independent Full VIDEO runs and real-time admission can vary; candidate metrics compare a fixed pose capture per video.
- Source bounds, unique admission timestamps, 4/32 pose caps, footage hashes and decoded label bounds passed. All captures completed, with zero non-loopback requests and zero browser JavaScript exceptions. Vendor warnings included missing source maps and MediaPipe feedback/projection warnings; failed model runs are excluded by a hard capture-completeness check, not silently dropped.
- Actual server-schema validation passed all 6,055 train and 15,853 dev selected-profile reports, zero rejections. Largest report: 8,720 bytes, below 65,536. See [train](train-schema-validation.json) and [dev](dev-schema-validation.json) counts. This is schema validation, not a full service/phone test.
- Final `npm run lint`: PASS. `npm run test`: **708 passed, 77 files**. `npm run build`: PASS. Evaluator/cache tests: **10 passed**. The isolated harness TypeScript check and scoped `git diff --check` passed.
- Synthetic tests cover contact positives, 3 Hz/slower elapsed-time handling, missing observations, static reach, hugs, handshakes, shared dance/pan motion, jitter, hidden wrists, episode profiles, lane separation, duplicate suppression and source-matched reports. Existing per-pair cooldown tests pass. No product layout was changed; no deployment, commit, branch switch or public-host test was performed.

## Reproduce

From `D:\NIVRA`, using installed Node 24 dependencies:

```powershell
node scripts/prepare-browser-runtime.mjs
node scripts/evaluation/detector/run.mjs --manifest D:/nivra-work/detector/frozen/vid-v4-train.json --expected-sha b69c02316ad4ca1872d93116e0692e6ae4fc5409c759047440df42c3d18ee2fc --max-groups 40
node scripts/evaluation/detector/score.mjs --split train --tune --out docs/evaluations/detector-accuracy/train-aggregate.json
node scripts/evaluation/detector/run.mjs --manifest D:/nivra-work/detector/frozen/vid-v4-dev.json --expected-sha 2750e04e88bf63c3639a1ea91275fc8a4ac40bc1a86581aa38c57954da088514
node scripts/evaluation/detector/score.mjs --split dev --out docs/evaluations/detector-accuracy/dev-aggregate.json
node scripts/evaluation/detector/diagnose.mjs --split train --out docs/evaluations/detector-accuracy/train-diagnostics.json
node scripts/evaluation/detector/validate-reports.mjs --split dev --out docs/evaluations/detector-accuracy/dev-schema-validation.json
node --test scripts/evaluation/detector/metrics.test.mjs
npm run lint
npm run test
npm run build
```

## Limitations

Labels are AI-made dense assistant reviews at approximately 4 fps, not independent human ground truth. VID is a short-video source domain, not a representative deployment/classroom sample. Group disjointness does not prove actor/session independence. Classroom is heavily confounded with positive labels and has almost no normal controls; `other` includes unresolved source contexts. Normal exposure is only about 13.7 minutes on dev. Neither bootstrap intervals nor software tests establish deployment accuracy, calibrated probabilities or production readiness.

RTMO counts are admitted model observations, not verified counts of people present or proof of actor coverage. Four is a MediaPipe capacity ceiling; fewer detected poses can also miss actors. Recorded inference rates are desktop CPU/WASM measurements with fresh workers per video and cannot be represented as phone rates. Private frames are not reviewed/relabelled for this experiment. F07/C01 exact clips were not found by filename in the approved local media/repository roots or by their published hashes in the frozen manifests; their historical missed-positive/quiet-negative outcome is not a fresh evaluation here. The [two-video report](../two-video-check/README.md) remains unchanged.
