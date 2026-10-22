# Round 2: public footage and CUDA fine-tuning

21 October 2026. **Do not replace the current public model with this candidate.**
The final-stage fine-tune learned the training data, but underperforms the current
community X3D-M on the existing wrestling diagnostics. The public service remains
on its original checkpoint.

## Data

Six independent Codex helper chats produced three positive reviews, two normal
reviews and the fine-tuner. Their output was integrated after checking media
hashes, duplicate IDs, source archives, annotation bounds and evidence paths.
The 17 every-frame normal spans also passed a decoder-presentation-time coverage
check; interval tails remain unknown.

- Imported pool: **932 videos**, including 378 from the two newly verified VID
  V2 CC0 archives. Original inventories remain unchanged; expanded inventories
  are separate. Copyright evidence does not establish independently audited
  participant releases or commercial clearance of the base model.
- Screened: **258 recordings**. Accepted for this experiment: **96**, consisting
  of 39 positive and 57 normal recordings. The other 162 screened clips are
  excluded/ambiguous; 674 imported clips remain unreviewed.
- Generated training windows: **156**, with 65 positive and 91 normal examples.
  Overlapping windows from a recording are not independent recordings.
- One unresolved VID recording/session cohort, entirely training-only. There
  is no calibration or holdout. Assistant visual labels remain provisional;
  they are not human ground truth or continuous-motion verification.

[vid-round2-v1.json](vid-round2-v1.json) SHA-256:
`1a0f6fc44704b73f32c5e0ab82b607fff2a702a848186b4403ddf357a0026a84`.
Rebuilding through the manifest CLI from all three inventories and eight review
files produced exactly the same bytes and SHA-256. The CLI accepts repeated
`--inventory` and `--review` arguments and rejects stale review provenance.

## Actual GPU run

The four-window CUDA smoke run passed before full fitting. The full run used
the **GTX 1660 Ti**, batch one, accumulation eight, FP32, five fixed epochs,
seed 17, head LR .0001, final-stage LR .00001 and training-only class weights.
The last residual stage and projected-pooling/classifier head were trainable;
earlier stages and all BatchNorm state remained frozen.

- Elapsed: **219.377 seconds**; 100 optimizer steps.
- Peak PyTorch GPU allocation: **218.160 MiB**; reservation: 298 MiB. These
  measurements exclude the live service, driver and other processes. The
  process allocator cap stayed at 40% of GPU memory.
- Decoded-frame cache: 890.326 MiB CPU RAM, within a 1536 MiB budget; 156 misses,
  780 hits, no evictions. Only decoded images were reused; model features and
  gradients were recomputed throughout training.
- Direct state comparison with seeded official initialization verified **42
  changed tensors**, including 38 in the final residual stage. Zero prefix or
  BatchNorm tensors changed. This was actual backbone adaptation, not just a
  frozen-feature probe.
- Weighted training loss fell from .5541 to .00945. Training classification
  fit all listed windows; this is not evaluation accuracy.

CUDA pooling backward is not strictly deterministic in the installed Torch
version. The run explicitly warned and records its fixed-seed/deterministic
settings without promising bitwise CUDA reproducibility.

Run directory: `runs/vid-finetune-round2-cuda-v1/`. Full safe CPU state:
`candidate-state.pt`, SHA-256
`bf0de977154bbd80d2e859a53961c92c47f77727565905f6a20b81d3a7956d4a`.
The safe loader verified all tensor contracts, source/provenance snapshots and
manifest hashes. Parent verification is saved beside the report.

## Diagnostic comparison

Threshold remained the predeclared, uncalibrated **score > .5**. No diagnostic
threshold tuning occurred. Candidate and baseline use identical source-window
timestamps; corpus hashes also match.

| Recording | Windows | Current model review windows | Round-2 candidate review windows |
| --- | ---: | ---: | ---: |
| Shadowboxing | 12 | 0 | 0 |
| Grappling | 17 | 13 | 1 |
| Staged wrestling kick | 2 | 2 | 0 |
| Squats | 19 | 0 | 0 |
| Grappling crop | 17 | 10 | 0 |

These are window decisions, not incident counts or accuracy. The crop repeats
the grappling source. All footage had already influenced development and cannot
serve as an independent holdout. Avoid interpreting fewer review windows as an
improvement when they are known contact examples.

`diagnostics.json` SHA-256:
`e2aa7639f160da07a42b48c257fa75e4d8859e8f4caf2cb55cd91ff6c0dcdcb8`.
`report.json` SHA-256:
`74edf60c951bb039a19892f88f1c4f7f27b5c851f8ddfa9480aabdd67c3fd087`.

## Verification and next requirement

The complete current Python suite passed **268 tests**, with two Windows
symlink restrictions and one opt-in CUDA unit test skipped. Real CUDA training,
gradient updates, frozen-state invariants, safe artifact loading, diagnostic
inference and public health were separately exercised. No frontend source or
deployment changed.

Keep this candidate offline. Training fit did not transfer to these diagnostic
videos; the underlying cause is not established by this experiment. Stronger
motion-reviewed labels, matching hard negatives and genuinely independent camera
evaluation are required before claiming an upgrade or changing the public model.
