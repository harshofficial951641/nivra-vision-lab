from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path

import cv2
import numpy as np
import pytest
import torch

from nivra.training_data import Event, Recording, TrainingManifest, Window
from nivra import x3d_training as training


def window(label=0, group='recording', split='train', start=0.):
    return Window(group, group, None, 'a' * 64, split, start, start + 4, label)


def synthetic_features():
    features = np.zeros((8, 2048), dtype=np.float32)
    labels = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    features[:, 0] = [-2., -1.8, -1.5, -1., 1., 1.5, 1.8, 2.]
    return features, labels


def test_preprocess_rgb_uniform_sampling_and_deployed_normalization():
    frames = [np.full((8, 10, 3), [i, i + 10, i + 20], dtype=np.uint8) for i in range(40)]
    tensor = training.preprocess_frames(frames)
    assert tensor.shape == (1, 3, 16, 224, 224)
    assert tensor.device.type == 'cpu' and tensor.dtype == torch.float32
    indices = np.linspace(0, 39, 16).astype(int)
    for sample, index in enumerate(indices):
        expected_rgb = np.array([index + 20, index + 10, index])
        expected = torch.tensor((expected_rgb / 255 - .45) / .225, dtype=torch.float32)
        torch.testing.assert_close(tensor[0, :, sample, 100, 100], expected)
    with pytest.raises(ValueError):
        training.preprocess_frames([])
    with pytest.raises(ValueError):
        training.preprocess_frames([np.zeros((8, 8, 3), dtype=np.float32)])


def test_pinned_checkpoint_rejected_before_model_load(tmp_path):
    path = tmp_path / 'untrusted.pyth'
    path.write_bytes(b'not weights')
    with pytest.raises(ValueError, match='checksum'):
        training.FrozenX3D(path)


def test_binary_logits_head_fits_and_is_deterministic():
    features, labels = synthetic_features()
    head, details = training.fit_head(features, labels, seed=5, epochs=60)
    scores = training.predict_head(head, features)
    assert np.array_equal(scores > .5, labels)
    assert details['selection'] == 'fixed epochs; train split only'
    assert details['classWeights'] is None
    repeat, _ = training.fit_head(features, labels, seed=5, epochs=60)
    for key, value in head.state_dict().items():
        torch.testing.assert_close(value, repeat.state_dict()[key], rtol=0, atol=0)
    assert isinstance(head, torch.nn.Linear)  # No Softmax before CrossEntropyLoss.


def test_training_class_weights_and_missing_class_guard():
    features, labels = synthetic_features()
    _, details = training.fit_head(features[:6], labels[:6], class_weight=True, epochs=1)
    assert details['classWeights'] == [.75, 1.5]
    with pytest.raises(ValueError, match='both binary'):
        training.fit_head(features[:4], labels[:4], epochs=1)


def test_calibration_minimizes_misses_with_strict_zero_observed_fp():
    scores = np.array([.1, .3, .4, .8, .9])
    labels = np.array([0, 0, 1, 1, 1])
    threshold, details = training.select_threshold(scores, labels)
    assert threshold == .3 and details['selectionSplit'] == 'calibration'
    report = training.metrics(scores, labels, threshold)
    assert report['fp'] == 0 and report['fn'] == 0
    assert report['falseAlertsPerCameraHour'] is None and report['eventRecall'] is None
    # Unseparable calibration must honestly expose missed positives.
    threshold, _ = training.select_threshold([.9, .1], [0, 1])
    assert training.metrics([.9, .1], [0, 1], threshold)['recall'] == 0


def test_no_calibration_or_holdout_is_honestly_unavailable():
    for scores, labels in [([], []), ([.7], [1]), ([.1, .2], [0, 0])]:
        threshold, details = training.select_threshold(scores, labels)
        assert threshold == .5 and details['status'] == 'uncalibrated'
        assert details['selectionSplit'] is None
    assert training.metrics([], [], .5) == {'status': 'not-available', 'windows': 0}


def test_smoke_sampler_bounds_preserves_classes_and_recordings():
    windows = [window(label, f'group-{label}-{group}', start=float(index))
               for label in (0, 1) for group in range(2) for index in range(5)]
    selected = training.select_windows(windows, 4, 17)
    assert len(selected) == 4
    assert len({entry.recording_group for entry in selected}) == 4
    assert {entry.label for entry in selected} == {0, 1}
    assert selected == training.select_windows(windows, 4, 17)


def test_feature_cache_is_scoped_to_base_manifest_window_and_preprocess(tmp_path):
    calls = []

    def extractor(tensor):
        calls.append(tensor.shape)
        return np.ones((1, 2048), dtype=np.float32)

    def reader(_):
        return [np.zeros((10, 10, 3), dtype=np.uint8)]

    first = training.extract_features([window()], extractor, tmp_path, 'manifest-1', reader=reader)
    second = training.extract_features([window()], extractor, tmp_path, 'manifest-1', reader=reader)
    np.testing.assert_equal(first, second)
    assert len(calls) == 1
    training.extract_features([window()], extractor, tmp_path, 'manifest-2', reader=reader)
    training.extract_features([window(start=4)], extractor, tmp_path, 'manifest-2', reader=reader)
    assert len(calls) == 3
    assert len(list(tmp_path.glob('*.npy'))) == 3
    training.extract_features([window()], extractor, tmp_path, 'manifest-1', reader=reader, device='cuda')
    assert len(calls) == 4 and len(list(tmp_path.glob('*.npy'))) == 4


def test_local_decoder_uses_full_window_and_releases_short_clip(tmp_path):
    path = tmp_path / 'local.avi'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 10, (64, 64))
    assert writer.isOpened()
    for index in range(50):
        writer.write(np.full((64, 64, 3), index, dtype=np.uint8))
    writer.release()
    frames = training.read_window(replace(window(), path=path))
    assert 35 <= len(frames) <= 41
    assert frames[0][0, 0, 0] < frames[-1][0, 0, 0]
    with pytest.raises(ValueError, match='four-second'):
        training.read_window(replace(window(), path=path, start_seconds=3., end_seconds=7.))
    path.unlink()  # Capture must be released on both success and error.


def test_decoder_rejects_large_timestamp_gap_despite_enough_frames_and_span(monkeypatch):
    times = [0, 100, 200, 300, 400, 1701, 2001, 2601, 3201, 3901]

    class Capture:
        index = 0
        released = False

        def isOpened(self):
            return True

        def set(self, *_):
            return True

        def get(self, property_id):
            if property_id == cv2.CAP_PROP_FPS:
                return 10
            if property_id == cv2.CAP_PROP_POS_MSEC:
                return times[self.index - 1]
            return self.index

        def read(self):
            if self.index >= len(times):
                return False, None
            self.index += 1
            return True, np.zeros((32, 32, 3), dtype=np.uint8)

        def release(self):
            self.released = True

    capture = Capture()
    monkeypatch.setattr(training.cv2, 'VideoCapture', lambda _: capture)
    with pytest.raises(ValueError, match='Discontinuous'):
        training.read_window(window())
    assert capture.released


def test_run_seals_threshold_before_holdout_and_saves_separate_artifact(tmp_path, monkeypatch):
    manifest_path = tmp_path / 'manifest.json'
    manifest_path.write_text('{}')
    checkpoint = tmp_path / 'official.pyth'
    checkpoint.write_bytes(b'pinned fixture')
    monkeypatch.setattr(training, 'BASE_SHA256', hashlib.sha256(checkpoint.read_bytes()).hexdigest())
    records = []
    for split in ('train', 'calibration', 'holdout'):
        for label in (0, 1):
            key = f'{split}-{label}'
            records.append(Recording(key, 'source', key, tmp_path / (key + '.avi'),
                                     'a' * 64, 4., split, 'reviewed', 'synthetic', label,
                                     (Event(0., 4., label),)))
    manifest = TrainingManifest(1, tmp_path, (), tuple(records))
    monkeypatch.setattr(training, 'load_manifest', lambda *_args, **_kwargs: manifest)
    seen = []
    original_select = training.select_threshold

    def select(scores, labels):
        seen.append('threshold-selected')
        return original_select(scores, labels)

    monkeypatch.setattr(training, 'select_threshold', select)

    def reader(entry):
        if entry.split == 'holdout':
            assert 'threshold-selected' in seen
        seen.append(entry.split)
        return [np.full((8, 8, 3), entry.label * 255, dtype=np.uint8)]

    class Extractor:
        def __init__(self, _):
            pass

        def __call__(self, tensor):
            result = np.zeros((1, 2048), dtype=np.float32)
            result[0, 0] = float(tensor.mean())
            return result

    output = tmp_path / 'new-run'
    report = training.run(manifest_path, tmp_path, checkpoint, output,
                          epochs=30, extractor_factory=Extractor, reader=reader)
    assert report['holdoutUsedForSelection'] is False and report['liveModelChanged'] is False
    assert report['splits']['holdout']['metrics']['windows'] == 2
    assert report['splits']['holdout']['metrics']['accuracy'] == 1
    assert report['candidateSha256'] == training.file_hash(output / 'candidate-head.pt')
    saved = torch.load(output / 'candidate-head.pt', weights_only=True, map_location='cpu')
    assert saved['threshold'] == report['threshold']
    assert saved['head_state']['weight'].shape == (2, 2048)
    assert json.loads((output / 'report.json').read_text())['device'] == 'cpu'
    for name, digest in report['implementationHashes'].items():
        assert training.file_hash(output / 'source' / name) == digest
    with pytest.raises(FileExistsError):
        training.run(manifest_path, tmp_path, checkpoint, output,
                     epochs=1, extractor_factory=Extractor, reader=reader)


def test_train_only_run_does_not_fabricate_evaluation(tmp_path, monkeypatch):
    path = tmp_path / 'manifest.json'
    path.write_text('{}')
    checkpoint = tmp_path / 'checkpoint.pyth'
    checkpoint.write_bytes(b'fixture')
    monkeypatch.setattr(training, 'BASE_SHA256', training.file_hash(checkpoint))
    windows = tuple(window(label, f'train-{label}') for label in (0, 1))
    monkeypatch.setattr(training, 'load_manifest', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(training, 'generate_windows', lambda _, split: windows if split == 'train' else ())

    class Extractor:
        def __init__(self, _):
            pass

        def __call__(self, tensor):
            return np.zeros((1, 2048), dtype=np.float32)

    report = training.run(path, tmp_path, checkpoint, tmp_path / 'train-only', epochs=1,
                          extractor_factory=Extractor,
                          reader=lambda _: [np.zeros((8, 8, 3), dtype=np.uint8)])
    assert report['threshold'] == .5 and report['calibration']['status'] == 'uncalibrated'
    for split in ('calibration', 'holdout'):
        assert report['splits'][split]['metrics']['status'] == 'not-available'
        assert report['splits'][split]['selectedWindows'] == 0


def test_source_snapshot_hashes_are_frozen_before_extractor_runs(tmp_path, monkeypatch):
    manifest_path = tmp_path / 'manifest.json'
    manifest_path.write_text('{}')
    checkpoint = tmp_path / 'checkpoint.pyth'
    checkpoint.write_bytes(b'fixture')
    monkeypatch.setattr(training, 'BASE_SHA256', training.file_hash(checkpoint))
    windows = tuple(window(label, f'train-{label}') for label in (0, 1))
    monkeypatch.setattr(training, 'load_manifest', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(training, 'generate_windows', lambda _, split: windows if split == 'train' else ())
    # Redirect __file__ to a disposable source tree, then mutate the file during
    # the long-running work. No actual repository sources are changed by this test.
    module_dir = tmp_path / 'source-tree' / 'nivra'
    module_dir.mkdir(parents=True)
    module = module_dir / 'x3d_training.py'
    module.write_bytes(b'initial training implementation')
    (module_dir / 'training_data.py').write_bytes(b'initial data implementation')
    (module_dir.parent / 'train_x3d.py').write_bytes(b'initial CLI implementation')
    monkeypatch.setattr(training, '__file__', str(module))

    class Extractor:
        def __init__(self, _):
            module.write_bytes(b'changed after fitting began')

        def __call__(self, tensor):
            return np.zeros((1, 2048), dtype=np.float32)

    output = tmp_path / 'snapshot-run'
    report = training.run(manifest_path, tmp_path, checkpoint, output, epochs=1,
                          extractor_factory=Extractor,
                          reader=lambda _: [np.zeros((8, 8, 3), dtype=np.uint8)])
    assert (output / 'source' / 'x3d_training.py').read_bytes() == b'initial training implementation'
    assert report['implementationHashes']['x3d_training.py'] == hashlib.sha256(b'initial training implementation').hexdigest()
    assert report['implementationHashes']['x3d_training.py'] != training.file_hash(module)


def test_cuda_unavailable_never_falls_back_or_creates_output(tmp_path, monkeypatch):
    monkeypatch.setattr(training.torch.cuda, 'is_available', lambda: False)
    output = tmp_path / 'must-not-exist'
    with pytest.raises(RuntimeError, match='no CPU fallback'):
        training.run(tmp_path / 'missing-manifest.json', tmp_path, tmp_path / 'missing.pyth',
                     output, device='cuda')
    assert not output.exists()


def test_cuda_allocator_cap_is_explicit_and_validated(monkeypatch):
    caps = []
    monkeypatch.setattr(training.torch.cuda, 'is_available', lambda: True)
    monkeypatch.setattr(training.torch.cuda, 'set_per_process_memory_fraction', caps.append)
    assert training.resolve_device('cuda', .4).type == 'cuda'
    assert caps == [.4]
    for invalid in (0, -1, 1.1, float('nan'), True):
        with pytest.raises(ValueError, match='memory fraction'):
            training.resolve_device('cuda', invalid)


def test_demo_yield_guard_waits_releases_and_fails_closed():
    now = [0.]
    states = iter([True, True, False])
    guard = training.DemoYieldGuard(fetch=lambda: {'busy': next(states)},
                                   clock=lambda: now[0], sleep=lambda seconds: now.__setitem__(0, now[0] + seconds))
    guard()
    assert now[0] == 2
    busy = training.DemoYieldGuard(timeout=2, fetch=lambda: {'busy': True},
                                  clock=lambda: now[0], sleep=lambda seconds: now.__setitem__(0, now[0] + seconds))
    with pytest.raises(RuntimeError, match='stayed busy'):
        busy()
    with pytest.raises(RuntimeError, match='Cannot verify'):
        training.DemoYieldGuard(fetch=lambda: {'busy': 'unknown'})()


@pytest.mark.skipif(os.environ.get('NIVRA_RUN_CUDA_TRAINING_TEST') != '1',
                    reason='Opt-in CUDA regression; leaves the live service running')
def test_real_cuda_frozen_window_and_binary_head_backprop():
    assert torch.cuda.is_available(), 'Explicit CUDA test requires an available GPU'
    checkpoint = Path(os.environ.get('NIVRA_X3D_BASE_CHECKPOINT',
                                    str(Path(__file__).resolve().parents[1] / 'models/x3d_m_kinetics.pyth')))
    guard = training.DemoYieldGuard()
    guard()
    extractor = training.FrozenX3D(checkpoint, device='cuda', cuda_memory_fraction=.4)
    frames = [np.zeros((224, 224, 3), dtype=np.uint8)] * 16
    features = extractor(training.preprocess_frames(frames))
    assert features.shape == (1, 2048) and np.isfinite(features).all()
    assert next(extractor.model.parameters()).device.type == 'cuda'
    assert not any(parameter.requires_grad for parameter in extractor.model.parameters())
    synthetic = np.zeros((2, 2048), dtype=np.float32)
    synthetic[:, 0] = [-1, 1]
    guard()
    head, details = training.fit_head(synthetic, [0, 1], epochs=2, device='cuda')
    assert details['device'] == 'cuda' and head.weight.device.type == 'cuda'
    assert head.weight.grad is not None and torch.isfinite(head.weight.grad).all()
    scores = training.predict_head(head, synthetic)
    assert isinstance(scores, np.ndarray) and np.isfinite(scores).all()
