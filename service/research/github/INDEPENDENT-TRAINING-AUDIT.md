# Independent training and evaluation audit

21 October 2026. Scope: immutable `service/training/runs/community-head-nll-v1/source/`, its manifest/rights copies, corresponding current implementation, focused CPU synthetic/stub tests, and the expanded evaluation policy. **No model scores or prediction reports were opened.** No real X3D construction, checkpoint loading from the pilot, CUDA, training job, detector inference, service operation or code fix was performed. Tiny synthetic networks in the authorized unit tests ran CPU math only. The only repository output written by this helper is this report.

## Actionable findings, in severity order

### P1 — Frozen pilot normal labels include automatically filled, incompletely inspected time

**Affected data remain unresolved; builder fix independently verified.** The builder initially inspected at SHA256 `c2201a8230681a1cbd80bd81468c004863a8c7149f9099332fb7022a9c990e05`, `service/build_training_manifest.py:48-49`, supplied `[0, durationSeconds]` whenever an accepted normal review omitted `events`. It then marked the record reviewed at line 55. A sparse visual decision therefore became a full-duration temporal annotation without explicit reviewed boundaries.

The immutable pilot manifest SHA256 `1a0f6fc44704b73f32c5e0ab82b607fff2a702a848186b4403ddf357a0026a84` includes **26 such records generating 60 of its 91 normal windows**. Their legacy review methods state 16 sampled frames, not exhaustive frame inspection or playback. The auto-filled intervals total **186.5854709113521 source seconds**; the 60 window rows sum to 240 window-seconds because end-aligned windows overlap. Neither number is independently verified normal exposure.

The current parent-fixed [builder](../../build_training_manifest.py:48), SHA256 `a95afe1c191942fac23fe55b0f1d3bce965943c0824dde5dfe13308355604365`, now rejects accepted positive **and** normal records lacking explicit `events`; it no longer fills from duration. Updated [tests](../../tests/test_build_training_manifest.py:67) and the [CLI no-publish regression](../../tests/test_build_training_manifest.py:158) passed independently: **31 passed**. This closes future implicit filling, **not** the old data-quality gap, and an explicit interval still does not establish continuous visual coverage by itself.

**Action:** preserve the old manifest and pilot as legacy sampled-label experimental evidence. Re-review the 40 less-covered normal source recordings before the larger run: 28 legacy sources plus 12 expanded sources. Record new evidence/intervals as a new annotation version and create a new hashed manifest/experiment. Re-review does not add independent recordings or create a holdout. Do not relabel this pilot as fully covered-normal training, or describe its label-0 intervals as verified camera-hour exposure. Parent received an immediate `threads_send` alert and acknowledged/fixed the builder; this helper changed no code, reviews, manifest or receipt.

### P2 — Existing event scorer is unsuitable for the new locked-audit matching and normal-exposure metrics

[`service/evaluate.py:35-49`](../../evaluate.py:35), SHA256 `6abd7bf3aeeddf9db6bc507c26bb3b206a547b8a12000fb9da61ad1f356f9772`, matches any unused prediction through **truth end + 3,000 ms**, without action/episode compatibility. It reports all unmatched predictions as `falseAlerts` and total clip duration as `minutes`; its schema has no explicit normal/unknown intervals. Consequently it cannot distinguish an unknown-time alert from an alert inside continuously annotated normal time.

Two model-free synthetic calls reproduced the boundary:

- Truth `[1000,2000]` ms and a prediction at `4000` ms: **1 detected, 0 missed**, despite no evidence associating that later alert with the annotated episode. The scorer cannot stop a later distinct action from receiving credit for an earlier one.
- Same truth and a prediction at `9000` ms: **1 false alert**, although no normal interval was supplied for that time. Returned exposure is the full ten-second clip.

These are defects **if this historical scorer is used for the new final audit**, not evidence that historical source clips have different labels. Its current tests cover one-prediction/one-event use, very late alerts and split leakage, but not event-compatible matching or unknown-time abstention. [`benchmark_cctv_candidates.py:546-612`](../../benchmark_cctv_candidates.py:546) is more candid: its `review` field is a `fightScore > .5` decision, and limitations explicitly say window overlaps are not incident recall. It still does not implement the new normal-exposure/event-audit contract.

**Action:** keep these runners development/diagnostic-only. Before a locked audit, supply an explicit scorer contract for episode compatibility, tolerance, duplicate/cooldown accounting and normal-time classification. Unmatched alerts in unknown time must remain unknown, not false positives or normal exposure. Do not derive operational false alerts/hour from the existing `minutes` field.

### P2 — Immutable run omits exact review files and the builder, limiting annotation reproducibility

[`community_x3d_training.py:220-232`](../../nivra/community_x3d_training.py:220), SHA256 `dcc907543f44173a4ffeab4559643c3a09f97f3a1d741a133f04913bae888694`, snapshots six trainer/dependency files and rights evidence. The CLI adds historical documents and the parent supplied a parity receipt, but the inspected run contains **none of the eight review JSON files and no `build_training_manifest.py` snapshot**. The manifest bytes are frozen, so this does not invalidate their checksum or the trainer's consumed labels. It means the run alone cannot recover the originating review decisions/methods and builder behavior. This matters especially because the builder changed during this audit and the corrected builder intentionally cannot recreate the old implicit labels.

**Action:** future receipts should copy/hash each input inventory, review JSON, annotation/evidence index, exact builder and role-assignment implementation alongside the emitted manifest. Preserve original versus superseding versions and methods; do not overwrite this run. The review hashes captured below document what was inspected now, not proof those bytes were the versions loaded when the pilot manifest was built.

**No additional material gradient, weighted-NLL tail-normalization, head-scope, Softmax-order or unsafe-pickle-loading bug was found within the bounded source/stub review.** This is not an independent validation of real X3D outputs, GPU execution, label truth or deployment readiness.

## Snapshot versus current source identity

All six current corresponding files matched the immutable source copies byte-for-byte at initial and final checks. The audit therefore applies to the pilot implementation and the current trainer, while the builder fix is a separate current change. Paths below are relative to `service/`; each source exists both in `training/runs/community-head-nll-v1/source/<basename>` and at the current path shown.

| Current source | Snapshot = current SHA256 |
|---|---|
| `nivra/community_x3d_training.py` | `dcc907543f44173a4ffeab4559643c3a09f97f3a1d741a133f04913bae888694` |
| `train_community_x3d.py` | `f38ab9a7953b4fb8f47acf88a285a12a0f7c5dc31afe997175c415bf289ab806` |
| `nivra/training_data.py` | `a2df7795345838f7c890e0f2bbd4335f66e21b10981acb055bfa647bef940239` |
| `nivra/x3d_training.py` | `99d13e5d1e13f774ea09ea50b4071b11702bd38a8514d05d8c87d20a04218831` |
| `nivra/x3d_finetune.py` | `18aeb3877df98dc86de57ed0e502bc025c851f550ee427489a706d7ddf6f8569` |
| `nivra/x3d_candidate.py` | `65798e408dbc85231b976187401850a9909eb899235f0eea7f5f4ac09fdabee4` |

Additional audited pins:

| File, relative to `service/` | SHA256 |
|---|---|
| `training/runs/community-head-nll-v1/manifest.json` | `1a0f6fc44704b73f32c5e0ab82b607fff2a702a848186b4403ddf357a0026a84` |
| `training/runs/community-head-nll-v1/provenance/vid-source.json` | `a85815cbdae9009ed36a2dc6aa4327da6fbac38d91d0d449bae39e6247eeb869` |
| `training/runs/community-head-nll-v1/provenance/DATA-RIGHTS.md` | `13c4ed71d7d966b0e16bc912dd65156a084d117f76402a94c971797244023bec` |
| `research/github/TRAINING-AND-TESTING-PLAN.md` | `0066d48160465b545d58b299fa58cf2049571541e50d81de52198b45bf9582e1` |
| `research/github/PROTOCOL.md` | `10e406f8487cdc4ed9fab22e0f98ba3f45e5f59497c8ac57aae6710174ca35b6` |
| `benchmark_cctv_candidates.py` | `304c62a00ebffebc9e9f4bafb22346355a272dcc18f76cb5fb61e1215962c1e9` |
| `tests/test_community_x3d_training.py` | `7cd0163c9ce1d1d62abb10896ce7b952fe0ea755d771926237bb4d7d920cd308` |
| `tests/test_training_data.py` | `1e8564eae31c36e009148e146c395e349d12e60f6685f15c9b4b66e8a1de7d3d` |
| `tests/test_x3d_training.py` | `07f0a9bdbfaee3a439a32b3318bafd905b7f33572b100a6aa119aba379f9d934` |
| `tests/test_evaluation.py` | `296f1f2a9225815b37ebea43083e07f36086db6db5730f773505275abfe46712` |
| `tests/test_build_training_manifest.py`, before parent fix | `c8762676ff88c40e740627a6493a8c2acfdd88acb5542a3ac25ae16f354330a5` |
| `tests/test_build_training_manifest.py`, after parent fix | `b594fd4e4ec63e1f9c66edba9d5529cbb8641eb0092f537f08fd7971d32b9758` |
| `.venv/Lib/site-packages/pytorchvideo/models/head.py`, source read only | `79e526f8c6e8f0fb4de7c808ce1f30e7f08b0fecc4d823f33338408c15e0be52` |
| `.venv/Lib/site-packages/pytorchvideo/models/x3d.py`, source read only | `564d7e92e0b810edabfc04fa4fb937cc16179754fd128a65993b87ae694f7158` |

Other immutable provenance files were hashed but their model-result content was **not read**: `00-ROUND2-RESULTS.md` → `ef5dea55f79af158a71836c671be32652ce6336875c383a9e3aae28d692dbae1`; `01-PAIRED-RESULTS.md` → `bf0d29b764d3e1f677774b002cbe211ec1bc223e9b8dda7c8ee5d5ff97de9884`; `02-3d-cnn-repos.md` → `dbb582f79358567ef5cc5818bb95d9b885979059aaa28c2816a9f38363f97901`; `03-community-zero-step-parity-v1.json` → `96bcf745b95105b0119e27974afee1a2c989e6ff2763f2dadbbbef76c26f9724`. A receipt's existence/hash is not this helper independently reproducing parity.

## Trainer, loader and timestamp review

**Retained architecture:** [`community_x3d_training.py:66-100`](../../nivra/community_x3d_training.py:66) constructs installed `pytorchvideo==0.1.5`, `pretrained=False`, restores the existing binary projection and strictly loads the checksum-pinned community baseline. `enable_head_only` requires the 2048→2 existing Linear, expected parameter names, Softmax(dim=1), output pool, and every module in eval. Only the two Linear tensors receive gradients. Installed source `head.py:371-391` confirms projection → activation → output averaging; `x3d.py:514-533` supplies class-dimension Softmax and adaptive average output pooling. No real constructor was called during this audit.

**Loss and tail:** [`fit:150-184`](../../nivra/community_x3d_training.py:150) computes class weights `N/(2*n_c)` and sums weighted NLL of retained probabilities. For accumulation group G, its objective is `sum_i(w_yi * -log(max(p_yi,1e-7))) / sum_i(w_yi)`. Division uses the **actual group's target-weight sum**, including its final partial group, not a fixed eight or per-singleton weighted mean. With 156 windows there are 20 optimizer steps/epoch, 60 total over three epochs. The imbalanced 11-example test has an eight-example group and three-example tail and matches a true batched weighted-NLL reference. No double Softmax or cross-entropy on post-pool probabilities occurs.

**Freeze scope:** eval mode disables both dropout sites and BN running-stat updates; `.requires_grad_(False)` freezes BN affine/prefix/projection-pool parameters. Full non-head state, including BN buffers, is hashed and rechecked each epoch. This correctly leaves autograd enabled through the final Linear; eval is not `no_grad`. The predeclared model intentionally uses deterministic eval dropout behavior during head adaptation. Clamp-below-epsilon zero gradients are explicitly disclosed; actual frequency/saturation on real media is unmeasured here.

**Safe loading:** [`baseline_model:76-84`](../../nivra/community_x3d_training.py:76) hashes before CPU `weights_only=True` load and allowlists numeric NumPy metadata only; strict state loading follows. [`validate_artifact:317-397`](../../nivra/community_x3d_training.py:317) checks artifact/snapshot hashes and contained paths, pinned manifest/counts, fixed settings, report/state consistency, tensor keys/shapes/dtypes/finiteness and frozen-tensor hashes before architecture construction. [`load_candidate:400-414`](../../nivra/community_x3d_training.py:400) checks the actual constructed state contract and disables all gradients for later diagnostics. Synthetic tests exercise checksum/tensor/threshold/config/selection corruption and pre-construction failure. They do not establish trusted real baseline equivalence: frozen hashes are relative to the run-recorded initial state, not a separately reconstructed baseline in this audit. Local checksums are integrity evidence, not external signatures.

**Source-time windows:** [`training_data.py:235-307`](../../nivra/training_data.py:235) unions same-label intervals (no double counting), requires positive coverage ≥50%, requires complete explicit normal coverage, rejects contradictory overlaps, omits clips <4 s and appends a full end-aligned window when needed. That last window can overlap another, so counts are dependent. This validates declared annotations, not how much was visually inspected.

[`x3d_training.py:103-146`](../../nivra/x3d_training.py:103) decodes one bounded window, uses source timestamp seeking, rejects invalid FPS, non-increasing time, >1,200 ms gaps and frame-budget overflow, and requires ≥8 observed frames spanning ≥3,800 ms. It downsamples near 100 ms and preprocessing selects 16 linspace-floor samples, BGR→RGB, square 224², `(x/255-.45)/.225`. No short-clip padding is introduced. Fallback `(frame_position-1)/FPS` is nominal timing, **not verified true presentation timestamps for VFR/problematic decoders**. Training receipts store declared windows, not the exact per-frame PTS returned by this reader; actual timing/seek fidelity across all source media was not independently checked. The 1,200 ms tolerance is a gap bound, not proof every intervening visual moment was observed.

## Exact data and coverage distinctions

Inert manifest validation/window generation independently reproduced **96 recordings, 156 windows: 65 positive, 91 normal, all train-only**, 96 distinct declared media hashes, exactly one `vid-v2-unresolved-session-cohort`. `validate_vid_cohort` at [`x3d_finetune.py:302-310`](../../nivra/x3d_finetune.py:302) enforces that cohort for recognized VID sources, and the fixed trainer additionally pins manifest SHA/counts/source licence. No random VID calibration/holdout was invented. Media SHA values were read from the frozen manifest; the 96 raw files were **not rehashed or visually re-reviewed in this audit**.

| Normal evidence category | Recordings | Training windows | Meaning |
|---|---:|---:|---|
| Legacy `negative-review.json` | 17 | 41 | 16 sampled frames; all 17 omitted explicit events, builder filled full duration |
| Legacy `campus-negative-review.json`, implicit | 9 | 19 | 16-frame + overview screening; omitted explicit events, filled full duration |
| Legacy campus explicit spans (`nv_b_24`, `nv_b_87`) | 2 | 2 | Explicit early `[0,7]` and `[0,5.5]` seconds; sampled visual coverage, not exhaustive frame inspection |
| `negative-round2-expanded.json` | 12 | 12 | Explicit `[0,4]`; 32 dense samples after sequential decoding, **not all decoded frames inspected** |
| `negative-round2-existing.json` | 17 | 17 | Explicit `[0,4]`; every-source-frame contact-sheet review as recorded in evidence, still provisional assistant review |
| **Total** | **57** | **91** | **40 sources need coverage re-review; 17 have the stronger recorded method** |

Sparse/dense samples, every-frame static contact sheets and continuous motion playback are different methods. This audit verified their recorded descriptions and manifest contributions, **not the images or the correctness of any action label**. Do not turn the 57 normal record labels into exhaustively inspected full clips. The 39 positive recordings remain sampled-contact provisional annotations with unknown margins; their 65 eligible windows are not 65 independent fights.

Review JSON hashes inspected now, relative to `service/training/`:

| Review | SHA256 |
|---|---|
| `negative-review.json` | `ff4391b7c14373c249d585ecd1a103f575e261a73b8d651ec3ce38ab1b68d63f` |
| `campus-negative-review.json` | `77f4b14c5da40d1097862527d461a973c23a1bbe5ec52e554c2cfd9beaad1010` |
| `positive-review.json` | `9cfd13947a0449c527de29e6bc04f6c4a1d0cc31245be9eba6476ac7834c4640` |
| `reviews/negative-round2-existing.json` | `8766e4ef4816dd0f941fcd86a53c3a706fe7326be113880b9129ff49a62b48c5` |
| `reviews/negative-round2-expanded.json` | `cb33bc794e6c4fb414e2ea7d7c67ae920289a630251b879c3107385e1befd90c` |
| `reviews/positive-round2-a.json` | `0eccf1faf3fe74f4b34a4372135f673ef0ed1be7e7fbaf0a43a9b3acd5efeddb` |
| `reviews/positive-round2-b.json` | `5f2972ad8855e712a0ac0fbf5378b1b37a521344d920af9b546d5444a764c5c6` |
| `reviews/positive-round2-c.json` | `42ef7f42dced4871d77ecfcb33b52d3c7324624fc93a73fcb9c7bbb4e2bbbc1e` |

Rights copies distinguish dataset CC0 copyright from author-reported consent and unresolved non-copyright rights, and acknowledge the community checkpoint's conflicting licence/card wording. The manifest's `trainingAllowed=True` is an experimental eligibility decision, not independent releases, commercial clearance or deployment authorization. No external licence status was re-researched here.

## New online development/audit rule: verified definition, admission still required

The [plan lines 44-57](TRAINING-AND-TESTING-PLAN.md:44) correctly specifies exact UTF-8 bytes of `nivra-online-wave1-v1:` followed by the frozen `sourceGroup`, SHA256 digest **first byte**, `<128` development, otherwise reserved audit. It must not use the first hex character as a decimal byte, take modulo twice, change group names, or retry names until a preferred role appears.

Independent test-only golden vectors (not real sources):

| Exact synthetic sourceGroup | First digest byte | Assigned role |
|---|---:|---|
| `author-alpha/session-1` | 65 | development |
| `author-epsilon/session-1` | 189 | reserved-audit |

The hash assignment is reproducible, **not proof of independence or balanced classes**. Grouping precedes hashing: combine same-event uploads, derivatives, crops and compression variants, plus common author/session material where actor/session independence remains unknown. Resolve connected lineage relationships conservatively before role assignment; do not let two guessed session names partition an unknown shared author cohort. Save source URL, upload/author metadata, original/derivative hashes, group reasoning and exact assigned byte. Recompute roles mechanically at admission.

At the inspected boundary, this role rule appears in the plan, but **no end-to-end enforcement of that role definition was found in the reviewed trainer/schema/evaluation paths**. The trainer accepts only its fixed VID train manifest; the old evaluator knows calibration/holdout, and the diagnostic runner uses historical splits. A field named holdout is not sufficient evidence of the new reserved-audit role. New online helper outputs/admission were not completed/verified by this audit; do not imply a locked independent corpus already exists.

## Focused tests and what they prove

Successful guarded CPU batch: **124 passed, 1 skipped in 9.87 s**. Files: `test_community_x3d_training.py`, `test_training_data.py`, pre-fix `test_build_training_manifest.py`, `test_evaluation.py`, plus three targeted preprocessing/decoder tests from `test_x3d_training.py`. The skip was Windows symlink creation permission. Separate post-fix builder batch: **31 passed in 0.37 s**, at the new source/test hashes above. These batches overlap; do not sum them into a unique test count.

Execution used `service/.venv/Scripts/python.exe`, `pytest.main` with `-q --tb=short -p no:cacheprovider`, bytecode disabled, `NIVRA_RUN_CUDA_TRAINING_TEST=0`, `CUDA_VISIBLE_DEVICES=''`; CUDA availability was stubbed false, execution/initialization/allocator functions guarded, real `pytorchvideo.models.hub.x3d_m` and `torch.hub.load` blocked, `cv2.setNumThreads(1)`. Synthetic decoder test uses one local MJPG capture, not dataset media. Temporary pytest fixtures were outside the repository; no cache, test or source file was added here.

Two earlier **audit-harness failures**, not repository regressions, are preserved in this accounting: first 12 failed / 80 passed / 1 skipped because CPU AdamW legitimately checked the guard on `cuda.is_available`; second 12 failed / 84 passed / 1 skipped because assigning one identical forbidden function to multiple CUDA APIs confused Torch Dynamo's object-rule registry. Unique guard closures and false availability corrected the harness. The successful batch above is the final trainer result, and it never reached a real CUDA or X3D constructor.

Meaningful coverage includes an explicit counterexample to swapping average/Softmax order, state equality before zero-update enablement, frozen BN/dropout and non-head mutation detection, imbalanced weighted accumulation with a partial tail against batched reference, fixed-seed repeatability, nontrain rejection before decode, rights/media/manifest rejection before construction, safe synthetic artifact round-trip, tamper checks and overwrite prevention. The original builder tests also demonstrated their **blind spot**: normal fixtures omitted intervals and accepted fallback behavior. Parent's new regressions now reject that path.

Remaining meaningful test gaps: saturated/clamped probabilities and zero/effectively-zero gradients; malformed probability shapes/NaNs; varied tail sizes/class compositions; decoder nominal-time fallback/VFR/start offsets; actual installed X3D parity; mixed-dtype/full real checkpoint safe-load compatibility; real GPU deterministic-backward warnings; and new role/normal-exposure/event-compatible scorer admission. Do not infer model transfer from tiny networks or manufacture accuracy from passing synthetic fixtures.

## Final locked-audit admission checks

1. **Freeze lineage and role before predictions.** Original media bytes/hash, author/upload/session evidence, duplicate/derivative graph and conservative sourceGroup are fixed; recomputed salted role matches. Training, model-selection development and reserved audit source groups/derivatives are disjoint. VID and all existing four-source diagnostics stay training/development, never the new independent audit. Unknown pretrained overlap remains disclosed.
2. **Freeze model-blind annotation evidence.** Exact event/episode IDs and source-time spans, explicit normal intervals and unknown gaps, inspection method/actual timestamp coverage, uncertainty, rights and attribution are immutable and hashed. No classifier output selected or resolved a label. Do not treat an events-empty clip as fully normal. Full normal intervals require the stated complete visual coverage; tails/gaps stay unknown. Sport/staged contact is tagged proxy rather than hostile-intent ground truth.
3. **Freeze one selected model and policy.** Candidate/baseline bytes and loader/preprocessing/source hashes; sample times; strict threshold semantics; smoothing, region scheduling, confirmation and cooldown; matching tolerance and event-compatible one-to-one rules are fixed after development. Avoid crediting a later separate kick for an earlier takedown. Decide duplicate-alert and cooldown-suppressed event accounting before scoring. No threshold, epoch, subset or group-name selection from reserved results.
4. **Compute the correct denominators.** Normal exposure is the union of eligible explicitly inspected normal intervals on original sources, minus unknown/positive intervals and declared matching/grace zones; do not sum overlapping windows, crops or codec variants as independent camera hours. Require continuous pipeline state/warmup/cooldown handling across the scored exposure. Report normal-time false episodes/hour with the exact deduplication policy, source/group counts and exposure; unknown alerts and duplicate alerts separately. Zero false alerts over short exposure is not a low operational rate. If an approximate Poisson upper bound is used, disclose its assumptions (`~3/T_hours` at 95% for zero events), not an unsupported guarantee.
5. **Require representative strata or mark gaps.** Real 50–100 visible people, person pixel height/occlusion, native 1080p/720p and degraded 480p separately, codec/compression/FPS, sensor-verified near-IR versus real low-light colour versus thermal. Synthetic tiled crowds/darkening/grayscale only test load/sensitivity. Measure proposal/person omissions, stale/dropped regions, classifier cost, end-to-end source-to-alert delay and system memory; no 100-person recall from a configured cap.
6. **Run the reserved comparison once under parent control.** Identical admitted source-time windows, no model download/custom code or account side effects, safe pinned loading, synchronized resource measurements, complete failures/receipts retained. Report missing events, unmatched alerts and per-group paired outcomes with selection bias/annotation uncertainty. If results influence any tuning, retire that audit into development and acquire fresh independent groups. No automatic live promotion.

**Unverified real-data properties:** visual correctness of all labels; exhaustive source-time normality; independence beyond conservative assigned cohorts; raw media rehashes/timestamp accuracy in this audit; actual baseline/candidate parity; real checkpoint/GPU behavior; calibrated scores; independent crowd/night performance; live capacity; and complete non-copyright/model-use clearance. This report does not evaluate the parent's finished pilot predictions or assert improvement.
