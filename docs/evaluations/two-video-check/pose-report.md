# Isolated comparison: earlier Full pose rules on F07 and C01

Actual T3 Chromium GPU replay, using the existing MediaPipe Full worker (`VIDEO`, numPoses4, confidence0.5), original `new ConflictEngine()` and current `new DeviceAnalysis()`. This is the isolated Full pose/ConflictEngine path, not the whole original application. EfficientDet, ROI/crowd Lite, transport and server alert routing were not run. No production model, threshold, service, phone, alert or workspace was changed.

| Clip | Source cadence | Unique frames | Detected poses per frame | Mean pose inference | Original / device alert |
|---|---|---:|---|---:|---|
| F07: declared grab/push | ≥200ms | 25 | 0:15, 1:10 | 69.3ms | no / no |
| C01: declared busy hall | ≥200ms | 25 | 0:4, 1:19, 2:2 | 64.9ms | no / no |
| F07 | ≥50ms (~15Hz) | 75 | 0:49, 1:25, 2:1 | 39.6ms | no / no |
| C01 | ≥50ms (~15Hz) | 75 | 0:12, 1:53, 2:10 | 46.7ms | no / no |

The earlier pose detector also missed F07. C01 stayed quiet. This agrees with the native two-clip test's clip-level outcomes; it does not show that either detector is accurate.

F07 at200ms had no frames with two detected poses. At the denser cadence it found two poses on just one frame, yielding a warming state rather than sustained conflict evidence. C01's two-person usable frames were judged too far apart; most frames supplied zero or one usable body. These are observed diagnostics, not a claim that absent poses mean absent people. The configured capacity is four, but actual coverage was much lower.

## Source and timing

`extract.swift` uses the same AVFoundation BGRA reader as the native test. It preserves actual presentation timestamps, including C01's edited first0ms frame. Each decoded source frame is exported once, full-frame, longest dimension960, JPEG quality0.95. No duplicate still-frame sequence, time rescaling, invented joints or labels were used. Native-cadence admission accepts the next unique source frame ≥200ms after the previous admitted PTS, with the same0.001ms tolerance. The denser protocol independently admits ≥50ms, reflecting the existing original-motion capture limit. Both run through the whole same5-second clips, retaining the native test's selected temporal region and source frames. These are continuous pose-rule replays, not independent16-frame X3D windows; the two algorithms have different temporal inputs.

Each clip/protocol gets a fresh worker and fresh engines. GPU is the actual returned delegate. The original engine retains its default body-size and600ms continuity settings; DeviceAnalysis retains its smaller body gates and3000ms continuity limit. Neither emitted an event. Results include every source timestamp, pose count, usable count, original diagnostics, explanation, events and timing. Clip and task hashes plus library version are in `results.json`.

The replay is offline: it waits for each inference before submitting the next actual source frame. Source timestamps drive motion rules; inference timings use wall time. It does not measure phone performance, busy-camera dropping, end-to-end alert latency or native Apple Vision pose coverage. JPEG intermediate compression is a comparison limitation. Full VIDEO tracking can vary between independent runs/delegates; GPU timings are warm/cold mixed, and model initialization is excluded. These two predeclared clips are not an independent accuracy benchmark; training overlap and dense human annotations are unknown.

## Reproduce locally

From repository root, copy the versioned harness into its ignored working directory:

```sh
mkdir -p test-results/pose-two-clip
cp scripts/evaluation/pose-two-clip/* test-results/pose-two-clip/
swift test-results/pose-two-clip/extract.swift '/path/to/footage/fights/cuts'
npx vite --host 127.0.0.1 --port 5197 --strictPort
```


Open only the isolated loopback page `/test-results/pose-two-clip/index.html`. Wait until `window.__poseReplay.done` is true; `window.__poseReplay.error` must be null. The page shows the result data, also available as `window.__poseReplay`. No application/session APIs are called. Raw frames and harness remain under ignored `test-results`; do not deploy them.
