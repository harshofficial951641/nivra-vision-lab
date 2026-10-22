"""Fixed offline head-only adaptation of the pinned community X3D-M.

Keep Softmax BEFORE output_pool and the entire model in eval mode. Training
consumes retained output probabilities, never pooled-feature surrogate logits.
"""
from dataclasses import asdict, dataclass
import hashlib
from importlib.metadata import version
import json
from pathlib import Path, PureWindowsPath
import re
import time

import numpy as np
import torch
from torch import nn

from .training_data import generate_windows, load_manifest
from .x3d_candidate import CHECKSUM, SOURCE, scalar
from .x3d_finetune import FrameCache, seed_everything, training_device, validate_vid_cohort
from .x3d_training import (CLASS_NAMES, PREPROCESS, DemoYieldGuard, content_hash,
                           file_hash, preprocess_frames, read_window, resolve_device,
                           window_identity)

ROOT = Path(__file__).resolve().parents[1]
KIND = 'community-x3d-m-fixed-head-nll'
ARCHITECTURE = 'pytorchvideo-0.1.5-community-x3d-m-softmax-before-output-pool'
MANIFEST_SHA256 = '1a0f6fc44704b73f32c5e0ab82b607fff2a702a848186b4403ddf357a0026a84'
EXPECTED_COUNTS = {'recordings': 96, 'windows': 156, 'positive': 65, 'normal': 91}
HEAD_FEATURES = 2048
HEAD_KEYS = ('blocks.5.proj.1.weight', 'blocks.5.proj.1.bias')
RIGHTS = {'purpose': 'research-only offline adaptation; no live promotion or public redistribution',
          'communityCheckpoint': 'MIT metadata conflicts with research/noncommercial card prose; unresolved and unchanged',
          'trainingFootage': 'VID CC0 copyright evidence; consent author-reported, not independent full release',
          'labels': 'provisional assistant visual screening, not human ground truth or continuous review'}


@dataclass(frozen=True)
class Config:
    epochs: int = 3
    seed: int = 17
    learning_rate: float = 1e-5
    weight_decay: float = .01
    accumulation_steps: int = 8
    probability_epsilon: float = 1e-7
    cuda_memory_fraction: float = .35
    device: str = 'cpu'
    yield_to_demo: bool = True
    input_cache_mib: int = 1536

    def validate(self):
        fixed = {'epochs': 3, 'seed': 17, 'learning_rate': 1e-5, 'weight_decay': .01,
                 'accumulation_steps': 8, 'probability_epsilon': 1e-7, 'cuda_memory_fraction': .35}
        for name, expected in fixed.items():
            value = getattr(self, name)
            if type(value) is not type(expected) or value != expected:
                raise ValueError('Predeclared experiment setting cannot change: ' + name)
        if self.device not in ('cpu', 'cuda') or type(self.yield_to_demo) is not bool:
            raise ValueError('Invalid explicit device/demo policy')
        if self.device == 'cuda' and not self.yield_to_demo:
            raise ValueError('CUDA requires DemoYieldGuard')
        if type(self.input_cache_mib) is not int or not 0 <= self.input_cache_mib <= 1536:
            raise ValueError('Decoded input cache must be between zero and 1536 MiB')


def architecture():
    """Trusted installed model, no downloads and no activation/pooling edits."""
    if version('pytorchvideo') != '0.1.5':
        raise ValueError('Requires pinned pytorchvideo==0.1.5')
    from pytorchvideo.models.hub import x3d_m
    model = x3d_m(pretrained=False)
    model.blocks[-1].proj = nn.Sequential(nn.Dropout(.3), nn.Linear(2048, 2))
    return model


def baseline_model(checkpoint):
    if file_hash(checkpoint) != CHECKSUM:
        raise ValueError('Pinned community baseline checksum mismatch')
    with torch.serialization.safe_globals([scalar, np.dtype, type(np.dtype('float64')),
                                            type(np.dtype('float32'))]):
        state = torch.load(checkpoint, map_location='cpu', weights_only=True)
    model = architecture()
    model.load_state_dict({name.removeprefix('backbone.'): value for name, value in state['model'].items()}, strict=True)
    return model.float().eval().requires_grad_(False)


def enable_head_only(model):
    model.eval().requires_grad_(False)
    head = model.blocks[-1]
    if (len(model.blocks) != 6 or not isinstance(head.proj, nn.Sequential) or len(head.proj) != 2 or
            not isinstance(head.proj[0], nn.Dropout) or head.proj[0].p != .3 or
            not isinstance(head.proj[1], nn.Linear) or head.proj[1].in_features != HEAD_FEATURES or
            head.proj[1].out_features != 2 or not isinstance(head.activation, nn.Softmax) or
            head.activation.dim != 1 or head.output_pool is None):
        raise ValueError('Expected unchanged community binary head/Softmax/output pooling path')
    head.proj[1].requires_grad_(True)
    names = tuple(name for name, parameter in model.named_parameters() if parameter.requires_grad)
    if names != HEAD_KEYS or any(module.training for module in model.modules()):
        raise ValueError('Only existing head weight/bias may train; all modules must stay eval')
    return head.proj[1]


def probabilities(model, tensor):
    output = model(tensor)
    if (output.shape != (len(tensor), 2) or output.dtype != torch.float32 or
            not torch.isfinite(output).all() or (output < 0).any() or (output > 1).any() or
            not torch.allclose(output.sum(-1), torch.ones(len(tensor), device=output.device), atol=1e-5, rtol=0)):
        raise ValueError('Expected retained finite two-class probabilities; no extra Softmax allowed')
    return output


def tensor_hash(tensor):
    tensor = tensor.detach().cpu().contiguous()
    header = json.dumps({'shape': list(tensor.shape), 'dtype': str(tensor.dtype)}, sort_keys=True).encode()
    return hashlib.sha256(header + tensor.numpy().tobytes()).hexdigest()


def frozen_hashes(model):
    return {name: tensor_hash(value) for name, value in model.state_dict().items() if name not in HEAD_KEYS}


def assert_frozen(model, expected):
    if any(module.training for module in model.modules()) or frozen_hashes(model) != expected:
        raise ValueError('Non-head/BatchNorm state changed or BN/dropout left eval mode')
    if tuple(name for name, parameter in model.named_parameters() if parameter.requires_grad) != HEAD_KEYS:
        raise ValueError('Trainable parameter scope changed')


def cooperate(device, guard):
    if device.type == 'cuda':
        torch.cuda.synchronize(device)
    if guard is not None:
        guard()


def fit(model, windows, config, *, reader=read_window, preprocess=preprocess_frames, yield_guard=None):
    config.validate()
    windows = tuple(windows)
    if any(window.split != 'train' for window in windows):
        raise ValueError('Only train windows accepted; no diagnostic/calibration/holdout fitting')
    if {window.label for window in windows} != {0, 1}:
        raise ValueError('Both reviewed training classes are required')
    if config.yield_to_demo and yield_guard is None:
        raise ValueError('Requested demo cooperation requires a guard')
    device = training_device(config)
    seed_everything(config.seed, config.device)
    cooperate(device, yield_guard)
    model.float().to(device)
    head = enable_head_only(model)
    initial_head = {name: value.detach().cpu().clone() for name, value in head.state_dict().items()}
    frozen = frozen_hashes(model)
    labels = torch.tensor([window.label for window in windows], dtype=torch.long)
    counts = torch.bincount(labels, minlength=2).float()
    weights = len(windows) / (2 * counts)
    criterion = nn.NLLLoss(weight=weights.to(device), reduction='sum')
    optimizer = torch.optim.AdamW(head.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
    generator = torch.Generator().manual_seed(config.seed)
    history, steps = [], 0
    for epoch in range(config.epochs):
        assert_frozen(model, frozen)
        order = torch.randperm(len(windows), generator=generator).tolist()
        epoch_loss = 0.
        for offset in range(0, len(order), config.accumulation_steps):
            indices = order[offset:offset + config.accumulation_steps]
            denominator = float(weights[labels[indices]].sum())
            optimizer.zero_grad(set_to_none=True)
            for index in indices:
                tensor = preprocess(reader(windows[index]))
                cooperate(device, yield_guard)
                output = probabilities(model, tensor.to(device))
                loss = criterion(output.clamp_min(config.probability_epsilon).log(), labels[index:index + 1].to(device))
                if not torch.isfinite(loss):
                    raise ValueError('Nonfinite NLL')
                (loss / denominator).backward()
                epoch_loss += float(loss.detach().cpu())
                del tensor, output, loss
                cooperate(device, yield_guard)
            if any(parameter.grad is None or not torch.isfinite(parameter.grad).all() for parameter in head.parameters()):
                raise ValueError('Invalid head gradients')
            cooperate(device, yield_guard)
            optimizer.step()  # No gradient clipping or additional hypothesis change.
            steps += 1
        assert_frozen(model, frozen)
        history.append(epoch_loss / float(weights[labels].sum()))
        print(json.dumps({'stage': 'community-head', 'epoch': epoch + 1, 'weightedNLL': history[-1]}), flush=True)
    optimizer.zero_grad(set_to_none=True)
    cooperate(device, yield_guard)
    changed = [name for name, value in head.state_dict().items() if not torch.equal(value.detach().cpu(), initial_head[name])]
    return {'optimizer': 'AdamW', 'batchSize': 1, 'optimizerSteps': steps,
            'classCounts': counts.int().tolist(), 'classWeights': weights.tolist(),
            'epochWeightedNLL': history, 'exportEpoch': 3,
            'selection': 'predeclared last epoch; no diagnostic selection',
            'loss': 'weighted NLL(log(clamp_min(retained probabilities, 1e-7)))',
            'accumulation': 'sum weighted NLL / actual group sum of target weights, including tail',
            'trainableParameters': list(HEAD_KEYS), 'changedHeadTensors': changed,
            'nonHeadUnchanged': True, 'batchNormAndDropout': 'entire model remains eval',
            'initialNonHeadHashes': frozen}


def validate_training_manifest(path, data_root, *, verify_files):
    if file_hash(path) != MANIFEST_SHA256:
        raise ValueError('Predeclared VID round-2 manifest checksum mismatch')
    manifest = load_manifest(path, data_root, verify_files=verify_files)
    validate_vid_cohort(manifest)
    if (len(manifest.sources) != 1 or manifest.sources[0].id != 'vid-v2' or
            manifest.sources[0].license != 'CC0-1.0' or not manifest.sources[0].training_allowed or
            any(record.split != 'train' for record in manifest.recordings)):
        raise ValueError('Only permitted VID train-only cohort accepted')
    windows = generate_windows(manifest, 'train')
    counts = {'recordings': len(manifest.recordings), 'windows': len(windows),
              'positive': sum(window.label == 1 for window in windows),
              'normal': sum(window.label == 0 for window in windows)}
    if counts != EXPECTED_COUNTS:
        raise ValueError('Predeclared manifest counts mismatch')
    if file_hash(path) != MANIFEST_SHA256:
        raise ValueError('Manifest changed during validation')
    return manifest, windows


def _snapshots(source_evidence, provenance_files):
    paths = {'source/community_x3d_training.py': Path(__file__),
             'source/train_community_x3d.py': ROOT / 'train_community_x3d.py'}
    for name in ('training_data.py', 'x3d_training.py', 'x3d_finetune.py', 'x3d_candidate.py'):
        paths['source/' + name] = Path(__file__).with_name(name)
    paths['provenance/vid-source.json'] = Path(source_evidence)
    paths['provenance/DATA-RIGHTS.md'] = ROOT / 'training/DATA-RIGHTS.md'
    for index, path in enumerate(provenance_files):
        paths[f'provenance/{index:02d}-{Path(path).name}'] = Path(path)
    evidence = json.loads(Path(source_evidence).read_text(encoding='utf-8'))
    if evidence.get('eligibility', {}).get('trainingAllowed') is not True:
        raise ValueError('VID source rights evidence does not allow experimental training')
    return {name: path.read_bytes() for name, path in paths.items()}


def run(manifest_path, data_root, checkpoint, output_dir, *, config=None,
        source_evidence=ROOT / 'training/vid-source.json', provenance_files=(),
        model_factory=baseline_model, reader=read_window, preprocess=preprocess_frames, yield_guard=None):
    config = config or Config()
    config.validate()
    output_dir, manifest_path = Path(output_dir), Path(manifest_path)
    if output_dir.exists():
        raise FileExistsError(output_dir)
    manifest, windows = validate_training_manifest(manifest_path, data_root, verify_files=True)
    if file_hash(checkpoint) != CHECKSUM:
        raise ValueError('Pinned community baseline checksum mismatch')
    snapshots = _snapshots(source_evidence, provenance_files)
    snapshots['manifest.json'] = manifest_path.read_bytes()
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in snapshots.items()}
    if hashes['manifest.json'] != MANIFEST_SHA256:
        raise ValueError('Manifest changed before snapshot')
    guard = yield_guard if yield_guard is not None else (DemoYieldGuard() if config.yield_to_demo else None)
    if guard:
        guard()
    device = training_device(config)  # .35 allocator cap before model creation.
    seed_everything(config.seed, config.device)
    cooperate(device, guard)
    output_dir.mkdir(parents=True, exist_ok=False)
    for name, data in snapshots.items():
        path = output_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    started = time.perf_counter()
    if device.type == 'cuda':
        torch.cuda.reset_peak_memory_stats(device)
    model = model_factory(checkpoint)
    cache = FrameCache(reader, config.input_cache_mib) if config.input_cache_mib else None
    training = fit(model, windows, config, reader=cache or reader, preprocess=preprocess, yield_guard=guard)
    state = {name: value.detach().cpu().clone() for name, value in model.state_dict().items()}
    contract = {name: {'shape': list(value.shape), 'dtype': str(value.dtype)} for name, value in state.items()}
    identities = [window_identity(window) for window in windows]
    artifact = {'schemaVersion': 1, 'kind': KIND, 'architecture': ARCHITECTURE,
                'baseSha256': CHECKSUM, 'manifestSha256': MANIFEST_SHA256,
                'config': asdict(config), 'snapshotHashes': hashes, 'preprocessing': PREPROCESS,
                'classNames': CLASS_NAMES, 'threshold': .5, 'rights': RIGHTS,
                'stateContract': contract, 'initialNonHeadHashes': training['initialNonHeadHashes'],
                'training': training,
                'model_state': state}
    torch.save(artifact, output_dir / 'candidate-state.pt')
    gpu = None
    if device.type == 'cuda':
        cooperate(device, guard)
        gpu = {'name': torch.cuda.get_device_name(), 'cudaMemoryFraction': .35,
               'peakAllocatedMiB': torch.cuda.max_memory_allocated() / 1024**2,
               'peakReservedMiB': torch.cuda.max_memory_reserved() / 1024**2,
               'scope': 'This process Torch allocator only; excludes live service, driver and decoder'}
    report = {name: value for name, value in artifact.items() if name != 'model_state'}
    report.update({'status': 'complete-offline-experimental-candidate', 'complete': True,
                   'candidateSha256': file_hash(output_dir / 'candidate-state.pt'),
                   'baseSource': SOURCE, 'training': training,
                   'initialBaselineForwardParity': 'not measured here; independent parent zero-step check required',
                   'precision': 'float32', 'device': config.device, 'gpu': gpu,
                   'inputCache': cache.summary() if cache else None,
                   'elapsedSeconds': time.perf_counter() - started,
                   'thresholdFittedHere': False, 'holdoutUsedForSelection': False, 'liveModelChanged': False,
                   'calibration': {'status': 'uncalibrated', 'windows': 0, 'selectionSplit': None},
                   'splits': {'train': {**EXPECTED_COUNTS, 'recordingGroups': 1,
                                        'windowsIdentitySha256': content_hash(identities), 'windowIdentities': identities},
                              'calibration': {'windows': 0, 'status': 'not-available'},
                              'holdout': {'windows': 0, 'status': 'not-available'}},
                   'versions': {'torch': str(torch.__version__), 'pytorchvideo': version('pytorchvideo'),
                                'numpy': np.__version__},
                   'determinism': 'fixed seeds and cuDNN deterministic; CUDA unsupported kernels warn; no bitwise claim',
                   'limitations': ['Training loss is not held-out accuracy or diagnostic improvement.',
                                   'No crowd/night holdout, live capacity or commercial clearance claim.',
                                   'NLL clamp has zero derivative below epsilon; outputs are not renormalized.',
                                   'Incomplete failed run directories are not candidates; use a new directory.']})
    (output_dir / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return report


def _digest(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('Invalid SHA-256')
    return value


def validate_artifact(run_dir):
    """Verify everything inert/CPU BEFORE constructing any architecture."""
    run_dir = Path(run_dir).resolve()
    report = json.loads((run_dir / 'report.json').read_text(encoding='utf-8'))
    if not isinstance(report, dict) or report.get('complete') is not True or report.get('status') != 'complete-offline-experimental-candidate':
        raise ValueError('Incomplete/invalid adaptation report')
    if file_hash(run_dir / 'candidate-state.pt') != _digest(report.get('candidateSha256')):
        raise ValueError('Adaptation artifact checksum mismatch')
    hashes = report.get('snapshotHashes')
    required = {'manifest.json', 'source/community_x3d_training.py', 'source/train_community_x3d.py',
                'source/training_data.py', 'source/x3d_training.py', 'source/x3d_finetune.py',
                'source/x3d_candidate.py', 'provenance/vid-source.json', 'provenance/DATA-RIGHTS.md'}
    if not isinstance(hashes, dict) or not required.issubset(hashes):
        raise ValueError('Missing adaptation provenance/source snapshots')
    for name, sha in hashes.items():
        if not isinstance(name, str) or PureWindowsPath(name).drive:
            raise ValueError('Invalid snapshot path')
        path = (run_dir / name).resolve()
        if path == run_dir or not path.is_relative_to(run_dir) or file_hash(path) != _digest(sha):
            raise ValueError('Adaptation snapshot checksum/path mismatch')
    _, windows = validate_training_manifest(run_dir / 'manifest.json', run_dir / 'unresolved-media', verify_files=False)
    evidence = json.loads((run_dir / 'provenance/vid-source.json').read_text(encoding='utf-8'))
    if evidence.get('eligibility', {}).get('trainingAllowed') is not True:
        raise ValueError('Training rights evidence invalid')
    artifact = torch.load(run_dir / 'candidate-state.pt', map_location='cpu', weights_only=True)
    if not isinstance(artifact, dict):
        raise ValueError('Invalid safe adaptation state')
    fixed = {'schemaVersion': 1, 'kind': KIND, 'architecture': ARCHITECTURE, 'baseSha256': CHECKSUM,
             'manifestSha256': MANIFEST_SHA256, 'preprocessing': PREPROCESS,
             'classNames': CLASS_NAMES, 'threshold': .5, 'rights': RIGHTS}
    for name, value in fixed.items():
        if report.get(name) != value or artifact.get(name) != value:
            raise ValueError('Adaptation contract mismatch: ' + name)
    for name in ('config', 'snapshotHashes', 'stateContract', 'initialNonHeadHashes', 'training'):
        if report.get(name) != artifact.get(name):
            raise ValueError('Adaptation report/state mismatch: ' + name)
    Config(**artifact['config']).validate()
    training = report.get('training', {})
    counts = [EXPECTED_COUNTS['normal'], EXPECTED_COUNTS['positive']]
    weights = (EXPECTED_COUNTS['windows'] / (2 * torch.tensor(counts).float())).tolist()
    expected_steps = 3 * ((EXPECTED_COUNTS['windows'] + 7) // 8)
    identities = [window_identity(window) for window in windows]
    expected_train = {**EXPECTED_COUNTS, 'recordingGroups': 1,
                      'windowsIdentitySha256': content_hash(identities), 'windowIdentities': identities}
    losses = training.get('epochWeightedNLL')
    if (report.get('splits', {}).get('train') != expected_train or
            training.get('classCounts') != counts or training.get('classWeights') != weights or
            training.get('optimizerSteps') != expected_steps or training.get('optimizer') != 'AdamW' or
            training.get('batchSize') != 1 or training.get('trainableParameters') != list(HEAD_KEYS) or
            training.get('initialNonHeadHashes') != artifact['initialNonHeadHashes'] or
            not isinstance(losses, list) or len(losses) != 3 or
            any(type(value) not in (int, float) or not np.isfinite(value) or value < 0 for value in losses)):
        raise ValueError('Predeclared training/manifest summary mismatch')
    if (report.get('liveModelChanged') is not False or report.get('thresholdFittedHere') is not False or
            report.get('holdoutUsedForSelection') is not False or
            report.get('calibration') != {'status': 'uncalibrated', 'windows': 0, 'selectionSplit': None} or
            any(report.get('splits', {}).get(split) != {'windows': 0, 'status': 'not-available'}
                for split in ('calibration', 'holdout')) or
            report.get('training', {}).get('exportEpoch') != 3 or
            report.get('training', {}).get('nonHeadUnchanged') is not True):
        raise ValueError('Adaptation selection/evaluation contract mismatch')
    state, contract, frozen = artifact.get('model_state'), artifact.get('stateContract'), artifact.get('initialNonHeadHashes')
    if (not isinstance(state, dict) or not state or not isinstance(contract, dict) or
            state.keys() != contract.keys() or not isinstance(frozen, dict) or set(frozen) != state.keys() - set(HEAD_KEYS)):
        raise ValueError('Invalid full-state/frozen tensor contract')
    for name, tensor in state.items():
        if (not isinstance(tensor, torch.Tensor) or tensor.device.type != 'cpu' or
                tensor.dtype not in (torch.float32, torch.int64) or not torch.isfinite(tensor).all() or
                contract[name] != {'shape': list(tensor.shape), 'dtype': str(tensor.dtype)} or
                (name in frozen and tensor_hash(tensor) != _digest(frozen[name]))):
            raise ValueError('Adaptation tensor/frozen-state validation failed: ' + name)
    for name, shape in zip(HEAD_KEYS, ((2, HEAD_FEATURES), (2,))):
        if name not in state or tuple(state[name].shape) != shape or state[name].dtype != torch.float32:
            raise ValueError('Invalid existing binary Linear head state')
    return report, artifact


def load_candidate(run_dir, *, device='cpu', model_factory=architecture):
    report, artifact = validate_artifact(run_dir)
    selected = resolve_device(device, .35)
    torch.set_num_threads(2)
    model = model_factory().float().cpu()
    expected = model.state_dict()
    state = artifact['model_state']
    if state.keys() != expected.keys() or any(state[name].shape != value.shape or state[name].dtype != value.dtype
                                             for name, value in expected.items()):
        raise ValueError('Adaptation architecture keys/shapes/dtypes mismatch')
    model.load_state_dict(state, strict=True)
    enable_head_only(model)  # Validate retained path, then disable all gradients for diagnostics.
    model.eval().requires_grad_(False).to(selected)
    return model, report


class CommunityCandidate:
    def __init__(self, adaptation_run, *, device='cpu'):
        self.model, self.report = load_candidate(adaptation_run, device=device)
        self.device = device

    @torch.inference_mode()
    def predict(self, frames):
        if len(frames) < 8:
            raise ValueError('At least eight observed BGR frames required; caller verifies continuity')
        output = probabilities(self.model, preprocess_frames(frames).to(self.device))
        values = output[0].cpu().tolist()
        return {'fightScore': values[1], 'classScores': values,
                'scoreKind': 'retained-backbone-softmax', 'fightIndex': 1}

    def metadata(self):
        return {'kind': KIND, 'source': SOURCE, 'baselineSha256': CHECKSUM,
                'adaptationSha256': self.report['candidateSha256'],
                'trainingManifestSha256': self.report['manifestSha256'],
                'trainedSourceHashes': self.report['snapshotHashes'],
                'classNames': CLASS_NAMES, 'fightIndex': 1, 'scoreKind': 'retained-backbone-softmax',
                'preprocess': PREPROCESS, 'config': self.report['config'], 'rights': RIGHTS}
