# Expanded community head adaptation V2

Original implementation: four new V2 files. Parent then authorized the bounded
benchmark integration described below. V1 trainer, its CLI/tests, builder, live
service, baseline checkpoint and existing run receipts remain unchanged.
This is a fixed offline hypothesis, not evidence that more epochs improve transfer.

## Fixed experiment and data gate

- Parent supplies an explicit manifest path **and SHA-256**. Every media hash,
  review/permission contract and recording split is checked before constructing a
  model or creating output. Only source `vid-v2`, CC0-1.0, training allowed, and
  the single `vid-v2-unresolved-session-cohort` are accepted. Both eligible window
  classes are required; counts are computed, never copied from round two.
  Parent must use the cleaned expanded manifest after dedicated re-review. An
  independent audit found the legacy builder had filled full-duration normal
  events for 26 records lacking explicit intervals; parent fixed that builder.
  V2 does not import the builder or fill annotation gaps. The old 96-recording
  manifest is not a default or evidence of fully observed normal coverage. Old
  pilot labels remain legacy sampled-label research. Explicit intervals and a
  `reviewed` flag are schema gates, not proof that a reviewer inspected the tail;
  independent source/evidence review must establish that before parent pins SHA.
- Reuse V1 trusted pinned community construction, retained Softmax **before**
  output pooling, existing binary Linear weight/bias, preprocessing and decoder.
  Do not substitute Softmax of pooled logits, features, or a new projection.
  The entire model stays eval, including BN and dropout; eval permits gradients.
- AdamW LR `1e-5`, weight decay `.01`, seed `17`, FP32, batch one, accumulation
  eight, weighted NLL of `log(clamp_min(probability, 1e-7))`. The clamp is not
  renormalized and has zero derivative below epsilon. Weights are N/(2*N_class),
  computed from train only. Each optimizer group divides summed weighted NLL by
  its actual target-weight sum, including the final partial group.
- Explicit max epochs **3, 10 or 20**. One optimizer and shuffle generator run
  continuously. Applicable milestones are 3; 3/10; or 3/10/20. Cumulative updates
  at epoch E are `E * ceil(N_windows/8)`; microbatches `E * N_windows`. No restart
  at milestones, early stopping, augmentation, scheduler, threshold fitting,
  diagnostics in training, or best-checkpoint selection.
- Reuse bounded CPU decoded-frame LRU, 0..1536 MiB (zero disables). No feature,
  representation, gradient or prediction cache. OpenCV one thread, Torch two;
  one decoder. CUDA requires explicit device, `.35` allocator fraction set before
  construction, seeded workspace policy and DemoYieldGuard before construction,
  each inference/backward microbatch and optimizer step. Guard is best effort,
  not an interprocess lock, and leaves model allocations resident while yielding.

Existing V1 zero-step equivalence was measured by parent, not rerun here. V2
imports the same forward-path utilities; real V2 zero-step/device parity remains
parent verification. Tiny CPU tests cover initial no-update behavior independently.
CUDA determinism is seeded/best effort: inherited Torch pooling warnings remain;
no bitwise reproducibility claim. Do not launch all budgets if an earlier
parent-reviewed transfer, gradient, loader or annotation result warrants stopping.

## Artifact and failure contract

`train_community_experiments.py` requires a **new** output directory. The root
preserves input/source/provenance bytes and hashes, immutable `started.json`, and
one `epoch-003`, `epoch-010`, `epoch-020` directory per requested milestone.
Each milestone independently contains:

- Full CPU float32/int64 `candidate-state.pt`, restricted-loadable with
  `torch.load(weights_only=True, map_location='cpu')`; no arbitrary pickle globals.
- `report.json` with actual export epoch, cumulative optimizer/microbatch counts,
  weighted loss history, actual class counts/weights/window identities, state
  shape/dtype contract and hashes proving all non-head tensors stayed unchanged.
- Exact manifest, rights evidence, imported-helper sources, V1/V2 CLI/module
  snapshots and explicit additional review/provenance files. No source is executed
  from these copies. Full state can reconstruct the same trusted installed
  architecture without loading another checkpoint or downloading anything.
- Distinct base SHA, candidate SHA, manifest SHA, source/provenance hashes,
  architecture/class/preprocessing contracts, fixed threshold `.5`, unresolved
  rights restrictions, and empty calibration/holdout explicitly recorded.

The last write is root `complete.json`, a catalog sealing report/checkpoint hashes
for **all** milestones. On fitting/export failure, retain `failed.json` and prior
evidence. No seal means no usable candidates, including an earlier milestone.
The loader checks every cataloged milestone still exists unchanged, rejects a
failed-run marker, checks selected provenance/manifest/rights/tensor/frozen proof
and exact epoch accounting **before** model construction. Keep the whole run
together; milestones have independent identities but require the root seal and
their siblings for completion validation. This is integrity checking, not a
cryptographic signature or independent audit of labels. Use a new output path
after failure; never resume/overwrite or silently call partial success complete.

### Runtime and dependency provenance (required for new V2 artifacts)

Parent's independent audit identified missing runtime/dependency provenance in
the initial V2 draft. New runs now include the same primitive `runtime` object in
`started.json`, every safe artifact/report and root seal. The seal additionally
hashes `started.json`; all copies and snapshot inventories must agree on load.
The runtime is also saved as hashed `runtime/environment.json` in the root and
each milestone, alongside the copied dependencies. Missing records in earlier
V2 drafts fail validation; existing artifacts/receipts are never rewritten.

Recorded actual observations: Python version/implementation/compiler build, OS
system/release/version/machine, Torch build version and reported source commit,
compiled CUDA toolkit and linked cuDNN library version (or null), NumPy/OpenCV/
PyTorchVideo module versions, and normalized installed package/version inventory.
CUDA/device/driver probing is not used to collect these fields. Compiled CUDA and
linked cuDNN metadata do **not** establish a usable GPU, driver version, actual
kernel execution or cross-device equivalence. Version strings are observations,
not invented revision pins or a determinism guarantee.

Snapshot the existing Python manifests/locks at service and repository roots:
`requirements*.txt`, `pyproject.toml`, `uv.lock`, `poetry.lock`, `Pipfile[.lock]`
and `pdm.lock`. This repository's `service/requirements.txt` and
`service/requirements-lock.txt` are required. Absent optional files are not
fabricated; unrelated frontend package locks are outside this Python experiment.
Copies preserve observed declarations even if they differ from the installed
inventory; this does not claim all declarations were enforced by an installer.

Bounded installed-source copies/hash pins cover the PyTorchVideo X3D hub/builder,
head/stem/residual/net/weight initialization, convolution/swish/rounding helpers;
the actual fvcore squeeze-excitation implementation imported by X3D; and Torch
AdamW/optimizer, activation/Linear/pooling/BatchNorm/functional implementations.
The total dependency snapshot budget is 8 MiB per copy. Sources are read through
installed distribution paths, never imported from the snapshots or executed to
collect metadata. These are critical implementation pins, not a complete binary
or transitive supply-chain attestation.

Before constructing a training model or loading a candidate, require installed
Torch, NumPy, OpenCV, PyTorchVideo, fvcore and torchvision distribution versions
to match the recorded inventory, and each selected installed source hash to match
its fitting pin. Changed local implementations fail closed. Platform/Python/CUDA
metadata is retained rather than automatically claimed equivalent on another
machine; cross-environment support requires explicit parent review and parity
testing. This stricter loading contract never installs packages or downloads code.

`ExperimentCandidate(milestone_dir, manifest_sha256=SHA, device='cpu')` exposes
`predict(BGR_frames)` inherited from the proven V1 adapter, returning `fightScore`,
`classScores` in `[normal, fight]` order, `fightIndex=1`, and
`scoreKind='retained-backbone-softmax'`. Minimum eight observed frames; the caller
must enforce continuous source-time coverage. `metadata()` includes V2 kind,
actual epoch, base/candidate/manifest hashes and trained source hashes. Decisions
remain strictly `fightScore > .5`; scores are uncalibrated.

## Parent commands (not executed by this helper)

From `service`, after independent review freezes the expanded manifest and SHA:

```powershell
$manifestPath = 'training/vid-round3-v1.json'
$manifestSha = '<PARENT-PREDECLARED-64-HEX-SHA256>'
.venv/Scripts/python.exe train_community_experiments.py --manifest $manifestPath --manifest-sha256 $manifestSha --data-root training/data/vid --baseline-checkpoint models/x3d_rwf2000.pt --output-dir training/runs/community-head-nll-v2-round3-e20 --device cuda --max-epochs 20 --yield-to-demo --input-cache-mib 1536 --provenance-file training/round3-review.json
```

The manifest and review paths above are proposed names, not claims they already
exist. Replace with the actual frozen deliverables; pass each separate review
file using repeated `--provenance-file`. Record the SHA before fitting. Parent can
choose `--max-epochs 3` or `10` and a corresponding fresh output path instead of
20. All other settings stay fixed. A CPU command uses `--device cpu` and a new
output path, but no real CPU model run was authorized here either.

Validation/load seam for parent CPU smoke, with no prediction implied:

```powershell
.venv/Scripts/python.exe -c "from nivra.community_x3d_experiments import load_candidate; model, report = load_candidate('training/runs/community-head-nll-v2-round3-e20/epoch-003', manifest_sha256='<FROZEN-SHA256>', device='cpu'); print(report['training']['exportEpoch'])"
```

Parent should first measure real zero-step equivalence against the pinned baseline
on identical source windows, then complete fitting and CPU reload parity. Compare
chosen completed milestones only on frozen development diagnostics; hold reserved
audit for one final frozen model/policy. Parent alone schedules actual GPU jobs,
one process/model at a time. Preserve prior report source hashes and outputs.

## Implemented separate benchmark integration

Parent authorized this bounded follow-up after reviewing V2. The runner now
accepts `--candidate community-v2`, requiring explicit
`--training-manifest-sha256` and a milestone path in `--adaptation-run`.
`community` remains V1; existing candidate/output behavior and nested
`qualityVariant` derivative/source-group reporting are preserved. Policy, strict
PTS, source-time pairing, crop geometry and preprocessing selection are unchanged.

Before runtime, model factory or decoding, the runner validates all diagnostic
media and the selected V2 artifact through `validate_artifact`: expected manifest
SHA, full milestone/root-seal completion, all sibling artifacts, selected report,
source/provenance snapshots, rights, actual epoch and frozen-state proof. It pins
the root seal before validation and verifies those bytes stayed unchanged during
validation. Explicit CPU is forwarded without automatic CUDA selection.
V2 CUDA requires `.35` as in its fixed loader; another fraction is rejected before
runtime so the loader cannot silently raise a caller's smaller requested cap.
Existing candidates retain their previous configurable fraction behavior.

Reports identify V2 separately through `candidate`, `adaptationIdentity` and the
adapter metadata. Identity records baseline/candidate/report/manifest SHA,
`exportEpoch`, `runSealSha256` and trained source hashes. Current implementation
hashes additionally cover V2, V1 helper, frame-cache/device helper, training-data
contracts and X3D constants/safe-loading helper. A changed seal during comparison
fails without writing a report. Incomplete/invalid assets fail before runtime;
existing output paths cannot be overwritten. Prior raw reports keep their
original runner hashes and bytes; a new runner hash is expected for new reports.

Example parent command after the cleaned expanded manifest and run are frozen:

```powershell
.venv/Scripts/python.exe benchmark_cctv_candidates.py --candidate community-v2 --training-manifest-sha256 '<FROZEN-SHA256>' --adaptation-run training/runs/community-head-nll-v2-round3-e20/epoch-003 --device cuda --corpus evaluation/corpus.json --output research/runs/community-v2-round3-e003-paired-v1.json --yield-to-demo --cuda-memory-fraction .35
```

Repeat only for predeclared eligible milestones with distinct new output paths.
The command is implemented; no actual V2 model scoring was run by this helper.

## Verification and interpretation

New CPU tests use the existing tiny synthetic model/fixture, never real weights,
media, CUDA, X3D construction or diagnostic predictions. They compare actual head
updates to batched weighted NLL over full/tail groups, verify continuous 3/10/20
milestones and export/reload parity, frozen BN/dropout/non-head state, bounded input
cache, explicit CPU/restricted load, no holdout fitting, media/permission/review/
source/manifest/base failures, corrupt artifacts/actual epoch/accounting/rights,
missing siblings, failed runs and no overwrite. Runtime regressions additionally
check observed package/source metadata without CUDA probing, started/report/state/
seal parity, missing requirements/locks/builders (including removal from a
re-signed inventory), altered runtime snapshots and changed local dependency
versions/source before model construction.

Final verification on the frozen implementation: **732 passed, 5 skipped** in
71.07 seconds, one existing Starlette/AnyIO deprecation warning. This includes
**71 V2 trainer tests and 63 runner tests**. Before final provenance extensions,
the focused runner/V2/quality-variants suite passed 168 tests; the focused
runtime/runner suite passed 133 before the final missing-fvcore regression. The
final full suite includes that regression. The opt-in real-CUDA regression was
explicitly disabled. No actual model/checkpoint/inference/training/GPU job was
run by this helper; tiny CPU networks perform real parameter updates in tests.

### Frozen implementation handoff

The bounded runner integration and runtime follow-up are implemented and ready
for independent review. No further implementation/test writes are planned after
these pins. Parent must still admit the independently reviewed cleaned expanded
manifest and complete final independent audit before scheduling any model job.
Training/diagnostic commands above are available, not executed evidence.

| File under service | SHA-256 |
| --- | --- |
| `nivra/community_x3d_experiments.py` | `d593b45b3e5985d7c15c24311c9c3646d908b4bdaf6c84a31fcd49486638fdc4` |
| `tests/test_community_x3d_experiments.py` | `0181b08ec3284754ea114019f2b0345839f27659f1d5c48544d6a2b5ca76be7d` |
| `train_community_experiments.py` | `f233e7e2be03040dd7dc81eabda1fcb23e1f1672c137ed7235fabb5654ff4811` |
| `benchmark_cctv_candidates.py` | `35f95c8134ead0c496b344f221cef3cc524467d002bf5c81217cb1fbd2859ad4` |
| `tests/test_benchmark_cctv_candidates.py` | `d747badef69ddba15e8660a4b6beedecb146f415eb426f326e0a4d566349c055` |

The prior auditor observation `db8fae...` was an intermediate V2 module pin;
it is superseded by the final module pin above. Exact final implementation pins
were sent directly to auditor chat `7cde41a3-5d12-4d46-943f-edb9ab718189` and
parent. Final receipt and this document's own hash follow in the completion
message; this document does not claim the final independent audit has passed.

Model failures can arise from the frozen representation, retained activation/
pooling path or limited head capacity. Data failures can arise from provisional
labels, VID staging/sport/background biases, unknown actor/session lineage,
occlusion, low person pixel size or sensor/illumination shift. Additional reviewed
VID and more epochs cannot isolate these causes or establish unseen accuracy.
No independent VID holdout/calibration exists; overlapping windows remain
dependent. No 50–100-person, real near-IR CCTV, thermal or low-light-colour holdout
is established. Synthetic grayscale/darkening is not night evidence. No live
capacity, hostile intent, injury, identity or guilt inference is authorized.

Estimated resource use only: frozen-backbone FP32, batch one, two trainable Linear
tensors and bounded decoded CPU input should resemble V1's training footprint;
extra epochs mainly add runtime and disk snapshots. `.35` of a nominal 6 GiB GPU
is about 2.1 GiB allocator allowance, **not measured peak or total free VRAM**.
Root reports record actual allocated/reserved peaks only when parent runs CUDA.
No runtime/accuracy/improvement estimate is presented as a measurement.

Community checkpoint code metadata and model-card research/noncommercial wording
remain conflicting. VID CC0 copyright evidence does not independently establish
full subject releases. Provisional assistant labels are not human ground truth.
All artifacts remain research-only, with no automatic live promotion or public
redistribution. More reviewed sources means more data, not a promised accuracy.
