# NIVRA complete project context

Prepared for Harsh Jain on 17 September 2026.

## 1. Identity

- Team name: Team Damage Control
- Project name: NIVRA
- Product line: Before impact.
- Working brand statement: Intelligence for the seconds that matter.
- Current status: product definition, working browser vision prototype, interface experiments, and brand exploration

## 2. Short explanation

NIVRA is a human-supervised early-intervention system for public spaces. It connects existing security cameras, temporary phone cameras, a control-room laptop, and multiple responder phones.

The system watches for visible movement sequences that may need attention. Examples include people repeatedly closing distance, unusually aggressive movement, chasing, crowd convergence, entry into a restricted area, or a sudden change in crowd density. NIVRA gives a human operator a short explanation and replay. The operator decides whether the event matters and whether a responder should be sent.

NIVRA does not identify people, infer guilt, predict crime, or automatically make policing decisions.

## 3. The problem

Most CCTV systems are passive. Someone must watch every feed continuously, or footage is reviewed after an incident.

NIVRA is built for the short interval when a situation is developing and a trained person may still be able to intervene. The product is meant to reduce the time between an observable warning pattern and a human response.

## 4. The first proof

The first complete demonstration should show one simple chain:

1. Phone 1 becomes a secure camera.
2. A confrontation-forming sequence is staged in front of it.
3. NIVRA observes movement over several seconds.
4. The control-room laptop receives a review event.
5. A human operator watches the preceding 8 to 10 seconds.
6. The operator confirms the event and dispatches a responder.
7. Phone 2 receives a location-specific alert.
8. The responder acknowledges it, marks "On scene", and later marks "Situation clear".
9. The laptop records the complete timeline and displays "No impact recorded".

The important point is that a phone can become a camera, a laptop can act as the command centre, and several other phones can work as responder devices.

## 5. Product principles

1. A human decides before operational action is taken.
2. NIVRA studies a sequence over time, not one dramatic-looking frame.
3. Every alert explains the visible signals that caused it.
4. Normal operation is quiet. The interface becomes more prominent only when review is useful.
5. There is no facial recognition, demographic inference, emotion recognition, criminal database, or permanent identity profile.
6. The system uses the least video needed for the task.
7. Reviews, dispatches, exports, configuration changes, and deletions are logged.
8. One organization can run many sites, cameras, phones, operators, and response teams.
9. Failures such as an offline camera, low battery, stale video, or unavailable responder must be visible.
10. The brand should communicate calm intervention, not aggressive surveillance.

## 6. Who it is for

Possible users include:

- public-space and venue security teams;
- school and college safety staff;
- event marshals;
- campus control rooms;
- private venue operators;
- transport operators in a later phase;
- civic and government operations in a later, properly governed phase.

The easiest first controlled pilot is likely a campus, event, or large private venue. A metro or government deployment is a long-term credibility goal, not the easiest first pilot.

## 7. The five connected product surfaces

### 7.1 NIVRA Command

The desktop or web control room is used to:

- view sites and camera health;
- watch live feeds;
- receive possible incidents;
- replay the previous few seconds;
- see the observed signals in plain language;
- dismiss, monitor, confirm, or dispatch;
- coordinate responders;
- track acknowledgement and arrival;
- record resolution;
- search incident history;
- manage sites, zones, devices, teams, and policies.

The main screen should stay focused on the live scene. It should not become a wall of decorative metrics.

### 7.2 NIVRA Camera

This mode turns an approved phone into a temporary or semi-permanent camera.

The user scans a short-lived pairing QR code, confirms the organization and site, selects a zone and camera, grants camera access, passes quality checks, and starts the secure feed.

The camera mode should report:

- camera name and assigned zone;
- connection quality and frame rate;
- battery level and charging state;
- heat or thermal warnings;
- orientation and framing;
- analysis status;
- last-seen time;
- whether the feed is live, degraded, paused, revoked, or offline.

The display can dim or lock while streaming, but it must retain a clear stop control. A temporary camera credential expires after the event or shift.

### 7.3 NIVRA Respond

This is the phone experience for guards, teachers, marshals, event staff, supervisors, or other trained responders.

It can:

- show shift, site, assigned zone, and availability;
- receive incident alerts;
- show the exact site, zone, landmark, camera, and event age;
- show a short preview when policy permits;
- allow "Acknowledge", "Cannot respond", and "Request backup";
- show an internal route when a site map exists;
- update status through "Acknowledged", "En route", "On scene", "Need backup", and "Situation clear";
- call the control room;
- submit a short resolution note;
- work in a low-bandwidth text-only mode;
- queue updates while offline and send them when the connection returns.

### 7.4 NIVRA Admin

Administrators can:

- create organizations and sites;
- define floors, zones, landmarks, entrances, exits, and restricted regions;
- register permanent cameras and pair phone cameras;
- invite staff and assign roles;
- create shifts and response teams;
- define escalation rules;
- enable detector modules by zone;
- set evidence access, retention, export, and deletion rules;
- review system health, false alerts, access logs, and device status;
- revoke a lost device or temporary team.

### 7.5 NIVRA Trust

A public, site-specific transparency page can be reached from a QR code on a physical NIVRA notice. It explains:

- which kinds of patterns are analyzed;
- that facial recognition is not used;
- who operates the system;
- whether audio is processed;
- the usual retention policy;
- how to make a privacy request;
- when the policy was last updated.

It never exposes live cameras or incidents.

## 8. Multiple phones and organizations

NIVRA is designed for many devices.

- One person may use more than one trusted phone.
- Each phone has its own device identity, push token, permissions, and revocation status.
- One organization may connect many camera phones and responder phones.
- There is no shared "master phone".
- A permanent employee may be authorized for several sites.
- A temporary responder joins only a selected site, zone, and shift, then expires automatically.
- The same app may contain Camera and Respond modes.
- One device cannot stream as a camera and act as a live responder at the same time.
- Switching modes requires stopping the feed and confirming the interruption.

The organization structure is:

```text
Organization
|-- Sites
|   |-- Zones, floors, and landmarks
|   |-- Permanent cameras
|   |-- Paired phone cameras
|   |-- Detector policies
|   |-- Response teams and shifts
|   `-- Incidents and evidence
|-- Users and roles
|-- Organization-wide policies
`-- Cross-site reporting
```

## 9. Roles

- Organization owner: creates sites, appoints administrators, manages organization policy and billing.
- Site administrator: manages one or more sites, devices, zones, teams, retention rules, and audit logs.
- Control-room operator: reviews events, confirms or dismisses them, and dispatches responders.
- Shift supervisor: can reassign incidents, take over a review, activate emergency mode, and accept shift handover.
- Responder: sees assigned incidents and sends field status updates.
- Camera contributor: can run an approved phone camera for a specific time and place.
- Investigator or evidence reviewer: accesses approved incident records after an event.
- Auditor or privacy officer: reviews access, export, deletion, and policy logs.
- Temporary event staff: receives time-limited permissions for one event or shift.
- Government or portfolio viewer: a later role for authorized aggregate views, not unrestricted camera access.

## 10. What NIVRA observes

The initial detector is "Possible confrontation forming". It may combine:

- sustained face-to-face orientation;
- repeated closing of distance;
- elevated arm or upper-body movement;
- sudden acceleration;
- approach and retreat cycles;
- bystanders rapidly converging;
- an optional rise in non-speech audio intensity.

The prototype may use a transparent rule engine. Example weights are:

```text
Sustained face-to-face orientation      +20
Distance closing repeatedly             +20
Elevated gesture velocity               +15
Sudden acceleration                     +15
Approach and retreat cycle               +10
Bystanders rapidly converging            +10
Optional audio intensity spike           +10
Review threshold                          55
High-priority review threshold            75
```

These are tuning values, not probabilities. The interface should say "Observed signal level" or "Review priority", never "probability of violence".

NIVRA uses short-lived track IDs to understand movement across nearby frames. The IDs expire and are not identities. Cross-camera identity tracking is not part of the first product.

## 11. Detection and decision flow

```text
Camera frames
-> person, pose, and object observations
-> temporary anonymous tracks
-> movement features over several seconds
-> site, zone, and schedule rules
-> candidate event score
-> human review event
-> operator decision
-> dispatch and response workflow
```

Noise controls should require persistence across several frames, merge duplicates, suppress repeated alerts from the same interaction, and display when lighting, movement, occlusion, or low frame rate reduces reliability.

NIVRA must not silently retrain itself on operational footage.

## 12. Incident lifecycle

```text
Monitoring
-> Candidate detected
-> Awaiting review
-> Monitoring, Dismissed, or Confirmed
-> Dispatching
-> Acknowledged
-> En route
-> On scene
-> Resolved, Escalated, or Transferred
-> Supervisor review
-> Retained or deleted by policy
```

When a candidate is created, the operator receives the site, zone, camera, timestamp, short replay, observed signals, quality limitations, and review priority.

The operator can:

- dismiss it with a quick reason;
- continue monitoring;
- confirm that operational attention is needed;
- dispatch immediately based on human judgement.

Responder ranking may use shift status, zone, capability, workload, and estimated proximity. The operator confirms the recipient. The initial product does not automatically call police or outside emergency services.

If nobody acknowledges, NIVRA moves through the configured escalation tree and alerts the operator. A delivered push notification is never treated as acknowledgement.

## 13. Simultaneous incidents and teams

- The first operator can take ownership of a review.
- Other operators can watch without issuing duplicate commands.
- A supervisor can transfer or take over an incident.
- Each incident keeps its own state, timeline, and responders.
- Confirmed incidents rank above unreviewed candidates.
- A single operator can pin one incident without hiding another.
- Events seen by two cameras may be suggested as duplicates, but a human confirms the merge.
- Unresolved incidents must appear in shift handover and be accepted by the incoming operator.

## 14. Alerts and escalation

NIVRA uses five notification levels:

1. Informational, such as camera reconnected.
2. Review, when a candidate needs operator attention.
3. Dispatch, when a responder has been assigned.
4. Urgent, for a confirmed incident or backup request.
5. System critical, when several cameras or a core service fail.

Locked-phone notifications reveal minimal sensitive information. Previews require unlock when policy requires it. Alert sound and vibration are tested at shift start.

## 15. Camera health and failure behavior

Camera states include Live, Degraded, Moved, Offline, Paused by policy, Revoked, and Maintenance.

Examples of expected behavior:

- Camera shake pauses behavior alerts and produces "Camera moved" or "Unstable view".
- A covered camera becomes "Occluded".
- A hot or low-battery phone reduces frame rate and warns before stopping.
- A slow connection reduces resolution before dropping the feed.
- Stale footage freezes with an exact label such as "Last live 12s ago".
- A lost phone can be revoked immediately.
- A stolen pairing QR cannot create unlimited devices because links are one-time, short-lived, and site-bound.
- If no responder is available, the interface says so and shows the manual escalation contact.
- If the system fails, it displays affected sites, the last known operational time, and the manual fallback procedure.

The system must fail loudly and honestly.

## 16. Privacy, retention, and evidence

Data is separated into:

1. transient live frames;
2. a short rolling context buffer;
3. candidate metadata;
4. an approved incident clip;
5. the response timeline;
6. audit records.

Default direction:

- non-events disappear when the rolling buffer expires;
- dismissed candidates keep minimal permitted metadata;
- confirmed incidents follow a site-defined retention period;
- legal holds require an authorized person and a recorded reason;
- clip access and exports are role-limited and logged;
- exported evidence is watermarked or traceable;
- faces and number plates may be blurred where identity is not needed;
- deletion shows what will be removed and what legal obligations prevent removal.

Real deployments require jurisdiction-specific checks for consent, signage, employee monitoring, data retention, audio processing, and government access.

## 17. Product modules

1. Confrontation: possible escalation, aggressive movement, chasing, and crowd convergence.
2. Crowd flow: sudden density increase, counterflow, congestion, directional waves, or platform-edge crowding.
3. Restricted zones: a person or object enters a defined area at a restricted time.
4. Abandoned object: an object remains after its temporary associated track leaves.
5. Rapid separation or possible snatching pattern: close contact, object-zone change, sudden separation, and fast exit.
6. Site-specific rules: wrong-way entry, closed-gate loitering, after-hours access, queue overflow, or an obstructed door.

Each module is enabled only for the zones where it has a justified use. The product should not switch on every detector everywhere.

## 18. Large feature inventory

The full feature backlog contains more than 350 ideas grouped under:

- accounts, organizations, sites, and multiple phones;
- phone-as-camera operation;
- permanent CCTV and NVR/VMS connections;
- maps, zones, landmarks, and privacy masks;
- the live command centre;
- temporal detection and quality checks;
- human review and incident creation;
- incident ownership and collaboration;
- responder mobile workflows;
- dispatch and escalation;
- notification and communication systems;
- evidence, legal hold, and investigation;
- privacy, governance, audit, and public trust;
- reliability, security, and failure handling;
- training, calibration, test alerts, and drill mode;
- response and detector analytics;
- administration and automation;
- multi-site and authorized government views;
- future differentiators such as the Focus review mode, public trust QR, local edge hub, and cross-camera event merging.

This backlog is a planning pool, not a promise that everything belongs in the first build.

## 19. Exact hackathon scope

The following parts should be real:

- a phone camera connection;
- live transport to the laptop or local service;
- person and pose observations from the live feed;
- temporal signal calculation;
- creation of a review event;
- a notification to a second phone;
- responder acknowledgement returning to Command;
- a timestamped incident timeline.

The following can be simulated if clearly labelled:

- multiple permanent CCTV feeds;
- a preloaded site map;
- walking ETA;
- a government portfolio dashboard;
- long-term analytics;
- production-grade legal hold and encryption;
- a local edge-hub failover.

The demonstration should stay narrow. One excellent end-to-end flow is stronger than many half-working detectors.

## 20. Technical shape

The planned end-to-end prototype is:

```text
Phone camera PWA
-> HTTPS, WebSocket, or WebRTC transport
-> Python FastAPI service
-> MediaPipe or another pose-capable vision model
-> transparent temporal rule engine
-> WebSocket event stream
-> React and Vite Command interface
-> responder PWA or second phone
```

The current browser prototype already exists under `nivra-vision-lab`.

Current implementation:

- React 19, TypeScript 6, Vite 8;
- MediaPipe Tasks Vision 1.0.1;
- Pose Landmarker running locally;
- EfficientDet-Lite0 running locally for supported objects;
- separate Web Workers for pose and object detection;
- independent backpressure so stale frames are dropped instead of queued;
- temporary in-session person and object tracks;
- local observation rules for carried, separated, transferred, unattended, and restricted-object states;
- local review tones through Web Audio;
- browser camera permission, device selection, and clean track shutdown;
- no cloud upload and no video recording in the current lab.

Current verification on 17 September 2026:

- lint passed;
- 7 test files passed;
- 24 tests passed;
- TypeScript build passed;
- Vite production build passed.

The current lab is a local scene-intelligence proof, not yet the complete multi-phone Command to Respond system.

## 21. Current model boundaries

The included EfficientDet-Lite0 model uses COCO categories. It can recognize common objects such as backpacks, handbags, suitcases, phones, bottles, laptops, bats, knives, and scissors.

It cannot recognize every carried item. COCO does not include firearms. A claim about categories outside the model requires a separately trained and validated model.

The browser lab does not infer identity, demographic traits, disability, emotion, guilt, or intent.

## 22. Roadmap

### Phase 0: brand and demo shell

- settle the NIVRA identity and product language;
- build Command, Camera, and Respond shells;
- complete QR pairing;
- polish one incident flow;
- use staged demonstration data where necessary.

### Phase 1: working end-to-end prototype

- real phone stream;
- pose and person tracking;
- rule-based confrontation signal;
- candidate review;
- second-phone dispatch and acknowledgement;
- replay and timeline.

### Phase 2: controlled-site pilot

- named accounts and permissions;
- permanent camera ingest;
- real site and zone setup;
- reliable push notifications;
- retention and audit controls;
- camera-health monitoring;
- calibration and drill tools;
- pilot reporting.

### Phase 3: multi-site product

- full organization hierarchy;
- concurrent operators;
- shift handover;
- evidence governance;
- more carefully validated modules;
- multi-site reporting;
- enterprise authentication and device management.

### Phase 4: high-reliability infrastructure

- an on-site NIVRA Hub;
- local operation during internet failure;
- approved emergency-system integrations;
- jurisdiction-specific governance;
- procurement and independent security evaluation;
- independently evaluated detection models;
- authorized portfolio views.

## 23. What NIVRA must not become

NIVRA should not build or advertise:

- facial recognition;
- emotion recognition;
- demographic classification;
- criminal or threat probability scores;
- permanent tracking of named people;
- automatic punishment;
- unreviewed automatic police dispatch;
- covert deployment without required notice;
- public access to live cameras;
- weapons or suspect imagery as branding;
- a social-credit or behavior-ranking system;
- a chatbot as the primary interface;
- a fake command centre full of decorative graphs;
- dozens of unreliable detectors for a demo.

## 24. Product language

Preferred wording:

- Possible incident detected.
- Possible escalation.
- Human review required.
- Observable escalation pattern.
- Response team notified.
- Analysis limited by poor visibility.
- No impact recorded.
- Situation resolved.

Never use:

- Criminal identified.
- Crime predicted.
- Dangerous person detected.
- Threat neutralized.
- AI proves intent.
- Suspect score.

## 25. Brand direction

The brand is still being selected. Early blue and coral work was rejected because it looked too generic and corporate. Later references established a better target: minimal technology branding, one compact memorable mark, strong typography, disciplined spacing, and one signal color.

Current strong visual routes are:

1. Signal Editorial. Warm white, black, and signal vermilion. Bold uppercase NIVRA wordmark. The line is "See it sooner."
2. Civic Cobalt. Paper white, carbon navy, and cobalt. Clear civic-tech tone. The line is "A clearer moment to act."
3. Human Signal. Mineral white, black, and acid chartreuse. Lowercase wordmark with a more contemporary, fashion-aware tone. The line is "People make the call."
4. A previous violet direction is polished but less distinctive. It uses black, warm white, and electric violet with the line "Quiet until it matters."

No route is final yet. The logo should avoid shields, eyes, camera shutters, birds, crosshairs, police symbols, sharp origami forms, and copied cybersecurity marks.

The desired personality is:

- calm;
- alert;
- human;
- modern;
- semi-professional;
- understandable to adults;
- current enough for Gen Z;
- never childish or meme-like in the product itself.

## 26. Interface direction

The product should feel like quiet public infrastructure.

- The live camera remains the main visual.
- Secondary evidence sits in a narrow observation rail.
- Normal monitoring has minimal overlays.
- A review event quiets the rest of the screen and opens Focus mode.
- Focus shows the preceding sequence, the observed changes, camera quality, and a few clear human actions.
- Color is never the only status indicator.
- The interface should meet WCAG 2.2 AA contrast and keyboard requirements.
- Urgency animation must not loop continuously.
- Reduced-motion settings must be respected.

## 27. Measures that matter

Useful metrics include:

- time from candidate creation to human review;
- time from confirmation to responder acknowledgement;
- time from acknowledgement to on-scene status;
- candidate-to-confirmed ratio by detector and zone;
- dismissal reasons;
- camera uptime and degraded minutes;
- incidents resolved with no impact recorded;
- backup and outside-escalation rate;
- missed alerts caused by unavailable staff;
- detector performance by lighting, camera quality, and zone;
- unusual evidence access or export;
- completion of training and test alerts.

These metrics should improve operations, not become covert employee punishment scores.

## 28. Pilot concept

A credible first pilot would use:

- one controlled site;
- 4 to 12 approved cameras;
- one control-room workstation;
- 5 to 20 named responders;
- one or two detector modules;
- a documented escalation procedure;
- visible public or employee notice;
- a 30-day calibration and false-alert review;
- weekly camera-health reporting;
- a named human safety owner.

## 29. Open questions

These are not settled:

- whether NIVRA is available as a trademark and domain;
- the acceptable false-alert rate for confrontation signals;
- the lawful basis for video or audio processing in each deployment;
- exact retention and signage requirements;
- access to real CCTV and NVR systems;
- server capacity per camera;
- suitable on-site hardware;
- pricing and contracts;
- whether audio should be used in the first pilot;
- whether the first commercial focus should be campuses, events, private venues, or transport;
- which brand route should become the final identity.

## 30. Immediate next build priorities

1. Lock one brand route and create a usable SVG logo, app icon, color tokens, and type system.
2. Connect a real phone camera to Command.
3. Send frames at a controlled analysis rate of roughly 6 to 10 FPS.
4. Produce a transparent confrontation review score across several seconds.
5. Build Focus mode with an 8 to 10 second replay and plain-language observations.
6. Connect a second phone as NIVRA Respond.
7. Send a real alert and return acknowledgement to Command.
8. Record the full event timeline.
9. Run staged tests for normal play, greeting, camera shake, low light, and a real confrontation-forming sequence.
10. Prepare a short demonstration where the complete value is visible without narration.

## 31. One-paragraph project description

NIVRA is a human-supervised early-intervention platform for public spaces. It connects live cameras, control-room operators, and multiple responder phones in one system. NIVRA analyzes observable movement patterns such as rapidly closing distance, aggressive gestures, and crowd convergence, then asks a human operator to review the preceding footage. The operator can dismiss the event, keep watching, or dispatch the nearest suitable responder. NIVRA does not use facial recognition, identify individuals, infer guilt, or make automatic policing decisions.

## 32. Brief summary

NIVRA turns passive cameras into an early-response network. A phone can become a secure camera, a laptop can act as the command centre, and multiple responder phones can receive location-specific alerts. The goal is simple: help trained people notice developing situations and act before impact.
