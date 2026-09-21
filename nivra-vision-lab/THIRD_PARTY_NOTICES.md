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
