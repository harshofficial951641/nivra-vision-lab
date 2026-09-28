# Design QA — Classroom Command

final result: passed

Scope: implemented local dashboard and camera-publisher UI. This is not a pass
for model accuracy, real-device streaming or a deployed classroom pilot.

## Visual source and captured implementation

- Source visual truth: `C:/Users/harsh.DESKTOP-VE90R6D/Downloads/Nivra/output/ui-ux-plan-2026-09-28/extended-screens/00-selected-reference.png`.
- Source pixels: 1586 × 992; implementation desktop viewport/capture: 1586 × 992,
  deviceScaleFactor 1. Both original images were opened together in the same
  comparison input; no browser chrome or density scaling was used for judgement.
- Current desktop: `output/qa/classroom-desktop.png`, sample state with one open
  review, active/limited/offline camera states and four classroom locations.
- Additional evidence: `output/qa/classroom-mobile.png`,
  `classroom-mobile-dialog.png`, `classroom-publisher-mobile.png`,
  `classroom-live-source.png`, `classroom-service-failure.png` in that directory.
  Phone CSS viewport 390 × 844; full-page captures can be taller.
- The in-app browser was also used to inspect the rendered local preview at its
  natural narrow desktop width. Automated screenshots/interactions use the
  browser-testing scope explicitly requested in the implementation plan.

The source depicts six campus cameras, while the confirmed pilot has four
classrooms. The 2 × 2 grid is intentional. A labelled generated classroom asset
replaces campus imagery only in sample mode. Actual mode uses received frames,
not a simulation. The canonical Nivra mark replaces the source's unapproved tower.
A working location directory replaces unprovided floor-plan geometry. Event
history has no playback/clip controls, following the confirmed no-recording scope.

## Comparison history and fixes

1. The earlier green interface study was superseded by the newer approved
   monochrome design received from the design chat. The implementation changed
   to a white/zinc sidebar, black actions, stable camera wall, right review rail
   and sparse semantic status color. The visual selection gate was not repeated.
2. [P2, fixed] Initial large camera images pushed the second row's coverage
   controls out of the desktop viewport. The grid image height now adapts to
   available viewport height. Post-fix 1586 × 992 capture shows all four camera
   cards and their coverage/detail controls above the status bar.
3. [P2, fixed] Dialog autofocus landed on its close button rather than the
   classroom name. Native modal opening now explicitly focuses the initial form
   input. Browser assertions verify initial focus, Escape dismissal and no mobile
   horizontal overflow; the mobile-dialog capture shows visible keyboard focus.
4. [P2, fixed] Bounding boxes could drift when a received image was letterboxed.
   The overlay now measures the actual contained-image geometry, and hides boxes
   whose evidence timestamp is more than 700 ms from the preview timestamp.
5. [P2, fixed] A slow stream could retain reassuring status after failure. A
   disconnected service clears preview URLs and exposes an unavailable warning;
   stale camera/analysis states are explicit. Live service browser tests verified
   stop, reconnect, revocation and injected bootstrap failure.

No actionable P0/P1/P2 visual findings remain in the implemented scope.

## Required fidelity checks

- **Typography:** Arial/Segoe UI sans-serif, clear 30 px desktop page title,
  14 px camera headings, smaller location/status metadata. No raster UI text.
  The native form and publisher use the same neutral sans-serif family. Minor
  compact metadata density differs from the concept and is P3 refinement only.
- **Layout:** compact left navigation, dominant stable 2 × 2 wall, fixed right
  review/context rail and status strip. Search, floor filter and focus layout
  work. Mobile becomes a single-column camera list with accessible top navigation
  and a review/context section below. No horizontal overflow at 390 px.
- **Color/tokens:** white/light-zinc surfaces, black primary buttons, gray borders,
  modest radii; amber only for review/coverage states and restrained green status
  dots. Text and icons accompany color-dependent states.
- **Assets:** supplied canonical logo and Phosphor icons. Generated sample image
  is labelled both in the banner and each tile. Live images preserve source
  aspect ratio and never use a generated fallback as a live feed. No fabricated
  floor-plan map, person identity or recorded-video thumbnail.
- **Copy/content:** “possible physical conflict,” explicit human review, distinct
  feed and analysis state, experimental model notice, no invented accuracy KPI.
  Sample states never write to the live camera/event database. Pairing clearly
  says local-only if no HTTPS origin is configured.

Camera headers, review card, sidebar and status strip were checked at original
1586 px width in the paired full-view inputs; their typography and controls were
legible there, so a separate cropped raster comparison was unnecessary. The
focused mobile dialog and publisher captures additionally verify form/permission
surface layout. The exact six-camera source and the four-classroom implementation
are not represented as identical content or as a pixel-for-pixel clone.

## Interaction and technical evidence

- Browser sample flow: search, floor filter, focus/grid, acknowledge, resolve,
  analytics, settings, track toggle, details, edit dialog and keyboard Escape.
- Browser real-service flow with Chromium's synthetic camera: create location,
  issue/redeem scoped pairing link, start feed, display actual local model output,
  stop/restart, pause/revoke and show connection failure.
- Original lab: actual CUDA pipeline, cropped source, stop/restart, responsive
  layout, backend selection, keyboard use, failed bootstrap and explicit retry.
- Tests inspect page/console errors on the sample path; real-service tests inspect
  page errors. Expected injected service errors are not called clean networking.
- `npm run verify`: lint, 214 unit tests and production build passed. Python suite:
  36 tests passed. Full browser suite: 14 passed, 2 opt-in footage tests skipped. The frozen-corpus evaluation was executed independently.

## Public pairing extension — 2026-09-28

Small in-system extension of the approved monochrome interface; no new visual
concept gate. Lead: design-preflight-orchestrator; support: Sites hosting.
Added locally rendered expiring QR codes, camera-only links, a private operator
gate and eight-hour remote sessions. Verification: 216 frontend tests, 37 Python
tests and two Worker boundary tests. Physical-phone scanning remains unverified.
Public protocol verification passed against Sites: anonymous rejection, single-use
operator redemption, operator WebSocket, camera-scoped authorization, synthetic
JPEG upload, CUDA processing, preview delivery, logout and unchanged event records.
QR dialog inspected at desktop and 390px width without horizontal overflow. Viewer
capacity increased to eight after concurrent test/operator tabs hit the old limit.

## Follow-up polish and explicit limits

- P3: denser secondary metadata can be enlarged if operators prefer fewer feeds
  per viewport. Sample images intentionally reuse one generated classroom view.
- Physical iPhone/Android tests, mobile data connectivity and background/locked
  capture are unverified; desktop emulation is not device validation.
- No claim of complete WCAG conformance or screen-reader certification. Labels,
  semantic controls, visible focus, dialog keyboard dismissal and layout were
  exercised within the requested flows.
- Accuracy and performance release gates remain experimental/failed as documented
  in `service/evaluation/RESULTS.md` and `CAPACITY.md`. UI QA does not override them.

## Camera-device inference — 2026-09-28

Universal design router → design preflight; direct extension of the already
approved monochrome camera page and dashboard. No new concept selection needed.
Publisher now identifies device GPU/CPU fallback, model loading/failure, original
fight-review observations and the four-person limit. Dashboard coverage and
settings identify camera-device reports rather than PC inference.

Verification: 225 frontend tests, 46 service tests; live public Chromium
fake-camera/model integration plus transport and existing dashboard browser tests.
Actual MediaPipe inference ran on browser CPU fallback, delivered results to the
public relay and dashboard, and survived stop/reconnect. Mobile 390px layout and
rendered screenshot inspected; keyboard controls and error states exercised.
No unexpected page/console errors; MediaPipe emits its known XNNPACK INFO message
through console.error, which is distinguished from application failures.
Relay-only construction verified that torch, onnxruntime and nivra.models are not
imported. No inference queue or RGB temporal buffer is filled for device sources.
Event validation, authorization, deduplication and stale/error states are tested.

Unverified: physical iPhone/Android/low-end hardware, thermal endurance, hardware
GPU performance and real-world fight recall. Prior PC model/capacity evaluations
do not apply to this browser detector. The original pose-rule limitations remain.

final result: passed
