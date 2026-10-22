"""Offline X3D-M head/final-stage adaptation; no live model integration.

Only local, pinned official weights and validated temporal labels enter fitting.
Artifacts contain full CPU state dictionaries and load with weights_only=True.
"""
from collections import OrderedDict
from dataclasses import asdict, dataclass
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import random
import re
import time
from urllib.parse import unquote

import cv2
import numpy as np
import torch
from torch import nn

from .training_data import generate_windows, load_manifest
from .x3d_training import (BASE_SHA256, BASE_URL, CLASS_NAMES, PREPROCESS,
                           DemoYieldGuard, content_hash, file_hash, metrics,
                           preprocess_frames, read_window, resolve_device,
                           select_threshold, select_windows, window_identity)

KIND = 'official-x3d-m-finetune'
ARCHITECTURE = 'pytorchvideo-0.1.5-x3d_m-binary-logits'
VID_COHORT = 'vid-v2-unresolved-session-cohort'
ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class FineTuneConfig:
    seed: int = 17
    epochs: int = 5
    train_last_stage: bool = True
    backbone_learning_rate: float = 1e-5
    head_learning_rate: float = 1e-4
    weight_decay: float = .01
    accumulation_steps: int = 8
    class_weight: bool = True
    device: str = 'cpu'
    cuda_memory_fraction: float = .4
    yield_to_demo: bool = True
    input_cache_mib: int = 0

    def validate(self):
        if type(self.seed) is not int or not 0 <= self.seed < 2**32:
            raise ValueError('Seed must be an integer in [0, 2**32)')
        if type(self.epochs) is not int or not 1 <= self.epochs <= 1000:
            raise ValueError('Epoch count must be between one and 1000')
        if type(self.accumulation_steps) is not int or not 1 <= self.accumulation_steps <= 1024:
            raise ValueError('Accumulation steps must be between one and 1024')
        for value in (self.train_last_stage, self.class_weight, self.yield_to_demo):
            if type(value) is not bool:
                raise ValueError('Training switches must be explicit booleans')
        for value in (self.backbone_learning_rate, self.head_learning_rate):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= .01:
                raise ValueError('Learning rates must be finite, positive and at most .01')
        if self.backbone_learning_rate > self.head_learning_rate:
            raise ValueError('Backbone learning rate must not exceed head learning rate')
        if (type(self.weight_decay) not in (int, float) or not math.isfinite(self.weight_decay)
                or not 0 <= self.weight_decay <= 1):
            raise ValueError('Invalid weight decay')
        if (self.device not in ('cpu', 'cuda') or
                type(self.cuda_memory_fraction) not in (int, float) or
                not math.isfinite(self.cuda_memory_fraction) or not 0 < self.cuda_memory_fraction <= 1):
            raise ValueError('Invalid device or CUDA memory fraction')
        if self.device == 'cuda' and not self.yield_to_demo:
            raise ValueError('CUDA fine-tuning requires DemoYieldGuard cooperation')
        if type(self.input_cache_mib) is not int or not 0 <= self.input_cache_mib <= 4096:
            raise ValueError('Input cache must be an integer between zero and 4096 MiB')


class FrameCache:
    """Bounded CPU-only LRU of decoded frames, never model features/gradients.

    Immutable arrays preserve repeated preprocessing. Keys bind exact source
    content and temporal bounds; reading evaluation still occurs only when its
    existing caller permits it. An oversized window is returned without caching.
    """

    def __init__(self, reader, budget_mib):
        if type(budget_mib) is not int or not 1 <= budget_mib <= 4096:
            raise ValueError('Frame cache requires a positive bounded MiB budget')
        self.reader = reader
        self.limit = budget_mib * 1024**2
        self.entries = OrderedDict()
        self.bytes = self.hits = self.misses = self.evictions = self.oversize = 0

    def __call__(self, window):
        key = (str(window.path), window.sha256, window.start_seconds, window.end_seconds)
        if key in self.entries:
            self.hits += 1
            self.entries.move_to_end(key)
            return self.entries[key][0]
        self.misses += 1
        frames = tuple(self.reader(window))
        if not frames or any(not isinstance(frame, np.ndarray) or frame.dtype != np.uint8
                             or frame.ndim != 3 or frame.shape[2] != 3 for frame in frames):
            raise ValueError('Frame cache requires decoded uint8 BGR frames')
        size = sum(frame.nbytes for frame in frames)
        if size > self.limit:
            self.oversize += 1
            return frames
        while self.bytes + size > self.limit:
            _, (_, removed) = self.entries.popitem(last=False)
            self.bytes -= removed
            self.evictions += 1
        for frame in frames:
            frame.setflags(write=False)
        self.entries[key] = (frames, size)
        self.bytes += size
        return frames

    def summary(self):
        return {'kind': 'immutable-decoded-BGR-frames-in-CPU-RAM',
                'budgetMiB': self.limit / 1024**2, 'residentMiB': self.bytes / 1024**2,
                'entries': len(self.entries), 'hits': self.hits, 'misses': self.misses,
                'evictions': self.evictions, 'oversizeReads': self.oversize}


def training_device(config):
    if config.device == 'cuda':
        workspace = os.environ.get('CUBLAS_WORKSPACE_CONFIG')
        if workspace not in (None, ':4096:8', ':16:8'):
            raise ValueError('Unsupported CUBLAS_WORKSPACE_CONFIG for seeded training')
        if workspace is None:
            if torch.cuda.is_initialized():
                raise RuntimeError('Set CUBLAS_WORKSPACE_CONFIG before CUDA initialization; use a fresh training process')
            os.environ['CUBLAS_WORKSPACE_CONFIG'] = ':4096:8'
    return resolve_device(config.device, config.cuda_memory_fraction)


def seed_everything(seed, device='cpu'):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(2)
    cv2.setNumThreads(1)
    # Torch 2.5.1 has no strictly deterministic CUDA AvgPool3d backward,
    # which the official X3D head requires. Warn explicitly, do not promise
    # bitwise CUDA reproducibility or replace the pinned architecture's pool.
    torch.use_deterministic_algorithms(True, warn_only=device == 'cuda')
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True


def binary_model():
    """Construct trusted installed architecture without downloading anything."""
    if version('pytorchvideo') != '0.1.5':
        raise ValueError('This candidate requires pinned pytorchvideo==0.1.5')
    from pytorchvideo.models.hub import x3d_m
    model = x3d_m(pretrained=False)
    model.blocks[-1].proj = nn.Linear(2048, 2)
    model.blocks[-1].activation = None  # CrossEntropyLoss consumes logits.
    return model


def official_model(checkpoint):
    # Hash before torch.load; never use unrestricted pickle or hub downloads.
    if file_hash(checkpoint) != BASE_SHA256:
        raise ValueError('Official X3D-M checkpoint checksum mismatch')
    model = binary_model()
    state = torch.load(checkpoint, map_location='cpu', weights_only=True)['model_state']
    # Strictly verify the complete original 400-class checkpoint before replacing
    # its classifier. The projected pooling head remains official initialization.
    binary = model.blocks[-1].proj
    model.blocks[-1].proj = nn.Linear(2048, 400)
    model.load_state_dict(state, strict=True)
    model.blocks[-1].proj = binary
    return model


def training_mode(model, train_last_stage):
    """Train projected pooling + binary head, optionally final residual stage.

    Frozen prefix remains eval. Every BN's affine parameters AND running stats
    stay frozen, including those in otherwise trainable blocks.
    """
    model.eval().requires_grad_(False)
    blocks = model.blocks
    if len(blocks) < 3 or not isinstance(blocks[-1].proj, nn.Linear) or blocks[-1].proj.out_features != 2:
        raise ValueError('Expected X3D blocks with binary logits head')
    if blocks[-1].activation is not None:
        raise ValueError('Fine-tuning requires logits, without a head activation')
    blocks[-1].train().requires_grad_(True)
    if train_last_stage:
        blocks[-2].train().requires_grad_(True)
    for module in model.modules():
        if isinstance(module, nn.modules.batchnorm._BatchNorm):
            module.eval().requires_grad_(False)
    return [name for name, parameter in model.named_parameters() if parameter.requires_grad]


def _cooperate(device, guard):
    # Complete queued kernels before reading demo health, so yielding cannot
    # leave this process's previous microbatch executing in the background.
    if device.type == 'cuda':
        torch.cuda.synchronize(device)
    if guard is not None:
        guard()


def _logits(model, tensor):
    logits = model(tensor)
    if logits.shape != (1, 2) or not torch.isfinite(logits).all():
        raise ValueError('Expected finite batch-one binary logits')
    return logits


def fit(model, windows, config, *, reader=read_window, preprocess=preprocess_frames, yield_guard=None):
    """Fit only train windows, using exact weighted-mean accumulation groups.

    In particular weighted CE(mean) on individual batch-one samples would cancel
    class weighting. Sum losses instead and divide by the actual group's total
    target weight, including an incomplete final accumulation group.
    """
    config.validate()
    windows = tuple(windows)
    if any(window.split != 'train' for window in windows):
        raise ValueError('Fitting accepts train windows only; no holdout/calibration fitting')
    if {window.label for window in windows} != {0, 1}:
        raise ValueError('Training requires both binary classes')
    if config.yield_to_demo and yield_guard is None:
        raise ValueError('Requested demo cooperation requires a yield guard')
    device = training_device(config)
    seed_everything(config.seed, config.device)
    _cooperate(device, yield_guard)
    model.to(device)
    trainable_names = training_mode(model, config.train_last_stage)
    head_ids = {id(parameter) for parameter in model.blocks[-1].parameters()}
    trainable = [parameter for parameter in model.parameters() if parameter.requires_grad]
    head = [parameter for parameter in trainable if id(parameter) in head_ids]
    backbone = [parameter for parameter in trainable if id(parameter) not in head_ids]
    groups = [{'params': head, 'lr': config.head_learning_rate}]
    if backbone:
        groups.append({'params': backbone, 'lr': config.backbone_learning_rate})
    optimizer = torch.optim.AdamW(groups, weight_decay=config.weight_decay)
    labels = torch.tensor([window.label for window in windows], dtype=torch.long)
    counts = torch.bincount(labels, minlength=2).float()
    weights = len(windows) / (2 * counts) if config.class_weight else torch.ones(2)
    criterion = nn.CrossEntropyLoss(weight=weights.to(device), reduction='sum')
    generator = torch.Generator().manual_seed(config.seed)
    history = []
    steps = 0
    for epoch in range(config.epochs):
        training_mode(model, config.train_last_stage)
        order = torch.randperm(len(windows), generator=generator).tolist()
        total_loss = 0.
        for offset in range(0, len(order), config.accumulation_steps):
            indices = order[offset:offset + config.accumulation_steps]
            denominator = float(weights[labels[indices]].sum())
            optimizer.zero_grad(set_to_none=True)
            for index in indices:
                tensor = preprocess(reader(windows[index])).to(device)
                _cooperate(device, yield_guard)
                loss = criterion(_logits(model, tensor), labels[index:index + 1].to(device))
                if not torch.isfinite(loss):
                    raise ValueError('Training loss is not finite')
                (loss / denominator).backward()
                total_loss += float(loss.detach().cpu())
                del tensor, loss
                _cooperate(device, yield_guard)
            torch.nn.utils.clip_grad_norm_(trainable, 1., error_if_nonfinite=True)
            _cooperate(device, yield_guard)
            optimizer.step()
            steps += 1
        epoch_loss = total_loss / float(weights[labels].sum())
        history.append(epoch_loss)
        print(json.dumps({'stage': 'finetune', 'epoch': epoch + 1,
                          'epochs': config.epochs, 'weightedTrainLoss': epoch_loss}), flush=True)
    optimizer.zero_grad(set_to_none=True)
    model.eval()
    _cooperate(device, yield_guard)
    return {'selection': 'fixed epochs; train split only', 'batchSize': 1,
            'optimizer': 'AdamW', 'optimizerSteps': steps,
            'classWeights': weights.tolist() if config.class_weight else None,
            'classCounts': counts.int().tolist(), 'epochWeightedLoss': history,
            'accumulationReduction': 'sum weighted CE / actual group sum of target weights; includes tail',
            'batchNorm': 'all affine parameters and running statistics frozen',
            'trainableParameters': trainable_names,
            'trainableParameterCount': sum(parameter.numel() for parameter in trainable)}


@torch.inference_mode()
def predict_windows(model, windows, *, reader=read_window, preprocess=preprocess_frames, yield_guard=None):
    model.eval()
    device = next(model.parameters()).device
    scores = []
    for window in windows:
        tensor = preprocess(reader(window)).to(device)
        _cooperate(device, yield_guard)
        scores.append(float(_logits(model, tensor).softmax(-1)[0, 1].cpu()))
    return np.asarray(scores, dtype=np.float32)


def validate_vid_cohort(manifest):
    """VID has unknown actor/session lineage; filenames cannot create splits."""
    sources = {source.id for source in manifest.sources
               if source.id.lower().startswith('vid') or
               '10.7910/dvn/n4lnzd' in unquote(source.url).lower()}
    for recording in manifest.recordings:
        if recording.source_id in sources:
            if recording.split != 'train' or recording.recording_group != VID_COHORT:
                raise ValueError('All VID footage must remain in one unresolved training cohort')


def _snapshots(provenance_files):
    paths = {'source/x3d_finetune.py': Path(__file__),
             'source/x3d_training.py': Path(__file__).with_name('x3d_training.py'),
             'source/training_data.py': Path(__file__).with_name('training_data.py'),
             'source/finetune_x3d.py': ROOT / 'finetune_x3d.py'}
    for index, path in enumerate(provenance_files):
        paths[f'provenance/{index:02d}-{Path(path).name}'] = Path(path)
    return {name: path.read_bytes() for name, path in paths.items()}


def run(manifest_path, data_root, checkpoint, output_dir, *, config=None,
        provenance_files=(), max_train_windows=None, model_factory=official_model,
        reader=read_window, preprocess=preprocess_frames, yield_guard=None):
    config = config or FineTuneConfig()
    config.validate()
    device = training_device(config)
    seed_everything(config.seed, config.device)
    guard = yield_guard or (DemoYieldGuard() if config.yield_to_demo else None)
    _cooperate(device, guard)
    manifest_path, output_dir = Path(manifest_path), Path(output_dir)
    snapshots = _snapshots(provenance_files)
    manifest_bytes = manifest_path.read_bytes()
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    manifest = load_manifest(manifest_path, data_root, verify_files=True)
    if file_hash(manifest_path) != manifest_sha:
        raise ValueError('Manifest changed during validation')
    validate_vid_cohort(manifest)
    if file_hash(checkpoint) != BASE_SHA256:
        raise ValueError('Official X3D-M checkpoint checksum mismatch')
    all_windows = {split: generate_windows(manifest, split) for split in ('train', 'calibration', 'holdout')}
    windows = dict(all_windows)
    windows['train'] = select_windows(windows['train'], max_train_windows, config.seed)
    if {window.label for window in windows['train']} != {0, 1}:
        raise ValueError('Reviewed training windows must contain both binary classes')
    snapshots['manifest.json'] = manifest_bytes
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in snapshots.items()}
    output_dir.mkdir(parents=True, exist_ok=False)
    for name, data in snapshots.items():
        destination = output_dir / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    started = time.perf_counter()
    input_cache = FrameCache(reader, config.input_cache_mib) if config.input_cache_mib else None
    if input_cache is not None:
        reader = input_cache
    if device.type == 'cuda':
        torch.cuda.reset_peak_memory_stats(device)
    _cooperate(device, guard)
    model = model_factory(checkpoint)
    training = fit(model, windows['train'], config, reader=reader,
                   preprocess=preprocess, yield_guard=guard)
    labels = {split: np.array([window.label for window in entries], dtype=np.int64)
              for split, entries in windows.items()}
    scores = {split: predict_windows(model, windows[split], reader=reader,
                                     preprocess=preprocess, yield_guard=guard)
              for split in ('train', 'calibration')}
    threshold, calibration = select_threshold(scores['calibration'], labels['calibration'])
    # Holdout is not decoded until fixed fitting and threshold selection finish.
    scores['holdout'] = predict_windows(model, windows['holdout'], reader=reader,
                                        preprocess=preprocess, yield_guard=guard)
    artifact = {'schemaVersion': 1, 'kind': KIND, 'architecture': ARCHITECTURE,
                'baseSha256': BASE_SHA256, 'manifestSha256': manifest_sha,
                'snapshotHashes': hashes, 'config': asdict(config), 'preprocessing': PREPROCESS,
                'classNames': CLASS_NAMES, 'threshold': threshold,
                'model_state': {name: tensor.detach().cpu().clone() for name, tensor in model.state_dict().items()}}
    torch.save(artifact, output_dir / 'candidate-state.pt')
    gpu = None
    if device.type == 'cuda':
        _cooperate(device, guard)
        gpu = {'name': torch.cuda.get_device_name(device), 'cudaMemoryFraction': config.cuda_memory_fraction,
               'allocatorLimitMiB': torch.cuda.get_device_properties(device).total_memory * config.cuda_memory_fraction / 1024**2,
               'peakAllocatedMiB': torch.cuda.max_memory_allocated(device) / 1024**2,
               'peakReservedMiB': torch.cuda.max_memory_reserved(device) / 1024**2,
               'scope': 'Measured this process allocator only; excludes demo, driver and other processes'}
    report = {key: value for key, value in artifact.items() if key != 'model_state'}
    report.update({'status': 'experimental-offline-candidate', 'device': config.device,
                   'precision': 'float32', 'base': {'url': BASE_URL, 'sha256': BASE_SHA256},
                   'training': training, 'calibration': calibration, 'gpu': gpu,
                   'inputCache': input_cache.summary() if input_cache is not None else None,
                   'determinism': {'fixedSeed': config.seed, 'cudnnDeterministic': True,
                                   'cudnnBenchmark': False,
                                   'algorithmPolicy': 'warn on unsupported CUDA kernels' if config.device == 'cuda' else 'strict',
                                   'bitwiseCudaReproducibilityClaimed': False,
                                   'cublasWorkspaceConfig': os.environ.get('CUBLAS_WORKSPACE_CONFIG') if config.device == 'cuda' else None},
                   'candidateSha256': file_hash(output_dir / 'candidate-state.pt'),
                   'elapsedSeconds': round(time.perf_counter() - started, 3),
                   'holdoutUsedForSelection': False, 'liveModelChanged': False,
                   'smoke': max_train_windows is not None, 'maxTrainWindows': max_train_windows,
                   'versions': {'torch': str(torch.__version__), 'pytorchvideo': version('pytorchvideo'),
                                'numpy': np.__version__, 'opencv': cv2.__version__},
                   'limitations': ['Training fit is not held-out accuracy or a deployment gate.',
                                   'VID labels are provisional assistant visual screening, not human ground truth or continuous review.',
                                   'VID actor/session lineage is unknown; all VID remains one training cohort.',
                                   'Diagnostic failures must remain visible; no automatic threshold relaxation or promotion.',
                                   'Official checkpoint-specific rights and participant release scope are not independently cleared.'],
                   'splits': {}})
    for split, entries in windows.items():
        identities = [window_identity(window) for window in entries]
        report['splits'][split] = {
            'metrics': metrics(scores[split], labels[split], threshold),
            'availableWindows': len(all_windows[split]), 'selectedWindows': len(entries),
            'recordings': len({window.recording_id for window in entries}),
            'recordingGroups': len({window.recording_group for window in entries}),
            'partial': len(entries) != len(all_windows[split]),
            'selectedSubsetSha256': content_hash(identities),
            'windows': [{**identity, 'score': float(score)} for identity, score in zip(identities, scores[split])]}
    (output_dir / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return report


def _digest(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('Invalid SHA-256 digest')
    return value


def load_candidate(run_dir, *, model_factory=binary_model):
    """Verify report, snapshots and safe full state; no base file is needed."""
    run_dir = Path(run_dir).resolve()
    report = json.loads((run_dir / 'report.json').read_text(encoding='utf-8'))
    if not isinstance(report, dict):
        raise ValueError('Candidate report must be an object')
    path = run_dir / 'candidate-state.pt'
    if file_hash(path) != _digest(report.get('candidateSha256')):
        raise ValueError('Candidate checksum mismatch')
    hashes = report.get('snapshotHashes')
    if not isinstance(hashes, dict) or not hashes or 'manifest.json' not in hashes:
        raise ValueError('Missing provenance snapshot hashes')
    for name, digest in hashes.items():
        snapshot = (run_dir / name).resolve()
        if not snapshot.is_relative_to(run_dir) or snapshot == run_dir:
            raise ValueError('Snapshot path escapes candidate directory')
        if file_hash(snapshot) != _digest(digest):
            raise ValueError('Snapshot checksum mismatch')
    if hashes['manifest.json'] != _digest(report.get('manifestSha256')):
        raise ValueError('Manifest checksum mismatch')
    artifact = torch.load(path, map_location='cpu', weights_only=True)
    if not isinstance(artifact, dict):
        raise ValueError('Candidate artifact must be an object')
    expected = {'schemaVersion': 1, 'kind': KIND, 'architecture': ARCHITECTURE,
                'baseSha256': BASE_SHA256, 'preprocessing': PREPROCESS, 'classNames': CLASS_NAMES}
    for key, value in expected.items():
        if report.get(key) != value or artifact.get(key) != value:
            raise ValueError('Unsupported candidate contract: ' + key)
    for key in ('manifestSha256', 'snapshotHashes', 'config', 'threshold'):
        if artifact.get(key) != report.get(key):
            raise ValueError('Candidate does not match report: ' + key)
    FineTuneConfig(**artifact['config']).validate()
    threshold = artifact['threshold']
    if type(threshold) not in (int, float) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError('Invalid threshold')
    state = artifact.get('model_state')
    if not isinstance(state, dict) or not state:
        raise ValueError('Missing full model state')
    for value in state.values():
        if not isinstance(value, torch.Tensor) or value.device.type != 'cpu' or not torch.isfinite(value).all():
            raise ValueError('Invalid candidate state tensor')
    cv2.setNumThreads(1)
    torch.set_num_threads(2)
    model = model_factory().cpu()
    expected_state = model.state_dict()
    if state.keys() != expected_state.keys() or any(
            state[name].shape != value.shape or state[name].dtype != value.dtype
            for name, value in expected_state.items()):
        raise ValueError('Candidate state shape/dtype mismatch')
    model.load_state_dict(state, strict=True)
    model.eval().requires_grad_(False)
    return model, report


class FineTuneCandidate:
    """CPU diagnostics contract: predict(uint8 BGR frames) -> scalar class-1 score."""

    def __init__(self, run_dir, *, model_factory=binary_model):
        self.model, self.report = load_candidate(run_dir, model_factory=model_factory)
        self.device = 'cpu'

    @torch.inference_mode()
    def predict(self, frames):
        return float(_logits(self.model, preprocess_frames(frames)).softmax(-1)[0, 1])


def diagnose(run_dir, corpus, output, *, candidate_factory=FineTuneCandidate, window_reader=None):
    """Reuse inspected corpus's causal windows; never fit or change thresholds."""
    from compare_x3d_training import event_overlaps, windows
    from evaluate import validate_manifest
    output, corpus = Path(output), Path(corpus)
    if output.exists():
        raise FileExistsError(output)
    cv2.setNumThreads(1)
    records = json.loads(corpus.read_text(encoding='utf-8'))
    if not isinstance(records, list) or not records:
        raise ValueError('Diagnostic corpus must contain recordings')
    validate_manifest(records)
    for clip in records:
        media = (corpus.parent / clip['path']).resolve()
        if not media.is_file() or file_hash(media) != _digest(clip['sha256']):
            raise ValueError('Diagnostic media checksum mismatch: ' + clip['id'])
        crop = clip.get('crop')
        if crop is not None and (not isinstance(crop, list) or len(crop) != 4 or
                any(type(value) not in (int, float) or not math.isfinite(value) for value in crop) or
                not 0 <= crop[0] < crop[2] <= 1 or not 0 <= crop[1] < crop[3] <= 1):
            raise ValueError('Invalid diagnostic crop')
    candidate = candidate_factory(run_dir)
    threshold = candidate.report['threshold']
    report = {'schemaVersion': 1, 'status': 'diagnostic-only', 'device': 'cpu',
              'candidateSha256': candidate.report['candidateSha256'],
              'trainingReportSha256': file_hash(Path(run_dir) / 'report.json'),
              'corpusSha256': file_hash(corpus), 'threshold': threshold,
              'thresholdFittedHere': False, 'liveModelChanged': False,
              'implementationSha256': file_hash(__file__),
              'windowPolicyImplementationSha256': file_hash(ROOT / 'compare_x3d_training.py'),
              'limitations': ['Previously inspected corpus is diagnostic, not held-out accuracy.',
                              'Crop variants are not independent; event overlaps are not binary window truth.',
                              'Scores are uncalibrated; no automatic promotion or threshold relaxation.'], 'clips': {}}
    for clip in records:
        rows = []
        for timestamp, start, frames in (window_reader or windows)(clip, corpus):
            before = time.perf_counter()
            score = float(candidate.predict(frames))
            if not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError('Invalid diagnostic score')
            rows.append({'timestampMs': timestamp, 'windowStartMs': start,
                         'labelledEventOverlaps': event_overlaps(clip, start, timestamp),
                         'candidate': {'score': score, 'review': score > threshold,
                                       'inferenceMs': round((time.perf_counter() - before) * 1000, 3)}})
        report['clips'][clip['id']] = {'sourceGroup': clip['sourceGroup'],
                                      'historicalSplit': clip['split'], 'syntheticCrop': bool(clip.get('crop')),
                                      'sha256': clip['sha256'], 'windows': len(rows),
                                      'candidateReviewWindows': sum(row['candidate']['review'] for row in rows),
                                      'samples': rows}
        print(json.dumps({'stage': 'diagnostics', 'clip': clip['id'], 'windows': len(rows)}), flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    return report
