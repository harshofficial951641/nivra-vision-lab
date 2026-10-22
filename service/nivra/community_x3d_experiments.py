"""Offline V2: one fixed head-only trajectory, predeclared 3/10/20 snapshots.

V1 stays immutable. A run seal is published only after every requested milestone
is exported; incomplete directories are evidence, never loadable candidates.
"""
from dataclasses import asdict, dataclass
import hashlib
from importlib.metadata import distribution, distributions
import json
import math
from pathlib import Path, PureWindowsPath
import platform
import re
import sys
import time

import cv2
import torch
from torch import nn

from . import community_x3d_training as base

ROOT = base.ROOT
KIND = 'community-x3d-m-head-nll-v2'
MILESTONES = (3, 10, 20)
DEPENDENCY_SOURCES = {
    'pytorchvideo': ('models/hub/x3d.py', 'models/x3d.py', 'models/head.py', 'models/stem.py',
                    'models/resnet.py', 'models/net.py', 'models/weight_init.py',
                    'layers/swish.py', 'layers/convolutions.py', 'layers/utils.py'),
    'fvcore': ('nn/squeeze_excitation.py',),
    'torch': ('optim/adamw.py', 'optim/optimizer.py', 'nn/modules/activation.py', 'nn/modules/linear.py',
              'nn/modules/pooling.py', 'nn/modules/batchnorm.py', 'nn/functional.py'),
}
REQUIRED_DEPENDENCIES = {
    'dependencies/manifests/service/requirements.txt',
    'dependencies/manifests/service/requirements-lock.txt',
    *(f'dependencies/installed/{package}/{name}'
      for package, names in DEPENDENCY_SOURCES.items() for name in names),
}


def runtime_snapshots():
    """Read installed metadata/source, never import builders or query a GPU.

    CUDA/cuDNN values describe linked/compiled libraries, not a probed driver or
    measured device. Requirements are observed files, not an assertion that the
    environment obeys every declared pin. No install, pip invocation or code run.
    """
    snapshots = {}
    for scope, root in (('service', ROOT), ('repository', ROOT.parent)):
        paths = set(root.glob('requirements*.txt'))
        paths.update(root / name for name in ('pyproject.toml', 'uv.lock', 'poetry.lock',
                                              'Pipfile', 'Pipfile.lock', 'pdm.lock'))
        for path in sorted(paths):
            if path.is_file():
                snapshots[f'dependencies/manifests/{scope}/{path.name}'] = path.read_bytes()
    for package, names in DEPENDENCY_SOURCES.items():
        installed = distribution(package)
        for name in names:
            path = Path(installed.locate_file(package + '/' + name))
            snapshots[f'dependencies/installed/{package}/{name}'] = path.read_bytes()
    if not REQUIRED_DEPENDENCIES.issubset(snapshots):
        raise ValueError('Missing required dependency manifests/source files')
    if sum(map(len, snapshots.values())) > 8 * 1024**2:
        raise ValueError('Dependency snapshots exceed bounded 8 MiB budget')
    packages = {}
    for installed in distributions():
        name = re.sub(r'[-_.]+', '-', installed.metadata['Name']).lower()
        value = str(installed.version)
        if name in packages and packages[name] != value:
            raise ValueError('Ambiguous installed package version: ' + name)
        packages[name] = value
    runtime = {'schemaVersion': 1,
               'python': {'version': platform.python_version(), 'implementation': platform.python_implementation(),
                          'build': sys.version},
               'platform': {'system': platform.system(), 'release': platform.release(),
                            'version': platform.version(), 'machine': platform.machine()},
               'torch': {'version': str(torch.__version__), 'gitVersion': torch.version.git_version,
                         'compiledCuda': torch.version.cuda, 'linkedCudnn': torch.backends.cudnn.version(),
                         'cudaDeviceOrDriverProbed': False},
               'numpy': str(base.np.__version__), 'opencv': str(cv2.__version__),
               'pytorchvideo': str(base.version('pytorchvideo')),
               'packages': dict(sorted(packages.items())),
               'dependencySnapshots': {name: hashlib.sha256(data).hexdigest()
                                       for name, data in sorted(snapshots.items())},
               'determinism': 'seeded best effort; no bitwise or cross-environment reproducibility claim'}
    snapshots['runtime/environment.json'] = (json.dumps(runtime, indent=2, allow_nan=False) + '\n').encode()
    return runtime, snapshots


def validate_runtime(runtime, hashes, directory):
    """Validate recorded primitive metadata and required snapshots, not install it."""
    if not isinstance(runtime, dict) or runtime.get('schemaVersion') != 1:
        raise ValueError('Missing/invalid runtime metadata')
    try:
        json.dumps(runtime, allow_nan=False)  # Reject tensors/custom objects even in safe states.
    except (TypeError, ValueError) as error:
        raise ValueError('Runtime metadata must contain safe JSON primitives') from error
    for section, fields in (('python', ('version', 'implementation', 'build')),
                            ('platform', ('system', 'release', 'version', 'machine'))):
        if not isinstance(runtime.get(section), dict) or any(
                not isinstance(runtime[section].get(name), str) or not runtime[section][name] for name in fields):
            raise ValueError('Invalid runtime ' + section)
    recorded_torch = runtime.get('torch')
    if (not isinstance(recorded_torch, dict) or not isinstance(recorded_torch.get('version'), str) or
            not recorded_torch['version'] or recorded_torch.get('cudaDeviceOrDriverProbed') is not False or
            any(name not in recorded_torch or (recorded_torch[name] is not None and not isinstance(recorded_torch[name], str))
                for name in ('compiledCuda', 'gitVersion')) or
            'linkedCudnn' not in recorded_torch or
            (recorded_torch['linkedCudnn'] is not None and type(recorded_torch['linkedCudnn']) is not int)):
        raise ValueError('Invalid Torch/CUDA/cuDNN runtime metadata')
    if any(not isinstance(runtime.get(name), str) or not runtime[name] for name in ('numpy', 'opencv', 'pytorchvideo')):
        raise ValueError('Missing runtime dependency versions')
    packages = runtime.get('packages')
    if (not isinstance(packages, dict) or
            not {'torch', 'numpy', 'opencv-python', 'pytorchvideo', 'fvcore', 'torchvision'}.issubset(packages) or
            any(not isinstance(name, str) or not name or not isinstance(value, str) or not value
                for name, value in packages.items())):
        raise ValueError('Missing installed package version inventory')
    if (runtime['numpy'] != packages['numpy'] or runtime['pytorchvideo'] != packages['pytorchvideo'] or
            recorded_torch['version'] != packages['torch'] or runtime['pytorchvideo'] != '0.1.5'):
        raise ValueError('Runtime module/package version mismatch')
    dependencies = runtime.get('dependencySnapshots')
    if not isinstance(dependencies, dict) or not REQUIRED_DEPENDENCIES.issubset(dependencies):
        raise ValueError('Missing required runtime dependency snapshots')
    for name, sha in dependencies.items():
        if not isinstance(name, str) or not name.startswith('dependencies/') or hashes.get(name) != base._digest(sha):
            raise ValueError('Runtime dependency hash mismatch')
    if 'runtime/environment.json' not in hashes:
        raise ValueError('Missing runtime environment snapshot')
    if json.loads((directory / 'runtime/environment.json').read_text(encoding='utf-8')) != runtime:
        raise ValueError('Runtime environment snapshot/metadata mismatch')


def validate_installed_dependencies(runtime):
    """Fail before construction if the local implementation differs from fitting."""
    for package in ('torch', 'numpy', 'opencv-python', 'pytorchvideo', 'fvcore', 'torchvision'):
        if str(distribution(package).version) != runtime['packages'][package]:
            raise ValueError('Installed dependency version differs from training: ' + package)
    for package, names in DEPENDENCY_SOURCES.items():
        installed = distribution(package)
        for name in names:
            expected = runtime['dependencySnapshots'][f'dependencies/installed/{package}/{name}']
            if base.file_hash(installed.locate_file(package + '/' + name)) != expected:
                raise ValueError('Installed dependency source differs from training: ' + package + '/' + name)


@dataclass(frozen=True)
class Config:
    max_epochs: int = 3
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
        if type(self.max_epochs) is not int or self.max_epochs not in MILESTONES:
            raise ValueError('max_epochs must be 3, 10 or 20')
        for name, value in {'seed': 17, 'learning_rate': 1e-5, 'weight_decay': .01,
                            'accumulation_steps': 8, 'probability_epsilon': 1e-7,
                            'cuda_memory_fraction': .35}.items():
            if type(getattr(self, name)) is not type(value) or getattr(self, name) != value:
                raise ValueError('Fixed V2 profile cannot change: ' + name)
        if self.device not in ('cpu', 'cuda') or type(self.yield_to_demo) is not bool:
            raise ValueError('Explicit cpu/cuda device and demo policy required')
        if self.device == 'cuda' and not self.yield_to_demo:
            raise ValueError('CUDA requires DemoYieldGuard')
        if type(self.input_cache_mib) is not int or not 0 <= self.input_cache_mib <= 1536:
            raise ValueError('Decoded input cache must be 0..1536 MiB')


def validate_training_manifest(path, data_root, expected_sha256, *, verify_files=True):
    base._digest(expected_sha256)
    if base.file_hash(path) != expected_sha256:
        raise ValueError('Explicit manifest checksum mismatch')
    manifest = base.load_manifest(path, data_root, verify_files=verify_files)
    base.validate_vid_cohort(manifest)
    if (len(manifest.sources) != 1 or manifest.sources[0].id != 'vid-v2' or
            manifest.sources[0].license != 'CC0-1.0' or not manifest.sources[0].training_allowed or
            any(record.split != 'train' for record in manifest.recordings)):
        raise ValueError('Only permitted VID training cohort accepted')
    windows = base.generate_windows(manifest, 'train')
    if {window.label for window in windows} != {0, 1}:
        raise ValueError('Both reviewed training classes required')
    if base.file_hash(path) != expected_sha256:
        raise ValueError('Manifest changed during validation')
    return manifest, windows


def train_summary(manifest, windows):
    identities = [base.window_identity(window) for window in windows]
    return {'recordings': len(manifest.recordings), 'windows': len(windows),
            'positive': sum(window.label == 1 for window in windows),
            'normal': sum(window.label == 0 for window in windows), 'recordingGroups': 1,
            'windowsIdentitySha256': base.content_hash(identities), 'windowIdentities': identities}


def fit(model, windows, config, *, reader=base.read_window, preprocess=base.preprocess_frames,
        yield_guard=None, on_milestone=None):
    """Keep one optimizer/RNG stream; callback receives an independent CPU state."""
    config.validate()
    windows = tuple(windows)
    if any(window.split != 'train' for window in windows):
        raise ValueError('Only train windows accepted')
    if {window.label for window in windows} != {0, 1}:
        raise ValueError('Both reviewed training classes required')
    if config.yield_to_demo and yield_guard is None:
        raise ValueError('Requested demo cooperation requires a guard')
    device = base.training_device(config)
    base.seed_everything(config.seed, config.device)
    base.cooperate(device, yield_guard)
    model.float().to(device)
    head = base.enable_head_only(model)
    frozen = base.frozen_hashes(model)
    initial_head = {name: base.tensor_hash(value) for name, value in head.state_dict().items()}
    labels = torch.tensor([window.label for window in windows], dtype=torch.long)
    counts = torch.bincount(labels, minlength=2).float()
    weights = len(windows) / (2 * counts)
    criterion = nn.NLLLoss(weight=weights.to(device), reduction='sum')
    optimizer = torch.optim.AdamW(head.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
    generator = torch.Generator().manual_seed(config.seed)
    losses, steps, milestones = [], 0, {}
    for epoch in range(1, config.max_epochs + 1):
        base.assert_frozen(model, frozen)
        order = torch.randperm(len(windows), generator=generator).tolist()
        total = 0.
        for offset in range(0, len(order), config.accumulation_steps):
            group = order[offset:offset + config.accumulation_steps]
            denominator = float(weights[labels[group]].sum())
            optimizer.zero_grad(set_to_none=True)
            for index in group:
                tensor = preprocess(reader(windows[index]))
                base.cooperate(device, yield_guard)
                output = base.probabilities(model, tensor.to(device))
                loss = criterion(output.clamp_min(config.probability_epsilon).log(), labels[index:index + 1].to(device))
                if not torch.isfinite(loss):
                    raise ValueError('Nonfinite NLL')
                (loss / denominator).backward()
                total += float(loss.detach().cpu())
                del tensor, output, loss
                base.cooperate(device, yield_guard)
            if any(parameter.grad is None or not torch.isfinite(parameter.grad).all() for parameter in head.parameters()):
                raise ValueError('Invalid head gradients')
            base.cooperate(device, yield_guard)
            optimizer.step()
            if any(not torch.isfinite(parameter).all() for parameter in head.parameters()):
                raise ValueError('Nonfinite updated head tensors')
            steps += 1
        base.assert_frozen(model, frozen)
        losses.append(total / float(weights[labels].sum()))
        print(json.dumps({'stage': KIND, 'epoch': epoch, 'weightedNLL': losses[-1],
                          'optimizerSteps': steps}), flush=True)
        if epoch in MILESTONES:
            details = {'exportEpoch': epoch, 'optimizerSteps': steps, 'microbatches': epoch * len(windows),
                       'optimizer': 'AdamW', 'batchSize': 1, 'classCounts': counts.int().tolist(),
                       'classWeights': weights.tolist(), 'epochWeightedNLL': list(losses),
                       'trainableParameters': list(base.HEAD_KEYS), 'nonHeadUnchanged': True,
                       'batchNormAndDropout': 'entire model remains eval',
                       'initialNonHeadHashes': frozen,
                       'changedHeadTensors': [name for name, value in head.state_dict().items()
                                              if base.tensor_hash(value) != initial_head[name]],
                       'selection': 'predeclared milestone; no diagnostic selection',
                       'loss': 'weighted NLL(log(clamp_min(retained probabilities, 1e-7)))',
                       'accumulation': 'sum weighted NLL / actual group sum of target weights, including tail'}
            if on_milestone:
                state = {name: value.detach().cpu().clone() for name, value in model.state_dict().items()}
                on_milestone(epoch, state, details)
            milestones[epoch] = details
    optimizer.zero_grad(set_to_none=True)
    base.cooperate(device, yield_guard)
    return milestones


def _write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + '\n')


def _snapshots(source_evidence, provenance_files):
    snapshots = base._snapshots(source_evidence, provenance_files)
    snapshots['source/community_x3d_experiments.py'] = Path(__file__).read_bytes()
    snapshots['source/train_community_experiments.py'] = (ROOT / 'train_community_experiments.py').read_bytes()
    return snapshots


def run(manifest_path, data_root, checkpoint, output_dir, *, manifest_sha256,
        config=None, source_evidence=ROOT / 'training/vid-source.json', provenance_files=(),
        model_factory=base.baseline_model, reader=base.read_window,
        preprocess=base.preprocess_frames, yield_guard=None):
    config = config or Config()
    config.validate()
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise FileExistsError(output_dir)
    manifest, windows = validate_training_manifest(manifest_path, data_root, manifest_sha256)
    if base.file_hash(checkpoint) != base.CHECKSUM:
        raise ValueError('Pinned community baseline checksum mismatch')
    snapshots = _snapshots(source_evidence, provenance_files)
    runtime, dependency_snapshots = runtime_snapshots()
    snapshots.update(dependency_snapshots)
    snapshots['manifest.json'] = Path(manifest_path).read_bytes()
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in snapshots.items()}
    if hashes['manifest.json'] != manifest_sha256:
        raise ValueError('Manifest changed before snapshot')
    summary = train_summary(manifest, windows)
    guard = yield_guard if yield_guard is not None else (base.DemoYieldGuard() if config.yield_to_demo else None)
    if guard:
        guard()
    device = base.training_device(config)  # allocator limit BEFORE trusted model construction
    base.seed_everything(config.seed, config.device)
    base.cooperate(device, guard)
    output_dir.mkdir(parents=True, exist_ok=False)
    # Preserve the exact planned inputs even if construction/epoch one fails.
    for name, data in snapshots.items():
        path = output_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(data)
    _write_json(output_dir / 'started.json', {'kind': KIND, 'config': asdict(config),
                                           'manifestSha256': manifest_sha256, 'baseSha256': base.CHECKSUM,
                                           'snapshotHashes': hashes, 'runtime': runtime, 'complete': False})
    started = time.perf_counter()
    catalog = {}
    cache = base.FrameCache(reader, config.input_cache_mib) if config.input_cache_mib else None

    def export(epoch, state, training):
        directory = output_dir / f'epoch-{epoch:03d}'
        directory.mkdir(exist_ok=False)
        for name, data in snapshots.items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(data)
        artifact = {'schemaVersion': 2, 'kind': KIND, 'architecture': base.ARCHITECTURE,
                    'baseSha256': base.CHECKSUM, 'baseSource': base.SOURCE,
                    'manifestSha256': manifest_sha256, 'config': asdict(config),
                    'runtime': runtime,
                    'snapshotHashes': hashes, 'preprocessing': base.PREPROCESS,
                    'classNames': base.CLASS_NAMES, 'threshold': .5, 'rights': base.RIGHTS,
                    'training': training, 'splits': {'train': summary,
                        'calibration': {'windows': 0, 'status': 'not-available'},
                        'holdout': {'windows': 0, 'status': 'not-available'}},
                    'stateContract': {name: {'shape': list(value.shape), 'dtype': str(value.dtype)}
                                      for name, value in state.items()}, 'model_state': state}
        with (directory / 'candidate-state.pt').open('xb') as stream:
            torch.save(artifact, stream)
        report = {key: value for key, value in artifact.items() if key != 'model_state'}
        report.update({'complete': True, 'status': 'offline-milestone-requires-run-seal',
                       'candidateSha256': base.file_hash(directory / 'candidate-state.pt'),
                       'thresholdFittedHere': False, 'holdoutUsedForSelection': False,
                       'liveModelChanged': False, 'precision': 'float32',
                       'calibration': {'status': 'uncalibrated', 'windows': 0, 'selectionSplit': None},
                       'initialBaselineForwardParity': 'not measured by this run; parent zero-step check required'})
        _write_json(directory / 'report.json', report)
        catalog[str(epoch)] = {'directory': directory.name,
                               'reportSha256': base.file_hash(directory / 'report.json'),
                               'candidateSha256': report['candidateSha256']}

    try:
        if device.type == 'cuda':
            torch.cuda.reset_peak_memory_stats(device)
        validate_installed_dependencies(runtime)
        model = model_factory(checkpoint)
        fit(model, windows, config, reader=cache or reader, preprocess=preprocess,
            yield_guard=guard, on_milestone=export)
        base.cooperate(device, guard)
        gpu = None if device.type == 'cpu' else {
            'peakAllocatedMiB': torch.cuda.max_memory_allocated(device) / 1024**2,
            'peakReservedMiB': torch.cuda.max_memory_reserved(device) / 1024**2,
            'scope': 'process Torch allocator only; excludes live service, driver and decoder'}
        seal = {'kind': KIND, 'complete': True, 'config': asdict(config),
                'manifestSha256': manifest_sha256, 'baseSha256': base.CHECKSUM,
                'runtime': runtime, 'startedSha256': base.file_hash(output_dir / 'started.json'),
                'milestones': catalog, 'inputCache': cache.summary() if cache else None,
                'gpu': gpu, 'elapsedSeconds': time.perf_counter() - started}
        _write_json(output_dir / 'complete.json', seal)  # Last write; failed runs cannot load.
        return seal
    except Exception as error:
        _write_json(output_dir / 'failed.json', {'complete': False, 'errorType': type(error).__name__,
                                               'exportedMilestones': sorted(catalog)})
        raise


def validate_artifact(milestone_dir, *, manifest_sha256):
    """Validate inert metadata, hashes and CPU-only restricted state before models."""
    base._digest(manifest_sha256)
    directory = Path(milestone_dir).resolve()
    seal = json.loads((directory.parent / 'complete.json').read_text(encoding='utf-8'))
    if base.file_hash(directory.parent / 'started.json') != base._digest(seal.get('startedSha256')):
        raise ValueError('V2 started receipt checksum mismatch')
    started = json.loads((directory.parent / 'started.json').read_text(encoding='utf-8'))
    for name in ('kind', 'config', 'manifestSha256', 'baseSha256', 'runtime'):
        if name not in seal or started.get(name) != seal[name]:
            raise ValueError('V2 started/seal metadata mismatch: ' + name)
    config = Config(**seal['config'])
    config.validate()
    epochs = [epoch for epoch in MILESTONES if epoch <= config.max_epochs]
    if (seal.get('kind') != KIND or seal.get('complete') is not True or
            seal.get('manifestSha256') != manifest_sha256 or seal.get('baseSha256') != base.CHECKSUM or
            (directory.parent / 'failed.json').exists() or
            set(seal.get('milestones', {})) != {str(epoch) for epoch in epochs}):
        raise ValueError('Invalid/incomplete V2 run seal')
    # All requested milestones must still exist unchanged; never accept partial success.
    for epoch in epochs:
        entry = seal['milestones'][str(epoch)]
        if entry.get('directory') != f'epoch-{epoch:03d}':
            raise ValueError('Invalid milestone directory')
        sibling = directory.parent / entry['directory']
        if (base.file_hash(sibling / 'report.json') != base._digest(entry.get('reportSha256')) or
                base.file_hash(sibling / 'candidate-state.pt') != base._digest(entry.get('candidateSha256'))):
            raise ValueError('Milestone report/artifact checksum mismatch')
    report = json.loads((directory / 'report.json').read_text(encoding='utf-8'))
    epoch = report.get('training', {}).get('exportEpoch')
    if type(epoch) is not int or epoch not in epochs or directory.name != f'epoch-{epoch:03d}':
        raise ValueError('Invalid actual export epoch')
    if report.get('candidateSha256') != seal['milestones'][str(epoch)]['candidateSha256']:
        raise ValueError('Milestone identity mismatch')
    hashes = report.get('snapshotHashes')
    required = {'manifest.json', 'source/community_x3d_experiments.py', 'source/train_community_experiments.py',
                'source/community_x3d_training.py', 'source/train_community_x3d.py', 'source/training_data.py',
                'source/x3d_training.py', 'source/x3d_finetune.py', 'source/x3d_candidate.py',
                'provenance/vid-source.json', 'provenance/DATA-RIGHTS.md'}
    if not isinstance(hashes, dict) or not required.issubset(hashes):
        raise ValueError('Missing V2 provenance/source snapshots')
    if started.get('snapshotHashes') != hashes:
        raise ValueError('V2 started/milestone snapshot hashes mismatch')
    for name, digest in hashes.items():
        if not isinstance(name, str) or PureWindowsPath(name).drive:
            raise ValueError('Invalid snapshot path')
        for container in (directory, directory.parent):
            path = (container / name).resolve()
            if path == container or not path.is_relative_to(container) or base.file_hash(path) != base._digest(digest):
                raise ValueError('Snapshot checksum/path mismatch')
    validate_runtime(seal.get('runtime'), hashes, directory)
    validate_runtime(seal.get('runtime'), hashes, directory.parent)
    manifest, windows = validate_training_manifest(directory / 'manifest.json', directory / 'unresolved-media',
                                                    manifest_sha256, verify_files=False)
    evidence = json.loads((directory / 'provenance/vid-source.json').read_text(encoding='utf-8'))
    if evidence.get('eligibility', {}).get('trainingAllowed') is not True:
        raise ValueError('Invalid rights evidence')
    artifact = torch.load(directory / 'candidate-state.pt', weights_only=True, map_location='cpu')
    if not isinstance(artifact, dict):
        raise ValueError('Invalid safe V2 artifact')
    fixed = {'schemaVersion': 2, 'kind': KIND, 'architecture': base.ARCHITECTURE,
             'baseSha256': base.CHECKSUM, 'baseSource': base.SOURCE, 'manifestSha256': manifest_sha256,
             'preprocessing': base.PREPROCESS, 'classNames': base.CLASS_NAMES, 'threshold': .5, 'rights': base.RIGHTS,
             'config': seal['config'], 'runtime': seal['runtime']}
    for key, value in fixed.items():
        if report.get(key) != value or artifact.get(key) != value:
            raise ValueError('V2 contract mismatch: ' + key)
    for key in ('snapshotHashes', 'training', 'splits', 'stateContract'):
        if report.get(key) != artifact.get(key):
            raise ValueError('V2 state/report mismatch: ' + key)
    summary = train_summary(manifest, windows)
    counts = [summary['normal'], summary['positive']]
    weights = (len(windows) / (2 * torch.tensor(counts).float())).tolist()
    training = report['training']
    losses = training.get('epochWeightedNLL')
    if (report['splits'].get('train') != summary or training.get('classCounts') != counts or
            training.get('classWeights') != weights or training.get('optimizer') != 'AdamW' or
            training.get('batchSize') != 1 or training.get('optimizerSteps') != epoch * math.ceil(len(windows) / 8) or
            training.get('microbatches') != epoch * len(windows) or
            training.get('trainableParameters') != list(base.HEAD_KEYS) or
            training.get('nonHeadUnchanged') is not True or
            training.get('batchNormAndDropout') != 'entire model remains eval' or
            training.get('selection') != 'predeclared milestone; no diagnostic selection' or
            not isinstance(losses, list) or len(losses) != epoch or
            any(type(loss) not in (int, float) or not math.isfinite(loss) or loss < 0 for loss in losses)):
        raise ValueError('Invalid training accounting/frozen proof')
    if (report.get('complete') is not True or report.get('status') != 'offline-milestone-requires-run-seal' or
            any(report.get(key) is not False for key in ('liveModelChanged', 'thresholdFittedHere', 'holdoutUsedForSelection')) or
            report.get('calibration') != {'status': 'uncalibrated', 'windows': 0, 'selectionSplit': None} or
            any(report['splits'].get(split) != {'windows': 0, 'status': 'not-available'}
                for split in ('calibration', 'holdout'))):
        raise ValueError('Invalid selection/evaluation contract')
    state, contract, frozen = artifact.get('model_state'), artifact.get('stateContract'), training.get('initialNonHeadHashes')
    if (not isinstance(state, dict) or not state or not isinstance(contract, dict) or state.keys() != contract.keys() or
            not isinstance(frozen, dict) or set(frozen) != state.keys() - set(base.HEAD_KEYS)):
        raise ValueError('Invalid full-state tensor contract')
    for name, tensor in state.items():
        if (not isinstance(tensor, torch.Tensor) or tensor.device.type != 'cpu' or
                tensor.dtype not in (torch.float32, torch.int64) or not torch.isfinite(tensor).all() or
                contract[name] != {'shape': list(tensor.shape), 'dtype': str(tensor.dtype)} or
                (name in frozen and base.tensor_hash(tensor) != base._digest(frozen[name]))):
            raise ValueError('Invalid tensor/frozen state: ' + name)
    for name, shape in zip(base.HEAD_KEYS, ((2, base.HEAD_FEATURES), (2,))):
        if name not in state or tuple(state[name].shape) != shape or state[name].dtype != torch.float32:
            raise ValueError('Invalid binary head tensor')
    return report, artifact


def load_candidate(milestone_dir, *, manifest_sha256, device='cpu', model_factory=base.architecture):
    report, artifact = validate_artifact(milestone_dir, manifest_sha256=manifest_sha256)
    validate_installed_dependencies(report['runtime'])
    selected = base.resolve_device(device, .35)
    torch.set_num_threads(2)
    model = model_factory().float().cpu()
    expected, state = model.state_dict(), artifact['model_state']
    if expected.keys() != state.keys() or any(value.shape != state[name].shape or value.dtype != state[name].dtype
                                             for name, value in expected.items()):
        raise ValueError('V2 architecture keys/shapes/dtypes mismatch')
    model.load_state_dict(state, strict=True)
    base.enable_head_only(model)
    model.eval().requires_grad_(False).to(selected)
    return model, report


class ExperimentCandidate(base.CommunityCandidate):
    """Same BGR/retained-probability API; distinct V2 identity and actual epoch."""
    def __init__(self, adaptation_run, *, manifest_sha256, device='cpu'):
        self.model, self.report = load_candidate(adaptation_run, manifest_sha256=manifest_sha256, device=device)
        self.device = device

    def metadata(self):
        metadata = super().metadata()
        metadata.update({'kind': KIND, 'exportEpoch': self.report['training']['exportEpoch']})
        return metadata
