# Community-head pilot: legacy-label development result

21 October 2026. **Training completed on CUDA; no live promotion.** This pilot
does not demonstrate improved detection. An independent audit subsequently found
that 26 legacy normal review records had no explicit intervals: the old manifest
builder inferred full-source normal spans despite sampled-frame review. The
builder now rejects missing intervals; the frozen pilot input/result is preserved
as legacy sampled-label research. Larger training awaits corrected review data.

## Actual run

- Pinned community X3D-M initialization; parent verified exact zero-step parity
  on boxing, grappling and kick windows, with maximum class-score difference 0.
- 96 training recordings, 156 windows (65 positive/91 normal), one unresolved VID
  cohort. No independent calibration/holdout; the label-coverage caveat above
  applies. Three fixed epochs, 60 optimizer steps, seed17, weighted NLL, AdamW
  LR1e-5, weight decay.01, accumulation8, FP32, CUDA allocator fraction.35.
- Only the existing Linear weight/bias changed. Every other tensor and BatchNorm
  state stayed unchanged; the whole model remained eval with dropout disabled.
- Weighted training NLL: **0.456846 -> 0.446911 -> 0.438221**. This is a training
  fit observation, not accuracy or independent generalization evidence.
- Run time **166.653 seconds**. Peak process Torch allocated **192.634 MiB**,
  reserved **240 MiB**; driver, other models and decoder are excluded. Decoded
  host-frame cache used 890.326 MiB, 156 misses/312 hits/no evictions.

## Paired development diagnostics

All **67 window decisions are individually unchanged** against the current
baseline, with matching corpus, policy and paired-window hashes:

| Recording | Baseline flagged / total | Pilot flagged / total |
|---|---:|---:|
| Shadowboxing | 0/12 | 0/12 |
| Grappling | 13/17 | 13/17 |
| Staged wrestling/kick | 2/2 | 2/2 |
| Squats | 0/19 | 0/19 |
| Synthetic cropped grappling | 10/17 | 10/17 |

Raw scores changed, but neither that change nor lower training loss demonstrates
improved decisions. The crop is dependent on the grappling source. These are old
development clips; no event-recall, camera-hour or crowded/night accuracy claim.

## Artifacts

All raw run files remain ignored and unmodified.

| Artifact | SHA-256 |
|---|---|
| `runs/community-head-nll-v1/candidate-state.pt` | `5fcd710000fe72f73622dfbf4daeb74a4bbbab52c4bf76401cad358f7fc33278` |
| `runs/community-head-nll-v1/report.json` | `5bb5aad9a246645a99005aea1830ddce5af736b46751ba33336cf3b170f61bc1` |
| `../research/runs/paired-community-head-nll-cuda-v1.json` | `79fab88d28f4ee5459f1b63bf0dcb93c96007dcc6259084567e4aba7e884f942` |

Zero-step evidence: `../research/runs/community-zero-step-parity-v1.json`.
Fixed implementation/settings: [COMMUNITY-TRAINING-PLAN.md](../research/github/COMMUNITY-TRAINING-PLAN.md).
Next data/evaluation rules: [TRAINING-AND-TESTING-PLAN.md](../research/github/TRAINING-AND-TESTING-PLAN.md).
The independent label audit and re-review are still in progress; do not treat
these frozen old intervals as fully observed normal time.
