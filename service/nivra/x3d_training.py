"""Offline linear probing of the official frozen Kinetics X3D-M.

Candidates produced here are separate artifacts, never replacements for the
running public model. CPU is the default; CUDA requires explicit selection.
"""
from collections import defaultdict, deque
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import random
import time
from urllib.request import urlopen

import cv2
import numpy as np
import torch

from .training_data import generate_windows, load_manifest

BASE_URL = 'https://dl.fbaipublicfiles.com/pytorchvideo/model_zoo/kinetics/X3D_M.pyth'
BASE_SHA256 = 'eb9583d5f5a988a5c5f06f75760b070a5c9715794bd3b0536b78bd30595dcf67'
PREPROCESS = {
    'version': 1, 'color': 'RGB', 'frames': 16, 'size': [224, 224],
    'resize': 'opencv-inter-linear-square', 'scale': 255,
    'mean': [.45, .45, .45], 'std': [.225, .225, .225],
    'temporalSampling': 'uniform-linspace-floor-from-100ms-source-samples',
    'windowSeconds': 4, 'minimumSpanMs': 3800,
}
CLASS_NAMES = ['non-violent', 'violent']


def resolve_device(device, cuda_memory_fraction=.4):
    if device not in ('cpu', 'cuda'):
        raise ValueError('Device must be cpu or cuda')
    if (type(cuda_memory_fraction) not in (int, float) or
            not math.isfinite(cuda_memory_fraction) or not 0 < cuda_memory_fraction <= 1):
        raise ValueError('CUDA memory fraction must be greater than zero and at most one')
    if device == 'cuda':
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA was requested but is unavailable; no CPU fallback was used')
        torch.cuda.set_per_process_memory_fraction(cuda_memory_fraction)
    return torch.device(device)


class DemoYieldGuard:
    """Best-effort cooperation with the existing demo, not an exclusive GPU lock."""

    def __init__(self, *, timeout=60, fetch=None, clock=time.monotonic, sleep=time.sleep):
        self.timeout, self.clock, self.sleep = timeout, clock, sleep
        self.fetch = fetch or self._fetch

    @staticmethod
    def _fetch():
        with urlopen('http://127.0.0.1:8765/api/v2/fight/health', timeout=3) as response:
            return json.load(response)

    def __call__(self):
        started = self.clock()
        while True:
            try:
                health = self.fetch()
                busy = health['busy']
                if type(busy) is not bool:
                    raise ValueError('Invalid health response')
            except Exception as error:
                raise RuntimeError('Cannot verify demo availability; --yield-to-demo stopped training') from error
            if not busy:
                return
            elapsed = self.clock() - started
            if elapsed >= self.timeout:
                raise RuntimeError('Demo stayed busy for 60 seconds; training stopped without changing it')
            print(json.dumps({'stage': 'yielding-to-demo', 'waitSeconds': round(elapsed, 1)}), flush=True)
            self.sleep(min(1, self.timeout - elapsed))


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def content_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def preprocess_frames(frames):
    """Match the deployed candidate's RGB, sampling and normalization contract."""
    if not frames:
        raise ValueError('A window must contain frames')
    indices = np.linspace(0, len(frames) - 1, 16).astype(int)
    images = []
    for index in indices:
        frame = frames[index]
        if not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError('Frames must be uint8 BGR images')
        images.append(cv2.resize(frame[:, :, ::-1], (224, 224)))
    tensor = torch.from_numpy(np.stack(images)).permute(3, 0, 1, 2).float() / 255
    return ((tensor - .45) / .225)[None]


def read_window(window):
    """Decode a bounded local source window; never pad a short recording."""
    capture = cv2.VideoCapture(str(window.path))
    frames = []
    last_sample = -math.inf
    first_sample = None
    try:
        if not capture.isOpened():
            raise ValueError(f'Cannot decode recording {window.recording_id}')
        fps = capture.get(cv2.CAP_PROP_FPS)
        if not math.isfinite(fps) or not 0 < fps <= 240:
            raise ValueError(f'Unsupported frame rate for {window.recording_id}')
        capture.set(cv2.CAP_PROP_POS_MSEC, window.start_seconds * 1000)
        previous = -math.inf
        for _ in range(2000):
            ok, frame = capture.read()
            if not ok:
                break
            timestamp = capture.get(cv2.CAP_PROP_POS_MSEC)
            if not math.isfinite(timestamp) or timestamp <= previous:
                position = capture.get(cv2.CAP_PROP_POS_FRAMES)
                timestamp = (position - 1) * 1000 / fps
            if not math.isfinite(timestamp) or timestamp <= previous:
                raise ValueError(f'Non-increasing decoder timestamp for {window.recording_id}')
            if math.isfinite(previous) and timestamp - previous > 1200:
                raise ValueError(f'Discontinuous decoder timestamps for {window.recording_id}')
            previous = timestamp
            if timestamp + .01 < window.start_seconds * 1000:
                continue
            if timestamp >= window.end_seconds * 1000 - .01:
                break
            if timestamp - last_sample < 100 - .01:
                continue
            if first_sample is None:
                first_sample = timestamp
            last_sample = timestamp
            frames.append(cv2.resize(frame, (224, 224)))
        else:
            raise ValueError(f'Decoder frame budget exceeded for {window.recording_id}')
    finally:
        capture.release()
    if len(frames) < 8 or first_sample is None or last_sample - first_sample < 3800:
        raise ValueError(f'No continuous four-second window for {window.recording_id}')
    return frames


class FrozenX3D:
    """Official frozen weights; return CPU float32 [batch, 2048] features."""

    def __init__(self, checkpoint, *, device='cpu', cuda_memory_fraction=.4):
        if file_hash(checkpoint) != BASE_SHA256:
            raise ValueError('Official X3D-M checkpoint checksum mismatch')
        self.device = resolve_device(device, cuda_memory_fraction)
        torch.set_num_threads(2)
        from pytorchvideo.models.hub import x3d_m
        state = torch.load(checkpoint, map_location='cpu', weights_only=True)
        self.model = x3d_m(pretrained=False)
        self.model.load_state_dict(state['model_state'], strict=True)
        self.model.blocks[-1].proj = torch.nn.Identity()
        self.model.blocks[-1].activation = None
        self.model.eval().requires_grad_(False).to(self.device)

    @torch.inference_mode()
    def __call__(self, tensor):
        features = self.model(tensor.to(self.device))
        if features.ndim != 2 or features.shape[1] != 2048 or not torch.isfinite(features).all():
            raise ValueError('Invalid frozen feature output')
        return features.cpu().numpy()


def window_identity(window):
    return {'recordingId': window.recording_id, 'recordingGroup': window.recording_group,
            'sha256': window.sha256, 'split': window.split,
            'startSeconds': window.start_seconds, 'endSeconds': window.end_seconds,
            'label': window.label}


def select_windows(windows, maximum, seed):
    """Bound smoke work with deterministic label/recording round-robin selection."""
    if maximum is not None and (type(maximum) is not int or maximum < 2):
        raise ValueError('Window limit must be at least two')
    if maximum is None or len(windows) <= maximum:
        return tuple(windows)
    buckets = defaultdict(list)
    for window in windows:
        buckets[(window.label, window.recording_group)].append(window)
    rng = random.Random(seed)
    queues = {}
    for key in sorted(buckets):
        entries = buckets[key]
        rng.shuffle(entries)
        queues[key] = deque(entries)
    groups = {label: deque(key for key in sorted(queues) if key[0] == label)
              for label in (0, 1)}
    selected = []
    while len(selected) < maximum and any(groups.values()):
        for label in (0, 1):
            if not groups[label] or len(selected) >= maximum:
                continue
            key = groups[label].popleft()
            selected.append(queues[key].popleft())
            if queues[key]:
                groups[label].append(key)
    return tuple(selected)


def extract_features(windows, extractor, cache_dir, manifest_sha, *, reader=read_window,
                     device='cpu', yield_guard=None):
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    features = []
    for index, window in enumerate(windows, 1):
        key = content_hash({'window': window_identity(window), 'baseSha256': BASE_SHA256,
                            'manifestSha256': manifest_sha, 'preprocessing': PREPROCESS,
                            'backend': {'device': device, 'dtype': 'float32', 'torch': str(torch.__version__)}})
        path = cache_dir / (key + '.npy')
        if path.exists():
            vector = np.load(path, allow_pickle=False)
        else:
            tensor = preprocess_frames(reader(window))
            if yield_guard:
                yield_guard()
            vector = np.asarray(extractor(tensor), dtype=np.float32)
            if vector.shape == (1, 2048):
                vector = vector[0]
            if vector.shape != (2048,) or not np.isfinite(vector).all():
                raise ValueError('Invalid feature vector')
            temporary = path.with_suffix('.tmp')
            with temporary.open('wb') as stream:
                np.save(stream, vector, allow_pickle=False)
            temporary.replace(path)
        if vector.shape != (2048,) or vector.dtype != np.float32 or not np.isfinite(vector).all():
            raise ValueError('Invalid cached feature vector')
        features.append(vector)
        print(json.dumps({'stage': 'features', 'split': window.split,
                          'completed': index, 'total': len(windows)}), flush=True)
    return (np.stack(features) if features else np.empty((0, 2048), dtype=np.float32))


def _arrays(features, labels, *, require_both=False):
    features = np.asarray(features, dtype=np.float32)
    labels = np.asarray(labels)
    if (features.ndim != 2 or features.shape[1] != 2048 or len(features) != len(labels)
            or labels.ndim != 1 or not np.isfinite(features).all()
            or not np.isin(labels, [0, 1]).all()):
        raise ValueError('Invalid binary feature dataset')
    if require_both and set(labels.tolist()) != {0, 1}:
        raise ValueError('Training requires both binary classes')
    return features, labels.astype(np.int64)


def fit_head(features, labels, *, seed=17, epochs=100, learning_rate=.01,
             weight_decay=.01, class_weight=False, device='cpu', cuda_memory_fraction=.4):
    features, labels = _arrays(features, labels, require_both=True)
    if type(epochs) is not int or not 1 <= epochs <= 10_000:
        raise ValueError('Epoch count must be between one and 10000')
    if not 0 < learning_rate <= 1 or not 0 <= weight_decay <= 1:
        raise ValueError('Invalid optimizer settings')
    torch.set_num_threads(2)
    torch.manual_seed(seed)
    selected_device = resolve_device(device, cuda_memory_fraction)
    head = torch.nn.Linear(2048, 2).to(selected_device)
    x = torch.from_numpy(features).to(selected_device)
    y = torch.from_numpy(labels).to(selected_device)
    weights = None
    if class_weight:
        counts = torch.bincount(y, minlength=2).float()
        weights = len(y) / (2 * counts)
    criterion = torch.nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.AdamW(head.parameters(), lr=learning_rate, weight_decay=weight_decay)
    generator = torch.Generator().manual_seed(seed)
    loss_value = None
    head.train()
    for _ in range(epochs):
        order = torch.randperm(len(y), generator=generator)
        for indices in order.split(32):
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(head(x[indices]), y[indices])
            if not torch.isfinite(loss):
                raise ValueError('Training loss is not finite')
            loss.backward()
            torch.nn.utils.clip_grad_norm_(head.parameters(), 1)
            optimizer.step()
            loss_value = float(loss.detach().cpu())
    head.eval()
    return head, {'epochs': epochs, 'seed': seed, 'learningRate': learning_rate,
                  'weightDecay': weight_decay, 'batchSize': 32,
                  'device': device,
                  'classWeights': weights.tolist() if weights is not None else None,
                  'lastBatchLoss': loss_value, 'selection': 'fixed epochs; train split only'}


@torch.inference_mode()
def predict_head(head, features):
    features = np.asarray(features, dtype=np.float32)
    if features.shape == (0, 2048):
        return np.empty(0, dtype=np.float32)
    if features.ndim != 2 or features.shape[1] != 2048 or not np.isfinite(features).all():
        raise ValueError('Invalid features')
    device = next(head.parameters()).device
    scores = head(torch.from_numpy(features).to(device)).softmax(-1)[:, 1].cpu().numpy()
    if not np.isfinite(scores).all():
        raise ValueError('Invalid classifier scores')
    return scores


def select_threshold(scores, labels):
    """Use calibration only; strict > gives zero observed negative windows."""
    scores, labels = np.asarray(scores), np.asarray(labels)
    if (scores.ndim != 1 or labels.ndim != 1 or len(scores) != len(labels) or not np.isfinite(scores).all()
            or not np.isin(labels, [0, 1]).all() or (scores < 0).any() or (scores > 1).any()):
        raise ValueError('Invalid calibration data')
    if set(labels.tolist()) != {0, 1}:
        return .5, {'status': 'uncalibrated', 'reason': 'Calibration requires both classes',
                    'selectionSplit': None}
    threshold = float(scores[labels == 0].max())
    return threshold, {'status': 'calibration-selected', 'selectionSplit': 'calibration',
                       'objective': 'Minimize missed positive windows subject to zero observed false-positive windows',
                       'comparison': 'score > threshold',
                       'note': 'Zero observed calibration errors do not establish deployment false-alert rates.'}


def metrics(scores, labels, threshold):
    scores, labels = np.asarray(scores), np.asarray(labels)
    if len(scores) == 0:
        return {'status': 'not-available', 'windows': 0}
    predicted = scores > threshold
    positive = labels == 1
    tp = int((predicted & positive).sum())
    fp = int((predicted & ~positive).sum())
    fn = int((~predicted & positive).sum())
    tn = int((~predicted & ~positive).sum())
    precision = tp / (tp + fp) if tp + fp else 0.
    recall = tp / (tp + fn) if tp + fn else None
    return {'status': 'available', 'unit': 'labelled four-second windows', 'windows': len(scores),
            'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
            'accuracy': (tp + tn) / len(scores), 'precision': precision, 'recall': recall,
            'f1': 2 * precision * recall / (precision + recall) if recall and precision else 0.,
            'falseAlertsPerCameraHour': None, 'eventRecall': None}


def run(manifest_path, data_root, checkpoint, output_dir, *, seed=17, epochs=100,
        learning_rate=.01, class_weight=False, max_windows_per_split=None,
        device='cpu', cuda_memory_fraction=.4, yield_to_demo=False,
        extractor_factory=FrozenX3D, reader=read_window):
    # Freeze bytes at invocation, before decoding/fitting. The end-of-run report
    # must not hash a different file revision edited while this process works.
    module_path = Path(__file__)
    source_paths = {'x3d_training.py': module_path,
                    'training_data.py': module_path.with_name('training_data.py'),
                    'train_x3d.py': module_path.parents[1] / 'train_x3d.py'}
    source_bytes = {name: path.read_bytes() for name, path in source_paths.items()}
    source_hashes = {name: hashlib.sha256(data).hexdigest() for name, data in source_bytes.items()}
    selected_device = resolve_device(device, cuda_memory_fraction)
    yield_guard = DemoYieldGuard() if yield_to_demo else None
    if yield_guard:
        yield_guard()
    manifest_path = Path(manifest_path)
    # Validate provenance, split lineage, paths and all media hashes before model load.
    manifest = load_manifest(manifest_path, data_root, verify_files=True)
    manifest_sha = file_hash(manifest_path)
    if file_hash(checkpoint) != BASE_SHA256:
        raise ValueError('Official X3D-M checkpoint checksum mismatch')
    all_windows = {split: generate_windows(manifest, split) for split in ('train', 'calibration', 'holdout')}
    windows = {split: select_windows(entries, max_windows_per_split, seed)
               for split, entries in all_windows.items()}
    if {entry.label for entry in windows['train']} != {0, 1}:
        raise ValueError('Reviewed training windows must contain both classes')
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    source_dir = output_dir / 'source'
    source_dir.mkdir()
    for name, data in source_bytes.items():
        (source_dir / name).write_bytes(data)
    started = time.perf_counter()
    if device == 'cuda':
        torch.cuda.reset_peak_memory_stats()
        extractor = extractor_factory(checkpoint, device=device, cuda_memory_fraction=cuda_memory_fraction)
    else:
        extractor = extractor_factory(checkpoint)
    feature_sets = {}
    for split in ('train', 'calibration'):
        feature_sets[split] = extract_features(windows[split], extractor, output_dir / 'feature-cache',
                                               manifest_sha, reader=reader, device=device, yield_guard=yield_guard)
    labels = {split: np.array([entry.label for entry in entries], dtype=np.int64)
              for split, entries in windows.items()}
    if yield_guard:
        yield_guard()
    head, training = fit_head(feature_sets['train'], labels['train'], seed=seed, epochs=epochs,
                             learning_rate=learning_rate, class_weight=class_weight,
                             device=device, cuda_memory_fraction=cuda_memory_fraction)
    scores = {split: predict_head(head, feature_sets[split]) for split in ('train', 'calibration')}
    threshold, calibration = select_threshold(scores['calibration'], labels['calibration'])
    # Holdout is first decoded after all fitting and threshold selection complete.
    feature_sets['holdout'] = extract_features(windows['holdout'], extractor, output_dir / 'feature-cache',
                                              manifest_sha, reader=reader, device=device, yield_guard=yield_guard)
    scores['holdout'] = predict_head(head, feature_sets['holdout'])
    selected = {split: [window_identity(entry) for entry in entries] for split, entries in windows.items()}
    report = {
        'schemaVersion': 1, 'status': 'experimental-offline-candidate',
        'kind': 'official-frozen-x3d-m-linear-head', 'device': device, 'cpuThreads': 2,
        'precision': 'float32', 'yieldToDemo': yield_to_demo,
        'base': {'url': BASE_URL, 'sha256': BASE_SHA256,
                 'provenance': 'Official PyTorchVideo Kinetics-400 model zoo',
                 'codeLicense': 'Apache-2.0',
                 'weightsLicenseNote': 'Official release; no separate checkpoint-specific grant verified. Underlying training-video rights not established.'},
        'manifestSha256': manifest_sha, 'preprocessing': PREPROCESS, 'classNames': CLASS_NAMES,
        'dataWindowing': {'windowSeconds': 4, 'strideSeconds': 4,
                          'positiveFraction': .5, 'normalRequiresExplicitFullCoverage': True},
        'training': training, 'threshold': threshold, 'calibration': calibration,
        'holdoutUsedForSelection': False, 'liveModelChanged': False,
        'maxWindowsPerSplit': max_windows_per_split,
        'smoke': max_windows_per_split is not None,
        'implementationHashes': source_hashes,
        'implementationSourceDirectory': 'source',
        'versions': {'torch': str(torch.__version__), 'pytorchvideo': version('pytorchvideo'),
                     'numpy': np.__version__, 'opencv': cv2.__version__},
        'splits': {}, 'elapsedSeconds': round(time.perf_counter() - started, 3),
        'limitations': ['Window metrics are not incident counts or camera-hour false-alert rates.',
                        'No public model promotion, classroom validation or commercial-rights clearance.',
                        'The head is trained on frozen official action features; it is not full-backbone fine-tuning.'],
    }
    if selected_device.type == 'cuda':
        torch.cuda.synchronize()
        report['gpu'] = {'name': torch.cuda.get_device_name(),
                         'cudaMemoryFraction': cuda_memory_fraction,
                         'allocatorLimitMiB': torch.cuda.get_device_properties(0).total_memory * cuda_memory_fraction / 1024**2,
                         'peakAllocatedMiB': torch.cuda.max_memory_allocated() / 1024**2,
                         'peakReservedMiB': torch.cuda.max_memory_reserved() / 1024**2,
                         'memoryScope': 'This training process only; excludes the live service, driver and other processes.',
                         'cudaVersion': torch.version.cuda,
                         'cudnnVersion': torch.backends.cudnn.version()}
    else:
        report['gpu'] = None
    for split in windows:
        partial = len(windows[split]) != len(all_windows[split])
        report['splits'][split] = {
            'metrics': metrics(scores[split], labels[split], threshold),
            'availableWindows': len(all_windows[split]), 'selectedWindows': len(windows[split]),
            'partial': partial, 'evaluation': 'smoke-diagnostic' if partial else 'complete-listed-split',
            'recordingGroups': len({entry.recording_group for entry in windows[split]}),
            'selectedSubsetSha256': content_hash(selected[split]),
            'windows': [{**identity, 'score': float(score)} for identity, score in zip(selected[split], scores[split])],
        }
    artifact = {'schemaVersion': 1, 'kind': report['kind'], 'baseSha256': BASE_SHA256,
                'manifestSha256': manifest_sha, 'preprocessing': PREPROCESS,
                'classNames': CLASS_NAMES, 'threshold': threshold,
                'head_state': {name: tensor.detach().cpu().clone() for name, tensor in head.state_dict().items()}}
    torch.save(artifact, output_dir / 'candidate-head.pt')
    report['candidateSha256'] = file_hash(output_dir / 'candidate-head.pt')
    (output_dir / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    return report
