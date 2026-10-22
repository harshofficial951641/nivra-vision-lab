# NIVRA device launcher

`WorkspaceStart.tsx` is the website entry at `/`. A fresh visitor enters a site name and explicitly creates a private browser workspace with `POST /workspaces`. Existing admin sessions resume guided setup. No local owner invitation or verification is required to start. `MobileHome.tsx` remains the secondary phone-role selector at `/mobile`, linking to `/camera`, `/guard`, `/wall` and `/setup`.

The pairing-link form only follows an actual same-origin camera or guard pairing URL carrying a valid-format `#pair=` token, or an owner invitation at `/` or `/wall` carrying `#operator=`. It does not redeem a token, change roles, or invent native-app deep links. Tokens stay out of server query strings and must not be logged or included in analytics.

Browser installation instructions distinguish a home-screen shortcut from a native binary. The existing guard manifest/service worker owns guard installation and notifications. The Android download points to the supplied `/downloads/nivra-android.apk` artifact. iPhone development distribution remains separate from App Store distribution. Verify packaged downloads and real-device behavior before calling either native release complete.

Real-device acceptance remains necessary for QR scanning, permissions, push delivery, foreground/background camera behavior, and any future native universal/app-link association.

## Legacy pilot owner access

`/owner` is registered separately from the authenticated console. On `localhost` or `127.0.0.1`, a user action bootstraps the local session and requests `/operator/invite`. The QR is never minted on page load. Other hostnames only show instructions for opening the owner page on the NIVRA computer; server loopback checks remain the authorization boundary.

Owner invitations grant owner access to the first visitor. The UI removes expired QRs and links, handles unavailable clipboards, and drops any previous QR before requesting its replacement. Opening a valid `#operator=` invitation is handled by `App.tsx` before authentication mounts, clears the hash, and redirects to `/setup?onboarding=1` after redemption.

## Guided first run

`/setup?onboarding=1` uses the existing admin-only setup route. It guides the owner through site naming, a named camera with building/floor and pairing QR, a named guard with reported floor and pairing QR, then a live readiness check before opening the wall. `/setup` retains device management and optional test alerts. Guard setup can be explicitly skipped; the launch page still shows dispatch as pending.

QR panels stay mounted when moving between steps so going Back does not silently mint a replacement QR or revoke a paired phone. Creating another QR remains an explicit action. Readiness uses live snapshots and recent GPS, and becomes pending when the console disconnects. API-confirmed newly created records appear immediately while awaiting the next snapshot.

## Private workspace session

The website entry checks `/me` before offering creation. Only an authenticated admin is resumed automatically. An existing guard/reviewer is directed to their assigned role; loading the page never creates a workspace or upgrades a paired phone. A 401/403 enables the site form, while service failures require retrying the session check.

`POST /workspaces` receives `{name}`, sets a private HttpOnly browser cookie, and returns `{workspace:{id,name,ownerVerification:'unverified'}}`. A confirmed creation opens `/setup?onboarding=1#cameras`. Isolation is enforced by the backend across HTTP APIs, QR exchanges, socket tickets and live streams. Owner verification remains a nonblocking pending state at Launch; the legacy `/owner` route is not used as a workspace-verification mechanism.

Workspace and legacy operator sessions sign out through `/operator/logout`; ordinary local developer identities retain `/auth/dev/logout`.
