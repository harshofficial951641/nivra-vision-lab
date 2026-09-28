# Nivra classroom pilot — implementation and remaining gates

Updated 28 September 2026. **Local experimental implementation; not a verified classroom safety system.**

## Confirmed scope

- 2–4 classrooms, one iPhone/Android/laptop camera each; approximately 30–50 people per classroom.
- Cameras may use different networks/mobile data. The central GTX 1660 Ti PC runs inference locally.
- Live video and persistent event records only. No clips, replay, microphone processing, face identification, automatic discipline, cloud deployment or external provisioning.
- Physical actions, including staged/sparring examples, may trigger human review. Arguments are outside scope.
- The newer approved black/white camera-wall contract from the design chat supersedes the earlier green option 3. Source: [selected reference](../../output/ui-ux-plan-2026-09-28/extended-screens/00-selected-reference.png). Canonical supplied Nivra mark retained; generated tower icon not adopted.

## Implemented core journey

1. Open the local dashboard and add a classroom/building/floor. Maximum four saved camera locations in this pilot; edit/reuse or pause them as needed.
2. Create a single-use QR pairing invitation. Scan it with the phone Camera app, open the link, grant video permission and press Start camera. The public Sites relay is described in `remote-camera-setup.md`.
3. Each device can publish only its assigned camera. It cannot inspect other rooms or the event desk. Re-pairing or pausing revokes its credential.
4. The stable camera grid shows classroom location, live/offline state, analysis readiness and limited coverage. Focus layout, floor filter, camera search and observed-track overlay are functional.
5. Candidate physical conflicts create persistent, idempotent event records with camera/location snapshots and source/evidence timestamps. Open candidates highlight their camera without reordering the grid.
6. The operator opens the live scene, acknowledges the record, and later resolves it. History is metadata only; no historical video can be inspected. Sound is opt-in, generated locally, and limited to one tone per ten seconds.
7. Analytics show actual event counts and current per-camera processing counters. Export contains the latest displayed metadata records, not media. These metrics do not measure detector recall or precision.
8. Source stop, reconnect, pause/revoke and service failure produce explicit unavailable states. The original browser/local-AI lab remains at `/lab` with its existing clip-review path.

## Detection and scheduling

Baseline local profile: YOLOX-S + ByteTrack + RTMPose-M + SlowFast-R50 AVA.
Experimental classroom profile: RTMO-M Body7 whole-frame pose/detection + ByteTrack + rotating SlowFast views + the pinned community X3D/RWF-2000 checkpoint. RTMO is a shared one-pass pose model; there is no per-person pose invocation for all 50 tracks. Missing joints do not suppress RGB action evaluation. Ambiguous overlaps suppress joint-motion evidence; predicted positions cannot count as observed impacts.

The whole-scene X3D score can flag a review but does not identify an actor or target. Its publisher score includes the publisher's second softmax and is not a calibrated fight probability. Grabbing alone does not qualify an AVA alert. Thresholds are engineering defaults, not held-out calibration.

One shared GPU model set serves independent per-camera trackers and incident state. The scheduler visits cameras fairly, holds one pending detection job per camera, and drops jobs older than 1.5 seconds. Separate bounded captured-frame histories retain temporal motion despite replacement of detection jobs. Source-time sampling avoids treating uneven GPU scheduling as even video time. Longer source gaps and image-size changes clear continuity; sparse observations reduce coverage explicitly.

The budget of 50 tracks is not proof that all 50 people are visible or reliably analyzed. Small back-row people, desks, occlusion and simultaneous incidents remain important failure modes. Completely hidden actions remain unobservable.

## Boundaries still open

- **Accuracy release gate failed:** the tiny diagnostic original-footage set improves from browser 0/3 events and earlier local 1/3 to 2/3, but the new candidate still has one unmatched alert versus browser zero. No representative 30–50-person classroom holdout exists.
- The natural-overlap grapple is detected, but at 4.24 seconds after a clip that starts mid-event. A synthetic crop is detected at 7.52 seconds. Neither establishes the requested live p95 delay or natural partial-body accuracy.
- The Sites relay passed an external protocol test including synthetic frame delivery to the GPU and preview return. Physical iPhone/Android foreground/interruption/mobile-data tests remain unverified.
- One-minute cloned two-person stream tests establish scheduler behavior only. They do not establish four crowded-classroom capacity. See `service/evaluation/RESULTS.md` for measured rates.
- No responder assignment app, team accounts, push delivery, real floor-plan geometry, outcome labelling workflow, operating schedules, zones or trained threshold presets are implemented. These were later product concepts, not demonstrated runtime capabilities. No fabricated map or generic accuracy KPI is shown.
- Training/fine-tuning requires independent labelled training/calibration data and a new untouched evaluation split. Every transform of an original must stay in the original's split. The already inspected holdout is diagnostic only.

## Acceptance gates

Before promoting the model: at least 20% fewer missed events with no higher false alerts/minute, improvement on natural overlap and partial-body subsets, and p95 live source-to-alert delay within three seconds. Report counts, sustained per-camera processing, complete GPU memory measurements, lost tracks and identity switches with matching ground truth. Evaluate unseen recordings only after calibration is frozen.

Before a real classroom pilot: verify lens placement and back-row coverage, real phones on the chosen networks, network loss, device interruption, camera revoke, overload and simultaneous events. Retain explicit degraded states. Passing application tests does not satisfy the accuracy or deployment gates.

## Reference material

- [PyTorchVideo action detection](https://pytorchvideo.org/docs/tutorial_torchhub_detection_inference)
- [OpenMMLab RTMO](https://github.com/open-mmlab/mmpose/tree/main/projects/rtmo)
- [Pinned X3D publisher](https://huggingface.co/visionlab-ai/school-violence-detection-models/tree/a744b6af7496f0cbfa4f0ba32acd46b65e52d4e1)
- [Browser secure-context camera requirement](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)

