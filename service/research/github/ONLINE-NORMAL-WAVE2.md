# Model-blind normal evaluation wave2

21 October2026. Bounded acquisition is complete with an explicit development gap: **0 eligible development windows;1 reserved four-second window**. The requested6-8 acquired recordings and>=3 development groups were not achieved. No old unknown label was changed.

Eight author groups were frozen before downloads/imagery review:5 development,3 reserved. Freeze SHA256: `01cd72f71c2b33ab44b781dded6140375714a06bbd51a1c1201092f0199160be`. Canonical credited-author groups and the required SHA256 role rule are preserved, including failures.

| ID | Author | Role | Result |
|---|---|---|---|
|wave2-normal-01|[Kerry Raymond](https://commons.wikimedia.org/wiki/File:Drum_dancing,_Gjoa_Haven,_2019_-_02.webm?oldid=1213637488)|reserved-audit|retain-normal; 1 windows|
|wave2-normal-02|[Rmall253](https://commons.wikimedia.org/wiki/File:The_dancing_men_of_Liberia_3.webm?oldid=1204569120)|development|unknown; 0 windows|
|wave2-normal-03|[Sdkb](https://commons.wikimedia.org/wiki/File:Contra_dancers_at_the_2019_Flurry_Festival.webm?oldid=867859214)|reserved-audit|unavailable; 0 windows|
|wave2-normal-04|[Vicente Quintero](https://commons.wikimedia.org/wiki/File:Sabana_Grande_Caracas._People_walking_on_the_Boulevard_of_Sabana_Grande,_famous_in_Caracas,_Venezuela.webm?oldid=1199293943)|development|unavailable; 0 windows|
|wave2-normal-05|[ProtoplasmaKid](https://commons.wikimedia.org/wiki/File:Cruce_peatonal_de_Eje_Central_L%C3%A1zaro_C%C3%A1rdenas_y_Avenida_Madero,_Ciudad_de_M%C3%A9xico.webm?oldid=1090402649)|development|unavailable; 0 windows|
|wave2-normal-06|[Basile Morin](https://commons.wikimedia.org/wiki/File:Shibuya_Crossing,_Tokyo,_Japan_(video).webm?oldid=1154429684)|development|unavailable; 0 windows|
|wave2-normal-07|[Amada44](https://commons.wikimedia.org/wiki/File:Venice_at_night.webm?oldid=515902327)|development|unavailable; 0 windows|
|wave2-normal-08|[Harriwillz](https://commons.wikimedia.org/wiki/File:Cultural_dancers.webm?oldid=1206462955)|reserved-audit|unavailable; 0 windows|

## Acquisition and rights

Downloaded **4,305,132bytes** across2 official published480p VP9 transcodes;100,000,000byte cap. Third media request (Sdkb) returnedHTTP429. Stopped all further upload.wikimedia.org requests; no retry, mirror, alternate endpoint or role substitution. Five candidates were not attempted after backoff; one failed. All8 official file-page snapshots, revision pins, byte hashes, exact direct/original URLs, file-level own-work claims, licence versions and attribution are in the review and cache metadata.

Kerry Raymond:CC BY4.0. Rmall253(IFES):CC BY-SA4.0. Remaining pinned file licences are in the review. File-level licences cover copying/adaptation subject to attribution/share-alike; no separate model-weight, consent, actor-release or commercial-clearance claim. Initial metadata parser wrongly picked the genericCC0 structured-data footer; that rejected output is preserved separately and was corrected before media acquisition. Final records use actual Summary/Licensing sections.

## Evidence and labels

Sequential single OpenCV decoder with `cv2.setNumThreads(1)` read each acquired file to EOF to record its actual CAP_PROP_POS_MSEC clock. Every decoded frame0-100 (PTS0-4000ms inclusive) for each acquired recording was rendered in chronological16-frame sheets and inspected via `view_image`: **202frames,14sheets**. Aspect-preserving tiles and per-frame timestamps include both boundaries. No FPS-derived timestamps or numerical-only approval. Decoded tails were not visually reviewed.

**Reserved Kerry Raymond:**0-4000ms ordinary rhythmic stepping and instrument movement; isolated full-body performer with seated spectators. Easier normal control, with a drum explicitly recorded as a prop. No person-to-person physical contact observed. One4s window; not an unarmed interaction stress test.

**Development Rmall253:**opening black-block transition obscures people through approximately880ms. Remaining inspected imagery shows energetic bending/acrobatic balancing with other people nearby. Frozen0-4000ms interval is unknown, not normal. Did not move to an easier interval or silently drop the example. No eligible4s development negative.

All uninspected tails remain unknown. `durationMs` is conservative observed clock extent to final decoded PTS, excluding its unverified final presentation duration. Published source dimensions are identified separately from camera-native dimensions (unknown). Downloaded transcode PTS is the annotation source clock; decoder-to-that-clock offset0ms, original-upload/camera offset unverified. No local working-media transcode; evidence sheets alone are resized derivatives. Person pixel height/crowd counts are unmeasured.

## Validation and handoff

Custom validation passed: frozen role recomputation; source-page/media hashes; existing corpus and all wave1 review metadata author/group/URL/hash exclusions; evidence paths; increasing actual PTS and boundary coverage; event bounds; cap accounting. Receipt: `../cache/eval-wave2/normals/validation.json`. No repository test suite was needed for data-only additions; no model runs or scores were used.

Review: `../evaluation/wave2-normal-review.json` SHA256 `f92be4c8cd5e4d623b701c8349ca4c7751c0e57994d4ac21cd5a155d165f9330`. Evidence, scripts, immutable candidate freeze, decoder clock crosswalk and acquisition receipts: `../cache/eval-wave2/normals/`.

Labels are provisional assistant static-frame interpretations, not human truth. Actor/session independence, source-model pretrain overlap, true CCTV/50-100person crowd/night representativeness remain unknown. **This bundle does not close the development-negative gap; candidate selection still lacks the requested fresh development evidence.**
