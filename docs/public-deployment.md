# Published NIVRA pilot

The public address is https://nivra.tanishq.work. Vercel serves the web app and proxies HTTP to a private Mac relay. Camera, wall and guard WebSockets connect directly to the relay using one-use, role-scoped tickets valid for 30 seconds. Browser cookies stay on the NIVRA domain. The subdomain moved from Netlify because its account credits blocked new deployments; DNS remains managed by the existing provider.

This deployment requires this Mac to stay powered, online and logged in. The host prevents idle system sleep while running. Closing the lid, shutdown, logout or a lost internet connection can interrupt camera feeds and alerts. Vercel alone does not host the Python service or its SQLite database.

## Website-first setup and phone pairing

1. Open https://nivra.tanishq.work and enter a site name. No owner verification or host QR is required.
2. The service creates a private workspace for that browser. Add a camera with its name, building and floor, then scan its camera QR on the camera phone.
3. Add a named guard and floor, then scan that guard's QR on their phone. Camera and guard QRs grant only their assigned phone role.
4. Allow camera/location on camera phones and tap Start camera. Guards tap Start shift to share foreground GPS and receive live incident alerts.
5. The launch checklist shows actual video, GPS and guard connection state. Owner verification stays pending and does not prevent opening the wall.

A private HttpOnly owner cookie lasts up to 30 days and resumes the same browser's workspace after a host restart. Keep using that browser; clearing its cookies removes its access. Owner verification and account recovery are not implemented yet. Anonymous workspace access is a private browser capability, not a verified identity. Public developer sign-in remains disabled.

Each guest workspace has a separate SQLite database and runtime. Camera/guard sessions, QR codes, WebSocket tickets, events and previews stay scoped to that workspace. Native apps use the existing QR URLs without a rebuild. Camera and guard pairing credentials are stored as hashes in each workspace database. New camera pairings last up to 30 days; guard pairings retain their 12-hour expiry. Valid pairings survive a host restart, including when the owner has not reopened the site. Re-pairing, disabling a camera, removing a device or logging a guard out revokes its stored credential. Phones paired before this update need one fresh QR because their earlier credentials were never saved. GPS runs while the paired page is active; floor labels are entered by staff. Native background capture, tracking and APNs/FCM notifications are not configured.

The pilot bounds active guest workspaces to 32 and new workspace creation to 8 per minute across the host. Guest incident frame storage is limited to 8 MiB per workspace. The original single-site pilot remains separate; its records are not exposed to new visitors. Its legacy host-only owner QR page at http://127.0.0.1:8765/owner is retained for recovery and is not part of new site setup.

## Host and deployment

The host entry point is `scripts/deploy/public_host.py`. It starts an authenticated gateway on loopback 8766 and the local service on 8765, opens a Cloudflare Quick Tunnel, updates only the linked NIVRA Vercel project's production relay environment, then builds and deploys the web app. A fresh tunnel address requires the redeployment performed by this script. Quick Tunnels are suitable for this pilot and do not provide a production availability guarantee.

Private runtime files are under `service/state/public/`; credentials and session data must stay out of Git. The original pilot database is `service/state/classrooms.sqlite`; private guest databases and the hashed ownership index live under `service/state/workspaces/`. The local Vercel CLI account supplies deployment access. `.vercel/project.json` links only the NIVRA project. The relay credential is server-side and is not bundled into the frontend or mobile apps.

For a frontend-only update while the host is healthy:

```bash
VITE_NIVRA_DIRECT_SOCKET_RELAY=1 npm run build
node scripts/deploy/prepare_vercel.mjs
VERCEL_CLI_USE_NATIVE_BINARY=0 vercel deploy --prebuilt --prod --yes --scope topperly4-3974s-projects
```

`public/downloads/nivra-android.apk` must exist before building to include the Android download. Build instructions are in `mobile/README.md`.

## Verification and current limits

The public domain and TLS were checked against public DNS. A real network test exercised private owner redemption, camera/guard QR pairing, guard isolation, a camera JPEG reaching the wall over WebSocket, and guard alert acknowledgement, on-scene and clear actions. Temporary QA records were removed afterward.

The Mac initially failed to resolve the new hostname even though authoritative DNS, Google DNS and Tailscale DNS returned valid addresses. Its native resolver later recovered during read-only checks. Normal HTTPS and the actual collaborative browser now load the domain without an address override; the full private-owner/socket/download check also passed over normal DNS. The exact cause of the earlier resolver failure was not established. No Mac DNS settings or TLS validation were changed during that resolver check.

Android has a signed debug APK for sideloading. iPhone has an Apple-signed development IPA restricted to devices in its development profile. Neither app is published in an app store. Physical camera/GPS behavior and background alerts have not been verified on real phones.

## Persistent host control on this Mac

Keep the active relay launcher session running. After a reboot, open Terminal in this checkout and run:

```bash
NIVRA_DEPLOY_PROVIDER=vercel NIVRA_VERCEL_PROJECT_ID=prj_6C9uDjbj39td2ZxpZwvzRTITTSZz python3 -u scripts/deploy/public_host.py --supervise
```

Keep that command running. The bounded supervisor uses `caffeinate -i -w <host-pid>` while its host process is alive. It stops after three failures within fifteen minutes, with five- and twenty-second recovery delays. Each attempt has a tunnel startup deadline, checks both local ports before changing the public relay, and terminates its own tunnel/backend process groups on shutdown. Routine status output contains no credentials or raw remote API errors.

The LaunchAgent helper is implemented, but its first live start on this Mac failed with launchd exit code 78 before Python or log creation. Access to the project under Documents may be the cause; that has not been established. Login-time startup is therefore **not verified**. The detached-launch helper is also unverified: its test supervisors disappeared after the invoking tool finished, without normal shutdown logs. Terminal-close persistence has therefore not been established in this environment. Keep the current relay process running; installing either helper does not establish a running service. Logout or reboot stops this pilot.

For a future detached-launch test, only when ports 8765 and 8766 are free:

```bash
service/.venv/bin/python scripts/deploy/public_host_service.py detach
service/.venv/bin/python scripts/deploy/public_host_service.py status
```

`status` reports whether launchd has the agent loaded, the saved supervisor state, and current PID liveness checks. It also reads the private runtime record: an active manually launched host appears as `mode: direct` with separate `hostAlive`, `backendAlive` and `tunnelAlive` checks. An earlier supervisor record is nested separately so it cannot label that direct host stopped. `checkScope: process-liveness-only` means these checks do not establish public readiness. Saved state can be stale after a crash; a live process also does not prove the public relay is ready. A detached process, if it remains alive, can have `loaded` set to false. Process state alone does not prove public connectivity; check `https://nivra.tanishq.work` and the local health route after startup. To stop the detached supervisor, send `SIGTERM` to the `supervisorPid` reported by status, verify both loopback listeners have closed, then run `detach` again if a restart is needed. Never signal a PID without confirming it is this NIVRA supervisor.

The optional LaunchAgent commands are:

```bash
service/.venv/bin/python scripts/deploy/public_host_service.py install
service/.venv/bin/python scripts/deploy/public_host_service.py start
service/.venv/bin/python scripts/deploy/public_host_service.py status
service/.venv/bin/python scripts/deploy/public_host_service.py restart
service/.venv/bin/python scripts/deploy/public_host_service.py stop
```

`install` writes only `~/Library/LaunchAgents/work.tanishq.nivra.public-host.plist`, with explicit Node/runtime paths and private log paths. It does not change the running host. For the initial transition from a manually launched host, stop that exact host gracefully, wait for its backend and tunnel to exit and both ports to close, then run `start`. `restart` unloads gracefully and waits for listeners to close before bootstrapping a fresh agent. It intentionally avoids `kickstart -k`, which can kill the supervisor before child cleanup. Do not start the LaunchAgent while a detached supervisor is running.

A restart creates a new tunnel and redeploys the site, so allow time for both. Unexpired phone pairings and the owner workspace resume after recovery. In-flight sockets reconnect; if a phone session has expired or been revoked, create a fresh QR. Logs and status remain private in `service/state/public/`. The helper never grants macOS privacy permissions or installs a system daemon.

## Simple phone flow

On a camera phone, scan its QR, tap **Start camera**, and allow camera and location access. Detection starts automatically. The preview and one combined detection status stay visible; camera settings, location readings and technical details are disclosures. Partial motion coverage remains explicit. GPS sharing starts with Start camera or an explicit location retry and stops with Stop camera.

A camera reconnects after a short connection failure without requesting another media stream. Transport and model retries are bounded; Stop cancels them. If model recovery is exhausted, **Retry detection** restarts models while the same video connection stays open. Guard phones show their assigned name/floor and one Start shift action, with sound and notification tools kept optional.

The launcher uses Vercel CLI's Node runtime through `VERCEL_CLI_USE_NATIVE_BINARY=0`. The native uploader repeatedly failed file transfers on this Mac. Frontend deployment retries keep the healthy relay running; exhausted attempts require a manual frontend publish using the command above.
