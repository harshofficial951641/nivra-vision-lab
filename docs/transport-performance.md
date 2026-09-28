# Live preview transport — 28 September 2026

The phone publisher previously allowed only one unacknowledged JPEG. Its effective
rate therefore fell with network round-trip time. The service also limited preview
broadcasts to one every 240 ms and waited for viewers before acknowledging capture.

The publisher now targets 12 frames/second with at most eight unacknowledged frames,
a 768 KiB normal in-flight budget, and a bounded socket backlog. One unusually large
valid frame can travel alone. Capture pauses when the oldest acknowledgement is
750 ms late; a ten-second stall ends the connection. Skipped captures are discarded,
not queued. Encoding time is included in the capture interval.

Each dashboard has one serialized sender and a latest-only mailbox: one pending
preview per camera and one pending snapshot. Capture acknowledgements and GPU work
do not wait for viewers. Stale queued previews are discarded; a viewer stalled for
500 ms is disconnected. Disconnected cameras lose their pending preview. Existing
latest-frame GPU scheduling, source timestamps, image dimensions and JPEG quality
are preserved. Frames remain in memory only.

## Measured public relay results

Same PC, Sites URL and Cloudflare tunnel; one temporary synthetic camera, 960 × 540,
145,030-byte JPEGs, approximately 12 seconds per run. No existing camera pairing was
changed. Test camera rows were removed afterward; no images or videos were saved.

| Measurement | Before | After |
| --- | ---: | ---: |
| Uploaded frames | 132 | 134 |
| Received preview frames, including final drain | 45 | 134 |
| Upload FPS | 10.97 | 11.12 |
| Preview FPS during capture | 3.74 | 11.04 |
| Median acknowledgement RTT | 32 ms | 31 ms |
| p95 synthetic send-to-preview arrival | 78 ms | 109 ms |

The preview throughput improved 2.95×. This low-RTT PC test did **not** demonstrate
lower per-frame network delay. It measures relay arrival, not physical camera
capture-to-screen latency. It is not a 2–4-classroom capacity or detection-accuracy
result. Real mobile data, phone thermal limits and crowded-scene bandwidth still
need direct verification.

A deterministic 400 ms RTT test sends 120 frames in ten simulated seconds while
staying within eight outstanding frames. A Chromium fake-camera test receives more
than 35 frames within five seconds with 400 ms delayed acknowledgements (the prior
stop-and-wait sender could manage about 12). It also checks stop, reconnect, failure,
mobile overflow, keyboard activation and console errors.

Re-run regressions with `npm run verify`,
`npx playwright test tests/camera-transport.spec.ts tests/classroom.spec.ts --grep-invert "real service"`,
and `service/.venv/Scripts/python.exe -m pytest service/tests` from the appropriate
Python import environment. Public measurements are retained as metadata only in
the ignored `output/qa/transport-before.json` and `transport-after.json` files.

Reload dashboard and phone pages to load the new publisher. Restarting the service
expires its in-memory sessions, requiring a new operator link and camera QR pairing.
