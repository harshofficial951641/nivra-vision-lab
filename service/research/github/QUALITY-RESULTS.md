# Resolution and compression development diagnostics

21 October 2026. Parent ran the current baseline and legacy-label three-epoch
community-head pilot on the same completed quality-v2 corpus. **All 187 window
decisions match individually between these two checkpoints. No improvement or
live-model change follows.** This comparison remains development sensitivity
testing; the pilot's label-coverage problem is recorded separately.

## Verified inputs and pairing

The complete CPU preparation receipt has four original sources, eight new H.264
media files and fifteen manifest records including dependent crop views. Parent
recomputed the corpus and every generated media hash before scoring. FFmpeg PTS
were preserved exactly and independent OpenCV source/output clocks agree within
2e-12 ms. No timestamps or event labels were adjusted to fit predictions.

- Corpus SHA-256: `c274ce34b0395ce6c0f20d6dbfbd3bb6a98d58c56c1eba783a7e17066ab8b7cd`
- Paired-window SHA-256 for both actual GPU runs:
  `cb8a1f7efc776aee0eedc6411fb7d4fd8f5e2bf678d90c36bf927c325d8b7399`
- Strict >0.5 threshold, unchanged four-second source-time policy, no tuning.

The runner now recognizes nested `qualityVariant` provenance as a derivative and
retains that metadata in its report. A new integration regression checks that
synthetic variants remain in their original source group and are not marked as
originals. Runner tests: 47 passed. Earlier raw reports remain unmodified at their
original implementation hashes.

## Observations

Both checkpoints produced the following flagged-window counts. These are raw
decisions, not independent event recall, accuracy or proof of true contact.

| Source/view | Original | 720p CRF23 / CRF35 | 480p CRF23 / CRF35 |
|---|---:|---:|---:|
| Shadowboxing | 0/12 | 0/12; 0/12 | 0/12; 0/12 |
| Grappling | 13/17 | Not generated: native height608 | 13/17; 16/17 |
| Staged wrestling/kick | 2/2 | Original is720p | 2/2; 1/2 |
| Synthetic cropped grappling | 10/17 | Not generated: dependent608p source | 11/17; 12/17 |
| Squats | 0/19 | Portrait original retained | No derivative in initial landscape matrix |

At heavier480p compression, one kick-clip window no longer passes the threshold.
Grappling/cropped-grappling flag counts rise under some transformations. Neither
direction proves improved or worsened operational accuracy: these are a few
dependent development recordings with approximate episode context. Compression
and scale were changed together; there is no separately measured resize-only
lossless-reference control in this initial matrix.

## Limits and artifacts

All variants were generated directly from originals. Sources are ordinary-light
few-person material, not true near-IR, low-light-colour or50-100-person validation.
The portrait fixture's unspecified SAR stays unknown; no square-pixel assumption
or portrait derivative was introduced. Failed earlier preparation receipts remain
preserved and were not consumed by either model run.

Ignored actual GPU reports:

- `service/research/runs/quality-x3d-cuda-v1.json`
- `service/research/runs/quality-community-head-nll-cuda-v1.json`

CPU preparation evidence and exact matrix:
[QUALITY-VARIANTS.md](QUALITY-VARIANTS.md).
Pilot and legacy-label limitations:
[COMMUNITY-PILOT-RESULTS.md](../../training/COMMUNITY-PILOT-RESULTS.md).
No window derivatives are added to training or reserved online audit data.
