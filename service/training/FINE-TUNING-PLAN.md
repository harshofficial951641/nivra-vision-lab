# Offline X3D-M fine-tuning candidate

Implemented on 21 October 2026. No fine-tuning GPU job has been run by this
helper, no candidate has been promoted, and the live community X3D-M is untouched.
Only the parent may schedule GPU execution alongside the public demo.

## Evidence and experiment boundary

Inspected `nivra/x3d_training.py`, `training_data.py`, `x3d_candidate.py`,
`compare_x3d_training.py`, installed PyTorchVideo 0.1.5 X3D/head builders,
`vid-pilot-v1.json`, `vid-source.json`, `RESULTS.md`, and both pilot run/report
locations. The GPU pilot's `report.json` and `diagnostics.json` confirm:

- 36 recordings, 76 train windows: 14 positive and 62 normal, one unresolved
  VID cohort; calibration and holdout empty.
- Frozen official Kinetics X3D-M plus a fresh linear head: perfect training fit,
  101.36-second GPU run. This is training fit, not independent accuracy.
- Candidate review windows: boxing 0/12, grappling 0/17, kick 0/2, squats 0/19,
  cropped grappling 0/17. Community counts on the same windows: 0, 13, 2, 0, 10.
  The crop shares its original recording and is not independent.
- Existing manifest SHA-256:
  `fc742397e912a22f8a7d32f893c2d105b87e4d68a2ad9ffe803a184dece5c0fd`.

No media was re-reviewed for this implementation. Existing labels remain
provisional assistant visual screening of timestamped contact sheets, not human
ground truth or continuous-motion review. Publisher categories do not enter
training. Author-reported consent is not an independently verified full release.

Two causes remain plausible and are not separated by these results:

1. **Model adaptation:** a linear separator on frozen general-action features
   may fail to represent this physical-interaction target. Adapt the projected
   pooling head and optionally the final residual stage to test this hypothesis.
2. **Data/domain coverage:** the small staged VID subset may reward backgrounds,
   appearance or a narrow interaction style. Different wrestling footage,
   framing, brief kick timing, and provisional temporal labels can all matter.
   Fine-tuning may increase memorization and cannot by itself fix these gaps.

There is no held-out accuracy estimate, calibration evidence, deployment
approval, incident recall, or false-alerts-per-camera-hour estimate here.

Parent integration update: schema, training permission, every media hash, cohort
rules and generated windows were validated without decoding or fitting for
`data/vid/integration/round2-positive-batches-staged.json`. SHA-256:
`f3cc6c3842492758d96ee9dd3a1edb5d81940f0ca272b193d684eb84882b8f3b`.
That snapshot has 67 recordings (39 positive, 28 normal), 127 training windows
(65 positive, 62 normal), one unresolved VID cohort, and zero calibration/holdout
windows. This is an integration snapshot, not a frozen final training selection;
additional normal reviews were pending. No new media review or improvement claim
was made by this helper. Capture the corresponding new review files when training.

## Implemented contract

`nivra/x3d_finetune.py` and `finetune_x3d.py` are separate from the frozen trainer
and the live loader. They do not download, provision, publish or alter checkpoints.

- Require the local official X3D-M checkpoint SHA-256
  `eb9583d5f5a988a5c5f06f75760b070a5c9715794bd3b0536b78bd30595dcf67`
  before safe `torch.load(weights_only=True)`. Strictly load its complete
  400-class state before retaining a fresh two-class projection. Architecture is
  pinned to the installed `pytorchvideo==0.1.5`; no hub code is downloaded.
- Default trainable scope: X3D `blocks[-2]` (last residual stage) and
  `blocks[-1]` (projected pooling and binary classifier). `--head-only` adapts
  projected pooling and classifier while freezing every residual stage. This
  head mode still differs from the prior frozen-feature linear probe.
- Freeze all BatchNorm affine parameters and running statistics on every entry
  into training mode. Earlier blocks remain in eval mode; trainable blocks
  retain their normal training behavior, including the official head dropout.
- Remove the head Softmax. Train binary **logits** with CrossEntropyLoss; apply
  Softmax exactly once for diagnostic class-1 scores. Scores are uncalibrated.
- Defaults: seed 17, fixed 5 epochs, AdamW, head LR `1e-4`, final-stage LR
  `1e-5`, weight decay `.01`, FP32, batch 1, accumulation 8, gradient norm cap 1.
  No early stopping, diagnostic-based selection, or automatic threshold changes.
- Class weights are `N_train / (2 * class_count_train)` only. Each accumulation
  group sums weighted losses and divides by its actual sum of target weights.
  The incomplete tail is stepped with its own correct denominator. This avoids
  class-weight cancellation from independently averaging batch-one CE losses.
- Reuse `load_manifest(..., verify_files=True)`, `generate_windows`,
  `read_window`, and `preprocess_frames`: local media hashes, explicit training
  permission, reviewed temporal labels, 16 RGB frames, 224 square, and existing
  four-second sampling/normalization. Normal requires explicit full coverage;
  positive requires at least half a full window. Short clips contribute none.
- All recognized VID source IDs/DOI aliases must remain `train` in
  `vid-v2-unresolved-session-cohort`. Filename-derived independent groups or
  VID calibration/holdout are rejected. A generic future manifest may contain
  independently sourced evaluation data, but fitting accepts only train windows.
  Holdout decoding starts after fixed fitting and calibration selection finish.
  Empty calibration preserves `.5` with strict `score > threshold` and an
  explicit uncalibrated status; empty holdout metrics remain unavailable.
- OpenCV uses one thread; Torch uses two CPU threads. Windows decode sequentially,
  with no worker pool or GPU feature cache. Seeds are fixed and cuDNN deterministic
  mode is enabled, with benchmarking off. CPU deterministic algorithms are strict.
  CUDA uses explicit deterministic warnings because Torch 2.5.1 documents no
  strictly deterministic CUDA AvgPool3d backward, required by the official head.
  Bitwise CUDA reproducibility is not promised. `CUBLAS_WORKSPACE_CONFIG=:4096:8`
  is set before context initialization unless an allowed `:16:8`/`:4096:8` value
  already exists; invalid values or a context initialized before setup fail.
  This policy is reported rather than silently replacing pooling or blocking
  the intended CUDA fine-tuning path.
- CUDA requires explicit `--device cuda`, an available device, a validated
  per-process allocator fraction (default `.4`), and DemoYieldGuard cooperation.
  Synchronize before yielding at microbatch boundaries and before optimizer
  steps. Unavailable/invalid health, prolonged busy status, OOM, and invalid
  gradients fail closed. There is no automatic CPU fallback, cap increase,
  input shrinking, retry, or service manipulation. Yielding is best effort:
  health can change after a check, and a microbatch cannot be preempted. Model,
  gradients and optimizer allocations remain resident while waiting.

## Artifacts and diagnostics

Each invocation requires a **new** output directory; an existing run is never
overwritten. A successful run writes:

- `candidate-state.pt`: full CPU tensor state plus config, architecture, pinned
  base hash, manifest hash, snapshot hashes, preprocessing, class order and
  threshold. It needs installed trusted architecture code but no base checkpoint
  file at diagnostic load time. No serialized module or unrestricted pickle.
- `report.json`: candidate hash, source/input hashes, selected window identities
  and scores, trainable parameter names/count, fixed training settings/losses,
  split metrics, package versions, elapsed time, limitations and optional measured
  process CUDA allocator peaks. Manifest-declared media hashes are preserved.
- `manifest.json`, `source/` implementation snapshots, and `provenance/` evidence
  snapshots. CLI defaults capture VID source, data rights and all three existing
  reviews. Additional evidence is appended with repeated `--provenance-file`;
  include the new review files supporting expanded manifests. Programmatic callers
  supply their complete evidence list through `provenance_files`.

An interrupted/failed run can leave a partial directory without a valid report.
Use a new directory on the next parent-authorized attempt. Do not mistake partial
files for a successful candidate. Integrity hashes detect modification; they are
not cryptographic signatures authenticating a maliciously replaced whole run.

`FineTuneCandidate(run_dir).predict(frames)` accepts BGR uint8 frames and returns
one scalar class-1 score on **CPU**. `load_candidate` verifies candidate/report
metadata, snapshot hashes, path containment, tensor keys/shapes/dtypes/finiteness,
and loads the complete state strictly with `weights_only=True`.

The new `diagnose` CLI reuses `compare_x3d_training.windows` and `event_overlaps`
on the existing corpus with its causal 4-second/100-ms source sampling and
400-ms prediction spacing. It verifies media hashes/crops, never fits a threshold,
and saves per-window scores and overlap context. Compare review counts and exact
timestamps with the frozen-head diagnostics above; no change to the old comparison
script is needed. Historical corpus split names remain diagnostic context. There
is no automated promotion and no automatic weakening of failed diagnostics.

## Parent-run commands

Run from `service` after the parent reserves GPU time. Commands below are
instructions only; this helper did not execute training on the real dataset.

```powershell
./.venv/Scripts/python.exe finetune_x3d.py train --manifest training/vid-pilot-v1.json --data-root training/data/vid --base-checkpoint models/x3d_m_kinetics.pyth --output-dir training/runs/vid-finetune-stage-v1 --device cuda --epochs 5 --accumulation-steps 8 --backbone-learning-rate 0.00001 --head-learning-rate 0.0001 --cuda-memory-fraction 0.4
```

A parent may first choose a bounded smoke run with `--max-train-windows 4` and a
different new output directory. A subsequent head-only ablation uses `--head-only`
and another new directory; reserve settings before observing diagnostic scores.
Neither ablation is an independent evaluation or a promotion gate.

```powershell
./.venv/Scripts/python.exe finetune_x3d.py diagnose --run-dir training/runs/vid-finetune-stage-v1 --corpus evaluation/corpus.json --output training/runs/vid-finetune-stage-v1/diagnostics.json
```

CPU diagnostics load CPU tensors and explicitly keep the model on CPU even when
CUDA is visible. They do not fetch demo health or instantiate the community model.

**Memory estimate, not a measurement:** budget roughly 1-3 GiB process VRAM for
batch-one FP32 last-stage adaptation at this resolution. Activation/workspace
choices make this uncertain; do not use the earlier frozen probe's 127.76 MiB
peak as a fine-tuning estimate. On the recorded 6 GiB GPU the `.4` allocator cap
is about 2457 MiB and may cause OOM. It caps this process's Torch allocator, not
total device use or driver allocations. Parent must measure real allocated and
reserved peaks plus demo latency/health before scheduling a longer run; the code
does not increase the cap automatically. No fine-tuning peak has been measured.

## Verification and next data requirement

CPU synthetic tests in `tests/test_x3d_finetune.py` verify real intended-stage
updates, unchanged prefix and all BN state, deterministic repeatability, weighted
accumulation equivalence to batched reference updates including the tail,
train-only class weights despite skewed evaluation, no non-train fitting,
threshold selection before holdout decode, honest empty evaluation, VID cohort
rejections, source permission/review/hash failures, pinned base rejection before
loading, new-directory protection, safe full-state round trips, corruption
rejection, CUDA-unavailable/cap validation without CUDA work, demo cooperation,
and fixed-policy CPU diagnostic output. GPU convergence, memory and speed remain
unverified. No new visual contact sheets or training labels were produced.

The real official checkpoint was hash-verified and loaded on CPU without any
forward pass or training. It has six blocks, a 2048-to-2 logits projection, and
2,304,050 trainable parameters across 42 tensors in the default final-stage/head
scope; zero BatchNorm modules are in training mode. Both CLI help entry points
passed. Test coverage also checks CUDA workspace initialization policy and explicit
warnings for unsupported deterministic pooling, using mocks without CUDA work.
Final verification: **252 passed, 3 skipped**, including **35 new fine-tuning
tests**. The skips include the opt-in real CUDA regression and Windows symlink
restrictions; the suite emitted one existing Starlette/AnyIO deprecation warning.
Assigned files passed a trailing-whitespace check. No live service or real dataset
training job was started, and no GPU forward/backward pass was executed.

## Completed parent run

The statements above describe the helper's implementation handoff. The parent
subsequently integrated all six chats, froze `vid-round2-v1.json` (96 recordings,
156 training windows), passed a real four-window CUDA smoke run and completed
five CUDA epochs. Measured peak allocation was 218.160 MiB, reservation 298 MiB,
and elapsed time 219.377 seconds. The earlier 1-3 GiB figure was an estimate,
not the actual result.

The parent added `--input-cache-mib`, default zero and bounded at 4096 MiB.
It caches immutable decoded uint8 BGR frames in CPU RAM, keyed by source path,
content hash and temporal bounds. It never caches model features or gradients.
The actual 1536 MiB budget held 890.326 MiB across 156 windows, with 780 reuse
hits and no evictions. Cache transparency, source/time separation, memory bounds,
oversized inputs and immutable data have regression coverage.

The final-stage adaptation failed the existing diagnostic comparison and remains
offline. Full results, artifact hashes and the decision are in
[ROUND2-RESULTS.md](ROUND2-RESULTS.md). No independent accuracy is established.

Before any real accuracy claim, expand continuously inspected physical-contact
spans and hard normal interactions in matching camera domains; exclude arguments,
props/weapons and unclear contact conservatively. Reserve genuinely independent
original recordings/sessions with confirmed lineage. Keep VID together, preserve
uncertain margins, and retain all diagnostic failures. Fine-tuning alone cannot
establish those missing data properties or a safe release gate.
