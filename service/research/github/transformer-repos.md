# Transformer repository and checkpoint audit

Research date: 21 October 2026. Scope: read-only primary-source inspection under [PROTOCOL.md](PROTOCOL.md). No model execution, GPU work, installation, service changes, complete checkpoint downloads, or external repository code execution occurred. Only this report was written.

## Decision

**Stage cliffer1 VideoMAE-Base as the simplest fully specified binary comparison; stage HappyGook VideoMAE-Base as a second, version-sensitive comparison. Neither is approved for live use or established as better than X3D-M.** Both have public safetensors and ordinary Transformers implementations. They are approximately 86M-parameter whole-clip classifiers, not small crowd-localization systems. Their rights/provenance gaps remain separate from their technical loadability.

The smaller KingTechnician release is **not a reproducible binary detector as published**: its “binary” card describes two classes, but the pinned config and actual safetensors header both contain seven outputs. Do not silently replace its head, override its labels, or report the card's binary metrics as this artifact's verified behavior.

No audited release establishes physical-fight detection for 50–100 visible people, genuine near-IR CCTV, low-light colour, or native 1080p/720p footage with degraded 480p copies. The existing few-person development diagnostics cannot establish these capabilities. Percentages from unrelated datasets were not used to rank candidates.

## What was actually inspected

- GitHub branch/HEAD pins through `git ls-remote`; pinned raw README, licence, architecture, preprocessing, dataset-loader and checkpoint-loading source where cited below. GitHub REST commit lookup hit an unauthenticated rate limit; Git refs supplied the revisions instead.
- Hugging Face model APIs, file inventories, pinned cards/configs/processors, advertised LFS SHA256 and byte lengths.
- HTTP `Range: bytes=0-65535` responses for HappyGook, cliffer1 and KingTechnician binary safetensors. Responses were HTTP 206; only 65,536 bytes per request were read, in memory. Headers were parsed as JSON, never deserialized as executable objects. HappyGook/cliffer1 were fetched twice for focused header checks. **Checkpoint SHA256 values below are publisher/LFS metadata, not independent hashes of complete downloaded weights.** No complete model was downloaded.
- Installed package metadata only: Python environment has torch `2.5.1+cu124`, torchvision `0.20.1+cu124`, OpenCV `4.11.0.86`; `transformers`, `safetensors` and `huggingface_hub` are absent. No imports of those candidate libraries or changes to the environment were made. Inference recipes therefore remain unexecuted.
- Dataset-author Zenodo metadata and the Bus Violence paper. No video footage was downloaded or visually reviewed in this research task.

## 1. Official MCG-NJU foundations

### VideoMAE: useful training foundation, not a fight detector

GitHub pin: [`14ef8d856287c94ef1f985fe30f958eb4ec2c55d`](https://github.com/MCG-NJU/VideoMAE/tree/14ef8d856287c94ef1f985fe30f958eb4ec2c55d).

The [model zoo](https://github.com/MCG-NJU/VideoMAE/blob/14ef8d856287c94ef1f985fe30f958eb4ec2c55d/MODEL_ZOO.md) supplies Kinetics/SSv2/UCF101 pretraining and action-classification assets, including ViT-S. These are generic action/pretraining checkpoints. Wrestling/boxing classes do not turn a Kinetics model into a binary unarmed-fight detector. The zoo's multiple temporal clips and spatial crops also cost more than one forward pass.

The official HF small Kinetics model is pinned at [`1bf2b82c809609f5df1ea7648aee577e2e486b63`](https://huggingface.co/MCG-NJU/videomae-small-finetuned-kinetics/tree/1bf2b82c809609f5df1ea7648aee577e2e486b63). Its [config](https://huggingface.co/MCG-NJU/videomae-small-finetuned-kinetics/blob/1bf2b82c809609f5df1ea7648aee577e2e486b63/config.json) specifies 384 hidden dimensions, 12 layers, 16 attention heads, 16 frames, 224 pixels, mean pooling and 400 outputs. Its inventory exposes `pytorch_model.bin` (88,197,173 bytes; advertised SHA256 `d69585904fec7e507bf2edfba4a7abe2b92def9afc76460d1dc14dbbf864bcfc`), not a safetensors release. Do not substitute the original GitHub ViT-S head count of six for the HF config's sixteen; the implementation/config differences require an explicit conversion audit.

The [licence](https://github.com/MCG-NJU/VideoMAE/blob/14ef8d856287c94ef1f985fe30f958eb4ec2c55d/LICENSE) is CC-BY-NC-4.0 for the majority of the project, with separately licensed upstream portions identified in the README. HF base/small model cards likewise carry CC-BY-NC-4.0. Kinetics/SSv2/UCF footage rights are separate and were not cleared here. Original [installation instructions](https://github.com/MCG-NJU/VideoMAE/blob/14ef8d856287c94ef1f985fe30f958eb4ec2c55d/INSTALL.md) describe older torch/timm/decord/DeepSpeed environments and A100/V100 experiments, not a verified Windows 6GB deployment. Original `.pth` loading needs review and explicit `weights_only=True` if any such asset is staged.

### VideoMAE-Action-Detection: person-conditioned action scores, greater integration work

GitHub pin: [`15615dbcf365fc45a3230446833c3f4183eb7f41`](https://github.com/MCG-NJU/VideoMAE-Action-Detection/tree/15615dbcf365fc45a3230446833c3f4183eb7f41).

The [zoo](https://github.com/MCG-NJU/VideoMAE-Action-Detection/blob/15615dbcf365fc45a3230446833c3f4183eb7f41/MODEL_ZOO.md) has an AVA ViT-S checkpoint after K400 pretraining+finetuning: [Drive asset `1b9Lp64IF8vjhh19mjDdyoSSiZk6cFfKb`](https://drive.google.com/file/d/1b9Lp64IF8vjhh19mjDdyoSSiZk6cFfKb/view). The reference [script](https://github.com/MCG-NJU/VideoMAE-Action-Detection/blob/15615dbcf365fc45a3230446833c3f4183eb7f41/scripts/ava/videomae_vit_small_k400_pretrain%2Bfinetune/run.sh) identifies the architecture and 16×4 frame sampling. The Drive checkpoint was not downloaded; byte hash, tensor layout and safe-load compatibility are unverified. No pinned safetensors equivalent was established.

Actual [architecture source](https://github.com/MCG-NJU/VideoMAE-Action-Detection/blob/15615dbcf365fc45a3230446833c3f4183eb7f41/modeling_finetune.py#L183) takes supplied person boxes, ROI-pools shared video features, and produces **80 AVA logits per proposal**. [Evaluation uses sigmoid](https://github.com/MCG-NJU/VideoMAE-Action-Detection/blob/15615dbcf365fc45a3230446833c3f4183eb7f41/engine_for_finetuning.py#L140), not a two-class softmax. The class vocabulary includes `fight/hit (a person)`, but a deployment must pin the actual AVA labelmap; [export adds one to output indices](https://github.com/MCG-NJU/VideoMAE-Action-Detection/blob/15615dbcf365fc45a3230446833c3f4183eb7f41/data/ava_eval.py#L64). Do not guess the fight tensor index. The external labelmap bytes were not fetched, so exact numeric mapping is a blocker.

[Preprocessing](https://github.com/MCG-NJU/VideoMAE-Action-Detection/blob/15615dbcf365fc45a3230446833c3f4183eb7f41/data/transforms.py) is 16 frames at stride four, test short side 256/max side 464, RGB (`TO_BGR=False`), mean `[122.7717,115.9465,102.9801]`, std `[57.375,57.375,57.375]`. This differs from the HF clip classifiers. The [validation loader](https://github.com/MCG-NJU/VideoMAE-Action-Detection/blob/15615dbcf365fc45a3230446833c3f4183eb7f41/datasets.py#L27) uses precomputed person detections with box threshold 0.8. No live detector/tracker is supplied by that evaluation path. The architecture's `proposal_per_clip=100` is a **training sampling cap**; evaluation extends and passes all supplied boxes. Neither this constant nor all-box forwarding proves coverage of 100 people.

ROIAlign's active [implementation](https://github.com/MCG-NJU/VideoMAE-Action-Detection/blob/15615dbcf365fc45a3230446833c3f4183eb7f41/alphaction/layers/roi_align_3d.py#L51) uses `torchvision.ops.roi_align`; the old custom CUDA call is commented out there. Avoid incorrectly treating that particular operator as a mandatory custom build. Other imports/dependencies still need a Windows smoke test. The [licence](https://github.com/MCG-NJU/VideoMAE-Action-Detection/blob/15615dbcf365fc45a3230446833c3f4183eb7f41/LICENSE) is CC-BY-NC-4.0; AVA movie footage, annotations, Kinetics weights and checkpoint terms remain separate. This is a localization research option, not the first quick binary comparison.

## 2. Runnable binary asset candidates

### A. cliffer1 VideoMAE-Base — first comparison on configuration completeness

- Model: `cliffer1/videomae-base-finetuned-kinetics-violence-nonviolence-tuned`.
- Full revision: [`613844b1d2d27f68944619bf91885a9befb101ac`](https://huggingface.co/cliffer1/videomae-base-finetuned-kinetics-violence-nonviolence-tuned/tree/613844b1d2d27f68944619bf91885a9befb101ac).
- [Weights](https://huggingface.co/cliffer1/videomae-base-finetuned-kinetics-violence-nonviolence-tuned/blob/613844b1d2d27f68944619bf91885a9befb101ac/model.safetensors): **344,937,328 bytes**, advertised SHA256 `5166b055ebee1439d6517c5bf2d516dce7a1f65afc53367f43b5848970853d53`; 86,228,738 F32 parameters per Hub metadata.
- [Config](https://huggingface.co/cliffer1/videomae-base-finetuned-kinetics-violence-nonviolence-tuned/blob/613844b1d2d27f68944619bf91885a9befb101ac/config.json): stock `VideoMAEForVideoClassification`, 768 hidden, 12 layers/heads, 16 frames, 224 pixels, tubelet 2, patch 16, **mean pooling**. Explicit class order **0 NonViolence, 1 Violence**; use `softmax(logits)[1]`. Header confirms a `[2,768]` classifier and older `q_bias`/`v_bias` attention layout.
- [Processor](https://huggingface.co/cliffer1/videomae-base-finetuned-kinetics-violence-nonviolence-tuned/blob/613844b1d2d27f68944619bf91885a9befb101ac/preprocessor_config.json): RGB uint8; resize shortest edge 224 with PIL bilinear (`resample=2`), centre crop 224×224, rescale 1/255, normalize mean `[.485,.456,.406]`/std `[.229,.224,.225]`.
- [Card](https://huggingface.co/cliffer1/videomae-base-finetuned-kinetics-violence-nonviolence-tuned/blob/613844b1d2d27f68944619bf91885a9befb101ac/README.md) names an **unknown dataset** and incomplete intended-use/data sections. Its accuracy has no demonstrated relation to NIVRA diagnostics, real IR, crowds or unseen-camera performance. Sampling cadence/training clip duration and split/actor lineage are unspecified.
- Checkpoint card: CC-BY-NC-4.0. Inference library: Apache-2.0 Transformers. Footage rights and training-code provenance: unresolved. No author training GitHub repository was established from the inspected card/inventory/searches. These omissions preclude treating technical loadability as production clearance.

### B. HappyGook VideoMAE-Base — second comparison, keep exact library generation

- Model: `HappyGook/videomae-violence-detector`.
- Full revision: [`975dadb8f6d7c5d3119ad40341c3622ee5f8ff43`](https://huggingface.co/HappyGook/videomae-violence-detector/tree/975dadb8f6d7c5d3119ad40341c3622ee5f8ff43).
- [Weights](https://huggingface.co/HappyGook/videomae-violence-detector/blob/975dadb8f6d7c5d3119ad40341c3622ee5f8ff43/model.safetensors): **344,975,792 bytes**, advertised SHA256 `d849b28ae5cc6be46c25f51de62a837410111ecee6f1f7e44e9f7a4ce5c863ec`; 86,237,954 F32 parameters.
- [Config](https://huggingface.co/HappyGook/videomae-violence-detector/blob/975dadb8f6d7c5d3119ad40341c3622ee5f8ff43/config.json): same base geometry as A, but **`use_mean_pooling=false`**, Transformers **5.8.1**. It omits `id2label`/`label2id`; the [author example](https://huggingface.co/HappyGook/videomae-violence-detector/blob/975dadb8f6d7c5d3119ad40341c3622ee5f8ff43/README.md) assigns **0 Non-Violent, 1 Violent**. Preserve this as author-documented mapping, not a tensor-derived semantic verification. Header independently confirms `[2,768]` head shape only.
- [Processor](https://huggingface.co/HappyGook/videomae-violence-detector/blob/975dadb8f6d7c5d3119ad40341c3622ee5f8ff43/preprocessor_config.json) has the same RGB/resize/crop/normalization as A. Card uniformly samples 16 indices over the **entire input video**, not a specified real-time duration. Feeding a four-second window is an explicit NIVRA comparison policy, not a reproduction of a documented four-second training cadence.
- Header contains learned `query.bias`, **`key.bias`** and `value.bias` in every attention layer. This matches inspected [Transformers 5.8.1 source](https://github.com/huggingface/transformers/blob/cc832f9055ba11c8c55f918ab4bda9472b910d48/src/transformers/models/videomae/modeling_videomae.py#L225). [4.57.1 source](https://github.com/huggingface/transformers/blob/8cb5963cc22174954e7dca2c0a3320b7dc2f4edc/src/transformers/models/videomae/modeling_videomae.py#L228) instead defines bias-free projections plus `q_bias`/`v_bias` and a fixed zero key bias. Do not load into 4.x and ignore warnings, discard key biases, or randomly initialize replacement parameters. First use 5.8.1 and require clean loading information.
- Do not override pooling to match another candidate: B's header has final `videomae.layernorm` parameters and no `fc_norm`; A has `fc_norm`. Standard no-mean-pooling inference selects the first encoded patch token. Changing this to mean pooling changes both parameter expectations and the classifier's input representation. Shape `[2,768]` does not prove class meanings; B's positive index still rests on the author example.
- Author lineage: MCG-NJU base → [`Nikeytas/videomae-crime-detector-production-v1`, revision `1df9b5c2e097829d8ef0c2c92677663f7b11c7f1`](https://huggingface.co/Nikeytas/videomae-crime-detector-production-v1/tree/1df9b5c2e097829d8ef0c2c92677663f7b11c7f1) on a UCF-Crime subset → Bus Violence finetune. Five-file HappyGook inventory contains no trainer script/notebook or custom Python modules. Searches did not establish an author training GitHub repository. The card's quick-start still uses `<your-repo-id>` placeholders; replace with the pinned local artifact, not an unpinned pipeline.
- Rights are **not uniformly MIT**: HappyGook/Nikeytas cards tag their checkpoints MIT; upstream MCG-NJU base is CC-BY-NC-4.0; UCF mirror's [card](https://huggingface.co/datasets/jinmang2/ucf_crime/blob/main/README.md) tags CC0 without establishing authority over original footage. The original UCF site could not be retrieved reliably (TLS verification failure locally; web fetch timed out); original footage permissions remain unverified.
- Bus Violence has a direct conflict: [Zenodo record/API](https://zenodo.org/records/7044203) structured metadata says CC-BY-4.0, while the same record's prose specifies attribution **for non-commercial use**. Record the conflict and retain a rights blocker; a downstream MIT tag does not resolve it.

The [Bus Violence paper](https://www.mdpi.com/1424-8220/22/21/8345) describes daytime recordings, ten actors, H.264/25fps, three cameras at 1280×960, 960×540 and 352×288, and 16–48-frame clips. It includes equipment-directed and object-taking actions beyond person-to-person fights. Thus this lineage establishes neither native 1080p/720p coverage, night/near-IR validation nor a precise NIVRA label match. The Zenodo summary omits the lowest-resolution camera; use the paper's more detailed camera account. HappyGook's claimed test split cannot be audited for actor/session/camera independence without its split lists and trainer code.

## 3. Smaller/alternative releases searched

| Candidate and pinned source | Actual released asset / finding | Disposition |
|---|---|---|
| [KingTechnician “binary” `856471799671b5f15889703a910a078f40b3d231`](https://huggingface.co/KingTechnician/videomae-small-finetuned-kinetics-xd-violence-binary/tree/856471799671b5f15889703a910a078f40b3d231) | 87,552,636-byte safetensors; advertised SHA256 `d3f424464a53ce5f37a48861b4197f89b88e8f7a9a9215d5b28c2be39b021e11`; 21,882,631 parameters. Config **and header**: seven logits `[7,384]`, labels `0:A,1:B1,2:B2,3:B4,4:B5,5:B6,6:G`; 16 heads, 12 layers, mean pooling. No processor file; card says direct resize 224×224, 16 frames, 2.133333s but omits normalization/interpolation. CC-BY-NC-4.0; dataset described as unknown. | **Blocked**: contradicts binary card; no verified seven-code-to-fight mapping or complete preprocessing. Do not sum all non-A scores into “fight.” |
| [KingTechnician multilabel `54875f0b60e8acad7f1f8934e3f20ca6118f5b36`](https://huggingface.co/KingTechnician/videomae-small-finetuned-kinetics-finetuned-xd-violence-multilabel/tree/54875f0b60e8acad7f1f8934e3f20ca6118f5b36) | Config lists the same seven codes, `multi_label_classification`; 87,552,636-byte safetensors, advertised SHA256 `a2a45601c62a1d55a917fa39dae8330e914676f884694afb1d960271a581be96`. No processor; unknown dataset and incomplete card. | Not a drop-in binary detector. Semantics/preprocessing/rights need resolution. |
| [KingTechnician third variant `f3681cd1d07c8ca4888a5c1d87c3a96c50e261cc`](https://huggingface.co/KingTechnician/videomae-small-finetuned-kinetics-finetuned-xd-violence/tree/f3681cd1d07c8ca4888a5c1d87c3a96c50e261cc) | Same seven-class config; 87,552,636-byte safetensors, advertised SHA256 `a4346a7537ab329956b3e441789da6acd8036498aecff87245ad6a0cbf8fcbc0`; no processor. | Does not repair the binary release problem. |
| [Oanhha9898 `53a806f4243724e3297974c9a33c8e552a8f24dd`](https://huggingface.co/Oanhha9898/videomae-base-finetuned-fight-dataset/tree/53a806f4243724e3297974c9a33c8e552a8f24dd) | Base-sized safetensors 344,937,368 bytes; SHA256 `2dd4dd38989bd736802578a6409dacf33ad3addc545497055ea67ef1c0645887`. Explicit **0 fight, 1 nofight**, standard 16×224 processor, no mean pooling. CC-BY-NC-4.0; card says unknown dataset, no training-code provenance. | Possible reserve; positive index is **0**, unlike A/B. No size or provenance advantage over A. |
| [archit11 `9d91868d20674ad4ca0bcb8abadc5904b63229e2`](https://huggingface.co/archit11/videomae-base-finetuned-fight-nofight/tree/9d91868d20674ad4ca0bcb8abadc5904b63229e2) | Base safetensors 344,937,368 bytes; SHA256 `25ffa88dcc22f8de83bbdf8e33d217cd306d05c53a2079b5eacff58113c753fc`; 0 Fight, 1 No Fight. Card names `Pinwheel/ActsOfAgression`, gives no licence and explicitly discourages expecting it to work. | Do not prioritize; rights and release quality insufficient. |
| `mitegvg/videomae-small-ssv2-binary-finetuned-xd-violence` | Search index advertises an 87.5MB safetensors release, but live unauthenticated Hub API returned 401. | Current availability/pin/config not verified; stale search results are not a usable asset. |

Additional GitHub code inspected:

- [`riham-esi/Violence-Detection-video` at `ed81b8c9e1be4b18d262a474b73521516dea7513`](https://github.com/riham-esi/Violence-Detection-video/tree/ed81b8c9e1be4b18d262a474b73521516dea7513): MIT code, R3D-18 plus two-layer temporal Transformer and attention pooling. [Actual model source](https://github.com/riham-esi/Violence-Detection-video/blob/ed81b8c9e1be4b18d262a474b73521516dea7513/models/model.py) retains temporal backbone features; the README's repeated-feature description is stale relative to this source. [Loader](https://github.com/riham-esi/Violence-Detection-video/blob/ed81b8c9e1be4b18d262a474b73521516dea7513/src/load_model.py) uses unqualified `torch.load`; constructor requests pretrained R3D weights. Do not run it as-is: initialization may download a second checkpoint, release/code compatibility is untested, and the `.pth` checkpoint terms/bytes were not independently audited. Config is 16 frames, direct 224-square resize, ImageNet normalization; the decoder repeats last frames on failure, which must be surfaced as degraded input rather than hidden. Code licence does not establish Kaggle training-footage or model rights. No reason established to prioritize it over the safetensors candidates.
- [`lourencodebonnet/spatiotemporal-violence-detection` at `dcb068101a011049b321db25cff78a8e8bf772b1`](https://github.com/lourencodebonnet/spatiotemporal-violence-detection/tree/dcb068101a011049b321db25cff78a8e8bf772b1): ResNet50 plus lightweight temporal Transformer. Pinned README explicitly says **no open-source licence assigned**. Do not reuse code/materials; no author contact authorized. Its own cross-dataset discussion reports reduced transfer, not evidence for NIVRA's setting.
- [`facebookresearch/TimeSformer` at `a5ef29a7b7264baff199a30b3306ac27de901133`](https://github.com/facebookresearch/TimeSformer/tree/a5ef29a7b7264baff199a30b3306ac27de901133): official generic K400/K600/SSv2/HowTo100M action models, CC-BY-NC-4.0 majority code, `.pyth` weights. No released fight-specific safe checkpoint established in this audit. Higher-resolution/long versions add memory demand; do not treat general action scores as binary fights.

This was a bounded release audit and model search, not proof that no other small usable classifier exists.

## 4. Reproducible staging and safe loading, for parent execution only

Only stage `README.md`, `config.json`, `preprocessor_config.json`, `model.safetensors` from the **exact HF revisions above**. Parent handles full weight downloads and independent SHA256 verification in ignored storage. Do not fetch or deserialize `training_args.bin`, optimizer files, repo Python, or pickle fallback weights. No `trust_remote_code=True` is necessary.

Library source pins inspected:

- Transformers **4.57.1**, commit [`8cb5963cc22174954e7dca2c0a3320b7dc2f4edc`](https://github.com/huggingface/transformers/tree/8cb5963cc22174954e7dca2c0a3320b7dc2f4edc), for candidate A's original attention layout. The Git tag is annotated; this is its dereferenced commit, not the tag-object hash. Apache-2.0; setup declares Python >=3.9, torch >=2.2, safetensors >=0.4.3.
- Transformers **5.8.1**, commit [`cc832f9055ba11c8c55f918ab4bda9472b910d48`](https://github.com/huggingface/transformers/tree/cc832f9055ba11c8c55f918ab4bda9472b910d48), for B. Apache-2.0; inspected setup declares torch >=2.4 and safetensors >=0.4.3. Python/dependency resolution still needs an isolated environment check.

Do not modify the live environment to try either. The installed torch version meets those declared lower bounds, but **actual import/load/inference compatibility is untested**. Parent should record a resolved dependency lock and Windows smoke test in a separate environment before a GPU slot is used.

Minimal CPU loading check below is a specification, **not executed in this task**. Use the matching library generation and an already downloaded local snapshot. Fail on any key mismatch; never use `ignore_mismatched_sizes=True` to make a candidate appear runnable.

```python
from pathlib import Path
import torch
from transformers import VideoMAEImageProcessor, VideoMAEForVideoClassification

snapshot = Path(r"PARENT_SUPPLIED_VERIFIED_LOCAL_SNAPSHOT")
processor = VideoMAEImageProcessor.from_pretrained(
    snapshot, local_files_only=True, trust_remote_code=False
)
model, info = VideoMAEForVideoClassification.from_pretrained(
    snapshot, local_files_only=True, trust_remote_code=False,
    use_safetensors=True, weights_only=True,
    attn_implementation="eager", output_loading_info=True,
)
for key in ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs"):
    if info.get(key):
        raise RuntimeError((key, info[key]))
assert model.config.num_frames == 16 and model.config.num_labels == 2
assert tuple(model.classifier.weight.shape) == (2, 768)
model = model.float().cpu().eval()

# Parent supplies exactly 16 successfully decoded RGB uint8 HWC arrays.
# Do not call this with BGR, already normalized images, or an unknown tail.
def score_rgb_frames(frames):
    assert len(frames) == 16
    batch = processor(list(frames), return_tensors="pt")
    assert tuple(batch.pixel_values.shape) == (1, 16, 3, 224, 224)
    with torch.inference_mode():
        logits = model(**batch).logits
    assert tuple(logits.shape) == (1, 2) and torch.isfinite(logits).all()
    return logits.softmax(-1)[0].tolist()  # A/B positive index 1
```

Small-file hashes independently computed from pinned metadata fetches:

| File | HappyGook SHA256 | cliffer1 SHA256 |
|---|---|---|
| `config.json` | `9a7522263dbabc7b3c286d3ab4834c8804aff99a0f688cc4217a588449f8b6b7` | `59e7a7ba3196e7d7272304b16dc59e15b09b9f17832d76e8cbd9755487afa8ed` |
| `preprocessor_config.json` | `4bc9b255ff212041bc28127d4fa0ae1630abca52bb2d882f3e4c0b9e5b763f06` | `4bc9b255ff212041bc28127d4fa0ae1630abca52bb2d882f3e4c0b9e5b763f06` |
| `README.md` | `ff328472f18188da87a25d17e3fde27fde18337876f4db2ed4d82464bb75f419` | `0d2adb5b283c3c4bd8fd087d5ce85d0c2a6528c7ca6cc6ff65da51645452614f` |

Comparison policy proposal, to freeze before parent runs: use identical source-time four-second windows, uniformly sample 16 decoded source frames per window, record actual timestamps, and reject incomplete decode. Preserve each asset's saved spatial processor. For A, duration is an unspecified training-preprocessing parameter; for B, uniform whole-input sampling is documented, but four-second input duration is still our policy. Fix the threshold/aggregation rule before diagnostic scoring; retain raw logits, probabilities and event-time matches. A `>.5` positive softmax is a transparent initial policy, **not calibrated cross-model equivalence**. Do not optimize it on diagnostics and call the result unseen testing.

## 5. GTX 1660 Ti 6GB and required-condition assessment

**Engineering estimate, not measured:** a single batch-one 16×224 VideoMAE-Base FP32 inference is plausibly feasible within a dedicated 6GB card. F32 weights are about 345MB; activations, attention, decoder buffers and allocator overhead add substantially. Tokens are `(16/2)×(224/16)^2 = 1,568`; eager full attention scales quadratically in token count. A 21.9M small variant saves parameter memory but does not remove the 1,568-token attention cost. Do not infer FPS, peak VRAM or available headroom alongside the live X3D service from weight size. No CUDA, latency or memory benchmark was performed.

Native camera resolution is distinct from model input. These saved clip processors reduce to 224 and centre crop: on a 16:9 view only the central square survives, approximately **56.25% of original image width**. Small/edge interactions can disappear. This follows from processor geometry; it is not measured detection accuracy. Full-frame stretching, tiling or interaction crops change the inference policy and must be separately declared and compared; do not silently alter preprocessing to claim crowd coverage.

Neither A nor B detects people, tracks them, localizes interactions, schedules regions, records dropped regions or guarantees that 50–100 people's interactions are represented. An independent region pipeline could improve visibility but creates detector recall, occlusion, region-cap, overlap, compute and time-to-alert constraints. Measure these separately from scene-level alerts. AVA's supplied-box model offers an architectural localization route, but its proposal source, thresholded box recall and Windows/checkpoint integration remain blockers.

For every real evaluation source, record native dimensions, codec/bitrate or compression evidence, fps, crowd size, person pixel heights, occlusion and camera domain. Evaluate native 1080p and 720p where genuinely available; generate explicit 480p derivatives and keep lineage. Upscaling is not native evidence. Real low-light colour and real near-IR/monochrome CCTV require separate licensed recordings and condition-specific results. Grayscale/darkened daylight is only synthetic sensitivity analysis; thermal long-wave IR is another domain. No audited card/release validates these NIVRA operating conditions.

## Final shortlist, blockers and claims still unverified

1. **First technical comparison: cliffer1 pinned binary VideoMAE-Base.** Complete local safe-load asset set and explicit labels. Blockers: unknown training dataset/rights, missing temporal training policy, absent author trainer/split evidence, missing isolated dependencies and all empirical checks.
2. **Second technical comparison: HappyGook pinned VideoMAE-Base with Transformers 5.8.1.** Safe-format two-logit asset with a saved processor and author-documented labels. Blockers: clean loading not yet tested; class semantics only author asserted; upstream/dataset licence conflicts; broad training labels; no trainer/split files; no genuine night/crowd validation.
3. **Localization research reserve: official AVA ViT-S.** Needs labelmap bytes/index verification, person detection integration, checkpoint hashing/safe conversion and Windows validation before a fair run. **Training foundation reserve:** official VideoMAE-S; no fight capability should be assigned to its generic pretrain/action head.
4. **Do not run KingTechnician “binary” as a binary detector** until release semantics and preprocessing are resolved. Other inspected community releases do not supply a demonstrated smaller, cleaner alternative.

Still unverified: complete checkpoint byte hashes; clean CPU load and Windows numerical outputs; GPU fit/latency/peak VRAM; matches/misses/false alerts versus the live X3D-M on fixed diagnostics; performance on an independent licensed holdout; wrestling/occluded-contact transfer; 50–100-person coverage/localization and alert delay under load; native-resolution/compressed-camera robustness; genuine near-IR and low-light colour performance; calibration; actor/session split independence; commercial/public redistribution permissions. **No winner, live promotion, accuracy improvement or crowd/night readiness is claimed.**
