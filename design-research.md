# Classroom command surface — concept brief

28 September 2026. Design owner: design-preflight-orchestrator, routed once by universal-design-router. The existing React/Vite/TypeScript stack stays. Ideation is a bounded image-generation support task; backend accuracy work is independent of visual selection.

Confirmed: 2–4 classrooms, one iPhone/Android/laptop camera per room, 30–50 people each; different networks/mobile data; live video plus event metadata only, no video retention. A school operator locates a possible physical incident, inspects the live feed, acknowledges, and records an outcome. No facial recognition, named student tracking, argument/audio classification, or automatic disciplinary decisions.

The existing mark was directly inspected at `../assets/pitch/logo.png`. Preserve forest #14251D, lime #D2F56A and paper #F7FAF5. Current single-camera UI is functional experimental tooling; its layout is not an approved dashboard visual.

Experience thesis: give the operator stable classroom views and a precise review queue, with analysis gaps as visible as alerts. Feed health and model coverage are separate. History has metadata, not playback controls. No camera-replay or clip-download affordance in these concepts.

## Bounded primary research

- Verkada's documented [camera grids](https://help.verkada.com/verkada-cameras/video-streaming-and-sharing/live-streaming/grids) supports the familiar persistent grid convention. Retain stable camera placement; Nivra adds analysis-age/limited-coverage labels beside video health.
- Ubiquiti's documented [camera zones](https://help.ui.com/hc/en-us/articles/360056987954-UniFi-Protect-Manage-Camera-Zones) supports explicit region configuration. Nivra's zones should show where analysis is applied and the effect on coverage.

These are documentation observations, not hands-on competitor usability tests or validated user research. No competitor layouts/assets are copied. Component plan: CSS grid video wall; native controls for filters and settings; accessible dialog/drawer for review and pairing; semantic event table/list; SVG icons from an established library during implementation. No 3D required.

## Three distinct visual hypotheses

- Camera wall: four equal stable feeds dominate, with a narrow review rail. Best for scanning every room continuously.
- Focus and respond: one expanded selected feed, three smaller persistent feeds, and a structured review panel. Best for detailed live inspection while retaining room awareness.
- Location desk: classroom/location navigation alongside stacked wide feed rows and a compact event ledger. Best for operators navigating rooms and checking status methodically.

All are 1440×1024 desktop concepts with conspicuous sample-data labelling, four classroom locations, one possible-incident state and one coverage/connection limitation. Forest/lime/paper are shared brand constraints, not three superficial colour variants. Mobile continuation is a focused camera publisher with room assignment, preview, lens switch and Stop sharing.

Selection gate: exactly three independently generated, visually inspected concepts, then Harsh chooses the direction before dashboard code. Source: Harsh's AGENTS instructions and `design-preflight-orchestrator/SKILL.md`. This gate does not block authorised detector fixes or tests.

## Approved implementation contract update

The design chat supplied Harsh's newer selected camera-wall reference at
`../output/ui-ux-plan-2026-09-28/extended-screens/00-selected-reference.png` in the
parent Nivra workspace. This supersedes the earlier green option 3: white/zinc
surfaces, black primary actions, gray borders and a stable camera wall.
Implementation preserves the supplied canonical logo and uses Phosphor icons.

Scope reconciliation: four classrooms rather than the mock's six campus cameras;
location directory rather than invented map geometry; event-only history rather
than replay; explicit generated sample imagery rather than simulated live feeds.
No Team/Respond account service or external notification deployment was inferred
from the extended concepts. Source-to-render evidence is in `design-qa.md`.
