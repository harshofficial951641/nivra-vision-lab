from copy import deepcopy
from dataclasses import replace
import json

import numpy as np
import pytest
import torch
from torch import nn

from nivra import x3d_finetune as ft
from nivra.training_data import Window, load_manifest


class TinyHead(nn.Module):
    def __init__(self):
        super().__init__()
        self.pool = nn.Linear(3, 4)
        self.proj = nn.Linear(4, 2)
        self.activation = None

    def forward(self, tensor):
        return self.proj(torch.tanh(self.pool(tensor)))


class TinyModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.blocks = nn.ModuleList([
            nn.Sequential(nn.Linear(2, 3), nn.BatchNorm1d(3), nn.Tanh()),
            nn.Sequential(nn.Linear(3, 3), nn.BatchNorm1d(3), nn.Tanh()),
            TinyHead(),
        ])

    def forward(self, tensor):
        if tensor.ndim == 5:  # Also exercise the real frame preprocessing API.
            tensor = tensor[:, :2].mean(dim=(2, 3, 4))
        for block in self.blocks:
            tensor = block(tensor)
        return tensor


def window(label=0, index=0, split='train'):
    return Window(str(index), str(index), None, 'a' * 64, split, float(index), float(index + 4), label)


def reader(entry):
    return torch.tensor([[entry.label * 2. - 1., entry.start_seconds / 10 + .1]])


def identity(tensor):
    return tensor


def config(**kwargs):
    return ft.FineTuneConfig(epochs=2, head_learning_rate=.001,
                            backbone_learning_rate=.0001, yield_to_demo=False, **kwargs)


@pytest.mark.parametrize('last_stage', [False, True])
def test_real_updates_only_intended_stages_and_all_bn_frozen(last_stage):
    torch.manual_seed(7)
    model = TinyModel()
    before = deepcopy(model.state_dict())
    settings = config(train_last_stage=last_stage, accumulation_steps=2)
    result = ft.fit(model, [window(0), window(1, 1), window(0, 2)], settings,
                    reader=reader, preprocess=identity)
    after = model.state_dict()
    assert torch.equal(before['blocks.0.0.weight'], after['blocks.0.0.weight'])
    assert not torch.equal(before['blocks.2.pool.weight'], after['blocks.2.pool.weight'])
    assert not torch.equal(before['blocks.2.proj.weight'], after['blocks.2.proj.weight'])
    assert torch.equal(before['blocks.1.0.weight'], after['blocks.1.0.weight']) is (not last_stage)
    assert result['optimizerSteps'] == 4  # two groups per epoch, tail included
    assert result['classWeights'] == pytest.approx([.75, 1.5])
    for name, module in model.named_modules():
        if isinstance(module, nn.modules.batchnorm._BatchNorm):
            assert not module.training
            assert not any(parameter.requires_grad for parameter in module.parameters())
            for suffix in ('weight', 'bias', 'running_mean', 'running_var', 'num_batches_tracked'):
                assert torch.equal(before[name + '.' + suffix], after[name + '.' + suffix])
    # Re-entering training mode must still keep every BN frozen.
    ft.training_mode(model, last_stage)
    assert all(not module.training for module in model.modules()
               if isinstance(module, nn.modules.batchnorm._BatchNorm))


@pytest.mark.parametrize('weighted', [False, True])
def test_accumulation_matches_weighted_batched_reference_including_tail(weighted):
    torch.manual_seed(33)
    model = TinyModel()
    reference = deepcopy(model)
    entries = [window(0, index) for index in range(3)] + [window(1, 3), window(1, 4)]
    settings = replace(config(class_weight=weighted, accumulation_steps=3), epochs=1)
    result = ft.fit(model, entries, settings, reader=reader, preprocess=identity)
    ft.training_mode(reference, True)
    head_ids = {id(parameter) for parameter in reference.blocks[-1].parameters()}
    trainable = [parameter for parameter in reference.parameters() if parameter.requires_grad]
    optimizer = torch.optim.AdamW([
        {'params': [parameter for parameter in trainable if id(parameter) in head_ids], 'lr': settings.head_learning_rate},
        {'params': [parameter for parameter in trainable if id(parameter) not in head_ids], 'lr': settings.backbone_learning_rate},
    ], weight_decay=settings.weight_decay)
    labels = torch.tensor([entry.label for entry in entries])
    weights = len(entries) / (2 * torch.bincount(labels).float()) if weighted else None
    order = torch.randperm(len(entries), generator=torch.Generator().manual_seed(settings.seed))
    for group in order.split(3):
        optimizer.zero_grad(set_to_none=True)
        x = torch.cat([reader(entries[index]) for index in group])
        loss = nn.functional.cross_entropy(reference(x), labels[group], weight=weights)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(trainable, 1.)
        optimizer.step()
    assert result['optimizerSteps'] == 2
    for key, tensor in reference.state_dict().items():
        torch.testing.assert_close(model.state_dict()[key], tensor, atol=1e-7, rtol=1e-6)


def test_seed_repeatability_and_yield_at_microbatch_boundaries():
    torch.manual_seed(44)
    model = TinyModel()
    repeat = deepcopy(model)
    entries = [window(0), window(1, 1)]
    calls = []
    settings = replace(config(), yield_to_demo=True)
    ft.fit(model, entries, settings, reader=reader, preprocess=identity,
           yield_guard=lambda: calls.append('guard'))
    ft.fit(repeat, entries, settings, reader=reader, preprocess=identity, yield_guard=lambda: None)
    assert len(calls) >= 2 * len(entries) * settings.epochs
    for name, value in model.state_dict().items():
        torch.testing.assert_close(value, repeat.state_dict()[name], atol=0, rtol=0)


def test_fit_rejects_other_splits_before_reading_and_missing_guard():
    def forbidden(_):
        pytest.fail('Non-train data was decoded')
    for split in ('holdout', 'calibration', 'diagnostic'):
        with pytest.raises(ValueError, match='train windows only'):
            ft.fit(TinyModel(), [window(0), window(1, 1, split)], config(), reader=forbidden)
    with pytest.raises(ValueError, match='yield guard'):
        ft.fit(TinyModel(), [window(0), window(1)], replace(config(), yield_to_demo=True))


@pytest.mark.parametrize('overrides', [
    {'epochs': 0}, {'seed': True}, {'accumulation_steps': 0}, {'train_last_stage': 1},
    {'head_learning_rate': float('nan')}, {'backbone_learning_rate': .002},
    {'weight_decay': float('inf')}, {'cuda_memory_fraction': True},
    {'device': 'cuda', 'yield_to_demo': False},
])
def test_invalid_config(overrides):
    with pytest.raises(ValueError):
        replace(config(), **overrides).validate()


def make_inputs(tmp_path, *, evaluation=False, vid=False):
    source_id = 'vid-v2' if vid else 'synthetic-source'
    source = {'id': source_id, 'url': 'https://example.test/synthetic', 'license': 'synthetic-fixture',
              'trainingAllowed': True, 'evidence': ['Synthetic test only']}
    records = []
    for split in (('train', 'calibration', 'holdout') if evaluation else ('train',)):
        for label in (0, 1):
            name = f'{split}-{label}.bin'
            media = tmp_path / name
            media.write_bytes(name.encode())
            records.append({'id': name, 'sourceId': source_id,
                            'recordingGroup': ft.VID_COHORT if vid else name,
                            'path': name, 'sha256': ft.file_hash(media), 'durationSeconds': 4.,
                            'split': split, 'reviewStatus': 'reviewed', 'domain': 'synthetic',
                            'label': label, 'events': [{'startSeconds': 0., 'endSeconds': 4., 'label': label}]})
    raw = {'schemaVersion': 1, 'sources': [source], 'recordings': records}
    path = tmp_path / 'input.json'
    path.write_text(json.dumps(raw), encoding='utf-8')
    checkpoint = tmp_path / 'base.pyth'
    checkpoint.write_bytes(b'pinned synthetic test base')
    return path, checkpoint, raw


def test_run_no_holdout_fitting_threshold_sealed_then_safe_full_roundtrip(tmp_path, monkeypatch):
    path, checkpoint, raw = make_inputs(tmp_path, evaluation=True)
    # Skew evaluation labels: balanced training weights must remain [1, 1].
    extra = deepcopy(raw['recordings'][-2])
    extra['id'] = extra['recordingGroup'] = 'additional-holdout-normal'
    raw['recordings'].append(extra)
    path.write_text(json.dumps(raw), encoding='utf-8')
    monkeypatch.setattr(ft, 'BASE_SHA256', ft.file_hash(checkpoint))
    calls = []
    select = ft.select_threshold

    def select_threshold(scores, labels):
        calls.append('threshold-sealed')
        return select(scores, labels)

    monkeypatch.setattr(ft, 'select_threshold', select_threshold)

    def checked_reader(entry):
        if entry.split != 'train':
            # fitting has finished: two epochs read two training windows each,
            # followed by exactly two training predictions.
            assert calls.count('train') == 6
        if entry.split == 'holdout':
            assert 'threshold-sealed' in calls
        calls.append(entry.split)
        return reader(entry)

    evidence = tmp_path / 'evidence.txt'
    evidence.write_text('explicit synthetic permission')
    output = tmp_path / 'new-run'
    report = ft.run(path, tmp_path, checkpoint, output, config=config(),
                    provenance_files=[evidence], model_factory=lambda _: TinyModel(),
                    reader=checked_reader, preprocess=identity)
    assert report['training']['classCounts'] == [1, 1]
    assert report['training']['classWeights'] == [1., 1.]
    assert report['holdoutUsedForSelection'] is False and report['liveModelChanged'] is False
    assert report['gpu'] is None
    for name, digest in report['snapshotHashes'].items():
        assert ft.file_hash(output / name) == digest
    saved = torch.load(output / 'candidate-state.pt', weights_only=True, map_location='cpu')
    assert 'model_state' in saved and 'head_state' not in saved
    assert all(tensor.device.type == 'cpu' for tensor in saved['model_state'].values())
    model, loaded_report = ft.load_candidate(output, model_factory=TinyModel)
    assert not model.training and not any(parameter.requires_grad for parameter in model.parameters())
    for name, value in model.state_dict().items():
        torch.testing.assert_close(value, saved['model_state'][name])
    candidate = ft.FineTuneCandidate(output, model_factory=TinyModel)
    assert 0 <= candidate.predict([np.zeros((8, 8, 3), dtype=np.uint8)] * 16) <= 1
    assert loaded_report == report
    with pytest.raises(FileExistsError):
        ft.run(path, tmp_path, checkpoint, output, config=config(), model_factory=lambda _: pytest.fail('overwrite'))


def test_train_only_vid_remains_one_cohort_with_empty_evaluation(tmp_path, monkeypatch):
    path, checkpoint, _ = make_inputs(tmp_path, vid=True)
    monkeypatch.setattr(ft, 'BASE_SHA256', ft.file_hash(checkpoint))
    report = ft.run(path, tmp_path, checkpoint, tmp_path / 'vid-run', config=config(),
                    model_factory=lambda _: TinyModel(), reader=reader, preprocess=identity)
    assert report['splits']['train']['recordingGroups'] == 1
    assert report['calibration']['status'] == 'uncalibrated' and report['threshold'] == .5
    for split in ('calibration', 'holdout'):
        assert report['splits'][split]['selectedWindows'] == 0
        assert report['splits'][split]['metrics'] == {'status': 'not-available', 'windows': 0}


@pytest.mark.parametrize('mutation,match', [
    ('permission', 'permission'), ('pending', 'reviewed'), ('media-hash', 'SHA-256'),
    ('base-hash', 'checksum'), ('vid-split', 'VID'), ('vid-group', 'VID'),
])
def test_bad_inputs_fail_before_model_or_output(tmp_path, monkeypatch, mutation, match):
    path, checkpoint, raw = make_inputs(tmp_path, vid=mutation.startswith('vid'))
    monkeypatch.setattr(ft, 'BASE_SHA256', ft.file_hash(checkpoint))
    if mutation == 'permission':
        raw['sources'][0]['trainingAllowed'] = False
    elif mutation == 'pending':
        raw['recordings'][0]['reviewStatus'] = 'pending'
    elif mutation == 'media-hash':
        raw['recordings'][0]['sha256'] = 'f' * 64
    elif mutation == 'base-hash':
        checkpoint.write_bytes(b'tampered base')
    elif mutation == 'vid-split':
        for record in raw['recordings']:
            record['split'] = 'holdout'
    elif mutation == 'vid-group':
        raw['recordings'][0]['recordingGroup'] = 'invented-session'
    path.write_text(json.dumps(raw), encoding='utf-8')
    output = tmp_path / 'must-not-exist'
    with pytest.raises(ValueError, match=match):
        ft.run(path, tmp_path, checkpoint, output, config=config(),
               model_factory=lambda _: pytest.fail('Untrusted inputs reached model construction'))
    assert not output.exists()


def test_vid_doi_alias_still_cannot_create_independent_splits(tmp_path):
    path, _, raw = make_inputs(tmp_path)
    raw['sources'][0]['url'] = 'https://example.test/?doi=10.7910%2FDVN%2FN4LNZD'
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match='VID'):
        ft.validate_vid_cohort(load_manifest(path, tmp_path))


def test_official_unpinned_weights_rejected_before_torch_load(tmp_path, monkeypatch):
    path = tmp_path / 'bad.pyth'
    path.write_bytes(b'not official')
    monkeypatch.setattr(ft.torch, 'load', lambda *_args, **_kwargs: pytest.fail('Unsafe load'))
    with pytest.raises(ValueError, match='checksum'):
        ft.official_model(path)


@pytest.mark.parametrize('tamper', ['candidate', 'snapshot', 'contract', 'tensor', 'report-type', 'artifact-type'])
def test_safe_loader_rejects_hash_contract_and_state_corruption(tmp_path, monkeypatch, tamper):
    path, checkpoint, _ = make_inputs(tmp_path)
    monkeypatch.setattr(ft, 'BASE_SHA256', ft.file_hash(checkpoint))
    output = tmp_path / 'run'
    ft.run(path, tmp_path, checkpoint, output, config=replace(config(), epochs=1),
           model_factory=lambda _: TinyModel(), reader=reader, preprocess=identity)
    if tamper == 'candidate':
        (output / 'candidate-state.pt').write_bytes(b'changed')
    elif tamper == 'snapshot':
        (output / 'manifest.json').write_text('{}')
    elif tamper == 'report-type':
        (output / 'report.json').write_text('[]')
    else:
        artifact = torch.load(output / 'candidate-state.pt', weights_only=True)
        if tamper == 'artifact-type':
            artifact = []
        elif tamper == 'contract':
            artifact['preprocessing'] = {'wrong': True}
        else:
            artifact['model_state']['blocks.2.proj.weight'][0, 0] = float('nan')
        torch.save(artifact, output / 'candidate-state.pt')
        report_path = output / 'report.json'
        report = json.loads(report_path.read_text())
        report['candidateSha256'] = ft.file_hash(output / 'candidate-state.pt')
        report_path.write_text(json.dumps(report))
    with pytest.raises(ValueError):
        ft.load_candidate(output, model_factory=lambda: pytest.fail('Invalid state reached model construction'))


def test_unavailable_cuda_and_cap_fail_without_output(tmp_path, monkeypatch):
    monkeypatch.delenv('CUBLAS_WORKSPACE_CONFIG', raising=False)
    monkeypatch.setattr(torch.cuda, 'is_initialized', lambda: False)
    monkeypatch.setattr(torch.cuda, 'is_available', lambda: False)
    with pytest.raises(RuntimeError, match='no CPU fallback'):
        ft.run(tmp_path / 'missing', tmp_path, tmp_path / 'missing-base', tmp_path / 'output',
               config=replace(config(), device='cuda', yield_to_demo=True))
    assert not (tmp_path / 'output').exists()
    caps = []
    monkeypatch.setattr(torch.cuda, 'is_available', lambda: True)
    monkeypatch.setattr(torch.cuda, 'set_per_process_memory_fraction', caps.append)
    assert ft.resolve_device('cuda', .35).type == 'cuda'
    assert caps == [.35]


def test_cuda_workspace_policy_before_context_and_explicit_pooling_warnings(monkeypatch):
    monkeypatch.delenv('CUBLAS_WORKSPACE_CONFIG', raising=False)
    monkeypatch.setattr(torch.cuda, 'is_initialized', lambda: False)
    monkeypatch.setattr(ft, 'resolve_device', lambda device, fraction: torch.device(device))
    settings = replace(config(), device='cuda', yield_to_demo=True)
    assert ft.training_device(settings).type == 'cuda'
    assert ft.os.environ['CUBLAS_WORKSPACE_CONFIG'] == ':4096:8'
    monkeypatch.setenv('CUBLAS_WORKSPACE_CONFIG', ':16:8')
    assert ft.training_device(settings).type == 'cuda'
    monkeypatch.setenv('CUBLAS_WORKSPACE_CONFIG', 'invalid')
    with pytest.raises(ValueError, match='CUBLAS_WORKSPACE_CONFIG'):
        ft.training_device(settings)
    monkeypatch.delenv('CUBLAS_WORKSPACE_CONFIG')
    monkeypatch.setattr(torch.cuda, 'is_initialized', lambda: True)
    with pytest.raises(RuntimeError, match='fresh training process'):
        ft.training_device(settings)
    monkeypatch.setattr(torch.cuda, 'is_initialized', lambda: False)
    policies = []
    monkeypatch.setattr(torch, 'use_deterministic_algorithms', lambda mode, **kwargs: policies.append((mode, kwargs)))
    ft.seed_everything(17, 'cuda')  # Seeds only; no CUDA tensors or kernels.
    ft.seed_everything(17, 'cpu')
    assert policies == [(True, {'warn_only': True}), (True, {'warn_only': False})]


def test_cpu_diagnostics_preserve_fixed_threshold_and_existing_windows(tmp_path):
    media = tmp_path / 'clip.bin'
    media.write_bytes(b'synthetic diagnostic')
    corpus = tmp_path / 'corpus.json'
    clip = {'id': 'diagnostic', 'path': media.name, 'sha256': ft.file_hash(media),
            'annotationStatus': 'reviewed', 'sourceGroup': 'one-recording', 'split': 'holdout',
            'durationMs': 5000, 'events': [{'startMs': 1000, 'endMs': 4000, 'label': 'contact'}]}
    corpus.write_text(json.dumps([clip]))
    run_dir = tmp_path / 'candidate'
    run_dir.mkdir()
    (run_dir / 'report.json').write_text('{}')

    class Candidate:
        def __init__(self, _):
            self.report = {'threshold': .5, 'candidateSha256': 'a' * 64}

        def predict(self, frames):
            return frames[0]

    output = tmp_path / 'diagnostics.json'
    report = ft.diagnose(run_dir, corpus, output, candidate_factory=Candidate,
                         window_reader=lambda *_: [(4000, 0, [.5]), (4400, 400, [.8])])
    assert report['clips']['diagnostic']['candidateReviewWindows'] == 1  # strict >
    assert report['thresholdFittedHere'] is False and report['liveModelChanged'] is False
    assert report['clips']['diagnostic']['samples'][0]['labelledEventOverlaps'][0]['overlapMs'] == 3000
    with pytest.raises(FileExistsError):
        ft.diagnose(run_dir, corpus, output)
    media.write_bytes(b'changed')
    with pytest.raises(ValueError, match='checksum'):
        ft.diagnose(run_dir, corpus, tmp_path / 'bad.json',
                     candidate_factory=lambda _: pytest.fail('Tampered diagnostic loaded model'))


def test_cli_help_and_invalid_cuda_settings_do_not_train(capsys, tmp_path):
    import finetune_x3d
    assert finetune_x3d.main(['train', '--manifest', str(tmp_path / 'missing'),
                              '--data-root', str(tmp_path), '--base-checkpoint', 'missing',
                              '--output-dir', str(tmp_path / 'output'), '--device', 'cuda',
                              '--no-yield-to-demo']) == 1
    assert 'DemoYieldGuard' in capsys.readouterr().err
