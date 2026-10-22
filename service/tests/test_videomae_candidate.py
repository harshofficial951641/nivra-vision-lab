"""Offline adapter contract tests: only stubs and small synthetic source images."""
from copy import deepcopy
import hashlib
import importlib.util
from importlib.metadata import PackageNotFoundError
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from nivra import videomae_candidate as candidate


@pytest.fixture
def staged(tmp_path, monkeypatch):
    config = {**deepcopy(candidate._CONFIG),
              'id2label': {'0': 'NonViolence', '1': 'Violence'},
              'label2id': {'NonViolence': 0, 'Violence': 1}}
    processor_config = {**deepcopy(candidate._PROCESSOR),
                        'image_processor_type': 'VideoMAEImageProcessor'}
    (tmp_path / 'config.json').write_text(json.dumps(config), encoding='utf-8')
    (tmp_path / 'preprocessor_config.json').write_text(json.dumps(processor_config), encoding='utf-8')
    (tmp_path / 'README.md').write_text('stub card', encoding='utf-8')
    (tmp_path / 'model.safetensors').write_bytes(b'stub; never deserialized')
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.iterdir()}
    monkeypatch.setattr(candidate, 'FILE_SHA256', hashes)
    calls = []

    class Processor:
        def __init__(self):
            self.__dict__.update(deepcopy(candidate._PROCESSOR))
            self.batch = None
            self.frames = None

        @classmethod
        def from_pretrained(cls, path, **kwargs):
            calls.append(('processor-load', path, kwargs))
            return processor

        def __call__(self, frames, **kwargs):
            calls.append(('process', kwargs))
            self.frames = frames
            return self.batch if self.batch is not None else {
                'pixel_values': torch.zeros(1).expand(1, 16, 3, 224, 224)}

    class Model:
        def __init__(self):
            loaded_config = {**deepcopy(config), 'id2label': {0: 'NonViolence', 1: 'Violence'}}
            self.config = SimpleNamespace(num_labels=2, to_dict=lambda: deepcopy(loaded_config))
            self.classifier = SimpleNamespace(weight=torch.zeros(2, 768), bias=torch.zeros(2))
            self.fc_norm = SimpleNamespace(normalized_shape=(768,))
            self.logits = torch.tensor([[1., 3.]])
            self.info = {'missing_keys': [], 'unexpected_keys': [], 'mismatched_keys': [], 'error_msgs': []}
            self.output = None
            self.loaded_config = loaded_config

        @classmethod
        def from_pretrained(cls, path, **kwargs):
            calls.append(('model-load', path, kwargs))
            return model, model.info

        def float(self):
            calls.append(('float',))
            return self

        def to(self, device):
            calls.append(('device', device))
            return self

        def eval(self):
            calls.append(('eval',))
            return self

        def __call__(self, **kwargs):
            assert torch.is_inference_mode_enabled()
            calls.append(('forward', kwargs['pixel_values'].device.type))
            return self.output if self.output is not None else SimpleNamespace(logits=self.logits)

    processor, model = Processor(), Model()
    fake = SimpleNamespace(VideoMAEImageProcessor=Processor, VideoMAEForVideoClassification=Model)
    monkeypatch.setitem(sys.modules, 'transformers', fake)
    monkeypatch.setattr(candidate, 'version', lambda package: '4.57.1')
    return SimpleNamespace(path=tmp_path, config=config, processor_config=processor_config,
                           hashes=hashes, calls=calls, processor=processor, model=model)


def frames(count=16):
    return [np.full((2, 4, 3), [i, i + 30, i + 60], dtype=np.uint8) for i in range(count)]


def rewrite_json(staged, filename, value):
    path = staged.path / filename
    path.write_text(json.dumps(value), encoding='utf-8')
    staged.hashes[filename] = hashlib.sha256(path.read_bytes()).hexdigest()


def test_pinned_source_and_all_four_expected_hashes():
    assert candidate.REVISION == '613844b1d2d27f68944619bf91885a9befb101ac'
    assert candidate.TRANSFORMERS_VERSION == '4.57.1'
    assert dict(candidate.FILE_SHA256) == {
        'README.md': '0d2adb5b283c3c4bd8fd087d5ce85d0c2a6528c7ca6cc6ff65da51645452614f',
        'config.json': '59e7a7ba3196e7d7272304b16dc59e15b09b9f17832d76e8cbd9755487afa8ed',
        'preprocessor_config.json': '4bc9b255ff212041bc28127d4fa0ae1630abca52bb2d882f3e4c0b9e5b763f06',
        'model.safetensors': '5166b055ebee1439d6517c5bf2d516dce7a1f65afc53367f43b5848970853d53',
    }


def test_module_import_does_not_require_transformers(monkeypatch):
    monkeypatch.setitem(sys.modules, 'transformers', None)
    spec = importlib.util.spec_from_file_location('isolated_videomae', Path(candidate.__file__))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.VideoMAECandidate


def test_constructor_is_strict_local_only_and_never_probes_cuda_for_cpu(staged, monkeypatch):
    def forbidden():
        pytest.fail('CPU construction must not probe CUDA')
    monkeypatch.setattr(torch.cuda, 'is_available', forbidden)
    adapter = candidate.VideoMAECandidate(staged.path)
    assert adapter.device == 'cpu'
    assert staged.calls == [
        ('processor-load', staged.path, {'local_files_only': True, 'trust_remote_code': False}),
        ('model-load', staged.path, {
            'local_files_only': True, 'trust_remote_code': False, 'use_safetensors': True,
            'weights_only': True, 'attn_implementation': 'eager', 'output_loading_info': True}),
        ('float',), ('device', 'cpu'), ('eval',),
    ]


@pytest.mark.parametrize('name', ['README.md', 'config.json', 'preprocessor_config.json', 'model.safetensors'])
@pytest.mark.parametrize('damage', ['missing', 'changed'])
def test_every_required_file_checked_before_loading(staged, name, damage):
    path = staged.path / name
    if damage == 'missing':
        path.unlink()
    else:
        path.write_bytes(b'changed')
    with pytest.raises(ValueError, match=name.replace('.', r'\.')):
        candidate.VideoMAECandidate(staged.path)
    assert staged.calls == []


@pytest.mark.parametrize('device', ['auto', 'cuda:0', 'mps', '', None])
def test_only_explicit_cpu_or_cuda(staged, device):
    with pytest.raises(ValueError, match='cpu or cuda'):
        candidate.VideoMAECandidate(staged.path, device=device)
    assert staged.calls == []


def test_missing_directory_rejected_without_loading(tmp_path):
    with pytest.raises(ValueError, match='local directory'):
        candidate.VideoMAECandidate(tmp_path / 'missing')


def test_symlink_rejected_before_loading(staged):
    path = staged.path / 'README.md'
    path.unlink()
    target = staged.path / 'other-card'
    target.write_text('stub card')
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip('Windows requires symlink privileges')
    with pytest.raises(ValueError, match='regular local README'):
        candidate.VideoMAECandidate(staged.path)
    assert staged.calls == []


@pytest.mark.parametrize('installed', ['4.49.0', '4.57.1.dev0', '5.8.1'])
def test_wrong_transformers_version_fails_before_library_loading(staged, monkeypatch, installed):
    monkeypatch.setattr(candidate, 'version', lambda _: installed)
    with pytest.raises(RuntimeError, match='requires Transformers 4.57.1'):
        candidate.VideoMAECandidate(staged.path)
    assert staged.calls == []


def test_missing_transformers_explains_isolation(staged, monkeypatch):
    def absent(_):
        raise PackageNotFoundError('transformers')
    monkeypatch.setattr(candidate, 'version', absent)
    with pytest.raises(RuntimeError, match='isolated Transformers 4.57.1'):
        candidate.VideoMAECandidate(staged.path)
    assert staged.calls == []


def test_explicit_unavailable_cuda_does_not_fallback(staged, monkeypatch):
    monkeypatch.setattr(torch.cuda, 'is_available', lambda: False)
    with pytest.raises(RuntimeError, match='no CPU fallback'):
        candidate.VideoMAECandidate(staged.path, device='cuda')
    assert staged.calls == []


def test_explicit_cuda_device_is_preserved_without_real_cuda_calls(staged, monkeypatch):
    monkeypatch.setattr(torch.cuda, 'is_available', lambda: True)
    adapter = candidate.VideoMAECandidate(staged.path, device='cuda')
    assert adapter.device == 'cuda' and ('device', 'cuda') in staged.calls


@pytest.mark.parametrize('change', [
    {'use_mean_pooling': False}, {'num_frames': 8}, {'hidden_size': 384},
    {'num_attention_heads': 6}, {'num_labels': 7},
    {'id2label': {'0': 'Violence', '1': 'NonViolence'}},
    {'label2id': {'NonViolence': 1, 'Violence': 0}},
])
def test_saved_config_contract_rejected_before_loading(staged, change):
    rewrite_json(staged, 'config.json', {**staged.config, **change})
    with pytest.raises(ValueError, match='config mismatch|class order|two labels'):
        candidate.VideoMAECandidate(staged.path)
    assert staged.calls == []


def test_saved_and_loaded_processor_must_match(staged):
    staged.processor.do_center_crop = False
    with pytest.raises(ValueError, match='loaded processor mismatch: do_center_crop'):
        candidate.VideoMAECandidate(staged.path)
    assert not any(call[0] == 'model-load' for call in staged.calls)


def test_changed_saved_normalization_rejected(staged):
    rewrite_json(staged, 'preprocessor_config.json', {**staged.processor_config, 'image_mean': [.5] * 3})
    with pytest.raises(ValueError, match='processor config mismatch: image_mean'):
        candidate.VideoMAECandidate(staged.path)
    assert staged.calls == []


@pytest.mark.parametrize('key', ['missing_keys', 'unexpected_keys', 'mismatched_keys', 'error_msgs', 'warnings'])
def test_all_nonempty_loading_diagnostics_fail(staged, key):
    staged.model.info[key] = ['incompatible checkpoint']
    with pytest.raises(ValueError, match='did not load cleanly'):
        candidate.VideoMAECandidate(staged.path)
    assert ('device', 'cpu') not in staged.calls


@pytest.mark.parametrize('damage', ['labels', 'class-order', 'frames', 'pooling', 'head', 'bias', 'norm'])
def test_loaded_model_contract_rechecked(staged, damage):
    if damage == 'labels':
        staged.model.config.num_labels = 7
    elif damage == 'class-order':
        staged.model.loaded_config['id2label'] = {0: 'Violence', 1: 'NonViolence'}
    elif damage == 'frames':
        staged.model.loaded_config['num_frames'] = 32
    elif damage == 'pooling':
        staged.model.loaded_config['use_mean_pooling'] = False
    elif damage == 'head':
        staged.model.classifier.weight = torch.zeros(7, 768)
    elif damage == 'bias':
        staged.model.classifier.bias = torch.zeros(7)
    else:
        staged.model.fc_norm = None
    with pytest.raises(ValueError, match='two labels|class order|config mismatch|shape mismatch'):
        candidate.VideoMAECandidate(staged.path)
    assert ('device', 'cpu') not in staged.calls


@pytest.mark.parametrize('count', [8, 15, 16, 23])
def test_sampling_rgb_source_dimensions_and_softmax(staged, count):
    adapter = candidate.VideoMAECandidate(staged.path)
    observed = frames(count)
    originals = [frame.copy() for frame in observed]
    result = adapter.predict(observed)
    indices = np.linspace(0, count - 1, 16).astype(int)
    for rgb, index in zip(staged.processor.frames, indices):
        assert rgb.shape == (2, 4, 3) and rgb.dtype == np.uint8 and rgb.flags.c_contiguous
        np.testing.assert_array_equal(rgb, originals[index][:, :, ::-1])
    for frame, original in zip(observed, originals):
        np.testing.assert_array_equal(frame, original)
    expected = torch.tensor([1., 3.]).softmax(-1).tolist()
    assert result == {'fightScore': expected[1], 'classScores': expected,
                      'scoreKind': 'softmax-on-logits', 'fightIndex': 1}
    assert staged.calls[-1] == ('forward', 'cpu')
    assert result['fightScore'] != pytest.approx(3.)


@pytest.mark.parametrize('bad', [
    [], None, (x for x in []), np.zeros((0, 2, 4, 3), dtype=np.uint8),
    np.array(1, dtype=np.uint8),
    [np.zeros((2, 4, 3), dtype=np.uint8)] * 7,
    [np.zeros((2, 4, 3), dtype=np.float32)] * 8,
    [np.zeros((2, 4), dtype=np.uint8)] * 8,
    [np.zeros((2, 4, 4), dtype=np.uint8)] * 8,
    [np.zeros((0, 4, 3), dtype=np.uint8)] * 8,
])
def test_invalid_input_fails_before_processor(staged, bad):
    adapter = candidate.VideoMAECandidate(staged.path)
    before = len(staged.calls)
    with pytest.raises(ValueError, match='frames|images'):
        adapter.predict(bad)
    assert len(staged.calls) == before


def test_unsampled_frame_is_still_validated(staged):
    adapter = candidate.VideoMAECandidate(staged.path)
    observed = frames(40)
    assert 1 not in np.linspace(0, 39, 16).astype(int)
    observed[1] = np.zeros((4, 4, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match='same dimensions'):
        adapter.predict(observed)
    assert not any(call[0] == 'process' for call in staged.calls)


def test_array_batch_is_accepted(staged):
    adapter = candidate.VideoMAECandidate(staged.path)
    assert adapter.predict(np.stack(frames(8)))['fightIndex'] == 1


@pytest.mark.parametrize('pixels', [
    torch.zeros(1, 16, 3, 2, 4), torch.zeros(1, 3, 16, 224, 224),
    torch.zeros(1, dtype=torch.float64).expand(1, 16, 3, 224, 224),
    torch.tensor([float('nan')]).expand(1, 16, 3, 224, 224),
])
def test_bad_processor_tensor_never_reaches_model(staged, pixels):
    adapter = candidate.VideoMAECandidate(staged.path)
    staged.processor.batch = {'pixel_values': pixels}
    with pytest.raises(ValueError, match='invalid pixel_values'):
        adapter.predict(frames())
    assert not any(call[0] == 'forward' for call in staged.calls)


@pytest.mark.parametrize('logits', [
    torch.zeros(2), torch.zeros(2, 2), torch.zeros(1, 7),
    torch.tensor([[0, 1]]), torch.tensor([[float('inf'), 1.]]),
    torch.tensor([[0., float('nan')]]), None,
])
def test_wrong_or_nonfinite_model_output_fails(staged, logits):
    adapter = candidate.VideoMAECandidate(staged.path)
    staged.model.logits = logits
    with pytest.raises(ValueError, match='two finite logits'):
        adapter.predict(frames())


def test_metadata_is_defensive_and_exposes_sampling_and_evidence_limits(staged):
    adapter = candidate.VideoMAECandidate(staged.path)
    first = adapter.metadata()
    first['revision'] = 'mutable caller copy'
    first['files']['config.json'] = 'changed'
    first['preprocess']['image_mean'][0] = 0
    fresh = adapter.metadata()
    assert fresh['revision'] == candidate.REVISION
    assert fresh['files']['config.json'] == staged.hashes['config.json']
    assert fresh['preprocess']['image_mean'] == [.485, .456, .406]
    assert fresh['preprocess']['repeatIndicesFor8To15Frames'] is True
    assert 'caller must validate' in fresh['preprocess']['sourceTimeCoverage']
    assert 'unknown' in fresh['provenance']['trainingDataset']
    assert 'unverified' in fresh['provenance']['crowdAndNightEvidence']
