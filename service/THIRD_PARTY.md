# Local inference provenance

- YOLOX-S: Megvii-BaseDetection/YOLOX, official `0.1.1rc0` ONNX release,
  [Apache-2.0](https://github.com/Megvii-BaseDetection/YOLOX/blob/main/LICENSE).
- RTMPose-M: OpenMMLab MMPose, Body7 420-epoch 256x192 SDK export dated
  2023-05-04, [Apache-2.0](https://github.com/open-mmlab/mmpose/blob/main/LICENSE).
  Inference follows the official SimCC/affine preprocessing examples.
- SlowFast-R50 AVA: Facebook Research PyTorchVideo 0.1.5,
  [Apache-2.0](https://github.com/facebookresearch/pytorchvideo/blob/main/LICENSE),
  official `SLOWFAST_8x8_R50_DETECTION.pyth` checkpoint.
- ByteTrack: used through supervision 0.25.1
  ([MIT](https://github.com/roboflow/supervision/blob/0.25.1/LICENSE.md));
  upstream algorithm [FoundationVision/ByteTrack](https://github.com/FoundationVision/ByteTrack), MIT.

Exact downloaded artifact URLs and SHA-256 values are in `model-manifest.json`.
Repository licenses above identify upstream code/model-release provenance; they
do not grant rights to the models' underlying training videos or imply deployment
validation. The service neither bundles nor redistributes those training datasets.

Evaluation clips retain their individual licenses and authors in
`evaluation/corpus.json`. Boxing training: Evworo, CC BY-SA 3.0. Lutte Africaine
Francophonie 2017: Kod B, CC BY-SA 4.0. Seth Rollins Avada Kedavra: HHH Pedrigree,
CC BY-SA 3.0. The exercise fixture's existing Pexels provenance remains in
`../tests/fixtures/README.md`. Cropped variants are runtime transformations, marked
as synthetic. If distributed, derivatives must retain attribution and applicable
share-alike terms. Clips remain excluded from Git. The explicit public `/fight`
demo serves the unchanged boxing and grappling clips from the PC; visible credits
and license/source links are provided on that page. Other evaluation footage is
not exposed through the sample endpoint.

- RTMO-M Body7: official OpenMMLab SDK export dated 2023-12-11, Apache-2.0
  upstream MMPose. Body7 includes crowd datasets; this checkpoint is not described
  as the separate CrowdPose-fine-tuned checkpoint.
- X3D candidate: community publisher `visionlab-ai/school-violence-detection-models`,
  commit `a744b6af7496f0cbfa4f0ba32acd46b65e52d4e1`, `final_x3d_realtime.pt`.
  Publisher declares MIT. Architecture is PyTorchVideo X3D-M. RWF-2000 training
  provenance and publisher validation claims are not Nivra classroom validation.
  No training dataset is redistributed. Loading verifies SHA-256, uses
  `weights_only=True`, and allowlists only the checkpoint's known NumPy numeric
  metadata constructors; no publisher remote code is executed.

- Offline MC3-18 diagnostic candidate: MohamedSebaie/
  Fight_Detection_From_Surveillance_Cameras-PyTorch_Project, revision
  `a27adffec6651c10639b5b453e0df8564b9be298`,
  `Models/model_16_m3_0.8888.pth`, SHA-256
  `8268694ade4c0e79a1c5fa41a4f3c21129082d75fac9eb7c25e5a0eabad49bfa`.
  Upstream repository declares MIT. Architecture uses torchvision MC3-18.
  The benchmark independently implements documented RGB resize/center-crop,
  normalization and class order; it does not execute upstream utility code.
  Loading uses `weights_only=True` and strict state-dict validation. Weights are
  local and ignored by Git; training-data rights and the correspondence between
  this checkpoint and the README's best accuracy claim have not been established.
