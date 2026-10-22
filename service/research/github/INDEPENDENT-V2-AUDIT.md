# Independent V2 training and artifact audit

Audit date: 21 October 2026. Read-only review; no trainer, manifest, media, model, benchmark integration or live-service changes. The sole authored repository file is this report. No real model constructor, checkpoint inference, CUDA job or training job was run. Synthetic CPU optimization of tiny test modules was permitted.

## Findings, ordered by severity

### P2, FIXED AND RECHECKED — initial V2 lost runtime dependency provenance present in V1

**Current disposition:** the trainer helper implemented the authorized fix during this audit. Independent guarded follow-up passed 109 CPU tests at the new pins below, unchanged before/after execution. The initial finding is closed within the stated source/metadata scope. No unresolved P0/P1/P2 implementation finding remains from this review. The original evidence is retained below; its line numbers refer to the initial module pin, not the revised module.

`nivra/community_x3d_experiments.py:212–230` exports configuration, source hashes and tensor contracts but no runtime versions. `:247–250` likewise omits them from the run seal. Compare V1 `nivra/community_x3d_training.py:300`, which records runtime versions. V2's required source/provenance list at `:288–291` does not require `requirements.txt`, `requirements-lock.txt`, installed dependency sources or a runtime receipt. Inherited construction enforces only `pytorchvideo==0.1.5` (`community_x3d_training.py:66–73`); it does not establish the actual Torch/NumPy/OpenCV build used for a run.

Consequently, a self-contained V2 run tree cannot establish which Torch optimizer/pooling, NumPy or OpenCV implementation produced its weights and samples. Repository requirements currently pin versions, but neither those bytes nor actual installed build versions are automatically preserved in a V2 artifact. This is a reproducibility regression, not evidence of an incorrect gradient or poor model quality.

Recommended before expensive fitting: record actual Python/Torch/Torchvision/PytorchVideo/NumPy/OpenCV versions and build information, snapshot the dependency lock/requirements, and bind that receipt to milestone/report validation. A version string alone does not pin dependency source or binary bytes. No code fix was made. Parent was notified immediately after confirmation.

No P0/P1 finding and no additional material trajectory, weighted-loss, accumulation-tail, frozen-state, safe-load or epoch-accounting bug was found within this bounded review. This conclusion does not certify annotation truth, real model parity, GPU behavior, or deployed detection quality.

## Follow-up: revised runtime provenance and seal independently checked

The revised `community_x3d_experiments.py` introduces `runtime_snapshots` (`:42–88`), `validate_runtime` (`:91–132`) and `validate_installed_dependencies` (`:135–145`). Review and tests establish these bounded properties:

- Observed Python/platform, actual imported Torch/NumPy/OpenCV/PytorchVideo versions, Torch git/build CUDA/cuDNN metadata and installed-package inventory are recorded. Linked/compiled CUDA metadata is distinguished from probing a device or driver. The helper reads dependency source/metadata; it does not execute preserved source, install anything or download weights.
- Required snapshots include service requirements/lock and selected installed PytorchVideo construction/head/convolution/swish/rounding sources, fvcore squeeze-excitation source and Torch optimizer/activation/pooling/Linear/BN/functional source. Optional additional manifest/lock files are captured if present. Dependency source copies are bounded to 8 MiB. These are selected source pins, not hashes of every transitive implementation or compiled library binary.
- Runtime metadata is bound identically into started receipt, state artifact, milestone report, environment JSON and final seal (`:324–326`, `:339–342`, `:376–380`). The seal now includes `startedSha256`.
- Validation requires the started receipt hash and metadata to match the seal (`:393–399`), requires selected/root snapshot inventories to agree and verifies snapshot bytes in both root and selected milestone (`:430–440`). Thus the first-pass root-evidence limitation below has been tightened: root started receipt and duplicate snapshots are now checked. Other siblings' report/checkpoint bytes remain required; their duplicate snapshot trees are not recursively validated while selecting another milestone.
- Required runtime/dependency entries cannot simply be omitted from a resealed inventory. JSON-safe metadata, environment-file equality, required snapshots and hashes are checked. Local package versions and selected installed dependency source hashes must match the recorded training environment before model construction at fitting and reload (`:367`, `:497–502`). This is controlled compatibility checking, not proof of identical compiled kernels or cross-device bitwise results.
- Training loop logic is unchanged; its line numbers shifted by 125 lines. Manifest/schema, provisional-label, cohort and optional review-provenance limitations remain as documented in the first pass.

**Independent rerun:** the same guarded CPU-only harness ran the V2 plus V1 test files: **109 passed in 38.18 seconds** (71 V2 parameterized cases plus 38 V1). This supersedes the earlier 89-test result for the revised implementation; do not sum the runs as independent coverage. Module/test/CLI/expanded-plan hashes printed immediately before and after pytest were identical. Tests performed no real model construction, media decoding, model inference or GPU work.

The 20 added V2 cases check observed runtime without CUDA probing, matching metadata across receipts/artifact/seal, corrupted/missing runtime and dependency bytes, required entries removed from self-consistently rewritten envelopes including fvcore, local dependency version/source drift before constructor, and nonprimitive/missing package inventory rejection. These are meaningful regressions for the reported issue. The added tests were authored by the trainer helper; this audit independently inspected and executed them without modifying shared source.

| Revised file relative to service | SHA-256 independently tested |
| --- | --- |
| nivra/community_x3d_experiments.py | `d593b45b3e5985d7c15c24311c9c3646d908b4bdaf6c84a31fcd49486638fdc4` |
| tests/test_community_x3d_experiments.py | `0181b08ec3284754ea114019f2b0345839f27659f1d5c48544d6a2b5ca76be7d` |
| train_community_experiments.py | `f233e7e2be03040dd7dc81eabda1fcb23e1f1672c137ed7235fabb5654ff4811` |
| research/github/EXPANDED-TRAINING-PLAN.md | `d84cb6526c884f513f061506fd9f9170e12328735321b24ab658a3e6c3d4decf` |

The plan pin above includes the runtime/dependency correction at lines 82–123 and was read during follow-up. Implementation/tests were declared frozen by their owner at exactly the tested pins. A prior intermediate fix passed 108 tests at module `db8fae90477ff59d66eb81ec8e9463ac7d6f1105d8f3d02b6854c88d15582c3d`; that result is superseded by the final fvcore/convolution/rounding and version-consistency additions. Do not use the intermediate pin for admission. Other initial dependency/source pins below remain the audit's observed evidence. No V2 run is claimed to exist merely because synthetic export tests passed.

After the independent test run, the helper made its final documentation-only verification update. Final `EXPANDED-TRAINING-PLAN.md` SHA-256 is `8d0377e73cba3148a6b5a9a00bf39dc414643ed7039f5a81230a994f4c6ab741`, independently rehashed/read. The implementation/test hashes remain the final tested values above. Its reported full-suite 732 passed / 5 skipped is the helper's separate run, not this audit's independently executed 109-test result. Cleaned-manifest admission is separately documented in `ROUND3-MANIFEST-AUDIT.md` and does not imply real-model validation.

## Initial-pass detail retained for traceability

**The remaining implementation line references and initial source table below refer to module `60046b…` and tests `675c15…`. Revised runtime/seal behavior and current test results are described above. In particular, old statements that root copies and runtime dependencies are unsealed describe the initial finding, not the independently checked revised implementation.**

## Review procedure and scope

1. Read `PROTOCOL.md`, `TRAINING-AND-TESTING-PLAN.md` and the V2 expanded plan; inspect V2 module/CLI/tests and relevant imported V1/data/decoder code.
2. Trace the fixed trajectory and export/validation contracts, including failures and sibling requirements; compare tests with independent mathematical expectations.
3. Run the V2 and inherited V1 synthetic test files under additional CPU-only guards; inspect actual test results and source hashes.
4. Record findings, admission requirements and properties that remain unverified. Recheck audited stable source hashes before completing this report.

The V1 immutable pilot source/manifest audit is preserved separately in `INDEPENDENT-TRAINING-AUDIT.md`. This V2 review concerns current source, not an actual completed V2 run or a V2 source snapshot. The separately changing benchmark integration is outside the audited implementation boundary. No model prediction reports were opened.

## Trajectory, loss and frozen forward path

| Contract | Evidence and assessment |
| --- | --- |
| One continuous 3/10/20 trajectory | `community_x3d_experiments.py:100–105`: AdamW and seeded shuffle generator are created once outside the epoch loop. `:133–148` exports after the declared epochs without reinitializing either. Max 3 exports 3; max 10 exports 3/10; max 20 exports 3/10/20. |
| Actual cumulative accounting | `:128–144` increments once per optimizer group; reports actual export epoch, cumulative updates and microbatches. Validator `:323–332` checks `E*ceil(N/8)`, `E*N` and E finite nonnegative loss values. These are consistency checks, not independent proof that an adversarial artifact performed those steps. |
| Weighted objective and tail | `:96–119`: train-only weights `N/(2*n_class)`, summed weighted NLL of clamped retained probabilities, divided by the actual sum of target weights in each group. Last partial group uses its own denominator. No extra Softmax, logits surrogate or tail division by eight. Epoch loss is the cumulative pre-update microbatch weighted NLL divided by all target weights (`:130`), not an end-of-epoch evaluation loss. |
| Stronger reference test | `test_community_x3d_experiments.py:38–72` independently batches 11 synthetic examples with a 7/4 imbalance into an 8-item group plus 3-item tail. A persistent reference optimizer and shuffle generator are advanced through every epoch; states are compared at every applicable milestone for budgets 3/10/20. This would catch optimizer restarts, wrong tail normalization and many generator/reset mistakes. |
| Existing head only | `:92–95` calls inherited `enable_head_only`; V1 `:87–100` freezes all parameters then enables only the existing final Linear weight/bias. It validates head layout, two classes, Dropout and Softmax/output-pool placement. No new random projection is introduced by V2. |
| BN/Dropout and non-head state | V1 `:118–126` hashes every non-head state tensor, checks all modules remain eval and exact trainable names. V2 checks at epoch boundaries (`:104`, `:129`) before export. This covers BN running buffers and counters as well as frozen parameters. It does not independently hash nonpersistent module attributes or instrument every internal operation. |
| Softmax-before-pooling | V2 reuses the pinned community architecture, does not replace its activation/output pool, and calls inherited retained-probability validation. The installed constructor is `pretrained=False`. Tiny tests exercise the intended order, first-forward preservation and corrupted BN rejection; they do not instantiate the real X3D graph. |
| Numerical limits | Epsilon is fixed at `1e-7`; below-clamp values have zero derivative, and the clamp is not renormalized. This matches the declared experiment, rather than being evidence that this objective transfers well. Finite loss, gradients and updated head tensors are checked (`:116–127`). |

The full CPU test comparison supports the software objective and accounting. It cannot establish meaningful learning or transfer from actual video. All model modules intentionally remain eval while gradients flow through the Linear head.

## Manifest, explicit intervals and annotation source basis

`validate_training_manifest` (`:52–67`) validates a caller-supplied SHA before and after parsing, media hashes at run admission, one permitted CC0 VID source, training permission, the one unresolved VID session cohort, train-only recordings and both eligible window classes. `run` separately checks that the snapshotted manifest bytes still have the supplied SHA (`:179–182`). It computes counts from admitted windows, rather than importing V1's 96/156 expectations.

Inherited `training_data.py:220–221` rejects empty model-split events and positive recordings without explicit positive events. `:247–270` requires full normal coverage or at least half positive coverage of a window; unknown gaps do not become normal. `:274–306` creates full four-second windows, omits recordings shorter than four seconds and may append a dependent end-aligned overlapping window. Conflicting overlapping labels and out-of-duration event bounds are rejected earlier. Both labels being present is not a representativeness or balance guarantee.

**Explicit events are a schema requirement, not evidence that those events were actually observed.** V2 cannot detect whether a manifest's explicit intervals were previously fabricated by the legacy builder. It accepts any matching permitted manifest with the declared schema, including an old manifest if a caller explicitly supplies its SHA. This is clearly distinguished in `EXPANDED-TRAINING-PLAN.md:15–22`; it is not a new automatic clean-data certification.

Additional review files are optional `provenance_files` in the Python API, and CLI `--provenance-file` defaults to none (`train_community_experiments.py:22`). The CLI automatically snapshots the two plans, but does not derive which review JSON/evidence files justify every interval. V2 source snapshots also omit the builder unless explicitly supplied. A successful run/load therefore does not prove its canonical review selection, review method, evidence coverage, annotation origin or supersession decisions. These remain parent admission work. Save the canonical review JSON, builder source, inventory/provenance mapping and evidence hashes with the run, rather than relying solely on a mutable path or `reviewed` flag.

The frozen old cohort's 91 normal windows retain the already quantified distinction: 60 from 26 implicit legacy records, 2 explicit but sampled legacy windows, 12 expanded dense-sampled windows and 17 every-frame reviewed windows. The 40 weaker-coverage sources require re-review; they do not become new independent data. This V2 audit did not reopen those videos, verify the pending re-review or validate a newly cleaned manifest. Parent-reported round-three normal admissions and evidence counts were not independently recounted here.

VID stays one training-only cohort. V2 explicitly exports zero calibration and holdout windows, default threshold .5 as unfitted, no holdout selection and provisional assistant labels. No independent split is inferred from IDs, archives, scenes, durations or overlapping windows.

## Artifact, sealed root, siblings and safe reload

| Check | Assessment |
| --- | --- |
| New output only | `:173–174` rejects existing paths; `:190` uses `mkdir(exist_ok=False)`, protecting against a concurrent creator as well. Snapshot, JSON and checkpoint writes use exclusive creation. No resume/overwrite path. |
| Admission before construction | Manifest/media/baseline SHA/rights snapshots and guard are checked before model construction (`:175–189`, `:239`). Input/guard failure tests assert no model or output directory is created. |
| Complete last | `:251` creates `complete.json` after all requested milestone exports and final cooperation. Ordinary exceptions inside fitting/export preserve `failed.json` and rethrow (`:253–256`). Earlier epoch success is unusable without the final seal. |
| Failure boundary | Snapshot setup and `started.json` writes precede the `try` (`:190–199` vs `:236`); setup I/O errors can leave a partial directory without `failed.json`. Process termination/KeyboardInterrupt likewise need not create a marker. These remain unloadable because no seal exists; do not promise every interrupted directory has `failed.json`. Writes are exclusive but not crash-durable transactions/fsync guarantees. |
| Root and siblings | `:263–280` requires the root seal, matching requested milestone set/config/base/manifest, no root failure marker, and exact report/checkpoint bytes for every sibling. Missing a later checkpoint prevents loading an earlier milestone. It does not silently select the last available success. |
| Scope of seal | Root `started.json` and duplicate root snapshots are not checked by the loader. Sibling report/checkpoint bytes are checked; sibling snapshot trees are not inspected while loading another selected milestone. Selected snapshot paths/hashes are checked. This matches the plan's distinction between all cataloged report/checkpoint hashes and selected provenance, but is not an authenticated seal of every file in the whole tree. |
| Selected provenance | `:287–304` requires specified sources, manifest and rights files; validates paths remain inside selected milestone and digests match; reparses the manifest without requiring original media presence. Loading an offline artifact therefore does not rehash/redecode training media. |
| CPU restricted deserialization | `:305` uses `weights_only=True, map_location='cpu'` before any model construction. Full CPU state, finite tensor types/shapes/dtypes, frozen hashes and exact binary head shape are checked (`:340–352`). This avoids arbitrary pickle globals; it does not impose a hostile-file size/memory budget or provide cryptographic authenticity. |
| Actual epoch and exact state | Directory name, selected report epoch and root catalog must agree; report/artifact contracts match; load constructs a trusted current installed architecture, verifies exact keys/shapes/dtypes and uses strict state load (`:356–367`). The selected model is eval and all parameters are nontrainable. |
| CPU device policy | Explicit CPU resolution does not probe CUDA; invalid device is rejected before construction. Guarded tests enforce restricted torch.load kwargs and this device behavior. |
| Scores and metadata | Inherited BGR API returns retained class probabilities with fight index 1; V2 metadata adds actual export epoch and V2 kind. Strict decision remains fightScore > .5. No calibration or localization claim follows from a class score. |

Integrity metadata is self-consistent local evidence, not a signature or an independent attestation of the training history. Current trusted loader/architecture code is executed; snapshotted Python is preserved as evidence and never executed. Validating snapshot hashes does not require the current installed helper implementations to match those snapshots. The P2 dependency finding matters particularly for future reloads in another environment.

## Independent checks actually executed

Command target, using the existing Python only:

```text
service/.venv/Scripts/python.exe -
pytest -q --tb=short -p no:cacheprovider
  service/tests/test_community_x3d_experiments.py
  service/tests/test_community_x3d_training.py
```

Result: **89 passed in 10.80 seconds**. V2 accounts for 51 parameterized cases; V1 for 38. This is one combined result, not 89 independent real-data trials. No test cache or bytecode writing was enabled. No additional tests were added to shared files.

The in-memory harness set `NIVRA_RUN_CUDA_TRAINING_TEST=0`, hid CUDA devices, returned false from CUDA availability, disabled CUDA seed work, blocked CUDA initialization/device selection/allocator configuration/synchronization, blocked `torch.hub.load` and replaced the PytorchVideo hub constructor with a failing sentinel. OpenCV threads were set to one; Torch initially one (the inherited loader sets two). Unique guard closures avoid TorchDynamo's duplicate-function-rule issue from the earlier V1 harness. Only tiny local synthetic nn.Modules, artificial media bytes and temporary directories were used.

Tests cover continuous trajectory/reference gradients and tail, declared budgets, full-state CPU roundtrip and actual epochs, unchanged non-head state, BN mutation, class index/BGR adapter contract, fixed configuration, rejected nontrain splits, bad manifest/media/baseline/rights/review/cohort/classes/empty events, mismatched/corrupt/resealed artifacts, missing later sibling, failed later fitting, guard-before-construction, no-overwrite, cache bounds and CLI requirements. They meaningfully test failure modes rather than just checking log strings.

Remaining synthetic-test gaps include setup-write interruption, missing/corrupt sibling report (checkpoint deletion is covered), snapshot path escape/drive variants, root-only evidence loss, dependency-environment mismatch and independently binding every event to its review evidence. No new failure was inferred merely from absent tests.

Audit environment metadata read without constructing models: Python 3.11.15, Torch 2.5.1+cu124, Torchvision 0.20.1+cu124, PytorchVideo 0.1.5, NumPy 1.26.4, OpenCV-Python 4.11.0.86, pytest 8.3.5. The CUDA-labelled wheel was used for CPU tensor operations only. These describe this audit environment, not an unobserved V2 training run.

## Source pins

SHA-256 values below are current working-file bytes, not Git revision claims. Audited stable trainer/CLI/test pins were checked before execution and again at completion. Plans may be edited by their owners; these pins define the versions reviewed. No source under an actual V2 run was inspected because this audit did not run or assume a V2 fit.

| File relative to service | SHA-256 |
| --- | --- |
| nivra/community_x3d_experiments.py | `60046b5140aea04933ebe5a5f635c5bdf549afce7ebfe3559c06cbaa43996cfe` |
| train_community_experiments.py | `f233e7e2be03040dd7dc81eabda1fcb23e1f1672c137ed7235fabb5654ff4811` |
| tests/test_community_x3d_experiments.py | `675c1593832663276135aae9e64e595408eeb6dd993df0c98adb0a5af1709421` |
| nivra/community_x3d_training.py | `dcc907543f44173a4ffeab4559643c3a09f97f3a1d741a133f04913bae888694` |
| train_community_x3d.py | `f38ab9a7953b4fb8f47acf88a285a12a0f7c5dc31afe997175c415bf289ab806` |
| tests/test_community_x3d_training.py | `7cd0163c9ce1d1d62abb10896ce7b952fe0ea755d771926237bb4d7d920cd308` |
| nivra/training_data.py | `a2df7795345838f7c890e0f2bbd4335f66e21b10981acb055bfa647bef940239` |
| nivra/x3d_training.py | `99d13e5d1e13f774ea09ea50b4071b11702bd38a8514d05d8c87d20a04218831` |
| nivra/x3d_finetune.py | `18aeb3877df98dc86de57ed0e502bc025c851f550ee427489a706d7ddf6f8569` |
| nivra/x3d_candidate.py | `65798e408dbc85231b976187401850a9909eb899235f0eea7f5f4ac09fdabee4` |
| requirements.txt | `c84d2cef3e9b05efd3dcc56a0ee61aadc5121042b3cd1a18d6cd6da4eedd25ad` |
| requirements-lock.txt | `35e29001b389a4f1c156afc2e475bd9c46ba8893fdd717d77235ae6166c15932` |
| research/github/EXPANDED-TRAINING-PLAN.md | `cdc46ab371f7cfba4509363b18ca6d32fd9b241e515d86679fe3c828a10d50c8` |
| research/github/TRAINING-AND-TESTING-PLAN.md | `9651405a38f9c58fff4ae711d45224fa55622ff57a39ce5c44190880d435632e` |
| research/github/PROTOCOL.md | `10e406f8487cdc4ed9fab22e0f98ba3f45e5f59497c8ac57aae6710174ca35b6` |

## Parent admission and locked-audit boundaries

Before fitting: freeze cleaned canonical review selection and manifest SHA after the legacy normal re-review, explicitly preserve annotation source/evidence hashes, recompute counts/window identities/media hashes, retain unknown margins, retain one VID training cohort, and address or separately capture runtime dependency provenance. Do not call this validation a new independent dataset. Dataset CC0 copyright evidence, author-reported consent and unresolved checkpoint terms remain separate from software licensing and model quality.

Before real comparison: parent must verify actual V2 zero-step baseline equivalence on identical source-time windows, real gradients/optimizer execution, all milestone state/epoch identities, CPU reload numerical parity, actual CUDA memory/latency and demo cooperation. The bounded tests do not exercise the actual X3D graph, real decoder/media, Windows GPU memory pressure or near-IR/night scenes. The inherited decoder enforces monotonic/fallback timestamps, bounded reads, at least eight samples and at least 3.8 seconds sampled span (`x3d_training.py:103–145`); that does not establish frame-accurate source alignment for every real codec or continuous visual annotation of the source. The adapter's frame-list API itself receives no timestamps.

Before locked audit: freeze candidate SHA, threshold and complete alert/matching policy using development groups only; enforce author/event/session grouping and the predeclared online role rule before scoring; preserve all derivatives within their source group. Verify explicit positive events, full normal coverage and unknown intervals separately. Count unmatched alerts on actually annotated normal time and state any unknown-time exclusions; use reviewed normal duration for false alerts/hour. The old evaluator's permissive match grace/whole-clip denominator is not automatically repaired by V2 training. Check suppression, duplicates and episode compatibility explicitly.

Report event/source-group counts and dependence; no meaningful operating false-alert bound follows from a few short clips with zero observed errors. Existing diagnostics remain development-only. Current source/test evidence establishes no 50–100-person coverage, native 720p/1080p robustness, low-quality CCTV transfer, real near-IR or low-light-colour capability. Grayscale/darkened daylight, thermal footage and tiled crowds cannot fill those empirical gaps. A locked audit used to tune the candidate becomes development material and needs replacement.
