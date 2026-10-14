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

final result: passed
