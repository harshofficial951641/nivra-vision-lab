# Third-party notices

## MediaPipe Tasks Vision

This project uses `@mediapipe/tasks-vision`, the MediaPipe Pose Landmarker Full and Lite models, and the EfficientDet-Lite0 float16 object-detection model from Google AI Edge.

- Package: <https://www.npmjs.com/package/@mediapipe/tasks-vision>
- Source: <https://github.com/google-ai-edge/mediapipe>
- Pose model guide: <https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker>
- Full pose model, float16 version 1: <https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task>
- Lite pose model, float16 version 1: <https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task>
- Pose model card: <https://storage.googleapis.com/mediapipe-assets/Model%20Card%20BlazePose%20GHUM%203D.pdf>
- Object detector model: <https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/float16/latest/efficientdet_lite0.tflite>
- License: Apache License 2.0, <https://www.apache.org/licenses/LICENSE-2.0>
- Full upstream license text: [licenses/MEDIAPIPE-LICENSE.txt](./licenses/MEDIAPIPE-LICENSE.txt)

The worker-based integration follows architectural patterns from Google's official MediaPipe browser samples:

- Source: <https://github.com/google-ai-edge/mediapipe-samples-web>
- License: Apache License 2.0

Copyright 2026 The MediaPipe Authors. Licensed under the Apache License, Version 2.0.

Model versions and SHA-256 checksums are pinned in `scripts/prepare-models.mjs`.

New UI dependency: `@phosphor-icons/react` 2.1.10, MIT. Used for standard interface
icons; actual installed version is pinned by package-lock.json. The sample
classroom image in `public/demo/` was generated for this local demonstration and
is explicitly labelled. It is not a recording or an accuracy dataset.

QR generation uses qrcode.react 4.2.0 (ISC), https://github.com/zpao/qrcode.react.
The optional local tunnel uses official cloudflared 2026.9.3 (Apache-2.0); its
checksum and operating limits are documented in docs/remote-camera-setup.md.


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
