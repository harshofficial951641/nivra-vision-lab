# Parent candidate decisions

21 October 2026. Interim decisions as independent audits arrive. No new model
has been selected or promoted. Read the linked audits for pinned source evidence.

## 3D-CNN / motion-stream audit

Source: [3d-cnn-repos.md](3d-cnn-repos.md).

| Candidate | Parent disposition | Reason / next gate |
|---|---|---|
| Existing MC3-18 | Retain comparison control | Already runnable locally; previous diagnostics did not beat X3D-M |
| Original Flow Gated Network | Defer adapter implementation | Released H5 contains serialized Lambdas; exact checkpoint class metadata/training lineage and model terms are unresolved. Requires safe explicit graph reconstruction and strict numeric-weight mapping |
| Fightdet gray + optical flow | Defer adapter implementation | Released legacy SavedModel, no verified model/code permission grant; runtime/signature equivalence untested. Native Windows GPU runtime compatibility requires separate work |
| VIGIl | Exclude from immediate model comparison | Inspected release lacks the required classifier checkpoint |
| Hepta-Col VideoFightDetection | Exclude from immediate implementation comparison | Inspected release is a dataset/code-forthcoming README, not released inference software |
| cvidgi baseline | Engineering reference only | Checkpoint absent from inspected release; useful evaluation structure does not establish model improvement |
| tiao lightweight pipeline | Conditional research lead | Backbone/head matching and class mapping need strict verification; not a conventional 3D CNN |

The motion-stream candidates are worth investigating as hypotheses, but neither
is the first implementation priority while safer, compatible checkpoint audits
are still pending. Do not install TensorFlow into the live PyTorch environment
or port a legacy model solely because its weights exist. A PyTorch port would
need numerical parity evidence before a quality comparison could be interpreted.

## Real night / crowd evidence

Source: [night-crowd-evidence.md](night-crowd-evidence.md), with the ARID author's
dataset licence declaration independently rechecked by parent.

No reviewed source closes the complete crowd/night requirement. ARID is a
possible real low-light everyday-action probe, not fight-recall evidence or a
native-HD source. TNO is a possible near-IR domain reference, not an established
temporal fight benchmark. No additional dataset import has been selected.

## First transformer staged: cliffer1 VideoMAE-Base

Source: [transformer-repos.md](transformer-repos.md). Parent selected this for
an offline development comparison, not adoption or public redistribution.
Exact revision: `613844b1d2d27f68944619bf91885a9befb101ac`.

Parent downloaded only the pinned card, config, processor and safetensors with
`../stage_videomae.py`. All four complete-file SHA-256 values matched the audit;
checkpoint bytes were independently verified at 344,937,328 bytes. Staging
receipt and assets remain in ignored `../cache/cliffer1-videomae/`.

An isolated research environment has Transformers 4.57.1 and safetensors 0.6.2;
its own site-packages contains a path reference to the existing service runtime
for Torch/OpenCV, without installing or changing packages in that runtime.
Resolved package versions are frozen in the ignored environment. Reproduction
therefore also depends on the existing service environment; this is not a fully
self-contained redistributable environment.

**CPU smoke passed:** local-only safetensors load, remote custom code disabled,
zero missing/unexpected/mismatched keys or loader errors, explicit labels
0=NonViolence / 1=Violence. Sixteen synthetic black RGB frames produced finite
two-logit output from input `[1,16,3,224,224]`. Load/preprocess/forward wall time
was 7.269 seconds with two CPU threads; this is not an inference latency
benchmark. No CUDA model run occurred. Receipt:
`../runs/cliffer1-cpu-smoke-v1.json` (ignored).

This proves basic local execution only. It provides no fight-quality, crowd,
night or performance evidence. Checkpoint card is CC-BY-NC-4.0; training footage
and author trainer/split provenance remain unknown. No live promotion or broad
use clearance follows. Next: bounded offline adapter and paired source-resolution
diagnostic runner, then parent-coordinated actual GPU comparison.

## Adapter integration check

Parent inspected `nivra/videomae_candidate.py` and reproduced its stub/unit suite:
72 passed, one Windows symlink-permission skip. The first test invocation from
the repository root lacked the service import path; rerunning from the documented
`service` working directory passed. No implementation change was needed.

The actual adapter then passed a CPU inference on a checksum-verified native
1920x1080 shadowboxing source window. Thirty source-resolution gate samples span
0-3822 ms; actual PTS were strictly increasing, and the saved processor received
the adapter's 16 uniform selections. All model-loading/config checks passed.
Its fight score was **0.5763841867**, which triggers the frozen strict >0.5 review
rule on this development-negative window. That is an early false-alert concern,
not an estimate of operational false-alert frequency or a complete ranking.
Single cold prediction took 5.113 seconds on two CPU threads, excluding load;
this is not GPU throughput. No GPU job or live change occurred.

Raw receipt: `../runs/cliffer1-adapter-cpu-window-v1.json` (ignored). The next
quality decision still requires every candidate on the same complete paired
diagnostic windows. Do not adjust thresholds based on this observation.

## End-to-end system audit disposition

Source: [cctv-system-repos.md](cctv-system-repos.md). Parent independently checked
the pinned SAF-DETR API: it explicitly assigns `violence_detected` from more
than two detections and permits random weights when a checkpoint is absent.
Exclude that release as a trained fight-model candidate. No attempt to make its
demo run is warranted for this comparison.

MMAction2 AVA is a localization engineering research path, requiring separate
checkpoint/runtime/proposal validation. SCVD's view-only terms prevent treating
it as reusable released software. CLIP is an image-semantic research control;
it is not a substitute for the selected temporal-classifier comparison, and its
card's deployment/surveillance suitability concerns remain recorded in the audit.
No extra model download has been selected from these systems.

Parent decoded source metadata independently: boxing is 1920x1080, kick
1280x720, grappling 880x608, and squats 720x1280 portrait. The WebM boxing/kick
nominal FPS values are malformed (30000/24000); use actual PTS. Thus some native
HD development material exists, but it remains few-person non-night footage.
Native resolution is not evidence of a crowded/night operating condition.

## Actual paired GPU decision

All three candidates completed **67 identical native-geometry windows**, with
matching corpus/policy/paired-window hashes. X3D flagged 0/12 shadowboxing
windows, MC3 12/12, VideoMAE 9/12. Both alternatives flagged more grappling
windows, but neither met the frozen no-extra-false-alert criterion. Keep X3D-M.
VideoMAE median adapter cost was 625.6 ms versus X3D 86.7 ms and MC3 53.4 ms.
See [PAIRED-RESULTS.md](PAIRED-RESULTS.md) for full counts, caveats, raw report
hashes and actual CUDA memory measurements. Full service tests: 420 passed,
four skipped. No live change or operational accuracy claim.

Next own-model experiment will initialize from working community fight weights
rather than replacing their representation with a randomly initialized binary
head on generic Kinetics features. Settings must be fixed before diagnostics;
no threshold tuning or development-clip training. Pipeline crowd/night gaps
remain separate, unresolved requirements.

## Quality preparation follow-up

Parent reproduced 47 variant tests and verified the kick-smoke v2 complete corpus
hash. That smoke has 111 paired frames, 87 ms of explicitly unknown declared tail,
two 854x480 H.264 derivatives and an all-frame verified -3 ms FFmpeg-to-OpenCV
backend offset. No event times were moved; source/output OpenCV clocks agree.

Parent's full `cctv-quality-v1` run generated eight media variants but failed on
the final portrait squats source's unspecified sample aspect ratio. It published
no complete corpus. The failed receipt/partial files remain evidence. The helper
is fixing unknown-SAR handling without assuming square pixels, then will run a
new bounded CPU matrix. No model comparison uses those incomplete artifacts.

A separate offline tiled RTMO observer is assigned to the crowd helper. Its
intended cap is 100 returned anonymous observations with omission/view telemetry,
not a claim of detecting every visible person or assessing every fight. Existing
live ingress/person limits remain unchanged until separately integrated and
verified. No true crowd/night evidence has been added.

## Outstanding work

Crowd/pose pipeline changes, end-to-end CCTV systems, and diagnostic integration
remain under review. Reconcile those findings before selecting further assets.
Keep model
quality separate from useful pipeline engineering and from unsupported operating
conditions; preserve the live X3D-M throughout offline investigation.
