# NIVRA Vision Lab — technical handoff (2026-10-22)

Written for the next engineer/agent. Sources: `README.md`, `service/README.md`,
`package.json`, `scripts/start-local-ai.ps1`, `sites/worker.mjs`,
`service/run_public.py`, `docs/remote-camera-setup.md`, `docs/command-system-contract.md`,
`docs/h2-backend-handoff.md`, `docs/mac-*.md`, `docs/guard-alerts.md`,
`service/training/ROUND3-RESULTS.md`, `design-research.md`, `design-qa.md`.
Everything below is read from those files; this handoff ran no tests, services or
deploys. The fresh validation results quoted below were run by the parent session.

## Current status — read first

- **Public `/fight` is reported OFFLINE now** (https://nivra-vision-lab.topperly.chatgpt.site/fight
  shows "Analysis PC offline"). **Not fixed** by this handoff. Last recorded passing
  public check: `design-qa.md`, 22 Oct 2026 (deployment `appgdep_6ad96756eae88191b918708cc05f365b`,
  Sites env revision 4, saved version 8).
- Live model stays **baseline X3D-M**. Round-3 epoch-20 candidate is **not promoted**.
- Original repository: `tanishqagg-dev/nivra-vision-lab` (`origin`). Direct push was
  rejected with HTTP 403 because the configured account `harshofficial951641` has
  read-only access. Parent created the public fork
  https://github.com/harshofficial951641/nivra-vision-lab (`harsh` remote) for this handoff.
  Local source/design snapshot: `58ea657` (1,084 files). This document is committed
  separately. Publication completion must be checked against the fork's branch head;
  the original repository has not been updated.

## Architecture

```
Browser (public)  ──HTTPS/WSS──>  Sites Worker (sites/worker.mjs → dist/server/index.js)
                                    │ adds X-Nivra-Relay: <NIVRA_RELAY_SECRET>
                                    ▼ NIVRA_UPSTREAM (must be https://*.trycloudflare.com)
                         Cloudflare Quick Tunnel (cloudflared, accountless, temporary URL)
                                    ▼
             PC 127.0.0.1:8766  PublicGateway (secret-checked, route allowlist)
             PC 127.0.0.1:8765  local dashboard/API (loopback only)
                 └─ one shared FastAPI app (service/nivra/server.py), one model instance,
                    one scheduler, one SQLite metadata DB (service/state/, gitignored)
```

- Frontend: React 19 + Vite 8 + TS, Clerk (`@clerk/clerk-react`), MediaPipe in browser.
  `npm run build` = `tsc -b && vite build && node scripts/build-sites.mjs` (copies the worker
  to `dist/server/index.js`).
- `service/run_public.py` reads hidden JSON `{origin, secret, fightDemo}` on stdin, sets
  `NIVRA_PUBLIC_ORIGIN`, runs `create_app(relay_only=True, enable_fight_demo=...)` on 8765 and
  `PublicGateway(app, secret)` on 8766. `relay_only` = no PC pose/action models; with
  `fightDemo: true` it loads only X3D-M on the GPU for `/api/v2/fight`.
- Worker returns the HTML "Analysis PC offline" page (503) for page routes when:
  `NIVRA_UPSTREAM`/`NIVRA_RELAY_SECRET` missing; upstream not `https://*.trycloudflare.com`;
  upstream fetch throws; or upstream returns 5xx/3xx. Only `nivra_*` cookies are forwarded.

## File map

| Path | Purpose |
|---|---|
| `src/App.tsx`, `src/main.tsx` | Route shell |
| `src/FightDemo.tsx` | Public `/fight` X3D-M demo |
| `src/VisionLab.tsx` | Original browser-only `/lab` |
| `src/classroom/` | Dashboard, `/camera` publisher, pairing, device analysis |
| `src/command/` | `/wall` command wall, floor map, review window, clip player |
| `src/auth/`, `src/guard/`, `src/setup/` | `/login`, `/guard` PWA, `/setup` admin |
| `sites/worker.mjs` (+ `worker.test.mjs`) | Public Sites relay |
| `service/nivra/server.py` | FastAPI app (v1 lab + v2 classroom/command API) |
| `service/nivra/public_gateway.py` | 8766 secret-gated public listener |
| `service/nivra/fight_demo.py` | `/api/v2/fight/*` (incl. `/api/v2/fight/health`) |
| `service/nivra/auth.py`, `sites.py`, `signing.py`, `clips.py`, `push.py`, `classroom_store.py` | Clerk/dev auth, sites/floors/guards registry, signed URLs, RAM clips, Web Push, SQLite store |
| `service/run_public.py` | Public relay launcher |
| `service/run_fight_model.py` | Standalone X3D-M CLI |
| `service/training/`, `service/research/` | Offline training + evaluation records |
| `scripts/start-local-ai.ps1`, `start-mac.sh`, `https-mac.sh` | Launchers |
| `docs/*.md` | Contracts and verification notes (see list above) |
| `design/` | Copied brand/design assets (see Design section) |
| `docs/project-context/NIVRA_COMPLETE_CONTEXT_FOR_HARSH_JAIN.md` | Product context (17 Sep 2026) |

## Windows startup (from sources)

Local only:

```powershell
npm run dev:classroom-ai      # build, verify models (--experimental), RTMO + X3D + regional AVA, :8765
npm run dev:local-ai          # build, YOLOX/RTMPose/AVA profile, :8765
service/.venv/Scripts/python.exe service/run_fight_model.py --video service/evaluation/media/grappling.webm
```

Public bridge (from `docs/remote-camera-setup.md`; run from `nivra-vision-lab`, service code
imports from `service/`):

1. From the repo root, start the relay service (Python puts the script's directory,
   `service/`, on the import path automatically):
   ```powershell
   service/.venv/Scripts/python.exe service/run_public.py
   ```
   Paste the hidden JSON when prompted (never as an argument or in source):
   `{"origin":"https://nivra-vision-lab.topperly.chatgpt.site","secret":"<random ≥40 chars>","fightDemo":true}`
2. Start the tunnel:
   ```powershell
   service/tools/cloudflared.exe tunnel --url http://127.0.0.1:8766 --no-autoupdate --protocol http2
   ```
   (cloudflared 2026.9.3, SHA256 `f096265e…f26ea7e2`, lives in ignored `service/tools/`.)
3. Copy the new `https://<words>.trycloudflare.com` URL. In Sites runtime settings set
   `NIVRA_UPSTREAM` = that URL and `NIVRA_RELAY_SECRET` = the same secret as step 1,
   then **deploy the saved version** (env changes need a redeploy).
4. Check `/fight` loads and public health (`/api/v2/fight/health`) reports ready/X3D-M/CUDA.
   `output/qa/diagnose-public.py` probes local gateway → tunnel → site, but its tunnel URL
   is hardcoded to an old one; update before use.

## Why the Site says "Analysis PC offline"

All of these must hold simultaneously:

1. The PC is awake and `run_public.py` is running (8765 + 8766 listening).
2. `cloudflared` is running and its current Quick Tunnel URL is alive. **Quick Tunnel URLs
   change every restart** and have no uptime guarantee.
3. Sites env `NIVRA_UPSTREAM` equals the *current* tunnel URL and `NIVRA_RELAY_SECRET`
   equals the secret given to the *current* `run_public.py` process; then redeployed.
4. Gateway returns non-5xx. A mismatched secret is rejected by the gateway; 5xx/redirects
   are converted to the offline page by the worker.

Any PC sleep/reboot, closed terminal, tunnel exit or service restart (which also revokes
all sessions) breaks the chain until steps 1–3 are redone. Memory note: the local DB
schema is now v4 with the Command system; the running public process may predate it —
restart `run_public.py` deliberately rather than killing it ad hoc, and re-sync Sites env.
Permanent fix (not done): named Cloudflare tunnel + Windows restart management.

**Worker version caveat:** the source worker now allows `/wall`, `/guard`, `/setup`,
`/login`, PUT floor plans and signed plan/clip GETs (7 worker tests per H2 doc). Whether
the deployed saved version 8 includes these is **not verified**; the 22 Oct restoration
reused version 8 without a new source build.

## Implemented vs. production-tested

| Capability | Implemented in source | Tested evidence | Not tested / not claimed |
|---|---|---|---|
| `/fight` public X3D-M demo | Yes | Public browser runs 22 Oct (grappling 17/20 review windows, shadowboxing 0/16) | Physical webcam/phone, own-file upload in public check |
| Command system `/wall` `/setup` `/guard` `/login` + Clerk | Yes (contract v1, 2026-10-22) | Service suite 922 passed/5 skipped (H2/guard docs); registry 37, auth 43 | Real Clerk tenant sign-in, live public plan/clip access, public deploy of these routes |
| Guard Web Push | Yes (`push.py`, service worker) | `guard-sw.test.mjs` 5 passed | Lock-screen delivery on real Android/iPhone |
| Mac showcase (`start-mac.sh`, `https-mac.sh`) | Yes | `bash -n`, `uv pip compile` for arm64 | Install on a Mac, CoreML/MPS, thermals, CA trust, venue network |
| Multi-camera runtime | Yes | Windows i5-10400F + GTX 1660 Ti: CUDA 6 cams ~1.2–1.3 fps/cam analysed, p95 134 ms (in-process, no network) | Real phones, TLS, mobile data; CPU 2/6-cam points unusable |
| Phone camera over public relay | Yes | External protocol test with synthetic frames (classroom plan) | Physical iPhone/Android foreground/interrupt/mobile data |
| Crowded classroom / night / crowd observer | Partial/offline | — | Accuracy unvalidated; crowd observer stays offline |

## Model decision (`service/training/ROUND3-RESULTS.md`)

- Epoch-20 head-only fine-tune (4,098 params, 163 windows, GTX 1660 Ti, 369 s) completed and audited.
- Reserved comparison (593 paired windows, 471 unknown excluded):
  contact-proxy windows 58/82 → 67/82; proxy episodes 6/6 → 6/6 (no coverage gain);
  normal windows flagged 14/40 → 15/40 (one more ordinary-dance false flag).
- **Decision: keep baseline X3D-M live; epoch-20 stays offline.** More sensitivity, no
  episode-coverage gain, slightly more false flags.
- Limits: proxies are sports/drill, not hostile fights; windows overlap/dependent; normal
  coverage only 31.2 of 44 annotated seconds; reserved groups now spent; no calibration,
  no camera-hour false-alert rate, no crowd/night/production accuracy. Scores are uncalibrated.

## Validation commands (from sources)

```powershell
npm run verify                                         # lint + vitest + build
npm run test:e2e                                       # build + Playwright
node --test sites/worker.test.mjs
node --test tests/guard-sw.test.mjs
```

Python tests: run from `service/` (from the repo root without `PYTHONPATH`, test collection fails):

```powershell
$env:NIVRA_RUN_CUDA_TRAINING_TEST='0'
.venv/Scripts/python.exe -m pytest tests -q
```

Fresh parent run, 2026-10-22: `npm run verify` **passed** (lint, 251 frontend tests, build);
node tests **12 passed**; pytest from `service/` **927 passed, 5 skipped, 1 warning** in
90.19 s with `NIVRA_RUN_CUDA_TRAINING_TEST=0`. Older recorded counts (231 FE on 14 Oct;
795 py on Round 3; 922 py earlier on 22 Oct) are superseded.

## Design assets

- Approved UI direction: monochrome command surface (`design-research.md`); `/fight` is a
  bounded extension, concept gate waived (`design-qa.md`).
- Copied into the repo today by the parent: `design/{brand-kit, brand-kit-fresh,
  brand-kit-ultimate-concepts, assets, deliverables}` and
  `docs/project-context/NIVRA_COMPLETE_CONTEXT_FOR_HARSH_JAIN.md` — 882 byte-identical
  files, ~400.7 MiB, provenance/SHA256 in `design/asset-manifest.json`. These are
  **historical variants; no approval is implied by their presence**. Largest file is
  13.25 MB, below GitHub's 100 MiB per-file limit.

## Guardrails

- Never commit `.env*`, `service/state/` (SQLite, TLS), `service/tools/`, evaluation/research
  runs, or private footage. Relay secret lives only in process memory and Sites env.
- No footage persisted: frames/clips are RAM-only; SQLite stores metadata.
- No product claims of validated fight/violence detection, intent, identity or accuracy.
