import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from nivra import crowd_observer as crowd
import research_crowd_observer as cli


def node(name, shape, dtype='tensor(float)'):
    return SimpleNamespace(name=name, shape=shape, type=dtype)


def empty_outputs():
    return np.zeros((1, 0, 5), np.float32), np.zeros((1, 0, 17, 3), np.float32)


class Session:
    def __init__(self, outputs=None):
        self.calls = []
        self.outputs = outputs
        self.inputs = [node('input', ['batch', 3, 640, 640])]
        self.nodes = [node('dets', ['batch', 'slots', 'columns']),
                      node('keypoints', ['batch', 'slots', 'joints', 'xyz'])]
        self.providers = ['CPUExecutionProvider']

    def get_inputs(self):
        return self.inputs

    def get_outputs(self):
        return self.nodes

    def get_providers(self):
        return self.providers

    def disable_fallback(self):
        self.fallback_disabled = True

    def run(self, names, feed):
        index = len(self.calls)
        self.calls.append((names, feed))
        if callable(self.outputs):
            return self.outputs(index)
        return self.outputs if self.outputs is not None else empty_outputs()


def outputs_for_boxes(boxes, confidence=.8):
    dets = np.zeros((1, len(boxes), 5), np.float32)
    pose = np.zeros((1, len(boxes), 17, 3), np.float32)
    for index, box in enumerate(boxes):
        dets[0, index] = [*box, confidence]
        pose[0, index, :, :2] = [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2]
        pose[0, index, :, 2] = confidence
    return dets, pose


@pytest.mark.parametrize('width,height', [(1920, 1080), (1080, 1920), (1280, 720), (640, 480), (32, 32)])
def test_native_bounds_and_five_fixed_views(width, height):
    geometry = crowd.view_geometry(width, height)
    assert len(geometry) == 5 and geometry[0] == (0, 0, width, height)
    assert geometry[1] == (0, 0, round(.65 * width), round(.65 * height))
    assert geometry[-1] == (round(.35 * width), round(.35 * height), width, height)
    session = Session()
    result = crowd.CrowdObserver(session).observe(np.zeros((height, width, 3), np.uint8), 123)
    assert len(session.calls) == result['coverage']['analyzedViews'] == 5
    assert result['coverage']['fightAnalyzedPeople'] is None
    assert result['coverage']['fightAnalysisStatus'] == 'not-run'


@pytest.mark.parametrize('shape', [(1081, 1920, 3), (1920, 1081, 3), (1920, 1920, 3), (20, 200, 3), (100, 100), (100, 100, 4)])
def test_bad_native_shapes_fail_before_any_run(shape):
    session = Session()
    with pytest.raises(ValueError):
        crowd.CrowdObserver(session).observe(np.zeros(shape, np.uint8), 0)
    assert session.calls == []


def test_letterbox_is_bgr_unnormalized_top_left_and_padding_114():
    frame = np.empty((100, 200, 3), np.uint8)
    frame[:] = [11, 45, 201]
    tensor, ratio = crowd.letterbox(frame)
    assert ratio == 3.2 and tensor.dtype == np.float32 and tensor.shape == (1, 3, 640, 640)
    assert tensor[0, :, 0, 0].tolist() == [11, 45, 201]
    assert tensor[0, :, 320:, :].min() == tensor[0, :, 320:, :].max() == 114


def test_tile_mapping_clips_coordinates_and_zeroes_outside_joint_confidence():
    # Lower-right tile of 1000x800 is [350,280,1000,800], ratio 640/650.
    geometry = crowd.view_geometry(1000, 800)[4]
    ratio = 640 / 650
    outputs = outputs_for_boxes([[-10 * ratio, 10 * ratio, 100 * ratio, 100 * ratio]])
    outputs[1][0, 0, 0] = [-5 * ratio, 20 * ratio, .9]
    outputs[1][0, 0, 1] = [650 * ratio, 20 * ratio, .9]
    observer = crowd.CrowdObserver(Session())
    people, telemetry = observer._map_outputs(outputs, geometry, 1000, 800, ratio, 4)
    person = people[0]
    assert person['boxPixels'] == pytest.approx([350, 290, 450, 380])
    assert person['boxNormalized'] == pytest.approx([.35, .3625, .45, .475])
    assert person['keypointsPixels'][0] == pytest.approx([350, 300, 0])
    assert person['keypointsPixels'][1] == pytest.approx([1000, 300, 0])
    assert person['clippedByView'] is True and telemetry['eligibleObservations'] == 1
    assert len(person['keypointsNormalized']) == 17


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -.1, 1.1])
def test_invalid_confidences_or_nonfinite_outputs_fail_even_on_low_score_slots(bad):
    outputs = outputs_for_boxes([[10, 10, 100, 100]], confidence=0)
    outputs[1][0, 0, 2, 2] = bad
    session = Session(outputs)
    with pytest.raises(ValueError):
        crowd.CrowdObserver(session).observe(np.zeros((640, 640, 3), np.uint8), 0)


@pytest.mark.parametrize('pose_shape,dets_shape', [((1, 1, 14, 3), (1, 1, 5)), ((1, 1, 17, 2), (1, 1, 5)),
                                                  ((2, 1, 17, 3), (2, 1, 5)), ((1, 2, 17, 3), (1, 1, 5)),
                                                  ((1, 257, 17, 3), (1, 257, 5))])
def test_exact_runtime_shapes_and_slot_bound(pose_shape, dets_shape):
    session = Session((np.zeros(dets_shape, np.float32), np.zeros(pose_shape, np.float32)))
    with pytest.raises(ValueError, match='runtime RTMO'):
        crowd.CrowdObserver(session).observe(np.zeros((100, 100, 3), np.uint8), 0)


def test_symbolic_metadata_stays_unknown_until_runtime_not_assumed_17_or_50():
    observer = crowd.CrowdObserver(Session())
    assert observer.metadata['metadataJointCount'] is None
    assert observer.metadata['metadataSlotCount'] is None
    assert observer.metadata['symbolicDimensionsRequireRuntimeValidation'] is True


@pytest.mark.parametrize('shape', [[1, 50, 14, 3], [1, None, 17, 3], [1, '', 17, 3], [1, 257, 17, 3], [1, 50, 17]])
def test_invalid_or_unnamed_unknown_metadata_rejected(shape):
    session = Session()
    session.nodes[1].shape = shape
    with pytest.raises(ValueError):
        crowd.CrowdObserver(session)
    assert session.calls == []


def test_overlap_duplicates_across_global_and_tiles_and_exact_telemetry():
    geometries = crowd.view_geometry(1000, 800)
    box = np.array([400, 350, 500, 450], dtype=float)

    def outputs(index):
        x, y, right, bottom = geometries[index]
        ratio = min(640 / (right - x), 640 / (bottom - y))
        local = (box - [x, y, x, y]) * ratio
        return outputs_for_boxes([local], confidence=.9 - index * .01)

    result = crowd.CrowdObserver(Session(outputs)).observe(np.zeros((800, 1000, 3), np.uint8), 0)
    coverage = result['coverage']
    assert coverage['eligibleBeforeDedup'] == 5
    assert coverage['deduplicatedBeforeCap'] == coverage['returnedObservations'] == 1
    assert coverage['duplicateObservationsRemoved'] == 4
    assert coverage['omittedByCap'] == 0
    assert result['observations'][0]['boxPixels'] == pytest.approx(box)
    assert 'sourceSlot' not in result['observations'][0]


def test_more_than_100_stub_people_counts_before_cap_without_all_pairs():
    boxes = [[x * 55 + 1, y * 55 + 1, x * 55 + 21, y * 55 + 31]
             for y in range(11) for x in range(11)]
    session = Session(lambda index: outputs_for_boxes(boxes) if index == 0 else empty_outputs())
    result = crowd.CrowdObserver(session).observe(np.zeros((640, 640, 3), np.uint8), 0)
    c = result['coverage']
    assert c['eligibleBeforeDedup'] == c['deduplicatedBeforeCap'] == 121
    assert c['returnedObservations'] == 100 and c['omittedByCap'] == 21
    assert c['dedupIoUComparisons'] < 121 * 120 // 2
    assert result['views'][0]['allReturnedSlotsEligible'] is True
    assert result['views'][0]['atConfiguredSlotSafetyLimit'] is False
    assert result['views'][0]['runtimeKeypointShape'] == [1, 121, 17, 3]


def test_dedup_dense_work_budget_fails_closed_instead_of_silent_drop():
    outputs = outputs_for_boxes([[0, 0, 10, 10], [20, 0, 30, 10], [40, 0, 50, 10]])
    session = Session(lambda index: outputs if index == 0 else empty_outputs())
    with pytest.raises(ValueError, match='comparison budget'):
        crowd.CrowdObserver(session, policy=crowd.ObserverPolicy(max_iou_comparisons=1)).observe(
            np.zeros((640, 640, 3), np.uint8), 0)


def pinned_model(tmp_path, monkeypatch):
    data = b'local stub model bytes; never executable'
    sha = hashlib.sha256(data).hexdigest()
    monkeypatch.setattr(crowd, 'MODEL_SHA256', sha)
    (tmp_path / 'models').mkdir()
    (tmp_path / 'models' / 'rtmo_m.onnx').write_bytes(data)
    (tmp_path / 'model-manifest.json').write_text(json.dumps({'models': [
        {'id': crowd.MODEL_ID, 'file': 'rtmo_m.onnx', 'sha256': sha}]}))
    return data


def fake_ort(providers, *, active=None):
    calls = []

    class Options:
        def __init__(self):
            self.entries = {}

        def add_session_config_entry(self, name, value):
            self.entries[name] = value

    def factory(data, **kwargs):
        session = Session()
        session.providers = active or [p[0] if isinstance(p, tuple) else p for p in kwargs['providers']]
        calls.append((data, kwargs, session))
        return session

    return SimpleNamespace(__version__='stub', get_available_providers=lambda: providers,
                           SessionOptions=Options, InferenceSession=factory,
                           ExecutionMode=SimpleNamespace(ORT_SEQUENTIAL='sequential')), calls


def test_cpu_hash_verified_bytes_one_session_no_cuda_or_inference(tmp_path, monkeypatch):
    data = pinned_model(tmp_path, monkeypatch)
    ort, calls = fake_ort(['CPUExecutionProvider', 'CUDAExecutionProvider'])
    observer = crowd.create_observer('cpu', service_root=tmp_path, ort_module=ort)
    assert len(calls) == 1 and calls[0][0] == data
    assert calls[0][1]['providers'] == ['CPUExecutionProvider']
    assert calls[0][2].fallback_disabled and calls[0][2].calls == []
    assert observer.runtime['cudaArenaLimitBytes'] is None


def test_bad_hash_never_loads_session(tmp_path, monkeypatch):
    pinned_model(tmp_path, monkeypatch)
    (tmp_path / 'models' / 'rtmo_m.onnx').write_bytes(b'tampered')
    ort, calls = fake_ort(['CPUExecutionProvider'])
    with pytest.raises(ValueError, match='checksum'):
        crowd.create_observer('cpu', service_root=tmp_path, ort_module=ort)
    assert calls == []


def test_changed_manifest_pin_never_loads_session(tmp_path, monkeypatch):
    pinned_model(tmp_path, monkeypatch)
    p = tmp_path / 'model-manifest.json'
    value = json.loads(p.read_text())
    value['models'][0]['sha256'] = '0' * 64
    p.write_text(json.dumps(value))
    ort, calls = fake_ort(['CPUExecutionProvider'])
    with pytest.raises(ValueError, match='approved asset pin'):
        crowd.create_observer('cpu', service_root=tmp_path, ort_module=ort)
    assert calls == []


def test_cuda_explicit_1gib_arena_and_no_cpu_fallback_configuration(tmp_path, monkeypatch):
    pinned_model(tmp_path, monkeypatch)
    monkeypatch.setattr(crowd.platform, 'system', lambda: 'Linux')
    ort, calls = fake_ort(['CPUExecutionProvider', 'CUDAExecutionProvider'])
    observer = crowd.create_observer('cuda', service_root=tmp_path, ort_module=ort)
    options = calls[0][1]
    assert options['providers'][0][0] == 'CUDAExecutionProvider'
    assert options['providers'][0][1]['gpu_mem_limit'] == 1 << 30
    assert options['sess_options'].entries['session.disable_cpu_ep_fallback'] == '1'
    assert observer.runtime['gpuPeakMemoryBytes'] is None
    assert calls[0][2].calls == []


@pytest.mark.parametrize('available,active', [(['CPUExecutionProvider'], None),
                                            (['CUDAExecutionProvider'], ['CPUExecutionProvider'])])
def test_cuda_unavailable_or_failed_activation_never_claims_fallback(tmp_path, monkeypatch, available, active):
    pinned_model(tmp_path, monkeypatch)
    monkeypatch.setattr(crowd.platform, 'system', lambda: 'Linux')
    ort, calls = fake_ort(available, active=active)
    with pytest.raises(RuntimeError):
        crowd.create_observer('cuda', service_root=tmp_path, ort_module=ort)
    assert not calls or calls[0][2].calls == []


def test_cpu_cannot_request_torch_dll_preload():
    with pytest.raises(ValueError, match='explicit Windows CUDA'):
        crowd.create_observer('cpu', preload_torch_dlls=True)


class Capture:
    def __init__(self, pts, *, shape=(64, 64, 3)):
        self.pts, self.shape, self.index, self.released = pts, shape, -1, False

    def isOpened(self):
        return True

    def read(self):
        self.index += 1
        return ((True, np.zeros(self.shape, np.uint8)) if self.index < len(self.pts) else (False, None))

    def get(self, prop):
        if prop == cli.cv2.CAP_PROP_FRAME_WIDTH:
            return self.shape[1]
        if prop == cli.cv2.CAP_PROP_FRAME_HEIGHT:
            return self.shape[0]
        if prop == cli.cv2.CAP_PROP_POS_MSEC:
            return self.pts[self.index]
        raise AssertionError('FPS or another invented clock must never be queried')

    def release(self):
        self.released = True


def local_video(tmp_path):
    path = tmp_path / 'source.webm'
    path.write_bytes(b'not decoded by stub')
    return path


def test_actual_pts_sampling_not_nominal_fps_and_releases_decoder(tmp_path):
    capture = Capture([5, 53, 107, 204])
    calls = []

    def factory(*args):
        calls.append(args)
        return capture

    rows = list(cli.sample_pts_frames(local_video(tmp_path), count=3, start_ms=0, interval_ms=100,
                                     capture_factory=factory))
    assert [r[0]['timestampMs'] for r in rows] == [5, 107, 204]
    assert [r[0]['frameIndex'] for r in rows] == [0, 2, 3]
    assert rows[-1][0]['targetOvershootMs'] == 4
    assert capture.released and calls[0][1] == cli.cv2.CAP_FFMPEG
    assert calls[0][2][:2] == [cli.cv2.CAP_PROP_N_THREADS, 1]


@pytest.mark.parametrize('pts', [[0, 0], [0, -1], [0, float('nan')], [0, 60_001]])
def test_bad_actual_pts_fail_and_release(tmp_path, pts):
    capture = Capture(pts)
    with pytest.raises(ValueError, match='presentation timestamp'):
        list(cli.sample_pts_frames(local_video(tmp_path), count=2, start_ms=0, interval_ms=100,
                                   capture_factory=lambda *args: capture))
    assert capture.released


def test_decode_frame_limit_is_hard_and_no_insufficient_sample_success(tmp_path):
    capture = Capture([0, 33, 66, 99, 132])
    with pytest.raises(ValueError, match='Insufficient'):
        list(cli.sample_pts_frames(local_video(tmp_path), count=2, start_ms=0, interval_ms=100,
                                   frame_limit=3, capture_factory=lambda *args: capture))
    assert capture.index == 2 and capture.released


@pytest.mark.parametrize('kwargs', [{'count': 9}, {'count': True}, {'interval_ms': 0},
                                   {'frame_limit': 2001}, {'timeout_seconds': 31}, {'start_ms': float('nan')}])
def test_sampling_budgets_reject_before_open(tmp_path, kwargs):
    called = []
    args = dict(count=2, start_ms=0, interval_ms=100)
    args.update(kwargs)
    with pytest.raises(ValueError):
        list(cli.sample_pts_frames(local_video(tmp_path), **args,
                                   capture_factory=lambda *args: called.append(args)))
    assert called == []


def staged_corpus(tmp_path, monkeypatch):
    service = tmp_path / 'service'
    service.mkdir()
    monkeypatch.setattr(cli, 'SERVICE', service)
    monkeypatch.setattr(cli, 'REPOSITORY', tmp_path)
    monkeypatch.setattr(cli, 'RUNS', service / 'research' / 'runs')
    monkeypatch.setattr(cli, 'DemoHealthGuard', lambda *a: lambda: None)
    rows = []
    for identifier in cli.ORIGINAL_IDS:
        source = service / (identifier + '.webm')
        source.write_bytes(identifier.encode())
        rows.append({'id': identifier, 'path': source.name, 'sha256': cli.digest(source),
                     'durationMs': 3000, 'license': 'test fixture only'})
    monkeypatch.setattr(cli, 'ORIGINAL_SHA256', {r['id']: r['sha256'] for r in rows})
    manifest = service / 'corpus.json'
    manifest.write_text(json.dumps(rows))
    return manifest, rows


def test_complete_cli_report_uses_one_observer_and_exclusive_output(tmp_path, monkeypatch):
    manifest, _ = staged_corpus(tmp_path, monkeypatch)
    sessions = []

    def factory(device, **kwargs):
        session = Session()
        sessions.append(session)
        return crowd.CrowdObserver(session)

    report = cli.run_research(corpus=manifest, corpus_sha256=cli.digest(manifest),
                              output=Path('new.json'), device='cpu', observer_factory=factory,
                              interval_ms=100, capture_factory=lambda *args: Capture([0, 100]))
    assert len(sessions) == 1 and len(sessions[0].calls) == 40
    assert len(report['frames']) == 8
    path = cli.RUNS / 'new.json'
    assert json.loads(path.read_text())['status'] == 'offline-research-observer-only'
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        cli.run_research(corpus=manifest, corpus_sha256=cli.digest(manifest), output=path,
                         device='cpu', observer_factory=lambda *a, **k: pytest.fail('must fail before model load'))
    assert path.read_bytes() == before


@pytest.mark.parametrize('name', ['../escape.json', 'data.txt', '/outside-report.json'])
def test_output_paths_are_confined(tmp_path, monkeypatch, name):
    staged_corpus(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        cli.output_path(Path(name))


def test_output_symlink_escape_is_rejected(tmp_path, monkeypatch):
    staged_corpus(tmp_path, monkeypatch)
    cli.RUNS.mkdir(parents=True)
    outside = tmp_path / 'outside'
    outside.mkdir()
    try:
        (cli.RUNS / 'linked').symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip('Windows symlink privilege unavailable')
    with pytest.raises(ValueError):
        cli.output_path(Path('linked/new.json'))


def test_source_hash_failure_precedes_model_load(tmp_path, monkeypatch):
    manifest, rows = staged_corpus(tmp_path, monkeypatch)
    (manifest.parent / rows[0]['path']).write_bytes(b'tampered')
    with pytest.raises(ValueError, match='checksum'):
        cli.run_research(corpus=manifest, corpus_sha256=cli.digest(manifest), output=Path('new.json'),
                         device='cpu', observer_factory=lambda *a, **k: pytest.fail('unverified sources'))
    assert not (cli.RUNS / 'new.json').exists()


def test_wrong_corpus_hash_and_sample_duration_fail_before_model_load(tmp_path, monkeypatch):
    manifest, _ = staged_corpus(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='checksum'):
        cli.load_corpus(manifest, '0' * 64)
    with pytest.raises(ValueError, match='duration'):
        cli.run_research(corpus=manifest, corpus_sha256=cli.digest(manifest), output=Path('new.json'),
                         device='cpu', frames_per_recording=8,
                         observer_factory=lambda *a, **k: pytest.fail('bad sample duration'))


@pytest.mark.parametrize('timestamp', [-1, True, float('nan'), float('inf')])
def test_invalid_frame_timestamp_precedes_any_inference(timestamp):
    session = Session()
    with pytest.raises(ValueError, match='timestamp'):
        crowd.CrowdObserver(session).observe(np.zeros((64, 64, 3), np.uint8), timestamp)
    assert session.calls == []


def test_nonfinite_box_and_out_of_range_detection_score_rejected():
    observer = crowd.CrowdObserver(Session())
    for channel, value in [(0, float('nan')), (4, 1.1), (4, -.1)]:
        outputs = outputs_for_boxes([[0, 0, 100, 100]])
        outputs[0][0, 0, channel] = value
        with pytest.raises(ValueError):
            observer._map_outputs(outputs, (0, 0, 640, 640), 640, 640, 1, 0)


def test_static_output_slot_count_is_enforced_at_runtime():
    session = Session()
    session.nodes = [node('dets', [1, 50, 5]), node('keypoints', [1, 50, 17, 3])]
    observer = crowd.CrowdObserver(session)
    assert observer.metadata['metadataJointCount'] == 17
    assert observer.metadata['metadataSlotCount'] == 50
    with pytest.raises(ValueError, match='static model metadata'):
        observer._map_outputs(empty_outputs(), (0, 0, 640, 640), 640, 640, 1, 0)


def test_decode_time_budget_is_enforced_and_decoder_released(tmp_path, monkeypatch):
    times = iter([0, 0, 21])
    monkeypatch.setattr(cli, 'perf_counter', lambda: next(times))
    capture = Capture([0])
    with pytest.raises(ValueError, match='wall-time budget'):
        list(cli.sample_pts_frames(local_video(tmp_path), count=1, start_ms=0, interval_ms=100,
                                   capture_factory=lambda *args: capture))
    assert capture.released


def test_observer_time_does_not_consume_decode_budget(tmp_path, monkeypatch):
    # A long pause while the generator yields represents caller's model work.
    times = iter([0, 1, 2, 3, 103, 104, 105, 106, 107])
    monkeypatch.setattr(cli, 'perf_counter', lambda: next(times))
    capture = Capture([0, 100])
    rows = list(cli.sample_pts_frames(local_video(tmp_path), count=2, start_ms=0, interval_ms=100,
                                     capture_factory=lambda *args: capture))
    assert len(rows) == 2 and capture.released


def test_bad_decoder_dimensions_rejected_before_read(tmp_path):
    capture = Capture([0], shape=(1081, 1920, 3))
    with pytest.raises(ValueError):
        list(cli.sample_pts_frames(local_video(tmp_path), count=1, start_ms=0, interval_ms=100,
                                   capture_factory=lambda *args: capture))
    assert capture.index == -1 and capture.released


def test_pinned_original_hash_cannot_be_replaced_by_editing_corpus(tmp_path, monkeypatch):
    manifest, rows = staged_corpus(tmp_path, monkeypatch)
    (manifest.parent / rows[0]['path']).write_bytes(b'replacement')
    rows[0]['sha256'] = cli.digest(manifest.parent / rows[0]['path'])
    manifest.write_text(json.dumps(rows))
    with pytest.raises(ValueError, match='checksum'):
        cli.load_corpus(manifest, cli.digest(manifest))


def test_failed_decode_writes_no_success_report(tmp_path, monkeypatch):
    manifest, _ = staged_corpus(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='presentation timestamp'):
        cli.run_research(corpus=manifest, corpus_sha256=cli.digest(manifest), output=Path('fail.json'),
                         device='cpu', interval_ms=100,
                         observer_factory=lambda *a, **k: crowd.CrowdObserver(Session()),
                         capture_factory=lambda *args: Capture([0, 0]))
    assert not (cli.RUNS / 'fail.json').exists()


def test_actual_sample_past_declared_duration_aborts_without_report(tmp_path, monkeypatch):
    manifest, _ = staged_corpus(tmp_path, monkeypatch)
    captures = []

    def factory(*args):
        capture = Capture([0, 4000])
        captures.append(capture)
        return capture

    with pytest.raises(ValueError, match='declared source duration'):
        cli.run_research(corpus=manifest, corpus_sha256=cli.digest(manifest), output=Path('fail.json'),
                         device='cpu', interval_ms=100,
                         observer_factory=lambda *a, **k: crowd.CrowdObserver(Session()),
                         capture_factory=factory)
    assert captures[0].released and not (cli.RUNS / 'fail.json').exists()


def profile_prefix(root):
    directory = root / 'research' / 'runs' / 'new.operators'
    directory.mkdir(parents=True)
    return directory / 'ort'


def profile_event(provider, op, name=None):
    return {'cat': 'Node', 'name': (name or op) + '_kernel_time',
            'args': {'provider': provider, 'op_name': op}}


def write_profile(prefix, events):
    path = prefix.parent / (prefix.name + '_stub.json')
    path.write_text(json.dumps(events))
    return path


def test_mixed_cuda_is_explicit_profiles_and_retains_first_gpu_and_arena(tmp_path, monkeypatch):
    pinned_model(tmp_path, monkeypatch)
    monkeypatch.setattr(crowd.platform, 'system', lambda: 'Linux')
    prefix = profile_prefix(tmp_path)
    ort, calls = fake_ort(['CUDAExecutionProvider', 'CPUExecutionProvider'])
    observer = crowd.create_observer('cuda', service_root=tmp_path, ort_module=ort,
                                      allow_cpu_operators=True, profile_prefix=prefix)
    options = calls[0][1]
    assert options['providers'][0][0] == 'CUDAExecutionProvider'
    assert options['providers'][1] == 'CPUExecutionProvider'
    assert options['providers'][0][1]['gpu_mem_limit'] == 1 << 30
    assert 'session.disable_cpu_ep_fallback' not in options['sess_options'].entries
    assert options['sess_options'].enable_profiling
    assert options['sess_options'].profile_file_prefix == str(prefix)
    assert calls[0][2].fallback_disabled and not calls[0][2].calls
    assert observer.runtime['allowCpuOperators'] is True
    assert observer.runtime['cpuExecutionFallbackDisabled'] is False
    assert observer.runtime['pythonProviderFallbackDisabled'] is True
    assert observer.runtime['gpuVerified'] is False  # Providers alone do not prove execution.


def test_mixed_requires_cuda_and_profile_before_model_load():
    with pytest.raises(ValueError, match='CUDA research policy'):
        crowd.create_observer('cpu', allow_cpu_operators=True)
    with pytest.raises(ValueError, match='require operator profiling'):
        crowd.create_observer('cuda', allow_cpu_operators=True)


def test_ort_pybind_like_initialization_failure_is_readable_runtime_error(tmp_path, monkeypatch):
    pinned_model(tmp_path, monkeypatch)
    ort, calls = fake_ort(['CUDAExecutionProvider'])

    class ORTFail(Exception):
        pass

    def fail(*args, **kwargs):
        raise ORTFail('CPU EP assigned nodes with CPU EP explicitly disabled')

    ort.InferenceSession = fail
    monkeypatch.setattr(crowd.platform, 'system', lambda: 'Linux')
    with pytest.raises(RuntimeError, match='ORT session initialization failed: CPU EP'):
        crowd.create_observer('cuda', service_root=tmp_path, ort_module=ort)
    assert calls == []


def test_profile_discloses_actual_operator_counts_and_unique_executions(tmp_path):
    prefix = profile_prefix(tmp_path)
    events = [profile_event('CUDAExecutionProvider', 'Conv'),
              profile_event('CUDAExecutionProvider', 'Conv'),
              profile_event('CUDAExecutionProvider', 'MemcpyFromHost'),
              profile_event('CPUExecutionProvider', 'Shape'),
              {'cat': 'Node', 'name': 'Conv_fence_before', 'args': {}},
              {'cat': 'Session', 'name': 'run'}]
    path = write_profile(prefix, events)
    summary = crowd.summarize_operator_profile(path, prefix)
    assert summary['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert summary['nodeExecutionCountsByProvider'] == {'CUDAExecutionProvider': 3, 'CPUExecutionProvider': 1}
    assert summary['uniqueExecutedNodeCountsByProvider'] == {'CUDAExecutionProvider': 2, 'CPUExecutionProvider': 1}
    assert summary['operatorExecutionCountsByProvider']['CPUExecutionProvider'] == {'Shape': 1}
    assert summary['cudaNonMemcpyComputeEvents'] == 2 and summary['gpuComputeObserved']


def test_memcpy_or_provider_presence_never_verifies_cuda_compute(tmp_path):
    prefix = profile_prefix(tmp_path)
    path = write_profile(prefix, [profile_event('CUDAExecutionProvider', 'MemcpyToHost'),
                                  profile_event('CPUExecutionProvider', 'Conv')])
    session = Session()
    session.end_profiling = lambda: str(path)
    observer = crowd.CrowdObserver(session, profile_prefix=prefix,
                                   runtime={'device': 'cuda', 'providers': ['CUDAExecutionProvider', 'CPUExecutionProvider']})
    summary = observer.finish_profile()
    assert summary['gpuComputeObserved'] is False
    assert observer.runtime['gpuVerified'] is False
    with pytest.raises(RuntimeError, match='already finalized'):
        observer.finish_profile()


def test_profile_positive_cuda_compute_required_to_mark_verified(tmp_path):
    prefix = profile_prefix(tmp_path)
    path = write_profile(prefix, [profile_event('CUDAExecutionProvider', 'Conv'),
                                  profile_event('CPUExecutionProvider', 'Reshape')])
    session = Session()
    session.end_profiling = lambda: str(path)
    observer = crowd.CrowdObserver(session, profile_prefix=prefix, runtime={'device': 'cuda'})
    observer.finish_profile()
    assert observer.runtime['gpuVerified'] is True
    assert observer.runtime['gpuVerification'] == 'profiled-cuda-compute'


@pytest.mark.parametrize('kind', ['bytes', 'events', 'malformed', 'outside'])
def test_profile_parser_bounded_and_confined(tmp_path, monkeypatch, kind):
    prefix = profile_prefix(tmp_path)
    path = write_profile(prefix, [profile_event('CUDAExecutionProvider', 'Conv')])
    if kind == 'bytes':
        monkeypatch.setattr(crowd, 'MAX_PROFILE_BYTES', 10)
    elif kind == 'events':
        monkeypatch.setattr(crowd, 'MAX_PROFILE_EVENTS', 0)
    elif kind == 'malformed':
        path.write_text('{invalid json')
    else:
        path = tmp_path / 'ort_outside.json'
        path.write_text('[]')
    with pytest.raises(ValueError):
        crowd.summarize_operator_profile(path, prefix)


def test_profile_prefix_cannot_reuse_directory_or_escape(tmp_path):
    prefix = profile_prefix(tmp_path)
    (prefix.parent / 'previous.json').write_text('[]')
    with pytest.raises(FileExistsError):
        crowd.validate_profile_prefix(prefix, tmp_path)
    with pytest.raises(ValueError):
        crowd.validate_profile_prefix(tmp_path / 'ort', tmp_path)


def test_health_guard_yields_busy_then_ready_without_device_calls():
    now = [0.]
    states = iter([{'status': 'ready', 'busy': True}, {'status': 'ready', 'busy': False}])
    guard = cli.DemoHealthGuard(fetch=lambda: next(states), clock=lambda: now[0],
                                sleep=lambda seconds: now.__setitem__(0, now[0] + seconds))
    guard()
    assert guard.summary()['checks'] == 2 and now[0] == .25


def test_health_guard_busy_timeout_and_unavailable_fail_closed():
    now = [0.]
    guard = cli.DemoHealthGuard(.5, fetch=lambda: {'status': 'loading', 'busy': False},
                                clock=lambda: now[0], sleep=lambda seconds: now.__setitem__(0, now[0] + seconds))
    with pytest.raises(RuntimeError, match='yield budget'):
        guard()
    unavailable = cli.DemoHealthGuard(fetch=lambda: (_ for _ in ()).throw(OSError('offline')))
    with pytest.raises(RuntimeError, match='health unavailable'):
        unavailable()


def test_health_guard_checks_before_each_view_and_aborts_before_next_run():
    calls = []

    def guard():
        calls.append('guard')
        if len(calls) == 2:
            raise RuntimeError('busy')

    session = Session()
    observer = crowd.CrowdObserver(session, yield_guard=guard)
    with pytest.raises(RuntimeError, match='busy'):
        observer.observe(np.zeros((64, 64, 3), np.uint8), 0)
    assert len(session.calls) == 1 and len(calls) == 2


def test_cli_yields_before_load_and_each_view(tmp_path, monkeypatch):
    manifest, _ = staged_corpus(tmp_path, monkeypatch)
    events = []

    def factory(*args, **kwargs):
        assert events == ['guard']
        events.append('load')
        return crowd.CrowdObserver(Session())

    report = cli.run_research(corpus=manifest, corpus_sha256=cli.digest(manifest), output=Path('guarded.json'),
                              device='cpu', frames_per_recording=1,
                              health_guard=lambda: events.append('guard'), observer_factory=factory,
                              capture_factory=lambda *args: Capture([0]))
    assert events.count('guard') == 21  # One before load, four frames times five views.
    assert report['operatorProfile'] is None


def test_cli_failed_initialization_has_no_success_report(tmp_path, monkeypatch):
    manifest, _ = staged_corpus(tmp_path, monkeypatch)

    def fail(*args, **kwargs):
        raise RuntimeError('ORT session initialization failed: CPU-assigned operators')

    with pytest.raises(RuntimeError, match='initialization failed'):
        cli.run_research(corpus=manifest, corpus_sha256=cli.digest(manifest), output=Path('fail.json'),
                         device='cuda', allow_cpu_operators=True, observer_factory=fail)
    assert not (cli.RUNS / 'fail.json').exists()


def test_cli_mixed_implies_associated_profile_and_actual_execution_summary(tmp_path, monkeypatch):
    manifest, _ = staged_corpus(tmp_path, monkeypatch)

    def factory(*args, **kwargs):
        assert kwargs['allow_cpu_operators'] is True and kwargs['profile_prefix'] is not None
        prefix = kwargs['profile_prefix']
        session = Session()

        def finish():
            return str(write_profile(prefix, [profile_event('CUDAExecutionProvider', 'Conv'),
                                              profile_event('CPUExecutionProvider', 'Shape')]))

        session.end_profiling = finish
        return crowd.CrowdObserver(session, profile_prefix=prefix, runtime={'device': 'cuda'})

    report = cli.run_research(corpus=manifest, corpus_sha256=cli.digest(manifest), output=Path('mixed.json'),
                              device='cuda', allow_cpu_operators=True, frames_per_recording=1,
                              observer_factory=factory, capture_factory=lambda *args: Capture([0]))
    assert report['operatorProfile']['operatorExecutionCountsByProvider']['CPUExecutionProvider'] == {'Shape': 1}
    assert report['modelRuntime']['gpuVerified'] is True
    path = Path(report['operatorProfile']['path'])
    assert path.parent == cli.RUNS / 'mixed.operators' and path.is_file()


def test_cli_main_initialization_error_readable_without_traceback(monkeypatch, capsys):
    import sys

    def fail(**kwargs):
        raise RuntimeError('ORT session initialization failed: required CPU operators')

    monkeypatch.setattr(cli, 'run_research', fail)
    monkeypatch.setattr(sys, 'argv', ['research_crowd_observer.py', '--device', 'cuda',
                                     '--corpus-sha256', '0' * 64, '--output', 'failed.json'])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    stderr = capsys.readouterr().err
    assert 'initialization failed' in stderr and 'Traceback' not in stderr


def test_forward_error_wrapped_without_retry_or_another_view():
    class ORTFail(Exception):
        pass

    def fail(index):
        raise ORTFail('operator failure')

    session = Session(fail)
    with pytest.raises(RuntimeError, match='ORT observer view 0 failed: operator failure'):
        crowd.CrowdObserver(session).observe(np.zeros((64, 64, 3), np.uint8), 0)
    assert len(session.calls) == 1


def test_health_guard_refusal_prevents_session_creation(tmp_path, monkeypatch):
    manifest, _ = staged_corpus(tmp_path, monkeypatch)

    def refuse():
        raise RuntimeError('demo busy')

    with pytest.raises(RuntimeError, match='demo busy'):
        cli.run_research(corpus=manifest, corpus_sha256=cli.digest(manifest), output=Path('busy.json'),
                         device='cuda', health_guard=refuse,
                         observer_factory=lambda *a, **k: pytest.fail('guard must precede model creation'))
    assert not (cli.RUNS / 'busy.json').exists()
