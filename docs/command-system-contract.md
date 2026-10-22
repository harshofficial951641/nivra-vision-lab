# NIVRA Command system — shared contract (v1, 2026-10-22)

Single source of truth for the backend helpers and the frontend. If a helper must
deviate, update this file in the same change and say so in its report.

Surfaces: `/wall` (reviewer + judges, review window opens over it), `/setup`
(admin portal), `/guard` (guard phone PWA), `/camera` (camera device, existing),
`/login` (reviewer sign-in), `/guard/login` handled inside `/guard`.
Showcase target: the Python service and model run on a **MacBook** (no CUDA) at
another venue; phones reach it over HTTPS.

## 1. Identity and auth

- Provider: **Clerk**. Frontend uses `@clerk/clerk-react` with
  `VITE_CLERK_PUBLISHABLE_KEY`. Backend verifies Clerk session JWTs with
  `CLERK_SECRET_KEY` / JWKS (`CLERK_JWKS_URL` optional override), checks `exp`,
  `nbf` (5 s leeway), `iss` (`CLERK_ISSUER`) and `azp` against
  `NIVRA_AUTHORIZED_PARTIES` (comma list of origins).
- `NIVRA_AUTH_MODE`: `clerk` (default when `CLERK_SECRET_KEY` is set) or `dev`.
  `dev` is only accepted on loopback/LAN demo hosts and is shown in the UI as
  "Developer sign-in". It exists so the system works before Clerk keys exist.
- Roles: `admin` (reviewer + setup portal), `reviewer`, `guard`. Stored in Clerk
  `public_metadata.role`; the backend reads it from the session-token claim
  `metadata.role` when present (Clerk session token template
  `{"metadata": "{{user.public_metadata}}"}`), else fetches the user via the
  Backend API with a 60 s cache. Bootstrap: emails in `NIVRA_ADMIN_EMAILS` are
  admin even without metadata.
- HTTP: `Authorization: Bearer <clerk session token>`; dev mode uses an HttpOnly
  `nivra_dev` cookie instead. WebSockets: first client message within 5 s must be
  `{"type":"auth","token":"<jwt>"}` (dev mode: cookie only, message optional);
  client re-sends `auth` every ≤50 s; server closes 4401 on missing/expired auth,
  4403 on wrong role.
- Camera devices stay device-paired (one-time QR token → device cookie). Only
  reviewers/admins create camera pairing links.

### Endpoints

Backend integration: `Classroom.require_admin(request)` and
`require_reviewer(request)` return a `Principal`; `require_guard(request)` returns
the linked callsign. They remain synchronous (HTTP bearer verification runs in
`AuthMiddleware` off the event loop). `await classroom.websocket_auth(socket,
roles=('guard',))` accepts and authenticates a socket, returning `SocketAuth` with
`.principal`, `.identity` (guard callsign), `.timeout`, `await .check()`, and
`await .consume(message)` (True for auth controls). Bound each receive by
`.timeout`, check before/after receiving, and catch `WebSocketDisconnect`;
authentication errors close with 4401/4403. H4 owns the guard stream loop.

| Method | Path | Role | Notes |
| --- | --- | --- | --- |
| GET | `/api/v2/me` | any signed-in | `{userId, name, email, role, guard: {callsign}\|null, authMode}` 403 if no NIVRA role |
| POST | `/api/v2/auth/dev` | none, dev mode only | body `{role, name}` → sets `nivra_dev`; 404 when not dev |
| POST | `/api/v2/auth/dev/logout` | dev | clears cookie |
| GET | `/api/v2/members` | admin | `[{userId,email,name,role,guardCallsign,lastActiveAt}]` |
| POST | `/api/v2/members/invite` | admin | `{email, role, callsign?}` → Clerk invitation with metadata, redirect to `/login` or `/guard`; dev mode creates a local member |
| PATCH | `/api/v2/members/{userId}` | admin | `{role}` |
| DELETE | `/api/v2/members/{userId}` | admin | revoke role + sessions |

### Identity implementation details

- Configure `CLERK_ISSUER` explicitly in Clerk mode. `CLERK_JWKS_URL` defaults to
  `{issuer}/.well-known/jwks.json`. RSA/RS256 only; required claims are `sub`, `iss`,
  `azp`, `exp`, `nbf`. JWKS cache lasts 300 s; unknown `kid` triggers a refresh,
  rate-limited to one attempt per 5 s, including failed requests.
- `NIVRA_AUTHORIZED_PARTIES` defaults to the effective allowed origins.
  `NIVRA_ALLOWED_ORIGINS` replaces the defaults when set; unset defaults are
  `http://127.0.0.1:8765,http://localhost:8765`. `NIVRA_PUBLIC_ORIGIN` is added if
  configured. Mutations and sockets require an exact allowed Origin. Same-origin
  GETs may omit Origin. Trusted hosts derive from these origins (plus the
  gateway's internal 127.0.0.1 host).
- Role precedence is token `metadata.role`, then Backend API public metadata,
  then `NIVRA_ADMIN_EMAILS` bootstrap for a **verified primary email** with no
  assigned role. Profile/callsign fallback uses the same 60 s user cache.
- `/auth/dev` accepts `{ "role": "admin|reviewer|guard", "name": "..." }` and
  returns HTTP 200 with the same object as `/me`. Cookie `nivra_dev` is HMAC-SHA256
  signed, HttpOnly, SameSite=Strict, scoped to `/api/v2`, lasts 8 h and is Secure
  on HTTPS. `NIVRA_DEV_SECRET` is optional; otherwise a random process secret is
  used. Sessions and local members are in memory and reset on restart, even with
  a configured secret. Logout returns 204 and invalidates that session server-side.
- Dev sign-in additionally requires an allowed loopback/private-IP host or
  `nivra.local`, matching Host/Origin, and no proxy/relay headers. It is never a
  public remote self-registration endpoint. For dev guards, use a name such as
  `G2` to select that stored callsign; other names select `G1`. A matching guard
  record must exist before `/me`/guard actions succeed. Dev identities do not
  overwrite persisted Clerk links.
- `/me` response example:
  `{"userId":"user_123","name":"Asha Patel","email":"asha@example.test","role":"guard","guard":{"callsign":"G2"},"authMode":"clerk"}`.
  For other roles `guard` is null. Missing Clerk authentication returns 401;
  an authenticated identity without the required role/link returns 403.
- `GET /members` returns member objects shaped
  `{"userId":"user_123","email":"asha@example.test","name":"Asha Patel","role":"reviewer","guardCallsign":null,"lastActiveAt":null}`.
  `POST /members/invite` accepts `{"email":"asha@example.test","role":"guard","callsign":"G2"}`
  (callsign required for guards) and returns 201
  `{"invitationId":"inv_123","status":"pending","member":null}` in Clerk mode.
  Dev returns `{"invitationId":null,"status":"created","member":{...}}`.
  `PATCH /members/{userId}` accepts `{"role":"reviewer"}` and returns the updated
  member object (200). `DELETE` returns an empty 204 after removing role metadata
  and revoking all active Clerk sessions. Provider failures return 503 without
  provider details. A failed revocation can be retried; local access is already
  revoked after metadata removal. Local role changes invalidate old JWTs and
  cached profiles; clients must request a newly minted token.
- `/` remains the legacy dashboard in dev mode: `/session`, operator invite/
  redeem/logout and the old operator cookie still work there. Legacy guard
  pairing remains **dev only** for existing phones/tests. In Clerk mode those
  flows are disabled and cookies cannot grant any role. Camera pairing is
  unchanged in both modes. Normal reviewer/operator and Clerk guard sockets use
  first-message `{"type":"auth","token":"<session JWT>"}` within 5 s, and the
  identical message for renewal before 50 s or token expiration (5 s leeway),
  whichever comes first. `ping` does not renew auth. No separate auth ACK is sent;
  a snapshot follows successful authentication. 4401 means invalid/missing/
  expired auth; 4403 means wrong role, changed identity, missing guard link, or
  disallowed Origin. Capacity remains 1013.
- `ClerkClient` owns every Clerk HTTP call. HTTP and socket verification perform
  network I/O off the event loop. `require_role(role)` is the registry dependency;
  `AuthService.invite_member(email=..., role=..., callsign=..., origin=None)` is
  the guard-invitation hook. Reviewer and guard actions pass principal user IDs
  to the store's `actor` keyword; legacy dev identities use explicit `dev_legacy_*`
  actor IDs.
- The public worker forwards bearer Authorization and WebSocket upgrades unchanged.
  Only the signed UUID plan/frame GET routes accept query strings: plan keys must
  be exactly `v` (64 hex), `exp` (unsigned decimal), `sig` (64 hex); frame keys
  exactly `exp`, `sig`. Duplicates, extra/encoded names, wrong paths/methods and
  malformed values are rejected. The raw query is forwarded unchanged, without
  end-user Authorization/Cookie headers. Backend HMAC verification remains final.
  Successful plans retain upstream `Cache-Control: private, max-age=300`; clips
  remain `no-store`. Only `PUT /api/v2/floors/{UUID}/plan` permits multipart bodies
  up to 8 MiB + 64 KiB; it forwards Authorization unchanged. Other request bodies
  retain the 8192-byte cap. `/setup`, `/login`, `/guard/login` are SPA routes through
  the service and gateway/worker.

## 2. Site registry (admin portal)

All ids are server-generated strings. Positions are **normalized 0..1** of the
floor-plan image (x right, y down). `range` is a fraction of plan width.

```ts
Site   = { id, name }                                  // one site for now
Floor  = { id, name, order, plan: { url, width, height } | null, sample: boolean,
           metersPerUnit: number | null }              // metres per plan-image pixel (set in Setup from "floor width in metres"), optional
Placement = { floorId, x, y, angle /*deg, 0=east, clockwise*/, fov /*deg*/, range }
Camera (existing fields) + { label: "CAM-01", placement: Placement | null }
Guard  = { id, callsign: "G2", name, userId | null, email | null, floorId | null,
           post: { x, y } | null, shift: "on_shift" | "break" | "off",
           presence: { online: boolean, lastSeen: number | null },
           push: boolean }                              // has a working push subscription
```

| Method | Path | Role |
| --- | --- | --- |
| GET/PATCH | `/api/v2/site` | reviewer read / admin write `{name}` |
| GET/POST | `/api/v2/floors` | reviewer / admin `{name}` |
| PATCH/DELETE | `/api/v2/floors/{id}` | admin `{name, order, metersPerUnit}` |
| PUT | `/api/v2/floors/{id}/plan` | admin, multipart `file` PNG/JPEG/WebP ≤ 8 MB, decoded and re-encoded (metadata stripped), ≤ 4096 px |
| POST | `/api/v2/floors/{id}/sample` | admin — use the built-in sample mall plan (`plan.url = "/demo/mall/plan.svg"`, `sample: true`) |
| PATCH | `/api/v2/cameras/{id}` | admin — existing fields plus optional `label`, `placement` |
| GET/POST | `/api/v2/guards` | reviewer / admin `{callsign, name, email?, floorId?, post?}` (POST with email also invites via §1) |
| PATCH/DELETE | `/api/v2/guards/{id}` | admin |

- Camera cap rises from 4 to `NIVRA_MAX_CAMERAS` (default 12).
- Plan image URLs are **signed**: `/api/v2/files/plan/{floorId}?v={hash}&sig=…&exp=…`
  (HMAC, 10 min) so `<img>` works without headers. Snapshots re-issue them.

### Registry details (H2)

- SQLite metadata version is **4**, upgraded atomically from v1/v2/v3. H4's
  `guard_push_subscriptions` and `guard_push_rounds` tables belong to this same
  migration (no separate v5). Existing rows and audit history are preserved.
- The initial single site is named `NIVRA`. New floors receive the next order;
  new guards start `off`. IDs are UUID strings. Legacy cameras receive `CAM-01`,
  `CAM-02`, etc.; new camera labels use the first unused number.
- Names/labels use 1–60 trimmed characters without control characters. Email is
  lowercased and validated; email, callsign and linked user are unique. PATCH is
  partial: omitted fields remain unchanged. `placement:null`, `post:null`,
  `floorId:null`, `email:null` and `metersPerUnit:null` clear optional values.
  A guard post requires a floor. Changing a guard's floor clears its old post
  unless a new post is supplied. `order` is a nonnegative integer and scale is
  metres per image pixel, finite and `0 < metersPerUnit <= 10` (or null).
  The sample plan is 1000 x 620 with `metersPerUnit: 0.1`.
  Guard PATCH accepts `shift` as well as POST fields.
- POST returns 201 and the created object; GET/PATCH/PUT/sample return 200 and
  the contract object (list GETs return arrays); DELETE returns 204 with no body.
  Invalid fields return 422; missing records/floors 404; duplicate identities 409.
- Uploaded plans allow at most 8 MiB of file bytes, enforced while streaming.
  Multipart framing is separately bounded to 64 KiB. Decoded PNG/JPEG/WebP
  images are verified, loaded, orientation-corrected, proportionally downscaled
  to a 4096-pixel longest side, and re-encoded as metadata-free lossless WebP.
  Unsupported/corrupt/unsafe images return 415; oversize uploads return 413.
- The signed GET includes the version query in its HMAC input, preventing hash
  tampering. Expiry is epoch seconds; invalid, missing or expired signatures
  return 403. A valid URL for a replaced/deleted plan returns 404. Files return
  `Content-Type: image/webp` and `Cache-Control: private, max-age=300`.
- Floor removal clears live camera placements and guard posts, but preserves
  historical `events.floor_id`. Replace/sample/delete removes the old uploaded
  image. Removing a guard also removes its stored push subscriptions.
- POST with email uses H1's `AuthService.invite_member` hook when available;
  without the hook the guard is saved and invitation unavailability is logged.
  If invitation fails after persistence, return 502 with
  `{detail:{message,guardId}}`; the record remains and the admin can retry using
  `/api/v2/members/invite`. This prevents pretending the local database and
  Clerk invitation are one transaction.

## 3. Operator snapshot (WS `/api/v2/operator`, version 3)

```ts
{ version: 3, type: "snapshot", serverTime, me: { role },
  site, floors: Floor[], cameras: Camera[] (as today + label, placement),
  guards: Guard[], events: Incident[] (as today + floor_id, clip),
  analytics, service, runtime, retention, experimental }
```
`Incident.clip = { status: "recording" | "ready" | "expired" | "none", frames: number }`.
Binary preview frames unchanged.

## 4. Incident clips (server, RAM only)

- Per live camera, keep the last 10 s of received JPEGs (≤ 6 fps) in RAM.
- On a new event, freeze 10 s before + record 8 s after into a clip bound to the
  event id. Never written to disk. Deleted on `dismiss`, `clear`, or 15 min TTL,
  and on service restart.
- `GET /api/v2/events/{id}/clip` (reviewer) →
  `{ status, startMs, peakMs, endMs, frames: [{ t /*epoch ms*/, url /*signed*/ }] }`.
  Frame URLs are signed like plan URLs (5 min).
- Clip times are server epoch milliseconds, anchored to successful event
  registration (`peakMs`); phone-local source timestamps are not epoch times.
  Early connection/disconnect can leave partial coverage. The shared RAM JPEG
  budget is 120 MiB, oldest clips evicted first. Deletion invalidates signed URLs.

## 5. Review lifecycle (existing, unchanged)

`POST /api/v2/events/{id}/review` actions `view|confirm|dismiss|alert|on_scene|clear`
(see service/nivra/classroom_store.py `Store.review`). Now requires role reviewer/admin
and records `reviewer_id` (Clerk user id) on every state-changing reviewer action
including `view`; audit rows record `actor` for every state-changing action including view
and guard actions. Repeated no-op views retain the existing revision/audit.

Setup check: `POST /api/v2/events/test` is **admin only**, body `{cameraId}`.
Returns **201** with the newly recorded event row, using the normal `Store.record`
path and a unique source ID. `model` is `"test"`; detail is exactly
`"Test alert — not a real incident. Confirm and alert a guard to check their phone rings."`
The event begins open/undecided, inherits the camera's floor, and is broadcast
in snapshot v3 unchanged (`model == "test"` identifies it to the UI). It does
not notify a guard until the normal human confirm/alert action is performed.
Only one successful test event per **10 seconds across all cameras/admins**
is allowed by the running service (429 with `Retry-After`; resets on restart).
An existing undecided test event on that camera returns **409**, including
after a view action; this check takes priority over the cooldown. Missing
camera returns 404 and invalid input 422. Failed requests do not consume the cooldown.

## 6. Guards

- Guard identity = Clerk user with role `guard` linked to a Guard record
  (by `userId`, or by `email` on first sign-in).
- `WS /api/v2/guard/stream` — auth per §1, role guard. Messages
  `{type:"guard-snapshot", version: 2, guard: Guard, floor: Floor|null,
    serverTime, alerts: GuardAlert[]}` (camera placements are embedded in alerts).
  GuardAlert = existing whitelisted fields + `placement` of the camera + `floorId`.
- `POST /api/v2/guard/events/{id}` `{action: ack|decline|on_scene|clear, revision}` (existing rules).
- `POST /api/v2/guard/shift` `{shift: on_shift|break|off}` returns the same object.
- Presence: online while a guard socket is open; `lastSeen` updated on messages.
- **Web Push**: `GET /api/v2/guard/push/key` → `{publicKey}` (VAPID);
  `POST /api/v2/guard/push` `{subscription}` returns 204; `DELETE /api/v2/guard/push`
  returns 204 (no body removes all own devices; optional `{endpoint}` removes one).
  Subscription is the browser object `{endpoint, expirationTime?, keys:{p256dh,auth}}`;
  at most five per guard, HTTPS push-provider allowlist, 404/410 removes expired endpoints.
  On alert, send a push (`{type:"alert", eventId, title:"NIVRA alert", body:"Go to <camera name>", url:"/guard"}`,
  `urgency: high`, TTL 60) in addition to the socket message. Service worker
  `/guard-sw.js` shows the notification with `requireInteraction` and vibrate pattern.
- Escalation: if no guard ack/decline within `NIVRA_ACK_TIMEOUT_S` (default 30 s),
  the event gets `escalated_at` and the operator snapshot shows it (reviewer re-alerts).
  Re-push at escalation, then every 15 seconds up to four total rounds including
  the initial alert. Ack/decline/on-scene/clear stop repeats; re-alert resets them.
  Persist round progress; coalesce missed rounds after restart. See
  [guard-alerts.md](guard-alerts.md) for exact JSON, configuration, delivery limits,
  and iOS Home Screen requirements.

## 7. Mac runtime

- `scripts/start-mac.sh`: venv (uv), deps without CUDA wheels, model prepare,
  build frontend, start service. Model device order: CUDA → MPS → CPU, logged
  in `runtime.device`. Frame rate budget adapts to measured latency.
- HTTPS for phones: `scripts/https-mac.sh` creates a local CA + cert with
  `mkcert` for the Mac's LAN IP / `nivra.local`; service serves TLS when
  `NIVRA_TLS_CERT`/`NIVRA_TLS_KEY` are set (port 8443). The existing public
  bridge remains optional.
- `NIVRA_ALLOWED_ORIGINS` (comma list) replaces hard-coded 127.0.0.1:8765 origin
  checks; defaults keep today's behaviour.
- `NIVRA_DEVICE=auto|cuda|mps|cpu` selects/forces inference. The X3D profile runs
  RTMO + X3D without redundant SlowFast execution. ONNX prefers CoreML on MPS
  where available. CPU/MPS overload or unsupported inference switches to device
  analysis; `runtime.device="camera-device"` and `fallbackReason` disclose it.
  Browser reports stay standby until that switch. `NIVRA_AUTO_RELAY=0` is for
  measurements; `NIVRA_RELAY_ONLY=1` explicitly bypasses server models.
- `NIVRA_PORT` overrides 8765 (HTTP) or 8443 (TLS). Both TLS paths are required.
  See [mac-showcase.md](mac-showcase.md) for setup and verification boundaries.
