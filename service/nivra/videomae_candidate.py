"""Pinned, offline cliffer1 comparison adapter; never selects or promotes a model.

The caller owns decoding and source-time continuity. Eight to fifteen observed
frames may repeat indices under the existing sampling policy; this does not
establish a four-second observation or fill missing decoder coverage.
"""
from collections.abc import Mapping, Sequence
from copy import deepcopy
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any

import numpy as np
import torch


MODEL_ID = 'cliffer1/videomae-base-finetuned-kinetics-violence-nonviolence-tuned'
REVISION = '613844b1d2d27f68944619bf91885a9befb101ac'
TRANSFORMERS_VERSION = '4.57.1'
FILE_SHA256 = MappingProxyType({
    'README.md': '0d2adb5b283c3c4bd8fd087d5ce85d0c2a6528c7ca6cc6ff65da51645452614f',
    'config.json': '59e7a7ba3196e7d7272304b16dc59e15b09b9f17832d76e8cbd9755487afa8ed',
    'preprocessor_config.json': '4bc9b255ff212041bc28127d4fa0ae1630abca52bb2d882f3e4c0b9e5b763f06',
    'model.safetensors': '5166b055ebee1439d6517c5bf2d516dce7a1f65afc53367f43b5848970853d53',
})
_CONFIG = {
    'architectures': ['VideoMAEForVideoClassification'],
    'model_type': 'videomae', 'hidden_size': 768, 'intermediate_size': 3072,
    'num_hidden_layers': 12, 'num_attention_heads': 12, 'num_channels': 3,
    'image_size': 224, 'num_frames': 16, 'patch_size': 16, 'tubelet_size': 2,
    'use_mean_pooling': True, 'problem_type': 'single_label_classification',
    'qkv_bias': True, 'norm_pix_loss': False,
}
_PROCESSOR = {
    'size': {'shortest_edge': 224}, 'crop_size': {'height': 224, 'width': 224},
    'do_resize': True, 'do_center_crop': True, 'do_rescale': True,
    'do_normalize': True, 'resample': 2, 'rescale_factor': 1 / 255,
    'image_mean': [.485, .456, .406], 'image_std': [.229, .224, .225],
}


def _verify_snapshot(snapshot: Path) -> None:
    if not snapshot.is_dir():
        raise ValueError('VideoMAE snapshot must be a local directory')
    for name, expected in FILE_SHA256.items():
        path = snapshot / name
        if path.is_symlink() or not path.is_file() or path.resolve().parent != snapshot:
            raise ValueError(f'VideoMAE snapshot requires a regular local {name}')
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != expected:
            raise ValueError(f'VideoMAE checksum mismatch: {name}')


def _check_config(config: Mapping[str, Any], *, loaded: bool = False) -> None:
    for key, expected in _CONFIG.items():
        value = config.get(key)
        if value != expected or (type(expected) is bool and type(value) is not bool):
            raise ValueError(f'VideoMAE config mismatch: {key}')
    labels = {0: 'NonViolence', 1: 'Violence'} if loaded else {'0': 'NonViolence', '1': 'Violence'}
    if (config.get('id2label') != labels or
            config.get('label2id') != {'NonViolence': 0, 'Violence': 1}):
        raise ValueError('VideoMAE class order must be NonViolence, Violence')
    if config.get('num_labels', 2) != 2:
        raise ValueError('VideoMAE must have two labels')


def _load_transformers():
    """Lazy dependency seam: importing the adapter never imports Transformers."""
    try:
        installed = version('transformers')
    except PackageNotFoundError as error:
        raise RuntimeError('VideoMAE requires an isolated Transformers 4.57.1 environment') from error
    if installed != TRANSFORMERS_VERSION:
        raise RuntimeError(f'VideoMAE requires Transformers {TRANSFORMERS_VERSION}; found {installed}')
    from transformers import VideoMAEForVideoClassification, VideoMAEImageProcessor
    return VideoMAEImageProcessor, VideoMAEForVideoClassification


class VideoMAECandidate:
    """Explicit cpu/cuda inference for one immutable-source comparison candidate."""

    def __init__(self, snapshot: str | Path, *, device: str = 'cpu'):
        if device not in ('cpu', 'cuda'):
            raise ValueError('VideoMAE device must be cpu or cuda')
        self.snapshot = Path(snapshot).resolve()
        _verify_snapshot(self.snapshot)
        config = json.loads((self.snapshot / 'config.json').read_text(encoding='utf-8'))
        _check_config(config)
        processor_config = json.loads(
            (self.snapshot / 'preprocessor_config.json').read_text(encoding='utf-8'))
        if processor_config.get('image_processor_type') != 'VideoMAEImageProcessor':
            raise ValueError('VideoMAE requires its saved image processor')
        for key, expected in _PROCESSOR.items():
            if processor_config.get(key) != expected:
                raise ValueError(f'VideoMAE processor config mismatch: {key}')
        processor_class, model_class = _load_transformers()
        if device == 'cuda' and not torch.cuda.is_available():
            raise RuntimeError('CUDA was requested but is unavailable; no CPU fallback was used')
        self.device = device
        self.processor = processor_class.from_pretrained(
            self.snapshot, local_files_only=True, trust_remote_code=False)
        for key, expected in _PROCESSOR.items():
            if getattr(self.processor, key, None) != expected:
                raise ValueError(f'VideoMAE loaded processor mismatch: {key}')
        model, info = model_class.from_pretrained(
            self.snapshot, local_files_only=True, trust_remote_code=False,
            use_safetensors=True, weights_only=True, attn_implementation='eager',
            output_loading_info=True)
        if not isinstance(info, Mapping) or any(info.values()):
            raise ValueError(f'VideoMAE checkpoint did not load cleanly: {info}')
        loaded_config = model.config.to_dict()
        loaded_config['num_labels'] = model.config.num_labels
        _check_config(loaded_config, loaded=True)
        if (tuple(model.classifier.weight.shape) != (2, 768) or
                tuple(model.classifier.bias.shape) != (2,) or
                model.fc_norm is None or tuple(model.fc_norm.normalized_shape) != (768,)):
            raise ValueError('VideoMAE classifier/mean-pooling shape mismatch')
        self.model = model.float().to(device).eval()

    @torch.inference_mode()
    def predict(self, BGR_frames: Sequence[np.ndarray] | np.ndarray) -> dict[str, Any]:
        if (not isinstance(BGR_frames, (Sequence, np.ndarray)) or
                (isinstance(BGR_frames, np.ndarray) and BGR_frames.ndim != 4) or
                len(BGR_frames) < 8):
            raise ValueError('VideoMAE requires at least eight observed BGR frames')
        shape = None
        for frame in BGR_frames:
            if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or
                    frame.ndim != 3 or frame.shape[2] != 3 or min(frame.shape[:2]) < 1):
                raise ValueError('VideoMAE frames must be nonempty uint8 BGR HWC images')
            if shape is not None and frame.shape != shape:
                raise ValueError('VideoMAE source frames must have the same dimensions')
            shape = frame.shape
        indices = np.linspace(0, len(BGR_frames) - 1, 16).astype(np.int64)
        rgb = [np.ascontiguousarray(BGR_frames[index][:, :, ::-1]) for index in indices]
        batch = self.processor(rgb, return_tensors='pt')
        if not isinstance(batch, Mapping) or set(batch) != {'pixel_values'}:
            raise ValueError('VideoMAE processor must return only pixel_values')
        pixels = batch['pixel_values']
        if (not isinstance(pixels, torch.Tensor) or
                tuple(pixels.shape) != (1, 16, 3, 224, 224) or
                pixels.dtype != torch.float32 or not torch.isfinite(pixels).all()):
            raise ValueError('VideoMAE processor returned invalid pixel_values')
        output = self.model(pixel_values=pixels.to(self.device))
        logits = getattr(output, 'logits', None)
        if (not isinstance(logits, torch.Tensor) or tuple(logits.shape) != (1, 2) or
                not logits.is_floating_point() or not torch.isfinite(logits).all()):
            raise ValueError('VideoMAE must return two finite logits for one clip')
        probabilities = logits.float().softmax(dim=-1)
        if not torch.isfinite(probabilities).all():
            raise ValueError('VideoMAE returned nonfinite class probabilities')
        scores = probabilities[0].cpu().tolist()
        return {'fightScore': scores[1], 'classScores': scores,
                'scoreKind': 'softmax-on-logits', 'fightIndex': 1}

    def metadata(self) -> dict[str, Any]:
        """Return a defensive copy; callers cannot modify the source contract."""
        return deepcopy({
            'modelId': MODEL_ID, 'revision': REVISION,
            'source': f'https://huggingface.co/{MODEL_ID}/tree/{REVISION}',
            'files': dict(FILE_SHA256), 'transformersVersion': TRANSFORMERS_VERSION,
            'device': self.device, 'architecture': 'VideoMAEForVideoClassification',
            'classNames': ['NonViolence', 'Violence'], 'fightIndex': 1,
            'scoreKind': 'softmax-on-logits', 'useMeanPooling': True,
            'preprocess': {
                **_PROCESSOR, 'inputColor': 'BGR', 'processorColor': 'RGB',
                'inputDtype': 'uint8', 'inputLayout': 'HWC',
                'outputLayout': 'B,T,C,H,W', 'frames': 16, 'minimumObservedFrames': 8,
                'temporalSampling': 'floor(linspace(0, observed_frame_count - 1, 16))',
                'repeatIndicesFor8To15Frames': True, 'sourceDimensions': 'preserved until saved processor',
                'sourceTimeCoverage': 'caller must validate; frame count does not prove duration or continuity',
            },
            'provenance': {
                'checkpointLicense': 'CC-BY-NC-4.0', 'trainingDataset': 'unknown per author card',
                'trainingCodeAndSplitLineage': 'unverified',
                'intendedUse': 'offline physical-fight comparison; no automatic live promotion',
                'qualityEvidence': 'development diagnostics only; not accuracy or independent holdout',
                'crowdAndNightEvidence': '50-100 people, near-IR and low-light colour unverified',
            },
        })
