# Connect cameras over offline Wi-Fi

Open **Start NIVRA.command** on the Mac, or use [the local camera setup](http://127.0.0.1:8870/local) if it is already running.

1. Turn on your Wi-Fi router. Its internet cable can stay unplugged.
2. Join that same Wi-Fi from the Mac and camera iPhones. Avoid a guest network that prevents devices from reaching each other.
3. On the Mac, click **Add camera**. It shows a QR code.
4. Open the updated NIVRA iPhone app, tap **Scan to connect**, and scan the Mac's QR. Allow Camera and Local Network access. The phone starts its camera and connects automatically. No code entry or Mac camera is required. Older connection methods are under **Troubleshooting**.
5. Choose **Watch cameras**. Use **Remove** to disconnect a camera.

The Mac launcher now opens this local setup and runs the host independently of the terminal. Old USB shortcuts open the same setup. Camera name and floor are optional, and cameras keep a stable identity across local address changes. Keep NIVRA visible on the phones. The Mac host prevents idle sleep while it runs. The public website remains the separate internet-connected option.

## Internet, speed and signal

Video travels directly from the native iPhone app to the Mac over your Wi-Fi router. The Mac loads its detector models from local files. Once the app, models and dependencies are installed, local video and analysis do not call an internet service.

The camera now targets 20 video frames per second, independently of slower detection. Both ends keep the newest frame rather than a backlog. The wall no longer substitutes historical detection frames for live video. Wireless interference, range, router isolation, a locked phone or an inactive camera app can still interrupt video. Detection cannot examine frames that never arrive.

The same-Mac authenticated HTTP/decode check received 19.05 fps at the 20 fps target. This used a synthetic JPEG through the Mac's private network address; it is not a measured physical iPhone Wi-Fi frame rate.

Google Maps, remote push delivery and the existing online guard-phone flow still need internet. Local camera mode does not provide an offline guard dispatch network. Android local camera support has not been implemented.

## Installation and checks

The updated native app must be installed before going offline. The signed iPhone development build is at `mobile/artifacts/Nivra-iPhone-Development.ipa`; installing it on a physical phone still depends on the phone's existing Apple development pairing and permissions.

For this prepared Mac, the launcher uses its existing service environment. A fresh environment also needs the additive dependencies in `service/requirements-local.txt`, the server model files, Node dependencies and `npm run build:local` before going offline.

The dashboard listens only at `127.0.0.1:8870`. A separate bounded LAN listener on `8871` accepts only phone pairing requests. The Mac QR contains validated private addresses and a short-lived pairing capability. It grants no admin access. Same-phone retries are safe, while different sessions cannot reuse a consumed QR. Camera phones advertise `_nivra-camera._tcp` and accept authenticated reads on local port `8940`; discovery advertises no connection key.

Verified: native simulator/device builds, LAN discovery and HTTP bounds, camera-session revocation, local model loading, sustained 20 fps target pacing, recovery after transient disconnects, and strict frame acknowledgements. Native capture tests cover 30 Hz sensor timing without a frame backlog.

On 22 October 2026, one physical iPhone connected through the older phone-QR fallback. A 5.02-second sample received 10.56 video frames per second. This is a short one-phone measurement, not a 20 fps or four-phone guarantee. The new Mac QR was recognized but the phone reported a connection error; that direction still needs device verification. Generating a QR in another Mac tab currently invalidates the previous tab's QR, which can produce that error. Native error classification has been added to distinguish expired codes, denied local-network access and actual network failures; those latest diagnostics are not yet installed on the phone.

Offline inference still runs on the Mac in this checkpoint. Moving the model onto the phone is the next requested change. Crowded-classroom and fight-detection accuracy remain unvalidated.
