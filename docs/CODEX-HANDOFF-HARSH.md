# NIVRA handoff for Harsh and Codex

Updated 23 October 2026. Start by reading this file, then inspect the current checkout before changing anything. Some older sections of the main README describe superseded model pipelines. The source and the evaluation documents linked below are more precise for this release.

## Repository and published version

- GitHub: https://github.com/harshofficial951641/nivra-vision-lab
- Website: https://nivra.tanishq.work
- Source checkpoint at handoff: `8b27691`. This includes the tested metadata-burst patch. The public frontend is at `7179cb1`; the burst patch has not yet been loaded by the live backend.
- Published Vercel deployment: `dpl_7fe4Geb8PJbM6STTuxddFefKAQ1G`. Its status was Ready and its served frontend bytes matched the build. A later handoff/documentation commit may sit above that checkpoint.
- Final 90-second public QA before the burst patch: **FAILED repeated `Camera metadata rate exceeded` closes despite ready models. The temporary QA workspace was deleted successfully. The bounded metadata token-bucket fix passes unit/integration checks but is not yet deployed or publicly verified.** Do not infer a pass from the deployment status.

The user wants a working security-camera product, not another redesign or a model demo. The wall should feel like fullscreen CCTV footage. Setup must be short, plain, black and white, and use one camera-management flow. A Mac shows a QR, the phone scans it, and the owner can see whether the phone is linked and whether video is actually live. Camera name, floor and place details should stay easy and optional where possible. Remove must be obvious. Do not recreate the duplicate guided and maintenance setup systems that were removed.

Keep guards, human review, quiet alerts, GPS and Google Maps. There are no uploaded floor plans in the normal flow. Floor is a staff-entered label; GPS cannot infer it reliably. The user also wants observations of 20+ students. Capacity is 32 observations, but the current fast action lane checks at most four poses. Never present these as equivalent coverage.

## Clone and run

Use Node 24, npm and Python 3.11. Commands below use `<repo>` as the checkout location; do not copy another person's virtual environment.

```sh
git clone https://github.com/harshofficial951641/nivra-vision-lab.git
cd nivra-vision-lab
npm ci
npm run dev -- --host 127.0.0.1
```

Vite normally serves port 5173. `/lab` works as a browser-only camera/video experiment. The multi-camera setup and wall need the Python API as well; a Vite page alone is not a complete running classroom service.

For a prepared Mac, `bash scripts/start-mac.sh` creates/checks the Python 3.11 environment, installs `service/requirements-mac.txt`, prepares experimental Python and browser models, builds the frontend, and runs the service. This first setup needs internet and several GB. It is the broader experimental local-AI launcher, so read it before invoking it just to inspect the website.

For a lightweight browser-compute service in an already prepared environment:

```sh
npm run build
cd service
NIVRA_RELAY_ONLY=1 .venv/bin/python -m nivra.server
```

It normally serves `http://127.0.0.1:8765`. Browser camera access from another phone needs a trusted HTTPS origin; plain HTTP on an arbitrary LAN address is insufficient. Use the public website for the internet phone flow. Do not expose an unrestricted developer-admin listener publicly. `docs/mac-showcase.md` describes local HTTPS preparation for older showcase workflows.

For the prepared offline Mac installation, open `Start NIVRA.command`. It starts the local host and opens `http://127.0.0.1:8870/local`. A fresh offline installation also needs the LAN dependency in `service/requirements-local.txt`, local assets built with `npm run build:local`, and the native app/model preparation described below.

## Routes and ownership

Public visitors can create a private workspace through `POST /api/v2/workspaces`. They should reach real setup without first obtaining a private owner QR. Owner verification is deferred. Isolation still matters: this is a private browser capability, not shared anonymous admin access. The persisted owner cookie lasts up to 30 days; losing it can lose convenient access to that workspace. Do not overwrite a real browser's owner cookie during QA.

Main routes:

- `/setup`: the single site, camera and guard management interface.
- `/wall`: CCTV grid, expansion/fullscreen, review and GPS/Google Maps views.
- `/camera`: paired browser camera, permissions, video and device analysis.
- `/guard`: paired guard shift, location and incident actions.
- `/lab`: original single-source browser lab and video review.
- `/local`: local native-camera setup on the separate port 8870 host.

`src/setup/SetupPortal.tsx`, `PairingPanel.tsx` and their CSS own setup and QR presentation. The old `OwnerOnboarding.tsx` exists in the tree but must not become a second runtime setup flow. Viewing setup must not silently create cameras or mint pairing credentials. New workspaces begin empty. Saved offline cameras can be real devices; do not delete them merely because they have no live socket.

Useful API code is in `service/nivra/classroom.py`, `sites.py`, `classroom_store.py` and `workspaces.py`. Camera creation, edit, delete and pair endpoints are under `/api/v2/cameras`. Camera and guard pairing accept either a fragment token or the eight-character backup code. Invitations expire after five minutes. Pairing credentials are hash-only, scoped to immutable device UUIDs, and persisted in each workspace SQLite database. Camera cookies are bounded to 30 days; guard cookies retain a 12-hour lifetime. Re-pairing, revocation and removal must invalidate old credentials and sockets. Never route a cookie into a different workspace through a reused camera name or guard callsign.

Camera and guard location updates are scoped to the paired phone. Incident GPS is frozen when the incident is created, so directions do not move with a later camera relocation. Guard floor updates use `PATCH /api/v2/guard/profile`. Camera `paired` and `live` are separate states: a paired phone may not have started capture.

Owner review uses `POST /api/v2/events/{id}/review` and revision checks. Closing an undecided alert retains history instead of declaring a false alarm. Dismiss/clear removes its temporary clip. Do not erase all old event records to tidy the UI. Demo data and test incidents must stay visibly labelled.

## Current browser detection

Read `docs/evaluations/browser-crowd-upgrade/README.md` and `model-manifest.json` in that directory. The active publisher has two independent lanes:

1. RTMO-t Body7 observes crowd boxes and skeletons on CPU/WASM, up to 32 admitted observations. It does not create a duplicate set of crowd motion alerts.
2. MediaPipe Full VIDEO runs the original fast motion checks on up to four poses. It retains its own status, source timestamps and result. Crowd results must not overwrite motion results or imply 32-person action coverage.

The pinned RTMO graph is `public/models/rtmo-t-body7-416-20aad6e2.onnx`, 27,342,008 bytes. SHA-256 is `20aad6e2e42359cac1c5b4a0b2da00e29bfe91a72a782fdcf287d273a04c1b24`. Input is float32 BGR 0..255 at 416x416, top-left aspect-fit letterboxing with value 114. It produces boxes and COCO-17 keypoints. Map only actual observed joints into the nullable 33-slot protocol. Do not invent hands, heels, toes or hidden bodies.

Product admission uses score 0.25, minimum box size and matched box/pose suppression at 0.65 IoU. The production CPU worker took median 295 ms on F07, 280 ms on C01 and 332 ms on the synthetic dense fixture with two WASM threads on the tested Mac. That is roughly three crowd observations per second. The tiled fixture yielded 20 observations, but it repeats one two-person image ten times and is not a real 20-student validation set.

Both ONNX Runtime Web 1.30 GPU paths tested, native WebGPU and legacy JSEP, returned inflated counts, including 32 capped detections on that fixture. They were rejected despite being faster. Do not enable GPU merely because initialization succeeds or the schema accepts its output.

Key files are `DeviceVision.ts`, `CrowdPoseVision.ts`, `crowdPoseGeometry.ts`, `deviceAnalysis.ts`, `capacity.ts` under `src/classroom`, plus `src/workers/crowdPose.worker.ts`. `src/lib/originalConflictEngine.ts` restores the historical published motion engine with integration additions; `conflictEngine.ts` also exists and has different behavior. Check the actual caller before changing thresholds. Original standard checks require repeated qualifying directed arm-motion episodes, visible usable bodies and temporal continuity. These are motion rules, not a trained fight classifier or a calibrated probability of violence.

The preselected positive F07 grab/push and negative C01 busy corridor both produced zero alerts in the fresh original-pose replay. F07 is a missed incident. Neither this release nor the native classifier establishes 90% accuracy. Do not hide that miss or tune thresholds on those two inspected clips and call the result validation.

## Video, reconnection and diagnosis

`browserVideoEncoder.ts` uses H264 toward 40 fps; `NativeVideoCanvas.tsx` decodes/displays it. `Publisher.tsx`, `frameWindow.ts` and `deviceReportQueue.ts` bound transport and metadata. Latest frames, not stale queued work, matter. Backpressure recovery waits for a fresh keyframe. Unsupported or failed encoding falls back to bounded JPEG capture.

The encoder has a 15-second initial-source allowance and a three-second watchdog only while encoded work is pending. Idle-to-active input resets that deadline. Publisher permits three delayed compressed-video retries at 1.5, 3 and 6 seconds. Stop/reconnect cancels them. Reconnection retains healthy capture and model workers, resets transport generation, and requires acknowledgements from the current socket. Do not respond to every network interruption by reacquiring camera permissions and reloading both models.

The server now returns fixed, non-sensitive policy-close categories for schema, metadata/video/JPEG rate, delegate mismatch, timestamps, video negotiation and timeout. It never returns the rejected payload or validation details. A shared model ID across result and motion lanes is valid; their clocks are tracked separately. Normal queues cap reports at 5 plus 10 per second. The longer public test confirmed that the strict rolling 24-per-second metadata window falsely disconnects batched network delivery. The source now replaces it with a token bucket allowing sustained 24 messages/second and a bounded 48-message burst. The live backend must be updated and publicly verified. Packet byte limits and the separate video limit stay enforced.

Computer evidence so far: a local combined synthetic pipeline drew 39.8 fps with both models; an earlier public 30.9-second sample drew 39.3 fps and recovered three forced disconnects in 2.6-3.4 seconds without model reload. A policy rejection occurred before that steady sample. The subsequent 90-second check failed with repeated metadata-rate rejections; it does not extend the earlier steady result. These are computer/synthetic measurements, not an iPhone or long-duration guarantee. Keep video draw fps, incoming fps, crowd Hz and motion Hz separate. Public verification of the rate fix has not run yet.

## Hosting and native/offline boundaries

The public frontend is Vercel. Its Node relay is `scripts/deploy/vercel-relay.mjs`, packaged by `prepare_vercel.mjs`. A Mac runs the persistent Python backend, SQLite and an authenticated Cloudflare Quick Tunnel. `service/run_public.py` exposes loopback application port 8765 and gated relay port 8766. `public_gateway.py` validates relay credentials and one-use scoped WebSocket tickets, including echoing the accepted ticket subprotocol. `workspaces.py` routes isolated owner/camera/guard sessions. This is a Mac-backed pilot; Vercel Ready alone does not prove the backend is reachable.

`public_host.py`, `public_host_service.py` and `vercel_environment.py` manage supervision, environment publication and deployment. The health monitor checks the actual application, local gateway and WAN control before restarting a blackholed tunnel. LaunchAgent status, runtime JSON and network checks have different meanings; a live PID is not public readiness. Read `docs/public-deployment.md` before touching them. Never start a second host, rotate a relay secret, change scope, or restart the live service just to run tests.

Native iOS code is in `mobile/ios/Nivra`, built from `project.yml`; scripts and signing requirements are in `mobile/README.md`. The iPhone development IPA only installs on appropriately registered devices. Android currently provides online WebView roles and QR scanning, not offline native LAN capture. Neither app provides native background guard tracking or APNs/FCM delivery.

Offline router mode uses the iPhone app, Mac port 8870, pair-only LAN port 8871 and authenticated phone reads on port 8940. The Mac QR starts native capture and pairing; Bonjour identity survives address changes. `run_usb.py` retains its historical name although it also hosts wireless cameras. `lan_transport.py` restricts peers to private IPv4 and bounds requests. Apple Vision and the converted float32 X3D candidate run on the phone. `NativeFightVision.swift` preserves real four-second windows and original preprocessing/scores; `native_camera.py` validates source reports. CoreML conversion fidelity was tested, but this does not prove fight accuracy. Model packages and original trained checkpoints may be absent from a fresh clone; follow provenance/export instructions and never silently substitute a different artifact. Google Maps and the existing guard flow need internet. See `docs/offline-wireless.md`.

## Verify and continue

```sh
npm run lint
npm run test
npm run build
cd service
.venv/bin/python -m pytest tests/test_classroom.py tests/test_device_analysis.py -q
```

At this checkpoint, 651 web tests and 194 targeted backend tests passed. A further 32 focused encoder/Publisher tests passed after the idle-input watchdog correction. These counts are recorded release evidence, not a claim that every optional research/model test passed on a fresh machine.

Next, coordinate deployment of the bounded metadata-rate fix with the current host owner (avoid overlapping restarts), publicly verify it, record its result and QA cleanup, then test representative real motion and dense scenes with independent labelled recordings. Preserve recording-level splits and report misses and false alerts. Acceptance means one setup flow, scoped pairing/removal, fresh video and source-matched marks, honest coverage, bounded reconnect behavior, and reviewable alerts. It does not mean every fight is detected.

Use synthetic isolated QA workspaces and delete them through `DELETE /api/v2/workspaces/current`. Never use a real owner's browser session for destructive tests. Do not commit cookies, tokens, relay secrets, `.env` files, runtime state, SQLite databases, signing material, person footage or private landmark dumps. Share this document and repository context; provision credentials separately through an authorized channel. Keep changes small, inspect existing code first, and use subagents for independent audits when requested.
