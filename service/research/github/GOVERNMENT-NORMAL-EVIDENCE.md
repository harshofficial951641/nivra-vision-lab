# Government exercise normal evidence — wave3

21 October2026. **Retained2 four-second ordinary-motion controls:1 development group,1 reserved group (8 annotated seconds). The target of3 eligible development groups is not met.** All8 frozen author groups and their roles are preserved. Six recordings remain unknown. No prior unknown labels changed, model scores inspected, training run, GPU job or live service change.

## Sources and frozen roles

Eight official DVIDS exercise B-roll sources were selected by metadata before role computation and frozen before media downloads/labels. `candidate-freeze.json` SHA256: `d8f11e2452599db568285fccac65bd6d77ad472c6096e1107317283ef5c26b16`. Group prefix `dvids-author:` plus lowercase full credited name; Mariah K. Duncan uses the fuller name in the official caption. Same-author/session derivatives remain together. Roles use first byte SHA256 UTF8(`nivra-online-wave1-v1:`+sourceGroup), below128 development; no renamed or discarded reserved roles.

| DVIDS source / credited author | Role | Result |
|---|---|---|
|[125927: Mariah K. Duncan](https://www.dvidshub.net/video/125927/physical-training)|reserved-audit|retain-normal; 1 four-second windows|
|[924587: Shaina Jupiter](https://www.dvidshub.net/video/924587/acdc-us-and-philippine-marines-conduct-physical-training-b-roll)|reserved-audit|unknown; 0 four-second windows|
|[1021147: Nan Yang](https://www.dvidshub.net/video/1021147/b-roll-delayen-26-mrf-d-marines-participate-physical-training-event)|reserved-audit|unknown; 0 four-second windows|
|[957953: Anita Ramos](https://www.dvidshub.net/video/957953/b-roll-us-marines-and-adf-participate-in-physical-training)|development|unknown; 0 four-second windows|
|[994732: Tamia Lee](https://www.dvidshub.net/video/994732/b-roll-setaf-af-leads-physical-training-during-sergeants-time)|development|unknown; 0 four-second windows|
|[831170: Traquez Coe](https://www.dvidshub.net/video/831170/4th-infantry-division-newcomers-physical-training-b-roll-package)|development|retain-normal; 1 four-second windows|
|[1002193: Tanner Orth](https://www.dvidshub.net/video/1002193/nimitz-conducts-flight-deck-physical-training)|reserved-audit|unknown; 0 four-second windows|
|[847160: Christopher Sanchez](https://www.dvidshub.net/video/847160/fuerzas-comando-2022-physical-conditioning-test-b-roll)|reserved-audit|unknown; 0 four-second windows|

The other suggested sources Holiday PT776125, A new fitness155251 and Army Physical Fitness995243 are classified Series, Package and Video Productions on their official pages. They were not downloaded into this B-roll-only cohort.

## Rights and acquisition

Each saved file page explicitly marks PUBLIC DOMAIN and credits U.S. military motion imagery. [DVIDS copyright/reuse policy](https://www.dvidshub.net/about/copyright) is saved with URL, UTC retrieval time, bytes and SHA256 alongside all eight source pages. This is a U.S. official-government-work claim, not CC0 or a worldwide clearance finding. DVIDS warns of third-party IP, preserves privacy/publicity rights and restricts implied endorsement and military marks. No separate model-weight or machine-learning training grant is inferred; acquisition and annotations here are for the authorized offline visual evaluation.

The appearance of U.S. Department of War (DoW) visual information does not imply or constitute DoW endorsement.

All8 sources acquired within **15,949,582 downloaded media bytes /100,000,000 cap**: one complete published embedded MP4 (125927) and seven opening10s HLS segments from public player playlists. Embedded full MP4s over the25MB per-file allocation were skipped before reading their bodies; their receipts remain. These are published web renditions, not camera originals. HLS master, rendition playlist, exact segment URLs, duration/offset, HTTP receipts, original byte counts and hashes are preserved. No accounts, agreements, forms, mirrors or Wikimedia retry. Requests were sequential with host backoff on429; DVIDS acquisition encountered no429.

Original acquired bytes (including any audio) are preserved only as source evidence. Working files were video-only FFmpeg7.1 stream-copy remuxes with `-map0:v:0 -an -c:v copy`; audio was not auditioned, modelled or cleared. No claim about copyright music is made. Executable SHA256 was checked against `2ce797a0f88d7f067180338fb227f7b1928ea727bd9a4d7a1d022f7c52af71a3`. CPU2threads; no video re-encode, resize, crop or fps conversion in working media. Attribution and policy restrictions accompany each recording.

## Visual evidence and annotations

**973 unique decoded frames inspected through65 view_image contact sheets**, including prefixes and rejected imagery. Sheets are chronological16-frame1600x1040 composites with readable actual sequential decoder PTS, preserving aspect ratio. One CPU decoder at a time, `cv2.setNumThreads(1)`. `visual-inspection-register.json` distinguishes actually inspected sheets/frame indices from additional generated sheets that were not opened. A17-frame sparse full-file overview of125927 located a later scene; those samples do not establish temporal normal coverage.

Retained development831170: **0–4000ms**, runners approaching camera and a foreground bend/turn; visible activity stays ordinary and other full-body runners remain visible. Easier running/bending control; transient lower-frame clipping is disclosed.

Retained reserved125927: **20020.020020–24020.020020ms**, five separated full-body people standing/gesturing and moving arms into stretches on grass. Easier arm-motion control. Every covering frame600–720 inclusive and the end boundary frame were inspected; selected sheet range extends through24124.124ms.

957953 remains unknown: dark, distant field formation; foreground walking is visible but background interactions are unresolved. 994732 remains unknown after dense0–8008ms review: equipment opening, underexposed/occluded carrying group and cuts. 924587 remains unknown after dense0–5005ms review: black prefix, progressively clipped bodies and defocus. 1002193 remains unknown: hard cut near3.25s leaves inspected uninterrupted shots under4s. 1021147 and847160 each have only the opening16frames visually inspected (distant field / cropped backs); all remaining frames unknown. No author label or exercise filename supplied negative approval.

All unannotated time, including sparse-only observations, remains unknown. Provisional assistant static-frame labels are not human ground truth or proof of continuous motion.

## Clock and lineage

Events use the acquired asset clock normalized to its first decoded video frame. Sequential OpenCV POS_MSEC values are recorded for every acquired working frame; no FPS-generated timestamps. Independent FFmpeg `-copyts` showinfo logs pin raw source and working first PTS. The crosswalk supplies decoder-to-raw-input and decoder-to-raw-working offsets, with1ms remux timestamp quantization allowance. For HLS, normalized asset0 denotes the first video frame in the first segment; exact mapping to the separate full embedded MP4/player clock is **unverified**. Original camera-clock offsets and native camera dimensions are unknown. Source raw-PTS event bounds are additionally saved, so these are not silently presented as camera timestamps.

Working published dimensions range480x270 to768x432 (125927:720x406); they are not native1080p/720p evidence. Person pixel heights and crowd counts unmeasured. Some images have visibly low-light colour appearance, but no verified time-of-day/NIR sensor provenance, temporal fight labels or representative CCTV/crowd operating-condition claim. These are exercise domain-shift controls.

## Validation and handoff

Review: `../evaluation/wave3-government-normal-review.json` SHA256 **`443554d53641562064603622c2ed125ee228f1199ed1180e683836dcccf2d7a8`**. Cache: `../cache/eval-wave3/government-normals/`. Custom check receipt: `validation.json` in that cache. Checks recompute frozen roles, source/media hashes, prior corpus/wave1/wave2 author/group/URL/hash exclusions, bounds/nonoverlap, evidence existence, event covering-frame inspection and downloaded-byte accounting. Sequential source versus silent working decoding compares all frame hashes/order and normalized PTS to verify the remux lineage. No application code changed; no application/GPU/model tests were run.

Actor/session independence and publisher-pretrain overlap remain unknown. **Only1 eligible fresh development group is supplied;2 more are still needed to meet the requested development-group target.** Reserved footage retains its reserved role.
