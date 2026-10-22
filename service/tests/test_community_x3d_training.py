"""CPU-only small models/synthetic media; never constructs actual X3D."""
from copy import deepcopy
from dataclasses import replace
import json

import numpy as np
import pytest
import torch
from torch import nn

from nivra import community_x3d_training as community
from nivra.training_data import Window


class Prefix(nn.Module):
    def __init__(self):
        super().__init__()
        self.linear = nn.Linear(2, 4)
        self.bn = nn.BatchNorm1d(4)
        self.dropout = nn.Dropout(.5)

    def forward(self, tensor):
        tensor = self.linear(tensor)
        shape = tensor.shape
        return self.dropout(self.bn(tensor.reshape(-1, 4)).reshape(shape))


class Head(nn.Module):
    def __init__(self):
        super().__init__()
        self.pool = nn.Linear(4, 4)
        self.dropout = nn.Dropout(.5)
        self.proj = nn.Sequential(nn.Dropout(.3), nn.Linear(4, 2))
        self.activation = nn.Softmax(dim=1)
        self.output_pool = nn.AdaptiveAvgPool1d(1)

    def forward(self, tensor):
        tensor = self.dropout(self.pool(tensor))
        tensor = self.proj(tensor).transpose(1, 2)
        return self.output_pool(self.activation(tensor)).flatten(1)


class Model(nn.Module):
    def __init__(self):
        super().__init__()
        self.blocks = nn.ModuleList([Prefix(), nn.Identity(), nn.Identity(), nn.Identity(), nn.Identity(), Head()])

    def forward(self, tensor):
        if tensor.ndim == 5:  # Real frame preprocessing API, still a tiny fake model.
            tensor = tensor[:, :2].mean(dim=(2, 3, 4))[:, None].repeat(1, 3, 1)
        for block in self.blocks:
            tensor = block(tensor)
        return tensor


@pytest.fixture(autouse=True)
def tiny_head(monkeypatch):
    monkeypatch.setattr(community, 'HEAD_FEATURES', 4)


def settings():
    return community.Config(input_cache_mib=0, yield_to_demo=False)


def window(label, index=0, split='train'):
    return Window(str(index), 'vid-v2-unresolved-session-cohort', None, 'a' * 64,
                  split, float(index), float(index + 4), label)


def reader(entry):
    x = float(entry.label * 2 - 1)
    return torch.tensor([[[x, .1], [x * 2, .2], [-x / 2, entry.start_seconds / 100 + .3]]])


def identity(value):
    return value


def inputs(tmp_path, monkeypatch):
    records = []
    for index, label in enumerate((0, 0, 1)):
        media = tmp_path / f'clip-{index}.avi'
        media.write_bytes(f'synthetic reviewed clip {index}'.encode())
        records.append({'id': str(index), 'sourceId': 'vid-v2', 'path': media.name,
                        'sha256': community.file_hash(media), 'durationSeconds': 4.,
                        'recordingGroup': 'vid-v2-unresolved-session-cohort', 'split': 'train',
                        'reviewStatus': 'reviewed', 'domain': 'synthetic', 'label': label,
                        'events': [{'startSeconds': 0., 'endSeconds': 4., 'label': label}]})
    raw = {'schemaVersion': 1, 'sources': [{'id': 'vid-v2', 'url': 'https://example.test/vid',
                                          'license': 'CC0-1.0', 'trainingAllowed': True,
                                          'evidence': ['synthetic permission fixture']}], 'recordings': records}
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps(raw), encoding='utf-8')
    monkeypatch.setattr(community, 'MANIFEST_SHA256', community.file_hash(manifest))
    monkeypatch.setattr(community, 'EXPECTED_COUNTS', {'recordings': 3, 'windows': 3, 'positive': 1, 'normal': 2})
    checkpoint = tmp_path / 'baseline.pt'
    checkpoint.write_bytes(b'pinned synthetic baseline fixture, never deserialized')
    monkeypatch.setattr(community, 'CHECKSUM', community.file_hash(checkpoint))
    evidence = tmp_path / 'source.json'
    evidence.write_text(json.dumps({'eligibility': {'trainingAllowed': True}}))
    return manifest, checkpoint, evidence, raw


def make_run(tmp_path, monkeypatch):
    manifest, checkpoint, evidence, _ = inputs(tmp_path, monkeypatch)
    output = tmp_path / 'new-run'
    report = community.run(manifest, tmp_path, checkpoint, output, config=settings(),
                            source_evidence=evidence, model_factory=lambda _: Model(),
                            reader=reader, preprocess=identity)
    return output, report


def test_eval_no_update_forward_semantics_and_softmax_before_pool_are_preserved():
    torch.manual_seed(3)
    model = Model().eval()
    tensor = reader(window(1))
    initial_state = deepcopy(model.state_dict())
    before = model(tensor).detach()
    head = community.enable_head_only(model)
    after = community.probabilities(model, tensor)
    torch.testing.assert_close(after.detach(), before, rtol=0, atol=0)
    assert after.requires_grad and head.weight.requires_grad and head.bias.requires_grad
    assert not any(module.training for module in model.modules())
    for name, value in model.state_dict().items():
        assert torch.equal(value, initial_state[name])
    # Counterexample proves average(Softmax(logits)) is not Softmax(average(logits)).
    toy = model.blocks[-1]
    with torch.no_grad():
        toy.pool.weight.copy_(torch.eye(4))
        toy.pool.bias.zero_()
        toy.proj[1].weight.zero_()
        toy.proj[1].bias.zero_()
        toy.proj[1].weight[0, 0] = 1.
        toy.proj[1].weight[1, 0] = -1.
    spatial = torch.tensor([[[-1., 0., 0., 0.], [-1., 0., 0., 0.], [5., 0., 0., 0.]]])
    retained = toy(spatial)
    wrong_surrogate = toy.proj(spatial).mean(1).softmax(-1)
    assert not torch.allclose(retained, wrong_surrogate, atol=.1)


def test_only_existing_linear_changes_all_bn_dropout_and_nonhead_state_frozen():
    torch.manual_seed(8)
    model = Model()
    initial = deepcopy(model.state_dict())
    details = community.fit(model, [window(0), window(0, 1), window(1, 2)], settings(),
                             reader=reader, preprocess=identity)
    assert details['optimizerSteps'] == 3 and details['exportEpoch'] == 3
    assert details['classCounts'] == [2, 1]
    assert details['classWeights'] == [.75, 1.5]
    assert details['trainableParameters'] == list(community.HEAD_KEYS)
    assert len(details['epochWeightedNLL']) == 3
    for name, value in model.state_dict().items():
        if name in community.HEAD_KEYS:
            assert not torch.equal(initial[name], value)
        else:
            assert torch.equal(initial[name], value)
    assert not any(module.training for module in model.modules())


def test_weighted_nll_accumulation_matches_batched_reference_with_partial_tail():
    torch.manual_seed(19)
    model = Model()
    reference = deepcopy(model)
    entries = [window(0, index) for index in range(7)] + [window(1, index) for index in range(7, 11)]
    result = community.fit(model, entries, settings(), reader=reader, preprocess=identity)
    head = community.enable_head_only(reference)
    optimizer = torch.optim.AdamW(head.parameters(), lr=1e-5, weight_decay=.01)
    labels = torch.tensor([entry.label for entry in entries])
    weights = len(entries) / (2 * torch.bincount(labels).float())
    generator = torch.Generator().manual_seed(17)
    for _ in range(3):
        order = torch.randperm(len(entries), generator=generator)
        for group in order.split(8):
            optimizer.zero_grad(set_to_none=True)
            tensor = torch.cat([reader(entries[index]) for index in group])
            probability = reference(tensor)
            loss = nn.functional.nll_loss(probability.clamp_min(1e-7).log(), labels[group], weight=weights)
            loss.backward()
            optimizer.step()
    assert result['optimizerSteps'] == 6  # full eight and tail three, each of three epochs
    assert result['classWeights'] == pytest.approx([11 / 14, 11 / 8])
    for name, value in model.state_dict().items():
        torch.testing.assert_close(value, reference.state_dict()[name], atol=1e-7, rtol=1e-6)


def test_fixed_seed_repeats_and_guard_failure_stops_before_updates():
    torch.manual_seed(13)
    model = Model()
    repeat = deepcopy(model)
    entries = [window(0), window(1, 1)]
    calls = []
    config = replace(settings(), yield_to_demo=True)
    community.fit(model, entries, config, reader=reader, preprocess=identity, yield_guard=lambda: calls.append(True))
    community.fit(repeat, entries, config, reader=reader, preprocess=identity, yield_guard=lambda: None)
    assert len(calls) >= 12
    for name, value in model.state_dict().items():
        assert torch.equal(value, repeat.state_dict()[name])
    with pytest.raises(RuntimeError, match='busy'):
        community.fit(Model(), entries, config, reader=reader, preprocess=identity,
                      yield_guard=lambda: (_ for _ in ()).throw(RuntimeError('busy')))


@pytest.mark.parametrize('split', ['diagnostic', 'holdout', 'calibration'])
def test_nontrain_windows_cannot_enter_fit(split):
    with pytest.raises(ValueError, match='Only train'):
        community.fit(Model(), [window(0), window(1, 1, split)], settings(),
                      reader=lambda _: pytest.fail('nontrain decoded'))


@pytest.mark.parametrize('change', [
    {'epochs': 2}, {'seed': 18}, {'learning_rate': .0001}, {'weight_decay': 0.},
    {'probability_epsilon': 1e-8}, {'accumulation_steps': 4}, {'cuda_memory_fraction': .4},
    {'device': 'auto'}, {'input_cache_mib': 1537}, {'device': 'cuda', 'yield_to_demo': False},
])
def test_fixed_hypothesis_cannot_be_silently_changed(change):
    with pytest.raises(ValueError):
        replace(settings(), **change).validate()


def test_tampered_nonhead_or_dropout_mode_is_detected():
    model = Model()
    community.enable_head_only(model)
    frozen = community.frozen_hashes(model)
    model.blocks[-1].dropout.train()
    with pytest.raises(ValueError, match='Non-head'):
        community.assert_frozen(model, frozen)
    model.eval()
    with torch.no_grad():
        model.blocks[0].bn.running_mean.add_(1)
    with pytest.raises(ValueError, match='Non-head'):
        community.assert_frozen(model, frozen)


def test_run_safe_cpu_artifact_roundtrip_and_honest_train_only_report(tmp_path, monkeypatch):
    manifest, checkpoint, evidence, _ = inputs(tmp_path, monkeypatch)
    output = tmp_path / 'new-run'
    trained = Model()
    report = community.run(manifest, tmp_path, checkpoint, output, config=settings(),
                            source_evidence=evidence, model_factory=lambda _: trained,
                            reader=reader, preprocess=identity)
    assert report['complete'] and report['candidateSha256'] == community.file_hash(output / 'candidate-state.pt')
    assert report['splits']['train']['windows'] == 3
    assert report['threshold'] == .5 and report['calibration']['status'] == 'uncalibrated'
    for split in ('calibration', 'holdout'):
        assert report['splits'][split] == {'windows': 0, 'status': 'not-available'}
    assert report['holdoutUsedForSelection'] is False and report['liveModelChanged'] is False
    assert report['initialBaselineForwardParity'].startswith('not measured')
    assert report['gpu'] is None
    for name, sha in report['snapshotHashes'].items():
        assert community.file_hash(output / name) == sha
    monkeypatch.setattr(torch.cuda, 'is_available', lambda: pytest.fail('CPU loader probed CUDA'))
    model, same = community.load_candidate(output, model_factory=Model)
    assert same == report and not any(parameter.requires_grad for parameter in model.parameters())
    saved = torch.load(output / 'candidate-state.pt', weights_only=True, map_location='cpu')
    for name, tensor in model.state_dict().items():
        assert torch.equal(tensor, saved['model_state'][name])
    torch.testing.assert_close(community.probabilities(trained, reader(window(1))),
                               community.probabilities(model, reader(window(1))), rtol=0, atol=0)
    candidate = community.CommunityCandidate.__new__(community.CommunityCandidate)
    candidate.model, candidate.report, candidate.device = model, report, 'cpu'
    result = candidate.predict([np.zeros((3, 5, 3), np.uint8)] * 16)
    assert result['fightScore'] == result['classScores'][1]
    assert result['scoreKind'] == 'retained-backbone-softmax'
    assert candidate.metadata()['adaptationSha256'] == report['candidateSha256']
    assert candidate.metadata()['trainedSourceHashes'] == report['snapshotHashes']
    assert candidate.metadata()['baselineSha256'] != report['candidateSha256']


@pytest.mark.parametrize('damage,match', [
    ('manifest-hash', 'manifest checksum'), ('baseline-hash', 'baseline checksum'),
    ('permission', 'permission'), ('rights', 'rights evidence'), ('pending', 'reviewed'),
    ('holdout', 'VID'), ('media', 'SHA-256'), ('cohort', 'VID'), ('counts', 'counts'),
])
def test_invalid_inputs_fail_before_model_output_or_decoding(tmp_path, monkeypatch, damage, match):
    manifest, checkpoint, evidence, raw = inputs(tmp_path, monkeypatch)
    if damage == 'manifest-hash':
        manifest.write_text('{}')
    elif damage == 'baseline-hash':
        checkpoint.write_bytes(b'changed')
    elif damage == 'rights':
        evidence.write_text('{"eligibility":{"trainingAllowed":false}}')
    elif damage == 'media':
        (tmp_path / raw['recordings'][0]['path']).write_bytes(b'changed')
    else:
        if damage == 'permission': raw['sources'][0]['trainingAllowed'] = False
        if damage == 'pending': raw['recordings'][0]['reviewStatus'] = 'pending'
        if damage == 'holdout':
            for record in raw['recordings']: record['split'] = 'holdout'
        if damage == 'cohort': raw['recordings'][0]['recordingGroup'] = 'invented-session'
        if damage == 'counts': raw['recordings'].pop()
        manifest.write_text(json.dumps(raw))
        monkeypatch.setattr(community, 'MANIFEST_SHA256', community.file_hash(manifest))
    output = tmp_path / 'never-created'
    with pytest.raises(ValueError, match=match):
        community.run(manifest, tmp_path, checkpoint, output, config=settings(), source_evidence=evidence,
                      model_factory=lambda _: pytest.fail('invalid inputs reached model'),
                      reader=lambda _: pytest.fail('invalid inputs decoded'))
    assert not output.exists()


@pytest.mark.parametrize('damage', ['weights', 'snapshot', 'threshold', 'frozen-tensor', 'head-shape', 'config', 'selection'])
def test_invalid_artifacts_fail_before_architecture_construction(tmp_path, monkeypatch, damage):
    output, _ = make_run(tmp_path, monkeypatch)
    artifact_path, report_path = output / 'candidate-state.pt', output / 'report.json'
    if damage == 'weights':
        artifact_path.write_bytes(b'changed')
    elif damage == 'snapshot':
        (output / 'source/community_x3d_training.py').write_bytes(b'changed')
    else:
        artifact = torch.load(artifact_path, weights_only=True)
        report = json.loads(report_path.read_text())
        if damage == 'threshold':
            artifact['threshold'] = report['threshold'] = .4
        elif damage == 'frozen-tensor':
            artifact['model_state']['blocks.0.bn.running_mean'][0] += 1
        elif damage == 'head-shape':
            artifact['model_state'][community.HEAD_KEYS[0]] = torch.zeros(2, 3)
        elif damage == 'config':
            artifact['config']['epochs'] = report['config']['epochs'] = 2
        elif damage == 'selection':
            report['training']['exportEpoch'] = 2
        torch.save(artifact, artifact_path)
        report['candidateSha256'] = community.file_hash(artifact_path)
        report_path.write_text(json.dumps(report))
    with pytest.raises(ValueError):
        community.load_candidate(output, model_factory=lambda: pytest.fail('invalid artifact constructed model'))


def test_no_overwrite_safe_baseline_loader_and_no_pretrained_path(tmp_path, monkeypatch):
    manifest, checkpoint, evidence, _ = inputs(tmp_path, monkeypatch)
    output = tmp_path / 'existing'
    output.mkdir()
    with pytest.raises(FileExistsError):
        community.run(manifest, tmp_path, checkpoint, output, config=settings(), source_evidence=evidence)
    model = Model()
    calls = []
    monkeypatch.setattr(community, 'architecture', lambda: Model())

    def loader(_path, **kwargs):
        calls.append(kwargs)
        return {'model': {'backbone.' + name: value for name, value in model.state_dict().items()}}

    monkeypatch.setattr(torch, 'load', loader)
    loaded = community.baseline_model(checkpoint)
    assert calls == [{'map_location': 'cpu', 'weights_only': True}]
    for name, value in model.state_dict().items():
        assert torch.equal(value, loaded.state_dict()[name])
    checkpoint.write_bytes(b'changed')
    with pytest.raises(ValueError, match='checksum'):
        community.baseline_model(checkpoint)
    assert len(calls) == 1


def test_frame_cache_is_bounded_decoded_only_and_reused_in_training(tmp_path, monkeypatch):
    manifest, checkpoint, evidence, _ = inputs(tmp_path, monkeypatch)
    calls = []

    def images(entry):
        calls.append(entry.recording_id)
        return [np.full((2, 4, 3), entry.label * 100, np.uint8)] * 8

    report = community.run(manifest, tmp_path, checkpoint, tmp_path / 'cache-run',
                            config=replace(settings(), input_cache_mib=1), source_evidence=evidence,
                            model_factory=lambda _: Model(), reader=images)
    assert len(calls) == 3
    assert report['inputCache']['misses'] == 3 and report['inputCache']['hits'] == 6
    assert report['inputCache']['residentMiB'] <= 1


def test_cli_fixed_settings_and_reject_cuda_without_cooperation(tmp_path, capsys):
    import train_community_x3d
    assert train_community_x3d.main(['--device', 'cuda', '--no-yield-to-demo',
                                     '--output-dir', str(tmp_path / 'none')]) == 1
    assert 'DemoYieldGuard' in capsys.readouterr().err
