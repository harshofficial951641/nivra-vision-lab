# Browser video classifier backend integration

23 October 2026. Work remains uncommitted on `harsh/police-and-detector` in `D:\NIVRA`.

`movinet-a0-vid-v1` is an additional backend alert source for authenticated `browser-video-v1` H264 publishers. Existing browser rules, native X3D, transport acknowledgements, relay permissions, review and guard contracts remain in place. Classifier evidence does not overwrite phone observations or identify an actor/target.

One spawned process owns bounded per-camera PyAV contexts and one TorchScript model. Decode continues while one bounded batch scores on a dedicated inference thread. The supervisor uses 20 ms polling, a 90 s loading deadline and 10 s heartbeat/inference watchdogs; a failed worker requires backend restart. Queues cap at 16 input packets and 64 output messages, with at most 32 cameras globally. Native decoder pixels are capped before decode. Overload discards work and requires a keyframe; video/socket generations and internal revisions discard stale results. Oldest due cameras get batches of up to four, normally once per second.

Model windows are causal four-second source intervals. The bounded ring retains target neighbours for 5.5 s to cover scheduler jitter. Exact training transform: nearest actual PTS inside the half-open window, earlier ties; 16 targets then indices `[0,2,4,6,8,10,12,15]`; OpenCV BGR resize224, RGB conversion, resize172; float32 `/255`, no crop/mean/std. Per-clip reset is baked into the export and tested. Human review previews preserve aspect ratio up to 640 px; all video, frames, IPC and incident clips stay in RAM.

Device priority is CUDA, MPS, CPU. CPU-traced tensor-factory Device literals are rebound in memory to the selected accelerator, preserving the shipped bytes and arithmetic. Auto accelerator warmup can fall back to CPU with a visible reason; forced benchmark devices fail explicitly. This adapter depends on pinned Torch 2.5.1 and must be revalidated on upgrades.

`NIVRA_VIDEO_CLASSIFIER=auto` (default) reads C2's policy once at startup; `on` explicitly enables; `off` skips policy/model access and worker creation and preserves previous camera/runtime behavior. Invalid policies fail closed. C2 policy was present at this report: `defaultEnabled=true`. Restart after C2 publishes/changes the policy. Exact C2 qualifying/strong thresholds, inclusive comparison, consecutive confirmation, 1 s stride, 2 s episode merging and 8 s cooldown are supported without adding a two-person gate. Source resets preserve a wall-clock cooldown; database dedupe suppresses classifier/browser duplicates in both arrival orders, across reconnects and backend restarts.

C2's held-out evaluation reports 11/53 events detected (20.75%), with 0 false alerts over 0.223794 actionable normal camera-hours. The exact Poisson upper97.5 rate is 16.48/h. The owner point-estimate gate enables the default, while reliable coverage and a confidence-bound rate of <=2/h remain unproven. See [C2 evaluation](../video-classifier/README.md).

All launchers inherit this through `create_app`, including `run_public.py` relay-only mode, `run_local.py` and `run_usb.py` / Start NIVRA.command; launcher behavior was not rewritten. Public guest apps share the primary classifier instance while camera status/callbacks remain workspace-scoped. Health and classroom runtime expose status/device/reason and per-camera window rate and analysed FPS (eight model samples per window, including overlap; not unique capture FPS). Explicit `off` retains the previous runtime payload.

Events use `record_event` with model id and detail “Video classifier: possible physical conflict. Review the clip.” Existing review captures, frozen event location and human-confirmed guard dispatch apply. No new UI controls or runtime frontend files changed. Guard payloads retain their privacy allowlist.

The bundled artifact is 11,169,076 bytes, SHA-256 `78e372a5ec6ad97925c3cdac2e0de0f5e9315ebd38fb151fa429d69304aaef87`. It is outside ignored `service/models/`. Manifest provenance, bundled-artifact verification, base PyAV 18.1.0 dependency (already pinned in Mac/lock requirements), full Apache-2.0/MIT licences and third-party notices are included. Original Google weights are Apache-2.0, port MIT, VID V2 fine-tuning data CC0; no footage is distributed.

Validation: full service suite **1,204 passed, 6 skipped**, with `NIVRA_RUN_CUDA_TRAINING_TEST=0`, `NIVRA_VIDEO_CLASSIFIER=off`, and only the two requested Mac host-tool files excluded. Explicit enabled-path tests cover preprocessing/C2 simulator parity, decoder corruption/gaps/generations/reconnect/SPS bounds, batching, loop lag, watchdogs, cooldown/dedupe, off no-op, runtime, clips, guard dispatch and workspace sharing. Separate CUDA parity: **1 passed**, batches 1–4 within `atol=rtol=1e-5`. Web: **711 tests / 77 files passed**; lint and production build passed. An existing guard-auth test assumed wall time always advances within one Windows tick; only its injected clock now advances explicitly. Runtime guard/auth code is unchanged.

Browser QA used a labelled synthetic incident and disposable RAM database on loopback port 43193: desktop/390 px wall and review, clip/explanation, confirmation, guard dispatch, keyboard acknowledgement, on-scene/clear and clip expiry passed. No horizontal overflow or unlabeled guard buttons were found. Console showed the expected initial unauthenticated 401 and a rejected manual duplicate-confirm 409; no uncaught JavaScript errors. GPS timed out; actual GPS/Maps were not validated. The QA app was stopped and tab cleared. No public hosts or prohibited listener ports were used.

PC performance: i5-10400F, 12 logical CPUs, GTX 1660 Ti, Windows, Python 3.11.15, Torch 2.5.1+cu124 / PyAV 18.1.0. Thirty seconds per device, four independent 1280x720/40 fps decoders, FP32, Torch two CPU threads, decoder one thread each, one batch-four model. Both runs decoded 4,804 frames and analysed 27 windows per camera with zero dropped/stale packets. CUDA held the existing shared GPU lock.

| Device | Decode CPU, one core | Batch-four inference ms p50 / p95 | Windows/s/camera | Loop lag ms p95 / max | Drops |
|---|---:|---:|---:|---:|---:|
| CPU | 20.5% | 211.1 / 287.2 | 1.00 | 6.0 / 22.0 | 0 |
| CUDA / GTX 1660 Ti | 19.2% | 83.8 / 267.2 | 0.99 | 6.0 / 22.0 | 0 |

Decode CPU includes decode/ring resize and excludes inference/JPEG. Divide CPU percentages by 12 for whole-machine percentage. Inference includes stack/transfer/softmax/output sync and excludes preprocessing. Maximum CUDA sample was 1366.9 ms; short runs include startup/driver variability and do not prove sustained capacity. Full raw metrics are adjacent JSON files. The harness uses synthetic MP4/H264 in BytesIO and writes metrics only.

Mac handoff: install the existing Mac requirements, build normally, then run the benchmark with `--device mps --seconds 900 --output <metrics.json>` and repeat with `--device cpu`. Check `/api/v1/health` → `runtime.videoClassifier` for the actual device/fallback. Confirm source-clip logits, batch independence, four real browser publishers, reconnects, event timing and sustained thermals on the target Mac. TorchScript/MPS is used; no CoreML/ANE placement, Mac performance, iPhone camera, long-duration behavior, production deployment or classifier accuracy claim has been established here. JPEG-only browser fallback and native phone streams do not enter this classifier lane.

Reproduce from `service/` using the specified prepared Python environment:

```powershell
$env:NIVRA_RUN_CUDA_TRAINING_TEST='0'
$env:NIVRA_VIDEO_CLASSIFIER='off'
python -m pytest --ignore=tests/test_public_host_tools.py --ignore=tests/test_local_host_tools.py -q
python benchmark_video_classifier.py --device cpu --seconds 30 --output ../docs/evaluations/video-classifier-integration/cpu-performance.json
# On the shared PC add --gpu-lock-source <existing training_v4/gpu_lock.py> for CUDA.
python benchmark_video_classifier.py --device cuda --seconds 30 --output ../docs/evaluations/video-classifier-integration/cuda-performance.json
```

Changed integration files (plus this report and its three adjacent JSON receipts):

- `service/nivra/video_classifier.py`
- `service/nivra/classroom.py`
- `service/nivra/server.py`
- `service/nivra/workspaces.py`
- `service/nivra/assets/movinet_a0_fight.pt`
- `service/model-manifest.json`
- `service/prepare_models.py`
- `service/requirements.txt`
- `service/THIRD_PARTY.md`
- `THIRD_PARTY_NOTICES.md`
- `licenses/MOVINET-APACHE-2.0.txt`
- `licenses/MOVINET-PORT-MIT.txt`
- `service/benchmark_video_classifier.py`
- `service/tests/test_video_classifier.py`
- `service/tests/video_classifier_fixtures.py`
- `service/tests/fixtures/movinet_probe_preprocessing.py`
- `service/tests/test_guard_auth.py`
- `src/command/CommandWall.test.tsx`
- `src/command/ReviewWindow.test.tsx`
- `src/guard/GuardApp.police.test.tsx`

C2-owned scripts/reports and browser detector files were preserved. No commits, pushes, branch switches, deployments or service provisioning were performed. `docs/HANDOFF-MAC-IOS.md` was not edited.
