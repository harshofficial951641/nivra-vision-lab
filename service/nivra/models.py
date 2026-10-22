"""Pinned inference adapters. No runtime downloads or remote inference."""
from pathlib import Path
import hashlib
import json
import os
import cv2
import numpy as np
import torch
import onnxruntime as ort

ROOT = Path(__file__).resolve().parents[1]


def select_device(requested=None):
    requested = requested or os.environ.get('NIVRA_DEVICE', 'auto')
    if requested not in ('auto', 'cuda', 'mps', 'cpu'):
        raise ValueError('NIVRA_DEVICE must be auto, cuda, mps, or cpu')
    available = {'cuda': torch.cuda.is_available(),
                 'mps': bool(getattr(torch.backends, 'mps', None) and torch.backends.mps.is_available()),
                 'cpu': True}
    if requested != 'auto':
        if not available[requested]:
            raise RuntimeError(f'Requested device {requested} is unavailable')
        return requested
    return next(device for device in ('cuda', 'mps', 'cpu') if available[device])


def onnx_providers(device):
    preferred = {'cuda': 'CUDAExecutionProvider', 'mps': 'CoreMLExecutionProvider'}.get(device)
    return ([preferred] if preferred in ort.get_available_providers() else []) + ['CPUExecutionProvider']


def iou(a, b):
    intersection = np.maximum(0, np.minimum(a[2:], b[2:]) - np.maximum(a[:2], b[:2])).prod()
    return float(intersection / max(1e-6, np.prod(a[2:] - a[:2]) + np.prod(b[2:] - b[:2]) - intersection))


class Models:
    def __init__(self, person_model=None, fight_model=None):
        self.person_model = person_model or os.environ.get('NIVRA_PERSON_MODEL', 'yolox')
        self.fight_model = fight_model or os.environ.get('NIVRA_FIGHT_MODEL', 'ava')
        if self.fight_model not in ('ava', 'x3d'):
            raise ValueError('Unknown fight model')
        if self.person_model not in ('yolox', 'rtmo'):
            raise ValueError('Unknown person model')
        manifest = json.loads((ROOT / 'model-manifest.json').read_text())
        for model in manifest['models']:
            required = (self.person_model == 'rtmo' and model['id'] == 'rtmo-m-body7') or (self.fight_model == 'x3d' and model['id'] == 'x3d-rwf2000-candidate')
            if model.get('optional') and not required:
                continue
            path = ROOT / 'models' / model['file']
            if not path.exists():
                raise RuntimeError('Models missing. Run service/prepare_models.py first.')
            with path.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != model['sha256']:
                    raise RuntimeError(f"Model integrity check failed: {model['id']}")
        self.device = select_device()
        torch.set_num_threads(4)
        # Loading torch first makes its bundled CUDA/cuDNN libraries available on Windows.
        if self.device == 'cuda' and hasattr(ort, 'preload_dlls'):
            ort.preload_dlls()
        providers = onnx_providers(self.device)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        if self.person_model == 'rtmo':
            self.detector = ort.InferenceSession(str(ROOT / 'models/rtmo_m.onnx'), options, providers=providers)
            self.pose = self.detector
        else:
            self.detector = ort.InferenceSession(str(ROOT / 'models/yolox_s.onnx'), options, providers=providers)
            self.pose = ort.InferenceSession(str(ROOT / 'models/rtmpose_m.onnx'), options, providers=providers)
        self.action = None
        if self.fight_model == 'ava':
            from pytorchvideo.models.hub import slowfast_r50_detection
            self.action = slowfast_r50_detection(pretrained=False)
            weights = torch.load(ROOT / 'models/slowfast_r50.pyth', map_location='cpu', weights_only=True)
            self.action.load_state_dict(weights['model_state'])
            self.action.eval().to(self.device)
        self.fight = None
        if self.fight_model == 'x3d':
            from .x3d_candidate import X3DCandidate
            self.fight = X3DCandidate()
            self.fight.model.to(self.device)
            self.fight.device = self.device
        self.runtime = {'device': self.device, 'action': self.device, 'detector': self.detector.get_providers()[0],
                        'pose': self.pose.get_providers()[0], 'personModel': self.person_model,
                        'fightModel': self.fight_model, 'maxPeople': 50 if self.person_model == 'rtmo' else 8,
                        'validated': False}

    def crowd_observations(self, frame):
        """Official RTMO end-to-end export: BGR letterbox and already-decoded boxes."""
        height, width = frame.shape[:2]
        ratio = min(640 / height, 640 / width)
        resized = cv2.resize(frame, (int(width * ratio), int(height * ratio)))
        padded = np.full((640, 640, 3), 114, np.uint8)
        padded[:resized.shape[0], :resized.shape[1]] = resized
        det, pose = self.detector.run(None, {self.detector.get_inputs()[0].name:
                                           padded.transpose(2, 0, 1)[None].astype(np.float32)})
        boxes, scores = det[0, :, :4].copy() / ratio, det[0, :, 4]
        joints = pose[0].copy()
        joints[:, :, :2] /= ratio
        outside = (joints[:, :, 0] < 0) | (joints[:, :, 0] >= width) | (joints[:, :, 1] < 0) | (joints[:, :, 1] >= height)
        joints[:, :, 2][outside] = 0
        joints[:, :, :2] /= [width, height]
        boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, width)
        boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, height)
        keep = []
        for index in np.argsort(-scores):
            if scores[index] < .1 or np.any(boxes[index, 2:] - boxes[index, :2] < 8):
                continue
            if all(iou(boxes[index], boxes[other]) < .7 for other in keep):
                keep.append(index)
        return boxes[keep], scores[keep], joints[keep]

    def detect(self, frame):
        height, width = frame.shape[:2]
        ratio = min(640 / height, 640 / width)
        resized = cv2.resize(frame, (int(width * ratio), int(height * ratio)))
        padded = np.full((640, 640, 3), 114, np.uint8)
        padded[:resized.shape[0], :resized.shape[1]] = resized
        # Official YOLOX export expects BGR, unnormalized 0..255 input.
        raw = self.detector.run(None, {self.detector.get_inputs()[0].name:
                                      padded.transpose(2, 0, 1)[None].astype(np.float32)})[0][0].copy()
        grids, strides = [], []
        for stride in (8, 16, 32):
            y, x = np.meshgrid(np.arange(640 // stride), np.arange(640 // stride), indexing='ij')
            grids.append(np.stack([x, y], -1).reshape(-1, 2))
            strides.append(np.full((x.size, 1), stride))
        grid, stride = np.concatenate(grids), np.concatenate(strides)
        raw[:, :2] = (raw[:, :2] + grid) * stride
        raw[:, 2:4] = np.exp(np.clip(raw[:, 2:4], -15, 15)) * stride
        scores = raw[:, 4] * raw[:, 5]
        raw, scores = raw[scores >= .1], scores[scores >= .1]
        boxes = np.concatenate([raw[:, :2] - raw[:, 2:4] / 2, raw[:, :2] + raw[:, 2:4] / 2], 1) / ratio
        boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, width)
        boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, height)
        keep = []
        for index in np.argsort(-scores):
            if np.any(boxes[index, 2:] - boxes[index, :2] < 8):
                continue
            if all(iou(boxes[index], boxes[other]) < .7 for other in keep):
                keep.append(index)
        return boxes[keep], scores[keep]

    def keypoints(self, frame, box):
        # RTMPose SimCC: preserve crop aspect, 1.25 padding, RGB/ImageNet normalization.
        center = (box[:2] + box[2:]) / 2
        size = (box[2:] - box[:2]) * 1.25
        size[0] = max(size[0], size[1] * 192 / 256)
        size[1] = size[0] * 256 / 192
        affine = np.array([[192 / size[0], 0, 96 - center[0] * 192 / size[0]],
                           [0, 256 / size[1], 128 - center[1] * 256 / size[1]]], np.float32)
        crop = cv2.warpAffine(frame, affine, (192, 256))[:, :, ::-1].astype(np.float32)
        crop = (crop - np.array([123.675, 116.28, 103.53])) / np.array([58.395, 57.12, 57.375])
        x, y = self.pose.run(None, {self.pose.get_inputs()[0].name: crop.transpose(2, 0, 1)[None].astype(np.float32)})
        coordinates = np.stack([x[0].argmax(-1), y[0].argmax(-1)], -1) / 2
        scores = np.minimum(x[0].max(-1), y[0].max(-1)).clip(0, 1)
        coordinates = coordinates / np.array([192, 256]) * size + center - size / 2
        h, w = frame.shape[:2]
        scores[(coordinates[:, 0] < 0) | (coordinates[:, 0] >= w) |
               (coordinates[:, 1] < 0) | (coordinates[:, 1] >= h)] = 0
        return np.column_stack([coordinates / [w, h], scores]).tolist()

    @torch.inference_mode()
    def actions(self, frames, boxes):
        if self.action is None:
            return np.zeros((len(boxes), 80), np.float32)
        if not len(boxes):
            return np.empty((0, 80), np.float32)
        h, w = frames[0].shape[:2]
        scale = 256 / min(h, w)
        # Bound landscape/portrait extremes before this adapter in the frame validator.
        images = np.stack([cv2.resize(f[:, :, ::-1], (round(w * scale), round(h * scale))) for f in frames])
        clip = torch.from_numpy(images.copy()).permute(3, 0, 1, 2).float().to(self.device) / 255
        clip = (clip - .45) / .225
        slow = clip[:, torch.linspace(0, 31, 8).long()]
        rois = np.column_stack([np.zeros(len(boxes)), np.asarray(boxes) * scale])
        prediction = self.action([slow[None], clip[None]], torch.tensor(rois, dtype=torch.float32, device=self.device))
        return prediction.cpu().numpy()
