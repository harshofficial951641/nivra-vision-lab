from dataclasses import replace
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

import benchmark_cctv_candidates as benchmark


class Capture:
    def __init__(self, times, dimensions=None):
        self.times = times
        self.dimensions = dimensions or [(80, 60)] * len(times)
        self.position = 0
        self.released = False

    def isOpened(self):
        return True

    def read(self):
        if self.position >= len(self.times):
            return False, None
        width, height = self.dimensions[self.position]
        self.position += 1
        return True, np.full((height, width, 3), [10, 20, 30], dtype=np.uint8)

    def get(self, property_id):
        if property_id == cv2.CAP_PROP_FPS:
            return 30000  # Deliberately malformed nominal WebM FPS; PTS are valid.
        return self.times[self.position - 1]

    def release(self):
        self.released = True


def clip(**extra):
    return {'id': 'clip', 'path': 'clip.avi', **extra}


def packet(end=3900., dimensions=(80, 60)):
    times = [float(value) for value in range(int(end - 3900), int(end) + 1, 100)]
    width, height = dimensions
    frames = [np.full((height, width, 3), 17, np.uint8)] * len(times)
    return benchmark.Window(times, frames, dimensions, dimensions, (0, 0, width, height))


class Runtime:
    calls = []

    def __init__(self, device, fraction):
        self.device = device
        self.calls.append(('runtime', device, fraction))

    def sync(self):
        self.calls.append(('sync',))

    def snapshot(self, phase):
        return {'phase': phase, 'timestampUtc': 'synthetic-time', 'stub': True}

    def metadata(self):
        return {'device': self.device, 'stub': True}


class Candidate:
    def __init__(self, name, *, score=.8):
        self.name, self.score, self.calls = name, score, []

    def metadata(self):
        return {'source': 'synthetic-fixture', 'preprocess': {'frames': 16}}

    def predict(self, frames):
        self.calls.append([frame.shape for frame in frames])
        index = 0 if self.name == 'mc3' else 1
        values = [1 - self.score, self.score] if index else [self.score, 1 - self.score]
        return {'fightScore': self.score, 'classScores': values, 'scoreKind': 'softmax', 'fightIndex': index}


def inputs(tmp_path, monkeypatch, count=2):
    records = []
    for index in range(count):
        path = tmp_path / f'clip-{index}.avi'
        path.write_bytes(f'synthetic media {index}'.encode())
        records.append({'id': f'clip-{index}', 'path': path.name,
                        'sha256': benchmark.digest(path), 'sourceGroup': f'group-{index}',
                        'annotationStatus': 'reviewed', 'split': 'holdout', 'license': 'synthetic-fixture',
                        'durationMs': 9000, 'events': [{'startMs': 3000, 'endMs': 4100, 'label': 'contact'}]})
    corpus = tmp_path / 'corpus.json'
    corpus.write_text(json.dumps(records), encoding='utf-8')
    checkpoint = tmp_path / 'control.pth'
    checkpoint.write_bytes(b'pinned synthetic state, not a model')
    asset = {'path': checkpoint, 'sha256': benchmark.digest(checkpoint), 'source': 'synthetic'}
    monkeypatch.setattr(benchmark, 'CONTROL_ASSETS', {'x3d': asset, 'mc3': asset})
    return corpus, checkpoint, records


def test_native_crop_coordinates_pts_and_uniform_selected_indices():
    capture = Capture(list(range(0, 4801, 100)))
    stats = {}
    rows = list(benchmark.windows(clip(crop=[.25, .1, .9, .8]), Path('corpus.json'), stats=stats,
                                  capture_factory=lambda _: capture))
    assert len(rows) == 3
    assert rows[0].source_dimensions == (80, 60)
    assert rows[0].view_dimensions == (52, 42)
    assert rows[0].crop_pixels == (20, 6, 72, 48)
    assert rows[0].frames[0].shape == (42, 52, 3)  # No old 224-square buffer.
    assert rows[0].timestamps == list(range(0, 3801, 100))
    assert [row.end for row in rows] == [3800, 4200, 4600]
    assert rows[-1].start == 600
    assert stats['nominalFps'] == 30000 and stats['nominalFpsUsedForClock'] is False
    assert stats['peakBufferedPixels'] <= 41 * 52 * 42
    assert capture.released


def test_source_gap_and_dimension_reset_cannot_bridge_missing_context():
    times = list(range(0, 3901, 100)) + list(range(5301, 9302, 100))
    dimensions = [(80, 60)] * 40 + [(90, 70)] * (len(times) - 40)
    capture = Capture(times, dimensions)
    stats = {}
    rows = list(benchmark.windows(clip(), Path('corpus.json'), stats=stats, capture_factory=lambda _: capture))
    assert [row.end for row in rows] == [3800, 9101]
    assert rows[-1].start == 5301
    assert stats['exclusions']['source-gap-reset'] == 1
    assert stats['exclusions']['dimension-reset'] == 1
    assert rows[-1].view_dimensions == (90, 70)
    assert capture.released


@pytest.mark.parametrize('times', [[0, 0, 33], [0, float('nan')], [10, 9], [-1, 0], [0, float('inf')]])
def test_strict_decoded_pts_fail_and_release(times):
    capture = Capture(times)
    with pytest.raises(ValueError, match='timestamp'):
        list(benchmark.windows(clip(), Path('corpus.json'), capture_factory=lambda _: capture))
    assert capture.released


@pytest.mark.parametrize('times', [[], list(range(0, 3701, 100)), [0, 600, 1200, 1800, 2400, 3000, 3800]])
def test_short_or_underobserved_clip_has_explicit_exclusion(times):
    stats = {}
    assert list(benchmark.windows(clip(), Path('corpus.json'), stats=stats,
                                  capture_factory=lambda _: Capture(times))) == []
    assert stats['exclusions']['no-eligible-window'] == 1


@pytest.mark.parametrize('overrides,match', [
    ({'max_source_pixels': 4000}, 'source dimensions'),
    ({'max_buffer_pixels': 20_000}, 'buffer'),
    ({'max_decode_frames': 3}, 'frame budget'),
    ({'max_windows': 1}, 'Window budget'),
])
def test_bounds_fail_without_shrinking_or_sampling_away_data(overrides, match):
    capture = Capture(list(range(0, 4801, 100)))
    with pytest.raises(ValueError, match=match):
        list(benchmark.windows(clip(), Path('corpus.json'), limits=replace(benchmark.Limits(), **overrides),
                                capture_factory=lambda _: capture))
    assert capture.released


def test_limits_accept_native_1080p_and_reject_invalid_or_unbounded_settings():
    assert benchmark.Limits().max_source_pixels >= 1920 * 1080
    for overrides in ({'max_windows': True}, {'max_source_pixels': 0}, {'max_windows': 10_001},
                      {'max_source_pixels': 3840 * 2160 + 1}, {'max_buffer_pixels': 200_000_001}):
        with pytest.raises(ValueError):
            replace(benchmark.Limits(), **overrides).validate()


@pytest.mark.parametrize('dimensions', [(1920, 1080), (720, 1280), (1080, 1920)])
def test_real_native_portrait_and_landscape_geometry_without_large_allocation(dimensions):
    width, height = dimensions
    # Zero-stride view has actual native shape but only a one-byte backing value.
    frame = np.broadcast_to(np.uint8(0), (height, width, 3))
    assert benchmark._frame(frame, benchmark.Limits()) == dimensions


@pytest.mark.parametrize('name', ['x3d', 'mc3', 'videomae'])
def test_full_stub_run_pairs_windows_warms_once_and_writes_only_complete(tmp_path, monkeypatch, name):
    corpus, _, records = inputs(tmp_path, monkeypatch)
    if name == 'videomae':
        snapshot = tmp_path / 'snapshot'
        snapshot.mkdir()
        pins = {}
        for filename in benchmark.VIDEOMAE_FILES:
            path = snapshot / filename
            path.write_bytes(filename.encode())
            pins[filename] = benchmark.digest(path)
        monkeypatch.setattr(benchmark, 'VIDEOMAE_FILES', pins)
    else:
        snapshot = None
    output = tmp_path / 'new-output' / 'report.json'
    model = Candidate(name, score=.5)
    seen = []
    Runtime.calls = []

    def factory(selected, assets, *, device):
        assert not output.exists() and not output.parent.exists()
        assert Runtime.calls[0] == ('runtime', 'cpu', .35)
        seen.append(('load', selected, device))
        return model

    def reader(entry, _corpus, *, limits, stats):
        assert not output.exists() and not output.parent.exists()
        stats['synthetic'] = True
        yield packet()

    report = benchmark.run(name, corpus, output, snapshot=snapshot, model_factory=factory,
                           window_reader=reader, runtime_factory=Runtime,
                           yield_guard=lambda: seen.append(('guard',)))
    assert seen[0] == ('guard',) and ('load', name, 'cpu') in seen
    assert len([item for item in seen if item == ('guard',)]) >= 2 + 3 + 2
    assert len(model.calls) == 5  # three warmups + two scored windows
    assert all(shapes == [(60, 80, 3)] * 16 for shapes in model.calls)
    assert report['windowCount'] == 2 and report['complete'] is True
    assert report['status'] == 'complete-diagnostic-only'
    assert report['policy']['threshold'] == .5
    assert report['clips']['clip-0']['reviewWindows'] == 0  # Strict tie rule.
    row = report['clips']['clip-0']['samples'][0]
    assert len(row['selectedFramePTS']) == 16 and row['selectedFramePTS'][0] == 0
    assert row['selectedFramePTS'][-1] == 3900
    assert row['labelledEventOverlaps'][0]['overlapMs'] == 900
    assert row['sourceGroup'] == records[0]['sourceGroup']
    assert len(report['pairedWindowSha256']) == 64 and 'accuracy' not in report['clips']['clip-0']
    assert [entry['phase'] for entry in report['memorySnapshots']] == ['after-load', 'after-three-warmups', 'complete']
    assert report['liveModelChanged'] is False and report['thresholdFittedHere'] is False
    assert json.loads(output.read_text(encoding='utf-8')) == report
    assert benchmark.main(['--candidate', name, '--device', 'cpu', '--corpus', str(corpus),
                           '--output', str(output)]) == 1


def test_quality_derivative_keeps_source_group_and_is_not_an_original(tmp_path, monkeypatch):
    corpus, _, records = inputs(tmp_path, monkeypatch)
    records[0]['qualityVariant'] = {'kind': 'original-reference', 'independentEvidence': False}
    records[1]['sourceGroup'] = records[0]['sourceGroup']
    records[1]['qualityVariant'] = {'kind': 'synthetic-resolution-compression',
                                    'parentSha256': records[0]['sha256'],
                                    'independentEvidence': False}
    corpus.write_text(json.dumps(records), encoding='utf-8')

    def reader(*args, **kwargs):
        yield packet()

    report = benchmark.run('x3d', corpus, tmp_path / 'variants.json',
                           model_factory=lambda name, assets, device: Candidate(name),
                           window_reader=reader, runtime_factory=Runtime, yield_guard=lambda: None)
    original, derived = report['clips']['clip-0'], report['clips']['clip-1']
    assert original['derivative'] is False
    assert derived['derivative'] is True
    assert derived['sourceGroup'] == original['sourceGroup']
    assert derived['qualityVariant'] == records[1]['qualityVariant']


def test_paired_identity_is_independent_of_model_scores(tmp_path, monkeypatch):
    corpus, _, _ = inputs(tmp_path, monkeypatch, count=1)
    reports = []
    for name, score in [('x3d', .8), ('mc3', .2)]:
        reports.append(benchmark.run(name, corpus, tmp_path / f'{name}.json', yield_to_demo=False,
                                     runtime_factory=Runtime,
                                     model_factory=lambda selected, assets, *, device: Candidate(selected, score=score),
                                     window_reader=lambda *_args, **_kwargs: iter([packet()])))
    assert reports[0]['pairedWindowSha256'] == reports[1]['pairedWindowSha256']
    assert reports[0]['clips']['clip-0']['reviewWindows'] == 1
    assert reports[1]['clips']['clip-0']['reviewWindows'] == 0


@pytest.mark.parametrize('corruption', ['media', 'model', 'review', 'crop', 'event', 'split-leak'])
def test_all_inputs_validated_before_factory_decoder_or_runtime(tmp_path, monkeypatch, corruption):
    corpus, checkpoint, records = inputs(tmp_path, monkeypatch)
    if corruption == 'media':
        (tmp_path / records[-1]['path']).write_bytes(b'changed last clip')
    elif corruption == 'model':
        checkpoint.write_bytes(b'changed weights')
    elif corruption == 'review':
        records[-1]['annotationStatus'] = 'pending'
    elif corruption == 'crop':
        records[-1]['crop'] = [0, 0, 2, 1]
    elif corruption == 'event':
        records[-1]['events'][0]['endMs'] = float('nan')
    elif corruption == 'split-leak':
        records[-1]['split'] = 'calibration'
        records[-1]['sourceGroup'] = records[0]['sourceGroup']
    corpus.write_text(json.dumps(records))
    output = tmp_path / 'never-created' / 'result.json'

    def forbidden(*_args, **_kwargs):
        pytest.fail('Corrupt input reached model/runtime/decoder')

    with pytest.raises(ValueError):
        benchmark.run('x3d', corpus, output, model_factory=forbidden, runtime_factory=forbidden,
                       window_reader=forbidden, yield_to_demo=False)
    assert not output.exists() and not output.parent.exists()


def test_snapshot_all_files_validated_before_videomae_factory(tmp_path, monkeypatch):
    corpus, _, _ = inputs(tmp_path, monkeypatch)
    snapshot = tmp_path / 'snapshot'
    snapshot.mkdir()
    pins = {}
    for filename in benchmark.VIDEOMAE_FILES:
        path = snapshot / filename
        path.write_bytes(filename.encode())
        pins[filename] = benchmark.digest(path)
    monkeypatch.setattr(benchmark, 'VIDEOMAE_FILES', pins)
    (snapshot / 'preprocessor_config.json').write_text('changed')
    with pytest.raises(ValueError, match='preprocessor_config'):
        benchmark.run('videomae', corpus, tmp_path / 'output.json', snapshot=snapshot,
                       model_factory=lambda *_a, **_k: pytest.fail('Invalid snapshot loaded'), yield_to_demo=False)
    assert not (tmp_path / 'output.json').exists()


def test_real_videomae_interface_with_processor_and_forward_stubs(tmp_path, monkeypatch):
    import torch
    from types import SimpleNamespace
    from nivra import videomae_candidate as adapter
    corpus, _, _ = inputs(tmp_path, monkeypatch, count=1)
    snapshot = tmp_path / 'snapshot'
    snapshot.mkdir()
    pins = {}
    for name in benchmark.VIDEOMAE_FILES:
        path = snapshot / name
        path.write_bytes(name.encode())
        pins[name] = benchmark.digest(path)
    monkeypatch.setattr(benchmark, 'VIDEOMAE_FILES', pins)
    candidate = adapter.VideoMAECandidate.__new__(adapter.VideoMAECandidate)
    candidate.device = 'cpu'
    shapes = []

    def processor(frames, **kwargs):
        shapes.extend(frame.shape for frame in frames)
        assert frames[0][0, 0].tolist() == [30, 20, 10]  # Real adapter's BGR->RGB.
        return {'pixel_values': torch.zeros(1).expand(1, 16, 3, 224, 224)}

    candidate.processor = processor
    candidate.model = lambda **kwargs: SimpleNamespace(logits=torch.tensor([[0., 2.]]))
    arguments = []

    def constructor(snapshot, *, device):
        arguments.append((str(snapshot), device))
        return candidate

    monkeypatch.setattr(adapter, 'VideoMAECandidate', constructor)
    window = packet(dimensions=(34, 52))
    window.frames = [np.full((52, 34, 3), [10, 20, 30], np.uint8)] * len(window.frames)
    report = benchmark.run('videomae', corpus, tmp_path / 'paired.json', snapshot=snapshot,
                           yield_to_demo=False, runtime_factory=Runtime,
                           window_reader=lambda *_a, **_k: iter([window]))
    assert arguments == [(str(snapshot.resolve()), 'cpu')]
    assert shapes == [(52, 34, 3)] * 16 * 4
    row = report['clips']['clip-0']['samples'][0]
    assert row['fightScore'] == pytest.approx(.880797, abs=1e-6)
    assert report['adapter']['revision'] == adapter.REVISION
    assert row['scoreKind'] == 'softmax-on-logits' and row['fightIndex'] == 1


def test_late_failure_budget_and_output_race_leave_no_success_report(tmp_path, monkeypatch):
    corpus, _, _ = inputs(tmp_path, monkeypatch)
    output = tmp_path / 'never' / 'result.json'

    def late_reader(entry, *_args, **_kwargs):
        if entry['id'] == 'clip-1':
            raise ValueError('late decode failure')
        yield packet()

    with pytest.raises(ValueError, match='late decode'):
        benchmark.run('x3d', corpus, output, yield_to_demo=False, runtime_factory=Runtime,
                       model_factory=lambda *_a, **_k: Candidate('x3d'), window_reader=late_reader)
    assert not output.parent.exists()
    with pytest.raises(ValueError, match='window budget'):
        benchmark.run('x3d', corpus, output, yield_to_demo=False, runtime_factory=Runtime,
                       limits=replace(benchmark.Limits(), max_windows=1),
                       model_factory=lambda *_a, **_k: Candidate('x3d'),
                       window_reader=lambda *_a, **_k: iter([packet()]))
    assert not output.parent.exists()
    output.parent.mkdir()
    output.write_text('existing user report')
    with pytest.raises(FileExistsError):
        benchmark.run('x3d', corpus, output, model_factory=lambda *_a, **_k: pytest.fail('overwrite'))
    assert output.read_text() == 'existing user report'


def test_guard_failure_before_loading_has_no_output(tmp_path, monkeypatch):
    corpus, _, _ = inputs(tmp_path, monkeypatch)

    def guard():
        raise RuntimeError('demo busy')

    with pytest.raises(RuntimeError, match='demo busy'):
        benchmark.run('x3d', corpus, tmp_path / 'output.json', yield_guard=guard,
                       model_factory=lambda *_a, **_k: pytest.fail('demo busy but model loaded'))
    assert not (tmp_path / 'output.json').exists()


@pytest.mark.parametrize('invalid', [
    {'fightIndex': 0}, {'fightScore': .9}, {'classScores': [.8, .8]},
    {'classScores': [float('nan'), .8]}, {'fightScore': float('inf')}, {'scoreKind': ''},
])
def test_prediction_rejects_wrong_class_activation_and_nonfinite_outputs(invalid):
    value = {'fightIndex': 1, 'fightScore': .8, 'classScores': [.2, .8], 'scoreKind': 'softmax'}
    value.update(invalid)
    with pytest.raises(ValueError):
        benchmark._prediction(value, 1)


@pytest.mark.parametrize('name', ['x3d', 'mc3'])
def test_independent_control_cpu_preprocess_and_activation_mapping(tmp_path, monkeypatch, name):
    import torch
    corpus, checkpoint, _ = inputs(tmp_path, monkeypatch)
    calls = []

    class Model:
        def load_state_dict(self, state, *, strict):
            assert strict and state == {'fixture': True}

        def eval(self):
            return self

        def float(self):
            return self

        def requires_grad_(self, value):
            assert value is False
            return self

        def to(self, device):
            calls.append(device)
            return self

        def __call__(self, tensor):
            assert tensor.device.type == 'cpu'
            assert tensor.shape == (1, 3, 16, 224, 224) if name == 'x3d' else tensor.shape == (1, 3, 16, 112, 112)
            if name == 'x3d':
                expected = (torch.tensor([30., 20., 10.]) / 255 - .45) / .225
                torch.testing.assert_close(tensor[0, :, 0, 0, 0], expected)
                return torch.tensor([[.2, .8]])  # Already Softmax; must remain .8.
            return torch.tensor([[2., 0.]])  # Logits, fight is index zero.

    monkeypatch.setattr(benchmark, '_construct_control', lambda _: Model())
    monkeypatch.setattr(benchmark, '_load_control_state', lambda *_args: {'fixture': True})
    monkeypatch.setattr(torch.cuda, 'is_available', lambda: pytest.fail('CPU control probed CUDA'))
    candidate = benchmark.ControlCandidate(name, benchmark.CONTROL_ASSETS[name], device='cpu')
    result = candidate.predict([np.full((50, 90, 3), [10, 20, 30], np.uint8)] * 16)
    assert result['fightScore'] == pytest.approx(.8 if name == 'x3d' else .880797, abs=1e-6)
    assert result['fightIndex'] == (1 if name == 'x3d' else 0)
    assert calls == ['cpu']


def test_control_loaders_are_cpu_weights_only_and_strip_known_prefix(tmp_path, monkeypatch):
    import torch
    calls = []

    def loader(path, **kwargs):
        calls.append(kwargs)
        return {'model': {'backbone.head.weight': 'synthetic'}}

    monkeypatch.setattr(torch, 'load', loader)
    assert benchmark._load_control_state('x3d', tmp_path / 'fixture') == {'head.weight': 'synthetic'}
    benchmark._load_control_state('mc3', tmp_path / 'fixture')
    assert calls == [{'map_location': 'cpu', 'weights_only': True}] * 2


def test_runtime_cpu_does_not_probe_cuda_and_cuda_cap_precedes_load(monkeypatch):
    import torch
    monkeypatch.setattr(torch.cuda, 'is_available', lambda: pytest.fail('CPU runtime touched CUDA'))
    runtime = benchmark.TorchRuntime('cpu', .35)
    runtime.sync()
    assert runtime.metadata()['device'] == 'cpu'
    assert 'peakAllocatedBytes' not in runtime.snapshot('cpu')
    calls = []
    monkeypatch.setattr(torch.cuda, 'is_available', lambda: True)
    monkeypatch.setattr(torch.cuda, 'set_per_process_memory_fraction', lambda fraction: calls.append(('cap', fraction)))
    monkeypatch.setattr(torch.cuda, 'reset_peak_memory_stats', lambda: calls.append(('reset',)))
    benchmark.TorchRuntime('cuda', .35)  # Mocked policy only; no CUDA allocations.
    assert calls == [('cap', .35), ('reset',)]
    monkeypatch.setattr(torch.cuda, 'is_available', lambda: False)
    with pytest.raises(RuntimeError, match='no CPU fallback'):
        benchmark.TorchRuntime('cuda', .35)


def test_cli_requires_device_and_rejects_invalid_cuda_policy_without_loading(tmp_path):
    with pytest.raises(SystemExit):
        benchmark.main(['--candidate', 'x3d', '--output', str(tmp_path / 'out.json')])
    assert benchmark.main(['--candidate', 'x3d', '--device', 'cuda', '--no-yield-to-demo',
                           '--output', str(tmp_path / 'out.json')]) == 1
    for fraction in (0, float('nan'), 1.1):
        with pytest.raises(ValueError, match='fraction'):
            benchmark.run('x3d', tmp_path / 'missing.json', tmp_path / 'out.json', cuda_memory_fraction=fraction)


def community_run(tmp_path, monkeypatch):
    from nivra import community_x3d_training as adaptation
    from test_community_x3d_training import inputs as training_inputs, Model, settings, reader, identity
    tmp_path.mkdir()
    monkeypatch.setattr(adaptation, 'HEAD_FEATURES', 4)
    manifest, checkpoint, evidence, _ = training_inputs(tmp_path, monkeypatch)
    output = tmp_path / 'adaptation'
    report = adaptation.run(manifest, tmp_path, checkpoint, output, config=settings(),
                            source_evidence=evidence, model_factory=lambda _: Model(),
                            reader=reader, preprocess=identity)
    return adaptation, output, report, Model


def test_community_candidate_integrates_safe_state_and_preserves_source_pairing(tmp_path, monkeypatch):
    adaptation, adaptation_run, training_report, tiny_model = community_run(tmp_path / 'training', monkeypatch)
    diagnostic = tmp_path / 'diagnostic'
    diagnostic.mkdir()
    corpus, _, _ = inputs(diagnostic, monkeypatch, count=1)
    model, report = adaptation.load_candidate(adaptation_run, model_factory=tiny_model)
    adapter = adaptation.CommunityCandidate.__new__(adaptation.CommunityCandidate)
    adapter.model, adapter.report, adapter.device = model, report, 'cpu'
    constructor_calls = []

    def constructor(path, *, device):
        constructor_calls.append((str(path), device))
        return adapter

    monkeypatch.setattr(adaptation, 'CommunityCandidate', constructor)
    adapted = benchmark.run('community', corpus, tmp_path / 'community.json', adaptation_run=adaptation_run,
                             yield_to_demo=False, runtime_factory=Runtime,
                             window_reader=lambda *_a, **_k: iter([packet()]))
    baseline = benchmark.run('x3d', corpus, tmp_path / 'baseline.json',
                              yield_to_demo=False, runtime_factory=Runtime,
                              model_factory=lambda *_a, **_k: Candidate('x3d'),
                              window_reader=lambda *_a, **_k: iter([packet()]))
    assert constructor_calls == [(str(adaptation_run.resolve()), 'cpu')]
    for field in ('pairedWindowSha256', 'corpusSha256', 'policySha256'):
        assert adapted[field] == baseline[field]
    assert adapted['candidate'] == 'community' and baseline['candidate'] == 'x3d'
    assert adapted['trainedSourceHashes'] == training_report['snapshotHashes']
    assert adapted['adaptationIdentity']['adaptationSha256'] == training_report['candidateSha256']
    assert adapted['adaptationIdentity']['baselineSha256'] == adaptation.CHECKSUM
    assert adapted['adaptationIdentity']['adaptationSha256'] != adaptation.CHECKSUM
    assert adapted['adapter']['trainingManifestSha256'] == training_report['manifestSha256']
    assert adapted['clips']['clip-0']['samples'][0]['scoreKind'] == 'retained-backbone-softmax'
    assert 'adaptationIdentity' not in baseline and 'trainedSourceHashes' not in baseline


def test_community_report_is_validated_before_runtime_factory_or_decoder(tmp_path, monkeypatch):
    _, adaptation_run, _, _ = community_run(tmp_path / 'training', monkeypatch)
    diagnostic = tmp_path / 'diagnostic'
    diagnostic.mkdir()
    corpus, _, _ = inputs(diagnostic, monkeypatch, count=1)
    report_path = adaptation_run / 'report.json'
    report = json.loads(report_path.read_text())
    report['threshold'] = .4
    report_path.write_text(json.dumps(report))

    def forbidden(*_args, **_kwargs):
        pytest.fail('Invalid community state reached runtime/model/decoder')

    with pytest.raises(ValueError, match='contract mismatch'):
        benchmark.run('community', corpus, tmp_path / 'no-report.json', adaptation_run=adaptation_run,
                       yield_to_demo=False, runtime_factory=forbidden, model_factory=forbidden,
                       window_reader=forbidden)
    assert not (tmp_path / 'no-report.json').exists()


def test_community_cli_requires_adaptation_run_and_keeps_output_new(tmp_path, monkeypatch, capsys):
    corpus, _, _ = inputs(tmp_path, monkeypatch, count=1)
    output = tmp_path / 'result.json'
    assert benchmark.main(['--candidate', 'community', '--device', 'cpu', '--corpus', str(corpus),
                           '--output', str(output), '--no-yield-to-demo']) == 1
    assert '--adaptation-run' in capsys.readouterr().err
    assert not output.exists()
    output.write_text('preserve existing result')
    with pytest.raises(FileExistsError):
        benchmark.run('community', corpus, output)
    assert output.read_text() == 'preserve existing result'


def community_v2_run(tmp_path, monkeypatch, epochs=3):
    """Existing synthetic V2 complete artifacts; never actual model weights."""
    import torch
    from nivra import community_x3d_training as base
    from nivra import community_x3d_experiments as adaptation
    from test_community_x3d_experiments import make_run
    tmp_path.mkdir()
    monkeypatch.setattr(base, 'HEAD_FEATURES', 4)
    monkeypatch.setattr(torch.cuda, 'is_available', lambda: False)  # AdamW CPU query stub
    output, seal, sha = make_run(tmp_path, monkeypatch, epochs)
    return adaptation, output, seal, sha


def test_community_v2_milestones_have_distinct_identity_same_policy_and_source_windows(tmp_path, monkeypatch):
    import torch
    from test_community_x3d_training import Model
    adaptation, root, seal, sha = community_v2_run(tmp_path / 'training', monkeypatch, epochs=10)
    diagnostic = tmp_path / 'diagnostic'
    diagnostic.mkdir()
    corpus, _, records = inputs(diagnostic, monkeypatch, count=1)
    records[0]['qualityVariant'] = {'kind': 'synthetic-resolution-compression',
                                    'parentSha256': 'a' * 64, 'independentEvidence': False,
                                    'encoding': {'codec': 'synthetic', 'quality': 17}}
    corpus.write_text(json.dumps(records))
    constructors = []
    candidate_class = adaptation.ExperimentCandidate

    def constructor(path, *, manifest_sha256, device):
        constructors.append((str(path), manifest_sha256, device))
        model, report = adaptation.load_candidate(path, manifest_sha256=manifest_sha256,
                                                   device=device, model_factory=Model)
        candidate = candidate_class.__new__(candidate_class)
        candidate.model, candidate.report, candidate.device = model, report, device
        return candidate

    monkeypatch.setattr(adaptation, 'ExperimentCandidate', constructor)
    monkeypatch.setattr(torch.cuda, 'is_available', lambda: pytest.fail('Explicit CPU adapter probed CUDA'))
    baseline = benchmark.run('x3d', corpus, tmp_path / 'baseline.json', yield_to_demo=False,
                              runtime_factory=Runtime, model_factory=lambda *_a, **_k: Candidate('x3d'),
                              window_reader=lambda *_a, **_k: iter([packet()]))
    reports = []
    for epoch in (3, 10):
        directory = root / f'epoch-{epoch:03d}'
        report = benchmark.run('community-v2', corpus, tmp_path / f'v2-e{epoch}.json',
                               adaptation_run=directory, training_manifest_sha256=sha,
                               yield_to_demo=False, runtime_factory=Runtime,
                               window_reader=lambda *_a, **_k: iter([packet()]))
        reports.append(report)
        assert report['candidate'] == 'community-v2' and report['device'] == 'cpu'
        identity = report['adaptationIdentity']
        assert identity['exportEpoch'] == epoch
        assert identity['runSealSha256'] == benchmark.digest(root / 'complete.json')
        assert identity['adaptationSha256'] == seal['milestones'][str(epoch)]['candidateSha256']
        assert identity['adaptationReportSha256'] == benchmark.digest(directory / 'report.json')
        assert identity['trainingManifestSha256'] == sha
        assert report['adapter']['exportEpoch'] == epoch
        assert report['trainedSourceHashes'] == report['adapter']['trainedSourceHashes']
        for field in ('pairedWindowSha256', 'policySha256', 'corpusSha256'):
            assert report[field] == baseline[field]
        assert report['policy'] == baseline['policy']
        row = report['clips']['clip-0']
        assert row['derivative'] is True and row['qualityVariant'] == records[0]['qualityVariant']
        assert row['samples'][0]['scoreKind'] == 'retained-backbone-softmax'
        for name in ('community_x3d_experiments.py', 'community_x3d_training.py',
                     'x3d_training.py', 'x3d_finetune.py', 'training_data.py', 'x3d_candidate.py'):
            assert report['implementationHashes']['nivra/' + name] == benchmark.digest(benchmark.ROOT / 'nivra' / name)
    assert reports[0]['adaptationIdentity'] != reports[1]['adaptationIdentity']
    assert constructors == [(str(root / 'epoch-003'), sha, 'cpu'), (str(root / 'epoch-010'), sha, 'cpu')]


@pytest.mark.parametrize('damage', ['missing-sha', 'malformed-sha', 'wrong-sha', 'missing-run',
                                   'missing-seal', 'corrupt-seal', 'incomplete-seal',
                                   'wrong-epoch', 'artifact', 'source', 'missing-sibling'])
def test_community_v2_invalid_assets_fail_before_runtime_model_or_decoder(tmp_path, monkeypatch, damage):
    adaptation, root, _, sha = community_v2_run(tmp_path / 'training', monkeypatch,
                                               epochs=10 if damage == 'missing-sibling' else 3)
    diagnostic = tmp_path / 'diagnostic'
    diagnostic.mkdir()
    corpus, _, _ = inputs(diagnostic, monkeypatch, count=1)
    directory = root / 'epoch-003'
    if damage == 'missing-sha': sha = None
    if damage == 'malformed-sha': sha = 'not-a-sha'
    if damage == 'wrong-sha': sha = '0' * 64
    if damage == 'missing-run': directory = None
    if damage == 'missing-seal': (root / 'complete.json').unlink()
    if damage == 'corrupt-seal': (root / 'complete.json').write_text('not-json')
    if damage == 'incomplete-seal':
        value = json.loads((root / 'complete.json').read_text())
        value['complete'] = False
        (root / 'complete.json').write_text(json.dumps(value))
    if damage == 'artifact': (directory / 'candidate-state.pt').write_bytes(b'corrupt')
    if damage == 'source': (directory / 'source/community_x3d_experiments.py').write_bytes(b'corrupt')
    if damage == 'missing-sibling': (root / 'epoch-010/candidate-state.pt').unlink()
    if damage == 'wrong-epoch':
        import torch
        from test_community_x3d_experiments import reseal
        artifact = torch.load(directory / 'candidate-state.pt', weights_only=True, map_location='cpu')
        report = json.loads((directory / 'report.json').read_text())
        artifact['training']['exportEpoch'] = report['training']['exportEpoch'] = 10
        torch.save(artifact, directory / 'candidate-state.pt')
        (directory / 'report.json').write_text(json.dumps(report))
        reseal(directory)

    def forbidden(*_a, **_k):
        pytest.fail('Invalid V2 reached runtime/model/decoder')

    monkeypatch.setattr(adaptation, 'ExperimentCandidate', forbidden)
    output = tmp_path / 'never-created' / 'report.json'
    with pytest.raises((ValueError, OSError)):
        benchmark.run('community-v2', corpus, output, adaptation_run=directory,
                       training_manifest_sha256=sha, yield_to_demo=False,
                       runtime_factory=forbidden, model_factory=forbidden, window_reader=forbidden)
    assert not output.parent.exists()


def test_community_v2_seal_change_during_comparison_prevents_output(tmp_path, monkeypatch):
    _, root, _, sha = community_v2_run(tmp_path / 'training', monkeypatch)
    diagnostic = tmp_path / 'diagnostic'
    diagnostic.mkdir()
    corpus, _, _ = inputs(diagnostic, monkeypatch, count=1)

    def reader(*_args, **_kwargs):
        seal_path = root / 'complete.json'
        seal_path.write_text(seal_path.read_text() + ' ')
        yield packet()

    output = tmp_path / 'never-created' / 'report.json'
    with pytest.raises(ValueError, match='seal changed during comparison'):
        benchmark.run('community-v2', corpus, output, adaptation_run=root / 'epoch-003',
                       training_manifest_sha256=sha, yield_to_demo=False, runtime_factory=Runtime,
                       model_factory=lambda *_a, **_k: Candidate('community-v2'), window_reader=reader)
    assert not output.parent.exists()


def test_community_v2_cli_forwards_explicit_pin_and_keeps_output_new(tmp_path, monkeypatch, capsys):
    corpus, _, _ = inputs(tmp_path, monkeypatch, count=1)
    output = tmp_path / 'result.json'
    for extra in ([], ['--training-manifest-sha256', 'bad']):
        assert benchmark.main(['--candidate', 'community-v2', '--device', 'cpu', '--corpus', str(corpus),
                               '--output', str(output), '--adaptation-run', str(tmp_path / 'missing'),
                               '--no-yield-to-demo', *extra]) == 1
        assert '--training-manifest-sha256' in capsys.readouterr().err
        assert not output.exists()
    calls = []

    def run(candidate, corpus, output, **kwargs):
        calls.append((candidate, kwargs))
        return {'status': 'synthetic', 'windowCount': 1, 'pairedWindowSha256': 'b' * 64}

    original_run = benchmark.run
    monkeypatch.setattr(benchmark, 'run', run)
    assert benchmark.main(['--candidate', 'community-v2', '--device', 'cpu', '--corpus', str(corpus),
                           '--output', str(output), '--adaptation-run', str(tmp_path / 'epoch-003'),
                           '--training-manifest-sha256', 'a' * 64, '--no-yield-to-demo']) == 0
    assert calls[0][0] == 'community-v2'
    assert calls[0][1]['training_manifest_sha256'] == 'a' * 64
    assert calls[0][1]['device'] == 'cpu'
    output.write_text('preserve prior raw report')
    with pytest.raises(FileExistsError):
        original_run('community-v2', corpus, output)
    assert output.read_text() == 'preserve prior raw report'


@pytest.mark.parametrize('fraction', [.2, .4])
def test_community_v2_fixed_loader_cannot_override_requested_cuda_budget(tmp_path, fraction):
    def forbidden(*_a, **_k):
        pytest.fail('Invalid fixed V2 budget reached runtime/model/decoder')

    with pytest.raises(ValueError, match='fixed .35 allocator'):
        benchmark.run('community-v2', tmp_path / 'missing.json', tmp_path / 'no-report.json',
                       device='cuda', cuda_memory_fraction=fraction, model_factory=forbidden,
                       runtime_factory=forbidden, window_reader=forbidden)
    assert not (tmp_path / 'no-report.json').exists()
