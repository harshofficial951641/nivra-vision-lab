"""Offline, bounded observer sampling of checksum-pinned development recordings."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import re
import time
from time import perf_counter
import urllib.request

import cv2

from nivra.crowd_observer import COCO17, create_observer, validate_dimensions, validate_frame


SERVICE = Path(__file__).resolve().parent
REPOSITORY = SERVICE.parent
RUNS = SERVICE / 'research' / 'runs'
ORIGINAL_IDS = ('boxing', 'grappling', 'kick', 'squats')
ORIGINAL_SHA256 = dict(zip(ORIGINAL_IDS, (
    '2dd4c6269c120978630b1a1e1fd3819b53d75b02dd1b9a6e34a5e9e9de966430',
    '1004027ef030303bef37144da30363aff7bdacda585d76d58b837d6db0272064',
    '752181dd7417113744baf0337a0682fd10813575cb8d327057957a164246455f',
    'ea9151e447b301985d5d65666551ef863b369a2e0f3a71ddd58abef2e722f96a')))
MAX_SOURCE_BYTES = 200_000_000
DEMO_HEALTH = 'http://127.0.0.1:8765/api/v2/fight/health'


class DemoHealthGuard:
    """Read-only loopback cooperation; no model/device calls, fail closed."""

    def __init__(self, max_wait_seconds=30., *, fetch=None, clock=time.monotonic, sleep=time.sleep):
        if (isinstance(max_wait_seconds, bool) or not isinstance(max_wait_seconds, (int, float))
                or not math.isfinite(max_wait_seconds) or not 0 < max_wait_seconds <= 60):
            raise ValueError('Demo wait budget must be >0 and <=60 seconds')
        self.max_wait_seconds, self.clock, self.sleep = max_wait_seconds, clock, sleep
        self.fetch = fetch or self._fetch
        self.checks, self.wait_seconds = 0, 0.

    @staticmethod
    def _fetch():
        # Fixed loopback address only; do not route local health via environment proxies.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(DEMO_HEALTH, timeout=1) as response:
            data = response.read(16_385)
        if len(data) > 16_384:
            raise ValueError('Demo health body too large')
        return json.loads(data)

    def __call__(self):
        started = self.clock()
        while True:
            try:
                health = self.fetch()
            except Exception as error:
                raise RuntimeError('Demo health unavailable; refusing research work') from error
            self.checks += 1
            if (not isinstance(health, dict) or type(health.get('busy')) is not bool
                    or health.get('status') not in ('ready', 'loading')):
                raise RuntimeError('Demo health is invalid/not operational; refusing research work')
            if health['status'] == 'ready' and not health['busy']:
                self.wait_seconds += self.clock() - started
                return
            elapsed = self.clock() - started
            if elapsed >= self.max_wait_seconds:
                self.wait_seconds += elapsed
                raise RuntimeError('Demo remained busy/loading beyond research yield budget')
            self.sleep(min(.25, self.max_wait_seconds - elapsed))

    def summary(self):
        return {'endpoint': DEMO_HEALTH, 'checks': self.checks,
                'guardHostWallSeconds': self.wait_seconds,
                'maxWaitSecondsPerCheck': self.max_wait_seconds,
                'policy': 'ready and not busy before model load and every view; fail closed; cooperative, not a reservation'}


def digest(path: Path) -> str:
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def output_path(path: Path) -> Path:
    raw = Path(path)
    if '..' in raw.parts:
        raise ValueError('Output traversal is not allowed')
    candidate = raw.absolute() if raw.is_absolute() else (RUNS / raw).absolute()
    allowed = RUNS.absolute()
    if (candidate.suffix.lower() != '.json' or not candidate.is_relative_to(allowed)
            or candidate == allowed):
        raise ValueError('Output must be a new JSON file under service/research/runs')
    for parent in (candidate, *candidate.parents):
        if parent.is_symlink():
            raise ValueError('Symlink output paths are not allowed')
        if parent == SERVICE.absolute():
            break
    if not candidate.resolve().is_relative_to(SERVICE.resolve() / 'research' / 'runs'):
        raise ValueError('Output path escapes runs root')
    if candidate.exists():
        raise FileExistsError(f'Output already exists: {candidate}')
    return candidate


def load_corpus(path: Path, expected_sha256: str) -> list[dict]:
    path = Path(path).resolve(strict=True)
    if not path.is_relative_to(REPOSITORY.resolve()) or not re.fullmatch('[0-9a-f]{64}', expected_sha256):
        raise ValueError('Expected local repository corpus and SHA-256')
    if path.stat().st_size > 1_000_000 or digest(path) != expected_sha256:
        raise ValueError('Corpus checksum/size mismatch')
    rows = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(rows, list) or not 4 <= len(rows) <= 16:
        raise ValueError('Invalid development corpus')
    selected = []
    for identifier in ORIGINAL_IDS:
        matches = [row for row in rows if isinstance(row, dict) and row.get('id') == identifier]
        if len(matches) != 1 or matches[0].get('crop') is not None:
            raise ValueError('Expected exactly one uncropped original per development recording')
        row = matches[0]
        raw = row.get('path')
        if not isinstance(raw, str) or ':' in raw or raw.startswith(('\\', '//')) or Path(raw).is_absolute():
            raise ValueError('Recording path must be local and relative')
        source = (path.parent / raw).resolve(strict=True)
        sha = row.get('sha256', '')
        duration = row.get('durationMs')
        if (not source.is_file() or not source.is_relative_to(REPOSITORY.resolve())
                or source.stat().st_size > MAX_SOURCE_BYTES
                or not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha)
                or sha != ORIGINAL_SHA256[identifier]
                or digest(source) != sha):
            raise ValueError(f'Recording checksum/path/size mismatch: {identifier}')
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 0 < duration <= 60_000:
            raise ValueError('Invalid declared development duration')
        selected.append({**row, 'localPath': source})
    if len({r['sha256'] for r in selected}) != 4:
        raise ValueError('The four originals must have distinct bytes')
    return selected


def sample_pts_frames(path: Path, *, count: int, start_ms: float, interval_ms: float,
                      frame_limit: int = 1200, timeout_seconds: float = 20,
                      capture_factory=None):
    """Sequentially select first decoded PTS at/after each target; never use FPS."""
    if type(count) is not int or not 1 <= count <= 8 or type(frame_limit) is not int or not 1 <= frame_limit <= 2000:
        raise ValueError('Invalid sample/decode frame budget')
    for value in (start_ms, interval_ms, timeout_seconds):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError('Non-finite sampling budget')
    if not 0 <= start_ms <= 60_000 or not 100 <= interval_ms <= 10_000 or not 0 < timeout_seconds <= 30 or start_ms + (count - 1) * interval_ms > 60_000:
        raise ValueError('Sampling budget outside allowed bounds')
    cv2.setNumThreads(1)
    path = Path(path).resolve(strict=True)
    if not path.is_file() or path.suffix.lower() not in ('.webm', '.mp4'):
        raise ValueError('Expected a local MP4/WebM file, never a camera or network URL')
    factory = capture_factory or cv2.VideoCapture
    started = perf_counter()
    cap = factory(str(path), cv2.CAP_FFMPEG,
                  [cv2.CAP_PROP_N_THREADS, 1, cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 3000,
                   cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000])
    previous, selected = -math.inf, 0
    try:
        if not cap.isOpened():
            raise ValueError('Cannot open local recording')
        width, height = cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        if not math.isfinite(width) or not math.isfinite(height) or width != int(width) or height != int(height):
            raise ValueError('Invalid decoded geometry metadata')
        validate_dimensions(int(width), int(height))
        for index in range(frame_limit):
            if perf_counter() - started > timeout_seconds:
                raise ValueError('Decode wall-time budget exceeded')
            ok, frame = cap.read()
            if perf_counter() - started > timeout_seconds:
                raise ValueError('Decode wall-time budget exceeded')
            if not ok:
                break
            actual_width, actual_height = validate_frame(frame)
            if (actual_width, actual_height) != (int(width), int(height)):
                raise ValueError('Decoded dimensions changed')
            pts = cap.get(cv2.CAP_PROP_POS_MSEC)
            if not math.isfinite(pts) or pts < 0 or pts <= previous or pts > 60_000:
                raise ValueError('Invalid/non-increasing actual presentation timestamp')
            previous = pts
            target = start_ms + selected * interval_ms
            if pts >= target:
                selected += 1
                decode_elapsed = perf_counter() - started
                yield {'frameIndex': index, 'timestampMs': float(pts),
                       'targetTimestampMs': target, 'targetOvershootMs': float(pts - target),
                       'decodedFramesSoFar': index + 1}, frame
                # Reset decode-only clock after caller's observer work, which is not decode time.
                started = perf_counter() - decode_elapsed
                if selected == count:
                    return
        raise ValueError('Insufficient actual PTS samples within decode frame budget')
    finally:
        cap.release()


def run_research(*, corpus: Path, corpus_sha256: str, output: Path, device: str,
                 frames_per_recording: int = 2, start_ms: float = 0,
                 interval_ms: float = 1000, decode_frame_limit: int = 1200,
                 decode_timeout_seconds: float = 20, preload_torch_dlls: bool = False,
                 allow_cpu_operators: bool = False, profile_operators: bool = False,
                 demo_wait_seconds: float = 30, health_guard=None,
                 observer_factory=None, capture_factory=None) -> dict:
    # Reject bad bounds, paths, and all bad source hashes before loading a model.
    started = perf_counter()
    if device not in ('cpu', 'cuda'):
        raise ValueError('Explicit cpu or cuda required')
    if type(allow_cpu_operators) is not bool or type(profile_operators) is not bool or (allow_cpu_operators and device != 'cuda'):
        raise ValueError('Mixed operator policy requires explicit CUDA')
    profile_operators = profile_operators or allow_cpu_operators
    destination = output_path(output)
    if type(frames_per_recording) is not int or not 1 <= frames_per_recording <= 8:
        raise ValueError('Expected 1 to 8 frames per recording')
    if type(decode_frame_limit) is not int or not 1 <= decode_frame_limit <= 2000:
        raise ValueError('Invalid decode frame limit')
    for value in (start_ms, interval_ms, decode_timeout_seconds):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError('Invalid sampling values')
    if not 0 <= start_ms or not 100 <= interval_ms <= 10_000 or not 0 < decode_timeout_seconds <= 30:
        raise ValueError('Invalid sampling bounds')
    records = load_corpus(corpus, corpus_sha256)
    if any(start_ms + (frames_per_recording - 1) * interval_ms >= r['durationMs'] for r in records):
        raise ValueError('Requested sample targets exceed a recording duration')
    guard = health_guard if health_guard is not None else DemoHealthGuard(demo_wait_seconds)
    guard()  # Yield before model hash/load/session creation, not just before forward calls.
    profile_prefix = None
    if profile_operators:
        destination = output_path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination = output_path(destination)
        directory = destination.parent / (destination.stem + '.operators')
        if directory.exists() or directory.is_symlink():
            raise FileExistsError('Report-associated operator profile directory already exists')
        directory.mkdir(exist_ok=False)
        profile_prefix = directory / 'ort'
    observer = (observer_factory or create_observer)(
        device, preload_torch_dlls=preload_torch_dlls, allow_cpu_operators=allow_cpu_operators,
        profile_prefix=profile_prefix, yield_guard=guard)
    observer.yield_guard = guard
    try:
        results = []
        for record in records:
            frames = sample_pts_frames(record['localPath'], count=frames_per_recording,
                                       start_ms=start_ms, interval_ms=interval_ms,
                                       frame_limit=decode_frame_limit, timeout_seconds=decode_timeout_seconds,
                                       capture_factory=capture_factory)
            try:
                for selection, frame in frames:
                    if selection['timestampMs'] >= record['durationMs']:
                        raise ValueError('Selected actual PTS exceeds declared source duration')
                    result = observer.observe(frame, selection['timestampMs'])
                    results.append({'recordingId': record['id'], 'sourceSha256': record['sha256'],
                                    'sourceLicense': record.get('license'), 'source': record.get('source'),
                                    'selection': selection, **result})
            finally:
                frames.close()
    except Exception:
        # Flush any bounded-run trace, but never turn a failed run into a success report.
        try:
            observer.finish_profile()
        except Exception:
            pass
        raise
    profile_summary = observer.finish_profile()
    report = {'schemaVersion': 1, 'status': 'offline-research-observer-only',
              'corpusSha256': corpus_sha256, 'modelRuntime': observer.runtime,
              'modelMetadata': observer.metadata,
              'operatorProfile': profile_summary,
              'demoYield': guard.summary() if hasattr(guard, 'summary') else {'policy': 'injected health guard'},
              'jointLayout': {'name': 'COCO-17', 'orderedKeypoints': list(COCO17)},
              'observerPolicy': asdict(observer.policy),
              'policy': {'framesPerRecording': frames_per_recording, 'maxTotalSamples': 32,
                         'actualTotalSamples': len(results), 'viewsPerFrame': 5,
                         'startMs': start_ms, 'intervalMs': interval_ms,
                         'decodeFrameLimitPerRecording': decode_frame_limit,
                         'decodeWallTimeLimitSecondsPerRecording': decode_timeout_seconds,
                         'clock': 'strict decoded CAP_PROP_POS_MSEC; no nominal-FPS fallback',
                         'frameSelection': 'first decoded frame at/after target; one frame cannot fill two targets'},
              'limitations': ['Person detector observations are not visible-human recall or fight classification.',
                              'No tracking, identity, actor attribution, interaction scheduling or fight model is run.',
                              'These four development recordings are not a crowd/night/IR holdout.',
                              'Fixed five views are global plus four overlapping native-source crops, each resized to 640 input.',
                              'IoU dedup can merge distinct overlapping people or retain imperfect duplicates.',
                              'ORT CUDA arena limit is not total device memory; GPU peak memory is unmeasured.',
                              'Existing live ingress/person limits and baseline X3D are unchanged.'],
              'frames': results}
    report['completedProcessingHostWallMsBeforeSerialization'] = (perf_counter() - started) * 1000
    # Recheck after computation. Exclusive creation never replaces another helper's result.
    destination = output_path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination = output_path(destination)
    serialized = json.dumps(report, indent=2, allow_nan=False) + '\n'
    with destination.open('x', encoding='utf-8') as stream:
        stream.write(serialized)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, default=SERVICE / 'evaluation' / 'corpus.json')
    parser.add_argument('--corpus-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True, help='New JSON name/path under service/research/runs')
    parser.add_argument('--device', choices=('cpu', 'cuda'), required=True)
    parser.add_argument('--frames-per-recording', type=int, default=2)
    parser.add_argument('--start-ms', type=float, default=0)
    parser.add_argument('--interval-ms', type=float, default=1000)
    parser.add_argument('--decode-frame-limit', type=int, default=1200)
    parser.add_argument('--decode-timeout-seconds', type=float, default=20)
    parser.add_argument('--preload-torch-dlls', action='store_true')
    parser.add_argument('--allow-cpu-operators', action='store_true', help='Explicit mixed CUDA-first policy; implies operator profiling')
    parser.add_argument('--profile-operators', action='store_true', help='Save bounded ORT trace beside new report and summarize actual provider executions')
    parser.add_argument('--demo-wait-seconds', type=float, default=30)
    args = parser.parse_args()
    try:
        report = run_research(corpus=args.corpus, corpus_sha256=args.corpus_sha256,
                              output=args.output, device=args.device,
                              frames_per_recording=args.frames_per_recording,
                              start_ms=args.start_ms, interval_ms=args.interval_ms,
                              decode_frame_limit=args.decode_frame_limit,
                              decode_timeout_seconds=args.decode_timeout_seconds,
                              preload_torch_dlls=args.preload_torch_dlls,
                              allow_cpu_operators=args.allow_cpu_operators,
                              profile_operators=args.profile_operators,
                              demo_wait_seconds=args.demo_wait_seconds)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(2, f'Observer research failed: {error}\n')
    print(json.dumps({'status': report['status'], 'samples': len(report['frames']),
                      'output': str(args.output if args.output.is_absolute() else RUNS / args.output)}))


if __name__ == '__main__':
    main()
