# Connect cameras over offline Wi-Fi

Open **Start NIVRA.command** on the Mac, or use [the local camera setup](http://127.0.0.1:8870/local) if it is already running.

1. Turn on your Wi-Fi router. Its internet cable can stay unplugged.
2. Join that same Wi-Fi from the Mac and camera iPhones. Avoid a guest network that prevents devices from reaching each other.
3. On the Mac, click **Add camera**. It shows a QR code.
4. Open the updated NIVRA iPhone app, tap **Scan to connect**, and scan the Mac's QR. Allow Camera and Local Network access. The phone starts its camera and connects automatically. No code entry or Mac camera is required. Older connection methods are under **Troubleshooting**.
5. Choose **Watch cameras**. Use **Remove** to disconnect a camera.

The Mac launcher now opens this local setup and runs the host independently of the terminal. Old USB shortcuts open the same setup. Camera name and floor are optional, and cameras keep a stable identity across local address changes. Keep NIVRA visible on the phones. Camera capture pauses when the app goes into the background and resumes with the same in-memory pairing when you return. Stop or Done disconnects it; closing the app completely requires scanning again. The Mac host prevents idle sleep while it runs. The public website remains the separate internet-connected option.

## Internet, speed and signal

Video travels directly from the native iPhone app to the Mac over your Wi-Fi router. The updated native app runs the trained X3D fight candidate through Core ML and observed body joints through Apple Vision on the camera phone. The Mac relays video, applies review rules to completed reports and stores incident records. It does not load the detector models in this local mode. Once the app and dependencies are installed, local video and analysis do not call an internet service.

The updated app requests 720p at approximately 40 video frames per second on supported camera formats, using hardware H.264. Unsupported 40 fps capture formats use 30 fps. The wall decodes video separately from inference, with 750 ms of playback buffering to absorb observed Wi-Fi packet bursts. Its displayed receive rate measures incoming frames, rather than the configured target. Ordered compressed packets are bounded; a gap waits for the next keyframe. A low-rate JPEG path supplies review clips and a browser fallback. Observed skeletons are matched to the displayed source timestamp and hidden when no sufficiently close report exists. Wireless interference, range, router isolation, a locked phone or an inactive camera app can still interrupt video.

One physical iPhone delivered 40.74 compressed frames per second to the Mac during a 5.01-second sample. The previous browser player drew only 6.6 frames per second during a separate five-second check. The player now has larger bounded queues, 750 ms of buffering and clock recovery after late packets; its physical-phone display rate still needs a fresh check. The browser decoder previously sustained 39.99 fps over 300 synthetic 1280×720 H.264 frames and recovered after an intentional gap. Synthetic Mac hardware encoding preserved 25 ms source timestamps. Fight analysis needs a real four-second source window and runs independently of video playback.

Google Maps, remote push delivery and the existing online guard-phone flow still need internet. Local camera mode does not provide an offline guard dispatch network. Android local camera support has not been implemented.

## Installation and checks

The updated native app must be installed before going offline. The signed iPhone development build is at `mobile/artifacts/Nivra-iPhone-Development.ipa`; installing it on a physical phone still depends on the phone's existing Apple development pairing and permissions.

For this prepared Mac, the launcher uses its existing service environment. A fresh environment needs the dependencies in `service/requirements-local.txt`, Node dependencies and `npm run build:local` before going offline. Building the native app also requires the verified float32 Core ML artifact in `mobile/ios/Models/NivraX3D.mlpackage`. The source weights and generated package are excluded from Git; `mobile/scripts/export-x3d-coreml.py` reproduces it from the pinned checkpoint in `service/models`. `mobile/ios/Models/provenance.json` records the checkpoint hash. The exporter requires the original X3D research dependencies plus `coremltools` and refuses to save a conversion that fails numerical parity. Do not substitute the rejected FP16 conversion.

The dashboard listens only at `127.0.0.1:8870`. A separate bounded LAN listener on `8871` accepts only phone pairing requests. The Mac QR contains validated private addresses and a five-minute pairing capability. It grants no admin access. Up to sixteen concurrent QR codes stay valid so another open tab cannot invalidate a visible QR. Same-phone retries are safe, while different sessions cannot reuse a consumed QR. Camera phones advertise `_nivra-camera._tcp` and accept authenticated reads on local port `8940`; discovery advertises no connection key. Native analysis and compressed-video negotiation are accepted only by the local host, not the public relay.

Verified: signed device build, thirty-six native tests, actual compiled Core ML outputs matching the original Python gray fixture, equivalent RGB/NV12 capture preprocessing, H.264 encode/decode, bounded LAN reads, session revocation, pause/resume intent, source clocks, stale-report rejection and reconnect alert deduplication. The float32 converted model differs from original PyTorch by less than 2.4e-7 on generated inputs. This checks conversion fidelity, not fight-detection accuracy.

An isolated replay of two videos found a missed grabbing/pushing incident and correctly left a normal busy corridor without an alert. These two examples do not establish 90% accuracy. The replay used the actual float32 Core ML model and native preprocessing on Mac CPU; it did not measure phone scheduling or end-to-end alert latency. The reproducible scripts are `mobile/scripts/evaluate-native-clips.swift` and `mobile/scripts/report-native-clips.py`. No production thresholds were changed to fit these clips. Physical multi-phone performance and crowded-classroom fight accuracy remain unverified.

The browser camera already uses MediaPipe Full for its fast four-pose lane and Lite for per-person crowd crops. These are pose models, not the trained X3D classifier. Native Apple Vision observes seventeen joint types mapped into nullable 33-slot skeletons; unsupported joints stay absent. Neither a configured 32-person capacity nor synthetic tests prove that every student is visible or that all fights will be detected.
