# Offline crowd observer: staged implementation

21 October 2026. **Implemented and stub-tested; this helper has run no real inference.** Parent reproduced the original 68 passed/1 skipped suite, then attempted CUDA initialization with Torch DLL preload. It failed before inference because strict CPU-operator rejection disallowed CPU-assigned graph nodes. No successful observer report resulted. The explicit mixed-operator/profile policy below is now staged; the parent has not rerun it in this helper's scope. The live community X3D-M remains unchanged after the parent's [67-window paired comparison](PAIRED-RESULTS.md). Parent also reports a later three-epoch community pilot produced the same 67 decisions as baseline; no improvement is claimed. This observer does not run X3D, classify fights or track people. It is a separate offline research entry point under [PROTOCOL.md](PROTOCOL.md), following the [crowd/pose audit](crowd-pose-repos.md).

## Files and scope

- [nivra/crowd_observer.py](../../nivra/crowd_observer.py): bounded five-view RTMO adapter, checksum validation, provider configuration, metadata/runtime shape validation, coordinate mapping and spatial deduplication.
- [research_crowd_observer.py](../../research_crowd_observer.py): local checksum-pinned four-recording CLI, sequential actual-PTS sampling and exclusive JSON output under ignored `service/research/runs/`.
- [tests/test_crowd_observer.py](../../tests/test_crowd_observer.py): pure stub inference/provider/decoder tests; no real model forward pass, GPU calls or video decoding.
- This document.

No existing model, pipeline, API, ingress guard, manifest, model asset, service, account, package environment or source corpus was changed. Existing maxPeople=50 and 1280px ingress limits remain. This CLI deliberately bypasses live ingress; it does not advertise API support for 100 people or native 1080p. It now reads the existing loopback demo health endpoint to yield cooperatively; that is a read-only check, not live integration or a service change.

## Actual local model inspection

The existing manifest entry `rtmo-m-body7` names `models/rtmo_m.onnx`. Its **actual local bytes** were SHA-256 checked, before a CPU-only ONNX Runtime session was created:

```text
750d872151ff4652f02c738efc3a547e112ce9b688fe920bc17f948e8c3afdac
```

Inspection used ONNX Runtime **1.21.1**, explicitly `CPUExecutionProvider`, one intra/inter-op thread, with session fallback disabled. **Neither `session.run` nor `observer.observe` was called on the real model.** The new adapter's CPU construction from verified model bytes was separately checked without a forward pass.

The actual returned metadata is:

```text
input       tensor(float) [batch, 3, 640, 640]
dets        tensor(float) [batch, Reshapedets_dim_1, Reshapedets_dim_2]
keypoints   tensor(float) [batch, Concatkeypoints_dim_1,
                          Concatkeypoints_dim_2, Concatkeypoints_dim_3]
```

**This metadata does not establish the real slot count or joint count.** Both remain null in the report metadata. No inference was authorized for this helper, and an ONNX graph parser package is absent; none was installed. The earlier upstream `keep_top_k=50` finding must not be substituted for this artifact's actual output shape. Parent-run inference must produce exactly float32 `[1,S,5]` detections and `[1,S,17,3]` keypoints, with `0 <= S <= 256`. The 256-slot number is a defensive **per-view safety bound**, not a claim about model capacity. Static dimensions, if ever declared, must match expected batch/column/joint dimensions and the runtime slot count. Invalid ranks, unnamed unknown dimensions, missing outputs or any non-finite output fail closed.

The complete expected joint order is exported in each report as COCO-17: nose; left/right eyes; left/right ears; left/right shoulders, elbows, wrists, hips, knees and ankles. The known asset hash and pinned upstream body7 config provide its intended layout; a runtime shape alone cannot prove joint semantics.

## Observation and coverage contract

One observer owns one reused ORT session and performs **exactly five sequential batch-one calls per valid frame**:

1. Global source frame.
2. Top-left `[0,0,.65,.65]` source view.
3. Top-right `[.35,0,1,.65]` source view.
4. Bottom-left `[0,.35,.65,1]` source view.
5. Bottom-right `[.35,.35,1,1]` source view.

Coordinates are normalized here only to specify crop boundaries; reported view geometry uses rounded full-source pixel boundaries. The source frame remains uint8 BGR. Every view is cropped directly from the native source, then resized into a **640x640 top-left letterbox**, pad 114, BGR float32 0..255 with no RGB swap/mean normalization. This matches the existing `Models.crowd_observations` preprocessing. These are native-source crops, not five native-resolution inference tensors and not a top-down call per person.

Inputs must be uint8 HWC three-channel images, minimum dimension 32, and fit either width<=1920/height<=1080 or width<=1080/height<=1920. No upscaling to claim native HD is performed. The model letterbox may upscale a small crop as part of its fixed input contract, which does not create source detail.

Every runtime tensor is validated before filtering, including low-score/padded slots: detection and keypoint confidences must be finite and in [0,1]; coordinates must be finite. Detection threshold is >=0.1. Mapped boxes are clipped to the source view, then rejected if either source-pixel side is below 8. Keypoints outside their source view receive confidence zero and are clipped to the view boundary before translation. Output contains anonymous person-category boxes and all 17 keypoints in both full-frame pixels and normalized coordinates, with the actual confidence retained. No track/person identity or source tensor slot is exported as an identity. `sourceView` identifies image geometry only.

**Dedup policy:** sort by descending confidence, then deterministic view/slot order; suppress a person-category observation when its full-frame box IoU is >=0.7 with an already retained observation. A 64px spatial grid restricts comparisons to boxes sharing a cell. Deduplication is completed before applying the output cap, so the pre-cap counts are genuine counts of this algorithm's retained observations. Retain at most **100**, report the exact `omittedByCap`. IoU is a geometric heuristic, not identity resolution: it can merge distinct people during close contact or retain an imperfect duplicate.

Work is bounded independently of scene claims: <=256 slots/view, <=1,280 candidate observations total, fixed five views, bounded native image dimensions, and <=50,000 IoU comparisons. The grid avoids unconditional all-pairs enumeration. It is not a claim of worst-case O(N): a dense cell can still create many candidates. Exceeding the comparison budget aborts the frame/report with an error rather than silently dropping work and claiming coverage. The implementation does not change ByteTrack or the live pipeline's other quadratic operations.

Each frame reports:

- `views`: all five geometries, actual runtime tensor shapes, raw returned slots, score-eligible slots, geometry rejection count, eligible observations, all-slots-eligible saturation proxy, safety-slot-bound hit and per-call host wall time.
- `coverage`: raw slots, eligible observations before dedup, deduplicated count before cap, duplicate removals, returned observations, cap omissions, actual view count and IoU work/budget.
- `visibleHumanCount=null`, `visibleHumanRecall=null`, `fightAnalyzedPeople=null`, `fightAnalysisStatus="not-run"` and no fight-localization result.

`allReturnedSlotsEligible` indicates possible output saturation, not known detector truncation. `atConfiguredSlotSafetyLimit` refers to the defensive 256-slot guard. `modelTopKLimitKnown=false` remains explicit even if a runtime call returns 50 rows: a returned shape does not prove unseen people were all covered or that it is the graph's configured top-K.

No whole-scene completeness or 50-100-person recall claim follows from these counts. They count detector observations in processed views, not manually annotated visible humans. There is no temporal interaction scheduler, pose-action head, alert policy, identity, audio, intent, injury, guilt or policing functionality here.

## Provider and memory boundaries

`--device` is mandatory: `cpu` or `cuda`. CPU requests only CPU EP and must report only CPU EP. CUDA requires CUDA EP to be advertised and actually activated as the first provider. **Strict default:** `session.disable_cpu_ep_fallback=1` rejects graph nodes assigned to CPU. Parent's initialization failure shows that this is too strict for the actual graph; it does not show a CUDA DLL failure or successful inference.

**Explicit research policy:** `--allow-cpu-operators` configures CUDA EP first plus CPU EP, omits that strict graph-partition rejection flag, and automatically enables operator profiling. It is rejected with `--device cpu`. This permits intentional CPU-assigned shape/unsupported operators; it does not authorize a whole-session retry to CPU. Both policies still call `session.disable_fallback()` to disable Python provider repair after construction. If ORT's constructor internally attempts a provider fallback, the actual-provider check rejects a CPU-first/CPU-only result **before any inference**. Mixed policy must have both providers present with CUDA first. There is no application retry to CPU, package installation or automatic repair.

Runtime provenance distinguishes `allowCpuOperators`, `cpuExecutionFallbackDisabled` and `pythonProviderFallbackDisabled`. **A successful `get_providers()` check is not evidence of actual CUDA execution.** `gpuVerified` starts false and can become true only after the bounded trace contains positive CUDA non-memcpy compute events. This means some actual compute executed on CUDA, not that all operators did, that memory/latency bounds passed, or that fight/crowd accuracy is validated. CPU operators and execution counts are disclosed even when CUDA compute is observed.

CUDA provider options set device 0 and `gpu_mem_limit=1073741824` (1 GiB), with `arena_extend_strategy=kSameAsRequested`. **This limits the ORT CUDA allocator arena, not the complete process or total GPU memory.** Driver allocations, workspaces outside that allocator, other processes and the resident live model can add memory. Run the research CLI in its own process; parent must measure total device usage and live-service coexistence separately.

On explicit Windows CUDA construction, ORT's DLL preloader may be used. `--preload-torch-dlls` is a separate explicit opt-in if DLL discovery needs it; it is rejected for CPU/non-Windows. That branch imports Torch only for DLL loading and never calls `torch.cuda` or a Torch model. This helper never exercised the CUDA or Torch-preload branches; provider tests use stubs.

`ortRunHostWallMs` measures synchronous host-wall `session.run` calls returning CPU arrays, including ORT overhead and transfers. `totalObserverHostWallMs` additionally includes demo yielding, view preprocessing, mapping and dedup; `demoYieldHostWallMs` is reported separately, and per-view ORT timing excludes the yield. Neither is isolated GPU kernel timing. Profiling itself adds overhead. The report includes processing wall time before serialization, and `gpuPeakMemoryBytes=null`; **Torch allocator statistics are not used to infer ORT or total device memory**. Parent must independently bound end-to-end calls, total process/device memory and sustained load. No timings or VRAM-fit claims were measured in this helper.

### Bounded operator execution evidence

`--profile-operators` explicitly enables ORT profiling for either device; mixed policy implies it even if the flag is omitted. A new report `name.json` gets a new, exclusive sibling directory `name.operators/` with an `ort_*.json` trace. Existing profile directories, reused files, traversal and symlink paths are rejected. ORT chooses the timestamp suffix; the returned path must resolve inside that associated directory and have the expected prefix/suffix. Raw trace collection is bounded by the existing <=32 frame/<=160 forward-call policy. Parsing additionally enforces **64 MiB maximum file bytes and 200,000 maximum trace events**; excess/malformed traces fail the run without a success report. ORT has no trace byte-rotation feature here, so a too-large trace can remain on disk after rejection; the size limit bounds parsing, not an absolute write quota.

The report records trace path, SHA-256, byte/event counts, kernel execution counts by provider, unique executed node-name counts by provider and operator-type counts by provider. Counters use `Node` events ending `_kernel_time` with explicit `args.provider` and `args.op_name`. Session/fence events do not prove compute. CUDA memcpy events alone never set `gpuVerified=true`. These are **observed execution events and unique executed node names**, not a full static graph-assignment census; repeated nodes across views/calls are counted as repeated executions. Missing CUDA compute leaves verification false with `no-cuda-compute-proven` even if CUDA EP is listed.

Profiles are finalized once after the bounded sample run. On a frame/decode failure, finalization is attempted only to flush diagnostic evidence; no success JSON is written. A failed initialization may leave an empty/partial associated profile directory; use a fresh report name for every retry. CLI initialization errors, including ORT pybind `Fail` exceptions, are wrapped as readable `Observer research failed: ORT session initialization failed: ...` exits, not mistaken for completed runs. No operator profile from real inference has been generated by this helper.

### Cooperative demo yielding

Before model hash/load/session creation and **before every view**, the CLI reads only `http://127.0.0.1:8765/api/v2/fight/health` using standard-library HTTP, no environment proxies or HTTP redirects, 1-second HTTP timeout and <=16 KiB response body. It proceeds only for `status=ready` with `busy=false`. Busy/loading responses yield in <=250 ms sleep increments with a `--demo-wait-seconds` budget per check (default 30, allowed >0 to 60); the final health request can add up to its 1-second transport timeout before the deadline is checked. Unavailable, malformed, disabled/error health or an exhausted wait budget fails closed. No CUDA or Torch call is used for the guard; it does not touch accounts or modify services. The report includes check count, guard wall time and policy. Tests inject the guard/fetch/clock; they do not contact the real endpoint.

This is a cooperative snapshot, **not a lock or reservation**: the demo can become busy after a health check, and an already-running ORT initialization/view cannot be preempted. Parent still owns GPU scheduling and may need to stop the offline process if live demand changes. No skip-guard CLI switch is provided.

## CLI source and output safeguards

The CLI reads only the four original IDs: boxing, grappling, kick, squats. The synthetic cropped grappling entry is deliberately omitted. The supplied raw corpus file must match `--corpus-sha256`; each original must also match its fixed, code-pinned SHA-256 and declared duration <=60 seconds. All paths resolve to local files inside the repository; model bytes are checked against both the pinned manifest entry and a fixed approved digest. The exact verified model bytes are passed to ORT, preventing a later path replacement between hashing and loading.

The current corpus file hash and all four source hashes were verified, without decoding:

```text
corpus.json 33d04d15bc4a6911face456fff7488320906505cc344f863042e4cae304bfb34
boxing      2dd4c6269c120978630b1a1e1fd3819b53d75b02dd1b9a6e34a5e9e9de966430
grappling   1004027ef030303bef37144da30363aff7bdacda585d76d58b837d6db0272064
kick        752181dd7417113744baf0337a0682fd10813575cb8d327057957a164246455f
squats      ea9151e447b301985d5d65666551ef863b369a2e0f3a71ddd58abef2e722f96a
```

Each source has a 200 MB file limit. Source attribution/licence is copied from the existing reviewed corpus as provenance, not independently cleared anew. The old `calibration/holdout` names are not promoted to evaluation independence.

Sampling is sequential through local FFmpeg-backed OpenCV, `cv2.setNumThreads(1)`, one decoder thread. It uses actual decoded `CAP_PROP_POS_MSEC` timestamps, requires finite nonnegative strictly increasing PTS and never reads nominal FPS or fabricates a clock. For each target, select the first decoded frame at/after that target, report actual PTS, decoded frame index and target overshoot. One frame cannot satisfy multiple targets. Actual selected PTS must remain below declared source duration. This is sparse observation sampling, not continuous motion review or full-recording coverage.

Bounds: 1-8 selected frames/original, <=32 samples total, <=160 model calls; target interval 100-10,000 ms; default 2 samples at targets 0/1000 ms, eight frames/40 calls total. Decode is capped at 1,200 frames/original by default (configurable 1-2,000), 20 seconds decode wall time/original (configurable >0 to 30), and 60 seconds source PTS. The decode clock excludes the caller's model work while the generator yields; model execution time is measured separately, not interrupted by this decoder budget. Open/read timeout options are 3 seconds, subject to the decoder backend honoring them. Decode geometry is checked before reading images and on every decoded image; it may not change. Failure to obtain the requested samples fails the run, rather than reporting partial sampling as complete.

No camera index, network URL, downloader or live-stream client is accepted. Output must be a **new .json child** of `service/research/runs`; path traversal, symlink escapes, outside paths and overwrites fail. Bounds, existing output and all source hashes are checked before model construction. Output is rechecked after processing and created exclusively with mode `x`. No successful report is written after a failed frame/decode. The JSON contains only bounded anonymous observations and provenance, not extracted images or frame files. Like any ordinary file write, disk interruption can leave an incomplete file; consumers must parse and validate it before treating it as a completed result.

## Reproduction commands

Run from the repository root in PowerShell. The following test/help commands were executed; they make no real model forward call:

```powershell
Push-Location service
.venv/Scripts/python.exe -m pytest tests/test_crowd_observer.py -q
.venv/Scripts/python.exe research_crowd_observer.py --help
Pop-Location
```

**Parent-controlled inference commands only; not executed by this helper:** choose new output names each time. CPU also performs real model inference and is included here for explicit parent choice, not as a fallback.

```powershell
service/.venv/Scripts/python.exe service/research_crowd_observer.py --device cpu --corpus-sha256 33d04d15bc4a6911face456fff7488320906505cc344f863042e4cae304bfb34 --frames-per-recording 2 --interval-ms 1000 --output crowd-observer-cpu-v1.json
```

```powershell
service/.venv/Scripts/python.exe service/research_crowd_observer.py --device cuda --corpus-sha256 33d04d15bc4a6911face456fff7488320906505cc344f863042e4cae304bfb34 --frames-per-recording 2 --interval-ms 1000 --output crowd-observer-cuda-v1.json
```

The strict CUDA command above is retained to reproduce the strict policy, but parent already observed its required-CPU-operator initialization failure. **Exact next mixed-provider/profile command**, with a new output name:

```powershell
service/.venv/Scripts/python.exe service/research_crowd_observer.py --device cuda --preload-torch-dlls --allow-cpu-operators --profile-operators --corpus-sha256 33d04d15bc4a6911face456fff7488320906505cc344f863042e4cae304bfb34 --frames-per-recording 2 --interval-ms 1000 --demo-wait-seconds 30 --output crowd-observer-cuda-mixed-profile-v1.json
```

This should create only the new ignored report and `service/research/runs/crowd-observer-cuda-mixed-profile-v1.operators/` trace directory after a successful run. It is staged for parent execution; no rerun was launched here. Parent must coordinate the GTX 1660 Ti 6 GB/live model before launching it. Initialization can still fail if DLLs/provider/operators are unavailable or the arena is insufficient; no environment repair occurs. Goal 1 is actual runtime tensor shapes and preprocessing/coordinate parity before any crowd coverage claim.

## Verification and remaining empirical work

Focused tests after the mixed-policy change: **88 passed, 1 skipped**. The skip is the Windows symlink-creation privilege test; non-symlink path confinement/overwrite checks passed. Tests cover the original bounds/hash/PTS/dedup safeguards plus strict versus explicit mixed-provider configuration, 1 GiB retention, initialization/forward error handling without retries, profile confinement/byte/event limits, CPU/CUDA execution and unique-node/type counts, memcpy-only non-verification, positive-compute verification, associated output paths, and demo yielding before load/every view with busy/unavailable failure. All model/provider/decoder execution in these tests uses stubs.

Prior actual non-inference checks remain: existing local model bytes match manifest/fixed SHA-256; CPU session metadata inspection and original adapter CPU construction succeeded; all four original source hashes and corpus hash matched; CLI help parsed. This fix was checked with stubs/static inspection only; parent alone attempted the failed actual CUDA initialization. The full shared service suite was not rerun for this isolated addition; other helpers' work was preserved. No real video decoder path or actual CPU/CUDA inference was exercised by this helper.

Remaining work for parent: run the staged command under the GPU schedule; record actual output shapes/slots, provider activation, end-to-end latency and total-device memory; visually compare native/tile coordinates and duplicate/merge failures on selected frames. This is still only an observer smoke test on four few-person development recordings. Real 50-100-person crowd recall, occlusion/contact coverage, genuine near-IR monochrome CCTV, low-light colour, native 1080p/720p versus explicitly derived 480p, interaction-localization accuracy and fight-alert performance remain **unverified**. Grayscale/darkened daylight and thermal IR do not substitute for near-IR/night-colour CCTV.

## Source/ref and licence boundaries

Original new adapter/CLI logic was written locally; no code from the unlicensed Fight-Detection repository was copied. Letterbox parity follows the existing local adapter and the official RTMO path. The implementation does not clone, execute, download or import external repository code at runtime.

Relevant reviewed primary source pins, retained separately from asset terms:

- [MMPose revision 759b39c13fea6ba094afc1fa932f51dc1b11cbf9](https://github.com/open-mmlab/mmpose/tree/759b39c13fea6ba094afc1fa932f51dc1b11cbf9), [body7 RTMO-m config](https://github.com/open-mmlab/mmpose/blob/759b39c13fea6ba094afc1fa932f51dc1b11cbf9/configs/body_2d_keypoint/rtmo/body7/rtmo-m_16xb16-600e_body7-640x640.py), [Apache-2.0 code licence](https://github.com/open-mmlab/mmpose/blob/759b39c13fea6ba094afc1fa932f51dc1b11cbf9/LICENSE).
- [MMDeploy revision 3f8604bd72e8e15d06b2e0552fe2fdb8f8de33c4 RTMO export defaults](https://github.com/open-mmlab/mmdeploy/blob/3f8604bd72e8e15d06b2e0552fe2fdb8f8de33c4/configs/mmpose/pose-detection_rtmo_onnxruntime_dynamic.py). The official export default of 50 is upstream configuration evidence, not verified cardinality of this local graph.
- Existing [model-manifest.json](../../model-manifest.json) identifies the official ONNX SDK archive, `end2end.onnx` member and archive/model hashes. Its source URL uses `main`; this document and the research audit preserve the exact reviewed code revision separately. No branch-following runtime fetch occurs.

The local manifest declares Apache-2.0 for this asset; code licence, separately published checkpoint terms and the seven body7 training datasets' media/participant rights are distinct. This task did not clear all checkpoint/data rights or commercial use. `rightsIndependentlyCleared=false` is included in runtime provenance. See the separate research audit for the unresolved source-data boundaries.
