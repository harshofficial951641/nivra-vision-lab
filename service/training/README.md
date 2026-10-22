# Offline X3D-M training

This workflow imports licensed public footage and trains separate experimental
candidates. It does not publish footage or replace the running model.

## Data and labels

The local VID import now contains **932 videos**. The authors'
Dataverse V2 deposit declares CC0. Consent and ethics approval are author-reported;
individual releases were not independently audited. See [DATA-RIGHTS.md](DATA-RIGHTS.md)
and [vid-source.json](vid-source.json) for primary evidence and excluded datasets.

The first pilot screened 48 clips and retained 36 recordings. Round 2 brings the
total screened pool to 258 recordings, retaining 96: 39 positive and 57 normal.
The current [manifest](vid-round2-v1.json) produces 156 four-second windows
(65 positive, 91 normal). Unreviewed and ambiguous material cannot enter fitting.
These are assistant-screened training labels, not continuous-motion or human
annotations.

All VID material remains in one unresolved session/recording cohort, entirely in
training. There is **no calibration or independent holdout**. Different filenames,
camera views, crops and pose-rendered copies do not establish independent samples.
The candidate has not demonstrated a detection improvement.

The completed CUDA last-stage/head adaptation and diagnostic failure are recorded
in [ROUND2-RESULTS.md](ROUND2-RESULTS.md). Its five-epoch GTX 1660 Ti run took
219.377 seconds; the current public model remains unchanged.

## Preparation

Run from the repository root using the existing service environment. Windows'
libarchive `tar.exe` reads RAR files; no dataset scripts are executed.

```powershell
service\.venv\Scripts\python.exe service\prepare_vid.py --archive nv_b_01.rar --archive nv_b_06.rar --archive v_c_b_01.rar
service\.venv\Scripts\python.exe service\review_training_clips.py --data-root service/training/data/vid --archive nv_b_01.rar --per-class 12 --dense
```

Preparation checks pinned download sizes and publisher MD5s, safe archive paths,
entry types, extracted sizes and readable video metadata. Each media file gets a
SHA-256 in the local inventory. Publisher categories remain unreviewed; importing
does not approve labels or assign splits. Review sheets and media stay in ignored
`data/`; results stay in ignored `runs/`.

Review decisions are versioned separately. Rebuild to a **new** output filename:

```powershell
service\.venv\Scripts\python.exe service\build_training_manifest.py --review service/training/positive-review.json --review service/training/negative-review.json --review service/training/campus-negative-review.json --output service/training/vid-pilot-rebuilt.json
```

The validator checks explicit source permission/evidence, safe local paths, media
hashes, temporal annotations and recording/hash isolation across splits. Permission
is an audited assertion; code cannot infer consent. Invalid output is not published.

## Model provenance and training

The official base is
[`X3D_M.pyth`](https://dl.fbaipublicfiles.com/pytorchvideo/model_zoo/kinetics/X3D_M.pyth),
SHA-256 `eb9583d5f5a988a5c5f06f75760b070a5c9715794bd3b0536b78bd30595dcf67`.
Download it separately into ignored `service/models/x3d_m_kinetics.pyth`.
PyTorchVideo code is Apache-2.0; a separate explicit checkpoint licence grant and
Kinetics source-video rights were not established by this audit. This is an
internal research candidate, with commercial model clearance unresolved. The
current community checkpoint also has conflicting MIT/noncommercial wording.

The later fine-tuner adapts the final residual stage plus projected pooling/head.
See [FINE-TUNING-PLAN.md](FINE-TUNING-PLAN.md) for the contract and commands. Use
`--manifest service/training/vid-round2-v1.json --input-cache-mib 1536` with the
training subcommand for the expanded dataset and bounded decoded-frame reuse.
The cache stores CPU images, not frozen features, and does not replace gradients.
Snapshot all five round-2 review files and the extra archive catalog using repeated
`--provenance-file` arguments. New run directories are always required.

The trainer fits a fresh linear head on frozen official X3D-M features. It uses
16 RGB frames at 224 square, mean .45/std .225, cross entropy on logits, and one
Softmax for prediction. This is **head training, not full-backbone fine-tuning**.
Class weights come only from training labels.

```powershell
service\.venv\Scripts\python.exe service\train_x3d.py --manifest service/training/vid-pilot-v1.json --data-root service/training/data/vid --base-checkpoint service/models/x3d_m_kinetics.pyth --output-dir service/training/runs/another-new-run --device cuda --yield-to-demo --epochs 100 --class-weight
```

CUDA is explicit and must be available; there is no silent CPU fallback. Use
`--device cpu` without `--yield-to-demo` for an offline CPU run. New runs save a
separate head, features, exact window IDs, configuration, source snapshots and
input/implementation hashes. They never overwrite a prior run or the live model.
Without calibration, threshold .5 is explicitly uncalibrated. Holdout cannot
influence fitting or threshold choice. Training fit is not detection accuracy.

## Diagnostic inference and promotion

```powershell
service\.venv\Scripts\python.exe service\compare_x3d_training.py --run-dir service/training/runs/vid-pilot-gpu-v1 --base-checkpoint service/models/x3d_m_kinetics.pyth --corpus service/evaluation/corpus.json --output service/training/runs/vid-pilot-gpu-v1/diagnostics.json
```

Comparison verifies all model/media hashes, uses identical causal windows and
forces CPU inference. Existing corpus clips have already influenced development;
they are diagnostics regardless of historical split names. The grappling crop is
a second view of the same recording. No holdout accuracy is claimed.

Before promotion, continuously review temporal labels, add difficult normal
interactions in matching settings and obtain an independent camera evaluation
separated by original recording/session. Compare missed events and false alerts
under one fixed policy, then check live latency and the human-review flow. Current
results and the public-model decision are recorded in [RESULTS.md](RESULTS.md).
