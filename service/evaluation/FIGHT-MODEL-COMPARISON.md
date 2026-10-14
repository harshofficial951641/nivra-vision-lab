# X3D-M versus MC3-18 diagnostic — 14 October 2026

**Decision: retain the existing experimental pipeline. No live model change.**

The current classifier is a community fight-tuned **X3D-M**, not X3D-S.
This comparison evaluates classifier outputs under one shared diagnostic policy;
it does not compare complete production pipelines or train either model.

## Observations

| Recording | Labelled events | X3D-M matched / missed | MC3-18 matched / missed | X3D-M / MC3-18 unmatched alerts |
| --- | ---: | ---: | ---: | ---: |
| Shadowboxing negative | 0 | 0 / 0 | 0 / 0 | 0 / 1 |
| Genuine-overlap grappling | 1 | 1 / 0 | 1 / 0 | 0 / 0 |
| Staged wrestling takedown/kick | 2 | 1 / 1 | 1 / 1 | 0 / 0 |
| Squats negative | 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Synthetic cropped grapple, separate | 1 | 1 / 0 | 1 / 0 | 0 / 0 |

Original footage: **both matched 2/3 events**, with **zero unmatched X3D-M alerts
and one unmatched MC3-18 alert**. The original footage totals 39.221 seconds;
these counts cannot estimate deployment accuracy or false alarms reliably.

Both classifiers first flag the original grapple at source time 3.84 seconds.
It begins mid-event, so this is not an incident-onset delay. The cropped version
first flags at 7.20 seconds for X3D-M and 3.84 seconds for MC3-18. The crop reuses
the original recording and is not independent evidence of natural partial-body
coverage. The short wrestling clip first flags at 3.879 seconds for both models.
The inherited matching tolerance assigns that prediction to the earlier event;
this is not proof that the takedown was recognized distinctly from the kick.

## Timing on this PC

NVIDIA GTX 1660 Ti 6 GB, PyTorch 2.5.1+cu124, float32, batch size one.
Each model processed 67 identical source-time windows, including the crop.

| Classifier | Median preprocessing + inference | p95 preprocessing + inference | Peak PyTorch allocated memory |
| --- | ---: | ---: | ---: |
| X3D-M | 132.3 ms | 244.9 ms | 145.1 MiB |
| MC3-18 | 56.6 ms | 113.4 ms | 115.7 MiB |

Three initial warmup calls are excluded. CUDA synchronization surrounds timing.
The models run sequentially while normal desktop applications remain open.
These are classifier-only measurements: they exclude video decoding, transport,
tracking, pose and action inference, alert confirmation and queueing. Memory is
PyTorch allocation only, excluding driver, decoder and other processes.
**They do not establish sustained multi-camera capacity or source-to-alert delay.**

MC3-18 uses 112x112 center crops; X3D-M uses 224x224 resized full frames, following
their respective preprocessing. Thus this is a checkpoint comparison, not an
equal-input-resolution architecture benchmark. MC3's center crop can exclude
people near the image edges, which deserves separate classroom evaluation.

## Frozen diagnostic method

- Existing checksum-verified `corpus.json` and media, with source groups intact.
- Four-second causal windows, minimum observed span 3.8 seconds.
- Source frames sampled at least 100 ms apart; inference at least 400 ms apart.
- Sixteen uniformly selected frames per window for both models.
- Each model's own RGB preprocessing, normalization and fight-class index.
- Fixed positive threshold strictly above 0.5 and eight-second alert cooldown.
- X3D uses its backbone softmax, not the publisher's second softmax.
- Inherited one-to-one event matching with a three-second trailing tolerance.
- No calibration, threshold tuning, fine-tuning or live policy modification.

All recordings were already inspected in prior development. The manifest's
historical `holdout` label does not make them unseen evaluation data. No classroom
crowds, hugs, handshakes, camera motion or comprehensive brief-hit cases are
covered. Classifier scores are uncalibrated and cannot be interpreted as violence
probabilities. Single full-scene scores cannot attribute the interacting actors.

## Reproduce

MC3 weights are local, Git-ignored and pinned to upstream revision
`a27adffec6651c10639b5b453e0df8564b9be298`; provenance is in `../THIRD_PARTY.md`.
The downloadable filename does not establish that it is the checkpoint behind
the upstream README's 92.5% result. Existing X3D provenance is unchanged.

From `nivra-vision-lab`:

```powershell
service/.venv/Scripts/python.exe service/benchmark_fight_models.py service/evaluation/corpus.json --output service/evaluation/runs/x3d-m-vs-mc3-18.json --mc3-sha256 8268694ade4c0e79a1c5fa41a4f3c21129082d75fac9eb7c25e5a0eabad49bfa
```

The local raw JSON records checkpoint, manifest and implementation hashes,
source links, policy, per-window scores, timing, events and matching counts.
Raw reports and weights remain ignored; this summary is reviewable in Git.

## Next evidence needed

MC3 is faster in this run but adds a false alert without improving original-event
matching. No promotion is justified. Obtain independent representative recordings
before calibration or fine-tuning, reserve unseen recording groups, then measure
false alerts per camera-hour, missed incidents and live alert delay. Evaluate
edge-of-frame actors and sustained multi-camera workload before choosing a
configuration. X3D-S training was not attempted on this diagnostic-only corpus.
