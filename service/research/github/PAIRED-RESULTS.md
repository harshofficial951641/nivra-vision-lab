# Paired GPU classifier diagnostics

21 October 2026. **Retain the existing community X3D-M.** Neither tested
alternative meets the predeclared goal of improving detection without adding
false alerts on these diagnostics. This is a limited development decision, not
evidence that X3D-M is universally best or ready for crowded/night CCTV.

Parent executed all three candidates sequentially on GTX 1660 Ti 6GB, FP32,
batch one, with a .35 Torch allocator fraction and live-demo cooperation. No
model, threshold or live service was changed. Each candidate's native saved
preprocessing was preserved; different centre crops still imply different
spatial coverage.

## Observations

Cells below are **flagged windows / eligible windows** at strict score >0.5,
not accuracy or event recall. Neighboring windows overlap and are dependent.

| Development recording | X3D-M | MC3-18 | cliffer1 VideoMAE-Base |
|---|---:|---:|---:|
| Shadowboxing negative | 0/12 | 12/12 | 9/12 |
| Grappling | 13/17 | 17/17 | 17/17 |
| Staged wrestling/kick | 2/2 | 2/2 | 2/2 |
| Squats negative | 0/19 | 0/19 | 0/19 |
| Synthetic cropped grappling, separate | 10/17 | 17/17 | 17/17 |

The alternatives flag grappling more consistently but also flag ordinary
shadowboxing. None of these counts demonstrates distinct recognition of the
earlier takedown versus the later kick. The crop shares its original source and
must not be counted as independent footage. The historical greedy event-credit
routine was deliberately excluded from this new comparison.

## Measured classifier cost

| Candidate | Median / p95 adapter time | Peak Torch allocated / reserved |
|---|---:|---:|
| X3D-M | 86.7 / 146.0 ms | 135.9 / 198.0 MiB |
| MC3-18 | 53.4 / 90.1 ms | 116.1 / 136.0 MiB |
| VideoMAE-Base | 625.6 / 972.2 ms | 598.9 / 650.0 MiB |

Timing includes spatial preprocessing, transfer, forward and returned scores;
three initial warmups are excluded and CUDA synchronization bounds every call.
Decode/window assembly and live-demo waiting are excluded. These are single-run
classifier measurements, not live FPS, end-to-end latency or 100-person capacity.
Torch memory excludes driver, ONNX, other processes and the resident live service.
VideoMAE's median here is approximately 7.2 times X3D's, without a false-alert
advantage. No independent repeat-variability measurement was performed.

## Pairing and reproduction

All three complete reports contain **67 rows**, observed from actual decoding:
12+17+2+19+17. No rows were added to meet an earlier expectation of 69.
Their corpus, policy and source-window identity hashes match exactly:

- Corpus: `33d04d15bc4a6911face456fff7488320906505cc344f863042e4cae304bfb34`
- Policy: `c974d6f61ab429335cd6a1d917687c6671370a6a0c0edc54633e5a869cd74ac4`
- Paired windows: `d42745b6512c14d2854e3a7eacb6a2adcaff58d324d2ee86b94db358b8c2c408`

Strict source presentation timestamps, native/cropped geometry and selected
frame PTS are recorded per row. Malformed WebM nominal FPS was never used as
a clock. The original four recordings total 39.221 seconds and have influenced
development; historical calibration/holdout names do not make them unseen data.

Ignored complete report files and independently computed SHA-256 values:

| File under `service/research/runs/` | SHA-256 |
|---|---|
| `paired-x3d-cuda-v1.json` | `f60454cc87c6166067339195b040b50f262df1d4c9191f6586f4e474808e9275` |
| `paired-mc3-cuda-v1.json` | `6d35587a099b21bec8a58c4996c462bd5431c04c736a56660af6fb003f30ff78` |
| `paired-videomae-cuda-v1.json` | `0552adfc722c30761f67165cf258341cdb62e60cda5cee0f06af5056bd4416c5` |

Commands and detailed protocol: [PAIRED-DIAGNOSTIC.md](PAIRED-DIAGNOSTIC.md).
Pinned assets and rights/provenance gaps remain in the [transformer audit](transformer-repos.md)
and [3D-CNN audit](3d-cnn-repos.md). This experiment does not clear public or
commercial redistribution of any checkpoint.

## Remaining work and limits

No measured result establishes 50-100 visible people, genuine near-IR,
low-light colour, camera-hour false-alert rates, interaction localization or
sustained camera capacity. Native HD input alone does not establish those
conditions. Fixed resolution/compression derivatives remain a sensitivity
experiment, not independent real-camera evidence.

The earlier own-model training attempt started from generic Kinetics weights and
failed transfer diagnostics despite fitting VID training data. The next bounded
training hypothesis is to retain the working fight-tuned representation and adapt
its head conservatively, preserving the exact baseline activation/pooling path.
That is an experiment to implement and run, not a promised improvement. VID
remains training-only with provisional annotations and unresolved session groups.

Parent verification before these runs: focused suites **124 passed, 1 skipped**.
Full service suite after implementation: **420 passed, 4 skipped**, with one
existing Starlette/AnyIO deprecation warning. Skips are platform/opt-in checks;
real CUDA inference for these three candidates was separately executed above.
