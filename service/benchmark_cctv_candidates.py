"""Bounded source-resolution classifier diagnostics. No live integration.

One explicitly selected model/device per process; local assets only. Existing
development footage is diagnostic, never held-out accuracy or crowd/night proof.
"""
import argparse
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import math
from pathlib import Path
import re
import sys
import time

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
POLICY = {'version': 'cctv-paired-v1', 'windowMs': 4000, 'sampleIntervalMs': 100,
          'predictionIntervalMs': 400, 'minimumSpanMs': 3800, 'minimumObservations': 8,
          'resetGapMs': 1200, 'framesPerWindow': 16,
          'sampling': 'uniform-linspace-floor-over-observed-gate-samples',
          'spatialBuffer': 'native source/cropped uint8 BGR; no pre-resize',
          'threshold': .5, 'comparison': 'fightScore > threshold',
          'shortClipPadding': False, 'sourceClock': 'strict decoded presentation timestamps'}
CONTROL_ASSETS = {
    'x3d': {'path': ROOT / 'models/x3d_rwf2000.pt',
            'sha256': 'e833f69d110f167cad4a6c38d385564bdb2f6de63d246e45cb03ff9aa17f0349',
            'source': 'https://huggingface.co/visionlab-ai/school-violence-detection-models/tree/a744b6af7496f0cbfa4f0ba32acd46b65e52d4e1'},
    'mc3': {'path': ROOT / 'models/mc3_18_sebaie.pth',
            'sha256': '8268694ade4c0e79a1c5fa41a4f3c21129082d75fac9eb7c25e5a0eabad49bfa',
            'source': 'https://github.com/MohamedSebaie/Fight_Detection_From_Surveillance_Cameras-PyTorch_Project/tree/a27adffec6651c10639b5b453e0df8564b9be298'},
}
VIDEOMAE_REVISION = '613844b1d2d27f68944619bf91885a9befb101ac'
VIDEOMAE_FILES = {
    'config.json': '59e7a7ba3196e7d7272304b16dc59e15b09b9f17832d76e8cbd9755487afa8ed',
    'preprocessor_config.json': '4bc9b255ff212041bc28127d4fa0ae1630abca52bb2d882f3e4c0b9e5b763f06',
    'README.md': '0d2adb5b283c3c4bd8fd087d5ce85d0c2a6528c7ca6cc6ff65da51645452614f',
    'model.safetensors': '5166b055ebee1439d6517c5bf2d516dce7a1f65afc53367f43b5848970853d53',
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def content_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


@dataclass(frozen=True)
class Limits:
    max_source_pixels: int = 1920 * 1080
    max_dimension: int = 3840
    max_buffer_pixels: int = 100_000_000
    max_windows: int = 1000
    max_decode_frames: int = 100_000
    max_clips: int = 100

    def validate(self):
        for value in asdict(self).values():
            if type(value) is not int or value <= 0:
                raise ValueError('Limits must be positive integers')
        if self.max_source_pixels > 3840 * 2160 or self.max_dimension > 7680:
            raise ValueError('Input geometry limit exceeds bounded runner maximum')
        if self.max_buffer_pixels > 200_000_000 or self.max_windows > 10_000:
            raise ValueError('Buffer/window limit exceeds bounded runner maximum')
        if self.max_decode_frames > 1_000_000 or self.max_clips > 1000:
            raise ValueError('Decode/corpus limit exceeds bounded runner maximum')


@dataclass
class Window:
    timestamps: list
    frames: list
    source_dimensions: tuple  # width, height before crop
    view_dimensions: tuple
    crop_pixels: tuple

    @property
    def start(self):
        return self.timestamps[0]

    @property
    def end(self):
        return self.timestamps[-1]


def _frame(frame, limits):
    if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or
            frame.ndim != 3 or frame.shape[2] != 3):
        raise ValueError('Decoded frames must be uint8 BGR images')
    height, width = frame.shape[:2]
    _dimensions(width, height, limits)
    return width, height


def _dimensions(width, height, limits):
    if (type(width) is not int or type(height) is not int or width <= 0 or height <= 0 or
            max(height, width) > limits.max_dimension or height * width > limits.max_source_pixels):
        raise ValueError('Decoded source dimensions exceed input pixel/dimension limit')


def _crop(value):
    if (not isinstance(value, list) or len(value) != 4 or
            not all(finite_number(number) for number in value) or
            not 0 <= value[0] < value[2] <= 1 or not 0 <= value[1] < value[3] <= 1):
        raise ValueError('Invalid normalized crop coordinates')


def validate_inputs(candidate, corpus, snapshot, limits, *, adaptation_run=None, training_manifest_sha256=None):
    """Hash ALL inputs before any model construction or decoder is invoked."""
    limits.validate()
    if candidate not in ('x3d', 'mc3', 'videomae', 'community', 'community-v2'):
        raise ValueError('Unknown candidate')
    if candidate == 'community-v2':
        if not isinstance(training_manifest_sha256, str) or not re.fullmatch('[0-9a-f]{64}', training_manifest_sha256):
            raise ValueError('community-v2 requires explicit --training-manifest-sha256 (64 lowercase hex)')
    corpus = Path(corpus)
    manifest_bytes = corpus.read_bytes()
    records = json.loads(manifest_bytes)
    if not isinstance(records, list) or not 1 <= len(records) <= limits.max_clips:
        raise ValueError('Corpus must be a nonempty bounded list')
    ids, groups, hashes = set(), {}, {}
    media = {}
    for clip in records:
        if not isinstance(clip, dict):
            raise ValueError('Corpus entries must be objects')
        for field in ('id', 'sourceGroup', 'path', 'license'):
            if not isinstance(clip.get(field), str) or not clip[field].strip():
                raise ValueError('Missing corpus field: ' + field)
        if clip['id'] in ids:
            raise ValueError('Duplicate clip ID')
        ids.add(clip['id'])
        if clip.get('annotationStatus') != 'reviewed':
            raise ValueError('Only reviewed diagnostic context is accepted')
        if clip.get('split') not in ('calibration', 'holdout', 'diagnostic'):
            raise ValueError('Unknown historical split')
        sha = clip.get('sha256')
        if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha):
            raise ValueError('Invalid media SHA-256')
        for index, key in ((groups, clip['sourceGroup']), (hashes, sha)):
            if key in index and index[key] != clip['split']:
                raise ValueError('Source/hash leakage across historical splits')
            index[key] = clip['split']
        duration = clip.get('durationMs')
        if not finite_number(duration) or duration <= 0:
            raise ValueError('Invalid declared duration')
        events = clip.get('events')
        if not isinstance(events, list):
            raise ValueError('Events must be explicit context array')
        for event in events:
            if (not isinstance(event, dict) or not finite_number(event.get('startMs')) or
                    not finite_number(event.get('endMs')) or
                    not 0 <= event['startMs'] <= event['endMs'] <= duration):
                raise ValueError('Invalid context event interval')
        if clip.get('crop') is not None:
            _crop(clip['crop'])
        path = (corpus.parent / clip['path']).resolve()
        if not path.is_file() or digest(path) != sha:
            raise ValueError('Diagnostic media checksum mismatch: ' + clip['id'])
        media[clip['id']] = {'sha256': sha, 'bytes': path.stat().st_size}
    if hashlib.sha256(corpus.read_bytes()).hexdigest() != hashlib.sha256(manifest_bytes).hexdigest():
        raise ValueError('Corpus changed during validation')
    if candidate in CONTROL_ASSETS:
        asset = CONTROL_ASSETS[candidate]
        if not Path(asset['path']).is_file() or digest(asset['path']) != asset['sha256']:
            raise ValueError('Pinned model asset checksum mismatch: ' + candidate)
        assets = {**asset, 'path': str(Path(asset['path']).resolve()),
                  'bytes': Path(asset['path']).stat().st_size}
    elif candidate in ('community', 'community-v2'):
        if adaptation_run is None:
            raise ValueError('Community candidate requires --adaptation-run')
        if candidate == 'community-v2':
            from nivra.community_x3d_experiments import validate_artifact
            seal_path = Path(adaptation_run).resolve().parent / 'complete.json'
            seal_sha = digest(seal_path)
            adaptation, _ = validate_artifact(adaptation_run, manifest_sha256=training_manifest_sha256)
            if digest(seal_path) != seal_sha:
                raise ValueError('V2 run seal changed during validation')
        else:
            from nivra.community_x3d_training import validate_artifact
            adaptation, _ = validate_artifact(adaptation_run)
        assets = {'adaptationRun': str(Path(adaptation_run).resolve()),
                  'adaptationSha256': adaptation['candidateSha256'],
                  'adaptationReportSha256': digest(Path(adaptation_run) / 'report.json'),
                  'baselineSha256': adaptation['baseSha256'],
                  'trainingManifestSha256': adaptation['manifestSha256'],
                  'trainedSourceHashes': adaptation['snapshotHashes']}
        if candidate == 'community-v2':
            assets['runSealSha256'] = seal_sha
            assets['exportEpoch'] = adaptation['training']['exportEpoch']
    else:
        if snapshot is None or not Path(snapshot).is_dir():
            raise ValueError('VideoMAE requires a verified local snapshot directory')
        files = {}
        for name, sha in VIDEOMAE_FILES.items():
            path = Path(snapshot) / name
            if not path.is_file() or digest(path) != sha:
                raise ValueError('Pinned VideoMAE asset checksum mismatch: ' + name)
            files[name] = {'sha256': sha, 'bytes': path.stat().st_size}
        assets = {'snapshot': str(Path(snapshot).resolve()), 'revision': VIDEOMAE_REVISION,
                  'files': files}
    return records, hashlib.sha256(manifest_bytes).hexdigest(), media, assets


def _exclude(stats, reason, timestamp=None):
    exclusions = stats.setdefault('exclusions', {})
    exclusions[reason] = exclusions.get(reason, 0) + 1
    examples = stats.setdefault('exclusionExamples', [])
    if timestamp is not None and len(examples) < 20 and reason in ('source-gap-reset', 'dimension-reset'):
        examples.append({'reason': reason, 'timestampMs': timestamp})


def windows(clip, corpus, *, limits=None, stats=None, capture_factory=None):
    """Strict PTS, native/cropped geometry, bounded gate-sample history."""
    limits, stats = limits or Limits(), stats if stats is not None else {}
    limits.validate()
    capture = (capture_factory or cv2.VideoCapture)(str((Path(corpus).parent / clip['path']).resolve()))
    history = deque()
    previous = last_sample = last_prediction = -math.inf
    geometry = None
    pixels = emitted = 0
    stats.update({'decodedFrames': 0, 'sampledFrames': 0, 'peakBufferedPixels': 0,
                  'sourceDimensions': [], 'viewDimensions': []})
    try:
        if not capture.isOpened():
            raise ValueError('Cannot decode diagnostic clip: ' + clip['id'])
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        stats['nominalFps'] = fps if math.isfinite(fps) else None
        stats['nominalFpsUsedForClock'] = False
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            stats['decodedFrames'] += 1
            if stats['decodedFrames'] > limits.max_decode_frames:
                raise ValueError('Decoded frame budget exceeded')
            timestamp = float(capture.get(cv2.CAP_PROP_POS_MSEC))
            if not math.isfinite(timestamp) or timestamp < 0 or timestamp <= previous:
                raise ValueError('Non-increasing or invalid decoder presentation timestamp')
            dimensions = _frame(frame, limits)
            gap = timestamp - previous > POLICY['resetGapMs'] if math.isfinite(previous) else False
            changed = geometry is not None and dimensions != geometry
            if gap or changed:
                if gap:
                    _exclude(stats, 'source-gap-reset', timestamp)
                if changed:
                    _exclude(stats, 'dimension-reset', timestamp)
                history.clear()
                pixels = 0
                last_sample = last_prediction = -math.inf
            previous, geometry = timestamp, dimensions
            stats.setdefault('firstDecodedPTS', timestamp)
            stats['lastDecodedPTS'] = timestamp
            if timestamp - last_sample < POLICY['sampleIntervalMs']:
                _exclude(stats, 'sample-spacing')
                continue
            last_sample = timestamp
            width, height = dimensions
            crop = clip.get('crop') or [0., 0., 1., 1.]
            left, top, right, bottom = (round(crop[0] * width), round(crop[1] * height),
                                       round(crop[2] * width), round(crop[3] * height))
            if not left < right or not top < bottom:
                raise ValueError('Crop has no observable pixels')
            view = frame[top:bottom, left:right].copy()
            while history and timestamp - history[0][0] > POLICY['windowMs']:
                expired = history.popleft()[1]
                pixels -= expired.shape[0] * expired.shape[1]
            pixels += view.shape[0] * view.shape[1]
            if pixels > limits.max_buffer_pixels or len(history) >= 48:
                raise ValueError('Native-frame buffer pixel/sample budget exceeded; no implicit resizing')
            history.append((timestamp, view))
            stats['sampledFrames'] += 1
            stats['peakBufferedPixels'] = max(stats['peakBufferedPixels'], pixels)
            for key, value in (('sourceDimensions', list(dimensions)),
                               ('viewDimensions', [view.shape[1], view.shape[0]])):
                if value not in stats[key]:
                    stats[key].append(value)
            if len(history) < 8 or timestamp - history[0][0] < POLICY['minimumSpanMs']:
                _exclude(stats, 'insufficient-context')
                continue
            if timestamp - last_prediction < POLICY['predictionIntervalMs']:
                _exclude(stats, 'prediction-spacing')
                continue
            emitted += 1
            if emitted > limits.max_windows:
                raise ValueError('Window budget exceeded')
            last_prediction = timestamp
            yield Window([item[0] for item in history], [item[1] for item in history],
                         dimensions, (view.shape[1], view.shape[0]), (left, top, right, bottom))
        if stats['decodedFrames'] == 0:
            _exclude(stats, 'empty-decoder')
        if not emitted:
            _exclude(stats, 'no-eligible-window')
        if finite_number(clip.get('durationMs')) and stats['decodedFrames']:
            stats['declaredEndUnobservedMs'] = max(0., clip['durationMs'] - stats['lastDecodedPTS'])
            if stats['declaredEndUnobservedMs'] > POLICY['resetGapMs']:
                _exclude(stats, 'declared-tail-unobserved')
    finally:
        history.clear()
        capture.release()


def _construct_control(name):
    import torch
    if name == 'x3d':
        from pytorchvideo.models.hub import x3d_m
        model = x3d_m(pretrained=False)
        model.blocks[-1].proj = torch.nn.Sequential(torch.nn.Dropout(.3), torch.nn.Linear(2048, 2))
        # Preserve official backbone Softmax, as in the pinned live checkpoint.
    else:
        from torchvision.models.video import mc3_18
        model = mc3_18(weights=None)
        model.fc = torch.nn.Linear(model.fc.in_features, 2)
    return model


def _load_control_state(name, path):
    import torch
    if name == 'x3d':
        from nivra.x3d_candidate import scalar
        with torch.serialization.safe_globals([scalar, np.dtype, type(np.dtype('float64')),
                                                type(np.dtype('float32'))]):
            checkpoint = torch.load(path, map_location='cpu', weights_only=True)
        return {key.removeprefix('backbone.'): value for key, value in checkpoint['model'].items()}
    return torch.load(path, map_location='cpu', weights_only=True)


class ControlCandidate:
    """Independent explicit-device controls; no auto-CUDA constructors/downloads."""

    def __init__(self, name, asset, *, device='cpu'):
        if name not in ('x3d', 'mc3') or device not in ('cpu', 'cuda'):
            raise ValueError('Invalid control/device')
        if digest(asset['path']) != asset['sha256']:
            raise ValueError('Model changed before safe loading')
        self.name, self.device, self.asset = name, device, asset
        self.model = _construct_control(name)
        self.model.load_state_dict(_load_control_state(name, asset['path']), strict=True)
        self.model.float().eval().requires_grad_(False).to(device)

    def metadata(self):
        x3d = self.name == 'x3d'
        return {'source': self.asset, 'classOrder': ['non-violent', 'violent'] if x3d else ['fight', 'noFight'],
                'fightIndex': 1 if x3d else 0,
                'preprocess': {'frames': 16, 'color': 'RGB', 'layout': 'B,C,T,H,W', 'scale': 255,
                               'resizeWH': [224, 224] if x3d else [171, 128],
                               'interpolation': 'opencv-INTER_LINEAR',
                               'centerCropXYWH': None if x3d else [29, 8, 112, 112],
                               'mean': [.45] * 3 if x3d else [.43216, .394666, .37645],
                               'std': [.225] * 3 if x3d else [.22803, .22145, .216989]},
                'scoreKind': 'backbone-softmax' if x3d else 'softmax-logits'}

    def predict(self, frames):
        import torch
        if len(frames) != 16:
            raise ValueError('Runner supplies exactly 16 timestamp-selected frames')
        images = []
        for frame in frames:
            if frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
                raise ValueError('Control input must be uint8 BGR')
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = cv2.resize(rgb, (224, 224) if self.name == 'x3d' else (171, 128))
            if self.name == 'mc3':
                image = image[8:120, 29:141]
            images.append(image)
        metadata = self.metadata()
        array = np.stack(images).astype(np.float32) / 255
        array = (array - np.array(metadata['preprocess']['mean'], np.float32)) / np.array(metadata['preprocess']['std'], np.float32)
        tensor = torch.from_numpy(array).permute(3, 0, 1, 2)[None].to(self.device)
        with torch.inference_mode():
            output = self.model(tensor)
            if output.shape != (1, 2) or not torch.isfinite(output).all():
                raise ValueError('Invalid binary control output')
            scores = output if self.name == 'x3d' else output.softmax(-1)
            values = scores[0].cpu().tolist()
        index = metadata['fightIndex']
        return {'fightScore': values[index], 'classScores': values,
                'scoreKind': metadata['scoreKind'], 'fightIndex': index}


def create_candidate(name, assets, *, device):
    if name == 'community-v2':
        from nivra.community_x3d_experiments import ExperimentCandidate
        return ExperimentCandidate(assets['adaptationRun'],
                                   manifest_sha256=assets['trainingManifestSha256'], device=device)
    if name == 'community':
        from nivra.community_x3d_training import CommunityCandidate
        return CommunityCandidate(assets['adaptationRun'], device=device)
    if name == 'videomae':
        from nivra.videomae_candidate import VideoMAECandidate
        return VideoMAECandidate(assets['snapshot'], device=device)
    return ControlCandidate(name, assets, device=device)


class TorchRuntime:
    def __init__(self, device, memory_fraction):
        import torch
        self.torch, self.device, self.fraction = torch, device, memory_fraction
        torch.set_num_threads(2)
        if device == 'cuda':
            if not torch.cuda.is_available():
                raise RuntimeError('Explicit CUDA is unavailable; no CPU fallback')
            torch.cuda.set_per_process_memory_fraction(memory_fraction)
            torch.cuda.reset_peak_memory_stats()
        self.loaded_at = utc_now()

    def sync(self):
        if self.device == 'cuda':
            self.torch.cuda.synchronize()

    def snapshot(self, phase):
        result = {'phase': phase, 'timestampUtc': utc_now()}
        if self.device == 'cuda':
            cuda = self.torch.cuda
            result.update({'allocatedBytes': cuda.memory_allocated(), 'reservedBytes': cuda.memory_reserved(),
                           'peakAllocatedBytes': cuda.max_memory_allocated(),
                           'peakReservedBytes': cuda.max_memory_reserved()})
        return result

    def metadata(self):
        result = {'device': self.device, 'torch': str(self.torch.__version__),
                  'precision': 'float32', 'cpuThreads': 2, 'opencvThreads': 1}
        if self.device == 'cuda':
            cuda = self.torch.cuda
            result.update({'name': cuda.get_device_name(), 'cudaVersion': self.torch.version.cuda,
                           'cudnnVersion': self.torch.backends.cudnn.version(),
                           'cudaMemoryFraction': self.fraction,
                           'allocatorLimitBytes': cuda.get_device_properties(0).total_memory * self.fraction,
                           'memoryScope': 'This process Torch allocator; excludes live model, driver and decoder'})
        return result


def _prediction(value, index):
    if (not isinstance(value, dict) or type(value.get('fightIndex')) is not int or
            value['fightIndex'] != index):
        raise ValueError('Candidate fight index mismatch')
    scores = value.get('classScores')
    if (not isinstance(scores, (list, tuple)) or len(scores) != 2 or
            not all(finite_number(score) and 0 <= score <= 1 for score in scores) or
            abs(sum(scores) - 1) > 1e-5 or not finite_number(value.get('fightScore')) or
            abs(value['fightScore'] - scores[index]) > 1e-6 or
            not isinstance(value.get('scoreKind'), str) or not value['scoreKind']):
        raise ValueError('Invalid candidate probability/activation contract')
    return {'fightScore': float(value['fightScore']), 'classScores': list(scores),
            'scoreKind': value['scoreKind'], 'fightIndex': index}


def _window_check(window, previous_end, limits):
    times, frames = window.timestamps, window.frames
    if (not 8 <= len(times) <= 48 or len(times) != len(frames) or
            not all(finite_number(timestamp) and timestamp >= 0 for timestamp in times) or
            any(not 100 <= right - left <= 1200 for left, right in zip(times, times[1:])) or
            not 3800 <= times[-1] - times[0] <= 4000 or
            times[-1] - previous_end < 400):
        raise ValueError('Window reader violated paired temporal contract')
    width, height = window.source_dimensions
    _dimensions(width, height, limits)
    left, top, right, bottom = window.crop_pixels
    if (not all(type(value) is int for value in window.crop_pixels) or
            not 0 <= left < right <= width or not 0 <= top < bottom <= height or
            tuple(window.view_dimensions) != (right - left, bottom - top)):
        raise ValueError('Window crop/source geometry mismatch')
    if sum(frame.shape[0] * frame.shape[1] for frame in frames) > limits.max_buffer_pixels:
        raise ValueError('Window exceeds pixel buffer budget')
    for frame in frames:
        if _frame(frame, limits) != tuple(window.view_dimensions):
            raise ValueError('Window reader geometry mismatch')


def run(candidate, corpus, output, *, device='cpu', snapshot=None, yield_to_demo=True,
        cuda_memory_fraction=.35, limits=None, model_factory=create_candidate,
        window_reader=windows, runtime_factory=TorchRuntime, yield_guard=None, adaptation_run=None,
        training_manifest_sha256=None):
    if device not in ('cpu', 'cuda') or not finite_number(cuda_memory_fraction) or not 0 < cuda_memory_fraction <= 1:
        raise ValueError('Invalid explicit device or CUDA memory fraction')
    if type(yield_to_demo) is not bool or (device == 'cuda' and not yield_to_demo):
        raise ValueError('CUDA requires yield-to-demo cooperation')
    if candidate == 'community-v2' and device == 'cuda' and cuda_memory_fraction != .35:
        # Its fixed offline loader also sets .35; never override a smaller requested cap.
        raise ValueError('community-v2 CUDA requires the fixed .35 allocator fraction')
    limits, corpus, output = limits or Limits(), Path(corpus), Path(output)
    if output.exists():
        raise FileExistsError('Output already exists: ' + str(output))
    records, corpus_sha, media, assets = validate_inputs(candidate, corpus, snapshot, limits,
                                                       adaptation_run=adaptation_run,
                                                       training_manifest_sha256=training_manifest_sha256)
    source_paths = {'benchmark_cctv_candidates.py': Path(__file__),
                    'nivra/x3d_training.py': ROOT / 'nivra/x3d_training.py'}
    adapter_name = {'videomae': 'videomae_candidate.py', 'community': 'community_x3d_training.py',
                    'community-v2': 'community_x3d_experiments.py'}.get(candidate, 'x3d_candidate.py')
    adapter_path = ROOT / 'nivra' / adapter_name
    if adapter_path.is_file():
        key = 'nivra/' + adapter_name if candidate == 'community-v2' else str(adapter_path.relative_to(ROOT))
        source_paths[key] = adapter_path
    if candidate == 'community-v2':
        for name in ('community_x3d_training.py', 'x3d_finetune.py', 'training_data.py', 'x3d_candidate.py'):
            source_paths['nivra/' + name] = ROOT / 'nivra' / name
    source_hashes = {name: digest(path) for name, path in source_paths.items()}
    guard = yield_guard
    if guard is None and yield_to_demo:
        from nivra.x3d_training import DemoYieldGuard
        guard = DemoYieldGuard()
    if guard:
        guard()
    cv2.setNumThreads(1)
    started_utc, started = utc_now(), time.perf_counter()
    runtime = runtime_factory(device, cuda_memory_fraction)  # Allocator cap BEFORE constructing/loading.
    runtime.sync()
    if guard:
        guard()
    model = model_factory(candidate, assets, device=device)
    metadata = model.metadata()
    json.dumps(metadata, allow_nan=False)
    runtime.sync()
    memory = [runtime.snapshot('after-load')]
    index = 0 if candidate == 'mc3' else 1
    all_identities, all_latencies, clips = [], [], {}
    warmed = False
    warmups = []

    def infer(frames):
        runtime.sync()
        if guard:
            guard()
        before = time.perf_counter()
        result = model.predict(frames)
        runtime.sync()
        elapsed = (time.perf_counter() - before) * 1000
        return _prediction(result, index), elapsed

    for clip in records:
        rows, stats = [], {}
        previous_end = -math.inf
        decode_started = time.perf_counter()
        iterator = iter(window_reader(clip, corpus, limits=limits, stats=stats))
        read_seconds = 0.
        try:
            while True:
                before_read = time.perf_counter()
                try:
                    window = next(iterator)
                except StopIteration:
                    read_seconds += time.perf_counter() - before_read
                    break
                read_seconds += time.perf_counter() - before_read
                _window_check(window, previous_end, limits)
                previous_end = window.end
                if len(all_identities) >= limits.max_windows:
                    raise ValueError('Total paired window budget exceeded; no partial output written')
                selected = np.linspace(0, len(window.frames) - 1, 16).astype(int).tolist()
                frames = [window.frames[position] for position in selected]
                if not warmed:
                    for _ in range(3):
                        _, elapsed = infer(frames)
                        warmups.append(elapsed)
                    warmed = True
                    memory.append(runtime.snapshot('after-three-warmups'))
                prediction, elapsed = infer(frames)
                identity = {'clipId': clip['id'], 'sourceGroup': clip['sourceGroup'],
                            'mediaSha256': clip['sha256'], 'crop': clip.get('crop'),
                            'windowStartMs': window.start, 'timestampMs': window.end,
                            'sourceDimensionsWH': list(window.source_dimensions),
                            'viewDimensionsWH': list(window.view_dimensions),
                            'cropPixelsLTRB': list(window.crop_pixels),
                            'sourceFramePTS': list(window.timestamps),
                            'selectedFramePTS': [window.timestamps[position] for position in selected]}
                overlaps = [{**event, 'overlapMs': min(window.end, event['endMs']) - max(window.start, event['startMs'])}
                            for event in clip['events'] if event['endMs'] > window.start and event['startMs'] < window.end]
                rows.append({**identity, **prediction, 'review': prediction['fightScore'] > .5,
                             'selectedFrameIndices': selected, 'repeatedSelectedIndices': 16 - len(set(selected)),
                             'labelledEventOverlaps': overlaps, 'inferenceMs': elapsed})
                all_identities.append(identity)
                all_latencies.append(elapsed)
        finally:
            close = getattr(iterator, 'close', None)
            if close:
                close()
        clips[clip['id']] = {'sourceGroup': clip['sourceGroup'], 'historicalSplit': clip['split'],
                             'derivative': bool(clip.get('crop') or clip.get('derivative') or clip.get('parentSha256') or
                                                (isinstance(clip.get('qualityVariant'), dict) and
                                                 clip['qualityVariant'].get('kind') not in (None, 'original-reference'))),
                             'qualityVariant': clip.get('qualityVariant'),
                             'crop': clip.get('crop'), 'conditions': clip.get('conditions', []),
                             'declaredDurationMs': clip['durationMs'], 'media': media[clip['id']],
                             'windows': len(rows), 'reviewWindows': sum(row['review'] for row in rows),
                             'decoder': stats, 'decodeAndWindowSeconds': read_seconds,
                             'clipWallSeconds': time.perf_counter() - decode_started, 'samples': rows}
        print(json.dumps({'stage': 'paired-diagnostic', 'candidate': candidate,
                          'clip': clip['id'], 'windows': len(rows)}), flush=True)
    if not all_identities:
        raise ValueError('No eligible four-second diagnostic windows; no report written')
    runtime.sync()
    memory.append(runtime.snapshot('complete'))
    versions = {}
    for package in ('numpy', 'opencv-python', 'torch', 'torchvision', 'pytorchvideo', 'transformers', 'safetensors'):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = None
    report = {'schemaVersion': 1, 'status': 'complete-diagnostic-only', 'complete': True,
              'candidate': candidate, 'device': device, 'startedUtc': started_utc, 'completedUtc': utc_now(),
              'elapsedSeconds': time.perf_counter() - started, 'policy': POLICY, 'policySha256': content_hash(POLICY),
              'limits': asdict(limits), 'corpusSha256': corpus_sha, 'assets': assets,
              'implementationHashes': source_hashes, 'adapter': metadata, 'versions': versions,
              'runtime': runtime.metadata(), 'memorySnapshots': memory,
              'yieldToDemo': yield_to_demo, 'liveModelChanged': False, 'thresholdFittedHere': False,
              'windowCount': len(all_identities), 'pairedWindowSha256': content_hash(all_identities),
              'warmup': {'calls': 3, 'inferenceMs': warmups, 'includedInScoredTiming': False},
              'timing': {'scope': 'Adapter preprocessing + transfer + forward + return; CUDA synchronized; guard/decode excluded',
                         'samples': len(all_latencies), 'p50InferenceMs': float(np.percentile(all_latencies, 50)),
                         'p95InferenceMs': float(np.percentile(all_latencies, 95)),
                         'p99InferenceMs': float(np.percentile(all_latencies, 99)),
                         'throughputIsLiveCapacity': False},
              'limitations': ['Previously inspected development diagnostics, not independent accuracy.',
                              'Window decisions and context overlaps are not incident recall or confirmed fights.',
                              'No verified 50-100-person, real near-IR or low-light-colour holdout evidence.',
                              'Scores are uncalibrated; no automatic promotion or threshold relaxation.',
                              'Paired source intervals do not make model centre-crop/spatial coverage equal.',
                              'Guard is best effort, not a GPU lock; model allocations remain resident while yielding.'],
              'clips': clips}
    if candidate in ('community', 'community-v2'):
        report['trainedSourceHashes'] = assets['trainedSourceHashes']
        report['adaptationIdentity'] = {name: assets[name] for name in
                                        ('adaptationSha256', 'adaptationReportSha256', 'baselineSha256', 'trainingManifestSha256')}
    if candidate == 'community-v2':
        report['adaptationIdentity'].update({key: assets[key] for key in ('runSealSha256', 'exportEpoch')})
        if digest(Path(assets['adaptationRun']).parent / 'complete.json') != assets['runSealSha256']:
            raise ValueError('V2 run seal changed during comparison; no report written')
    if digest(corpus) != corpus_sha or any(digest(path) != source_hashes[name]
                                          for name, path in source_paths.items()):
        raise ValueError('Corpus or implementation changed during comparison; no report written')
    payload = json.dumps(report, indent=2, allow_nan=False) + '\n'
    # No progress/report/directory writes until every requested clip has completed.
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        stream.write(payload)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', choices=('x3d', 'mc3', 'videomae', 'community', 'community-v2'), required=True)
    parser.add_argument('--device', choices=('cpu', 'cuda'), required=True)
    parser.add_argument('--corpus', type=Path, default=ROOT / 'evaluation/corpus.json')
    parser.add_argument('--output', type=Path, required=True, help='New report path only; no overwrite')
    parser.add_argument('--snapshot', type=Path, help='Pinned cliffer1 local directory; VideoMAE only')
    parser.add_argument('--adaptation-run', type=Path, help='Complete community run or community-v2 milestone directory')
    parser.add_argument('--training-manifest-sha256', help='Required explicit training manifest SHA for community-v2')
    parser.add_argument('--yield-to-demo', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--cuda-memory-fraction', type=float, default=.35)
    parser.add_argument('--max-windows', type=int, default=1000, help='Hard total window budget; exceeding fails without report')
    parser.add_argument('--max-source-pixels', type=int, default=1920 * 1080)
    parser.add_argument('--max-buffer-pixels', type=int, default=100_000_000)
    args = parser.parse_args(argv)
    try:
        report = run(args.candidate, args.corpus, args.output, device=args.device, snapshot=args.snapshot,
                     yield_to_demo=args.yield_to_demo, cuda_memory_fraction=args.cuda_memory_fraction,
                     adaptation_run=args.adaptation_run, training_manifest_sha256=args.training_manifest_sha256,
                     limits=Limits(max_windows=args.max_windows, max_source_pixels=args.max_source_pixels,
                                   max_buffer_pixels=args.max_buffer_pixels))
        print(json.dumps({'status': report['status'], 'output': str(args.output),
                          'windows': report['windowCount'], 'pairedWindowSha256': report['pairedWindowSha256'],
                          'liveModelChanged': False}), flush=True)
        return 0
    except (ValueError, RuntimeError, OSError, KeyError, TypeError, ImportError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
