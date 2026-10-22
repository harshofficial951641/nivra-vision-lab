# Online night evaluation acquisition and review — wave 1

2026-10-21. Model-blind CPU acquisition/review only. Read `TRAINING-AND-TESTING-PLAN.md`, `PROTOCOL.md` and `night-crowd-evidence.md` before acquisition. Only the assigned night cache, review bundle and this report were written.

## Outcome

**No eligible four-second evaluation window was acquired.** Six real low-light colour clips were fully inspected as chronological decoded-frame sequences, with **17,966.666666 ms of provisional ordinary-motion annotation**, but every acquired ARID file is shorter than four seconds. This annotation time must not enter an unchanged four-second classifier's evaluation denominator.

- 180 ARID individual-file attempts; **179 successful**, one HTTP 500 receipt preserved.
- **18,375,994 bytes of actual media downloaded**, zero archives. Cache including metadata/evidence was 35,554,939 bytes at validation, below the 500,000,000-byte cap.
- Six visually reviewed recordings; **545 distinct decoded frames** inspected through `view_image` in 19 gamma-lifted chronological sheets, plus six raw first-page sheets. Gamma pages include every frame, not just 16/32 samples.
- **One downloaded/reviewed source group**, all development; **zero eligible source groups** and zero reserved-audit reviewed groups. No source-group/role independence is inferred from filenames, action folders or actors.
- **Zero physical-contact-proxy events, verified near-IR videos, crowd/night capability claims or model runs.** Ordinary movement is not a fight-recall test.

## Artifacts

- `service/research/evaluation/wave1-night-review.json`: schemaVersion 1, **179 recording records** plus explicit unavailable/rejected-source receipts. Six have ordinary-motion events; the other 173 have no imagery review, no event labels and full-duration unknown intervals.
- `service/research/cache/eval-wave1/night/`: 179 preserved author-distributed AVIs, sequential decoder PTS, source/rights pages, folder listings, selection/role precommit receipts, contact sheets, small reviewed utilities, acquisition errors and `validation.json`.
- `acquisition.json` / `acquisition-extra.json` preserve all 180 file-attempt receipts, including `Drink_1_2.avi` HTTP 500. No failed receipt was replaced with a success claim.

## Source rights, attribution and acquisition

[ARID's official author page](https://xuyu0010.github.io/arid.html#papers-and-download) explicitly declares **dataset use CC BY 4.0** and points to its [pinned licence](https://github.com/xuyu0010/ARID_v1/blob/b03d0975f41547e8aa78929b8e26a62248f8e18f/LICENSE). Attribution: Yuecong Xu, Jianfei Yang, Haozhi Cao, Kezhi Mao, Jianxiong Yin and Simon See, *ARID: A New Dataset for Recognizing Action in the Dark*. The [author paper v4](https://arxiv.org/html/2006.03876v4) says capture was strictly during night hours with commercial cameras; these are real dark RGB recordings, not daylight made dark. Copyright permission is separate from independent participant/privacy clearance and from model/code/weight terms.

Saved pins:

| Evidence | Cache file | SHA-256 |
|---|---|---|
| Official dataset/rights page | `arid-source.html` | `b05b00b3d6da5f26b74fcfa61117c06a4d5c6b81afcfaa3b70df85e9f5760b2f` |
| Pinned CC BY 4.0 licence | `arid-LICENSE.txt` | `7e7170e3cebf88a9f60c7b8421418323c09304da1af4d5e90f4da1dc1c8a2661` |

The compact v1 archive's public Drive metadata reports **2,450,783,151 bytes**; v1.5 reports **7,913,857,849 bytes**. Both exceed the cap and were not downloaded. Instead, the author's linked [original v1 folder](https://drive.google.com/drive/folders/1SQuAYv_mLixDqjyUU_A304wkaYLWgztg) exposes individual AVI files. The exact Drive file IDs, human source URLs, direct `drive.usercontent.google.com/download` URLs, byte sizes and actual SHA-256 hashes are saved per recording. No unlicensed mirror was used.

The decoded files are **320×240 at 30 fps**, actual FourCC **FMP4**. This differs from assuming the paper's generic DivX description identifies every distributed file. These are author-published derivatives; camera-native dimensions/codec were not independently established. `nativeDimensions` is explicitly unknown, while `sourceDimensions` and `workingDimensions` are measured 320×240. Source and working video bytes are identical; no crop, gamma, resampling, concatenation, repetition, padding or stretching was applied to media. No new audio model or audio evidence was used.

## Selection and fixed roles

Before imagery or model scores, `role-precommit.json` fixed:

`sourceGroup = arid-v1-xu-et-al-unresolved-actor-session-cohort`

First byte SHA-256 of UTF-8 `nivra-online-wave1-v1:` plus that exact string is **87**, hence **development**. All 179 files remain together. Original training overlaps, actors and sessions remain unresolved.

Initial selection: six equally spaced entries from the first public page in each of six official AVI action folders, 36 files. Since none reached four seconds, a preselected 144-file extension from Drink/Stand/Sit first pages was checked, with a stop rule of six length-eligible files. No such file appeared, so the extension was exhausted. This bounds the result to **these 180 attempts**, not all ARID footage.

The six imagery-review candidates were then selected by **longest decoded duration within each initial publisher category**. Selection used duration only, never a classifier or inferred label. Folders and filenames remain provenance, not annotation. Every hard/too-short attempted item remains represented in receipts; no score-based filtering occurred.

## Actual temporal evidence inspected

Every decoded frame in the six clips below was inspected chronologically, in pages of up to 32 frames with decoder timestamps. Raw first pages establish original visibility. Additional display-only gamma 0.45 pages assist observation of dark details. They use `uint8((display/255)**0.45*255)` after a display resize to 224×157; this is an evidence transform, **not an evaluation-video transform**. No continuous-speed playback or human ground-truth claim is made. Contact-sheet review remains limited by source darkness, compression, display scaling and any motion lost in the source encoding.

| Clip | Frames | Duration ms | Ordinary-motion annotation ms | Visible observation |
|---|---:|---:|---:|---|
| `Wave_2_21.avi` | 89 | 2966.666667 | 0–2933.333333 | One standing person raises and lowers an arm before a ribbed wall |
| `Walk_1_1.avi` | 82 | 2733.333333 | 0–2700 | One person moves laterally past a wall with alternating leg positions |
| `Pour_1_9.avi` | 91 | 3033.333333 | 0–3000 | One seated person handles a container/cup at a table |
| `Drink_2_13.avi` | 119 | 3966.666667 | 0–3933.333333 | One seated person raises a small container to the mouth and lowers it |
| `Push_2_10.avi` | 73 | 2433.333333 | 0–2400 | One person bends and moves a chair/padded seat; no person-to-person push |
| `Jump_2_21.avi` | 91 | 3033.333333 | 0–3000 | One person bends/rises in jumping-like movement beside a railing |

Each final decoder PTS to duration margin remains **unknown**, not normal. No other person or interpersonal contact is visible in these reviewed encoded frames, but out-of-frame people are not ruled out. Person pixel height was not measured; the JSON records null rather than an invented value. Furniture/framing restricts body visibility in several clips. No 50–100-person scene is demonstrated.

For all 179 acquisitions, sequential `VideoCapture.read()` PTS were saved with `cv2.setNumThreads(1)` and one decoder. These are OpenCV `CAP_PROP_POS_MSEC` values after each read, not independently demuxed packet timestamps. Frame count/fps gives duration; timestamps are strictly increasing. No prediction, detector, CUDA, training or inference code was run.

## Longer low-light and near-IR gaps

A separate self-authored low-light colour lead was verified at [Quahadi's pinned Commons source revision](https://commons.wikimedia.org/w/index.php?title=File:Ban_Jela%C4%8Di%C4%87_square,_Zagreb_20240726_210003.webm&oldid=1076443621): **Own work, CC0 1.0**, 46.007-second published 3840×2160 upload, 24,031,191 bytes, declared SHA-1 `89b053886e9cdde56609bb98fe544ee4d547696a`. Source page and rights metadata were saved before attempting media. Page SHA-256: `30f77c4767d10b816ab8313ceebde88b234ab852ba3324d48e6c829666f0820d`.

Its conservative author group `commons-quahadi-unresolved-author-cohort` hashes to first byte **195**, reserved-audit, fixed before any media download. Six source-time four-second probe intervals were predeclared. The official original media URL returned **HTTP 429** on the first request and on one later retry. No rate-limit workaround or further retry occurred. **No media bytes, working video, imagery review or event annotation exists for this lead.** Published upload resolution would not by itself establish camera-native resolution.

Verified near-IR temporal people footage remains unavailable in this bounded task. [LLVIP](https://bupt-ai-cz.github.io/LLVIP/) was not substituted: its infrared partner is **8–14 µm thermal**, and its [dataset terms](https://github.com/bupt-ai-cz/LLVIP/blob/c1a655cce437ebfd990a97b04fc48fbb99f4c47b/Term%20of%20Use%20and%20License.md) are conditional/non-commercial. Saved fresh source/terms pins are in the cache. [TNO v2](https://api.figshare.com/v2/articles/1008029/versions/2) includes nighttime NIR imagery, but no verified temporal people-action sequence was established; no TNO stills were downloaded as a fight test. Arbitrary monochrome, thermal, astronomy, face/identity data and unrelated IR-proximity footage were not accepted as near-IR CCTV probes.

## Validation and limits

Local checks passed for all **179 media SHA-256 hashes/sizes**, unique hashes, role assignments, source-page hashes, strictly increasing sequential decoder PTS, event/review/unknown bounds, evidence-file existence, and no exact media SHA-256 overlap with `service/evaluation/corpus.json`. Only input-footage metadata was checked; no classifier results/predictions were opened. No VID data was acquired. Source-author/session and publisher-pretraining overlap remain unknown despite the exact-byte uniqueness.

The pinned FFmpeg binary's SHA-256 was checked and matched `2ce797a0f88d7f067180338fb227f7b1928ea727bd9a4d7a1d022f7c52af71a3`; **FFmpeg was not executed** because no downloaded media required transformation. Existing Python/OpenCV handled CPU work. No package installation, accounts, agreements/forms, external messages, commits, deployments or live-code/service changes occurred.

The goal of at least six eligible four-second probes was **not met**: **eligible annotated duration = 0 ms**, eligible source groups = 0, true near-IR videos = 0. Six short ordinary-motion annotations are retained for transparency and possible future short-clip methodological work, not silently promoted into the current evaluation. Genuine longer licensed low-light videos and sensor-verified near-IR CCTV remain acquisition blockers. This work supplies no accuracy, fight recall, crowd coverage or camera-hour false-alert estimate.
