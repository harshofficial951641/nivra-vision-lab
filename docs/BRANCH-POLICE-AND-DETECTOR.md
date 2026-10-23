# Branch `harsh/police-and-detector` (23 October 2026)

Based on Tanishq's `main` at `f145b61`. Nothing on `main` or the live host was changed.

## What is in it

1. **Police contact for guards and reviewers.**
   - Placement: the guard alert, the guard response screen, and the review window (for undecided and active incidents).
   - Flow: tap **Police**, then **Call 112**, **Text police** (pre-filled with the camera name and location) or **Cancel**. Nothing dials without confirmation.
   - Number: `VITE_NIVRA_POLICE_NUMBER` overrides 112 after validation.
   - Logging: each contact is recorded in the incident history (`event_audit`, no schema change, no revision bump) and shown on the wall, the review window and the guard screen as "Police contacted (call/text) by … at …". Duplicates within 10 s are refused.
   - Endpoints: `POST /api/v2/events/{id}/police` (reviewer/admin) and `POST /api/v2/guard/events/{id}/police` (assigned guard).
   - Android opens `tel:`/`sms:` through `ACTION_DIAL`/`ACTION_SENDTO`. It was not built here.
   - **iOS still blocks these links.** See `docs/HANDOFF-MAC-IOS.md`.
2. **Browser detector replay harness and measured accuracy** (`scripts/evaluation/detector`, `docs/evaluations/detector-accuracy`).
   - The harness replays labelled VID clips through the real `DeviceVision` + RTMO + original conflict engine path.
   - On 227 held-out dev videos, the current default caught **0/116** labelled events.
   - The train-selected crowd-contact profile reached **6.9%** recall but added **13.2 false alerts/h**, so it failed the gate and **stays off**.
   - A conservative profile reached 4.3% with no observed false alerts. It was not train-selected, so it stays off pending fresh confirmation.
   - In 88–93% of samples inside labelled fights, two usable bodies were not visible. Skeleton rules alone cannot reach high recall on this footage.
   - `DEFAULT_DETECTOR_EXPERIMENT = null`: production behaviour is unchanged.
3. **Video fight classifier on the Mac backend (MoViNet A0).** It decodes the existing browser H264 stream, scores 4 s windows about once a second, and creates human-review events (`movinet-a0-vid-v1`). These are de-duplicated against browser-rule alerts within 8 s.
   - Held-out test: **11/53 fights (21%, CI 6–35%)** with **0 false alerts in 13.4 normal minutes**. That passes the owner's ≤2/h rule on the point estimate only; the upper bound is about 16/h. Calibration half: 4/62.
   - It is ON by default through `NIVRA_VIDEO_CLASSIFIER=auto` and `policy.json`. `off` restores previous behaviour.
   - Weights are bundled (11 MB; Apache-2.0 MoViNet weights, MIT port, fine-tuned on CC0 VID).
   - See `docs/evaluations/video-classifier/` and `docs/evaluations/video-classifier-integration/`.
4. **Test-only fixes.**
   - GPS test guard ordering tie.
   - LAN interface stub (no `ifaddr`).
   - Guard-stream snapshot draining.
   - Windows-safe temp socket path.

## Verification on Windows (i5-10400F, GTX 1660 Ti)

- **Frontend:** lint passes, build passes, and Vitest **711/711** (77 files) on the final commit. Repeated runs at `0a8c51f`: 4 full runs, plus police/guard/wall files 10×.
- **Python:** **1,204 passed, 6 skipped, 0 failed** on the final commit, classifier included. Classifier evaluation unit tests: 22/22 (`python -m unittest`). The Mac-only `test_public_host_tools.py` and `test_local_host_tools.py` were excluded. At `0a8c51f`: 3 full runs, and police/classroom/GPS 15× each.
- **Known non-regressions:**
  - `test_usb.py` sustained-pump throughput can dip below 16 fps under heavy CPU load.
  - `tests/classroom.spec.ts` sample-wall test (`/?demo=1`) fails on `main` too.
- **Security review:** no unauthorised or cross-workspace police logging or reading; relay forwarding is unchanged in exposure.

## Needs Tanishq / a Mac

See `docs/HANDOFF-MAC-IOS.md`: the iOS `WebSession.swift` change, the Android build, phone checks, and the live-host redeploy of the token-bucket fix.
