# NIVRA — app structure and UI/UX plan

Prepared for Harsh · 28 September 2026 · Camera Wall selected; extended image concepts in extended-screens/README.md. App remains unimplemented.

## 1. Product decision

NIVRA should open as a multi-camera operating workspace. Connect approved iPhones, Android phones, laptop webcams and, later, supported CCTV sources. Give each source a permanent place label. Show feeds together, bring a possible physical conflict to human attention, and carry the response through acknowledgement and resolution.

The primary job is: **See which camera needs attention, understand where it is and what changed, then coordinate a human response without losing awareness of the other cameras.**

Audience: campus safety teams and private-venue operators. Command is desktop-first; Respond and Capture are phone-first. A site can be a campus, building or venue; an event is a time-bound operating context within a site. English is the initial planning assumption; labels should support later localization.

Latest visual instruction: mostly black and white, with shadcn-style components. Use white and zinc surfaces, black text/buttons, thin grey borders and restrained amber review states. Retain NIVRA identity without flooding the app with the brandboard palette. The brandboard is identity reference; its claims do not prove detection/prevention performance. Earlier colored explorations are superseded. No app layout is approved yet.

## 2. What exists versus what is proposed

Inspected: `nivra-vision-lab/README.md`, `PRODUCT.md`, `package.json`, `src/App.tsx`, camera state handling and component/service inventory; plus the project context document and supplied brand image.

| Existing prototype, according to source/docs | Proposed product work |
| --- | --- |
| React 19, TypeScript, Vite, custom CSS | Preserve this stack for Command and an initial responsive Capture/Respond proof |
| Local camera, local video and scripted scenarios | Authenticated remote devices, pairing and a multi-camera media pipeline |
| Browser MediaPipe and experimental temporal motion rules | Independently evaluated detection service, per-camera state and capacity controls |
| Local review banners and acknowledgement | Operator ownership, dispatch, delivery receipts, responder acknowledgement and audit history |
| Frames are not uploaded, recorded or persisted in this prototype | Explicit live transmission policy and separately authorized replay/retention design |
| Current documentation describes one selected pair and a global alert cooldown | Independent concurrent reviews; one camera must not suppress another camera's alert |

This plan does not establish operational detection accuracy. The repository itself documents model-use limitations. Model suitability and representative evaluation are prerequisites for an operational pilot, not something a UI redesign resolves.

## 3. Product surfaces and navigation

### Command — operator laptop / desktop

| Navigation | Primary job | Essential contents |
| --- | --- | --- |
| **Live** — default | Monitor the site | Saved camera walls, zone filters, layout controls, persistent review rail, health summary |
| **Reviews** | Decide what needs action | Unclaimed/mine/all filters, event age, location, replay, observations, quality limits, claim and decision |
| **Incidents** | Coordinate and close | Active response, assignments, acknowledgement clock, notes, timeline, resolution and handover |
| **Locations** | Understand coverage | Site → building → floor → zone; floorplan pins, camera direction, linked camera list |
| **Analytics** | Improve operations | Review outcomes, response times, camera health, detector workload and coverage gaps |
| **Devices** | Connect and maintain | Add camera, pair device, source health, configuration, renew/revoke, maintenance |
| **Team** | See response capacity | On-shift availability, assigned zones, workload, contact and handover |
| **Settings** — role gated | Govern the site | Detection rules, notifications, roles, evidence policy, audit log |

Site selector and search persist at the top. Persistent alert count follows the operator into Analytics and Settings. An active incident remains reachable without reopening the camera wall. Administration uses secondary pages within Command, not another competing dashboard.

### Respond — staff phone

Navigation: **Tasks / Shift / Contact**. The active task dominates the home view. Each task carries incident ID, site, floor, zone, landmark, assigned time and operator contact. Actions follow the actual state: Acknowledge or Cannot respond → En route → On scene → Request backup / Situation clear. Resolution captures a short outcome and note. A location diagram is optional; text directions always work.

### Capture — approved phone or laptop webcam

A single-purpose flow: Pair → Confirm site/location → Select camera → Check framing/connection → Start feed → Feed health → Stop or disconnect. A Capture device cannot browse other cameras, receive responder tasks or change its own authorization.

Public Trust information is a later supporting page; it never exposes live video. This plan does not include a marketing website.

## 4. The default Live workspace

Desktop starting grid: approximately 180–208 px navigation, flexible video wall, 288–320 px review rail. Final dimensions depend on the selected concept. Make useful space for footage rather than oversized KPI cards.

```text
NIVRA | Site / Building              Search           Connection / Operator
Nav   | View: North campus  [4] [9] [16]  Filters  Save view   Add camera
      | Camera 01       Camera 02       Camera 03   | Needs review
      | location        REVIEW          location    | Gate 02 · 18s ago
      | Camera 04       Camera 05       Camera 06   | Possible conflict
      | location        location        OFFLINE     | Open review
      | Camera 07       Camera 08       Camera 09   | Other active incidents
      |---------------------------------------------------------------
      | Coverage: 8 connected · 1 offline | Analysis: 7 active · 1 paused
```

**Grid controls:** 1, 4, 9 and 16 visible slots; a 1-large-plus-5-small focus layout; drag to reorder with an equivalent Move menu; pin; full-screen; fit/contain; saved personal and shared layouts; zone and health filters. These are layout options, not guaranteed concurrent stream capacity. Performance tests determine enabled stream limits on each target device.

**Every tile:** camera name; site/floor/zone; LIVE, REPLAY or STALE label; connection state; separate analysis state; visible event badge when relevant. Hover/focus exposes expand, locate, quality and menu. Main status remains visible without hover. Optional technical detail belongs in an inspector, not over every frame.

**Stable positions:** an alert outlines the tile and adds a text badge, but does not reshuffle the entire wall. The matching queue item and location pin highlight together. Optional focus-on-alert is an explicit operator setting; never steal focus from an open incident. Off-screen cameras still produce visible queue entries.

**Multiple events:** confirmed urgent incidents rank first, followed by priority and age. Show owner and acknowledgement state. Group repeated observations from the same event while retaining its timeline. Two independent cameras must remain independently actionable. A merge across cameras requires human confirmation.

**Alarm behavior:** one short configured sound plus persistent visual status; no perpetual flashing. Test audio at shift start. Sound muted is a visible state and never removes the review. No ambient microphone capture is planned.

## 5. Camera pairing and device lifecycle

1. In Devices, choose **Add camera** → Phone / Laptop webcam / Existing IP camera. Mark IP camera integration unavailable until implemented; do not expose a fake working connector.
2. Select site, building/floor, zone, camera name and landmark. Place a pin on an uploaded floorplan if available. Location is explicit setup data; GPS is not assumed to know the indoor floor or room.
3. Generate a short-lived, one-use pairing QR and equivalent typed code. Scope it to one site and a pending device. A code alone must not grant organization-wide access.
4. Capture opens the invitation, displays the organization/site and requests camera permission after a clear user action. Laptop users can select a USB webcam; phone users can switch front/back where supported.
5. Command approves the pending device; compare a short verification code and preview. Save stable device ID separately from its editable display name.
6. Run a readiness check: image visible, correct orientation, usable framing, connection available, analysis status known. Show unsupported battery/thermal data as unavailable, never invent readings.
7. Start feed and show confirmation on both devices. The new tile includes its assigned location.
8. During use, show reconnecting, degraded, stopped, expired or revoked states. Credential renewal and shift expiry must be explicit. Revocation ends media access as well as API access.

Capture must say **Keep this screen open** for the initial browser proof. Do not promise locked-phone or background capture. Validate actual iOS Safari, Android Chrome and laptop behavior before a native-app decision. Secure camera access, screen lock, power management, battery APIs and heat behavior are device-dependent engineering checks.

The camera's installed location remains visible even if the stream fails. A moved device needs location/framing revalidation. A location edit records an effective time so historical events keep their original location snapshot.

## 6. Alert → review → response

1. An experimental detector emits a candidate, labelled **Possible physical conflict — review required**. Never turn its internal score into a probability of violence.
2. The camera tile, queue entry and location pin gain the same review status. Show event age and a consistent event ID.
3. **Open review** enters Focus: enlarged relevant feed, explicit LIVE/REPLAY switch, recent sequence if available, nearby cameras and a plain-language evidence panel.
4. Evidence distinguishes observed movement from quality limitations. Show unavailable replay explicitly. A live feed is not presented as the earlier event.
5. **Claim review** establishes one owner atomically; other operators can observe. Supervisor takeover is logged. Claiming is not confirmation of a conflict.
6. Decisions: **Dismiss** with reason; **Keep watching** with a visible reminder; **Confirm incident**. After confirmation, **Assign responder** opens a recipient picker with availability, zone and existing workload. Permit urgent manual dispatch with a recorded human decision.
7. Command shows **Sending → Delivered → Awaiting acknowledgement → Acknowledged → En route → On scene**. Delivery is never treated as acknowledgement.
8. Cannot respond, timeout or backup request stays visible and exposes the configured reassignment/escalation path. No eligible responder means **No responder available**, with manual control-room procedure.
9. Responder submits an outcome; operator resolves or escalates. “No impact recorded” is an optional human-entered observation, never an automatic claim of prevention.
10. Unresolved work enters shift handover and remains owned until the receiving operator accepts it.

## 7. Locations and maps

Start with a location hierarchy and camera list; support a user-uploaded 2D floorplan with manually placed pins. Clicking a pin opens the feed; Locate from a tile selects the pin. Floor switch, named landmarks and a list equivalent must work without geocoding.

Separate **camera health** from **incident priority** using different badges/shapes. A coverage cone is a configured approximation, not proof of visibility. Phone cameras can move; their setup must flag stale placement. Do not display person trails, identity tracking or an exact responder dot without a separately defined source, permission and freshness rule.

Venue mode adds opening hours, event/shift labels and temporary-device expiry. Campus mode emphasizes buildings, floors, entrances and fixed zones. Both share the same underlying site model.

## 8. Analytics that lead to a decision

Keep Analytics on its own page with tabs **Response / Review quality / Camera health**. Filters: date range, site, floor/zone, camera, detector version and operating schedule. Every chart links to the underlying records, displays timezone and sample size, and distinguishes missing data from zero.

| Metric | Definition | Decision it supports |
| --- | --- | --- |
| Review volume | Unique candidates after documented deduplication | Which zones or rules create workload? |
| Confirmation share | Confirmed / (confirmed + dismissed); pending shown separately | Which rules need investigation? This is not detector accuracy |
| Dismissal reasons | Human reason counts, with denominator | Is play, poor framing or duplicate evidence driving reviews? |
| Time to review | First human review/claim time minus candidate creation; median and p90 | Are queues being neglected? |
| Time to acknowledgement | Responder acknowledgement minus assignment creation; per assignment attempt | Are notifications or staffing failing? |
| Time to on-scene | On-scene minus acknowledgement | Are directions and coverage adequate? |
| Camera uptime | Fresh connected seconds / scheduled monitoring seconds | Which devices need maintenance? |
| Analysis coverage | Seconds with valid analysis / scheduled analysis seconds | Is video present but detection unavailable? |
| Stream health | Bitrate, received FPS, jitter/packet loss where measured; freshness | Is the network or device limiting visibility? |
| Review density by zone/time | Counts normalized by observed camera-hours, with coverage shown | Where should staff inspect operations? Not a crime prediction map |

Use daily trend lines, a location table and a time-of-day matrix; avoid a wall of donuts. Show explicit empty, partial-period and insufficient-data states. Exclude demos, training events and test tones by default. Corrected outcomes retain audit history. Do not invent precision/recall without a labelled evaluation set that includes missed events.

## 9. Adjustment controls

| Scope | Controls | Safeguard |
| --- | --- | --- |
| Personal workspace | Layout, density, pinned cameras, theme, sound preference | Never changes organization detection policy |
| Camera display | Stream quality, contain/full-screen, local digital zoom | Digital zoom does not imply physical PTZ |
| Camera configuration | Name/location, source, permitted resolution/FPS, orientation | Apply preview, show reconnect impact and log edits |
| Detection policy | Enable module, active schedule, region of interest, calibrated sensitivity presets, cooldown | Role gated; explain effect, preview on staged clips, version and roll back |
| Notification policy | Recipients, priority, repeat suppression, acknowledgement timeout and escalation | Test path; suppression must not hide unresolved incidents |
| Evidence policy | Whether replay exists, retention, export roles and deletion | Explicit administrative policy and audit; never silent recording |

Avoid a single “AI sensitivity” slider that suggests universal reliability. Separate pose visibility thresholds, event rules and alert cooldown. Existing low-level lab controls belong in an Advanced diagnostics area, not an operator's main screen.

## 10. UI system and responsive behavior

White #FFFFFF and zinc #FAFAFA provide surfaces; #18181B provides text and primary buttons; #E4E4E7 provides borders. Amber means review needed, red is reserved for urgent confirmed incidents or destructive actions, grey supports neutral/unavailable states. Labels and icons accompany states. Follow shadcn-style primitive behavior and spacing; do not add green or chartreuse dashboard chrome.

Retain the repository's system sans stack initially; use tabular numerals for clocks and metrics. Proposed scale: 12px secondary metadata, 14px dense desktop labels, 16px body/mobile, 20–24px section headings. Metadata must remain zoomable; critical location/action labels cannot be tiny. Use a restrained 4/8px spacing rhythm, approximately 6–8px control radii, opaque surfaces and visible borders. Brandboard display type is for brand moments, not dense event rows.

Desktop 1440/1920: wall + queue. Compact laptop 1280: narrower nav, four or six useful tiles; queue still reachable. Tablet: wall and review become adjacent tabs or a drawer while alert count persists. Phone Command: prioritized camera list and one feed at a time, not a shrunken nine-feed wall. Respond/Capture: single-column, large actions, safe-area padding, landscape preview where useful.

Target WCAG 2.2 AA in implementation: measured contrast, keyboard-complete actions, visible focus, labelled video controls, non-drag reordering, screen-reader status announcements with throttling, accessible tables, reduced motion and no flashing urgency. Prefer 44–48px phone targets. Preserve focus during new alerts and restore it after dialogs. These are acceptance requirements, not a claim that generated raster screens are accessible.

## 11. Proposed technical shape

```text
Capture: phone / laptop webcam     Later: IP camera gateway
             | authenticated live media          |
             +-------- Media relay / SFU ---------+
                         |             |
                  Command viewers   Analysis workers
                                           |
                       Candidate/event service
                              |
              Command review + durable incident state
                              |
                 notification service → Respond
                              |
                  acknowledgements + audit → Analytics
```

Recommendation for a multi-viewer pilot: WebRTC media transport with authenticated signalling, TURN fallback and a relay/SFU so each Capture device need not send a separate full stream to every viewer. Use a lower-quality wall stream and promote the selected feed where supported. This is a proposed architecture, not a chosen vendor or provisioned service. A small peer-to-peer spike can validate pairing but must not be mistaken for production scaling. [WebRTC connection guidance](https://webrtc.org/getting-started/peer-connections).

Run per-camera analysis independently of which feed the operator opens. Avoid making one laptop tab the sole monitoring authority for a site. A site appliance or hosted worker deployment remains an explicit later decision based on network, privacy and measured capacity. RTSP/ONVIF sources need a supported gateway/integration; do not promise that every camera URL plays in a browser.

The current no-recording prototype cannot supply pre-event replay automatically. Proposed replay requires a bounded rolling buffer, explicit policy, retention/deletion mechanics and visible recording state. Keep live transmission, temporary buffering and retained incident clips separate in the data model and UI.

Core records: Organization, Site, Location, Device, CameraSource, StreamSession, CameraHealth, DetectionPolicyVersion, Candidate, Incident, Assignment, ResponseUpdate, EvidenceAsset and AuditEvent. Store stable IDs, site scope, timestamps and server revision. Candidate snapshots include camera location, rule version, quality limitations and observed interval. Media references carry separate access rights and expiry.

Mutations such as claim, confirm, assign, acknowledge and resolve require validated transitions, server-side role/site authorization, idempotency keys and optimistic concurrency. Reconnect resumes from an event cursor. Offline response updates show **Pending sync**, retain original client time plus server receipt time, and must not overwrite a newer resolved/transferred assignment. Media access is separately authorized and revocable. Logs must avoid raw footage, tokens and unnecessary personal data.

No backend provider, cloud region, recording duration, supported camera count or detection latency is approved by this plan. Resolve these through a hardware/network spike and site requirements before committing to an operational architecture.

## 12. Failure-state contract

| Failure | Required UI and recovery |
| --- | --- |
| Permission denied / camera busy | Specific device instructions, retry and choose another camera; preserve pairing context |
| QR expired or already used | Explain why; generate a new code from Command |
| Phone locks or Capture loses camera | Mark feed interrupted; show last fresh frame time and restore instructions |
| Video connected, analysis stalled | Separate warning: Live video / Analysis unavailable; never show monitoring healthy |
| Stream frozen | Label STALE with elapsed time; do not leave a green LIVE badge |
| Network congestion | Lower preview quality where supported; show degradation and affected feeds |
| Replay absent or expired | Explain missing evidence; retain metadata permitted by policy |
| Concurrent operator claim | Show current owner; offer supervisor transfer, not duplicate dispatch |
| Responder offline or no acknowledgement | Pending delivery/acknowledgement state, timed escalation and manual contact |
| Command reload / laptop disconnects | Rehydrate server state; other operators and analysis continue where deployed |
| Map missing | Full location text and camera list remain functional |
| No data / no events | Distinguish no recorded events from disabled monitoring or missing telemetry |

## 13. Build sequence and acceptance gates

| Phase | Deliverable | Exit evidence |
| --- | --- | --- |
| **0 — Design selection** | Three branded multi-camera layouts; this structure, state and metric contract | Harsh selects one; refinements recorded before code |
| **1 — Device/network spike** | One iPhone, one Android and one second laptop feeding one dashboard on an authorized test setup | Measured freshness, reconnect, foreground/lock behavior and CPU/network cost; no supported-device claim from simulation |
| **2 — Multi-camera foundation** | Auth/site roles, pairing, location assignment, 4-feed wall, saved layout, health and revoke | End-to-end tests plus actual device checks; access isolation and stream revocation verified |
| **3 — Review journey** | Independent candidates, camera highlight, claim, focus, explicit replay policy, dismiss/monitor/confirm | Two simultaneous events; stale feed, missing replay and concurrent claim scenarios pass |
| **4 — Response journey** | Respond tasks, acknowledgement, backup, reassignment, resolution and handover | Real two-device acknowledgement and outage recovery; duplicate submissions do not duplicate actions |
| **5 — Analytics and tuning** | Defined metrics, drill-downs, versioned rules, audit and operational reports | Fixtures reconcile chart totals to source events; missing/demo data handled correctly |
| **6 — Controlled pilot readiness** | Capacity envelope, evaluated detector, operating procedure and support ownership | Representative positive/negative evaluation, limitations documented and named human owner accepts readiness |

Keep the existing Vision Lab available as a labelled diagnostic harness. Reuse its camera lifecycle, worker cancellation and audio controls where suitable; do not copy its single-session assumptions into multi-camera orchestration.

Repository validation commands for later implementation: `npm run lint`, `npm run test`, `npm run build`, `npm run test:e2e`. Add integration checks for site authorization, pairing replay, revocation, per-camera isolation, concurrent ownership, idempotency, offline reconciliation and metrics. Browser QA must cover 390/768/1280/1440 widths, keyboard, zoom, reduced motion, console and visual comparison. Planning work does not require pretending these tests already ran.

## 14. Usability validation plan

Recruit actual campus/venue operators and responders for formative testing after a clickable prototype exists. Proposed tasks: connect a phone to the correct floor; identify the highlighted camera; distinguish replay from live; handle two reviews; assign an available responder; recover from no acknowledgement; locate an offline camera; explain a chart's denominator.

Record task completion, wrong-camera actions, state confusion, missed parallel events and recovery errors. Any wrong-camera dispatch or mistaken delivery-as-acknowledgement is a release-blocking design defect. Timing goals should be set with site staff after baseline observation; no usability sessions or performance gains are claimed here.

## 15. Direction choice

The new concepts must all honor this brand and multi-camera requirement. Compare composition, not palettes:

1. **Watchfloor:** persistent grid, compact queue and small location panel. Most direct match to the requested security-camera experience.
2. **Incident Focus:** one selected camera enlarged with the rest retained in a filmstrip/grid and a strong evidence/response rail. Better during review; fewer equally sized feeds.
3. **Spatial Desk:** grid and 2D floorplan share the workspace, with an incident queue beneath/beside them. Strong location context; less room per feed.

Recommended starting point: Watchfloor as the default operating view. Focus and location views can be available modes after a single coherent visual direction is selected; mixing unapproved compositions is not assumed.

Companion files: `design-research.md`, `design-qa.md`, generated concept PNGs and `concept-prompts.md`. Status remains **awaiting-selection**. No app code, deployment or production configuration is changed by this planning package.

