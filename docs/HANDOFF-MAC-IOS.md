# Mac and iOS handoff for `harsh/police-and-detector`

Written 23 October 2026 on a Windows PC without Xcode, an Apple device or the Android SDK.
Everything below needs a Mac, a physical phone or the live host. None of it was verified on Windows.

## 1. Police contact inside the native apps (required)

The website now offers **Police → Call 112 / Text police** on the guard alert, the guard response
screen and the reviewer's review window. Contacts are logged in the incident history.

Both native wrappers currently swallow `tel:` and `sms:` navigations, so the buttons do nothing inside the apps.
They work in Safari and Chrome.

- **iOS** (`mobile/ios/Nivra/WebSession.swift`, `webView(_:decidePolicyFor:decisionHandler:)`) cancels every
  scheme except `about` and `https`. Open `tel:` and `sms:` with `UIApplication.shared.open(url)` before
  cancelling the WebView navigation. The exact snippet is in section 5.
- **Android** (`MainActivity.java` and `UrlPolicy.java`): the fix is in this branch (`ACTION_DIAL` / `ACTION_SENDTO`),
  with JUnit cases in `UrlPolicyTest.java`. It was **not built**. Run the Gradle unit tests and an install on a phone.

Physical checks on each platform, in the browser and in the app:
- Tap Police, then Call 112. The dialer must open with 112 filled in and must not dial automatically.
- Tap Text police. The messaging app must open with the camera name and location pre-filled.
- Afterwards, the wall shows "Police contacted (call/text) by … at …".
- On the Mac wall, `tel:` opens FaceTime or iPhone Continuity. Confirm this works for the reviewer.

## 2. Browser detector changes

Any detector change in this branch is browser-only: `DeviceVision`, the RTMO crowd lane and the conflict engine.
The iPhone native path (Apple Vision + Core ML X3D in `NativeFightVision.swift`) is unchanged and needs no rebuild for it.
See `docs/evaluations/detector-accuracy/README.md` for what changed, what is on by default and the measured effect.
Check on real phones:
- Crowd CPU load and camera frame rate with the new defaults on an iPhone (Safari) and a mid-range Android phone.
- 10+ minutes of continuous camera operation without thermal throttling or reconnect loops.

## 3. Live host (Tanishq)

- Redeploy the bounded metadata token-bucket fix that was already in `8b27691`, plus this branch once it is reviewed.
  Then run the public 90-second stability check (`scripts/evaluation/browser-speed/run.cjs`).
- Never run two hosts at once. Follow `docs/public-deployment.md`.

## 4. Still unverified anywhere

- iPhone/Android lock-screen or background behaviour of guard alerts and of the police controls.
- Real classroom footage: the accuracy numbers come from the VID dataset with AI-made labels, not venue recordings.

## 5. iOS code change (from the police task)

In `mobile/ios/Nivra/WebSession.swift`, inside `webView(_:decidePolicyFor:decisionHandler:)`, keep the internal-navigation
checks above it unchanged. Replace the HTTP-only external-opening line and its trailing cancellation with:

```swift
if ["https", "http", "tel", "sms"].contains(url.scheme ?? "") {
    UIApplication.shared.open(url)
}
decisionHandler(.cancel)
```

Then build on a Mac and verify on a physical iPhone. The dialer and Messages composer must open, and nothing may dial automatically.

## 6. Android build check

Run the JUnit cases in `mobile/android/app/src/test/java/work/tanishq/nivra/UrlPolicyTest.java` and an Android Studio build.
`UrlPolicy.externalScheme` routes `tel:` to `ACTION_DIAL` and `sms:` to `ACTION_SENDTO` with `sms_body`.
Neither was compiled here: this PC has no JDK or Android SDK.

## 7. Android: possible lost police log (suspected, review finding)

`src/classroom/contracts.ts` waits for a token before starting the keepalive logging request.
`MainActivity.java` may unload the WebView as soon as the dialer opens, which could drop that request before it starts.
On a real Android phone, check that tapping Call 112 still records "Police contacted" on the wall.
If it doesn't, start the logging request before the external intent fires, or log it from native code.

## 8. Video fight classifier on the Mac backend (new)

`service/nivra/video_classifier.py` decodes the existing browser H264 camera stream on the backend with PyAV.
It scores a 4 s window per camera about once a second with MoViNet A0 (`service/nivra/assets/movinet_a0_fight.pt`, checksum in `model-manifest.json`).
It records "Video classifier: possible physical conflict" events for human review.
`NIVRA_VIDEO_CLASSIFIER=auto` (the default) follows `docs/evaluations/video-classifier/policy.json`, which has `defaultEnabled: true`. `off` loads nothing and restores the previous behaviour.

Before relying on it, check on the Mac:
- The device is reported honestly in the health/runtime snapshot (MPS or CPU) and the four-camera load stays acceptable. Run `service/benchmark_video_classifier.py`; instructions are in `docs/evaluations/video-classifier-integration/README.md`. On Windows: CPU batch-4 ≈ 211 ms p50, CUDA ≈ 84 ms, decode about 20% of one core for four 720p/40 fps cameras.
- 10+ minutes of four cameras without watchdog restarts, loop lag or thermal slowdown on the fanless Air.
- **False alarms on real cameras.** The held-out test had 0 false alerts in only 13.4 minutes of usable normal footage (Poisson upper bound about 16/h), and caught 11/53 = 21% of labelled fights. The threshold is extreme (0.999), so real-camera compression and lighting can shift scores. Watch the alert rate for the first days; if it exceeds ~2 per camera-hour, set `NIVRA_VIDEO_CLASSIFIER=off` or raise the thresholds in `policy.json`.
- The native iPhone camera path and JPEG-only fallback cameras are not analysed by this classifier.
