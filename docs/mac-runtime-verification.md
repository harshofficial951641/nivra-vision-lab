# H3 runtime verification — 2026-10-22

Measured on Windows: Intel Core i5-10400F, NVIDIA GTX 1660 Ti (6 GiB).
These are observations on the shared development PC, not Mac estimates or
accuracy validation. No existing service on 8765/8766 was stopped or modified.

`service/verify_camera_runtime.py` loads real RTMO/X3D weights, sends JPEGs at
12 fps/camera through the actual `/api/v2/camera/stream` handler, and uses
disposable SQLite metadata. The WebSocket transport is in-process ASGI TestClient;
these measurements exclude real network/TLS/phone overhead. Replays lasted 22 s.
Repeated copies of a sample are not independent scenes.

| Device | Cameras | Sample | Mean inference ms | p95 ms | Analysed fps total | Analysed fps/camera | Events / clips |
| --- | ---: | --- | ---: | ---: | ---: | --- | ---: |
| CPU | 1 | grappling | 775.95 | 1089.48 | 1.045 | 1.045 | 1 / 1 |
| CPU | 2 | grappling | 836.35 | 1274.13 | 0.999 | 0.500 each | 0 / 0 |
| CPU | 6 | grappling | 1345.25 | 2446.44 | 0.545 | 0.091 each | 0 / 0 |
| CUDA | 1 | grappling | 89.06 | 132.99 | 4.136 | 4.136 | 3 / 3 |
| CUDA | 2 | boxing | 109.08 | 174.99 | 5.405 | 2.680–2.725 | 0 / 0 |
| CUDA | 6 | grappling | 93.69 | 134.22 | 7.540 | 1.226–1.317 | 12 / 12 |

This table uses `--no-fallback` to measure server capacity. The CPU 2/6-camera
runs are not acceptable showcase operating points: sparse observations produced
no events. The separate default-fallback CPU run switched after 12 measured jobs,
recorded one event, and retained a ready 62-frame clip. Its 679.93 ms mean includes
warmup and was collected while focused tests were also running; do not compare
that timing directly with the capacity table. Fallback readiness still depends
on the browser's own detector reaching `ready`.

Raw JSON is local and gitignored under `service/evaluation/runs/`:
`mac-cpu-1-capacity.json`, `mac-cpu-2-capacity.json`, `mac-cpu-6-capacity.json`,
`mac-cuda-1.json`, `mac-cuda-2-boxing.json`, `mac-cuda-6.json`, and `mac-cpu-1.json`.
Earlier runs sampled the runtime's budget after disconnect, so their
`targetFpsPerCamera` reflects zero live cameras. The measured frame counts/fps
above are taken before disconnect. The harness now samples the budget before
disconnect as well.

Reproduce from `service` (use `.venv/bin/python` on Mac):

```shell
.venv/Scripts/python.exe verify_camera_runtime.py --device cpu --cameras 1 --seconds 22 --no-fallback
.venv/Scripts/python.exe verify_camera_runtime.py --device cuda --cameras 6 --seconds 22 --no-fallback
```

Apple Silicon Python 3.11 dependency resolution was checked using `uv pip compile
service/requirements-mac.txt --python-platform aarch64-apple-darwin --python-version
3.11`. Both Mac scripts passed `bash -n`. This does not prove package installation,
CoreML partitioning, MPS operator support, sustained Mac thermals, Safari/Chrome
camera capture, CA trust, Clerk sign-in, or venue networking. Those require the
[actual-device showcase checklist](mac-showcase.md).
