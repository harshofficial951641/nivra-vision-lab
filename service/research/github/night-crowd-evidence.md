# Night, infrared and crowded-fight evaluation evidence

Audit date: 2026-10-21. Metadata/source inspection only. Sole output: this report. Read `PROTOCOL.md` first. No media, checkpoints or archives downloaded; no repository code executed; no packages, accounts, terms acceptance, external messages, model runs or live-service changes.

## Decision

**No audited source establishes a rights-cleared evaluation set combining 50–100 visible people, physical-fight/nonfight intervals, real near-IR night CCTV, low-light colour, and native 720p/1080p plus degraded 480p.** This is a bounded search result, not a claim that no such footage exists anywhere. Dataset population/volunteer totals are not simultaneous visible crowd counts.

ARID is the strongest immediately relevant copyright-licensed source for **real low-light colour action sensitivity**, but lacks a fight class and is distributed below 480p. LLVIP is a conditional low-light pedestrian-coverage source, **not a fight benchmark and not near-IR**. InfAR has a fight class but is thermal and rights/access remain unresolved. NTU offers controlled interpersonal actions and sensor IR, not crowded night CCTV. Fraunhofer IOSB is sunny-day thermal/object-action footage. None can support the required operational claim alone.

## Rights and modality ledger

“Conditional” below is not authorization to download or accept terms. Training and evaluation must each fit the source terms; internal evaluation for commercial gain is not automatically non-commercial. Code, weights and footage are separate assets.

| Source | Actual modality / labels | Training rights evidence | Evaluation rights evidence | 50–100 / night CCTV relevance |
|---|---|---|---|---|
| ARID v1 / v1.5 | Genuine low-light RGB; 11 actions, no fight | Author explicitly declares dataset CC BY 4.0; attribution/change notices required | Same copyright grant; suitability and participant/privacy rights still separate | No verified 50–100 scenes; v1 released 320×240 |
| LLVIP | Low-light visible + **thermal 8–14 µm**; pedestrian boxes | Non-commercial use only under explicit dataset terms | Same non-commercial boundary, including derivatives | No fight labels or verified crowd-count stratum |
| InfAR | Thermal action clips; includes fight, punch, push and benign interactions | No explicit original footage licence verified | Public-paper availability is not a dataset permission grant | No verified 50–100 or near-IR/night subset |
| Fraunhofer IOSB | Sunny-day visible + LWIR; object actions | Download request required; no explicit grant verified | Citation request alone does not establish permitted evaluation | Not a night or interpersonal-fight benchmark |
| NTU RGB+D / 120 | Kinect v2 RGB, depth, skeleton, IR; interpersonal action IDs | Academic/non-commercial, institutional eligibility and release agreement | Same restrictions; no assumption that commercial evaluation is allowed | Controlled action capture, not a verified 50–100/night-CCTV set |
| TNO Image Fusion v2 | Real nighttime intensified visible, near-IR and thermal imagery | Deposit CC BY 4.0; no action-training benchmark established | Useful sensor-domain inspection within terms | No fight labels, crowd counts or temporal benchmark verified |
| Violent-Flows | Real crowd violence/nonviolence from YouTube | Original landing page lacks explicit footage licence | Citation/access mechanism does not settle source-video rights | Relevant crowd lead; **50–100 and sensor/night conditions unverified** |
| RWF-2000 | Real surveillance fight/nonfight; quality challenges | Commercial use and modification/redistribution require approval | Same commercial boundary; official videos currently unavailable | Relevant quality lead; no verified 50–100 near-IR/night subset |

Evidence and asset pins follow. No dataset is marked “normal” merely because its labels omit fighting.

## 1. ARID — shortlist for low-light colour sensitivity only

The [author dataset page](https://xuyu0010.github.io/arid.html#papers-and-download) explicitly licences **dataset usage** under CC BY 4.0 and links the repository licence. It distinguishes v1 from v1.5; the latter has 5,572 clips. The [v1 paper, sections 3.1–3.3](https://arxiv.org/html/2006.03876v4) describes 3,784 clips captured strictly at night, using commercial cameras; released clips are 320×240, 30 fps, DivX AVI. These are real dark recordings, separate from the paper's synthetic HMDB51-dark comparison. The paper categorizes pushing under **person actions with objects**, so `Push` cannot automatically become a person-to-person fight positive.

Reproducible source: [`xuyu0010/ARID_v1@b03d0975f41547e8aa78929b8e26a62248f8e18f`](https://github.com/xuyu0010/ARID_v1/tree/b03d0975f41547e8aa78929b8e26a62248f8e18f). Exact numeric order in [`mapping_table.txt`](https://github.com/xuyu0010/ARID_v1/blob/b03d0975f41547e8aa78929b8e26a62248f8e18f/dataset/ARID/raw/list_cvt/mapping_table.txt): **0 Drink, 1 Jump, 2 Pick, 3 Pour, 4 Push, 5 Run, 6 Sit, 7 Stand, 8 Turn, 9 Walk, 10 Wave**. Three split train/test lists are in that same directory. Preserve group splits; do not randomly split neighboring clips.

Assets linked by the official page, not downloaded or checksum-verified:

- [v1.5 archive](https://drive.google.com/file/d/10sitw9Mi9Gv1jMfyMwbv78EZSpW_lKEx/view); do not assume v1 code lists match it.
- [v1 original folder](https://drive.google.com/drive/folders/1SQuAYv_mLixDqjyUU_A304wkaYLWgztg) and [compact v1](https://drive.google.com/file/d/1s1fenc8fDEXCIHFDv_eI0Fa42xisff3w/view).
- [Pretrained-model folder](https://drive.google.com/drive/folders/1bcfnAb8K6wQueCY3Em49DiDvdCs03YoM): individual checkpoint identity, checksum, training lineage and weight-specific terms **not verified**. The author's blanket CC BY statement is not an independent clearance of upstream Kinetics/ImageNet pretrained weights.

Actual code inspection: [`test/evaluate_video.py`](https://github.com/xuyu0010/ARID_v1/blob/b03d0975f41547e8aa78929b8e26a62248f8e18f/test/evaluate_video.py) defaults to 16 frames, interval 2, resize 256×256 then random 224×224 crop, 30 rounds, CUDA assertion and DataParallel. Normalization is **commented out**, despite means/stds existing in `network/config.py`. [`video_iterator.py`](https://github.com/xuyu0010/ARID_v1/blob/b03d0975f41547e8aa78929b8e26a62248f8e18f/data/video_iterator.py) converts BGR to RGB; [`video_transforms.py`](https://github.com/xuyu0010/ARID_v1/blob/b03d0975f41547e8aa78929b8e26a62248f8e18f/data/video_transforms.py) produces C×T×H×W float values divided by 255. Do not replace this with a guessed normalized recipe and call it checkpoint reproduction.

Use: after separate continuous review, eligible clips could probe false alerts on real dark everyday movement. They cannot measure fight recall, natural camera-hour false alerts, native 480p/720p/1080p accuracy, or crowd coverage. Upscaling 320×240 does not repair that gap. Dataset/README CC BY evidence is distinct from the paper's own arXiv publication licence.

## 2. LLVIP — conditional low-light person coverage, thermal rather than near-IR

The [official project](https://bupt-ai-cz.github.io/LLVIP/) identifies 15,488 aligned visible/infrared image pairs, pedestrian annotations and **8–14 µm thermal IR**. The [official terms](https://github.com/bupt-ai-cz/LLVIP/blob/c1a655cce437ebfd990a97b04fc48fbb99f4c47b/Term%20of%20Use%20and%20License.md) allow academic and non-academic entities' **non-commercial** use, require attribution, restrict commercial gain and reserve other rights; new annotations have disclosure/citation conditions. They describe 24 dark scenes and two daytime scenes. No fight/event labels are established.

Pin: [`bupt-ai-cz/LLVIP@c1a655cce437ebfd990a97b04fc48fbb99f4c47b`](https://github.com/bupt-ai-cz/LLVIP/tree/c1a655cce437ebfd990a97b04fc48fbb99f4c47b). This is the repository linked by the current official homepage; do not substitute the older `huiern214/LLVIP` snapshot examined during discovery.

The homepage has an information/terms form, **but** the pinned [`download_dataset.md`](https://github.com/bupt-ai-cz/LLVIP/blob/c1a655cce437ebfd990a97b04fc48fbb99f4c47b/download_dataset.md) also publishes official Drive links: processed data ID `1VTlT3Y7e1h-Zsne4zahjx5q0TK2ClMVv`, raw unregistered images/videos ID `1a0zNvj1mBh1v_HFWJ43LFbNEq8YLXB9-`. Public URLs do not remove licence conditions. No form submitted; file availability, bytes and checksums not tested.

Actual config [`yolov5/data/LLVIP.yaml`](https://github.com/bupt-ai-cz/LLVIP/blob/c1a655cce437ebfd990a97b04fc48fbb99f4c47b/yolov5/data/LLVIP.yaml) has `nc: 1`, `names: ['person']`; **index 0 is person, not fight**. It names train/val paths; verify packaging before reuse. Embedded YOLOv5 has [GPL-3.0](https://github.com/bupt-ai-cz/LLVIP/blob/c1a655cce437ebfd990a97b04fc48fbb99f4c47b/yolov5/LICENSE), while [FusionGAN code has MIT](https://github.com/bupt-ai-cz/LLVIP/blob/c1a655cce437ebfd990a97b04fc48fbb99f4c47b/FusionGAN/LICENSE). Neither relicences footage or establishes checkpoint-specific rights. No weights chosen.

Use only as a possible detection/missed-person study after permissible access and scene review. Image frames are not continuous fight-negative windows. Released/raw dimensions, codecs, temporal continuity and counts of simultaneously visible people remain unverified here. No claim of native HD or representative 50–100-person scenes.

## 3. InfAR — fight-labelled thermal lead, blocked on original rights/access

The [original dataset paper](https://doi.org/10.1016/j.neucom.2016.05.094) establishes infrared actions recorded across seasons. Its linked [original dataset site](https://sites.google.com/site/gaochenqiang/publication/infrared-action-dataset) redirected this audit to Google sign-in. No account used and no original footage licence recovered. Both training and evaluation permission therefore remain **unresolved**, not implicitly granted by a public download mirror.

The [TSTDDs author page](https://yangliu9208.github.io/TSTDDs/) explicitly links InfAR and shows a fight category. Its [authors' transfer-learning paper, section 4.1 and Figure 4](https://arxiv.org/pdf/1909.08297) describes 600 **thermal** clips at 293×256 / 25 fps, roughly four seconds on average, with 12 classes: fight, handclapping, handshake, hug, jog, jump, punch, push, skip, walk, one-hand wave, two-hand wave. These are semantic names, **not a verified numeric checkpoint class order**. Solo punch/push and ambiguous contact require review before any binary fight mapping. No verified night-hour stratum or 50–100-person count is supplied by these inspected descriptions.

Pinned ancillary release: [`yangliu9208/TSTDDs@2a023542e71dbacb4686ad1a8025fae111e25ce6`](https://github.com/yangliu9208/TSTDDs/tree/2a023542e71dbacb4686ad1a8025fae111e25ce6). Git tree contains README and site config, not the linked implementation archive. README links `InfAR_TDDs_rgb_iter_10000.caffemodel` ([Drive asset](https://drive.google.com/open?id=1ewd8RSUfyinKr_RFK3DfDKeRuu-BlwIv)), five-fold split indices and Matlab code; requires Matlab R2016b+, compiled improved trajectories/TV-L1 flow and MatCaffe. No licence file or explicit weight-specific terms found in this pinned repo. Archives/checkpoint not fetched; preprocessing and numeric class order remain blocked on source inspection. The paper's publication licence does not licence InfAR footage.

Verdict: conditional **thermal transfer** research lead only; not near-IR CCTV evidence and not immediately executable/cleared for NIVRA.

## 4. Fraunhofer IOSB / Hough forests — reject for required night-fight benchmark

The [institute's dataset page](https://www.iosb.fraunhofer.de/en/competences/image-exploitation/object-recognition/vca/vca-datasets.html#Multispectral%20Action%20Dataset) explicitly describes a **sunny summer day**. Two AXIS Q1922 cameras capture 8–14 µm LWIR, with visible AXIS cameras at two views. Postprocessed dimensions are IR 640×480 and visible 800×600, at 25 fps. Ten participants is a dataset total, not evidence of ten simultaneous people.

Classes are film, hit an **object with a stick**, kick an **object**, point, throw, wave, and other. These do not establish unarmed interpersonal fight labels. The page requests author contact for a download link/password and citation of [Hilsenbeck et al., 2016](https://publica-rest.fraunhofer.de/server/api/core/bitstreams/b68a39a6-74fe-4d04-ac2c-3c6832dc03db/content). No explicit footage training/evaluation grant, pinned code release, trained asset or numerical model class order was verified. No contact sent. **Do not count thermal daylight as real night validation or object strikes as physical fights.**

## 5. NTU RGB+D / 120 — controlled interactions, restricted access

[ROSE Lab's terms](https://rose1.ntu.edu.sg/dataset/actionRecognition/#terms) limit use to academic/non-commercial research by eligible educational/research institutions; access requires registration, request and release agreement. Commercial use, redistribution and deriving a new dataset require expressed permission; demonstrations are restricted to academic publications/presentations. This does not authorize NIVRA product evaluation/training by default. Neither terms acceptance nor downloads occurred.

Pinned author source: [`shahroudy/NTURGB-D@ac2ebc87e6e9777ea6bac67e65e53b325b903f74`](https://github.com/shahroudy/NTURGB-D/tree/ac2ebc87e6e9777ea6bac67e65e53b325b903f74). [README](https://github.com/shahroudy/NTURGB-D/blob/ac2ebc87e6e9777ea6bac67e65e53b325b903f74/README.md) documents Kinect v2 RGB at 1920×1080 and sensor IR/depth at 512×424, filename fields `SsssCcccPpppRrrrAaaa`, and action IDs. Relevant IDs: **A050 punch/slap another person; A051 kick another person; A052 push; A053 pat back; A055 hug; A058 handshake; A059 approach; A060 separate**. IDs are one-based dataset labels; checkpoint output indexing needs its own mapping. Do not automatically mark every clip in the first three classes as a fight interval.

The [original paper](https://arxiv.org/abs/1604.02808) describes controlled daily/mutual actions, not a crowd/night-CCTV benchmark. Kinect IR is a real sensor stream, not converted RGB; [Microsoft's v2 documentation](https://download.microsoft.com/download/6/7/6/676611b4-1982-47a4-a42e-4cf84e1095a8/kinecthig.2.0.pdf) identifies an IR emitter/camera. This audit does not pin an exact wavelength or establish nighttime capture. Do not equate Kinect capture with an installed near-IR security camera.

Actual source inspected: [`show_skeleton_on_IR_frames.m`](https://github.com/shahroudy/NTURGB-D/blob/ac2ebc87e6e9777ea6bac67e65e53b325b903f74/Matlab/show_skeleton_on_IR_frames.m) uses VideoReader and crops displayed IR to 424×512. `Python/txt2npy.py` reads skeleton coordinates; it is not a CCTV fight classifier. No root code licence or checkpoint was verified. Preserve original sensor intensity/bit depth until actual assets and candidate preprocessing are audited. IR upscaling cannot count as native 720p/1080p.

## 6. Additional leads that do not close the gap

**TNO nighttime near-IR:** [official deposit v2](https://doi.org/10.6084/m9.figshare.1008029.v2), [versioned metadata API](https://api.figshare.com/v2/articles/1008029/versions/2), declares CC BY 4.0 and identifies intensified visible, near-IR and thermal nighttime imagery. This is useful genuine-NIR domain material, **not verified temporal fight/nonfight or crowd evidence**. No action labels, numeric class order or runnable action model established. Archive metadata only: `TNO_Image_Fusion_Dataset.zip`, file ID `1475454`, **122,712,465 bytes**, computed/supplied MD5 `1ab9ce3b84dd3e5894630c13abd20953`; bytes not downloaded. Description permits credited research use; CC BY metadata is explicit copyright evidence, not proof of participant releases or applicability to product surveillance.

**Violent-Flows:** [author page](https://talhassner.github.io/home/projects/violentflows/index.html) offers 246 crowd violence/nonviolence YouTube clips, duration 1.04–6.52 seconds (mean 3.60), Matlab `VIF_create_feature_vec.m`, and a details form to reveal FTP credentials for `Movies.zip`. No explicit footage licence identified. No form completed. Crowd scenes are relevant but do not verify the requested 50–100 count, near-IR sensor, night colour, HD originals or clearance of underlying videos. Some clips cannot form a four-second window; never stretch/repeat them to manufacture one. Descriptor code availability is not video permission or a trained fight checkpoint.

**RWF-2000:** [pinned official README](https://github.com/mchengny/RWF2000-Video-Database-for-Violence-Detection/blob/1267a1208574af651dc2ea9b1439cb60b5a9fc54/README.md) describes surveillance quality/crowd problems, 2,000 YouTube-sourced clips within five seconds, and says videos are currently unavailable for privacy reasons. It requires approval for commercial use and modification/redistribution. Both training and commercial-purpose evaluation remain gated. A Kaggle/Hugging Face MIT label is not a replacement licence. No verified near-IR, exact crowd counts, source-native HD or clean model-independent holdout. Existing community fight-model training provenance must be checked before using RWF for comparative generalization claims.

**SCFD:** [pinned README](https://github.com/seymanurakti/fight-detection-surv-dataset/blob/ff83b7c521e5ca4eb67a212cc42dbc54f39d6290/README.md) describes 300 YouTube-derived two-second clips, including object strikes. Its [MIT file](https://github.com/seymanurakti/fight-detection-surv-dataset/blob/ff83b7c521e5ca4eb67a212cc42dbc54f39d6290/LICENSE) grants software/documentation rights; no separate explicit source-video clearance established. Two seconds cannot fill NIVRA's four-second window. No verified crowd/night modalities; not an immediately eligible target benchmark.

**DarkAct, current supplementary lead:** [`darkact-creator/DarkAct@091a181a1bac5b1250ad6f4c75049decd9a9695c`](https://github.com/darkact-creator/DarkAct/tree/091a181a1bac5b1250ad6f4c75049decd9a9695c) describes paired low-light RGB/thermal video, 27 daily-action classes and 11 volunteers; it declares MIT for the project but **non-commercial academic research for the dataset**. No fight class or 50–100 crowd evidence. Inspected Git tree contains LICENSE, README, paper and illustrations, **no model implementation/config/checkpoint despite README implementation claims**. Its officially linked [HF card](https://huggingface.co/datasets/Gooddayorig/DarkAct/blob/main/README.md) contains an MIT tag; do not let this erase the author's explicit dataset restriction. Numeric class order, bytes, native resolutions and executable assets remain unverified; not shortlisted for immediate running.

## Reproduction and evidence limits

Repository revisions above were resolved from public GitHub commit/tree metadata or `git ls-remote HEAD`, then selected raw text/config/licence files were read without execution. GitHub API rate limiting prevented additional discovery; raw primary files and refs supplied the documented pins. InfAR's original site redirected to login. The LLVIP CVF PDF endpoint returned 403 and its arXiv PDF exceeded the web tool size limit; no large-paper workaround or media fetch performed. Therefore dimensions not confirmed in the inspected LLVIP text remain unknown here.

Metadata fingerprints fetched 2026-10-21 around 15:53 UTC (hashes identify response bytes, not downloadable footage):

| Source response | SHA-256 |
|---|---|
| `https://xuyu0010.github.io/arid.html` | `b05b00b3d6da5f26b74fcfa61117c06a4d5c6b81afcfaa3b70df85e9f5760b2f` |
| `https://bupt-ai-cz.github.io/LLVIP/` | `ae0627cdb08b83dcb8102e280f8226698bd838bb167473289dcfe21ad6da5ece` |
| TNO version-2 API response | `db5ad319442ae610b75601ffce828d91704c2672882283d49f1e9a50f2f107bc` |

No footage was visually reviewed in this task. All capture/label descriptions above are attributed source claims, not independent frame review. No media/checkpoint file checksum was verified; TNO MD5 is deposit metadata only. No pretrained accuracy percentage is ranked against another dataset.

## Final shortlist, blockers and empirical work left to parent

1. **ARID v1, then separately audited v1.5:** first choice for real low-light RGB action/false-alert sensitivity under explicit CC BY dataset copyright terms. Preserve released groups; individually verify candidate normal windows. Blockers: no fight class, small source resolution, no 50–100 crowd stratum; checkpoint lineage not audited.
2. **LLVIP visible stream:** conditional person-coverage/occlusion study if proposed use is permitted; raw video needs its own continuity and annotation audit. Blockers: non-commercial terms, no fight/normal temporal labels, thermal rather than near-IR partner. It cannot validate fight recall.
3. **TNO v2:** narrowly useful real nighttime near-IR sensor-domain reference under explicit CC BY deposit metadata. Blockers: no established action/crowd-video benchmark. Never treat thermal pairs, image fusion examples or still images as near-IR fight windows.
4. **InfAR and NTU:** permission-dependent controlled interaction/thermal-or-sensor-domain probes only. Fraunhofer is out of the required night-fight shortlist. Violent-Flows/RWF remain rights/access and exact-condition leads, not approved imports.

**Windows / GTX1660Ti 6 GB fit (engineering inference, untested):** sequential bounded OpenCV decoding and metadata preparation should be practical on CPU; use the existing runtime and `cv2.setNumThreads(1)`. ARID's legacy CUDA/DataParallel evaluator needs isolated compatibility review and explicit bounded batch/round settings before any parent-run experiment. No full legacy model/checkpoint fit, throughput or VRAM claim is established. Matlab/Caffe/compiled optical-flow TSTDDs is a poor immediate Windows integration choice. LLVIP/NTU/TNO are data sources, not runnable fight replacements. Nothing here establishes that 50–100 regions can be scheduled within alert latency or 6 GB.

**Required new independent evidence:** rights-cleared real near-IR monochrome night CCTV and low-light colour recordings, each containing actual 50–100 visible people, with both fight events and representative long nonfight periods. Record native dimensions/codec/bitrate/fps, camera modality evidence, source-time action boundaries, visible counts, person pixel heights and occlusion. Native 1080p and 720p need actual source files; derive fixed 480p/compression variants only afterward. Separate camera/session/actor lineages before choosing a held-out set; verify overlap with every candidate's training corpora.

**Claims still unverified:** crowded fight recall, near-IR-night fight recall, low-light-colour fight recall, false alerts per camera-hour, crowd localization/coverage, small/occluded-person sensitivity, native-HD and degraded-480p transfer, frame drops/region starvation, alert delay, Windows compatibility, classifier latency and peak GPU memory. None can be inferred from the existing few-person diagnostics, synthetic darkening/grayscale/tiled crowds, or a perfect VID training fit. Parent retains the live X3D-M until an independently supported comparison warrants a change.
