# Online hard-normal evaluation evidence — wave 1

## Delivered evidence

13 recordings from 13 conservatively grouped source authors were acquired independently of classifier outputs. Ten retain provisional ordinary-motion intervals; three remain entirely unknown. The bundle contains 340.802 seconds of acquired media and 227.959 seconds of proposed normal intervals: 62.983 development and 164.976 reserved-audit. The 13 author groups split into 4 development and 9 reserved-audit; the 10 groups with retained intervals split into 3 and 7 respectively.

These are **provisional assistant annotations from sampled still images**, not human ground truth or continuous visual observation. Unknown includes ambiguous interaction, occlusion, and uninspected opening/tail margins. It is never a negative label. No model outputs were read, and no inference, training, CUDA, environment installation or service change was performed.

Machine-readable deliverable: `service/research/evaluation/wave1-negative-review.json`. Evidence and acquisition receipts: `service/research/cache/eval-wave1/negatives/`. Paths in the bundle are relative to the repository root.

## Source and interval register

Every source below links to its saved primary Commons page revision. The bundle contains the original/direct URL, acquired-file SHA-256 and size, author attribution, licence URL, rights metadata hashes, source revision, dimensions, PTS lineage, events and unknown intervals. Distinct authors do not establish actor/session independence or absence from pretraining.

| ID | Primary source revision / author | Licence | Frozen role | Normal seconds | Review result |
|---|---|---|---|---:|---|
| online-normal-01 | [Diti hugs Natalie.ogv](https://commons.wikimedia.org/w/index.php?oldid=1206753875) — Dimitri “Diti” Torterat | [CC BY 2.0 fr](https://creativecommons.org/licenses/by/2.0/fr/deed.en) | reserved-audit | 10.480 | Provisional subsets |
| online-normal-02 | [Helping Needy People - Makar Sankranti Observance - Ramkrishnapur Ghat Area - Howrah 2018-01-14 6977.webm](https://commons.wikimedia.org/w/index.php?oldid=1159285115) — Biswarup Ganguly | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0) | development | 0.000 | Entirely unknown |
| online-normal-03 | [Chinese man dancing.webm](https://commons.wikimedia.org/w/index.php?oldid=856725232) — Nicholas Gemini | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) | reserved-audit | 24.502 | Provisional subsets |
| online-normal-04 | [Baganda traditional dance 01.webm](https://commons.wikimedia.org/w/index.php?oldid=1028459281) — Kateregga1 | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) | reserved-audit | 58.486 | Provisional subsets |
| online-normal-05 | [Oroko Traditional Dancer.webm](https://commons.wikimedia.org/w/index.php?oldid=1129511112) — Adesolive | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) | reserved-audit | 40.516 | Provisional subsets |
| online-normal-06 | [Tajcsi Magfalv%C3%A1n.ogv](https://commons.wikimedia.org/w/index.php?oldid=898244144) — Elekes Andor | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) | development | 30.962 | Provisional subsets |
| online-normal-07 | [Dog walking in the Mission in San Francisco.ogv](https://commons.wikimedia.org/w/index.php?oldid=1207923663) — Sage Ross | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0) | reserved-audit | 16.500 | Provisional subsets |
| online-normal-08 | [Queue 2 - Belarus, Minsk, Presidential Voting 2020.webm](https://commons.wikimedia.org/w/index.php?oldid=862192089) — Melirius | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) | reserved-audit | 0.000 | Entirely unknown |
| online-normal-09 | [Queue for gas cylinders in Gangtok (Sikkim) during the 2026 West Asia conflict.webm](https://commons.wikimedia.org/w/index.php?oldid=1255446829) — Rajani Gairshail | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) | reserved-audit | 4.012 | Provisional subsets |
| online-normal-10 | [Shadow dance, NIT Hamirpur.webm](https://commons.wikimedia.org/w/index.php?oldid=1090196342) — Meerah Dhiman | [CC0](http://creativecommons.org/publicdomain/zero/1.0/deed.en) | reserved-audit | 0.000 | Entirely unknown |
| online-normal-11 | [The Iyase of Issele Uku arriving to receive a royal handshake.webm](https://commons.wikimedia.org/w/index.php?oldid=1282473618) — King Waltz | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) | development | 12.516 | Provisional subsets |
| online-normal-12 | [%22Nem Hagyjuk Abba!%22 - t%C3%BCntet%C5%91k a D%C3%ADsz t%C3%A9ren.webm](https://commons.wikimedia.org/w/index.php?oldid=1221882534) — Envagyokabela | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) | reserved-audit | 10.480 | Provisional subsets |
| online-normal-13 | [Example of team work.webm](https://commons.wikimedia.org/w/index.php?oldid=1236897377) — Hridoy Kundu | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) | development | 19.505 | Provisional subsets |

Visual findings by source (approximate seconds in these descriptive notes follow the contact-sheet caption clock; final event/unknown interval fields in the JSON are authoritative acquired-container PTS):

- **online-normal-01**: Observed approach, arm opening and sustained two-person embrace involving a costumed figure; bilateral upper-body contact is ordinary greeting-like interaction in sampled frames, with stationary bystanders. No directed strikes or rough play apparent. No identity or intent inferred.
- **online-normal-02**: Close crowd extends bowls/arms toward a central area. From roughly 3.76s a foreground arm crosses an upper body and some shoulder/arm contact is obscured. Serving context is suggested by visible bowls, but it does not resolve the physical interaction. Retain entire clip as unknown for normal scoring rather than infer nonfight from the source title.
- **online-normal-03**: One foreground person repeatedly lifts and sweeps arms while holding a small device; no other-person contact is apparent in retained intervals. A passer crosses the camera around 14.77-16.28s, so that intervening portion is unknown. Camera rolls during the first part; preserve the acquired orientation. Later device handling and stationary movement are ordinary non-contact motion.
- **online-normal-04**: Foreground performers remain spatially separated while stepping, bending, rotating and lifting arms beside drums. Background group stands/steps in rows. All four timestamped sheets inspected through 58.754s; no directed person-to-person contact or rough play apparent. Background occlusion and small figures limit certainty, so this is an ordinary-visible-motion proxy, not proof about hidden interactions. Unseen opening/tail remain unknown.
- **online-normal-05**: Solo foreground dancer steps, bends and swings arms/legs in an open area before seated spectators. Leave 14.258-24.258s unknown as another person approaches and moves close, and 41.258-50.258s unknown during a foreground crossing and overlapping dancers. Retain only clearer solo-motion subsets. All four sampled sheets inspected; no uninspected tail is normal.
- **online-normal-06**: A dispersed outdoor group performs coordinated arm raises, bends and weight shifts, with some seated bystanders. No directed contact apparent in retained samples. Leave 16.25-22.771s unknown around children/people crossing and crouching in the foreground. Figures in background are small and overlapping. This is ordinary visible group motion, not a verified 50-100-person coverage test.
- **online-normal-07**: A person walks a dog on a leash along a pavement; camera follows the dog and later returns to the person. Cars and a distant cyclist pass. No person-to-person interaction is apparent in the sampled interval. Contains a substantial animal-only camera segment, so it is a lower-difficulty ordinary-motion control rather than a pure hard human-interaction negative.
- **online-normal-08**: A distant line/group stands and walks behind repeated passing cars, trees and a large truck. Upper bodies intermittently visible but body/contact coverage is inadequate to approve a full normal interval. All acquired samples inspected; retain unknown rather than infer a clean negative from queue context.
- **online-normal-09**: People stand/walk with space between them along a line of cylinders during the initial camera pan. No directed physical interaction apparent in retained initial samples. Later rotation and passing vehicles make distant groups too unclear, so all later footage is unknown. Only a narrow four-second ordinary-visible-motion subset is retained.
- **online-normal-10**: Despite dance filename, actual samples show silhouettes carrying curved/trident-like props, staged directed swings, close upper-body contact and a drop to the stage. These cannot be used as a hard-normal unarmed/non-contact example. Entire recording retained unknown/excluded from normal scoring, including later silhouettes and darkness; no positive fight label is inferred from theatre.
- **online-normal-11**: Foreground figure walks/stands in an open ceremonial space carrying a long staff/sword-like object while others stand at the edge. No directed person-to-person interaction apparent in retained intervals. Leave 6.258-9.258s unknown during a close foreground crossing. The advertised handshake is not actually observed; do not annotate one from the title. Object presence is recorded and this remains ordinary standing/walking only, not a prop-action positive.
- **online-normal-12**: People walk past the camera in a group, with clapping, raised arms, placards and a wheeled mobility aid visible. No directed physical contact or rough play apparent across the sampled span. No identity or political/intent label is assigned; the retained target is ordinary visible walking/gesturing.
- **online-normal-13**: An elevated camera shows several people at staggered positions passing/handling brick-sized objects, reaching to a stack and repeatedly bending/crouching. Enlarged source frames at 1.251, 6.761, 12.777 and 16.766s support object handling rather than directed person-to-person contact. No rough play apparent in retained samples. Bodies near the doorway and under the foreground edge are partly occluded; no hidden-action guarantee is made.

## Acquisition, rights and lineage

Total acquired media: **49,832,758 bytes** against the 300,000,000-byte cap. One author-uploaded original (Diti) and twelve publisher-generated Commons transcodes were preserved. No local media trim, crop, reencoding, time stretch or synthetic degradation was applied. The 12 unavailable original files have no claimed SHA-256; their publisher metadata and original URLs are recorded separately from the actual acquired derivative hashes. Working files are at most 854×480 landscape, 720×576 for the original, 638×360 for the stage clip, or 270/272×480 portrait. Published original dimensions are not verified native camera dimensions; `nativeDimensions` is null.

Own-work source declarations and licence metadata were saved before media acquisition. Sources use CC BY, CC BY-SA or CC0 as listed above. Diti uses the author’s Commons information template, with expanded CC BY 2.0 France metadata; the author page mentions another YouTube version, but the acquired file is the directly licensed Commons original, not a YouTube compilation. Copyright licences do not prove participant/model releases or remove privacy/personality rights. Such releases were not independently inspected. Source attribution and derivative-evidence licence obligations remain attached in each record.

Initial original requests encountered HTTP 429. Failed receipts were preserved, including the first batch that continued after rate limiting. Subsequent acquisition stopped on rate-limit errors and used bounded publisher derivative metadata, backoff and 20-second pacing. All successful and failed media requests are in `download-receipt.json`; original metadata and frozen selection/role plans are retained. No access-control bypass, login or external contact was used.

Pexels was screened and rejected without acquiring footage: its [current terms](https://www.pexels.com/terms-of-service/) restrict automated collection, including machine learning use. The screening receipt is retained. Public accessibility was not treated as a licence.

## Evidence actually inspected

All **26 primary timestamped contact sheets containing 680 retained frames**, plus **five enlarged uncertainty sheets containing 20 additional frame observations**, were inspected with `view_image`. Sampling retained the first decoded frame at or after 0.25 decoder-relative seconds and then approximately every 0.5 seconds. Additional enlargements cover sources 02, 05, 08, 10 and 13. Some enlarged observations overlap the primary samples; 700 observations does not mean 700 unique frames or continuous playback.

OpenCV used `cv2.setNumThreads(1)`, sequential single-file decoding and bounded contact sheets. Sequential FFmpeg showinfo decoding used CPU threads=2 and filter_threads=1. The pinned FFmpeg executable SHA-256 was verified as `2ce797a0f88d7f067180338fb227f7b1928ea727bd9a4d7a1d022f7c52af71a3`. OpenCV and FFmpeg frame counts agree for all 13 files; PTS are monotonic and maximum adjacent gaps are at most 100 ms. These numerical checks do not substitute for continuous visual inspection.

Contact-sheet captions use decoder-relative time. Per-frame `pts-crosswalk.json` files map these samples to actual acquired-container PTS; first-frame offsets are 0–14 ms. Final annotations use acquired-container source milliseconds, with these offsets applied. This clock is not camera wall time, and for transcodes it is not independently verified original-file time. Historical `original-sequential-pts.*` utility filenames describe the acquired file; for 12 records this is explicitly the publisher transcode.

## Bundle contract and validation

Roles were computed before review using the first byte of SHA256 UTF-8(`nivra-online-wave1-v1:` + sourceGroup): below 128 means development; otherwise reserved-audit. Source groups are fixed author identifiers, not names chosen to obtain a desired role. The frozen plans preserve this decision. No scores influenced selection, roles or annotation.

`events` contain only `label: ordinary-motion`, `targetLabel: 0`, and `physicalFightGroundTruth: false`, with explicit source-time start/end milliseconds. Ordinary embrace contact is distinct from physical-fight contact. `reviewedIntervals` explicitly describe sampled-image coverage. `unknownIntervals` partition every other source-time interval, including tails. No positive event or physical-contact proxy is approved here.

Run from repository root:

```powershell
service/.venv/Scripts/python.exe service/research/cache/eval-wave1/negatives/validate.py
```

Result: **PASS**. Checks cover required fields; unique IDs/groups/content hashes; exact acquired bytes/SHA-256; predeclared role hashes; exclusion against existing corpus source URLs and hashes; rights metadata hashes; all 127 referenced evidence paths; bounded working dimensions; sequential PTS and frame crosswalks; annotation bounds within sampled spans; nonoverlapping normal/unknown partition; and the download cap. `validation.json` preserves the receipt. Bundle SHA-256: `e90d7bf4867fc0f989a95df4ce234e4b431d66c0bdaf16b3d4ce1d4512e4c9b4`.

A separate eligibility receipt tiles complete nonoverlapping four-second windows from each retained interval’s beginning: **49 windows / 196 seconds**, 12 development and 37 reserved-audit. This is deterministic annotation eligibility only, not the parent runner’s final sampling policy, independent observations, classifier performance or label verification. No model was executed for validation.

## Limits and handoff

The 59-second group dance and 60-second solo dance provide longer curated negative-time evidence, with uncertain portions excluded. This pool does not establish operational camera-hour false-alert rates. Source 07 is an easier dog-walking control. Source 09 contributes only a narrow 4.012-second interval. Source 11 contains ordinary walking with a carried ceremonial object; its title did not establish a handshake. Source 10 includes props, close interaction and staged drops and is entirely unknown, not an approved negative or positive.

No visually verified shadowboxing or actual handshake example was secured. Helping/serving source 02 and occluded queue source 08 remain entirely unknown. This pool supplies no verified native 1080p/720p working sample, genuine near-IR/black-white CCTV, thermal IR, or low-light-colour CCTV. Backlit stage silhouettes are not night/IR evidence. Crowd counts are approximate, person pixel heights were not measured, and 50–100-person fight-detection capability remains untested. Compression and low working resolution alone do not establish CCTV domain transfer.

All accuracy, false-alert, latency, crowd, night and model-transfer claims remain unverified. Parent alone schedules model/GPU runs and controls reserved-audit use. Before treating these intervals as a strict continuously observed negative holdout, obtain continuous human review or use them with the explicit sampled-evidence limitation.
