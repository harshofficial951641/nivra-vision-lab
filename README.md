# NIVRA Vision Lab

On-device pose tracking and motion-review alerts in the browser. Open a camera or a local video, see skeleton overlays, and review repeated directed arm movements with a visible alert and optional sound.

This is an experimental motion-rule prototype, not a trained fight classifier or a crime detector. Sports, play, missed poses, and occlusion can produce mistakes. Every alert needs human review.

## Run locally

Use Node.js 24 and a current Chrome browser. From this repository's root:

```bash
cd nivra-vision-lab
npm ci
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173/`. Wait for `Waiting for camera`, then select **Start camera** or **Video file**. Do not open `index.html` directly.

MediaPipe models and WASM are included locally. Once dependencies are installed, inference does not need internet access. Frames stay on the device; the application does not upload or record them.

## What is included

- React, TypeScript, and Vite application in [`nivra-vision-lab/`](./nivra-vision-lab/).
- Full and Lite pose models, up to eight pose observations, and aligned skeleton overlays.
- CPU video review at fixed 40 ms source intervals, with pause, resume, and replay. Detailed review can run slower than normal playback.
- Real-time camera analysis with GPU when available and CPU fallback.
- Optional object watching, local alert tones, diagnostics, and unit/browser tests.

Phone streaming, a command-room backend, responder dispatch, and validated real-world fight classification are not implemented in this repository.

## Verify

From `nivra-vision-lab/`:

```bash
npm run verify
npx playwright install chromium
npm run test:e2e
```

The supplied-video diagnostic is opt-in. It is skipped unless `NIVRA_TEST_VIDEO` names a local file. Test traces and screenshots are excluded from Git.

See the [application README](./nivra-vision-lab/README.md) for controls, diagnostics, test commands, and detection limits. See [third-party notices](./nivra-vision-lab/THIRD_PARTY_NOTICES.md) and [test-fixture provenance](./nivra-vision-lab/tests/fixtures/README.md) for bundled assets.
