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


## Bundled MoViNet A0 VID candidate

`service/nivra/assets/movinet_a0_fight.pt` is the fixed epoch-3 T7 eight-frame
fine-tune, model id `movinet-a0-vid-v1`. SHA-256, input contract and provenance
are recorded in `service/model-manifest.json` (paths relative to service).
Original Google MoViNet weights: Apache-2.0, [publisher model licence](https://www.kaggle.com/models/google/movinet).
The [A0 stream model card](https://github.com/tensorflow/tfhub.dev/blob/81fdea8ffa53b5acbd66a012d17fb8f9602c714b/assets/docs/tensorflow/models/movinet/a0/stream/kinetics-600/classification/3.md)
identifies the upstream model. The PyTorch port is by Atze00, MIT, pinned to
`c2d1edf48fc6c5259707f9d833f22171b4f63493`:
[source and licence](https://github.com/Atze00/MoViNet-pytorch/blob/c2d1edf48fc6c5259707f9d833f22171b4f63493/LICENSE).
The bundled derivative uses VID V2 CC0-1.0 fine-tuning data; no training footage
is redistributed. Preserve Google Apache-2.0 and port MIT obligations. Full
licence texts are in `licenses/MOVINET-APACHE-2.0.txt` and
`licenses/MOVINET-PORT-MIT.txt` at repository root.
This is a review aid, not a calibrated violence probability or a claim of
classroom accuracy, deployment clearance, or Apple hardware validation.
