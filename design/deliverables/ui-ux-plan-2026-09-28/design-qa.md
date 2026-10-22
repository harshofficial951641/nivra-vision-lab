# NIVRA concept review

Status: Camera Wall composition selected through the screenshot supplied by Harsh. Extended screens are in extended-screens/README.md. Generated raster concepts, not implemented or user-tested interfaces.

Latest visual constraint: black, white and neutral greys; shadcn-style controls. Colored dashboard explorations are superseded. The supplied logo remains canonical; wordmark-only concepts avoid treating an image-generated symbol as a replacement logo.

All three final images were visually inspected directly in imagegen output. Each presents six sources, a review location, human review actions and an offline source. The camera wall was corrected to remove an invented logo icon, neutralize live dots and distinguish live video from paused analysis.

- 01-camera-wall.png: six equal tiles plus queue/location rail. Strongest default monitoring layout. Text and core actions visible; source/analysis states separated.
- 02-review-workspace.png: explicit replay, five other source thumbnails, evidence and human decision actions. Core review state readable. Raster demo timestamps are illustrative and not a canonical event-time specification.
- 03-location-workspace.png: six tiles alongside a labelled map and review table. Location context is strongest, with smaller footage. Hall A's two separate health labels must be explicit in implementation; map geometry is illustrative, not a real site plan.

These images are sufficient to compare composition. They do not prove interaction, accessibility, responsive layout, feed latency, detection accuracy or backend behavior. Exact iconography, timestamp consistency, semantic states, keyboard controls and measured contrast remain implementation QA. No code or service changes were made.

Gate: Harsh selects a direction before dependent implementation. His standing instructions and ultimate-design/SKILL.md require three independently generated, visually checked concepts and selection; no extra deployment authority follows from selection.
