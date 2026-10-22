# Fixed community X3D-M head adaptation

21 October 2026. Implementation ready for parent-controlled offline execution.
This helper has not loaded, trained or inferred with a real model/checkpoint,
run CUDA work, installed/downloaded anything, or changed the live service. Tests
use tiny CPU models, stub forwards and synthetic arrays only.

## Evidence and fixed hypothesis

[PAIRED-RESULTS.md](PAIRED-RESULTS.md) records 67 identical paired development
windows for the three parent-run GPU candidates. Shadowboxing flags were X3D
0/12, MC3 12/12 and VideoMAE 9/12. VideoMAE median adapter time was 625.6 ms versus
86.7 ms for X3D. Retain the live community checkpoint; these observations do not
establish representative accuracy, 50-100-person performance or night/IR coverage.
The previous generic-Kinetics final-stage experiment fitted its training windows
but failed transfer diagnostics and was not promoted.

Predeclared hypothesis: conservatively adapt the existing fight-tuned binary
Linear head while preserving the useful baseline representation and complete
forward semantics. This is an experiment, not a prediction of improvement.

| Setting | Fixed value |
| --- | --- |
| Baseline | Existing community X3D-M, full byte SHA-256 `e833f69d110f167cad4a6c38d385564bdb2f6de63d246e45cb03ff9aa17f0349` |
| Manifest | `training/vid-round2-v1.json`, SHA-256 `1a0f6fc44704b73f32c5e0ab82b607fff2a702a848186b4403ddf357a0026a84` |
| Data | 96 recordings; 156 windows, 65 positive/91 normal; one unresolved VID training cohort |
| Trainable tensors | Existing `blocks.5.proj.1.weight` and `.bias` only |
| Model state/mode | Whole model `eval()`; all other parameters frozen; all BN and both dropout locations remain eval |
| Architecture | Pinned PyTorchVideo 0.1.5 X3D-M, original projected pooling, head activation and output pooling retained |
| Loss | Weighted NLL of `log(output_probabilities.clamp_min(1e-7))` |
| Optimizer | AdamW, LR 1e-5, weight_decay .01, Torch default betas (.9,.999) and eps 1e-8 |
| Schedule | Exactly 3 epochs, seed 17, FP32, batch 1, accumulation 8, no gradient clipping |
| Weights | Training only: `N/(2*n_class)`; counts `[91,65]`, approximately `[.8571429,1.2]` |
| Selection | Export last epoch 3; no checkpoint selection from diagnostic scores |
| Decisions | Raw class 1 retained probability strictly >.5; uncalibrated; no tuning |
| Resource policy | Explicit device; CUDA allocator fraction .35; DemoYieldGuard; Torch 2/OpenCV 1 CPU threads; decoded image cache at most 1536 MiB |

The CLI does not expose hyperparameter overrides. `Config.validate()` rejects a
changed fixed setting; only explicit device, CPU demo-yield opt-out, and a smaller
decoded-cache budget are supported. CUDA cannot opt out of demo cooperation.
There is no augmentation, feature/logit cache, backbone unfreezing, random split,
early stopping or automatic promotion. Data shorter than4 seconds and uncertain
temporal margins follow the unchanged shared manifest/window contracts.

## Why retained probabilities matter

Installed PyTorchVideo `ResNetBasicHead.forward` runs projected pooling, dropout,
projection, **Softmax before `output_pool`**, then global averaging. Removing the
activation or fitting CE on a pooled-feature surrogate changes that function.
The new `baseline_model` only reconstructs the existing dropout+Linear projection
required by the pinned state dictionary; it does not replace activation or pooling.
All model modules stay eval while only the existing Linear weight/bias require
gradients. Eval mode does not disable their gradients.

The implementation directly forwards the full model and validates its two
probabilities. There is no second Softmax or post-pooling logit reconstruction.
NLL uses clamp-min epsilon 1e-7 only inside the loss: outputs are not renormalized
or clamped for prediction. Below epsilon the clamp derivative is zero; this
conservative limitation is recorded rather than silently loosening the loss.

Accumulation sums weighted NLLs, dividing each by the **actual group's sum of
target weights**, including the final four-window tail. This avoids cancellation
of class weighting from batch-one mean losses. 156 windows yield 20 steps/epoch,
60 fixed steps over 3 epochs. Tiny CPU tests compare updates with a batched
weighted-NLL reference using an incomplete group.

Every non-head tensor, including all BN affine parameters, means, variances and
counters, is hashed before fitting and asserted unchanged at every epoch end.
Every module's eval mode and exact trainable parameter list are also asserted.
The report records which head tensors changed, without pretending that weight
change or training loss establishes transfer performance.

## Inputs, rights and artifacts

Before model construction: verify manifest pin, every media hash, exact recording/
window/class counts, explicit review/permission, one CC0 VID source and its train-only
cohort, community baseline pin, and source-rights evidence. Calibration, holdout or
diagnostic recordings are rejected. No publisher-category labels enter fitting.
`training_data`, `read_window`, `FrameCache`, seeds/device setup and DemoYieldGuard
are reused by import; shared/live code is not edited.

VID copyright evidence does not independently verify participant releases. The
community publisher's MIT metadata conflicts with research/noncommercial prose;
that uncertainty is unchanged. This run is research-only, with no live promotion,
public redistribution or commercial-rights claim. Source evidence and DATA-RIGHTS
are copied; the CLI also copies round-2 results, paired results and the 3D-CNN
rights/source audit. Additional review/receipt files can be added with repeated
`--provenance-file` without changing the pinned training selection.

Each output directory must be new. Successful runs contain:

- `candidate-state.pt`: full safe CPU tensor state, state shape/dtype contract,
  config, baseline/manifest hashes, source/provenance hashes, rights, fixed class
  order/threshold, training summary and initial non-head hashes.
- `report.json`: `complete=true`, last-epoch choice, weighted losses/class weights,
  all training window identities, frozen-state assertions, cache statistics,
  measured process allocator peaks if run on CUDA, package versions and limitations.
- Exact `manifest.json`, implementation files in `source/`, evidence in `provenance/`.

No unrestricted pickle, remote code, pretrained download or live-loader change.
A failed run can leave source snapshots or an artifact without a complete valid
report. Use another new directory; do not treat those files as a candidate.
Hashes detect modification, not a malicious replacement of a whole self-consistent
run. Candidate validation uses restricted `weights_only=True` and finite CPU
tensors before architecture construction, then strict model keys/shapes/dtypes.
It revalidates frozen hashes, fixed settings/selection, copied manifest/rights,
empty evaluation splits and source snapshots. Raw media/base files are not needed
to load the self-contained candidate after the successful run.

`CommunityCandidate(run_dir, device='cpu').predict(BGR_frames)` returns
`fightScore`, two `classScores`, `fightIndex=1` and
`scoreKind=retained-backbone-softmax`. It reconstructs exactly the training
architecture and preserves its output, without a second activation.

## Parent-only zero-step check and execution

**No real initial forward parity is claimed by this helper.** The training report
explicitly says it was not measured there. Before fitting, parent should independently
compare `baseline_model`/`enable_head_only` output against the explicit-device
baseline control on representative valid windows, with identical selected frames.
Compare both class scores (suggested absolute tolerance 1e-6), unchanged state,
raw >.5 decisions and preprocessing. Keep that measured receipt separately, and
pass it as provenance if desired. Toy tests prove no-update semantics and provide
a counterexample to pooled-logit substitution; they do not prove real checkpoint parity.

From repository root, after the parent reserves GPU time and verifies parity:

```powershell
service/.venv/Scripts/python.exe service/train_community_x3d.py --device cuda --manifest service/training/vid-round2-v1.json --data-root service/training/data/vid --baseline-checkpoint service/models/x3d_rwf2000.pt --output-dir service/training/runs/community-head-nll-v1 --input-cache-mib 1536 --yield-to-demo
```

This is the single fixed full run, not a diagnostic-selected sweep. A CPU run is
possible with `--device cpu` and its own new output path, but no real CPU model
run was performed here. CUDA memory estimates/previous measurements are not a
measured peak for this new run; use its actual allocated/reserved peak report.

After the final epoch is exported, parent runs diagnostics in one separate process:

```powershell
service/.venv/Scripts/python.exe service/benchmark_cctv_candidates.py --candidate community --adaptation-run service/training/runs/community-head-nll-v1 --device cuda --cuda-memory-fraction 0.35 --corpus service/evaluation/corpus.json --output service/research/runs/paired-community-head-nll-cuda-v1.json --yield-to-demo
```

For a CPU diagnostic, change device to `cpu` and use a new CPU output filename.
No automatic cap increases, retry, service manipulation, threshold relaxation or
model promotion occur. Guard is best-effort cooperation, not an exclusive GPU lock.
Resident weights remain allocated while yielding.

## Benchmark versioning and acceptance

The minimal new `community --adaptation-run` branch validates report/artifact
before runtime/model construction. It records an adaptation weight hash separately
from baseline hash, training manifest hash and trained source hashes. The adapter
uses the same native crop/time buffer and selected frame PTS as other candidates.
Compare corpus, policy and paired-window hashes, not filenames or model labels.

Prior three completed paired reports pin runner SHA-256
`cb43e7f67f9e836031afb5198f4e119e7ecffc5b703c5b03ace0c91bf605a4bc`.
They are preserved exactly. The community extension changes runner implementation
bytes; it does **not** rewrite their source hash or change the paired policy.
New reports record their actual current implementation hash. During the parent
execution window, runner/test writes were held; work resumed only after release.

Current paired references are 67 actual windows, not the earlier expectation 69.
Calibration and holdout for VID remain explicitly empty. Paired development
comparisons can reject the candidate but cannot establish independent accuracy,
real crowded/night performance or live camera capacity. Parent retains the live
community X3D unless later evidence supports a separately authorized change.

## Verification status

Focused community-training and benchmark integration tests pass using tiny CPU
models/stubs, including actual parameter updates, identical exported/loaded
probabilities, no-update eval semantics, Softmax-before-pool counterexample,
correct weighted tail accumulation, frozen BN/dropout/non-head assertions, fixed
settings, rights/hash/manifest/artifact rejection, CPU-only safe loading, bounded
decoded cache, distinct artifact identity, unchanged pairing and no overwrite.
No actual checkpoint or GPU was exercised by this helper.

Final complete service unit suite: **553 passed, 4 skipped**, with the real CUDA
opt-in test explicitly disabled for this helper's test process and one existing
Starlette/AnyIO deprecation warning. Focused owned trainer/benchmark suites:
**84 passed** (38 new trainer tests plus 46 benchmark tests). Both CLI help paths
passed. No real checkpoint constructor/forward, CUDA, training job or service
change was performed by this helper.

An earlier suite run encountered two concurrent shared schema-version assertions
expecting 2 versus actual 3; the shared tests were subsequently updated outside
this scope, and the final rerun above passed. This helper did not edit those files.
All real GPU parity/training/diagnostic quality checks remain parent work.

The final runner SHA-256 is
`275e32ebca4c43859b7a390e54f3ba87dcf925cec40bb90d1bf581e2035fc773`.
The unchanged policy SHA-256 is
`c974d6f61ab429335cd6a1d917687c6671370a6a0c0edc54633e5a869cd74ac4`.
No prior paired report was rewritten.
