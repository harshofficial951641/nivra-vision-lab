# H2 backend handoff

- H2 owns `classroom_store.py` schema. v4 migration and registry helpers are now present.
- H4 integration: push tables/index have been folded into H2's atomic **v4** migration. Do not bump to v5. `push.migrate` is no longer called; its DDL now lives in `classroom_store.py`. No push functionality was removed. Early local v4 databases get the idempotent push DDL on reopen. Unreleased transient v5 test databases should be discarded, not used as service state.
- H1: `Store.review(..., actor=None)` and `Store.guard_action(..., actor=None)` accept authenticated user IDs. Pass actor from HTTP routes. `reviewer_id` changes for every state-changing reviewer action, including view; every state-changing reviewer/guard action audits actor. No-op repeated views retain the existing row.
- H1: `sites.role_dependency` imports `auth.require_role(role)`; H1's factory is integrated and reviewer reads admit admins. The requested defensive legacy fallback remains.
- H1: guards POST uses `classroom.auth.invite_member(email=..., role='guard', callsign=...)`. The live hook is integrated and tested in dev mode; Clerk delivery itself was not attempted. If unavailable, the guard is persisted and invitation unavailability is logged. Upstream failure returns 502 with the saved guard ID and a members/invite retry instruction.
- H1/H4 store rows use snake_case: `guard(id)`, `guards()`, `guard_by_callsign(callsign)`, `guard_by_user(user_id)`, `guard_by_email(email)`, `link_guard_user(guard_id,user_id)`, `set_shift(guard_id,shift)`. Guards have user_id/email/floor_id/post_x/post_y/shift. `sites.guard_payload(row)` converts to contract camelCase and placeholders for presence/push.
- H4: `floor(id)` / `floors()` return raw rows; `sites.floor_payload(row)` signs uploaded plan URLs. `sites.camera_payload(row)` adds placement. events.escalated_at exists; re-alert resets it. Coordinate any extra persistent tables/methods with H2; do not add separate schema migrations.
- H3: shared `signing.sign_url(path, *, ttl=600, now=None)` and `verify_url(path, exp, sig, *, now=None)` are ready. Use ttl=300 for frames. Exact path (including existing `?v=...` query) and integer exp are HMAC inputs. Configured NIVRA_URL_SECRET or random process key.
- H2 changed server cache middleware to setdefault so signed file Cache-Control survives. Plan responses use private,max-age=300.
- H2 preserved H3 clip enrichment already in snapshot; snapshot is now v3 with site/floors/guards/serverTime/me and maxCameras from environment.

## Exact API examples

See [h2-api-examples.json](h2-api-examples.json). It contains 17 recorded HTTP
exchanges, including each registry method, uploaded plan bytes/headers, and a
complete `snapshotV3` object. Captured using FastAPI TestClient with temporary
SQLite and plan files; these example resource IDs are not live resources and
the signed example URL expires. No real account or invitation was created.

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| GET | `/api/v2/site` | none | 200 Site |
| PATCH | `/api/v2/site` | `{name}` | 200 Site |
| GET | `/api/v2/floors` | none | 200 Floor[] |
| POST | `/api/v2/floors` | `{name}` | 201 Floor |
| PATCH | `/api/v2/floors/{id}` | partial `{name,order,metersPerUnit}` | 200 Floor |
| DELETE | `/api/v2/floors/{id}` | none | 204 empty |
| PUT | `/api/v2/floors/{id}/plan` | multipart field `file` | 200 Floor |
| POST | `/api/v2/floors/{id}/sample` | none | 200 Floor with sample image and scale 0.1 |
| GET | `/api/v2/files/plan/{id}?v=...&exp=...&sig=...` | none | 200 WebP bytes, private max-age=300 |
| PATCH | `/api/v2/cameras/{id}` | partial legacy fields, `label`, `placement` | 200 camera metadata + placement |
| GET | `/api/v2/guards` | none | 200 Guard[] with H4 presence/push |
| POST | `/api/v2/guards` | `{callsign,name,email?,floorId?,post?}` | 201 Guard |
| PATCH | `/api/v2/guards/{id}` | partial POST fields plus `shift` | 200 Guard |
| DELETE | `/api/v2/guards/{id}` | none | 204 empty |

`metersPerUnit` means metres per image pixel, nullable or `0 < value <= 10`.
Sample sets it to `0.1` at 1000 x 620. Camera `range` remains a normalized
fraction of plan width (`0.02..1`). Names/labels are 1–60 trimmed characters,
without control characters. Invalid input is 422, unknown records/floors 404,
duplicate callsign/email/user 409, unsupported images 415, oversized images 413,
and bad/expired signatures 403. Full semantics are in contract section 2.

## Store and serialization interfaces

All store getters return raw SQLite dictionaries (snake_case), or None for a
missing single row. Mutations return the resulting row; deletes return the
deleted row. `KeyError` identifies missing rows/floors. The route layer maps
`sqlite3.IntegrityError` to 409; invalid domain values raise `ValueError`.

```python
Store.site()
Store.update_site(name)
Store.floors()
Store.floor(floor_id)
Store.add_floor(name)
Store.update_floor(floor_id, **changes)
    # name, ord, meters_per_unit, plan_path, plan_w, plan_h, plan_hash, sample
Store.delete_floor(floor_id)
Store.add_camera(name, building, floor)
Store.patch_camera(camera_id, **changes)
    # name, building, floor, enabled, label, placement (contract dict or None)
Store.max_cameras  # property, NIVRA_MAX_CAMERAS or 12
Store.guards()
Store.guard(guard_id)
Store.guard_by_callsign(callsign)
Store.guard_by_user(user_id)
Store.guard_by_email(email)
Store.add_guard(callsign, name, email=None, floor_id=None, post=None)
Store.update_guard(guard_id, **changes)
    # callsign, name, email, floor_id, post, shift, user_id
Store.link_guard_user(guard_id, user_id)
    # Refuses reassignment or duplicate ownership with ValueError.
Store.set_shift(guard_id, shift)
Store.delete_guard(guard_id)
Store.review(event_id, action, revision, *, reason=None, note=None, guard=None, actor=None)
Store.guard_action(event_id, guard, action, revision, *, actor=None)
Store.record(camera_id, generation, event)  # bool; copies camera.floor_id

sites.camera_payload(row)
sites.floor_payload(row)  # fresh signed URL for uploaded plans
sites.guard_payload(row)  # default presence/push
classroom.guard_payload(row)  # H4 enrichment used by registry routes/snapshot
signing.sign_url(path, *, ttl=600, now=None)
signing.verify_url(path, exp, sig, *, now=None)
signing.signature(path, exp)
```

## H2 file contributions

New: `service/nivra/sites.py`, `service/nivra/signing.py`,
`service/tests/test_sites.py`, this report, and `docs/h2-api-examples.json`.

Modified: `service/nivra/classroom_store.py` (v4 migration, metadata helpers,
cap/labels, floor attribution, audit actor); `classroom.py` (registry
serialization, snapshot v3, partial camera PATCH); `server.py` (mount registry,
preserve explicit file cache header); `.gitignore` (plans); both service
requirements files (multipart; explicit Pillow dependency); existing
`test_classroom.py` expectations for v4, cap 12, and clip-enriched snapshots;
`docs/command-system-contract.md` (behavior/scale/errors clarified).

Shared files also contain H1/H3/H4 and pre-existing edits. H2 did not touch
frontend, package.json, research/training sources, live processes, or commits.

## Verification

- Dedicated registry suite: **37 passed** (including v1/v2/v3 migrations and
  rollback, concurrency at camera cap, CRUD/role boundaries, user uniqueness,
  reviewer/guard audit, historical floor attribution, all three image formats,
  metadata stripping, downscale, malformed/oversize streaming, replacement and
  deletion cleanup, database-failure file preservation, signing tamper/expiry,
  snapshot v3, actual dev invitation and failure recovery).
- Exact response example capture succeeded through all 17 HTTP exchanges.
- Focused registry + Clerk guard-auth integration rerun: **43 passed**.
- H2's final full suite (`cd service && .venv/Scripts/python.exe -m pytest tests -q`):
  **922 passed, 5 skipped, 1 warning in 136.61 seconds**. Warning is the existing
  Starlette/AnyIO BlockingPortal deprecation. H1 independently reported the
  same 922 passed / 5 skipped result in 126.63 seconds.
- Python compilation of `sites.py`, `signing.py`, `classroom_store.py` passed;
  tracked H2/shared-file `git diff --check` passed (only Git CRLF notices).
- Validation is in-process backend testing. No live-service restart, deployment,
  Clerk delivery, real push delivery, or frontend/browser QA was performed by H2.

## Public-worker integration (assigned to H1 by the lead)

H1 found that the current `sites/worker.mjs` rejects query strings and PUT.
H2 notified the lead and H3; the lead assigned worker/gateway changes to H1.
The public bridge must narrowly forward:

- `PUT /api/v2/floors/{UUID}/plan`, multipart up to 8 MiB file + 64 KiB framing.
- Signed GET `/api/v2/files/plan/{UUID}?v={64hex}&exp={integer}&sig={64hex}`;
  backend verifies the signature and responds private max-age=300.
- H3 signed GET `/api/v2/events/{UUID}/clip/frames/{index}?exp={integer}&sig={64hex}`;
  clip frames remain no-store. The manifest has no query and requires reviewer auth.

H1 reports the signed plan/clip allowances, PUT upload and plan cache policy are
now implemented with **7 worker tests passing**. H2 did not edit or deploy the
worker, and does not claim live public plan/clip access is verified.
