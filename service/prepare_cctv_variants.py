"""Prepare bounded CPU-only CCTV sensitivity variants; never run a model."""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import threading
from typing import Any


SERVICE = Path(__file__).resolve().parent
REPOSITORY = SERVICE.parent
RUNS = SERVICE / 'research' / 'runs'
FFMPEG_SHA256 = '2ce797a0f88d7f067180338fb227f7b1928ea727bd9a4d7a1d022f7c52af71a3'
MAX_BYTES = 200_000_000
RESERVE_BYTES = 8_000_000
MAX_LOG_BYTES = 2_000_000
MAX_FRAMES = 2000
MAX_SECONDS = 60
MAX_GAP = Fraction(6, 5)
TIMESCALE = 1_000_000
TOLERANCE = Fraction(1, 1000)


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False,
                                     separators=(',', ':')).encode()).hexdigest()


def finite_number(value: Any) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def relative_path(path: Path, directory: Path) -> str:
    return Path(os.path.relpath(path, directory)).as_posix()


def owned_destination(path: Path) -> Path:
    """Only new directories below the fixed ignored runs root may be created."""
    allowed = RUNS.absolute()
    candidate = path.absolute()
    if not candidate.is_relative_to(allowed) or candidate == allowed:
        raise ValueError('Output must be a new child directory under service/research/runs')
    for item in (candidate, *candidate.parents):
        if item.is_symlink():
            raise ValueError('Symlink output paths are not allowed')
        if item == allowed:
            break
    resolved = candidate.resolve()
    if not resolved.is_relative_to(allowed.resolve()) or resolved == allowed.resolve():
        raise ValueError('Output path escapes runs root')
    if candidate.exists():
        raise FileExistsError(f'Output already exists: {candidate}')
    return resolved


def load_inputs(manifest: Path, expected_hash: str, only_ids: list[str] | None = None
                ) -> tuple[list[dict], dict[str, dict]]:
    from evaluate import validate_manifest

    manifest = manifest.resolve(strict=True)
    if not manifest.is_relative_to(REPOSITORY.resolve()):
        raise ValueError('Input manifest must be inside repository')
    if not re.fullmatch(r'[0-9a-f]{64}', expected_hash) or digest(manifest) != expected_hash:
        raise ValueError('Manifest checksum mismatch')
    records = json.loads(manifest.read_text(encoding='utf-8'))
    if not isinstance(records, list) or not 1 <= len(records) <= 64:
        raise ValueError('Expected 1 to 64 diagnostic records')
    validate_manifest(records)
    parents: dict[str, dict] = {}
    for record in records:
        if not isinstance(record['id'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', record['id']):
            raise ValueError('Unsafe recording ID')
        if not isinstance(record['sourceGroup'], str) or not record['sourceGroup']:
            raise ValueError('Missing source group')
        if not finite_number(record['durationMs']) or not 0 < record['durationMs'] <= MAX_SECONDS * 1000:
            raise ValueError('Invalid or excessive declared duration')
        for event in record['events']:
            if not all(finite_number(event[key]) for key in ('startMs', 'endMs')):
                raise ValueError('Non-finite event time')
        crop = record.get('crop')
        if crop is not None:
            if (not isinstance(crop, list) or len(crop) != 4
                    or not all(finite_number(x) for x in crop)
                    or not 0 <= crop[0] < crop[2] <= 1
                    or not 0 <= crop[1] < crop[3] <= 1):
                raise ValueError('Crop must use valid normalized source coordinates')
        raw = record['path']
        if not isinstance(raw, str) or Path(raw).is_absolute() or ':' in raw or raw.startswith(('\\', '//')):
            raise ValueError('Source path must be a local relative path')
        source = (manifest.parent / raw).resolve(strict=True)
        if not source.is_relative_to(REPOSITORY.resolve()) or not source.is_file():
            raise ValueError('Source path escapes repository or is not a file')
        sha = record['sha256']
        if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{64}', sha) or digest(source) != sha:
            raise ValueError(f'Source checksum mismatch: {record["id"]}')
        if sha in parents:
            if (parents[sha]['sourceGroup'], parents[sha]['split']) != (record['sourceGroup'], record['split']):
                raise ValueError('Identical source bytes have contradictory lineage/split')
        else:
            parents[sha] = {'path': source, 'sha256': sha, 'sourceGroup': record['sourceGroup'],
                            'split': record['split']}
    if only_ids:
        if len(set(only_ids)) != len(only_ids) or set(only_ids) - {r['id'] for r in records}:
            raise ValueError('Unknown or duplicate --only-id')
        records = [r for r in records if r['id'] in only_ids]
        parents = {sha: row for sha, row in parents.items() if sha in {r['sha256'] for r in records}}
    if len(parents) > 16:
        raise ValueError('At most 16 unique parents per bounded run')
    return records, parents


def run_command(args: list[str], timeout: float) -> str:
    """No shell, no stdin; cap combined diagnostic output even on bad inputs."""
    process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, shell=False)
    collected = bytearray()
    overflow = threading.Event()

    def read_log() -> None:
        assert process.stdout is not None
        while chunk := process.stdout.read(65536):
            if len(collected) + len(chunk) > MAX_LOG_BYTES:
                overflow.set()
                process.kill()
                break
            collected.extend(chunk)

    reader = threading.Thread(target=read_log, daemon=True)
    reader.start()
    try:
        code = process.wait(timeout=timeout)
    except BaseException:
        process.kill()
        process.wait()
        raise
    finally:
        reader.join(timeout=5)
        if process.stdout is not None:
            process.stdout.close()
    log = collected.decode('utf-8', errors='replace')
    if overflow.is_set() or reader.is_alive():
        raise ValueError('FFmpeg diagnostic log exceeded bounded capture')
    if code:
        raise RuntimeError(f'FFmpeg exited {code}: {log[-3000:]}')
    return log


def checked_ffmpeg(path: Path, expected_hash: str, timeout: float) -> tuple[Path, str]:
    path = path.resolve(strict=True)
    if expected_hash != FFMPEG_SHA256 or digest(path) != FFMPEG_SHA256:
        raise ValueError('FFmpeg checksum does not match the approved pinned binary')
    version = run_command([str(path), '-nostdin', '-version'], timeout)
    if not version.startswith('ffmpeg version 7.1'):
        raise ValueError('Expected pinned FFmpeg 7.1')
    encoders = run_command([str(path), '-nostdin', '-hide_banner', '-encoders'], timeout)
    if not re.search(r'\blibx264\b', encoders):
        raise ValueError('Pinned FFmpeg does not expose libx264')
    return path, version


def base_args(ffmpeg: Path) -> list[str]:
    return [str(ffmpeg), '-nostdin', '-hide_banner', '-nostats', '-loglevel', 'info',
            '-n', '-xerror', '-copyts', '-filter_threads', '1', '-filter_complex_threads', '1',
            '-hwaccel', 'none', '-threads', '2', '-noautorotate']


def input_args(ffmpeg: Path, path: Path) -> list[str]:
    containers = {'.webm': 'matroska', '.mkv': 'matroska', '.mp4': 'mov',
                  '.mov': 'mov', '.avi': 'avi'}
    if path.suffix.lower() not in containers:
        raise ValueError('Unsupported input video container')
    return base_args(ffmpeg) + ['-probesize', '5000000', '-analyzeduration', '5000000',
                               '-max_pixels', str(1920 * 1080), '-err_detect', 'explode',
                               '-protocol_whitelist', 'file,pipe', '-f', containers[path.suffix.lower()],
                               '-i', str(path), '-map', '0:v:0', '-an', '-sn', '-dn']


def dimensions_allowed(width: int, height: int) -> None:
    if width < 2 or height < 2:
        raise ValueError('Invalid dimensions')
    if ((width >= height and (width > 1920 or height > 1080))
            or (width < height and (width > 1080 or height > 1920))):
        raise ValueError('Source exceeds bounded 1080 landscape / portrait dimensions')


def parse_header(log: str) -> dict:
    line = next((x for x in log.splitlines() if re.search(r'Stream #0:\d+.*Video:', x)), '')
    codec = re.search(r'Video:\s*([\w]+)', line)
    size = re.search(r'(?<!\w)(\d{1,5})x(\d{1,5})(?=[\s,\[])', line)
    if not codec or not size:
        raise ValueError('No bounded video-stream metadata')
    width, height = map(int, size.groups())
    dimensions_allowed(width, height)
    rotation = re.search(r'(?:rotation of\s+|rotate\s*:\s*)([-\d.]+)', log)
    if rotation and float(rotation[1]) % 360:
        raise ValueError('Rotated source not supported in initial matrix')
    return {'codec': codec[1], 'width': width, 'height': height,
            'rotationDegrees': 0, 'headerLine': line.strip(),
            'nominalRatePolicy': 'Header rate is untrusted and never used for timing or GOP'}


@dataclass(frozen=True)
class Clock:
    ticks: tuple[int, ...]
    time_base: Fraction
    width: int
    height: int
    sar: Fraction
    pixel_format: str
    keyframes: tuple[int, ...] = ()

    @property
    def pts(self) -> tuple[Fraction, ...]:
        return tuple(t * self.time_base for t in self.ticks)

    @property
    def median_delta(self) -> Fraction:
        return statistics.median(b - a for a, b in zip(self.pts, self.pts[1:]))


def validate_clock(clock: Clock) -> None:
    dimensions_allowed(clock.width, clock.height)
    if not 2 <= len(clock.ticks) <= MAX_FRAMES:
        raise ValueError('Decoded frame count outside 2..2000; possible truncation')
    if (not isinstance(clock.time_base, Fraction) or clock.time_base <= 0
            or not isinstance(clock.sar, Fraction) or clock.sar < 0
            or any(type(t) is not int for t in clock.ticks)):
        raise ValueError('Invalid decoder time base, SAR or integer PTS')
    pts = clock.pts
    if pts[0] < 0 or pts[-1] > MAX_SECONDS:
        raise ValueError('PTS outside bounded 0..60 source seconds')
    for a, b in zip(pts, pts[1:]):
        if b <= a:
            raise ValueError('PTS must be finite and strictly increasing')
        if b - a > MAX_GAP:
            raise ValueError('Decoder PTS gap exceeds 1200 ms')
    if pts[-1] - pts[0] + clock.median_delta > MAX_SECONDS + TOLERANCE:
        raise ValueError('Decoded duration exceeds 60 seconds')


def parse_showinfo(log: str) -> Clock:
    time_bases = re.findall(r'config in time_base:\s*(\d+/\d+)', log)
    if not time_bases or len(set(time_bases)) != 1:
        raise ValueError('Missing or changing decoder time base')
    ticks, keys = [], []
    geometry = set()
    for line in log.splitlines():
        if 'showinfo' not in line or not re.search(r'\bn:\s*\d+', line):
            continue
        sample = re.search(r'\bn:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:', line)
        size = re.search(r'\bs:(\d+)x(\d+)', line)
        sar = re.search(r'\bsar:(-?\d+)/(-?\d+)', line)
        pixel_format = re.search(r'\bfmt:(\S+)', line)
        key = re.search(r'\biskey:(\d)', line)
        if not all((sample, size, sar, pixel_format, key)):
            raise ValueError('Incomplete decoder frame metadata')
        if int(sample[1]) != len(ticks):
            raise ValueError('Missing or reordered decoded frame number')
        if int(sar[1]) < 0 or int(sar[2]) <= 0:
            raise ValueError('Invalid negative or zero-denominator decoder SAR')
        ticks.append(int(sample[2]))
        geometry.add((*map(int, size.groups()), Fraction(int(sar[1]), int(sar[2])), pixel_format[1]))
        if key[1] == '1':
            keys.append(len(ticks) - 1)
    if len(geometry) != 1:
        raise ValueError('Missing or changing decoded dimensions/SAR/pixel format')
    width, height, sar, pixel_format = geometry.pop()
    clock = Clock(tuple(ticks), Fraction(time_bases[0]), width, height, sar,
                  pixel_format, tuple(keys))
    validate_clock(clock)
    return clock


def clock_evidence(clock: Clock) -> dict:
    return {'timeBase': str(clock.time_base), 'ptsTicks': list(clock.ticks),
            'frameCount': len(clock.ticks), 'width': clock.width, 'height': clock.height,
            'sampleAspectRatio': '0/1' if clock.sar == 0 else str(clock.sar),
            'sampleAspectRatioStatus': 'unknown-unspecified' if clock.sar == 0 else 'specified',
            'displayAspectRatio': None if clock.sar == 0 else str(Fraction(clock.width, clock.height) * clock.sar),
            'pixelFormat': clock.pixel_format,
            'medianDeltaSeconds': str(clock.median_delta),
            'measuredMedianFps': str(1 / clock.median_delta),
            'keyframeIndices': list(clock.keyframes),
            'keyframePtsSeconds': [str(clock.pts[i]) for i in clock.keyframes],
            'keyframeIntervalsSeconds': [str(clock.pts[b] - clock.pts[a])
                                         for a, b in zip(clock.keyframes, clock.keyframes[1:])]}


def opencv_clock_worker(path: Path, expected_sha256: str) -> dict:
    """Independent runner-backend decode; invoked in a timeout-bounded child."""
    import cv2

    path = path.resolve(strict=True)
    if not path.is_relative_to(REPOSITORY.resolve()) or digest(path) != expected_sha256:
        raise ValueError('OpenCV worker source path/checksum mismatch')
    cv2.setNumThreads(1)
    capture = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG,
                               [cv2.CAP_PROP_N_THREADS, 2, cv2.CAP_PROP_HW_ACCELERATION,
                                cv2.VIDEO_ACCELERATION_NONE])
    pts, dimensions = [], set()
    try:
        if not capture.isOpened():
            raise ValueError('Independent OpenCV decoder could not open media')
        backend = capture.getBackendName()
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            height, width = frame.shape[:2]
            dimensions_allowed(width, height)
            dimensions.add((width, height))
            pts.append(capture.get(cv2.CAP_PROP_POS_MSEC))
            if len(pts) > MAX_FRAMES:
                raise ValueError('OpenCV decoded frame limit exceeded')
        if len(dimensions) != 1:
            raise ValueError('OpenCV dimensions missing or changed')
        width, height = dimensions.pop()
        evidence = {'ptsMs': pts, 'frameCount': len(pts), 'width': width, 'height': height,
                    'backend': backend, 'opencvVersion': cv2.__version__,
                    'buildInformationSha256': hashlib.sha256(cv2.getBuildInformation().encode()).hexdigest(),
                    'threads': 2, 'opencvThreads': 1, 'hardwareAcceleration': False,
                    'clockSource': 'CAP_PROP_POS_MSEC after each successful sequential read; no FPS fallback'}
        opencv_pts(evidence)
        return evidence
    finally:
        capture.release()


def opencv_pts(evidence: dict) -> tuple[Fraction, ...]:
    values = evidence['ptsMs']
    if (not isinstance(values, list) or not 2 <= len(values) <= MAX_FRAMES
            or evidence['frameCount'] != len(values) or not all(finite_number(v) for v in values)):
        raise ValueError('Invalid independent OpenCV frame clock')
    pts = tuple(Fraction(str(v)) / 1000 for v in values)
    if pts[0] < 0 or pts[-1] > MAX_SECONDS:
        raise ValueError('OpenCV PTS outside bounded source seconds')
    for a, b in zip(pts, pts[1:]):
        if b <= a or b - a > MAX_GAP:
            raise ValueError('Invalid independent OpenCV PTS order/gap')
    return pts


def inspect_opencv(path: Path, expected_sha256: str, timeout: float, commands: list[dict]) -> dict:
    args = [sys.executable, str(Path(__file__).resolve()), '--opencv-clock-worker', str(path),
            '--worker-sha256', expected_sha256]
    operation = {'kind': 'independent-opencv-pts', 'args': args, 'status': 'started'}
    commands.append(operation)
    log = run_command(args, timeout)
    evidence = json.loads(log)
    opencv_pts(evidence)
    operation.update(status='decoded', logSha256=hashlib.sha256(log.encode()).hexdigest())
    return evidence


def verify_backend_clock(clock: Clock, independent: dict) -> dict:
    """Prove cv_pts[i] = ff_pts[i] + constant, for all frames, within 1 ms."""
    pts = opencv_pts(independent)
    if len(pts) != len(clock.ticks) or (independent['width'], independent['height']) != (clock.width, clock.height):
        raise ValueError('Independent OpenCV count/dimensions disagree with FFmpeg')
    offset = pts[0] - clock.pts[0]
    errors = [abs(cv - ff - offset) for cv, ff in zip(pts, clock.pts)]
    if max(errors) > TOLERANCE:
        raise ValueError('FFmpeg/OpenCV clock mapping is not constant across all frames')
    return {'kind': 'all-frame-constant-backend-offset', 'allFramesVerified': True,
            'opencvEqualsFfmpegPlusOffsetMs': float(offset * 1000),
            'offsetSecondsExact': str(offset), 'maxResidualMs': float(max(errors) * 1000),
            'toleranceMs': 1, 'eventsPolicy': 'events stay in existing OpenCV runner source-time coordinates'}


def verify_runner_pair(source: dict, output: dict) -> dict:
    source_pts, output_pts = opencv_pts(source), opencv_pts(output)
    if len(source_pts) != len(output_pts):
        raise ValueError('Independent runner frame count changed')
    error = max(abs(a - b) for a, b in zip(source_pts, output_pts))
    if error > TOLERANCE:
        raise ValueError('Source/output OpenCV runner clocks differ; unchanged events cannot be paired')
    return {'kind': 'all-frame-opencv-runner-identity', 'allFramesVerified': True,
            'maxAbsoluteErrorMs': float(error * 1000), 'toleranceMs': 1,
            'eventsPolicy': 'retain original event times; no relabeling or offset guessed'}


def declared_coverage(record: dict, independent: dict) -> dict:
    """Container extent is not observed coverage or evidence of a normal tail."""
    pts = opencv_pts(independent)
    declared_end = Fraction(str(record['durationMs'])) / 1000
    tail = declared_end - pts[-1]
    if tail < 0:
        raise ValueError('Declared duration ends before observed content')
    if tail > MAX_GAP or pts[0] > MAX_GAP:
        raise ValueError('Declared unobserved head/tail gap exceeds 1200 ms')
    for event in record['events']:
        if (Fraction(str(event['startMs'])) / 1000 < pts[0]
                or Fraction(str(event['endMs'])) / 1000 > pts[-1]):
            raise ValueError('Annotated event extends beyond observed content into unknown coverage')
    return {'id': record['id'], 'coordinateSystem': 'original OpenCV runner PTS milliseconds',
            'declaredDurationMs': record['durationMs'], 'observedFirstPtsMs': float(pts[0] * 1000),
            'observedLastPtsMs': float(pts[-1] * 1000),
            'observedFrameSpanMs': float((pts[-1] - pts[0]) * 1000),
            'unobservedHeadMs': float(pts[0] * 1000), 'unobservedTailMs': float(tail * 1000),
            'unobservedTailIntervalMs': [float(pts[-1] * 1000), record['durationMs']],
            'maxDeclaredGapMs': 1200,
            'coveragePolicy': 'PTS endpoints only; no inferred last-frame duration, padding, normal-tail label or exposure'}


def inspect_media(ffmpeg: Path, path: Path, timeout: float, commands: list[dict]
                  ) -> tuple[dict, Clock]:
    probe = input_args(ffmpeg, path) + ['-c:v', 'copy', '-frames:v', '0', '-f', 'null', '-']
    log = run_command(probe, timeout)
    commands.append({'kind': 'header', 'args': probe, 'logSha256': hashlib.sha256(log.encode()).hexdigest()})
    header = parse_header(log)  # Reject large coded dimensions before decoding.
    args = input_args(ffmpeg, path) + ['-vf', 'showinfo', '-frames:v', str(MAX_FRAMES + 1),
                                     '-threads', '2', '-fps_mode', 'passthrough', '-f', 'null', '-']
    log = run_command(args, timeout)
    commands.append({'kind': 'decode-pts', 'args': args, 'logSha256': hashlib.sha256(log.encode()).hexdigest()})
    clock = parse_showinfo(log)
    if (header['width'], header['height']) != (clock.width, clock.height):
        raise ValueError('Header and actual decoder dimensions disagree')
    return header, clock


def target_dimensions(width: int, height: int, target_height: int) -> tuple[int, int]:
    if (type(target_height) is not int or target_height % 2 or target_height < 2
            or target_height >= height):
        raise ValueError('Target must downscale to an even height; no upscaling or same-size encode')
    scaled_width = Fraction(width * target_height, height)
    even_width = 2 * math.floor(scaled_width / 2 + Fraction(1, 2))
    if even_width < 2 or even_width > width:
        raise ValueError('Invalid or upscaled target width')
    return even_width, target_height


def matrix_heights(width: int, height: int) -> tuple[list[int], str | None]:
    if height > width:
        return [], 'portrait derivatives skipped in initial landscape matrix'
    if height == 1080:
        return [720, 480], None
    if height in (720, 608):
        return [480], None
    return [], 'native height outside initial 1080/720/608 landscape matrix'


def encoding_args(ffmpeg: Path, source: Path, output: Path, source_clock: Clock,
                  height: int, crf: int, byte_limit: int) -> tuple[list[str], dict]:
    if output.exists():
        raise FileExistsError(f'Encoder output already exists: {output}')
    validate_clock(source_clock)
    if source_clock.sar == 0:
        raise ValueError('Unspecified source SAR; cannot verify derivative display aspect')
    if crf not in (23, 35) or byte_limit < 100_000:
        raise ValueError('Invalid CRF or remaining artifact budget')
    width, height = target_dimensions(source_clock.width, source_clock.height, height)
    gop = max(1, round(Fraction(2) / source_clock.median_delta))
    transform = {'kind': 'synthetic-resolution-compression', 'width': width, 'height': height,
                 'scale': 'area', 'aspectPolicy': 'even rounded dimensions; scale retains display aspect via SAR',
                 'codec': 'h264', 'encoder': 'libx264', 'crf': crf, 'preset': 'medium',
                 'pixelFormat': 'yuv420p', 'gopFrames': gop, 'gopTargetSeconds': 2,
                 'gopBasis': 'median consecutive decoded PTS differences, not nominal FPS',
                 'sceneCutThreshold': 0, 'fpsMode': 'passthrough',
                 'encoderTimeBase': f'1/{TIMESCALE}', 'mp4Timescale': TIMESCALE,
                 'audio': 'omitted', 'rotation': 'autorotate disabled', 'threads': 2}
    args = input_args(ffmpeg, source) + [
        '-vf', f'scale={width}:{height}:flags=area', '-c:v', 'libx264',
        '-threads', '2', '-preset', 'medium', '-crf', str(crf), '-pix_fmt', 'yuv420p',
        '-g', str(gop), '-keyint_min', str(gop), '-sc_threshold', '0',
        '-fps_mode', 'passthrough', '-enc_time_base', f'1/{TIMESCALE}',
        '-video_track_timescale', str(TIMESCALE), '-avoid_negative_ts', 'disabled',
        '-use_editlist', '1', '-map_metadata', '-1', '-frames:v', str(MAX_FRAMES + 1),
        '-fs', str(byte_limit), '-f', 'mp4', str(output)]
    return args, transform


def verify_pair(source: Clock, output: Clock, expected_size: tuple[int, int]) -> dict:
    validate_clock(source)
    validate_clock(output)
    if len(source.ticks) != len(output.ticks):
        raise ValueError('Variant decoded frame count changed; no output promotion')
    if (output.width, output.height) != expected_size or output.pixel_format != 'yuv420p':
        raise ValueError('Variant dimensions or pixel format disagree with transform')
    if source.sar == 0 or output.sar == 0:
        raise ValueError('Unspecified source/output SAR; cannot claim display aspect preservation')
    source_aspect = Fraction(source.width, source.height) * source.sar
    output_aspect = Fraction(output.width, output.height) * output.sar
    if abs(source_aspect - output_aspect) > Fraction(1, 10000):
        raise ValueError('Variant display aspect ratio changed')
    errors = [abs(a - b) for a, b in zip(source.pts, output.pts)]
    if max(errors) > TOLERANCE:
        raise ValueError('Variant PTS mapping changed by more than 1 ms; no output promotion')
    return {'kind': 'identity-pts-within-tolerance', 'allFramesVerified': True,
            'toleranceMs': 1, 'maxAbsoluteErrorMs': float(max(errors) * 1000),
            'sourceToOutputOffsetMs': 0, 'eventsPolicy': 'source event times retained unchanged'}


def artifact_bytes(directory: Path) -> int:
    return sum(p.stat().st_size for p in directory.rglob('*') if p.is_file())


def publish_json(path: Path, value: Any) -> None:
    """Exclusive final name; an incomplete JSON can never be a completion marker."""
    data = (json.dumps(value, indent=2, allow_nan=False) + '\n').encode('utf-8')
    if len(data) > 2_000_000 or artifact_bytes(path.parent) + len(data) > MAX_BYTES:
        raise ValueError('Artifact/metadata budget exceeded')
    if path.exists():
        raise FileExistsError(f'JSON output already exists: {path}')
    pending = path.with_name(path.name + '.pending')
    with pending.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.link(pending, path)  # Atomic, fails if target exists on Windows and POSIX.
    finally:
        # After a successful link the target is complete. Cleanup failure must
        # not turn a published completion marker into a failed run.
        try:
            pending.unlink()
        except OSError:
            pass


def derived_records(records: list[dict], parents: dict[str, dict], variants: list[dict],
                    directory: Path, parent_evidence: list[dict]) -> list[dict]:
    result = []
    for source in records:
        original = deepcopy(source)
        original['path'] = relative_path(parents[source['sha256']]['path'], directory)
        original['qualityVariant'] = {'kind': 'original-reference', 'developmentOnly': True,
                                      'independentEvidence': False, 'parentSha256': source['sha256']}
        evidence = next(p for p in parent_evidence if p['sha256'] == source['sha256'])
        coverage = next(c for c in evidence['declaredCoverage'] if c['id'] == source['id'])
        original['qualityVariant'].update(observedCoverage=coverage,
                                          backendClockMapping=evidence['backendClockMapping'],
                                          sampleAspectRatio=evidence['ptsEvidence']['sampleAspectRatio'],
                                          sampleAspectRatioStatus=evidence['ptsEvidence']['sampleAspectRatioStatus'])
        result.append(original)
        for variant in variants:
            if variant['parentSha256'] != source['sha256']:
                continue
            row = deepcopy(source)
            row['id'] = f'{source["id"]}--h{variant["transform"]["height"]}-crf{variant["transform"]["crf"]}'
            row['path'] = variant['file']
            row['sha256'] = variant['sha256']
            row['qualityVariant'] = {'kind': 'synthetic-resolution-compression',
                                     'parentId': source['id'], 'parentSha256': source['sha256'],
                                     'transformSha256': variant['transformSha256'],
                                     'developmentOnly': True, 'independentEvidence': False,
                                     'ptsMapping': variant['ptsMapping'],
                                     'runnerClockMapping': variant['runnerClockMapping'],
                                     'backendClockMapping': variant['backendClockMapping'],
                                     'observedCoverage': coverage}
            # Events, duration, split, sourceGroup, crop and source attribution stay unchanged.
            result.append(row)
    from evaluate import validate_manifest
    validate_manifest(result)
    return result


def run(manifest: Path, manifest_sha256: str, output: Path, ffmpeg: Path,
        ffmpeg_sha256: str, *, timeout: float = 120, only_ids: list[str] | None = None) -> dict:
    if not finite_number(timeout) or not 1 <= timeout <= 300:
        raise ValueError('Timeout must be between 1 and 300 seconds per subprocess')
    destination = owned_destination(output)
    records, parents = load_inputs(manifest, manifest_sha256, only_ids)
    ffmpeg, version = checked_ffmpeg(ffmpeg, ffmpeg_sha256, timeout)
    destination.mkdir(parents=True, exist_ok=False)
    receipt: dict = {'schemaVersion': 1, 'status': 'incomplete',
                     'inputManifest': str(manifest.resolve()), 'inputManifestSha256': manifest_sha256,
                     'implementationSha256': digest(Path(__file__)), 'selectedIds': [r['id'] for r in records],
                     'ffmpeg': {'path': str(ffmpeg), 'sha256': ffmpeg_sha256, 'version': version,
                                'versionArgs': [str(ffmpeg), '-nostdin', '-version'],
                                'encoderCheckArgs': [str(ffmpeg), '-nostdin', '-hide_banner', '-encoders'],
                                'redistributed': False},
                     'limits': {'artifactBytes': MAX_BYTES, 'durationSeconds': MAX_SECONDS,
                                'decodedFramesPerMedia': MAX_FRAMES, 'threads': 2,
                                'timeoutPerCommandSeconds': timeout, 'hardwareAcceleration': False},
                     'evidenceBoundary': 'Development diagnostics only; derivatives/crops are not independent',
                     'parents': [], 'variants': [], 'commands': []}
    corpus = destination / 'corpus.json'
    try:
        publish_json(destination / 'receipt.started.json', receipt)
        for sha, parent in parents.items():
            path = parent['path']
            if digest(path) != sha:
                raise ValueError('Parent changed before inspection')
            header, clock = inspect_media(ffmpeg, path, timeout, receipt['commands'])
            heights, skipped = matrix_heights(clock.width, clock.height)
            requested_heights = list(heights)
            if heights and clock.sar == 0:
                heights = []
                skipped = 'unspecified source SAR (0/1); landscape derivatives skipped because display aspect is unknown'
            evidence = {'path': str(path), 'sha256': sha,
                                       'sourceGroup': parent['sourceGroup'], 'header': header,
                                       'ptsEvidence': clock_evidence(clock), 'derivativeSkipReason': skipped,
                                       'requestedDerivativeHeights': requested_heights,
                                       'generatedDerivativeHeights': list(heights),
                                       'skippedDerivativeHeights': [h for h in requested_heights if h not in heights],
                                       'sensor': 'unknown', 'illumination': 'unknown',
                                       'visiblePeople': 'unknown', 'occlusion': 'unknown', 'declaredCoverage': []}
            receipt['parents'].append(evidence)
            source_opencv = inspect_opencv(path, sha, timeout, receipt['commands'])
            evidence['opencvClock'] = source_opencv
            evidence['backendClockMapping'] = verify_backend_clock(clock, source_opencv)
            for record in (r for r in records if r['sha256'] == sha):
                evidence['declaredCoverage'].append(declared_coverage(record, source_opencv))
            for height in heights:
                for crf in (23, 35):
                    filename = f'{sha}-h{height}-crf{crf}.mp4'
                    partial = destination / f'{sha}-h{height}-crf{crf}.partial.mp4'
                    remaining = MAX_BYTES - RESERVE_BYTES - artifact_bytes(destination)
                    args, transform = encoding_args(ffmpeg, path, partial, clock, height, crf, remaining)
                    operation = {'kind': 'encode', 'args': args, 'status': 'started'}
                    receipt['commands'].append(operation)
                    log = run_command(args, timeout)
                    operation.update(status='encoded-not-yet-verified',
                                     logSha256=hashlib.sha256(log.encode()).hexdigest())
                    if artifact_bytes(destination) > MAX_BYTES - RESERVE_BYTES:
                        raise ValueError('Media exceeded artifact budget; no output promotion')
                    out_header, out_clock = inspect_media(ffmpeg, partial, timeout, receipt['commands'])
                    if out_header['codec'] != 'h264':
                        raise ValueError('Variant is not decoded H.264')
                    mapping = verify_pair(clock, out_clock, (transform['width'], transform['height']))
                    output_sha256 = digest(partial)
                    output_opencv = inspect_opencv(partial, output_sha256, timeout, receipt['commands'])
                    backend_mapping = verify_backend_clock(out_clock, output_opencv)
                    runner_mapping = verify_runner_pair(source_opencv, output_opencv)
                    operation['status'] = 'verified'
                    byte_count = partial.stat().st_size
                    if not byte_count:
                        raise ValueError('Empty encoded output')
                    receipt['variants'].append({'parentSha256': sha, 'sourceGroup': parent['sourceGroup'],
                                                'file': filename, 'partialFile': partial.name,
                                                'sha256': output_sha256, 'bytes': byte_count,
                                                'transform': transform, 'transformSha256': canonical_hash(transform),
                                                'encoderEvidence': [line for line in log.splitlines()
                                                                    if 'libx264' in line and any(token in line
                                                                        for token in ('264 -', 'profile ', 'using cpu'))],
                                                'ptsMapping': mapping, 'header': out_header,
                                                'opencvClock': output_opencv,
                                                'backendClockMapping': backend_mapping,
                                                'runnerClockMapping': runner_mapping,
                                                'ptsEvidence': clock_evidence(out_clock),
                                                'containerBitrateEstimateBps': float(byte_count * 8 /
                                                    (out_clock.pts[-1] - out_clock.pts[0] + out_clock.median_delta))})
        if digest(manifest.resolve()) != manifest_sha256 or any(digest(p['path']) != sha for sha, p in parents.items()):
            raise ValueError('Input bytes changed during run')
        output_records = derived_records(records, parents, receipt['variants'], destination, receipt['parents'])
        for variant in receipt['variants']:
            partial = destination / variant['partialFile']
            os.link(partial, destination / variant['file'])
            partial.unlink()
        publish_json(corpus, output_records)
        receipt.update(status='complete', outputManifest='corpus.json',
                       outputManifestSha256=digest(corpus), outputRecords=len(output_records),
                       uniqueParents=len(parents), generatedMedia=len(receipt['variants']))
        publish_json(destination / 'receipt.complete.json', receipt)
        return receipt
    except (Exception, KeyboardInterrupt) as error:
        # Only this fresh run's own corpus can be removed. No shared file is touched.
        if corpus.exists():
            corpus.unlink()
        for variant in receipt['variants']:
            final, partial = destination / variant['file'], destination / variant['partialFile']
            if final.exists() and not partial.exists():
                os.link(final, partial)
                final.unlink()
        discarded = []
        for partial in sorted(destination.glob('*.partial.mp4'), key=lambda p: p.stat().st_size, reverse=True):
            if artifact_bytes(destination) <= MAX_BYTES - RESERVE_BYTES:
                break
            discarded.append({'file': partial.name, 'bytes': partial.stat().st_size})
            partial.unlink()
        receipt['discardedForBudget'] = discarded
        receipt.update(status='failed', error=f'{type(error).__name__}: {error}',
                       outputManifest=None, eligibleForComparison=False)
        publish_json(destination / 'receipt.failed.json', receipt)
        raise


def main() -> None:
    if '--opencv-clock-worker' in sys.argv[1:]:
        worker = argparse.ArgumentParser(description='Internal bounded OpenCV clock decoder')
        worker.add_argument('--opencv-clock-worker', type=Path, required=True)
        worker.add_argument('--worker-sha256', required=True)
        args = worker.parse_args()
        print(json.dumps(opencv_clock_worker(args.opencv_clock_worker, args.worker_sha256), allow_nan=False))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--ffmpeg', required=True, type=Path)
    parser.add_argument('--ffmpeg-sha256', required=True)
    parser.add_argument('--timeout-seconds', type=float, default=120)
    parser.add_argument('--only-id', action='append', dest='only_ids')
    args = parser.parse_args()
    result = run(args.manifest, args.manifest_sha256, args.output_dir, args.ffmpeg,
                 args.ffmpeg_sha256, timeout=args.timeout_seconds, only_ids=args.only_ids)
    print(json.dumps({'status': result['status'], 'outputRecords': result['outputRecords'],
                      'generatedMedia': result['generatedMedia']}))


if __name__ == '__main__':
    main()
