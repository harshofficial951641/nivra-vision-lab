# Public X3D model demo verification

Route: `nivra-public-fight-demo-2026-10-14`, contract version 1.
Universal design router classified an extension of the existing NIVRA app.
Design preflight owns the established monochrome interface; Sites supports
publication, with an independent backend/security reviewer. The concept gate
is waived for this bounded extension of the existing design system.

The user explicitly selected PC GPU inference and requested a public Sites link.
The new `/fight` page leaves the operator dashboard, camera pairing and original
Vision Lab journeys intact. Existing brand assets and interface conventions are
retained; no new visual direction or generated assets are introduced.

## Verified

- Frontend lint and production TypeScript/Vite build pass.
- Existing frontend suite: 21 files / 231 tests pass.
- Python service suite: 78 tests pass, including 23 public fight-demo cases.
- Sites Worker suite: three tests pass, including cookie forwarding and offline state.
- Independent PublicGateway integration confirms fight cookies cannot read
  private classroom state, create cameras or mutate events.
- Actual local GPU service reports X3D-M on CUDA, with single-stream ownership.
- Browser sample interaction returns real review signals for grappling.
- Browser shadowboxing interaction returns clear windows without review signals.
- Stop closes the stream and health confirms the GPU slot is released.
- Desktop 1280x800 and mobile 390x844 layouts were visually inspected.
  Both have no horizontal overflow; source controls, form labels, focus styles,
  status/alert roles and sample attribution are present.
- No application console errors on the current verified browser tab.
- Videos and inference history stay in memory; no demo footage/events are persisted.

## Limits

This is a scene-classifier demo, not the complete two-person/tracked incident
pipeline. No calibrated probability, contact, intent, identity or production
accuracy claim is made. Source seeking can run slower than playback. Physical
webcam/phone execution is unverified. The public deployment depends on the PC
service and temporary bridge remaining online; deployment/live checks are
recorded by the Sites tools separately.

## Public access restoration ? 22 October 2026

Hosting-only restoration of the existing approved `/fight` interface; no new visual concept or source build. Sites project `appgprj_6ab0ca77fc5c8191b14a130684b40844` remains public. Reused saved version 8 and refreshed only the protected runtime bridge credentials/upstream. Deployment `appgdep_6ad96756eae88191b918708cc05f365b` succeeded with environment revision 4. No training data, model weights, credentials, or local research artifacts were packaged or published in this operation.

Public entry: https://nivra-vision-lab.topperly.chatgpt.site/fight

Fresh checks:
- Anonymous HTTP `/fight` returned 200, with no Site sign-in required. Public health reported ready, X3D-M, CUDA, busy false after completion. Anonymous protected `/api/v2/me` returned 403.
- Browser grappling sample completed: 20 analyzed windows, 17 review windows, final displayed score 0.997. These are overlapping classifier windows, not independent incidents or accuracy evidence.
- Browser non-fight/shadowboxing sample completed: 16 analyzed windows, zero review windows, final displayed score 0.123. Both runs used the PC GPU through the public Site WebSocket connection.
- Inspected desktop 1280x800 and 1280x900 and mobile 390x844. No horizontal overflow at the checked desktop/mobile sizes; source preview, controls and results remained present. File input has its visible label; keyboard focus styling is present. This is a bounded accessibility check, not a full WCAG audit.
- Console inspection found Electron preview-host startup errors and aborted blob seek requests; no application exception stopped either completed model run. Own-file selection and physical webcam permission/capture were not exercised in this restoration check.
- Kept the selected baseline checkpoint and classifier threshold unchanged. The fine-tuned offline candidate was not promoted. PC service and tunnel are intentionally left running; PC sleep/shutdown or tunnel exit interrupts remote inference.

Evidence: desktop completed grappling screenshot `C:/Users/harsh.DESKTOP-VE90R6D/.t3codex/userdata/browser-artifacts/browser-screenshot-nivra-vision-lab-topperly-chatgpt-site-mviv9rg7-6245665c.png`; mobile `browser-screenshot-nivra-vision-lab-topperly-chatgpt-site-mvivagg7-a0b448bb.png`; final desktop `browser-screenshot-nivra-vision-lab-topperly-chatgpt-site-mvivcjse-dab8aa17.png` in the same directory.

final result: passed

---

# Police contact QA â€” 23 October 2026

Scope: contact-police extension to the established black/white guard and review flows.
Route: universal-design-router â†’ design-preflight-orchestrator; React best-practices review supports verification. No new visual direction, assets, stack, or services.
Source contract: the owner's supplied two-step Police / Call 112 / Text police / Cancel specification, existing `gd-btn` / `cm-btn` styles, and unchanged guard/review journeys. Small in-system change; concept gate waived explicitly by owner.

## Browser evidence

Used the T3 collaborative preview against a synthetic relay-only app on `127.0.0.1:5184`; no public host or model inference. Inspected actual desktop (1280Ã—800) and mobile (390Ã—844) screenshots.

- Reviewer: disclosure starts closed; Call and Text expose the exact URI contracts; camera and location are encoded in the SMS message. Each click reached the real audit API. A QA-only document listener intercepted OS navigation after the component handler and verified `defaultPrevented === false`; no emergency call or message was placed.
- Reviewer: latest contact updates from the response/snapshot. Simulated fetch rejection renders the required error. Cancel restores focus; Enter reopens the disclosure. Dialog scrolling reaches the controls on mobile without horizontal overflow.
- Guard incoming and responding: checked both screenshots and interactions. Controls are 54 px high, with black text on white incoming UI and white text on black response UI. Reviewer links are 44 px high. Labelled groups, focus outlines, wrapping and native anchors retained.
- Real guard Text request records `guard:G2`, renders as G2, then keyboard acknowledgement succeeds. Contact remains visible on the response screen and through snapshots.
- Wall: the incident status displays its contact. A new incident cannot inherit an older closed incident's contact label; integration regression test added.
- QA caught a duplicate React sibling key shared with the acknowledgement slider. Fixed with a police-specific key, added clock-advance regression coverage, rebuilt, and verified one control remains through repeated clock ticks.
- Console inspection: no uncaught component errors in the corrected flows. Earlier expected 403 responses came from unauthenticated/role-switch probes; the abandoned Vite preview failed because its watcher scanned Windows pytest temporary links. Production static preview was used successfully.

## Automated evidence

- `npm run lint`: passed without warnings.
- `npm run test -- --pool=threads --maxWorkers=2`: final shared-checkout run 701 passed, 77 files. Default fork workers timed out on this machine; thread workers complete successfully.
- `npm run build`: passed after the final web changes.
- Backend final full suite: 1,170 passed, 5 skipped, 1 existing Starlette/anyio deprecation warning in 299.02 seconds. Run from `service` with `NIVRA_RUN_CUDA_TRAINING_TEST=0`, `--ignore=tests/test_public_host_tools.py --ignore=tests/test_local_host_tools.py`, and an isolated `--basetemp`. No other files excluded.
- `node --test sites/worker.test.mjs`: 7 passed. Existing relays forward both police endpoints; no relay changes needed.
- Full-suite validation exposed two fixture portability issues: the discovery lifecycle test now mocks interface enumeration; the USB framing test uses the pytest temporary directory and real socketpair bytes with only the unavailable Unix connection adapter mocked on Windows. Two lifecycle tests now wait for the requested event revision while allowing repeated snapshots; exact result assertions remain.
- `git diff --check`: passed. No commits, pushes, branch changes, public hosts, or forbidden listeners. Isolated browser server/database and task-created test temporary directories cleaned up.

## Native boundaries

Android: URL policy and JUnit cases added; ACTION_DIAL / ACTION_SENDTO with `sms_body` implemented. No Android SDK; `where java` and `where javac` found neither executable, and checked standard installation locations contained no JDK. Java compilation, JUnit execution, and device handoff remain unverified.

iOS Swift unchanged as requested; the final handoff supplies the exact `UIApplication.shared.open` scheme change. No actual emergency services contacted. No commit, push, branch switch, deployment or secret handling.

final result: passed
