# Benchmark readiness: classifier comparison and CCTV robustness

21 October 2026. Read-only audit under [PROTOCOL.md](PROTOCOL.md). **No model,
inference, training, GPU, transcode or live-service run was performed.** Only this
report was written; no packages, checkpoints or external repository code were
installed or executed. Public source/config/API responses were inspected in
memory. Local checkpoint files were hashed without deserialization.

## Decision

The repository supports a reproducible **development diagnostic**, but its two
comparison scripts are not yet a fair, general benchmark for new checkpoints,
native-resolution degradation, 50-100 people, or genuine night/near-IR cameras.
Preserve community X3D-M as the control. Retain MC3-18 as a known faster control,
not a newly promising detector. Reserve a third slot for a parent-selected GitHub
classifier only after its checkpoint, class order, preprocessing, safe loader and
permissions pass the admission contract below. Official Flow-Gated Network is a
concrete third-repository option inspected here, but currently blocked.

The immediate engineering prerequisite is a source-resolution, timestamp-checked
window contract with explicit device selection. Do not feed all candidates the
public demo's pre-resized 224-square buffers and call that native preprocessing.
Run the historical reproduction and the new contract as separately named tracks.
No README accuracy percentage was used to rank candidates.

## Existing evidence, not a new experiment

[FIGHT-MODEL-COMPARISON.md](../../evaluation/FIGHT-MODEL-COMPARISON.md) records
both X3D-M and MC3-18 matching 2/3 original annotated events, with one extra
shadowboxing unmatched alert from MC3. The four original clips total 39.221 s;
the fifth entry is a crop of the grappling source. All influenced development.
Neither their historical split names nor additional codec variants create an
independent holdout. Cropped grappling must remain outside original-source totals.

That prior GTX 1660 Ti FP32/batch-one run reported X3D median/p95 132.3/244.9 ms
and 145.1 MiB peak Torch allocation; MC3 56.6/113.4 ms and 115.7 MiB. These are
historical measurements, not rerun here. They include adapter preprocessing and
inference, exclude decode/tracking/transport/queues, and do not measure camera
capacity. The report used three warmups and synchronized CUDA timing.

[ROUND2-RESULTS.md](../../training/ROUND2-RESULTS.md) supersedes the earlier pilot:
96 VID recordings, 156 training windows, one unresolved cohort, no calibration or
holdout. The final-stage/head candidate fitted training but flagged only 1/17
grappling windows, 0/2 kick windows and 0/17 cropped grappling windows, versus
13/17, 2/2 and 10/17 for community X3D. It was not promoted. Training fit does
not identify whether model representation, annotations, background shortcuts or
domain coverage caused failed transfer. VID must not be repurposed as unseen
evaluation or automatically relabeled from publisher categories.

## Local readiness findings

| Priority | Inspected source | Consequence for comparison |
| --- | --- | --- |
| Blocking for general candidates | [compare_x3d_training.py:113-143](../../compare_x3d_training.py), [fight_demo.py:25-63](../../nivra/fight_demo.py) | Decoder PTS are validated, gaps/dimension changes reset history, but `FightWindow.add` resizes every retained frame to 224x224. This is faithful public-demo replay, not a source-resolution buffer for a different checkpoint or optical flow. |
| Blocking for a robust new runner | [benchmark_fight_models.py:56-85](../../benchmark_fight_models.py) | Preserves decoded spatial resolution but has no finite/strictly increasing PTS validation, discontinuity/dimension reset, minimum eight-frame condition, or explicit short/gap coverage rejection. A corrupt clock can silently omit data; a sparse history can bridge missing observations. Do not reuse this clock unchanged. |
| Blocking for parent-controlled CPU staging | [x3d_candidate.py:20-46](../../nivra/x3d_candidate.py), [benchmark_fight_models.py:30-53,101-144](../../benchmark_fight_models.py) | Constructors automatically choose CUDA when visible. The older runner lacks a device flag, memory cap and DemoYieldGuard. `compare_x3d_training.py` hides CUDA only in its standalone entry point, rejects visible CUDA in `run`, and supports only the frozen-head artifact kind. It is not a plug-in runner for arbitrary candidates. |
| Score-policy mismatch | [fight_demo.py:287-295](../../nivra/fight_demo.py), [pipeline.py:143-146](../../nivra/pipeline.py), [decision.py:31-49](../../nivra/decision.py) | Public `/fight` and the classifier benchmark use `backboneScore > .5`. The separate operator pipeline feeds `publisherScore` into a .4/.7 confirmation rule with a two-observed-person gate. These are different systems and must not share an unlabeled accuracy/timing table. No live policy was changed. |
| Event metrics need qualification | [benchmark_fight_models.py:88-98](../../benchmark_fight_models.py), [evaluate.py:35-49](../../evaluate.py) | Historical alerts use strict >.5 and an 8000-ms cooldown. Matching greedily assigns the first unused alert between event start and event end+3000 ms. The kick alert can therefore be credited to the earlier takedown. A repeated alert during one long event becomes an unmatched alert. Neither count alone is a verified normal-scene false positive. |
| Measurements incomplete | [benchmark_fight_models.py:114-143](../../benchmark_fight_models.py), [compare_x3d_training.py:192-210](../../compare_x3d_training.py) | Older benchmark warms/synchronizes and records allocated memory, but not reserved memory, RSS, queue/drop statistics, device-total use, demo interference or repeat variability. Comparison script is CPU-only and lacks a dedicated timing protocol. Neither establishes real-time throughput. |
| Run integrity incomplete in older runner | [benchmark_fight_models.py:101-144](../../benchmark_fight_models.py) | It writes/overwrites output as models finish and does not mark a partially populated report explicitly incomplete. It does not validate every model/media input before any model is loaded. New comparison should fail before construction on bad inputs and publish completion only after all required cells finish. |
| Manifest semantics narrow | [evaluate.py:15-32](../../evaluate.py), [corpus.json](../../evaluation/corpus.json) | Validation checks IDs, reviewed status, event bounds and group split leakage, but not a full native-resolution/sensor/variant-lineage contract. Existing `reviewed` means approximate episode review, not exhaustive per-window or person-level ground truth. Unknown intervals cannot be counted as verified normal. |

The current full-state fine-tune adapter, [FineTuneCandidate](../../nivra/x3d_finetune.py),
already offers CPU `predict(BGR_frames)->float` and integrity-checked safe loading.
Its diagnostic path reuses the same pre-resized public windows. Preserve it for
replaying that failed experiment, without interpreting it as a generic raw-frame
benchmark or editing it during this research task.

### Installed capabilities, inspected without importing Torch/CUDA

`service/.venv/Scripts/python.exe` reports Python 3.11.15 and native Windows build
10.0.26200. Distribution metadata: torch 2.5.1+cu124, torchvision 0.20.1+cu124,
PyTorchVideo 0.1.5, NumPy 1.26.4, OpenCV 4.11.0.86, ONNX Runtime GPU 1.21.1,
pytest 8.3.5. No TensorFlow, Keras, h5py, safetensors or Albumentations distribution
was found in that environment. Local adapters reproduce the relevant MC3 resize,
crop and normalization without needing Albumentations.

Neither `ffmpeg` nor `ffprobe` was found on PATH by `shutil.which`; this does not
exclude a separately bundled binary elsewhere. OpenCV presence does not establish
controlled libx264 encoder availability or reproducible CRF/GOP settings. Parent
must stage a trusted codec tool/version before the compression matrix. No package
installation or codec operation was attempted here.

## Pinned assets and preprocessing

### A. Community X3D-M: required control, already local

- Publisher/model revision: `a744b6af7496f0cbfa4f0ba32acd46b65e52d4e1`.
  Exact asset is [final/final_x3d_realtime.pt](https://huggingface.co/visionlab-ai/school-violence-detection-models/blob/a744b6af7496f0cbfa4f0ba32acd46b65e52d4e1/final/final_x3d_realtime.pt),
  **12,268,364 bytes**, SHA-256
  `e833f69d110f167cad4a6c38d385564bdb2f6de63d246e45cb03ff9aa17f0349`.
  Local `models/x3d_rwf2000.pt` matches size/hash. This is not the separate
  `x3d_m/x3d_m_best.pt` asset; renaming the final asset is not a new candidate.
- Local adapter: PyTorchVideo X3D-M, dropout/linear two-class projection; class
  order `[non-violent, violent]`, fight index **1**. Retained backbone activation
  is already Softmax. Use `backboneScore`; never apply a second Softmax as though
  it were logits. Sampling is 16 floor-linspace indices from the source-window
  samples, BGR->RGB, OpenCV square 224 resize, float32 /255, mean .45/std .225.
- Source wrapper was checked at Space revision
  `67d51a3743f276b96f87fa07d83d4ac5b9d326f8`:
  [x3d_model.py](https://huggingface.co/spaces/visionlab-ai/school-violence-detection-app/blob/67d51a3743f276b96f87fa07d83d4ac5b9d326f8/sv_model/x3d_model.py)
  leaves the backbone activation intact. Its
  [loader](https://huggingface.co/spaces/visionlab-ai/school-violence-detection-app/blob/67d51a3743f276b96f87fa07d83d4ac5b9d326f8/model_loader.py)
  uses unrestricted `weights_only=False` and non-strict state loading; do not
  adopt those behaviors. Local loader instead pins bytes and uses restricted
  numeric-metadata allowlisting with `weights_only=True` and strict keys.
- Publisher config/card contain generic 32-frame settings, while the final asset
  spec explicitly uses 16 frames and publisher threshold .4. Freeze **NIVRA's
  existing >.5 control**, not a silent threshold migration. Public model code is
  inspectable in its HF Space; the model card does not supply a public training
  GitHub URL. Describe this honestly as an existing HF-hosted control using a
  GitHub framework, not a newly verified GitHub training release.

Rights are three separate questions. PyTorchVideo code is Apache-2.0. Publisher
metadata says MIT, while its pinned [model-card License section](https://huggingface.co/visionlab-ai/school-violence-detection-models/blob/a744b6af7496f0cbfa4f0ba32acd46b65e52d4e1/README.md)
also describes research/noncommercial use; record that conflict rather than
declaring commercial checkpoint clearance. Its reported RWF-2000 training
provenance does not confer dataset or participant-release rights. The RWF
authors' separate restrictions are linked under C below. This audit does not
expand the baseline's existing usage authority.

### B. MohamedSebaie MC3-18: required historical control, already local

[Repository/code revision](https://github.com/MohamedSebaie/Fight_Detection_From_Surveillance_Cameras-PyTorch_Project/tree/a27adffec6651c10639b5b453e0df8564b9be298)
is `a27adffec6651c10639b5b453e0df8564b9be298`, verified as current main during
this audit. Asset [Models/model_16_m3_0.8888.pth](https://github.com/MohamedSebaie/Fight_Detection_From_Surveillance_Cameras-PyTorch_Project/blob/a27adffec6651c10639b5b453e0df8564b9be298/Models/model_16_m3_0.8888.pth)
is **46,044,557 bytes**, SHA-256
`8268694ade4c0e79a1c5fa41a4f3c21129082d75fac9eb7c25e5a0eabad49bfa`;
local `models/mc3_18_sebaie.pth` matches. Architecture: torchvision `mc3_18`,
two-output `fc`, raw logits. Publisher classes are `[fight, noFight]`: fight
index **0**, opposite the X3D convention. Apply Softmax once and select index 0.

The pinned [utility source](https://github.com/MohamedSebaie/Fight_Detection_From_Surveillance_Cameras-PyTorch_Project/blob/a27adffec6651c10639b5b453e0df8564b9be298/UtilsFiles/Fight_utils.py)
documents 16 frames; RGB resize width171/height128, center crop112 at x29/y8,
/255, mean `[.43216,.394666,.37645]`, std `[.22803,.22145,.216989]`.
NIVRA's adapter uses floor-linspace temporal selection for the shared causal
window. Publisher whole-video/frame-skip inference is a different temporal
protocol, not a live comparison contract. Its original helper requests pretrained
weights and performs unrestricted loading; continue using the independent local
safe adapter, not a package import or utility execution.

The [repository LICENSE](https://github.com/MohamedSebaie/Fight_Detection_From_Surveillance_Cameras-PyTorch_Project/blob/a27adffec6651c10639b5b453e0df8564b9be298/LICENSE)
is MIT code/software licensing. No distinct checkpoint-specific grant or complete
training-video rights/participant-release record was verified. The filename does
not prove correspondence to the README's best run. Source/input equivalence is
not equal spatial coverage: its center crop discards peripheral scene content.

### C. Official RWF-2000 Flow-Gated Network: concrete but blocked third slot

[Repository revision](https://github.com/mchengny/RWF2000-Video-Database-for-Violence-Detection/tree/1267a1208574af651dc2ea9b1439cb60b5a9fc54)
`1267a1208574af651dc2ea9b1439cb60b5a9fc54` was verified as current master.
Git tree advertises `Models/keras_model.h5`, **1,208,192 bytes**, Git blob
`a99c011537e5165e3e828b55e18ebb85e4036d6b`. **Checkpoint bytes/SHA-256 and
serialized config were not fetched or validated**; a Git blob SHA-1 is not a
locally verified checkpoint SHA-256.

Inspected [network notebook code cells](https://github.com/mchengny/RWF2000-Video-Database-for-Violence-Detection/blob/1267a1208574af651dc2ea9b1439cb60b5a9fc54/Networks/Flow%20Gated%20Network.ipynb)
specify `(batch,64,224,224,5)`, RGB and two flow channels, two-way Softmax,
sorted training-folder label order and separate RGB/flow whole-clip z-score
normalization. Sampling uses ceil-stride plus tail padding, not linspace.
The shown training selector names `ViolentFlow-opt`, so neither checkpoint
training lineage nor exact class-index correspondence is proved by that notebook.
The network contains Lambda layers and legacy four-GPU training helpers;
do not deserialize functions or execute the notebook.

[Preprocessing notebook](https://github.com/mchengny/RWF2000-Video-Database-for-Violence-Detection/blob/1267a1208574af651dc2ea9b1439cb60b5a9fc54/Preprocess/Video2Numpy.ipynb)
shows RGB INTER_AREA resize, Farneback flow from adjacent decoded frames,
per-component mean removal and 0-255 scaling, zero final flow, and uint8 storage.
Folder names `Fight`/`NonFight` suggest index0 only if the released model used
that exact generator/data; do not assume it. Flow must be computed before sparse
temporal selection. Static flow also exposes zero-std normalization in shown code.

No separate permissive code LICENSE was present in the inspected Git tree, and
no checkpoint-specific grant was established. The authors'
[README terms](https://github.com/mchengny/RWF2000-Video-Database-for-Violence-Detection/blob/1267a1208574af651dc2ea9b1439cb60b5a9fc54/README.md)
restrict dataset modification/redistribution and commercial use without approval;
they are not a blanket code/model license. The database is no longer supplied
there for privacy reasons. Source code, checkpoint terms and dataset rights remain
distinct unresolved gates.

Current environment lacks its runtime. Official [TensorFlow native-Windows guidance](https://www.tensorflow.org/install/pip#windows-native)
states 2.10 was the last release with native-Windows GPU support; modern TF
would require a different runtime route. Do not modify the live venv or stage
legacy CUDA dependencies here. A reviewed weights-only conversion/reimplementation
would be a separately versioned adapter requiring numerical parity evidence.
Do not count FGN as runnable or GTX-fit merely because its file is small.

## Proposed comparison contract: `nivra-classifier-cctv-v1`

Everything below is a proposal for parent implementation/runs, not code added or
results produced by this helper.

### Admission and adapter boundary

Admit 2-3 checkpoint identities, not repository marketing names. For each freeze:
code commit and source hash, weight URL/filename/byte count/SHA-256, package
versions, architecture/head, stored logits versus probabilities, complete class
order/fight index, color/range/layout, resize/crop/interpolation/normalization,
temporal sampler and minimum context, safe loader, licenses/rights uncertainties,
device/precision and decision policy. Unknown mapping or incompatible safe loading
is a blocking status, not an opportunity to infer labels from diagnostic scores.

Recommended interface, independently implemented from inspected code:

```text
CandidateSpec: immutable provenance + tensor/preprocessing/output contract
load(spec, local_checkpoint, device='cpu', dtype='float32') -> Candidate
WindowPacket: sourceGroup, variantId, start/end PTS, source frame PTS,
              BGR uint8 frames at variant resolution, validity/coverage metadata
Candidate.predict(packet) -> {fightScore, classScores, scoreKind,
                              fightIndex, evidenceStartMs, evidenceEndMs}
```

An adapter owns tensor sampling/spatial preprocessing only; it must not decode,
fetch weights, change devices automatically, choose thresholds or suppress alerts.
CPU means CPU even on a GPU machine. Load checksum first, trusted local architecture
with pretrained downloads disabled, restricted weights-only state loading and
strict shape/key validation. No remote custom code or unsafe-pickle fallback.
Finite in-range fight score is required; logits and probability vectors are
validated according to their declared contract. No zero-sum/NaN repair is hidden.

### Clock, frames and policy

1. **Legacy reproduction lane:** use each historical script/source hash and its
   exact windows/policy only to reproduce its saved report. Do not compare new
   native-preprocessing candidates against historical scores on different buffers.
2. **New paired lane:** freeze a source-time endpoint/index manifest before any
   classifier runs. Validate finite strictly increasing decoder presentation PTS;
   never derive time from a malformed nominal FPS denominator. Source gaps >1200 ms,
   dimension changes, seeks or stream changes clear history. Require >=8 observed
   gate samples, >=3800-ms span, <=4000-ms history, >=100-ms gate sample spacing,
   and >=400-ms prediction spacing. Record actual start/end, coverage and exclusions.
   No padding across missing time or stretching a <4-s source into a window.
3. Retain source/variant-resolution frames, or deterministically re-decode indexed
   frames under an explicit RAM budget; **no global 224 resize**. One decoder/model
   at a time. Give every candidate identical eligible source intervals and region
   geometry; apply each checkpoint's documented resize/crop afterward. Store its
   selected frame indices/PTS. For current X3D/MC3 use their existing 16 floor-linspace
   picks from gate samples. A 32/64-frame candidate needs sufficiently dense source
   observations and its own documented sampler; do not manufacture them by repeating
   a shared 16-frame tensor. Any source-native padding policy is a named sensitivity
   condition, never hidden valid coverage. A different required context is a separate
   matched-context experiment, not a silently unequal temporal comparison.
4. Primary diagnostic rows: uncalibrated score, strict `score > .5` review decision,
   timing, PTS and overlap context. All candidates use the fixed .5 checkpoint
   comparator; publisher-specific thresholds, if inspected and frozen beforehand,
   are a clearly separate secondary table. Equal .5 does not mean equal operating
   points or calibration. No selecting the better threshold after seeing this corpus.
5. Preserve the 8000-ms source-time cooldown and inherited end+3000-ms greedy
   `score_clip` convention only in a table labeled **historical event diagnostic**.
   Also show raw review windows, disagreements, per-event compatible alerts and
   ambiguity: no claim that a later kick recognized an earlier takedown. Counts
   of overlapping positive windows are not incident recall or independent trials.
6. Prospective acceptance needs independently reviewed episode annotations and
   normal/unknown coverage. Predeclare matching/tolerance before seeing predictions;
   recommended primary tolerance is 1000 ms after visible episode end, with valid
   evidence-window overlap and one-to-one chronological episode matching. Report
   cooldown-suppressed close episodes and duplicate alerts separately from alarms
   on verified normal time. Keep legacy matching as a secondary sensitivity table.
   Mid-event clip starts cannot yield incident-onset delay. Scene-only classifiers
   are evaluated for any visible scene interaction, not attribution to people.

For independent future calibration, use recording/session-disjoint camera footage
and freeze the threshold before a separate untouched holdout. All variants/crops
stay with their parent source. VID lineage remains unresolved and training-only.
Unknown labels and normal-time gaps are excluded, with their duration reported.

### Resolution and compression matrix

Keep original bytes as variant `original`; capture actual width/height, rotation,
codec/profile, pixel format/bit depth, frame rate and complete PTS, bitrate, duration,
illumination/sensor provenance, camera/session lineage, occlusion, visible-person
count range, and representative/interaction person pixel heights. Unknown metadata
remains unknown. Current corpus does not carry those crowd/sensor annotations.

Proposed controlled synthetic matrix, using a parent-staged trusted encoder:

| Native parent source | Derived sizes allowed | Codec conditions at each size |
| --- | --- | --- |
| Genuine 1920x1080 | 1080, 720 and 480 lines | H.264 libx264, preset medium, yuv420p, CRF23 and CRF35 |
| Genuine 1280x720 | 720 and 480 lines | Same settings |
| Genuine 480-line source | Original and 480 only | Same settings if re-encoding |
| Smaller/unknown native parent | No invented higher-native tier | Log native evidence as unavailable; lower-resolution sensitivity only |

For a 16:9 parent use 1920x1080, 1280x720 and even-width 854x480; preserve
aspect ratio for other sources and record actual dimensions. Use INTER_AREA or
equivalent declared area downsampling before encoding, no sharpening/denoising,
no frame interpolation. Pin encoder binary/version/hash and full commands. GOP
target 2 s at measured frame rate; disable scene-cut variation where supported,
and report GOP/keyframes and resulting bitrate, not CRF alone. Preserve source
PTS; verify frame count/PTS correspondence after B-frame reordering. If a backend
rebases or shifts clocks, prove/document the mapping before pairing score rows.
Reject unmapped changes rather than moving event labels by assumption.

For a verified constant-30-fps, zero-based, 16:9 source, this is an illustrative
**parent-only, not executed** 480p/CRF35 command after staging a trusted binary:

```powershell
ffmpeg -n -copyts -i original.mp4 -map 0:v:0 -an -vf "scale=-2:480:flags=area" -c:v libx264 -preset medium -crf 35 -pix_fmt yuv420p -g 60 -keyint_min 60 -sc_threshold 0 -fps_mode passthrough -avoid_negative_ts disabled derived-480-crf35.mp4
```

For other measured frame rates, freeze the corresponding GOP frame count and
actual keyframe intervals; do not assume 30 fps from a filename. For non-zero or
variable-rate sources, retain/verify the actual source-to-variant PTS mapping.
Generate every variant directly from the original, never by cascading 1080->720->480
or CRF23->CRF35. Do not run this command with an uninspected PATH binary or treat
an encoder's successful exit as verification of its output/timestamp contract.

CRF23/35 are proposed reproducible sensitivity levels, **not validated models of
Harsh's cameras**. A re-encoded 1080p copy is not native camera evidence. Use the
same frozen variant bytes for every candidate; variant metadata includes parent
SHA-256, transform hash, output hash and lineage. Report paired score changes,
miss/review changes and timing per original recording; do not pool derivatives
as independent samples. Distinguish resize-only loss from additional codec loss
with a lossless decoded/downsampled reference when parent tooling permits.

Do not convert grayscale/darkened daylight into purported night evidence. Such
variants, if later requested, are synthetic sensitivity tests only. Native
near-IR/monochrome CCTV needs sensor/IR-cut/illumination provenance where available;
an unknown black-and-white clip is only unknown-sensor monochrome. Thermal IR is
a separate sensor modality. Genuine low-light color needs its own real recordings,
noise/motion blur/compression and camera metadata. Record any bit-depth/tone mapping
explicitly before an 8-bit model adapter; do not silently truncate higher-bit data.

### Crowd coverage is a separate benchmark

Whole-scene 224/112 classifiers have no person-count output or interaction
localization. Many far-field bodies become tiny after resize; MC3's crop also
removes edges. This task cannot be satisfied by increasing a `maxPeople` setting.

[server.py:29,152](../../nivra/server.py) caps the operator protocol at 50;
[models.py:63](../../nivra/models.py) advertises 8 or 50 depending on person model.
[pipeline.py:75](../../nivra/pipeline.py) selects confidence*sqrt(area), potentially
excluding small/distant people. [regions.py:4-21](../../nivra/regions.py) rotates
five fixed views and excludes boxes with <70% of their area in a view; it is not
an exhaustive interaction scheduler. At the best-case 400-ms action cadence,
revisiting five views takes about 2 s before load-induced delay. The X3D scene
branch remains a whole-scene call. These are code observations, not measured
50/100-person behavior; the public `/fight` path is a separate scene-only demo.

A later end-to-end track must measure person detection/track availability by
pixel height/occlusion; which interacting pairs/regions were observed, scheduled,
expired or dropped; per-region evidence age and revisit interval; burst/queue
latency; and localized interaction recall with anonymous spatial annotations.
Report scene alerting separately from localization. Real 50-100-person normal
interactions and fights in the required camera modalities are absent from current
holdout evidence. Synthetic tiled crowds or mocked detections can test scheduling
and memory only. They establish neither crowd recognition nor real occlusion
performance. No identity, audio or policing functions belong in this adapter.

## Parent-only CPU smoke to GPU schedule

1. **Freeze before runs:** select at most three admitted checkpoint IDs; copy
   manifests/policies/hashes into a new ignored run directory. Validate every input
   and permission gate before constructing models. Existing reports/checkpoints
   are immutable. No training or threshold selection in this benchmark.
2. **CPU smoke in a fresh isolated process:** parent explicitly forces CPU before
   importing model adapters, Torch threads2 and OpenCV threads1. Validate safe
   load/tensor/output mapping with a short valid source window; then original
   diagnostics, identical row keys and positive/negative clip presence. This
   helper did not perform even CPU inference. A semantic smoke failure is a
   candidate status, never a reason to invert classes or lower its threshold.
3. **One parent-coordinated GPU process at a time:** explicit CUDA, FP32, batch1,
   inference mode, parent-approved allocator fraction (existing precedent .4),
   three warmups outside scored rows. Check/yield to demo health before work;
   fail closed on unavailable health, long busy state or OOM. Synchronize around
   timed regions and before yielding; no retries with a larger cap. Never start,
   stop or reconfigure the live service. A health gate is best-effort cooperation,
   not an exclusive lock or proof of no demo interference.
4. **Measure after smoke:** sequential candidates, balanced/counterbalanced order,
   three short repeat passes on the same original endpoints; then paired variants.
   Separate cold load/warmup from steady-state timing. Reset peak statistics only
   at the declared phase boundary. If measuring shared-demo coexistence later,
   report it as a separate experiment; do not mix busy GPU runs into a supposedly
   isolated architecture table.
5. **Report complete cells or explicit failures:** write partial progress with
   an incomplete status, then a new completed result only when every required
   input/candidate cell is accounted for. No live-model promotion is automatic.
   A diagnostic gain permits further evaluation, not a crowd/night production claim.

Required measurements: adapter-only preprocessing/H2D/forward/D2H p50/p95/p99 and
sample count, decode and queue/wait times separately, end-to-end source-to-review
wall delay, deadline misses, throughput under a specified schedule, actual clock
coverage, and suppressed/dropped regions. Report real-time factor rather than
calling reciprocal classifier latency camera FPS. A 400-ms policy offers at most
2.5 predictions/s/camera before additional regions; K independently scored regions
multiply calls by K. Warmup needs observed context before that cadence is possible.

Memory: loaded-model baseline, current/peak Torch allocated **and reserved** bytes,
allocator cap, per-process CPU RSS/decoded-buffer peak, and device/process-total
VRAM from an explicitly named external measurement where available. Torch allocator
statistics exclude the driver, video decode, ONNX sessions and the live process.
Log sampling frequency; short device-total peaks can be missed. Include hardware,
Torch/CUDA/cuDNN/driver versions, decoder/encoder backend, thread count, precision,
power/clock state if measurable, and OOM/health-yield counts. The historical small
X3D/MC3 peaks make single-model batch-one fit plausible on 6GB and already observed
in that older run, but do not reserve capacity for current coexistence or crowd ROIs.

## Recommended behavior tests, not implementation-mirroring tests

Existing test sources were read/AST-parsed, **not executed**: four tests in
`test_benchmark_fight_models.py`, five in `test_compare_x3d_training.py`, fourteen
in `test_fight_demo.py`, and two in `test_regions.py` (function counts before
parametrization). Current patterns cover strict threshold/cooldown duplicates,
hash failure before decoding/loading, crop separation, report/artifact mismatch,
mock score comparison, malformed WebM nominal FPS, clock rejection and ROI geometry.

Add only tests needed by the proposed general adapter/runner:

- Golden synthetic color/ramp/time-index tensors for each checkpoint's real
  preprocessing, edge-of-frame crop behavior, class order, logits-vs-probability
  mapping and exactly-once activation. Test numerical mechanics, not whether an
  arbitrary synthetic image is semantically a fight.
- Clock/state tests: NaN/duplicate/backward PTS, >1200-ms gaps, dimension/stream
  resets, insufficient span/short clips, valid source endpoints, decoder release
  and exact paired row keys across adapters/variants. No hidden padding/resizing.
- Safety/device tests: wrong bytes/permissions/schema/class mapping fail before
  construction; CPU selection must not invoke CUDA; unsafe checkpoint objects
  fail without an unrestricted fallback; incomplete runs cannot masquerade as
  complete. Test capped/yielded failures using mocks, without GPU CI jobs.
- Variant tests: native versus derived dimensions and lineage, aspect ratio,
  stable PTS-to-label mapping, no parent split leakage, no synthetic IR/thermal
  relabeling, and explicit status when codec support is missing.
- Policy tests: threshold tie, cooldown boundary, duplicate-vs-normal unmatched
  classification, event overlap/late tolerance, in-progress onset exclusions,
  close/simultaneous episode ambiguity. Preserve the old matcher as a named mode.
- Later scheduler tests with mocked 50/100 detections: cap/exclusion/drop counters,
  bounded queues/RAM, region coverage/staleness and overdue-region behavior. These
  are load/control tests; real crowd/night accuracy still needs licensed footage.

## Audit reproducibility and limits

Local source SHA-256 at inspection:

| File | SHA-256 |
| --- | --- |
| `PROTOCOL.md` | `10e406f8487cdc4ed9fab22e0f98ba3f45e5f59497c8ac57aae6710174ca35b6` |
| `benchmark_fight_models.py` | `a751eb36a655ef0b8e1c675a9563aa7855b711d630919217993fd1bcaf88aaf6` |
| `compare_x3d_training.py` | `089d9aa554cb57db29c3bbffacb578c63312331f2a60f6d474eeb258f976dcb8` |
| `nivra/x3d_candidate.py` | `65798e408dbc85231b976187401850a9909eb899235f0eea7f5f4ac09fdabee4` |
| `evaluate.py` | `6abd7bf3aeeddf9db6bc507c26bb3b206a547b8a12000fb9da61ad1f356f9772` |
| `nivra/fight_demo.py` | `d923b2c8403c96af25d35bf89090f85da83932ae0f4dee8313205202a3d0e331` |
| `nivra/pipeline.py` | `58171ec4ac20bf9d306ff91a1d4961bfd47bd363c83adeb39aa6502dbe33c588` |
| `nivra/regions.py` | `dec4eca701d75fe344d3163cdb8fd2a289dc93bc970deb4c670b1932082cd14b` |

Small remote files were fetched as text/JSON only. Example source SHA-256:
MC3 utility `c484e756eba8d5c61e168839086eefe948ebd834ae15ef1d4acd625efdbc2817`;
FGN network notebook `b9a005b92b838dfe430cc7a4615df3b371035980ae25274c6e98abc03b00548e`;
FGN preprocessing notebook `3c6fb61de03da6300881b18a4b51acced433d9adb3cf42b22615336829ec0847`;
pinned HF X3D wrapper `69b3a9f9c3ea7267fda51d9589d59f68e75d650b80973eb29440c54a676e8b48`.
Repository-head and HF asset metadata were read via public APIs. Later framework
tag-to-commit API lookups hit GitHub's unauthenticated rate limit; no framework
commit SHA was invented. Installed package versions are independently reported
above. No checkpoint was downloaded, deserialized or run in this task; no footage
was visually reviewed and no new labels were produced.

## Final shortlist, blockers and unverified claims

| Slot | Runnable assets / Windows GTX1660Ti 6GB expectation | Current blocker / decision |
| --- | --- | --- |
| Community X3D-M control | Exact local 12.27-MB asset/hash, 16x224 RGB, class1 probability; existing Torch/PyTorchVideo stack. Batch-one GPU fit was observed historically. | Preserve >.5 backbone score and live model. No new accuracy or crowd/night evidence; publisher MIT/noncommercial wording remains unresolved. |
| MohamedSebaie MC3-18 control | Exact local 46.04-MB asset/hash, 16x112 RGB center crop, class0 softmax; installed torchvision. Batch-one fit/faster historical inference observed. | Already failed to improve event matching and added a shadowboxing alert. Do not promote from speed; map edge/crop misses and uncertainty. |
| Third GitHub slot: official Flow-Gated Network, or a better release nominated by the other research chats | FGN commit/file/blob and source input64x224x224x5 known, but byte SHA, model config, label lineage and safe loader are unverified. Its input alone is about 61.25 MiB FP32; file size is not a working-set estimate. | FGN is **blocked**, not runnable in this native venv: legacy TF/Keras, Lambda serialization, mapping/normalization and permissions unresolved. A different third candidate must satisfy the same admission gate; no runtime/package changes are authorized here. |

Still empirically unverified: any new candidate's improvement over X3D; genuine
near-IR and low-light-color detection; native 1080p/720p and compressed/degraded
480p performance; fights among 50-100 visible people; far-field/occluded interaction
localization; unknown/normal-time false-alert rate per camera-hour; independent
event recall/onset delay; sustained camera/region capacity; current demo coexistence,
GPU/CPU memory peaks and tail latency. Synthetic transformations and repeated
development diagnostics cannot establish those claims. The next authorized parent
action is to freeze admitted assets/policy, implement isolated adapters/runner
changes, and schedule CPU smoke before one-at-a-time GPU comparison; it is not
another training run or automatic live replacement.
