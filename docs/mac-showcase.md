# Mac showcase: local inference and phone cameras

This is an experimental physical-interaction review demo. A connected camera is
not proof of adequate inference coverage. Confirm the runtime and each camera's
analysis state before presenting it.

## Prepare before travelling

1. Use an Apple Silicon Mac, with Python 3.11 managed by `uv`, Node/npm, and
   `mkcert` available. If Homebrew is already installed: `brew install uv node mkcert`.
   Allow several GB for packages and pinned model weights. Copy the repository;
   do not copy the Windows `service/.venv` directory.
2. In the repository root, run `bash scripts/start-mac.sh` while online. It creates
   the venv, installs pinned non-CUDA dependencies, verifies/downloads models,
   prepares browser models, runs `npm ci` and the build, then starts the service.
   An existing incompatible venv fails with a clear message instead of being deleted.
   Ctrl+C stops this instance. Rerunning is safe; downloads verify existing hashes.
3. Decide authentication before the venue. Clerk needs internet for sign-in and
   verification. Set `VITE_CLERK_PUBLISHABLE_KEY` before the frontend build, and
   `CLERK_SECRET_KEY`, `CLERK_ISSUER`, `NIVRA_AUTH_MODE=clerk` in the service's
   environment. Configure the session token metadata and reviewer/admin roles
   described in [the shared contract](command-system-contract.md#1-identity-and-auth).
   Never put a secret key into a `VITE_` variable.
4. For an offline, explicitly labelled demo, use `NIVRA_AUTH_MODE=dev` and the
   Developer sign-in on a loopback/private LAN host. This is not Clerk authentication.
   Test the actual chosen mode; a cached login is not an offline readiness test.

## At the venue

1. Connect the Mac and all camera phones to the same network. Guest Wi-Fi often
   isolates clients: internet may work while phone-to-Mac connections fail. Ask
   for a network without client/AP isolation. If unavailable, use a tested travel
   router or phone hotspot with all devices on it. Some hotspots also isolate
   clients or prevent the hosting phone from reaching peers; test this topology.
2. Run `bash scripts/https-mac.sh` after connecting. It installs the local mkcert
   CA on the Mac (macOS may ask for permission) and generates a certificate for
   `nivra.local`, `localhost`, loopback, and detected LAN IPv4 addresses. It writes
   a private, gitignored `service/state/tls/mac-env.sh` containing paths and exact
   origins. The printed LAN-IP URL is preferred: a certificate alone does not
   create DNS for `nivra.local`. Rerun after changing network/IP.
3. Transfer only `rootCA.pem` from `mkcert -CAROOT` to the demo phones, for example
   using AirDrop or a cable. Never transfer `rootCA-key.pem` or `mac-key.pem`.
   On iPhone, open the certificate, install its downloaded profile, then enable
   full trust under Settings → General → About → Certificate Trust Settings.
   Installation alone is insufficient. See [Apple's trust instructions](https://support.apple.com/en-gb/102390).
   On Android, install it as a CA certificate under Security → Encryption &
   credentials → Install a certificate (names vary by vendor). Test in Chrome;
   managed devices can prohibit user CAs. See [mkcert's mobile instructions](https://github.com/FiloSottile/mkcert#mobile-devices).
4. For Clerk, use the exact scheme/host/port you will open. Set
   `NIVRA_AUTHORIZED_PARTIES` to the actual browser origins, including the printed
   `https://LAN-IP:8443`. `NIVRA_ALLOWED_ORIGINS` is generated for local HTTP/WS
   requests; it does not configure Clerk. Configure allowed development/redirect
   origins in your existing Clerk instance where applicable, and test sign-in
   from the venue URL. A production Clerk instance is domain-bound; do not assume
   adding a LAN IP makes production sessions work. Use a previously configured
   development instance or the explicit dev mode if the domain setup is unavailable.
   See [Clerk environments](https://clerk.com/docs/guides/development/managing-environments).
5. Run `bash scripts/start-mac.sh`. It sources the generated TLS environment,
   serves HTTPS on all interfaces at port 8443, and reads H1's origin allowlist.
   Allow incoming Python connections through the Mac firewall when prompted.
   Use the printed `/wall` URL on the Mac; pair cameras from the setup interface
   and open each QR link in the phone's normal browser. Grant camera access.
6. Keep phones awake, plugged in, and on the camera page. Keep the Mac powered
   and awake (`caffeinate -i` in another terminal is sufficient). Test the longest
   intended demonstration with all 2–6 phones connected, not just one.

## Runtime and fallback

The launcher selects RTMO + X3D. `NIVRA_DEVICE=auto` chooses CUDA, then MPS, then
CPU; `NIVRA_DEVICE=cpu` forces CPU inference. ONNX uses CoreML when available on
MPS, otherwise CPU. The X3D profile no longer also runs SlowFast. The models remain
uncalibrated; removing unused AVA work does not establish detection accuracy.
Device selection follows [PyTorch MPS availability](https://docs.pytorch.org/docs/main/notes/mps.html)
and [ONNX provider precedence](https://onnxruntime.ai/docs/api/python/api_summary).

The service keeps one newest pending detection job per camera and schedules
fairly. It drops work older than 1.5 s, budgets analysis to measured latency,
and caps per-camera analysis at 6 fps. Input preview cadence is independent.
`runtime.device`, `analysisMs`, and `targetFpsPerCamera` expose the selected path
and current budget. Temporal RGB history is independently bounded and resized.

After at least 12 measured jobs, CPU/MPS overload below approximately one
analysis per camera per second automatically switches to browser-device analysis.
Unsupported CPU/MPS inference also switches; Mac model-load failure switches at
startup. `runtime.device= "camera-device"`, `compute= "camera-device"`, and
`fallbackReason` disclose this. Browser detector status must reach `ready`;
fallback cannot make an unsupported phone analyse. A restart retries local models.
`NIVRA_RELAY_ONLY=1` explicitly starts in relay mode. `NIVRA_AUTO_RELAY=0` disables
automatic fallback for controlled measurements, not for a reliable live demo.

## Incident replay

The server samples received JPEGs at no more than 6 fps, keeping 10 seconds per
camera. A newly persisted event freezes that history and collects 8 seconds
after event registration. The peak is the server's event-registration epoch time,
not a claim about the physical instant of contact; source clocks are phone-local.
Short initial history or disconnection produces a partial clip without fabricated
frames. Rolling buffers are cleared on disconnect; captured clips survive it.

JPEGs never go to disk. The 120 MiB combined compressed ring/clip budget counts
shared references conservatively, evicts oldest captured clips first, then old
rolling frames. Clips expire after 15 minutes, on dismiss/clear, or restart.
This is a JPEG-store cap, not a cap on model weights or decoded inference RAM.
Manifests require reviewer/admin. Frame URLs are bearer capabilities signed by
the shared signer for 5 minutes, return `image/jpeg` with `Cache-Control: no-store`,
and stop working immediately when the RAM clip is deleted.

## Before judges arrive

- Open the exact HTTPS URL on every phone without a certificate warning.
- Confirm auth mode, reviewer identity, pairing, camera permissions, and no Wi-Fi isolation.
- Confirm every live camera has current analysis; read runtime fallback reason if present.
- Perform a controlled sample replay and inspect the resulting incident clip.
  A clip must remain after camera disconnection and disappear after dismiss/clear.
- Confirm floor/guard workflow separately with the other helpers' checklist.
- Test with 2–6 simultaneous cameras for the planned duration, powered and awake.
- Keep the tested hotspot/router fallback ready. Changing IP requires certificate
  regeneration, restarting, updating authorized origins, and repairing cameras.
- Do not present desktop measurements as Mac results. MPS/CoreML execution,
  phone CA trust, Clerk sign-in, thermals, and venue Wi-Fi need actual-device QA.

## Repeatable backend measurement

On the Mac, after setup:

```shell
cd service
.venv/bin/python verify_camera_runtime.py --device cpu --cameras 2 --seconds 30
.venv/bin/python verify_camera_runtime.py --device mps --cameras 6 --seconds 60
```

The harness uses real model weights and paced JPEGs through the actual
`/api/v2/camera/stream` handler with in-process ASGI WebSocket transport and a
disposable metadata database. It does not bind ports or touch the running service.
It reports latency, analysed frames per camera, events, and captured clip counts.
It does not measure Wi-Fi, TLS/network overhead, or phone browser performance.
