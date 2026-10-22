# Fresh original Full pose comparison

Fresh headless Chromium replay of the actual MediaPipe Full model, VIDEO mode, four-pose cap, confidence 0.5, CPU delegate. Each clip used a fresh worker. The identical observed landmarks and source timestamps went into the published original rules and the current modified rules. No live camera, owner session, service, alert, or production source was changed.

| Clip | Unique frames | Pose count distribution | Frames with ≥2 poses | Original / current alert | Mean / median inference |
|---|---:|---|---:|---|---|
| F07 | 75 | 0: 49, 1: 24, 2: 2 | 2 | 0 / 0 | 74.3 / 81.1 ms |
| C01 | 75 | 0: 12, 1: 58, 2: 5 | 5 | 0 / 0 | 88.2 / 85.3 ms |

F07 was predeclared as an employee grab/push positive; C01 as a normal busy-hall negative. A missing alert on F07 is a miss for this clip. A quiet C01 matches its declared label. These two outcomes do not establish accuracy or validate performance on classrooms.

The four-pose setting is a capacity cap, not a guarantee that four people are located. The report records detected and usable bodies rather than treating missing poses as absent people. Both engines receive identical actual landmarks; any model coverage failure is shared.

The original engine uses its default standard sensitivity and historical 600ms continuity rule. The current comparison engine uses its default constructor. It is not the custom smaller-body, 3000ms DeviceAnalysis configuration. No trained fight classifier, EfficientDet object watch, crop/crowd path, transport freshness, or server incident routing was run.

Inputs are the existing private full-frame JPEG extracts, longest side at most960px, with their actual source presentation timestamps. Admission requires at least50ms from the preceding admitted frame, with0.001ms roundoff tolerance. Serial offline inference retains every admitted source frame and does not reproduce busy live-camera dropping. Model initialization is excluded from inference timings; cold first-frame inference is included. CPU timing is not phone runtime or end-to-end alert latency.

Machine-readable metadata is in [original-pose-summary.json](original-pose-summary.json). Raw source landmarks remain only in ignored results.private.json; do not publish that file or the frame images.


## Reproduce locally

With the existing private frames in `test-results/pose-two-clip`, copy the versioned replay into its ignored working directory, then start Vite on loopback:

```sh
mkdir -p test-results/original-pose-fresh
cp scripts/evaluation/original-pose/* test-results/original-pose-fresh/
npx vite --host 127.0.0.1 --port 5188 --strictPort
```

In another terminal, run `node test-results/original-pose-fresh/run.mjs`. The browser is restricted to loopback requests. Raw landmarks are written only to the ignored private results file; keep that file and the source frames out of Git and deployments.
