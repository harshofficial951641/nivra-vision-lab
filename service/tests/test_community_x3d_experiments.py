"""Tiny CPU models only. No actual checkpoints, CUDA, media or model inference."""
from copy import deepcopy
from dataclasses import replace
import json

import numpy as np
import pytest
import torch
from torch import nn

from nivra import community_x3d_experiments as experiment
from nivra import community_x3d_training as base
from test_community_x3d_training import Model, inputs, reader, identity, window


@pytest.fixture(autouse=True)
def cpu_only(monkeypatch):
    monkeypatch.setattr(base, 'HEAD_FEATURES', 4)
    # AdamW itself queries this even for CPU tensors; never reach real CUDA.
    monkeypatch.setattr(torch.cuda, 'is_available', lambda: False)


def settings(epochs=3):
    return experiment.Config(max_epochs=epochs, input_cache_mib=0, yield_to_demo=False)


def make_run(tmp_path, monkeypatch, epochs=3):
    manifest, checkpoint, evidence, _ = inputs(tmp_path, monkeypatch)
    output = tmp_path / 'new-run'
    report = experiment.run(manifest, tmp_path, checkpoint, output,
                            manifest_sha256=base.file_hash(manifest), config=settings(epochs),
                            source_evidence=evidence, model_factory=lambda _: Model(),
                            reader=reader, preprocess=identity)
    return output, report, base.file_hash(manifest)


@pytest.mark.parametrize('epochs', [3, 10, 20])
def test_one_trajectory_matches_batched_weighted_nll_and_tail_at_every_milestone(epochs):
    torch.manual_seed(19)
    model = Model()
    reference = deepcopy(model)
    entries = [window(0, index) for index in range(7)] + [window(1, index) for index in range(7, 11)]
    before = deepcopy(model.state_dict())
    captured = {}
    result = experiment.fit(model, entries, settings(epochs), reader=reader, preprocess=identity,
                            on_milestone=lambda epoch, state, details: captured.update({epoch: state}))
    head = base.enable_head_only(reference)
    optimizer = torch.optim.AdamW(head.parameters(), lr=1e-5, weight_decay=.01)
    labels = torch.tensor([entry.label for entry in entries])
    weights = len(entries) / (2 * torch.bincount(labels).float())
    generator = torch.Generator().manual_seed(17)
    assert set(result) == {epoch for epoch in (3, 10, 20) if epoch <= epochs}
    for epoch in range(1, epochs + 1):
        order = torch.randperm(len(entries), generator=generator)
        for group in order.split(8):
            optimizer.zero_grad(set_to_none=True)
            output = reference(torch.cat([reader(entries[index]) for index in group]))
            nn.functional.nll_loss(output.clamp_min(1e-7).log(), labels[group], weight=weights).backward()
            optimizer.step()
        if epoch in result:
            assert result[epoch]['optimizerSteps'] == epoch * 2
            assert result[epoch]['microbatches'] == epoch * 11
            assert len(result[epoch]['epochWeightedNLL']) == epoch
            for name, value in reference.state_dict().items():
                torch.testing.assert_close(captured[epoch][name], value, atol=1e-7, rtol=1e-6)
    for name, value in model.state_dict().items():
        if name in base.HEAD_KEYS:
            assert not torch.equal(before[name], value)
        else:
            assert torch.equal(before[name], value)
    assert not any(module.training for module in model.modules())


@pytest.mark.parametrize('epochs', [3, 10, 20])
def test_safe_milestones_roundtrip_parity_independent_identity_and_empty_eval(tmp_path, monkeypatch, epochs):
    output, seal, sha = make_run(tmp_path, monkeypatch, epochs)
    expected = {str(epoch) for epoch in experiment.MILESTONES if epoch <= epochs}
    assert set(seal['milestones']) == expected
    assert seal['gpu'] is None and seal['complete']
    candidate_hashes = []
    for epoch in sorted(map(int, expected)):
        directory = output / f'epoch-{epoch:03d}'
        report, artifact = experiment.validate_artifact(directory, manifest_sha256=sha)
        with monkeypatch.context() as loader_policy:
            loader_policy.setattr(torch.cuda, 'is_available', lambda: pytest.fail('CPU loader probed CUDA'))
            model, same = experiment.load_candidate(directory, manifest_sha256=sha, model_factory=Model)
        assert same == report
        assert report['training']['exportEpoch'] == epoch
        assert report['training']['optimizerSteps'] == epoch
        assert report['splits']['train']['windows'] == 3
        assert report['splits']['train']['recordings'] == 3
        for split in ('holdout', 'calibration'):
            assert report['splits'][split] == {'windows': 0, 'status': 'not-available'}
        assert not any(parameter.requires_grad for parameter in model.parameters())
        restored = Model().eval()
        restored.load_state_dict(artifact['model_state'])
        torch.testing.assert_close(model(reader(window(1))), restored(reader(window(1))), rtol=0, atol=0)
        assert all(value.device.type == 'cpu' for value in artifact['model_state'].values())
        candidate_hashes.append(report['candidateSha256'])
        candidate = experiment.ExperimentCandidate.__new__(experiment.ExperimentCandidate)
        candidate.model, candidate.report, candidate.device = model, report, 'cpu'
        result = candidate.predict([np.zeros((3, 5, 3), np.uint8)] * 8)
        assert result['fightScore'] == result['classScores'][1]
        assert result['scoreKind'] == 'retained-backbone-softmax' and result['fightIndex'] == 1
        assert candidate.metadata()['kind'] == experiment.KIND
        assert candidate.metadata()['exportEpoch'] == epoch
        assert candidate.metadata()['trainingManifestSha256'] == sha
        with pytest.raises(ValueError, match='eight'):
            candidate.predict([np.zeros((3, 5, 3), np.uint8)] * 7)
    assert len(set(candidate_hashes)) == len(expected)


@pytest.mark.parametrize('split', ['holdout', 'calibration', 'diagnostic'])
def test_no_nontraining_fit(split):
    with pytest.raises(ValueError, match='Only train'):
        experiment.fit(Model(), [window(0), window(1, split=split)], settings(),
                        reader=lambda _: pytest.fail('nontrain decoded'))


@pytest.mark.parametrize('change', [
    {'max_epochs': 4}, {'max_epochs': True}, {'seed': 18}, {'learning_rate': .001},
    {'weight_decay': 0.}, {'accumulation_steps': 4}, {'probability_epsilon': 1e-8},
    {'cuda_memory_fraction': .4}, {'input_cache_mib': 1537}, {'device': 'auto'},
    {'device': 'cuda', 'yield_to_demo': False},
])
def test_profile_is_fixed_and_device_explicit(change):
    with pytest.raises(ValueError):
        replace(settings(), **change).validate()


@pytest.mark.parametrize('damage', ['manifest', 'baseline', 'rights', 'media', 'permission',
                                   'review', 'cohort', 'holdout', 'license', 'source', 'one-class', 'missing-events'])
def test_input_failures_precede_model_and_output(tmp_path, monkeypatch, damage):
    manifest, checkpoint, evidence, raw = inputs(tmp_path, monkeypatch)
    sha = base.file_hash(manifest)
    if damage == 'manifest':
        sha = '0' * 64
    elif damage == 'baseline':
        checkpoint.write_bytes(b'changed')
    elif damage == 'rights':
        evidence.write_text('{"eligibility":{"trainingAllowed":false}}')
    elif damage == 'media':
        (tmp_path / raw['recordings'][0]['path']).write_bytes(b'changed')
    else:
        if damage == 'permission': raw['sources'][0]['trainingAllowed'] = False
        if damage == 'review': raw['recordings'][0]['reviewStatus'] = 'pending'
        if damage == 'cohort': raw['recordings'][0]['recordingGroup'] = 'invented-session'
        if damage == 'holdout': raw['recordings'][0]['split'] = 'holdout'
        if damage == 'license': raw['sources'][0]['license'] = 'unknown'
        if damage == 'source': raw['sources'][0]['id'] = raw['recordings'][0]['sourceId'] = 'other'
        if damage == 'missing-events': raw['recordings'][0]['events'] = []
        if damage == 'one-class':
            for record in raw['recordings']:
                record['label'] = record['events'][0]['label'] = 0
        manifest.write_text(json.dumps(raw))
        sha = base.file_hash(manifest)
    output = tmp_path / 'never-created'
    with pytest.raises(ValueError):
        experiment.run(manifest, tmp_path, checkpoint, output, manifest_sha256=sha,
                        config=settings(), source_evidence=evidence,
                        model_factory=lambda _: pytest.fail('invalid input constructed model'))
    assert not output.exists()


def reseal(directory):
    report_path = directory / 'report.json'
    report = json.loads(report_path.read_text())
    report['candidateSha256'] = base.file_hash(directory / 'candidate-state.pt')
    report_path.write_text(json.dumps(report))
    seal_path = directory.parent / 'complete.json'
    seal = json.loads(seal_path.read_text())
    # Epoch is inferred from directory, never the possibly corrupted report.
    entry = seal['milestones'][str(int(directory.name.split('-')[1]))]
    entry['reportSha256'] = base.file_hash(report_path)
    entry['candidateSha256'] = report['candidateSha256']
    seal_path.write_text(json.dumps(seal))


@pytest.mark.parametrize('damage', ['artifact-bytes', 'snapshot', 'manifest-sha', 'frozen', 'epoch',
                                   'steps', 'config', 'threshold', 'head', 'rights', 'seal', 'failed'])
def test_artifact_validation_before_architecture_even_if_outer_hashes_updated(tmp_path, monkeypatch, damage):
    output, _, sha = make_run(tmp_path, monkeypatch)
    directory = output / 'epoch-003'
    if damage == 'artifact-bytes':
        (directory / 'candidate-state.pt').write_bytes(b'changed')
    elif damage == 'snapshot':
        (directory / 'source/community_x3d_experiments.py').write_bytes(b'changed')
    elif damage == 'manifest-sha': sha = '0' * 64
    elif damage == 'seal': (output / 'complete.json').unlink()
    elif damage == 'failed': (output / 'failed.json').write_text('{}')
    else:
        artifact = torch.load(directory / 'candidate-state.pt', weights_only=True, map_location='cpu')
        report = json.loads((directory / 'report.json').read_text())
        if damage == 'frozen': artifact['model_state']['blocks.0.bn.running_mean'][0] += 1
        if damage == 'epoch': artifact['training']['exportEpoch'] = report['training']['exportEpoch'] = 10
        if damage == 'steps': artifact['training']['optimizerSteps'] = report['training']['optimizerSteps'] = 99
        if damage == 'config': artifact['config']['max_epochs'] = report['config']['max_epochs'] = 10
        if damage == 'threshold': artifact['threshold'] = report['threshold'] = .4
        if damage == 'rights': artifact['rights'] = report['rights'] = {}
        if damage == 'head': artifact['model_state'][base.HEAD_KEYS[0]] = torch.zeros(2, 3)
        torch.save(artifact, directory / 'candidate-state.pt')
        (directory / 'report.json').write_text(json.dumps(report))
        reseal(directory)
    with pytest.raises((ValueError, OSError)):
        experiment.load_candidate(directory, manifest_sha256=sha,
                                   model_factory=lambda: pytest.fail('invalid artifact constructed model'))


def test_failed_later_epoch_retains_evidence_but_cannot_load_earlier_milestone(tmp_path, monkeypatch):
    manifest, checkpoint, evidence, _ = inputs(tmp_path, monkeypatch)
    output = tmp_path / 'failed-run'
    calls = []

    def fail_reader(entry):
        calls.append(entry)
        if len(calls) > 9:  # finish epoch three, fail epoch four
            raise RuntimeError('synthetic decode failure')
        return reader(entry)

    with pytest.raises(RuntimeError, match='synthetic decode'):
        experiment.run(manifest, tmp_path, checkpoint, output, manifest_sha256=base.file_hash(manifest),
                        config=settings(10), source_evidence=evidence, model_factory=lambda _: Model(),
                        reader=fail_reader, preprocess=identity)
    assert (output / 'epoch-003/report.json').exists() and (output / 'failed.json').exists()
    assert not (output / 'complete.json').exists()
    with pytest.raises(OSError):
        experiment.validate_artifact(output / 'epoch-003', manifest_sha256=base.file_hash(manifest))
    with pytest.raises(FileExistsError):
        experiment.run(manifest, tmp_path, checkpoint, output, manifest_sha256=base.file_hash(manifest))


def test_all_milestones_required_not_just_selected_one(tmp_path, monkeypatch):
    output, _, sha = make_run(tmp_path, monkeypatch, 10)
    (output / 'epoch-010/candidate-state.pt').unlink()
    with pytest.raises(OSError):
        experiment.validate_artifact(output / 'epoch-003', manifest_sha256=sha)


def test_guard_failure_precedes_model_and_new_output(tmp_path, monkeypatch):
    manifest, checkpoint, evidence, _ = inputs(tmp_path, monkeypatch)
    output = tmp_path / 'never'
    with pytest.raises(RuntimeError, match='busy'):
        experiment.run(manifest, tmp_path, checkpoint, output, manifest_sha256=base.file_hash(manifest),
                        config=replace(settings(), yield_to_demo=True), source_evidence=evidence,
                        yield_guard=lambda: (_ for _ in ()).throw(RuntimeError('busy')),
                        model_factory=lambda _: pytest.fail('busy demo constructed model'))
    assert not output.exists()


def test_first_forward_is_unchanged_and_frozen_mutation_fails():
    model = Model().eval()
    expected = model(reader(window(0))).detach().clone()
    calls = []

    def observe(entry):
        if not calls:
            torch.testing.assert_close(model(reader(window(0))).detach(), expected, atol=0, rtol=0)
            assert not any(module.training for module in model.modules())
        calls.append(entry)
        return reader(entry)

    experiment.fit(model, [window(0), window(1)], settings(), reader=observe, preprocess=identity)
    assert len(calls) == 6

    def corrupt(entry):
        with torch.no_grad():
            model.blocks[0].bn.running_mean.add_(1)
        return reader(entry)

    with pytest.raises(ValueError, match='Non-head'):
        experiment.fit(model, [window(0), window(1)], settings(), reader=corrupt, preprocess=identity)


def test_loader_is_restricted_cpu_and_invalid_device_never_constructs(tmp_path, monkeypatch):
    output, _, sha = make_run(tmp_path, monkeypatch)
    real_load = torch.load
    calls = []

    def tracked_load(path, **kwargs):
        calls.append(kwargs)
        return real_load(path, **kwargs)

    monkeypatch.setattr(torch, 'load', tracked_load)
    experiment.load_candidate(output / 'epoch-003', manifest_sha256=sha, model_factory=Model)
    assert calls == [{'weights_only': True, 'map_location': 'cpu'}]
    with pytest.raises(ValueError):
        experiment.load_candidate(output / 'epoch-003', manifest_sha256=sha, device='auto',
                                   model_factory=lambda: pytest.fail('invalid device constructed model'))


def test_v2_cache_remains_bounded_decoded_inputs_only(tmp_path, monkeypatch):
    manifest, checkpoint, evidence, _ = inputs(tmp_path, monkeypatch)
    calls = []

    def images(entry):
        calls.append(entry.recording_id)
        return [np.full((2, 4, 3), entry.label * 100, np.uint8)] * 8

    seal = experiment.run(manifest, tmp_path, checkpoint, tmp_path / 'cache-run',
                           manifest_sha256=base.file_hash(manifest),
                           config=replace(settings(10), input_cache_mib=1), source_evidence=evidence,
                           model_factory=lambda _: Model(), reader=images)
    assert len(calls) == 3
    assert seal['inputCache']['misses'] == 3 and seal['inputCache']['hits'] == 27
    assert seal['inputCache']['residentMiB'] <= 1


def test_cli_requires_manifest_pin_and_rejects_cuda_without_guard(tmp_path, capsys):
    import train_community_experiments as cli
    with pytest.raises(SystemExit):
        cli.main(['--manifest', 'fixture', '--device', 'cpu', '--output-dir', str(tmp_path), '--max-epochs', '3'])
    assert cli.main(['--manifest', 'fixture', '--manifest-sha256', 'a' * 64, '--device', 'cuda',
                     '--no-yield-to-demo', '--output-dir', str(tmp_path), '--max-epochs', '3']) == 1
    assert 'DemoYieldGuard' in capsys.readouterr().err


def test_runtime_versions_and_dependency_sources_are_observed_without_cuda_probe(monkeypatch):
    import platform
    from importlib.metadata import version
    for name in ('init', 'is_available', 'is_initialized', 'get_device_name', 'device_count'):
        monkeypatch.setattr(torch.cuda, name, lambda *_a, **_k: pytest.fail('Runtime metadata probed a GPU'))
    runtime, snapshots = experiment.runtime_snapshots()
    assert runtime['python']['version'] == platform.python_version()
    assert runtime['torch']['version'] == str(torch.__version__)
    assert runtime['torch']['compiledCuda'] == torch.version.cuda
    assert runtime['torch']['linkedCudnn'] == torch.backends.cudnn.version()
    assert runtime['torch']['cudaDeviceOrDriverProbed'] is False
    assert runtime['packages']['pytorchvideo'] == version('pytorchvideo')
    assert runtime['pytorchvideo'] == version('pytorchvideo')
    assert runtime['numpy'] == np.__version__
    assert experiment.REQUIRED_DEPENDENCIES.issubset(snapshots)
    for name, data in snapshots.items():
        assert isinstance(data, bytes)
        if name.startswith('dependencies/'):
            assert runtime['dependencySnapshots'][name] == experiment.hashlib.sha256(data).hexdigest()
    assert json.loads(snapshots['runtime/environment.json']) == runtime


def test_runtime_parity_in_started_artifact_report_and_seal(tmp_path, monkeypatch):
    root, seal, sha = make_run(tmp_path, monkeypatch)
    report, artifact = experiment.validate_artifact(root / 'epoch-003', manifest_sha256=sha)
    started = json.loads((root / 'started.json').read_text())
    runtime = seal['runtime']
    assert report['runtime'] == artifact['runtime'] == started['runtime'] == runtime
    assert seal['startedSha256'] == base.file_hash(root / 'started.json')
    for directory in (root, root / 'epoch-003'):
        assert json.loads((directory / 'runtime/environment.json').read_text()) == runtime
        for name, digest in runtime['dependencySnapshots'].items():
            assert base.file_hash(directory / name) == digest


@pytest.mark.parametrize('damage', ['started', 'seal-runtime', 'report-runtime', 'artifact-runtime',
                                   'environment-bytes', 'root-environment-bytes', 'dependency-bytes',
                                   'missing-requirements', 'missing-lock', 'missing-builder'])
def test_runtime_corruption_fails_before_architecture(tmp_path, monkeypatch, damage):
    root, _, sha = make_run(tmp_path, monkeypatch)
    directory = root / 'epoch-003'
    if damage == 'started':
        path = root / 'started.json'
        value = json.loads(path.read_text())
        value['runtime']['numpy'] = 'changed'
        path.write_text(json.dumps(value))
    elif damage == 'seal-runtime':
        path = root / 'complete.json'
        value = json.loads(path.read_text())
        value['runtime']['numpy'] = 'changed'
        path.write_text(json.dumps(value))
    elif damage == 'report-runtime':
        path = directory / 'report.json'
        value = json.loads(path.read_text())
        value['runtime']['numpy'] = 'changed'
        path.write_text(json.dumps(value))
        reseal(directory)
    elif damage == 'artifact-runtime':
        path = directory / 'candidate-state.pt'
        value = torch.load(path, weights_only=True, map_location='cpu')
        value['runtime']['numpy'] = 'changed'
        torch.save(value, path)
        reseal(directory)
    elif damage == 'environment-bytes': (directory / 'runtime/environment.json').write_bytes(b'changed')
    elif damage == 'root-environment-bytes': (root / 'runtime/environment.json').write_bytes(b'changed')
    elif damage == 'dependency-bytes':
        (directory / 'dependencies/installed/pytorchvideo/models/x3d.py').write_bytes(b'changed')
    else:
        name = {'missing-requirements': 'dependencies/manifests/service/requirements.txt',
                'missing-lock': 'dependencies/manifests/service/requirements-lock.txt',
                'missing-builder': 'dependencies/installed/pytorchvideo/models/x3d.py'}[damage]
        (directory / name).unlink()
    with pytest.raises((ValueError, OSError)):
        experiment.load_candidate(directory, manifest_sha256=sha,
                                   model_factory=lambda: pytest.fail('Bad runtime constructed architecture'))


def rewrite_runtime_bundle(root, mutate):
    """Re-sign inert test envelopes so validators must inspect inner requirements."""
    directory = root / 'epoch-003'
    seal = json.loads((root / 'complete.json').read_text())
    started = json.loads((root / 'started.json').read_text())
    report = json.loads((directory / 'report.json').read_text())
    artifact = torch.load(directory / 'candidate-state.pt', weights_only=True, map_location='cpu')
    runtime, hashes = deepcopy(seal['runtime']), deepcopy(report['snapshotHashes'])
    mutate(runtime, hashes)
    data = (json.dumps(runtime) + '\n').encode()
    for container in (root, directory):
        (container / 'runtime/environment.json').write_bytes(data)
    hashes['runtime/environment.json'] = experiment.hashlib.sha256(data).hexdigest()
    for value in (seal, started, report, artifact):
        value['runtime'] = runtime
    for value in (started, report, artifact):
        value['snapshotHashes'] = hashes
    (root / 'started.json').write_text(json.dumps(started))
    seal['startedSha256'] = base.file_hash(root / 'started.json')
    (root / 'complete.json').write_text(json.dumps(seal))
    torch.save(artifact, directory / 'candidate-state.pt')
    (directory / 'report.json').write_text(json.dumps(report))
    reseal(directory)


@pytest.mark.parametrize('missing', ['dependencies/manifests/service/requirements.txt',
                                    'dependencies/manifests/service/requirements-lock.txt',
                                    'dependencies/installed/pytorchvideo/models/x3d.py',
                                    'dependencies/installed/fvcore/nn/squeeze_excitation.py',
                                    'dependencies/installed/torch/optim/adamw.py'])
def test_required_dependency_snapshot_cannot_be_dropped_from_resigned_inventory(tmp_path, monkeypatch, missing):
    root, _, sha = make_run(tmp_path, monkeypatch)

    def mutate(runtime, hashes):
        runtime['dependencySnapshots'].pop(missing)
        hashes.pop(missing)

    rewrite_runtime_bundle(root, mutate)
    with pytest.raises(ValueError, match='required runtime dependency'):
        experiment.load_candidate(root / 'epoch-003', manifest_sha256=sha,
                                   model_factory=lambda: pytest.fail('Missing runtime snapshots accepted'))


@pytest.mark.parametrize('damage', ['package-version', 'installed-source'])
def test_local_dependency_drift_rejected_before_model_construction(tmp_path, monkeypatch, damage):
    from types import SimpleNamespace
    root, _, sha = make_run(tmp_path, monkeypatch)
    original_distribution = experiment.distribution
    changed = tmp_path / 'changed-builder.py'
    changed.write_bytes(b'synthetic changed installed source; never executed')

    def installed(name):
        value = original_distribution(name)
        if name != 'pytorchvideo':
            return value
        return SimpleNamespace(version='changed' if damage == 'package-version' else value.version,
                               locate_file=lambda path: changed if str(path).endswith('models/x3d.py') else value.locate_file(path))

    monkeypatch.setattr(experiment, 'distribution', installed)
    with pytest.raises(ValueError, match='Installed dependency'):
        experiment.load_candidate(root / 'epoch-003', manifest_sha256=sha,
                                   model_factory=lambda: pytest.fail('Changed local dependency constructed model'))


def test_runtime_metadata_rejects_nonprimitive_values_and_missing_inventory(tmp_path, monkeypatch):
    root, seal, _ = make_run(tmp_path, monkeypatch)
    report = json.loads((root / 'epoch-003/report.json').read_text())
    runtime = deepcopy(seal['runtime'])
    runtime['custom'] = torch.ones(1)
    with pytest.raises(ValueError, match='safe JSON primitives'):
        experiment.validate_runtime(runtime, report['snapshotHashes'], root)
    runtime = deepcopy(seal['runtime'])
    runtime.pop('packages')
    with pytest.raises(ValueError, match='package version inventory'):
        experiment.validate_runtime(runtime, report['snapshotHashes'], root)
