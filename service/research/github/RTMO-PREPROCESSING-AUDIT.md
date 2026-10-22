# RTMO static preprocessing and duplicate-policy audit

21 October 2026. **BGR, float32 NCHW, raw 0–255 pixel scale and padding value 114 agree with the released SDK metadata. Geometry does not match the pinned upstream Python reference: that reference uses a centered affine warp; the observer resizes and pads at the top-left. The local graph also embeds an NMS score threshold of 0.15, despite metadata describing 0.1.** These are static findings, not a measured explanation for the previous duplicate detections.

Only this new report was written. No model/session initialization, inference, GPU operation, package installation, source-code change, media decoding or live-service interaction was performed. The earlier eight-frame visual findings remain in [CROWD-OBSERVER-RESULTS.md](CROWD-OBSERVER-RESULTS.md); this audit does not claim a duplicate fix or improved detection.

## Inspected bytes and reproducible source pins

| Local artifact | SHA-256 |
|---|---|
| `service/models/rtmo_m.onnx` (89,269,977 bytes) | `750d872151ff4652f02c738efc3a547e112ce9b688fe920bc17f948e8c3afdac` |
| `service/models/rtmo-m-official.zip` | `6b9d3be1323cc030444f731bbe593ea61f59b9481e23da2f8b60cb4b72136e16` |
| [Manifest](../../model-manifest.json) | `23d73df69d131556c5105aecb9cfc0f05302be2d4846baf378742be179191170` |
| [Observer](../../nivra/crowd_observer.py) | `06b3ffd71dd7cd57941f1bce4f50f5e0fb52ee30fc1fe6cf626d7df941f3706d` |
| [CLI](../../research_crowd_observer.py) | `de146a85292202f57e622615ce46d02a0e149865eb87f3c7e23f372f1ffbb9ea` |

The [official archive URL](https://download.openmmlab.com/mmpose/v1/projects/rtmo/onnx_sdk/rtmo-m_16xb16-600e_body7-640x640-39e78cc4_20231211.zip) was not downloaded again. Its local `deploy.json`, `detail.json` and `pipeline.json` were read with Python's standard-library ZIP/JSON readers.

Two upstream source snapshots were inspected as text, never executed:

- MMPose `759b39c13fea6ba094afc1fa932f51dc1b11cbf9`: [body7 RTMO-M config](https://github.com/open-mmlab/mmpose/blob/759b39c13fea6ba094afc1fa932f51dc1b11cbf9/configs/body_2d_keypoint/rtmo/body7/rtmo-m_16xb16-600e_body7-640x640.py), [BottomupResize](https://github.com/open-mmlab/mmpose/blob/759b39c13fea6ba094afc1fa932f51dc1b11cbf9/mmpose/datasets/transforms/bottomup_transforms.py#L465-L611), [warp construction](https://github.com/open-mmlab/mmpose/blob/759b39c13fea6ba094afc1fa932f51dc1b11cbf9/mmpose/structures/bbox/transforms.py#L372-L424), [preprocessor](https://github.com/open-mmlab/mmpose/blob/759b39c13fea6ba094afc1fa932f51dc1b11cbf9/mmpose/models/data_preprocessors/data_preprocessor.py#L53-L105), [inverse mapping](https://github.com/open-mmlab/mmpose/blob/759b39c13fea6ba094afc1fa932f51dc1b11cbf9/mmpose/models/pose_estimators/bottomup.py#L168-L185).
- MMDeploy `3f8604bd72e8e15d06b2e0552fe2fdb8f8de33c4`: [RTMO export rewrite](https://github.com/open-mmlab/mmdeploy/blob/3f8604bd72e8e15d06b2e0552fe2fdb8f8de33c4/mmdeploy/codebase/mmpose/models/heads/rtmo_head.py#L44-L100), [backend inverse mapping](https://github.com/open-mmlab/mmdeploy/blob/3f8604bd72e8e15d06b2e0552fe2fdb8f8de33c4/mmdeploy/codebase/mmpose/deploy/pose_detection_model.py#L185-L223).

**Export provenance gap:** the archive reports MMPose 1.2.0 and MMDeploy 1.3.0, a checkpoint filename ending `39e78cc4_20231211.pth`, and a relative `../rtmpose_upload/` config path. It does not identify exporter Git commits or include that config's bytes. The actual MMPose v1.2.0 tree at `6d10b2ec81da7e252016b3154c7fdb46c403ecd8` has no RTMO paths; MMDeploy v1.3.0 at `1132e827d73b308f04c6d636298ff3a7094c585a` has no RTMO paths either. Recursive primary GitHub trees were checked. Thus the newer pinned sources above are inspectable reference implementations, **not a proven exact reproduction of the archive's exporter checkout**. The [v1.3.0 SDK-config builder](https://github.com/open-mmlab/mmdeploy/blob/1132e827d73b308f04c6d636298ff3a7094c585a/mmdeploy/codebase/mmpose/deploy/pose_detection.py#L32-L68) explains how normalization metadata is emitted, but does not close that gap.

## Local graph: what is actually inside

`onnx` is not installed in the existing environment. No installation or ORT runtime was used. A read-only inline Python wire-format reader inspected the checksum-pinned ModelProto's graph, ValueInfo, node inputs/outputs, attributes and small constant tensors; large tensor payloads were skipped for decoding. This is structural inspection, not `onnx.checker` validation or shape inference. The graph contains 796 nodes and 240 initializers, IR version 6, default-domain opset 11, producer `pytorch` version `1.12.1`.

| Item | Actual static evidence |
|---|---|
| Input | One `input`, TensorProto dtype 1 (FLOAT/float32), shape `['batch',3,640,640]`; spatial dimensions fixed, batch symbolic. Observer deliberately uses batch 1. |
| Outputs | FLOAT `dets`, rank 3, and FLOAT `keypoints`, rank 4. Non-batch dimensions in graph ValueInfo are symbolic, including joint count. Static output metadata alone does **not** prove 17 joints; the parent's separate 40-call smoke demonstrated 17 at runtime. |
| Input consumers | Only `Slice_16` and `Slice_21`, slicing spatial axis 2 with start 0/1 and step 2. Subsequent slices on axis 3 form four spatial phases. `Concat_24` combines them into `input.1`; `Conv_25` consumes that tensor and weights shaped `[48,12,3,3]`. |
| Explicit input normalization/channel processing | No Sub/Div/Mul normalization, channel reversal, resize or image padding occurs on any input-to-first-convolution branch. This spatial slicing is the Focus stem, not RGB conversion. Later feature-map Resize/Mul operations are not image preprocessing. Learned convolution weights could mathematically absorb a linear transform; graph structure alone cannot infer training colour semantics. The SDK/config evidence supplies those semantics. |
| Embedded NMS | `NonMaxSuppression_560` consumes `boxes`, `scores` and constants `onnx::NonMaxSuppression_1356/1357/1358`: max output/class **200**, IoU **0.6499999761581421**, score **0.15000000596046448**. |
| Final outputs | `Reshape_662` produces `dets`; `Concat_795` produces `keypoints`. TopK nodes also exist; this audit does not certify their full dynamic limit expressions from metadata alone. |

The archive's `detail.json` defaults are score .05, IoU .5, pre-top-K 2000 and keep-top-K 50; `pipeline.json` postprocess says score .1, NMS .65. **Neither substitutes for inspecting constants in this graph.** The pinned rewrite allows test-config overrides for thresholds and max-per-image. Do not describe lowering the observer's host threshold below .15 as recovering candidates already removed by embedded NMS. The host .1 check remains an additional filter, not the effective model's .1 detection threshold.

## Caller contract and geometry parity

The SDK pipeline explicitly lists `BottomupResize(input_size=[640,640], pad_val=[114,114,114])`, then `Normalize(mean=[0,0,0], std=[1,1,1], to_rgb=false)`, ImageToTensor, Collect. It declares a postprocess component named `UNKNOWN`. Consequently it is useful evidence of intended transforms, **not proof of a functioning end-to-end SDK postprocessor**.

The pinned RTMO config has mean 0/std 1, no BGR-to-RGB override, a validation BottomupResize and no flip-test pipeline. PoseDataPreprocessor defaults BGR-to-RGB to false. Those facts support retaining raw BGR values cast to float32; adding `/255`, ImageNet mean/std or RGB conversion would contradict the inspected contract. They do not establish pixel-level equivalence of different resamplers.

| Stage | Pinned Python reference | Current observer |
|---|---|---|
| Layout and colour | BGR to float32 NCHW, no scale normalization | Matches; [letterbox lines 76–87](../../nivra/crowd_observer.py#L76). |
| Resize | BottomupResize defaults `fit`, size factor 32, non-UDP. Builds centered affine matrix and calls `cv2.warpAffine(..., INTER_LINEAR)` | `cv2.resize` to integer-truncated dimensions, then copies at `(0,0)` into 640-square uint8 array. Both interpolate linearly, but coordinate conventions and truncation differ. |
| Padding | Value 114 around a centered fitted image | Value 114 only below/right. |
| Model coordinates | Padded 640-square input pixels | Same coordinate domain, but a different input image transform. |
| Inverse map | `p_source = p_model * input_scale/input_size + input_center - input_scale/2`, for boxes and joints | Divides by scalar ratio, clips to view, adds tile origin; normalized joints divide by full frame width/height; [lines 353–400](../../nivra/crowd_observer.py#L353). |
| Additional policy | Decode/NMS are in exported head; native clipping is caller-dependent | Score .1, minimum 8px box sides, clips boxes and joints, clears confidence outside view, host cross-view IoU .7 dedup. These are observer policies, not official recall guarantees. |

For a view of width `w`, height `h`, let `r=min(640/w,640/h)`. The centered affine reference is nominally `p_model=r*p_view+t`, where `t=((640-r*w)/2,(640-r*h)/2)`. Its inverse is `(p_model-t)/r`. This formula follows the inspected non-UDP square-fit implementation; exact input generation should use its matrix/warp operation, rather than assuming resize-plus-padding is pixel-identical. The observer instead uses `t=(0,0)` and integer-sized resize. For a 1920x1080 view, centered offset is `(0,140)` model pixels; for a 720x1280 view it is `(140,0)`. These are differences between the transforms, **not measured coordinate errors in the current output**.

Changing only inverse mapping would break the current top-left contract. A later isolated parity experiment must pair centered preprocessing with its exact inverse, preserve the old variant separately and compare generated input tensors before comparing model outputs. The previous aligned overlays demonstrate internal mapping consistency for the existing transform, not canonical upstream preprocessing parity. The live [Models.crowd_observations lines 66–77](../../nivra/models.py#L66) also uses top-left resize/padding; it was not changed.

## Bounded cached-output duplicate-policy options

These are proposals only. The earlier cache contains post-clipping, post-dedup retained outputs for eight frames, not every original tensor or suppressed candidate. It cannot reconstruct the complete pre-dedup set or restore confidence discarded outside a tile. Any replay must be marked **retained-cache association diagnostic**, with immutable input/report hashes and original indices retained, never called a full detector evaluation.

The two squat frames already show why IoU-only is insufficient: five observations correspond to one apparent exerciser; global-to-tile intersection/smaller-area is about .97–.99 while all pairwise IoUs remain below .7. Common high-confidence joints align closely. This motivates testing containment plus joints; it does not select production thresholds or establish a fix from eight frames.

| Option | Minimal bounded rule to investigate | Failure risk / disposition |
|---|---|---|
| A: conservative cross-view suppression | Preserve current IoU policy. For **different overlapping source views only**, additionally consider intersection/smaller-area >=.95, at least 6 corresponding joints with both confidences >=.5, at least two represented body regions, and median joint distance <=.03 of the larger box diagonal. Require >=80% of those joint distances <=.06 diagonal. Treat these as predeclared exploratory values, not tuned/validated constants. | Distinct people in close contact can have nearly identical boxes/joints or a pose attached to the wrong body. Retain both when evidence conflicts or is sparse. This rule deliberately leaves same-view duplicates unresolved. |
| B: association telemetry before suppression | Apply A only to emit anonymous within-frame duplicate proposals, including IoU, containment, joint count/spread, distances, view pair and ambiguity. Leave observations unchanged. | Safest first cached experiment; establishes neither unique-person counts nor recall. Avoid transitive connected components that can chain two real people through an intermediate partial pose. |
| C: complete-view preference after strong association | Only after A establishes an unambiguous pair, prefer a less-truncated observation with more confident, spatially spread joints; use confidence and deterministic view/slot order as tie-breakers. Select an existing observation, without synthesizing an averaged skeleton. | `clippedByView=false` does not prove anatomical completeness; cropping can remove a head without pushing the predicted box outside a view. Higher confidence alone is also insufficient. Do not fuse uncertain pairs. |

Recommended sequence: **B first**, then independently review false associations on distinct overlapping people before considering A/C. Do not lower IoU globally or suppress on containment alone. No new model calls are needed for this limited diagnostic, but a future complete replay needs raw pre-host-dedup outputs and geometry under each preprocessing variant.

Preserve fixed five views, <=256 slots/view and <=1,280 candidate bound. Generate cross-view candidate pairs through the existing spatial index; stop at the existing 50,000-comparison budget, report exhaustion and retain unresolved observations. Cap joint work at 17 correspondences/pair (<=850,000 joint comparisons at that budget). Use deterministic greedy representatives with pairwise checks against the representative, without unbounded all-pairs scans or transitive clustering. Disclose proposed merges, ambiguous pairs, budget exhaustion, before/after association counts and the existing 100-observation cap separately. None is a count of visible humans.

## Checks, rights and remaining uncertainty

- Re-read the local protocol, observer/CLI, previous visual report and cached analysis; recomputed the local hashes above. Parsed the actual graph input path and embedded NMS constants, independently compared their implications with SDK JSON and pinned primary source. No inference tests were run; no new visual inspection was claimed in this task.
- Source inspection is paraphrased; no upstream implementation was copied or executed. The inspected [MMPose licence](https://github.com/open-mmlab/mmpose/blob/759b39c13fea6ba094afc1fa932f51dc1b11cbf9/LICENSE) and [MMDeploy licence](https://github.com/open-mmlab/mmdeploy/blob/3f8604bd72e8e15d06b2e0552fe2fdb8f8de33c4/LICENSE) are Apache-2.0. This code-licence finding does not independently establish checkpoint-specific terms or Body7 constituent dataset/footage rights.
- Unresolved: exact historical exporter/config checkout; a runnable canonical SDK postprocessor; full dynamic TopK/output-slot semantics; official-versus-local tensor/output numerical parity; the causal contribution of preprocessing to false/duplicate detections; and duplicate-rule precision/recall on independently annotated crowded overlap cases.
- No 50–100-person coverage, fight accuracy, true near-IR/night performance, production latency or deployment suitability is established. The existing X3D baseline and live ingress limits remain untouched. Parent alone coordinates any later model/GPU comparison.
