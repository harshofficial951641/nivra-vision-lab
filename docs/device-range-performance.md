# Camera-device range and laptop workload — 28 September 2026

## Changes

- Pose Lite requests at most ten poses instead of four. The server validates the same ten-person bound. This is capacity configuration, not verified ten-person detection accuracy.
- Camera-device body admission accepts torso scales down to 0.035 of image height instead of 0.07; inferred upper-body shoulder admission is 0.0275 instead of 0.055. Reliable-joint confidence and impact thresholds are unchanged. The original lab retains its former size defaults.
- Duplicate removal requires agreement across at least four reliable joints, including available limbs. Similar shoulders alone no longer merge two observations. If Pose Lite returns one skeleton for two people, these rules cannot recover the missing skeleton.
- Whole-frame analysis remains default. Left, center and right focus choices crop half of the source before model resizing. Returned boxes map back to full-frame coordinates. Areas outside the focus are not analyzed. The overlay follows the actual camera aspect ratio.
- Balanced uses a 640-pixel maximum input side; optional detail uses 960. Larger input is not an optical zoom or a guarantee of better pose detection. Pose Lite still preprocesses inputs internally.
- One worker, one outstanding frame, no inference queue. Smoothed inference time paces analysis between 100 and 500 ms. Slow analysis lowers preview size from 960 to 640 and preview target from about 12 to 8 FPS. A visible warning appears above 400 ms per result.
- Frame counters render twice per second. Dashboard previews coalesce into one update per 80 ms with at most one pending frame per camera; obsolete frames never enter image decoding. Routine metadata broadcasts share one 200 ms task across cameras. New review events bypass this delay.

## Verification and limits

Synthetic observation regressions cover ten small visible bodies, stable IDs, exact-duplicate removal, distinct overlapping limbs, focus-coordinate mapping, crop-before-resize, adaptive pacing, stale frames and worker lifecycle. They do not measure model accuracy on real crowded footage.

Existing single-hit and negative-motion checks remain required. Public verification uses a temporary synthetic camera only, never the user's existing camera pairings or footage. Browser checks include keyboard activation, mobile layout, focus selection, disabled controls while running, stop/restart and explicit connection failures.

No physical iPhone, Android, low-end laptop or measured distance benchmark is available for this change. Optical detail, occlusion, camera placement, heat and GPU support still constrain detection. No reliable metre range or ten-person accuracy claim is made.

The request for a review image is pending the owner's choice between a temporary still and a saved event still. Current retention remains event records only; no still-image persistence has been added. Any later image must represent the exact analyzed source frame and be labelled as an alert frame, not proof of contact.
