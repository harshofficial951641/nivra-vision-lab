# Original browser skeleton detector

The default web camera now uses the browser skeleton mode from the published 3.0 checkout, commit `a99f3e8` (21 September 2026). The later uncommitted trained-video additions in that folder are a different pipeline and were not copied.

## What runs

- MediaPipe Pose Landmarker Full, VIDEO mode, up to four poses, detection/presence/tracking confidence 0.5. GPU when supported, with CPU fallback.
- One pose worker on each camera phone. The newer person detector and per-person crop workers do not run in the default web camera profile.
- The original directed arm-motion rules: three complete episodes in standard mode, two in early clip review, four for wrist-only evidence. Original warmup, visibility, continuity and cooldown rules are retained.
- The camera preview and network sends run separately from inference. Busy inference skips frames; repeated video frames are not counted as fresh motion.
- Observed 33-joint skeletons and anonymous boxes still reach the camera wall. QR pairing, guard response, GPS and incident review retain their existing contracts.

`src/lib/originalConflictEngine.ts` contains the historical source plus a read-only `observedTracks()` adapter for the current camera overlay. Removing that adapter and its provenance comment yields the historical source byte for byte. Its source SHA-256 is `0e04628b0fd3902c65466b29e2c33c3f0e5cbb8a0a1018efdeba7f75142c2c90`.

Both `/camera` and the existing `/lab` local video-review workspace use these original rules. The installed native iPhone camera has its separate native detector; this change verifies the browser path.

## Model provenance

The files already present here match the 3.0 model files byte for byte. No model download or threshold tuning was needed.

| Asset | SHA-256 |
|---|---|
| Full | `5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1` |
| Lite, available in the lab | `59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a` |
| EfficientDet, optional lab object checks | `4b59100025bea1235a84c1038879a6cccc9f6c49f5e41144e91e74d99e780993` |

## Verification and limits

The historical rule tests are retained in `originalConflictEngine.test.ts`. Device tests verify one worker, fresh video frames, skeleton reports and CPU fallback. These tests verify software behavior, not deployment accuracy.

This exact restoration retains the original four-pose capacity and global eight-second event cooldown. It does not establish coverage for twenty students or multiple simultaneous fights. A pose detector supplies joint observations; the motion rules flag interactions for human review and are not a trained fight classifier. See the fresh replay results in the two-video evaluation folder before making accuracy claims.
