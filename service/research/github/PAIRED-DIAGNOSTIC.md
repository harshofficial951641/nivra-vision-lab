# Bounded paired classifier runner

Implemented 21 October 2026 in `service/benchmark_cctv_candidates.py`; no live
integration or real candidate inference was performed by this helper. Parent
owns actual CPU/GPU runs. Shared model adapters, services, environments, weights
and existing benchmark scripts were preserved.

Read [PROTOCOL.md](PROTOCOL.md) and
[OPERATING-CONDITIONS.md](OPERATING-CONDITIONS.md) before interpreting results.
Physical-fight review only; no identity/audio/policing. Development clips do not
establish accuracy, 50-100-person coverage, true near-IR or low-light-color quality.

## Implemented scope

- One `x3d`, `mc3` or `videomae` per invocation and explicit `cpu`/`cuda`.
  Controls reconstruct the known local architecture independently with downloads
  disabled, strict safe state loading, FP32 and explicit device. They do not use
  the old auto-CUDA constructors. X3D retains its backbone Softmax and selects
  class1; MC3 applies Softmax once to logits and selects class0.
- VideoMAE uses the separately implemented `VideoMAECandidate(snapshot, device=...)`.
  All four cliffer1 snapshot hashes are checked before construction. Adapter
  metadata, source/preprocessing, class order and implementation hashes are saved.
  The adapter rechecks its pinned assets/config and uses its saved processor.
- Every corpus media hash and selected model asset is validated **before** runtime,
  model construction or decoding. Invalid review context/crops/events/group leakage
  fail validation. Corpus and implementation hashes are rechecked at completion.
- The new reader does not import or reuse the old 224-square `FightWindow`.
  Decode PTS must be finite, nonnegative and strictly increasing. Nominal FPS is
  recorded but never used to manufacture a clock. Source gap >1200 ms and source
  dimension changes clear history. Crop coordinates are applied to native pixels
  before any model-specific transform and reported as normalized/pixel bounds.
- Policy: four-second source history, >=100 ms between retained observations,
  >=400 ms between predictions, >=8 observations and >=3800 ms observed span.
  Sixteen floor-linspace indices are selected from each valid history; those exact
  native/cropped frames are supplied to every candidate. Adapter re-selection of
  sixteen from sixteen is identity. Repeated indices when only 8-15 observations
  exist are explicitly counted; no short clip or missing-time span is padded.
- Default geometry cap is **2,073,600 source pixels** and maximum side 3840, accepting
  1920x1080 landscape, 720x1280 portrait and 1080x1920 portrait. Buffer cap is
  100,000,000 retained pixels (~286 MiB BGR uint8), at most 48 samples. A full 41-frame
  1080p history fits. Bounds are on retained history, not total process RSS; decoder
  current frames, model tensors and preprocessing have additional memory cost.
- Default hard limits: 1000 total windows, 100,000 decoded frames/clip, 100 clips.
  Exceeding a window/geometry/pixel/frame budget fails without a partial report;
  it never silently resizes or removes eligible windows to pass a cap. Increasing
  configurable limits remains constrained by hard upper bounds in `Limits`.
- Torch threads 2, OpenCV threads 1. CUDA cap defaults to **.35** and is set before
  constructing/loading a model. CUDA cannot disable demo cooperation or fall back
  silently to CPU. DemoYieldGuard is called before load and every prediction,
  including three warmups on the first eligible window. All warmups are excluded
  from scored timing. CUDA synchronizes before health checks and around timing.
  Guard failure/OOM aborts; no automatic cap increase, retry or service manipulation.
  Guard is best effort, not a lock; resident model memory remains while yielding.

## Output and pairing

Output must be a new path. No file/directory is written until every requested
clip finishes; then exclusive creation prevents overwrite. A successful valid JSON
has `status=complete-diagnostic-only` and `complete=true`. Failed decoding/loading,
invalid model output or exceeded limits produce no successful report. All-short
corpora fail rather than producing a zero-window success. An individual short
clip remains listed with zero windows and explicit exclusions.

Each row records source group, media hash, actual source/cropped dimensions, crop
pixel coordinates, window start/end, observed frame PTS, selected frame PTS/indices,
class probabilities, fight index/score kind, fixed strict `> .5` review decision,
event overlap context and adapter-call timing. Decoder counters record resets,
warmup/context exclusions and unobserved declared tails; unknown tail coverage is
not converted into a normal label. Derivatives remain flagged at clip level.

Compare **all three** `corpusSha256`, `policySha256` and `pairedWindowSha256`
across completed candidate reports. The last hash covers clip/source identities,
geometry, crop and exact observed/selected PTS, excluding scores and model identity.
Never compare a newly decoded candidate against old scores from different buffers.

No window count is fabricated or forced. Parent's expected 69-window diagnostic
must be verified from the actual completed reports. If actual decoding yields a
different count, retain the observed count/PTS and investigate the mismatch;
do not add, drop or duplicate rows to reach 69. No real corpus decoding/model run
was executed by this helper to assert the final count.

Primary results are raw window decisions and overlap context. The old greedy
event-credit routine is deliberately not run: an alert caused by a later kick
can be credited to an earlier takedown under its three-second tolerance. No
accuracy/event-recall/camera-hour claim follows from this runner's few-person clips.

Timing includes adapter RGB/resize/crop/normalization, host/device transfer, forward
and returning scores. Decode/window assembly and demo waiting are excluded from
per-call timing; clip wall/decode assembly and whole-run time are separate. p50,
p95 and p99 include sample counts and exclude the three warmups. They are classifier
timings, not live camera throughput, queue latency or end-to-end alert delay.
Memory phase snapshots include UTC sampling timestamps and current/peak allocated
and reserved Torch bytes on CUDA, after load/warmup/completion. These timestamps
mark observations, not the unknown exact instant of each allocator peak. Driver,
decoder, ONNX, other processes and the live service are excluded. CPU RSS and
total-device memory are not measured by this scoped runner.

## Parent-only commands

Run from the repository root. Every output below must be absent. Models and the
cliffer1 snapshot must already be staged; these commands never download assets.
Do not execute simultaneously. CPU commands retain demo yielding by default;
`--no-yield-to-demo` is supported for CPU only if parent deliberately chooses it.

```powershell
service/.venv/Scripts/python.exe service/benchmark_cctv_candidates.py --candidate x3d --device cpu --corpus service/evaluation/corpus.json --output service/research/runs/paired-x3d-cpu-v1.json --yield-to-demo
service/.venv/Scripts/python.exe service/benchmark_cctv_candidates.py --candidate mc3 --device cpu --corpus service/evaluation/corpus.json --output service/research/runs/paired-mc3-cpu-v1.json --yield-to-demo
service/research/venvs/videomae457/Scripts/python.exe service/benchmark_cctv_candidates.py --candidate videomae --device cpu --snapshot service/research/cache/cliffer1-videomae/613844b1d2d27f68944619bf91885a9befb101ac --corpus service/evaluation/corpus.json --output service/research/runs/paired-videomae-cpu-v1.json --yield-to-demo
```

When parent reserves one GPU slot, sequentially:

```powershell
service/.venv/Scripts/python.exe service/benchmark_cctv_candidates.py --candidate x3d --device cuda --cuda-memory-fraction 0.35 --corpus service/evaluation/corpus.json --output service/research/runs/paired-x3d-cuda-v1.json --yield-to-demo
service/.venv/Scripts/python.exe service/benchmark_cctv_candidates.py --candidate mc3 --device cuda --cuda-memory-fraction 0.35 --corpus service/evaluation/corpus.json --output service/research/runs/paired-mc3-cuda-v1.json --yield-to-demo
service/research/venvs/videomae457/Scripts/python.exe service/benchmark_cctv_candidates.py --candidate videomae --device cuda --cuda-memory-fraction 0.35 --snapshot service/research/cache/cliffer1-videomae/613844b1d2d27f68944619bf91885a9befb101ac --corpus service/evaluation/corpus.json --output service/research/runs/paired-videomae-cuda-v1.json --yield-to-demo
```

The .35 fraction is an allocator cap, not reserved hardware capacity or proof of
VideoMAE fit/coexistence. Parent must retain failures and measured peaks; no speed,
memory or detection improvement is claimed by this implementation.

## Verification

Unit/integration seams use small synthetic arrays, fake decoders, stub models and
mock CUDA policy calls. No real model constructor or real inference is run. Tests
cover strict PTS, gap/dimension resets, native crop coordinates, portrait/landscape
geometry using one-byte broadcast views, pixel/frame/window bounds, all-input
validation before construction, exact paired identities, warmups, yielding, late
failure/no partial output, strict >.5, safe weights-only flags, explicit CPU with
CUDA probes forbidden, allocator-cap ordering and correct activation/class index.

A real `VideoMAECandidate.predict` method is exercised with a stub saved processor
and two-logit fake forward: it preserves source geometry until the processor,
swaps BGR->RGB and produces the expected interface. This is not a checkpoint run.
Relevant shared adapter/benchmark suites are also run with their stubs. Actual
paired results and all crowd/night operating conditions remain parent-run or
unverified; no live promotion is authorized by a successful software test.

Verification result: **124 passed, 1 skipped**, including **43 new runner tests**.
The skip is the shared VideoMAE Windows symlink-permission test. CLI `--help`
passed without importing a real model. From `service`, the executed test command:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_benchmark_cctv_candidates.py tests/test_videomae_candidate.py tests/test_benchmark_fight_models.py tests/test_compare_x3d_training.py -q
```
