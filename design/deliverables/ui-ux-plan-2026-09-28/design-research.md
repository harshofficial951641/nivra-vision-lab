# NIVRA — comparative product research

Inspected 28 September 2026. Scope: official public documentation and product pages; read-only browser inspection of Verkada documentation. No authenticated product sessions, customer interviews, analytics or measured competitor usability. This is a workflow study, not a full hands-on product audit. A large Verkada brochure could not be fetched by the web tool; no visual conclusions rely on it.

| Reference | Documented pattern | NIVRA adaptation / decision |
| --- | --- | --- |
| [Verkada Camera Grids](https://help.verkada.com/verkada-cameras/video-streaming-and-sharing/live-streaming/grids) | Saved layouts, selectable camera tiles, reordering, personal/shared views and a home grid | Make Live a stable saved wall. Keep off-screen alerts visible; do not auto-cycle away from an unresolved incident |
| [Verkada Operations](https://help.verkada.com/verkada-cameras/analytics/verkada-operations-user-guide) | Claiming tickets, operator permissions, clip/live switching, activity history and filters | Separate ownership, review decision and responder acknowledgement; show each explicitly |
| [UniFi Alarm Manager](https://help.ui.com/hc/en-us/articles/27721287753239-UniFi-Alarm-Manager-Customize-Alerts-Integrations-and-Automations-Across-UniFi) | Rules separate trigger, scope and action; schedules and repeated-action suppression | Use a clear rule builder: observed event → cameras/zones/time → notify/review. Suppression does not erase incident state |
| [AXIS Camera Station Pro manual](https://help.axis.com/en-US/axis-camera-station-pro) | Live viewing and playback are distinct; search can use time/area filters; a separate analytics dashboard uses supported data sources | Separate Live, Reviews and Analytics. Offer charts only when the source metric is actually collected |
| [Genetec Mission Control](https://www.genetec.com/products/operations/mission-control) | Vendor describes coordinated detection-to-response and guided incident handling | Add concise site procedure and escalation next to an incident; treat claimed benefits as vendor claims |

## Synthesis

Keep familiar camera walls, explicit locations, saved layouts, clip/live separation, event ownership and device health. NIVRA's original emphasis is the connection between an ordinary approved device, an understandable movement sequence and a human response. Do not copy identity analytics, police dispatch automation or door-control capabilities from these products.

The risk to test is fragmented context: an operator should not need to memorize a camera name while moving between video, map and response. Persistent camera/event IDs, cross-highlighting and location breadcrumbs are proposed remedies. This is a design hypothesis, not an observed failure rate in competitors.

## Technical feasibility sources

- [WebRTC peer connections](https://webrtc.org/getting-started/peer-connections): media connection and signalling are separate; STUN/TURN participates in connectivity. Proposed relay/SFU architecture is our recommendation, not a provisioned integration.
- [WebKit WebRTC discussion](https://webkit.org/blog/7763/a-closer-look-into-webrtc/): documents permission and capture constraints. It is historical guidance, not proof of current target-device background behavior; actual devices remain a required spike.
- [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/): target for later implementation verification, not a raster concept certification.

## Component feasibility

Prefer existing React/TypeScript/CSS conventions. `ObservationRail`, `ConflictPanel`, `BrowserCameraSource`, `VisionWorkerClient` and `ReviewTonePlayer` are source-backed reuse candidates, not drop-in multi-camera components. Their lifecycle and single-session assumptions need review during implementation.

Proposed custom components fill product-specific gaps: CameraWall, CameraTile, AlertQueue, ReviewWorkspace, LocationPicker, PairingSession, AssignmentPanel and HealthStatus. Use native buttons/selects first; any dialog primitive or chart library must be inspected for compatibility, accessibility, license and maintained version before installation. No UI library is imported in this plan. Decorative component catalogues were considered unnecessary for an operational wall.
