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
3. **Test-only fixes.**
   - GPS test guard ordering tie.
   - LAN interface stub (no `ifaddr`).
   - Guard-stream snapshot draining.
   - Windows-safe temp socket path.

## Verification on Windows (i5-10400F, GTX 1660 Ti)

- **Frontend:** lint passes, build passes, and Vitest **708/708** (77 files) on the final commit. Repeated runs at `0a8c51f`: 4 full runs, plus police/guard/wall files 10×.
- **Python:** **1,171 passed, 5 skipped, 0 failed** on the final commit. The Mac-only `test_public_host_tools.py` and `test_local_host_tools.py` were excluded. At `0a8c51f`: 3 full runs, and police/classroom/GPS 15× each.
- **Known non-regressions:**
  - `test_usb.py` sustained-pump throughput can dip below 16 fps under heavy CPU load.
  - `tests/classroom.spec.ts` sample-wall test (`/?demo=1`) fails on `main` too.
- **Security review:** no unauthorised or cross-workspace police logging or reading; relay forwarding is unchanged in exposure.

## Needs Tanishq / a Mac

See `docs/HANDOFF-MAC-IOS.md`: the iOS `WebSession.swift` change, the Android build, phone checks, and the live-host redeploy of the token-bucket fix.
