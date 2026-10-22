from copy import deepcopy
from fractions import Fraction
import io
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

import prepare_cctv_variants as variants
from evaluate import validate_manifest


def clock(width=880, height=608, ticks=tuple(range(0, 2000, 100)),
          time_base=Fraction(1, 1000), sar=Fraction(1)):
    return variants.Clock(ticks, time_base, width, height, sar, 'yuv420p', (0,))


def showinfo(ticks=(0, 33, 67), nominal='30000/1', size='1920x1080'):
    lines = [f'[Parsed_showinfo_0] config in time_base: 1/1000, frame_rate: {nominal}']
    for i, pts in enumerate(ticks):
        lines.append(f'[Parsed_showinfo_0] n: {i:3d} pts: {pts:8d} pts_time:ignored '
                     f'fmt:yuv420p sar:1/1 s:{size} i:P iskey:{int(i == 0)} type:I')
    return '\n'.join(lines)


def staged(tmp_path, monkeypatch):
    monkeypatch.setattr(variants, 'REPOSITORY', tmp_path)
    monkeypatch.setattr(variants, 'RUNS', tmp_path / 'research' / 'runs')
    source = tmp_path / 'original.webm'
    source.write_bytes(b'original video fixture; not decoded')
    portrait = tmp_path / 'portrait.mp4'
    portrait.write_bytes(b'portrait fixture; not decoded')
    row = {'id': 'grapple', 'sourceGroup': 'shared-session', 'split': 'calibration',
           'path': source.name, 'sha256': variants.digest(source), 'durationMs': 2000,
           'annotationStatus': 'reviewed', 'events': [{'startMs': 400, 'endMs': 1400}],
           'source': 'original attribution', 'license': 'fixture', 'conditions': ['development']}
    cropped = deepcopy(row)
    cropped.update(id='grapple-crop', crop=[0, 0, 1, .7])
    exercise = deepcopy(row)
    exercise.update(id='exercise', path=portrait.name, sha256=variants.digest(portrait),
                    sourceGroup='exercise', split='holdout', events=[])
    records = [row, cropped, exercise]
    manifest = tmp_path / 'corpus.json'
    manifest.write_text(json.dumps(records))
    ffmpeg = tmp_path / 'ffmpeg.exe'
    ffmpeg.write_bytes(b'not an executable')
    destination = variants.RUNS / 'new-run'
    return manifest, source, portrait, ffmpeg, destination, records


def mock_media(monkeypatch, portrait, *, damage=None, source_sar=Fraction(1), portrait_sar=Fraction(1)):
    calls = []
    original_inspections = []
    monkeypatch.setattr(variants, 'checked_ffmpeg', lambda path, sha, timeout: (path, 'ffmpeg version 7.1 mock'))

    def inspect(ffmpeg, path, timeout, commands):
        if path.name.endswith('.partial.mp4'):
            out = clock(694, 480, sar=Fraction(880, 608) / Fraction(694, 480))
            if damage == 'drop':
                out = clock(694, 480, ticks=out.ticks[:-1], sar=out.sar)
            elif damage == 'shift':
                out = clock(694, 480, ticks=tuple(x + 2 for x in out.ticks), sar=out.sar)
            return {'codec': 'h264', 'width': out.width, 'height': out.height}, out
        original_inspections.append(path)
        result = clock(720, 1280, sar=portrait_sar) if path == portrait else clock(sar=source_sar)
        return {'codec': 'vp8', 'width': result.width, 'height': result.height}, result

    def encode(args, timeout):
        calls.append((args, timeout))
        if damage == 'encoder':
            Path(args[-1]).write_bytes(b'partial output')
            raise RuntimeError('encoder failed')
        if damage == 'timeout':
            raise subprocess.TimeoutExpired(args, timeout)
        Path(args[-1]).write_bytes(('encoded ' + args[-1]).encode())
        return '[libx264] 264 - core mock version\n'

    monkeypatch.setattr(variants, 'inspect_media', inspect)
    monkeypatch.setattr(variants, 'run_command', encode)

    def independent(path, sha256, timeout, commands):
        result = clock(720, 1280) if path == portrait else clock()
        if path.name.endswith('.partial.mp4'):
            result = clock(694, 480)
        pts = [float(t * 1000) for t in result.pts]
        if damage == 'opencv-shift' and path.name.endswith('.partial.mp4'):
            pts = [t + 3 for t in pts]
        return {'ptsMs': pts, 'frameCount': len(pts), 'width': result.width,
                'height': result.height, 'backend': 'FFMPEG mock'}

    monkeypatch.setattr(variants, 'inspect_opencv', independent)
    return calls, original_inspections


@pytest.mark.parametrize(('width', 'height', 'expected', 'skipped'), [
    (1920, 1080, [720, 480], False), (1280, 720, [480], False),
    (880, 608, [480], False), (720, 1280, [], True), (640, 480, [], True),
])
def test_first_matrix_never_calls_portrait_a_landscape_tier(width, height, expected, skipped):
    sizes, reason = variants.matrix_heights(width, height)
    assert sizes == expected
    assert bool(reason) == skipped


@pytest.mark.parametrize(('width', 'height', 'target'), [
    (640, 360, 480), (1280, 720, 720), (880, 608, 481), (880, 608, 0),
])
def test_no_upscale_same_size_or_odd_targets(width, height, target):
    with pytest.raises(ValueError):
        variants.target_dimensions(width, height, target)


def test_even_dimensions_and_display_aspect_verified():
    assert variants.target_dimensions(1920, 1080, 480) == (854, 480)
    assert variants.target_dimensions(880, 608, 480) == (694, 480)
    source = clock()
    output = clock(694, 480, sar=Fraction(880, 608) / Fraction(694, 480))
    assert variants.verify_pair(source, output, (694, 480))['allFramesVerified']
    with pytest.raises(ValueError, match='aspect'):
        variants.verify_pair(source, clock(694, 480), (694, 480))


def test_nominal_wrong_fps_and_rounded_pts_time_are_not_used(tmp_path):
    source = variants.parse_showinfo(showinfo((0, 33, 67, 100, 133), nominal='30000/1'))
    args, transform = variants.encoding_args(tmp_path / 'ffmpeg.exe', tmp_path / 'source.webm',
                                            tmp_path / 'out.mp4', source, 480, 35, 1_000_000)
    assert source.median_delta == Fraction(33, 1000)
    assert transform['gopFrames'] == 61  # 2 / .033, not 2 * 30000.
    assert '-r' not in args and 'fps=' not in ' '.join(args)
    assert args[args.index('-fps_mode') + 1] == 'passthrough'
    assert args[args.index('-enc_time_base') + 1] == '1/1000000'
    assert args[args.index('-video_track_timescale') + 1] == '1000000'
    assert args[args.index('-hwaccel') + 1] == 'none'
    assert '-n' in args and '-y' not in args and '-copyts' in args
    assert args[args.index('-threads') + 1] == '2'
    assert args[args.index('-max_pixels') + 1] == '2073600'


def test_rational_gap_boundary_has_no_float_rounding_bridge():
    variants.validate_clock(clock(ticks=(100, 1300)))
    with pytest.raises(ValueError, match='gap'):
        variants.validate_clock(clock(ticks=(100, 1301)))


@pytest.mark.parametrize('ticks', [(0, 0), (10, 0), (0, float('nan')), (-1, 100),
                                  tuple(range(2001)), (0, 61000)])
def test_bad_or_excessive_decoder_clocks_fail_closed(ticks):
    with pytest.raises(ValueError):
        variants.validate_clock(clock(ticks=ticks))


def test_missing_and_changing_showinfo_metadata_fail_closed():
    with pytest.raises(ValueError, match='time base'):
        variants.parse_showinfo('nothing')
    with pytest.raises(ValueError, match='changing'):
        variants.parse_showinfo(showinfo() + '\nconfig in time_base: 1/30000')
    with pytest.raises(ValueError, match='frame number'):
        variants.parse_showinfo(showinfo().replace('n:   1', 'n:   9'))
    with pytest.raises(ValueError, match='dimensions'):
        variants.parse_showinfo(showinfo().replace('s:1920x1080', 's:1280x720', 1))


def test_pts_pairing_checks_every_frame_and_exact_one_ms_tolerance():
    source = clock(1280, 720)
    sar = Fraction(1280, 720) / Fraction(854, 480)
    output = clock(854, 480, ticks=tuple(t + 1 for t in source.ticks), sar=sar)
    assert variants.verify_pair(source, output, (854, 480))['maxAbsoluteErrorMs'] == 1
    damaged = list(source.ticks)
    damaged[10] += 2
    with pytest.raises(ValueError, match='PTS mapping'):
        variants.verify_pair(source, clock(854, 480, ticks=tuple(damaged), sar=sar), (854, 480))


def test_output_and_source_paths_cannot_escape_or_overwrite(tmp_path, monkeypatch):
    manifest, source, _, _, output, records = staged(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='runs'):
        variants.owned_destination(tmp_path / 'elsewhere')
    with pytest.raises(ValueError, match='escapes'):
        variants.owned_destination(variants.RUNS / '..' / 'escape')
    output.mkdir(parents=True)
    with pytest.raises(FileExistsError):
        variants.owned_destination(output)
    outside = tmp_path.parent / (tmp_path.name + '-outside.webm')
    records[0]['path'] = '../' + outside.name
    manifest.write_text(json.dumps(records))
    outside.write_bytes(source.read_bytes())
    with pytest.raises(ValueError, match='escapes'):
        variants.load_inputs(manifest, variants.digest(manifest))


def test_input_hashes_verified_before_any_encoder_invocation(tmp_path, monkeypatch):
    manifest, source, _, ffmpeg, output, _ = staged(tmp_path, monkeypatch)
    monkeypatch.setattr(variants, 'checked_ffmpeg', lambda *_: pytest.fail('must fail before FFmpeg'))
    with pytest.raises(ValueError, match='Manifest checksum'):
        variants.run(manifest, '0' * 64, output, ffmpeg, variants.FFMPEG_SHA256)
    expected = variants.digest(manifest)
    source.write_bytes(b'tampered')
    with pytest.raises(ValueError, match='Source checksum'):
        variants.run(manifest, expected, output, ffmpeg, variants.FFMPEG_SHA256)
    assert not output.exists()


def test_ffmpeg_pin_cannot_be_replaced_by_another_binary_hash(tmp_path, monkeypatch):
    binary = tmp_path / 'ffmpeg.exe'
    binary.write_bytes(b'unapproved')
    monkeypatch.setattr(variants, 'run_command', lambda *_: pytest.fail('must not execute unapproved bytes'))
    with pytest.raises(ValueError, match='pinned binary'):
        variants.checked_ffmpeg(binary, variants.digest(binary), 1)


def test_header_probe_bounds_and_rotation_are_checked_before_decode():
    log = 'Stream #0:0: Video: vp8, yuv420p(progressive), 1920x1080, 30000 fps'
    assert variants.parse_header(log)['codec'] == 'vp8'
    with pytest.raises(ValueError, match='bounded'):
        variants.parse_header(log.replace('1920x1080', '3840x2160'))
    with pytest.raises(ValueError, match='Rotated'):
        variants.parse_header(log + '\nrotation of 90 degrees')


def test_deduplicated_parents_crop_coordinates_and_labels_survive(tmp_path, monkeypatch):
    manifest, source, portrait, ffmpeg, output, originals = staged(tmp_path, monkeypatch)
    before = manifest.read_bytes(), source.read_bytes(), portrait.read_bytes()
    calls, inspections = mock_media(monkeypatch, portrait)
    receipt = variants.run(manifest, variants.digest(manifest), output, ffmpeg, variants.FFMPEG_SHA256)
    assert receipt['status'] == 'complete'
    assert receipt['uniqueParents'] == 2 and receipt['generatedMedia'] == 2
    assert inspections == [source, portrait]
    assert len(calls) == 2
    assert all(args[args.index('-i') + 1] == str(source) for args, _ in calls)
    records = json.loads((output / 'corpus.json').read_text())
    validate_manifest(records)
    assert len(records) == 7  # Three original references plus two variants for each of two crop views.
    for original in originals:
        rows = [r for r in records if r['id'] == original['id'] or r['id'].startswith(original['id'] + '--')]
        assert all(r['sourceGroup'] == original['sourceGroup'] and r['split'] == original['split']
                   and r['events'] == original['events'] and r.get('crop') == original.get('crop') for r in rows)
    crop = next(r for r in records if r['id'] == 'grapple-crop--h480-crf23')
    normal = next(r for r in records if r['id'] == 'grapple--h480-crf23')
    assert crop['path'] == normal['path'] and crop['sha256'] == normal['sha256']
    assert next(p for p in receipt['parents'] if p['sha256'] == originals[2]['sha256'])['derivativeSkipReason'].startswith('portrait')
    assert all(p['sensor'] == p['visiblePeople'] == 'unknown' for p in receipt['parents'])
    assert (output / 'receipt.complete.json').exists()
    assert all(c['status'] == 'verified' for c in receipt['commands'] if c['kind'] == 'encode')
    assert not list(output.glob('*.partial.mp4'))
    assert before == (manifest.read_bytes(), source.read_bytes(), portrait.read_bytes())
    with pytest.raises(FileExistsError):
        variants.run(manifest, variants.digest(manifest), output, ffmpeg, variants.FFMPEG_SHA256)


@pytest.mark.parametrize('damage', ['encoder', 'timeout', 'drop', 'shift', 'opencv-shift'])
def test_failure_has_explicit_receipt_and_never_publishes_corpus(tmp_path, monkeypatch, damage):
    manifest, _, portrait, ffmpeg, output, _ = staged(tmp_path, monkeypatch)
    mock_media(monkeypatch, portrait, damage=damage)
    with pytest.raises((ValueError, RuntimeError, subprocess.TimeoutExpired)):
        variants.run(manifest, variants.digest(manifest), output, ffmpeg, variants.FFMPEG_SHA256)
    assert not (output / 'corpus.json').exists()
    assert not (output / 'receipt.complete.json').exists()
    failed = json.loads((output / 'receipt.failed.json').read_text())
    assert failed['status'] == 'failed' and failed['eligibleForComparison'] is False
    assert failed['outputManifest'] is None
    assert not [p for p in output.glob('*.mp4') if not p.name.endswith('.partial.mp4')]


def test_completion_write_failure_demotes_media_and_manifest(tmp_path, monkeypatch):
    manifest, _, portrait, ffmpeg, output, _ = staged(tmp_path, monkeypatch)
    mock_media(monkeypatch, portrait)
    publish = variants.publish_json

    def fail_complete(path, value):
        if path.name == 'receipt.complete.json':
            raise OSError('completion storage failed')
        return publish(path, value)

    monkeypatch.setattr(variants, 'publish_json', fail_complete)
    with pytest.raises(OSError, match='completion storage'):
        variants.run(manifest, variants.digest(manifest), output, ffmpeg, variants.FFMPEG_SHA256)
    assert not (output / 'corpus.json').exists()
    assert len(list(output.glob('*.partial.mp4'))) == 2
    assert json.loads((output / 'receipt.failed.json').read_text())['status'] == 'failed'


def test_budget_failure_and_exclusive_receipt(tmp_path, monkeypatch):
    path = tmp_path / 'receipt.json'
    variants.publish_json(path, {'status': 'incomplete'})
    with pytest.raises(FileExistsError):
        variants.publish_json(path, {'status': 'complete'})
    assert json.loads(path.read_text())['status'] == 'incomplete'
    monkeypatch.setattr(variants, 'MAX_BYTES', 10)
    with pytest.raises(ValueError, match='budget'):
        variants.publish_json(tmp_path / 'other.json', {'tooMuch': 'metadata'})


def test_only_id_selects_source_once_and_rejects_unknown(tmp_path, monkeypatch):
    manifest, _, _, _, _, _ = staged(tmp_path, monkeypatch)
    records, parents = variants.load_inputs(manifest, variants.digest(manifest), ['grapple-crop'])
    assert [r['id'] for r in records] == ['grapple-crop'] and len(parents) == 1
    with pytest.raises(ValueError, match='Unknown'):
        variants.load_inputs(manifest, variants.digest(manifest), ['missing'])


def test_large_header_is_rejected_before_decoder_command(tmp_path, monkeypatch):
    calls = []

    def probe(args, timeout):
        calls.append(args)
        return 'Stream #0:0: Video: vp8, yuv420p, 3840x2160, 30 fps'

    monkeypatch.setattr(variants, 'run_command', probe)
    with pytest.raises(ValueError, match='bounded'):
        variants.inspect_media(tmp_path / 'ffmpeg.exe', tmp_path / 'input.webm', 2, [])
    assert len(calls) == 1 and '-vf' not in calls[0]


@pytest.mark.parametrize('mode', ['timeout', 'overflow', 'ok'])
def test_process_wrapper_has_timeout_log_bound_and_no_shell(monkeypatch, mode):
    observed = []

    class Process:
        def __init__(self):
            self.stdout = io.BytesIO(b'log output')
            self.killed = False

        def wait(self, timeout=None):
            if mode == 'timeout' and timeout is not None:
                raise subprocess.TimeoutExpired(['ffmpeg'], timeout)
            return 0

        def kill(self):
            self.killed = True

    process = Process()

    def start(args, **kwargs):
        observed.append((args, kwargs))
        return process

    monkeypatch.setattr(variants.subprocess, 'Popen', start)
    if mode == 'overflow':
        monkeypatch.setattr(variants, 'MAX_LOG_BYTES', 3)
        with pytest.raises(ValueError, match='bounded capture'):
            variants.run_command(['ffmpeg', '-n'], 2)
        assert process.killed
    elif mode == 'timeout':
        with pytest.raises(subprocess.TimeoutExpired):
            variants.run_command(['ffmpeg', '-n'], 2)
        assert process.killed
    else:
        assert variants.run_command(['ffmpeg', '-n'], 2) == 'log output'
    assert observed[0][1]['shell'] is False
    assert observed[0][1]['stdin'] == subprocess.DEVNULL


def test_output_budget_discards_oversize_partial_but_retains_failure_receipt(tmp_path, monkeypatch):
    manifest, _, portrait, ffmpeg, output, _ = staged(tmp_path, monkeypatch)
    mock_media(monkeypatch, portrait)
    monkeypatch.setattr(variants, 'MAX_BYTES', 200_000)
    monkeypatch.setattr(variants, 'RESERVE_BYTES', 80_000)

    def oversized(args, timeout):
        Path(args[-1]).write_bytes(b'x' * 200_001)
        return 'encoded'

    monkeypatch.setattr(variants, 'run_command', oversized)
    with pytest.raises(ValueError, match='budget'):
        variants.run(manifest, variants.digest(manifest), output, ffmpeg, variants.FFMPEG_SHA256)
    assert variants.artifact_bytes(output) <= variants.MAX_BYTES
    failed = json.loads((output / 'receipt.failed.json').read_text())
    assert failed['status'] == 'failed' and failed['discardedForBudget']
    assert not list(output.glob('*.partial.mp4'))


def kick_clocks():
    # Synthetic regression clock matching parent-reported v1 endpoints/count/
    # median, not a claim that these constructed interior PTS are real footage.
    # Actual all-frame evidence is saved only by the independent real decoders.
    pts = tuple(round(i * 4588 / 110) for i in range(111))
    ffmpeg = clock(1280, 720, ticks=tuple(t + 3 for t in pts))
    independent = {'ptsMs': list(pts), 'frameCount': len(pts), 'width': 1280, 'height': 720}
    return ffmpeg, independent


def test_declared_duration_is_not_observed_frame_span_or_normal_tail():
    ffmpeg, independent = kick_clocks()
    assert ffmpeg.median_delta == Fraction(42, 1000)
    mapping = variants.verify_backend_clock(ffmpeg, independent)
    assert mapping['opencvEqualsFfmpegPlusOffsetMs'] == -3
    assert mapping['maxResidualMs'] == 0 and mapping['allFramesVerified']
    record = {'id': 'kick', 'durationMs': 4675, 'events': [{'startMs': 3100, 'endMs': 3800}]}
    evidence = variants.declared_coverage(record, independent)
    assert evidence['observedFrameSpanMs'] == 4588
    assert evidence['unobservedTailMs'] == 87
    assert evidence['unobservedTailIntervalMs'] == [4588, 4675]
    assert evidence['declaredDurationMs'] == 4675
    assert record['events'] == [{'startMs': 3100, 'endMs': 3800}]


@pytest.mark.parametrize(('duration', 'events', 'message'), [
    (4587, [], 'before observed'), (5789, [], '1200 ms'),
    (4675, [{'startMs': 4500, 'endMs': 4590}], 'unknown coverage'),
    (4675, [{'startMs': 4600, 'endMs': 4675}], 'unknown coverage'),
])
def test_negative_large_or_annotated_unknown_tail_is_rejected(duration, events, message):
    _, independent = kick_clocks()
    with pytest.raises(ValueError, match=message):
        variants.declared_coverage({'id': 'kick', 'durationMs': duration, 'events': events}, independent)


def test_declared_tail_gap_uses_runner_gap_bound_not_arbitrary_frame_tolerance():
    _, independent = kick_clocks()
    assert variants.declared_coverage({'id': 'kick', 'durationMs': 5788, 'events': []},
                                      independent)['unobservedTailMs'] == 1200


def test_backend_mapping_checks_every_frame_not_only_endpoints():
    ffmpeg, independent = kick_clocks()
    independent['ptsMs'][55] += 2
    with pytest.raises(ValueError, match='not constant'):
        variants.verify_backend_clock(ffmpeg, independent)


def test_runner_pair_cannot_silently_rebase_events():
    _, source = kick_clocks()
    output = deepcopy(source)
    assert variants.verify_runner_pair(source, output)['allFramesVerified']
    output['ptsMs'] = [v + 3 for v in output['ptsMs']]
    with pytest.raises(ValueError, match='unchanged events'):
        variants.verify_runner_pair(source, output)


def test_opencv_worker_uses_sequential_pts_no_fps_and_releases(tmp_path, monkeypatch):
    import cv2

    monkeypatch.setattr(variants, 'REPOSITORY', tmp_path)
    path = tmp_path / 'source.webm'
    path.write_bytes(b'trusted mock video')
    requested, threads = [], []

    class Capture:
        index = -1
        released = False

        def isOpened(self):
            return True

        def getBackendName(self):
            return 'FFMPEG'

        def read(self):
            self.index += 1
            return (True, SimpleNamespace(shape=(720, 1280, 3))) if self.index < 3 else (False, None)

        def get(self, key):
            assert key == cv2.CAP_PROP_POS_MSEC  # Nominal FPS must never be requested.
            return [0, 42, 83][self.index]

        def release(self):
            self.released = True

    capture = Capture()

    def open_capture(*args):
        requested.append(args)
        return capture

    monkeypatch.setattr(cv2, 'VideoCapture', open_capture)
    monkeypatch.setattr(cv2, 'setNumThreads', threads.append)
    evidence = variants.opencv_clock_worker(path, variants.digest(path))
    assert evidence['ptsMs'] == [0, 42, 83] and capture.released
    assert threads == [1]
    assert requested[0][1:] == (cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 2,
                                               cv2.CAP_PROP_HW_ACCELERATION, cv2.VIDEO_ACCELERATION_NONE])


def test_unknown_sar_is_preserved_without_invalidating_clock_or_inventing_square_pixels():
    # FFmpeg 7.1 showinfo semantics: AVFrame SAR 0/1 is unknown/unspecified.
    log = showinfo(tuple(2048 * i for i in range(65)), size='720x1280').replace('sar:1/1', 'sar:0/1')
    log = log.replace('time_base: 1/1000', 'time_base: 1/10240')
    decoded = variants.parse_showinfo(log)
    assert decoded.sar == 0 and len(decoded.ticks) == 65
    evidence = variants.clock_evidence(decoded)
    assert evidence['sampleAspectRatio'] == '0/1'
    assert evidence['sampleAspectRatioStatus'] == 'unknown-unspecified'
    assert evidence['displayAspectRatio'] is None
    independent = {'ptsMs': [float(t * 1000) for t in decoded.pts],
                   'frameCount': len(decoded.ticks), 'width': 720, 'height': 1280}
    assert variants.verify_backend_clock(decoded, independent)['allFramesVerified']
    assert variants.verify_runner_pair(independent, independent)['allFramesVerified']


@pytest.mark.parametrize('sar', ['-1/1', '1/-1', '-1/-1', '0/0', '1/0'])
def test_negative_or_zero_denominator_sar_is_not_reinterpreted_as_unknown(sar):
    with pytest.raises(ValueError, match='decoder SAR'):
        variants.parse_showinfo(showinfo().replace('sar:1/1', 'sar:' + sar))


def test_unknown_sar_cannot_be_encoded_or_asserted_as_aspect_preserved(tmp_path):
    source = clock(sar=Fraction(0))
    with pytest.raises(ValueError, match='Unspecified source SAR'):
        variants.encoding_args(tmp_path/'ffmpeg.exe', tmp_path/'source.webm', tmp_path/'output.mp4',
                               source, 480, 23, 1_000_000)
    with pytest.raises(ValueError, match='Unspecified source/output SAR'):
        variants.verify_pair(source, clock(694, 480), (694, 480))
    with pytest.raises(ValueError, match='Unspecified source/output SAR'):
        variants.verify_pair(clock(), clock(694, 480, sar=Fraction(0)), (694, 480))
    with pytest.raises(ValueError, match='SAR'):
        variants.validate_clock(clock(sar=Fraction(-1)))


def test_unknown_sar_portrait_is_admissible_as_original_reference(tmp_path, monkeypatch):
    manifest, _, portrait, ffmpeg, output, _ = staged(tmp_path, monkeypatch)
    calls, _ = mock_media(monkeypatch, portrait, portrait_sar=Fraction(0))
    result = variants.run(manifest, variants.digest(manifest), output, ffmpeg, variants.FFMPEG_SHA256)
    assert result['status'] == 'complete' and len(calls) == 2
    parent = next(p for p in result['parents'] if p['path'] == str(portrait))
    assert parent['derivativeSkipReason'].startswith('portrait')
    assert parent['ptsEvidence']['sampleAspectRatio'] == '0/1'
    rows = json.loads((output/'corpus.json').read_text())
    original = next(r for r in rows if r['id'] == 'exercise')
    assert original['qualityVariant']['sampleAspectRatioStatus'] == 'unknown-unspecified'
    assert original['qualityVariant']['sampleAspectRatio'] == '0/1'
    assert not any(r['id'].startswith('exercise--') for r in rows)


def test_unknown_sar_landscape_skips_requested_tiers_with_explicit_evidence(tmp_path, monkeypatch):
    manifest, _, portrait, ffmpeg, output, _ = staged(tmp_path, monkeypatch)
    calls, _ = mock_media(monkeypatch, portrait, source_sar=Fraction(0))
    result = variants.run(manifest, variants.digest(manifest), output, ffmpeg, variants.FFMPEG_SHA256)
    assert result['status'] == 'complete' and not calls and result['generatedMedia'] == 0
    parent = next(p for p in result['parents'] if p['path'] != str(portrait))
    assert parent['requestedDerivativeHeights'] == [480]
    assert parent['generatedDerivativeHeights'] == []
    assert parent['skippedDerivativeHeights'] == [480]
    assert 'unspecified source SAR (0/1)' in parent['derivativeSkipReason']
    assert parent['ptsEvidence']['displayAspectRatio'] is None
    assert len(json.loads((output/'corpus.json').read_text())) == 3
