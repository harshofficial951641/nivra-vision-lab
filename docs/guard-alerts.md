# Guard alerts and Web Push

## Integration contract

All four HTTP routes require H1's authenticated guard role linked to a registry
record. Requests use the same Bearer token/dev cookie and Origin rules as other
guard actions. Operator and admin credentials do not grant guard access.

- `GET /api/v2/guard/push/key` returns `200 {"publicKey":"<base64url P-256 key>"}`.
- `POST /api/v2/guard/push` accepts the browser's serialized subscription wrapped
  as `{"subscription":{"endpoint":"https://fcm.googleapis.com/...","expirationTime":null,"keys":{"p256dh":"<browser key>","auth":"<browser secret>"}}}`.
  Returns `204` with no body. Up to five endpoints per guard; updating an existing
  endpoint is idempotent. A sixth or an endpoint owned by another guard returns
  `409`; invalid URLs/keys return `422`.
- `DELETE /api/v2/guard/push` with no body deletes all of the signed-in guard's
  subscriptions. Optional `{"endpoint":"https://fcm.googleapis.com/..."}` deletes
  only that device. Both return `204`, including when already absent. Prefer the
  device-specific form during device logout, then call `subscription.unsubscribe()`.
- `POST /api/v2/guard/shift` accepts and returns `{"shift":"on_shift"}` (`200`).
  Allowed values are `on_shift`, `break`, and `off`; other values return `422`.

The guard stream includes only this guard, their assigned floor, and their own
whitelisted alerts. Camera placement is embedded in each alert; there is no
camera list, live frame, clip, model result, or other guard record.

```json
{
  "type": "guard-snapshot",
  "version": 2,
  "serverTime": 1792600000000,
  "guard": {
    "id": "guard-id", "callsign": "G2", "name": "Guard Two",
    "userId": "user_guard", "email": null, "floorId": "floor-id",
    "post": {"x": 0.4, "y": 0.6}, "shift": "on_shift",
    "presence": {"online": true, "lastSeen": 1792600000000}, "push": true
  },
  "floor": {
    "id": "floor-id", "name": "Ground floor", "order": 0,
    "plan": null, "sample": false, "metersPerUnit": null
  },
  "alerts": [{
    "id": "event-id", "camera_id": "camera-id", "camera_name": "East entrance",
    "location": "Main / Ground floor", "detail": "Review the scene.", "note": null,
    "received_at": 1792599999000, "alerted_at": 1792600000000,
    "guard_ack_at": null, "guard_declined_at": null, "on_scene_at": null,
    "status": "acknowledged", "revision": 1, "floorId": "floor-id",
    "placement": {"floorId": "floor-id", "x": 0.2, "y": 0.3, "angle": 90, "fov": 60, "range": 0.2}
  }]
}
```

Presence is online while at least one authenticated guard socket is open.
Connection and every received message update `lastSeen` (epoch milliseconds).
Presence resets offline and lastSeen resets to null after restart. `push` means a
registered subscription not yet rejected as expired; it does not prove that the
phone displayed a notification. Shift does not suppress an explicit reviewer alert.

## Delivery and escalation

On confirm-with-guard or alert, a background task sends
`{"type":"alert","eventId":"event-id","title":"NIVRA alert","body":"Go to East entrance","url":"/guard"}`
with `Urgency: high` and TTL 60 seconds. Requests do not wait on push providers.
Allowed HTTPS hosts: `fcm.googleapis.com`, `updates.push.services.mozilla.com`,
subdomains of `notify.windows.com`, `web.push.apple.com`, and subdomains of
`push.apple.com`. Credentials, fragments, non-443 ports and redirects are rejected.
HTTP 404/410 deletes the subscription; transient errors keep it for the next ring.

The one lifespan escalation scanner runs once per second. Initial delivery is
round 0; unanswered alerts escalate at `NIVRA_ACK_TIMEOUT_S` (default 30 seconds)
and re-push then, 15 seconds later, and another 15 seconds later: four total rounds
per alert cycle, each sent to up to five devices. Ack, decline, on-scene, clear,
or reassignment stops the old cycle. Reviewer re-alert resets the cycle.
Escalation increments the event revision and appends an `escalate` audit row.

H2 integrated `guard_push_subscriptions` and `guard_push_rounds` into its schema
**4** migration transaction using idempotent DDL for early v4 databases. H2 owns
`events.escalated_at`; this helper adds no event columns. Stored rounds plus
`alerted_at` survive service restart. Missed
rounds are coalesced into one current delivery, not replayed in a burst. A round is
reserved before delivery; a crash between reservation and provider acceptance
can lose that attempt. Push is best effort, not an exactly-once or guaranteed alarm.

## Configuration

- `NIVRA_VAPID_PUBLIC`: uncompressed P-256 public key, base64url.
- `NIVRA_VAPID_PRIVATE`: 32-byte P-256 private scalar, base64url. Set both key vars
  together. Do not put the private key in frontend env files or logs.
- `NIVRA_VAPID_SUBJECT`: contact `mailto:` or HTTPS URL. Local fallback is
  `mailto:nivra@localhost`; configure a real operator contact before phone use.
- `NIVRA_ACK_TIMEOUT_S`: finite positive number of seconds, default `30`.

If key vars are absent, first key use creates `service/state/vapid.json` once,
logs the path (never the keys), and reuses it. `service/state/` is gitignored.
Permissions are restricted to 0600 where supported; Windows deployments must
use an appropriate user ACL. Preserve this file across restarts and backups.
Changing the VAPID pair requires browsers to unsubscribe and resubscribe.

Dependency: `pywebpush==2.5.0`; it requires cryptography >=47, so requirements pin
`cryptography==50.0.2`. Both service requirement sets and the lock include the change.

## Phone setup and verification

The frontend owner must link `/guard.webmanifest`, register `/guard-sw.js`, request
notification permission from a user gesture, subscribe with `userVisibleOnly:true`
and the public key, then POST the serialized subscription. This helper does not
edit React. Vite copies public files into dist on build; rebuilding and deployment
are separate lead-owned steps. There is no service-worker fetch handler or API cache.

Use trusted HTTPS on the phone. On **iOS/iPadOS 16.4+**, **Add to Home Screen**,
launch that installed app, then enable notifications. A normal browser tab is not
enough. See [WebKit's platform requirements](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/)
and [Apple's Web Push guidance](https://developer.apple.com/documentation/usernotifications/sending-web-push-notifications-in-web-apps-and-browsers).

Sounds use the system default; there is no custom alarm-sound control. Vibration,
interaction persistence, repeat notifications, Focus/DND and lock-screen display
are OS/browser controlled. The service worker requests `requireInteraction`,
`renotify` and vibration `[800,400,800,400,800]` and focuses/opens `/guard` on tap.

Real-device acceptance: verify iPhone Home Screen installation and Android browser
permission, foreground/background/locked-screen delivery, notification tap and
authentication return, initial + three repeat rings, ack/decline stopping repeats,
system sounds/Focus behavior, denied permission, and stale subscription cleanup.
Automated fake-provider tests cannot prove OS notification delivery or audibility.

## Verification (2026-10-22)

- `cd service && .venv/Scripts/python.exe -m pytest tests -q`: **922 passed,
  5 skipped**, 134.96 seconds. One existing Starlette/AnyIO deprecation warning.
- `node --test tests/guard-sw.test.mjs`: **5 passed**. Notification options,
  malformed pushes, safe focus/open behavior, no fetch handler, manifest/icon sizes.
- `uv pip check --python service/.venv/Scripts/python.exe`: all 80 installed
  packages compatible. Installed pywebpush 2.5.0 and cryptography 50.0.2 verified.
- Guard tests use fake push providers, real pywebpush encryption with mocked HTTP,
  injected escalation clocks, temporary databases/keys, and real RSA/JWT signatures
  against H1's fake Clerk transport. No real provider notifications were sent.
- No React edits, frontend build, deployment, browser/phone notification test,
  or restart of the running service was performed by this helper.
