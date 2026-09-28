# Public camera pilot — updated 2026-09-28

Harsh authorized live frames through an encrypted Cloudflare/Sites relay without
saving video. The current public publisher runs the original Nivra detector on
the camera device: MediaPipe Pose Lite on GPU where available, an explicit device
CPU fallback otherwise, and the existing single-hit motion rules. Event records
stay on the PC. `run_public.py` starts a relay-only app and does not load PC AI
models. The PC still uses ordinary CPU/RAM for the relay, previews and metadata.
Physical iPhone/Android use over mobile data remains unverified. The older
configuration notes below are historical.

This is a four-person experimental browser detector, not a trained video-action
fight classifier or validated 30–50-person classroom system. Original shoulder,
overlap and motion-rule limitations still apply. The phone shows its actual
GPU/CPU delegate and any inference failure; there is no silent fallback to PC AI.
The phone OS/browser controls its GPU memory allocation; phone memory is not
pooled with the PC. Keep the camera page foregrounded and powered.

## Current public journey

1. Keep the dashboard/relay PC, public Python service and tunnel running.
2. On the local dashboard choose Settings → Open public dashboard. The private
   invitation works once within five minutes and creates an eight-hour session.
3. Add/select a camera, choose Connect device, and scan its QR with the phone's
   Camera app. Tap the link, allow camera access, then Start camera.
4. Keep the phone browser in the foreground. Stop on the phone or Pause on the
   dashboard. Re-pairing revokes the earlier device.

Site: https://nivra-vision-lab.topperly.chatgpt.site. The page is public; feeds and
records require an operator session. A phone credential cannot access other rooms.
Restarting the service revokes all sessions. No demo feeds are served publicly.

The Site Worker forwards through a temporary Cloudflare Quick Tunnel to a separate
loopback listener on 8766. Every request requires a server-held relay secret. The
listener cannot bootstrap local credentials; 8765 remains the local dashboard.
No firewall rule, account, subscription or custom domain was created. Quick Tunnels
have no uptime guarantee and require reconnection after the process stops.

`service/run_public.py` takes JSON with `origin` and `secret` through hidden stdin.
Use the Site origin and a cryptographically random secret of at least 40 characters.
Never put the secret in command arguments/source. It lives in process memory and
the Sites secret NIVRA_RELAY_SECRET. Start the tunnel with:

```powershell
service/tools/cloudflared.exe tunnel --url http://127.0.0.1:8766 --no-autoupdate --protocol http2
```

On reconnect, update NIVRA_UPSTREAM to its returned HTTPS URL and NIVRA_RELAY_SECRET
to the new secret through Sites runtime settings, then deploy the saved version.
This manual restart is a pilot limitation; a permanent install needs a named tunnel
and restart management. No Windows service was installed.

The official cloudflared 2026.9.3 Windows amd64 binary was checksum-verified:
`f096265ec2fcbe9bb6e2d64268db167ced3fcbb83d894bdb9e2fcdb26f2ea7e2`.
It lives in ignored service/tools/. QR rendering uses qrcode.react 4.2.0.

Frames are encrypted in transit through the relay, not end-to-end against its
operator. Application code saves no frames and logs no bodies or credentials.
Only Nivra cookies are forwarded. The gateway rejects foreign mutation/WebSocket
origins, blocks local-only routes, bounds JSON bodies and disables caching.
The original transport, metadata retention and physical-device limits below still
apply; the statement that no public gateway exists is superseded by this section.

# Original local-only setup notes (superseded)

The publisher and scoped API are implemented. Actual iPhone/Android operation over
mobile data is **not verified**. No public gateway, DNS, certificate, firewall rule,
relay, hosting subscription or external account was created.

## Transport

The pilot uses JPEG frames over WSS, targeting at most 12 captured frames/second,
960 px on the longest edge, one outstanding upload per device. Preview delivery is
limited to approximately four frames/second. GPU detection has an independent,
fair, latest-frame queue. Temporal models retain a separate 4.5-second/64-frame
RAM history, so discarded detection jobs do not automatically erase captured
motion. This is an image stream, not a full-motion WebRTC implementation.

The tradeoff is bandwidth and browser foreground reliability. WebRTC/native capture
is a possible later transport upgrade, not a silently provisioned dependency. The
browser requests video only. Locked-screen/background streaming is not promised.

## Required deployment configuration, not performed

1. Supply an operator-controlled HTTPS origin that reaches this PC. Prefer a
   gateway on the same PC so video does not traverse a third-party inference host.
2. Set `NIVRA_PUBLIC_ORIGIN=https://your-camera-host.example` in the launch shell.
   This only configures the allowed Origin and pairing-link base. It does not
   establish connectivity, expose a port, or prove TLS works.
3. Keep the AI service on `127.0.0.1:8765`. Forward only the camera page/assets and
   `/api/v2/camera/*`. Block `/api/v1/*`, `/api/v2/session`, `/api/v2/operator`,
   `/api/v2/state`, `/api/v2/cameras*` and `/api/v2/events*` at the public gateway.
4. Preserve the external Host, set trusted forwarding headers, and do not rewrite
   remote requests as local-origin requests. The local bootstrap additionally
   rejects public Hosts and any forwarding headers. The operator dashboard is
   intentionally local to this computer.
5. Use valid, browser-trusted TLS. Do not bypass certificate warnings. Disable
   request/response-body logging and buffering for camera WebSockets. Do not
   enable access logs containing pairing bodies or frames.
6. Test one phone, then two cameras, before a four-camera attempt. Verify camera
   permission, lens/framing, network interruption, Stop, reconnect, revoke,
   foreground/background behavior and source-to-alert delay on each real device.

Only after that configuration should the dashboard's camera pairing link be used
on a remote phone. Without it, the link says it works on this computer only.

## Credential scope and records

The dashboard creates a single-use, five-minute random pairing link. Its secret
uses the URL fragment, is removed from browser history after exchange, and is
never logged or persisted by the service. The camera receives a HttpOnly,
SameSite=Strict cookie scoped to `/api/v2/camera`; HTTPS cookies are Secure.
Pairing again revokes the earlier publisher. Pause also revokes access. A service
restart expires all camera/operator credentials; saved locations/events remain.

Camera credentials cannot list cameras, view review records, acknowledge events,
or open the operator stream. The public-Origin tests exercise these boundaries
in-process; they are not a real external network or penetration test.

SQLite schema version 1 lives under ignored `service/state/`. To choose a separate
pilot or test store, set `NIVRA_METADATA_DB` before launch. Event IDs are unique
per camera, connection generation and pipeline generation. Review updates use
revision checks and an audit row in the same transaction. Never put frame blobs,
thumbnails or media URLs into the metadata database.
