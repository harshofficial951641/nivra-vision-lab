# Local physical-interaction AI (experimental)

This optional Windows service runs YOLOX-S, ByteTrack, RTMPose-M, and the
SlowFast-R50 AVA action detector on the local machine. It is an implemented
inference pipeline, **not a validated fight-detection release**. It can miss
grappling and can mistake sports/background action for an incident. See
`evaluation/RESULTS.md` for the actual observations and remaining release gates.

## Setup and launch

From the `nivra-vision-lab` directory, with Python 3.11 and `uv` installed:

```powershell
uv venv --python 3.11 service/.venv
uv pip install --python service/.venv/Scripts/python.exe -r service/requirements-lock.txt --extra-index-url https://download.pytorch.org/whl/cu124 --index-strategy unsafe-best-match
service/.venv/Scripts/python.exe service/prepare_models.py
npm run dev:local-ai
```

The CUDA wheel includes its required runtime; do not install a system CUDA toolkit
for this application. The initial packages and weights are several GB. Inference
does not need network access after setup. Open **http://127.0.0.1:8765**. The
launcher builds the frontend, verifies model hashes, and starts the foreground
service. Ctrl+C stops it. Only one browser can own the local inference stream at a
time. Close other Nivra local-AI tabs before starting another.

The local URL selects **Local AI · experimental**. The existing browser-only
launcher remains `npm run dev -- --host 127.0.0.1`. Switching engines stops the
source and clears evidence. A service error requires an explicit retry or engine
switch. Object watch and browser pose-quality settings apply only in Browser mode.

## Behavior and limits

- Person detection is independent of whether both shoulders or legs are visible.
- ByteTrack associates person boxes across frames. A size-aware processing cap
  prioritizes foreground people over small spectators; it cannot guarantee all
  people are covered. Tracks are temporary IDs, not identified individuals.
- Visible keypoints provide supporting motion evidence. Missing joints remain
  invisible. Overlap suspends ambiguous joint motion; strong RGB video evidence
  may still create an interaction review without actor attribution.
- At least two currently observed people are required. Predicted/hidden people
  cannot create an alert. Grabbing by itself is insufficient.
- Action windows use source time, not processing time. A sampling gap over 600 ms
  discards motion continuity. Slow machines may therefore lose coverage; check
  processed FPS and status rather than assuming a connected service is reliable.
- Default thresholds are **uncalibrated engineering defaults**, not probabilities
  or validated operating points. No microphone or argument analysis is included.

## Protocol and privacy

The service binds only `127.0.0.1:8765` and serves the app and API on one origin.
`GET /api/v1/health` returns runtime readiness. Same-origin
`POST /api/v1/session` sets a per-launch, HttpOnly, SameSite=Strict session cookie;
the credential is never put in URLs or printed. `WS /api/v1/stream` validates the
origin and cookie and accepts only one active connection.

Each binary message has a four-byte little-endian header length, a UTF-8 JSON
header, and JPEG bytes. The header contains `version: 1`, `streamId`,
`timestampMs`, and `maxPeople`. Frames are capped at 1.5 MB/1280 px and decoded
dimensions are checked before OpenCV allocation. The client allows one outstanding
frame. Generation IDs discard late results; reset control messages release session
buffers on stop/source changes. Frames and the bounded action window live in RAM.
The service does not record footage, persist sessions, or send frames elsewhere.

Results contain observed tracks/keypoints, evidence time, action scores, coverage,
timings, and the existing human-review event shape. Scores are diagnostic model
outputs, never a displayed probability of violence. Source changes/restarts clear
history; ordinary pause/resume retains the UI review log with generation-safe IDs.

## Reproduce verification

```powershell
service/.venv/Scripts/python.exe -m pytest service/tests -q
npm run verify
service/.venv/Scripts/python.exe service/download_corpus.py
service/.venv/Scripts/python.exe service/evaluate.py service/evaluation/corpus.json --output service/evaluation/runs/candidate.json
$env:NIVRA_EVAL_MANIFEST='service/evaluation/corpus.json'
npx playwright test tests/evaluation-baseline.spec.ts
service/.venv/Scripts/python.exe service/evaluate.py service/evaluation/corpus.json --compare service/evaluation/runs/baseline.json service/evaluation/runs/candidate.json --output service/evaluation/runs/comparison.json
```

Run Python tests from `service` (`.venv/Scripts/python.exe -m pytest tests -q`)
if the shell does not add that directory to the import path. Evaluation artifacts
include pose/track traces and are gitignored. Do not substitute scripted tests for
real-model accuracy evidence. `corpus.json` pins clip hashes, attribution, labels,
and recording-level splits. Cropped variants stay with the original recording.
The current corpus is far too small for a release claim, and inspected holdout
results are now diagnostic evidence, not a fresh unseen validation set.

## Required next data/training gate

Before fine-tuning, collect independent, explicitly licensed/consented recordings
covering single punches/slaps/kicks, forceful shoves/grappling, overlap, partial
bodies, hugs, handshakes, waving, crossings, and ordinary conversation. Annotate
event intervals and person boxes/IDs. Keep all clips from a recording in one split.
Use only training/calibration recordings for fitting/threshold selection; replace
the already inspected diagnostic holdout with genuinely unseen recordings.

Fine-tuning on one wrestling example would overfit. No trained improvement is
claimed or shipped here. Promotion requires 20% fewer missed events, no increased
false-alert rate, improvements in overlap and partial-body subsets, and measured
live p95 alert delay at most three seconds on the target PC. Missing evidence or
a failed gate leaves this engine experimental.

## Classroom profile and metadata service

`npm run dev:classroom-ai` opts into RTMO-M Body7, regional SlowFast AVA and the
pinned X3D/RWF-2000 candidate. `prepare_models.py --experimental` verifies/downloads
those optional artifacts. `npm run dev:local-ai` retains YOLOX/RTMPose/AVA. Neither
profile is a validated classroom classifier. Model licenses/provenance remain in
`model-manifest.json` and `THIRD_PARTY.md`.

The root application is now Classroom Command. `/lab` preserves the original
single-camera interface and explicit Browser engine. `/camera` is the scoped
publisher. `/api/v2/session`, `/api/v2/state`, `/api/v2/cameras`, `/api/v2/events/{id}`,
`WS /api/v2/operator`, `/api/v2/camera/pair` and `WS /api/v2/camera/stream` comprise
the versioned classroom API. V1 and V2 share an inference lock; they never execute
concurrent GPU jobs against the same model objects.

The four-camera queue replaces old detection work while retaining each source's
captured RGB in a separate 4.5-second/64-frame bounded RAM window. Only metadata
is stored in `service/state/classrooms.sqlite` (ignored). Camera credentials expire
on service restart. Pausing revokes access and requires pairing again to resume.
The API validates origins, cookies, frame size/dimensions, source ordering and
publisher rate. SQLite review transitions require a matching revision and append
an audit record. Schema version 1 requires no migration from the prior lab, which
had no database; unknown schemas fail explicitly.

Optional configuration: `NIVRA_METADATA_DB` chooses a separate local metadata file;
`NIVRA_PUBLIC_ORIGIN` supplies one exact HTTPS origin for an already-authorized
camera gateway. The process still binds to loopback. See
`docs/remote-camera-setup.md`; setting this variable does not deploy a gateway.

Latest candidate comparison:

```powershell
service/.venv/Scripts/python.exe service/evaluate.py service/evaluation/corpus.json --person-model rtmo --max-people 50 --regional-actions --fight-model x3d --output service/evaluation/runs/crowd-x3d-final.json
service/.venv/Scripts/python.exe service/evaluate.py service/evaluation/corpus.json --compare service/evaluation/runs/baseline.json service/evaluation/runs/crowd-x3d-final.json --output service/evaluation/runs/crowd-final-comparison.json
```

For isolated multi-camera software tests, first launch with a disposable metadata
path (never your pilot records), then:

```powershell
$env:NIVRA_CLASSROOM_AI='1'
$env:NIVRA_LOCAL_AI='1'
npx playwright test tests/classroom.spec.ts tests/local-ai.spec.ts
service/.venv/Scripts/python.exe service/benchmark_classrooms.py service/evaluation/media/grappling.webm --seconds 60 --cameras 4 --confirm-disposable-db --output service/evaluation/runs/four-camera-final.json
```

The benchmark refuses to replace cameras not named `QA ...`. It reports actual
processing and transport timings using duplicated public footage. It is not an
accuracy test or a substitute for four real classroom feeds.
