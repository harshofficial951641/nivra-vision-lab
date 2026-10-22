# Independent bounded audit of the completed round-three V2 run

21 October 2026. **No blocking artifact, source-pin, provenance, runtime, state or training-accounting finding was found.** The completed run is internally consistent with the independently audited fixed head-only trainer and admitted manifest. This does not establish better detection, a useful decision threshold, unseen transfer or deployment readiness.

Audited run: `service/training/runs/community-head-nll-v2-round3-e20`. Only this assigned report was written. No architecture/model constructor, model forward, inference, fitting, CUDA work, scoring report, service mutation or package installation was performed. This was a CPU restricted-state/hash inspection, not a replay of training.

## Actual artifacts and milestone identities

| Milestone | Optimizer steps | Microbatches | Recorded epoch weighted NLL |
| --- | ---: | ---: | ---: |
| Epoch 3 | 63 | 489 | 0.4678831399204472 |
| Epoch 10 | 210 | 1,630 | 0.42240541053587005 |
| Epoch 20 | 420 | 3,260 | 0.37026026145932894 |

The frozen manifest has **127 recordings / 163 train windows: 91 positive and 72 normal**. All three artifacts contain the same exact train summary/window identity list, one VID unresolved session cohort, no calibration and no holdout. Window identity SHA-256 is `4e22887fcec5dfeeaae1b463939244c519f5e1e1a2f5286c6fc305aebad1611f`.

There are 21 optimizer groups per epoch: 20 groups of eight plus a final three-window tail. Counts equal `E * ceil(163/8)` and `E * 163`. Recorded class counts are `[72,91]`, weights `[1.1319444179534912,0.8956044316291809]`. The fixed profile is seed 17, AdamW LR 1e-5, weight decay .01, FP32, microbatch one, accumulation eight, weighted NLL of retained clamped probabilities, CUDA allocator fraction .35 and yielding enabled. No scheduler, early stopping, diagnostic selection or threshold fitting is declared.

Epoch 3 and epoch 10 loss histories are exact prefixes of epoch 20's 20-entry history. First recorded loss is 0.4824486335155249; last is 0.37026026145932894. All are finite. The audited source creates one optimizer and shuffle generator outside the epoch loop; exports do not restart either. Source, prefix histories and step counts support the declared continuous trajectory. Checkpoints do not preserve the optimizer/RNG state or per-step gradients, so these artifacts alone cannot independently replay or prove every historical optimizer operation.

The loss is an online aggregate of training microbatches as updates occur, not a separate end-of-epoch evaluation. **Lower training NLL is not training accuracy, diagnostic accuracy, calibration or improved detection.**

| Artifact relative to run | SHA-256 |
| --- | --- |
| complete.json | `0584dec4936ea5c7b1461974985adbf405b8825eb633b037ac4f8ef1e3e7c509` |
| started.json | `9c8160436a12ea75048c0cb37d6380897f36a8f7a181cf9c887313666a5509a0` |
| epoch-003/report.json | `facf5a5b6464725cbe0d69bcc185b56e8c86fbd978d39b3ce3b48bc368af0371` |
| epoch-003/candidate-state.pt | `0c8176ddc62d9a02d02ec1ecef33610f00d4775df14bf25247204bfb4cb68abb` |
| epoch-010/report.json | `f8b737ea9edcef8747532d33de0b37eb654b5cf4e1c7579e4a813a9ef6bd5189` |
| epoch-010/candidate-state.pt | `0cdcd2665b0c5101ad64f79320b83a4a30aab79471b78ed4c9ef50ec071fb64c` |
| epoch-020/report.json | `4cda52975126f4e00887cf58f9527db55c6cbfdcd1386b1c444daaa8fb668319` |
| epoch-020/candidate-state.pt | `7c58a0f2e6ffc63ebdc4ab2df7b15882d90c3a14e0bc892f55f4e2760471e30f` |
| manifest.json | `68cf0c4048dcc9d4d10e5553bf5bcf9be6cd6ab36bd7aeaff23208f2b55e0970` |
| runtime/environment.json | `d65731293e856554dc5c4240db546fecb97cab2b93116c239ad78dda5f2dfe30` |

## Frozen state independently checked against the actual baseline

The baseline checkpoint's actual SHA-256 was verified before deserialization:

`e833f69d110f167cad4a6c38d385564bdb2f6de63d246e45cb03ff9aa17f0349`.

It was loaded on CPU with `weights_only=True` and only the audited NumPy scalar/dtype safe globals required by this pinned checkpoint, using no architecture construction. The `backbone.` key prefix was removed as in the audited loader. Each candidate was loaded on CPU through `validate_artifact`, which uses restricted deserialization, validates tensor contracts and performs no model construction.

Each state contains **563 entries**. For all three milestones:

- All **561 non-head entries** are exactly tensor-equal to the actual pinned baseline, not merely equal to self-reported hashes. This includes BN running buffers/counters. Every stored `initialNonHeadHashes` map also equals independently computed baseline hashes.
- Only `blocks.5.proj.1.weight` and `blocks.5.proj.1.bias` are declared trainable. Their shapes are `[2,2048]` and `[2]`, totaling **4,098 scalar parameters**. Both changed from baseline and both change between the successive saved milestones.
- All candidate tensors are CPU-resident, finite and satisfy the full key/shape/dtype contract. Declared non-head hashes, actual baseline state and all milestone state agree.

| Epoch | Head weight L2 change from baseline | Head bias L2 change from baseline |
| --- | ---: | ---: |
| 3 | 0.014107751660048962 | 0.0003024019824806601 |
| 10 | 0.0468498133122921 | 0.0010713683441281319 |
| 20 | 0.09061668068170547 | 0.0019495596643537283 |

These differences establish saved head updates, not meaningful learning or better behavior. This is **head-only adaptation of a frozen representation**, not backbone representation learning. Artifact state cannot prove every transient historical module flag; the pinned source and previously executed synthetic regressions enforce whole-model eval, exact trainable scope and frozen hashes at epoch boundaries. BN/Dropout mode itself is not serialized as a state tensor.

## Seal, snapshots, runtime and provenance

Root `complete.json` is complete, identifies exactly epochs 3/10/20, binds the root started receipt and all sibling report/checkpoint hashes, and has no `failed.json` marker. Its SHA stayed unchanged across this audit. All three milestone validators passed without constructing a model. No sibling was missing or substituted; actual export epoch/directory names and cumulative counts agree.

The run preserves **53 snapshot files per copy**: 8 source files, 23 provenance files, 20 dependency files, one runtime JSON and one manifest. This audit explicitly hashed all 53 files in the root and in **each** of the three milestone directories: **212/212 snapshot hash checks passed**. This extends beyond checking just the selected milestone's provenance. All paths stayed confined to their expected directories.

The snapshot-hash mapping itself, serialized using `json.dumps(mapping, sort_keys=True, separators=(',', ':')).encode()`, has SHA-256:

`5776b80018b566cd71711dc4494182579d2205d4118d0dc85a78951cfb1fce12`.

Runtime JSON, started receipt, all milestone reports/artifacts and final seal agree. Recorded actual environment is CPython 3.11.15 on Windows AMD64, Torch 2.5.1+cu124 with git version `a8d6afb511a69687bbb2b7e88a3cf67917e1697e`, compiled CUDA 12.4, linked cuDNN 90100, NumPy 1.26.4, OpenCV module 4.11.0/package 4.11.0.86 and PytorchVideo 0.1.5. Device/driver probing is explicitly false in this metadata. This audit did not query a device or driver.

All required service requirements/lock and selected installed Torch/PytorchVideo/fvcore source copies are present and hashed. `validate_installed_dependencies` passed for each selected milestone against the current local installed package versions and selected source hashes, before any model construction could occur. This closes the earlier missing-runtime-provenance finding for this actual run. It remains selected-source/build evidence, not complete transitive/binary supply-chain attestation or deterministic cross-device execution proof.

The eight preserved training sources match both current source bytes and the independently reviewed pins:

| Snapshot filename under source/ | SHA-256 |
| --- | --- |
| community_x3d_experiments.py | `d593b45b3e5985d7c15c24311c9c3646d908b4bdaf6c84a31fcd49486638fdc4` |
| train_community_experiments.py | `f233e7e2be03040dd7dc81eabda1fcb23e1f1672c137ed7235fabb5654ff4811` |
| community_x3d_training.py | `dcc907543f44173a4ffeab4559643c3a09f97f3a1d741a133f04913bae888694` |
| train_community_x3d.py | `f38ab9a7953b4fb8f47acf88a285a12a0f7c5dc31afe997175c415bf289ab806` |
| training_data.py | `a2df7795345838f7c890e0f2bbd4335f66e21b10981acb055bfa647bef940239` |
| x3d_training.py | `99d13e5d1e13f774ea09ea50b4071b11702bd38a8514d05d8c87d20a04218831` |
| x3d_finetune.py | `18aeb3877df98dc86de57ed0e502bc025c851f550ee427489a706d7ddf6f8569` |
| x3d_candidate.py | `65798e408dbc85231b976187401850a9909eb899235f0eea7f5f4ac09fdabee4` |

Canonical review SHA is `52dff3653829d64433795a7f4b9b0e58b5600957102f92ea5def8b35c7652a63`. Its copy is present, and **all ten `inputHashes` have exactly one matching preserved provenance file**, including original accepted reviews, new reviews, the legacy normal re-review, positive coverage audit and old manifest. Every preserved provenance file also matched its corresponding current source file. The frozen plans, data-rights/source records, canonical assembly script, admission receipt, prior independent audits and preflight/parity receipts are included. Actual provenance filename/identity mapping is preserved in sealed `started.json`; this audit did not rely solely on similar basenames.

The run is not an entirely self-contained media archive. The original 517 contact-sheet/JSON evidence files and training media remain external and ignored; source review JSON retains their paths. Inventory content and `build_training_manifest.py` are not separate snapshot payloads in this run, although the admission receipts/reports preserve their SHA values and the exact generated manifest is included. These are archival scope limits, not a failed artifact check or a new label change. Full future reassembly/re-review requires retaining those external bytes. Do not describe 53 snapshot files as every data-preparation dependency.

## Stored parent preflight receipts

The strict actual-PTS decode receipt was inspected as inert data and matched its snapshotted/current bytes:

`8c20810f6e4e230677d46e4e30ed2137ad419ad5a5e15442c1d1d4ea8644cbde`.

It has 163 rows matching every generated `(recording ID,start,end)` tuple in order. Their decoded-frame counts sum to **19,661**, every row reports no FPS fallback, and recorded sampled spans are at least 3.8 seconds. Manifest and reader source hashes agree with this run. This verifies receipt consistency; this audit did not rerun 163 decodes or certify capture-clock fidelity or visual labels. The full standalone implementation of the parent's strict preflight is not included as a separate run source snapshot, so the receipt cannot alone independently demonstrate its execution history.

The real-CUDA zero-step parity receipt hash is:

`0e920e70010056b3a810eda0d46c80d7bf189b3d8744eab90a36cee7a3499388`.

Its included verifier source hash is `4cc4bcee761388227af72d2bde73d0a7ad07a052500db5ad2aaf3129ce20c9a6`. The verifier was read, never executed. It compares the current control adapter against the pinned candidate forward with the existing head enabled but no optimizer. Three development windows report maximum absolute difference **0** with tolerance 1e-6; receipt source/manifest/corpus/script hashes match their actual bytes. The receipt declares no training or live change. Per-class scores were not used for selection, training or accuracy conclusions in this audit, and no later development-scoring reports were opened.

These are limited zero-update forward checks, not trained CPU/GPU reload parity, independent event recall, true four-second annotation coverage or general graph equivalence over all inputs. This audit independently loaded trained states safely but did not execute them; trained forward/reload parity and development transfer remain parent empirical work.

## Recorded resource measurements and limits

The seal records **369.34610299998894 seconds** elapsed, process Torch peak allocated **192.63427734375 MiB**, reserved **240 MiB**, and decoded CPU frame cache resident **930.0908203125 MiB** within a 1,536 MiB cache budget. Cache counts are consistent with 20 epochs over 163 windows: 163 initial misses, 3,097 hits, 163 entries, zero evictions/oversize reads. These are preserved parent-run measurements, not measurements independently repeated by this CPU audit.

GPU allocator peaks exclude the live service, driver and decoder; CPU frame-cache residency is not total process RAM. Demo yielding is cooperative, not an exclusive GPU lock. No end-to-end latency, live-service continuity or total free VRAM conclusion follows from these fields.

## Checks, boundaries and disposition

The existing `service/.venv/Scripts/python.exe` was used with bytecode disabled, CUDA opt-in disabled, CUDA devices hidden, OpenCV one thread and Torch one thread. Guard closures raised on CUDA initialization/availability/device/memory/synchronization APIs. `torch.hub.load`, the PytorchVideo hub constructor and baseline/architecture constructor entry points were replaced by failing sentinels. All candidate state loads used `weights_only=True,map_location='cpu'`; the pinned baseline used the audited restricted NumPy safe-global exception. No model object was constructed, no tensor was moved to CUDA, and no forward/optimizer was run.

Executed checks: three actual artifact validators, three local dependency checks, 212 snapshot hashes, all sibling report/checkpoint hashes, current source/provenance identity checks, baseline checksum plus **1,683 exact non-head tensor comparisons**, six saved head-change comparisons, loss-prefix/count/window-contract checks, all ten canonical provenance links and preflight/parity receipt identity/accounting. Assertions passed. The broader synthetic trainer tests were already completed in `INDEPENDENT-V2-AUDIT.md`; they were not rerun just to inflate this artifact audit's coverage.

The data uncertainty remains unchanged: 27 old sampled positives contribute 45 windows, five disagreements remain quarantined, seven supported old positives use proposed audit events, and all 72 normal windows are only explicit 0–4 spans. These sources remain one training cohort, with provisional assistant still-image labels, unknown actor/session lineage, unknown tails, copyright/consent distinctions and unresolved checkpoint terms. Nothing here adds an independent holdout, human ground truth, new sensor modality or crowd evidence.

The completed artifacts are structurally suitable for the parent's predeclared **development-only comparison** under the existing research restrictions. No candidate is recommended for promotion by this report. Head updates, lower training loss, a successful loader and three zero-step parity examples do not establish fewer misses or fewer false alerts. Real near-IR, low-light colour, low-quality CCTV and 50–100-person coverage remain empirical gaps unless separately demonstrated with appropriate independent footage and complete alert-policy evaluation.
