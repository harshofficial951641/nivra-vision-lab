"""CPU-only diagnostic comparison; never promotes or changes the public model.

The existing corpus is already inspected. Event overlaps describe source content,
not binary window ground truth, accuracy, actor identity or confirmed violence.
"""
import os

# Must precede torch in the standalone CLI, without changing an importing app's
# process environment. Imported callers must themselves use a CPU-only process.
if __name__ == '__main__':
    os.environ['CUDA_VISIBLE_DEVICES'] = '-1'

import argparse
import json
import math
from pathlib import Path
import re
import sys
import time

import cv2
import torch

from evaluate import validate_manifest
from nivra.fight_demo import FightWindow
from nivra.x3d_candidate import CHECKSUM, SOURCE, X3DCandidate
from nivra.x3d_training import (BASE_SHA256, BASE_URL, CLASS_NAMES, PREPROCESS,
                                FrozenX3D, file_hash, preprocess_frames)

KIND = 'official-frozen-x3d-m-linear-head'
ROOT = Path(__file__).resolve().parent


def _digest(value, name):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError(f'Invalid {name} SHA-256')
    return value


def validate_inputs(run_dir, base_checkpoint, corpus, community_checkpoint=None):
    """Verify every local input before constructing models or decoding media."""
    run_dir, base_checkpoint, corpus = Path(run_dir), Path(base_checkpoint), Path(corpus)
    community_checkpoint = Path(community_checkpoint or ROOT / 'models/x3d_rwf2000.pt')
    report_path, artifact_path = run_dir / 'report.json', run_dir / 'candidate-head.pt'
    for path in (report_path, artifact_path, base_checkpoint, corpus, community_checkpoint):
        if not path.is_file():
            raise ValueError('Required local input is missing: ' + str(path))
    report = json.loads(report_path.read_text(encoding='utf-8'))
    if not isinstance(report, dict) or report.get('schemaVersion') != 1 or report.get('kind') != KIND:
        raise ValueError('Unsupported training report')
    if file_hash(artifact_path) != _digest(report.get('candidateSha256'), 'candidate'):
        raise ValueError('Candidate checksum mismatch')
    if file_hash(base_checkpoint) != BASE_SHA256 or report.get('base', {}).get('sha256') != BASE_SHA256:
        raise ValueError('Official base checkpoint checksum mismatch')
    if file_hash(community_checkpoint) != CHECKSUM:
        raise ValueError('Community checkpoint checksum mismatch')
    _digest(report.get('manifestSha256'), 'training manifest')
    threshold = report.get('threshold')
    if type(threshold) not in (int, float) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError('Invalid candidate threshold')
    if report.get('preprocessing') != PREPROCESS or report.get('classNames') != CLASS_NAMES:
        raise ValueError('Candidate preprocessing or class order mismatch')
    records = json.loads(corpus.read_text(encoding='utf-8'))
    if not isinstance(records, list) or not records:
        raise ValueError('Diagnostic corpus must contain recordings')
    validate_manifest(records)
    for clip in records:
        if not isinstance(clip.get('path'), str):
            raise ValueError('Invalid diagnostic media path')
        path = (corpus.parent / clip['path']).resolve()
        if not path.is_file() or file_hash(path) != _digest(clip.get('sha256'), 'media'):
            raise ValueError('Diagnostic media missing or checksum mismatch: ' + clip['id'])
        crop = clip.get('crop')
        if crop is not None:
            if (not isinstance(crop, list) or len(crop) != 4 or
                    any(type(value) not in (int, float) or not math.isfinite(value) for value in crop) or
                    not 0 <= crop[0] < crop[2] <= 1 or not 0 <= crop[1] < crop[3] <= 1):
                raise ValueError('Invalid diagnostic crop')
    artifact = torch.load(artifact_path, map_location='cpu', weights_only=True)
    if (not isinstance(artifact, dict) or artifact.get('schemaVersion') != 1 or
            artifact.get('kind') != KIND or artifact.get('baseSha256') != BASE_SHA256 or
            artifact.get('manifestSha256') != report['manifestSha256'] or
            artifact.get('preprocessing') != PREPROCESS or artifact.get('classNames') != CLASS_NAMES or
            artifact.get('threshold') != threshold):
        raise ValueError('Candidate artifact does not match its report')
    state = artifact.get('head_state')
    if not isinstance(state, dict) or set(state) != {'weight', 'bias'}:
        raise ValueError('Invalid binary classifier state')
    for key, shape in (('weight', (2, 2048)), ('bias', (2,))):
        tensor = state[key]
        if (not isinstance(tensor, torch.Tensor) or tuple(tensor.shape) != shape or
                tensor.device.type != 'cpu' or tensor.dtype != torch.float32 or not torch.isfinite(tensor).all()):
            raise ValueError('Invalid binary classifier tensor')
    return report, artifact, records, community_checkpoint


class HeadCandidate:
    def __init__(self, base_checkpoint, artifact, *, extractor_factory=FrozenX3D):
        self.extractor = extractor_factory(base_checkpoint)
        self.head = torch.nn.Linear(2048, 2)
        self.head.load_state_dict(artifact['head_state'], strict=True)
        self.head.eval().requires_grad_(False)

    @torch.inference_mode()
    def predict(self, frames):
        features = self.extractor(preprocess_frames(frames))
        score = float(self.head(torch.from_numpy(features).cpu()).softmax(-1)[0, 1])
        if not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError('Invalid candidate score')
        return score


def windows(clip, corpus):
    """Use the public demo's bounded, causal source-time sampling policy."""
    capture = cv2.VideoCapture(str((Path(corpus).parent / clip['path']).resolve()))
    history = FightWindow()
    previous = -math.inf
    try:
        if not capture.isOpened():
            raise ValueError('Cannot decode diagnostic recording: ' + clip['id'])
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            timestamp = capture.get(cv2.CAP_PROP_POS_MSEC)
            # Some WebM containers expose a time-base denominator (e.g. 30000)
            # as nominal FPS. Their decoded frame presentation times are valid.
            # Never manufacture a clock from that metadata or silently skip it.
            if not math.isfinite(timestamp) or timestamp < 0 or timestamp <= previous:
                raise ValueError('Non-increasing diagnostic timestamp')
            previous = timestamp
            if clip.get('crop'):
                height, width = frame.shape[:2]
                left, top, right, bottom = clip['crop']
                frame = frame[round(top * height):round(bottom * height),
                              round(left * width):round(right * width)]
            frames = history.add(timestamp, frame)
            if frames is not None:
                yield timestamp, history.frames[0][0], frames
    finally:
        history.reset()
        capture.release()


def event_overlaps(clip, start, end):
    return [{'label': event.get('label', 'unspecified'), 'startMs': event['startMs'],
             'endMs': event['endMs'],
             'overlapMs': round(min(end, event['endMs']) - max(start, event['startMs']), 3)}
            for event in clip['events']
            if event['endMs'] > start and event['startMs'] < end]


def run(run_dir, base_checkpoint, corpus, output, *, community_checkpoint=None,
        candidate_factory=HeadCandidate, community_factory=X3DCandidate, window_reader=windows):
    output = Path(output)
    if output.exists():
        raise FileExistsError('Diagnostic output already exists: ' + str(output))
    training_report, artifact, records, community_checkpoint = validate_inputs(
        run_dir, base_checkpoint, corpus, community_checkpoint)
    if torch.cuda.is_available():
        raise RuntimeError('CPU-only diagnostics require a fresh process with CUDA_VISIBLE_DEVICES=-1')
    torch.set_num_threads(2)
    candidate = candidate_factory(base_checkpoint, artifact)
    current = community_factory(community_checkpoint)
    if getattr(current, 'device', 'cpu') != 'cpu':
        raise RuntimeError('Community model must remain on CPU')
    # The legacy candidate sets four threads in its constructor; restore the cap.
    torch.set_num_threads(2)
    threshold = float(artifact['threshold'])
    report = {
        'schemaVersion': 1, 'status': 'diagnostic-only', 'device': 'cpu', 'cpuThreads': 2,
        'liveModelChanged': False, 'thresholdFittedHere': False,
        'corpusSha256': file_hash(corpus), 'implementationSha256': file_hash(__file__),
        'candidate': {'kind': KIND, 'sha256': training_report['candidateSha256'],
                      'trainingReportSha256': file_hash(Path(run_dir) / 'report.json'),
                      'trainingManifestSha256': artifact['manifestSha256'],
                      'baseSha256': BASE_SHA256, 'baseSource': BASE_URL,
                      'threshold': threshold, 'calibration': training_report.get('calibration')},
        'current': {'source': SOURCE, 'sha256': CHECKSUM, 'threshold': .5},
        'policy': {'windowMs': 4000, 'minimumSpanMs': 3800, 'sampleIntervalMs': 100,
                   'predictionIntervalMs': 400, 'framesPerWindow': 16, 'comparison': 'score > threshold',
                   'sourceClock': 'strict decoder presentation timestamps in milliseconds; no nominal-FPS fallback'},
        'limitations': ['Existing inspected footage is diagnostic, including historical holdout labels.',
                        'Cropped variants share a recording and are not independent evidence.',
                        'Event overlaps are context, not binary window truth; no accuracy or event-recall claim.',
                        'CPU classifier timing excludes decoding and transport; it is not live GPU capacity.',
                        'Scores are uncalibrated classifier outputs, not probabilities of violence.'],
        'clips': {},
    }
    for clip in records:
        rows = []
        for timestamp, start, frames in window_reader(clip, corpus):
            before = time.perf_counter()
            current_score = float(current.predict(frames)['backboneScore'])
            current_ms = (time.perf_counter() - before) * 1000
            before = time.perf_counter()
            candidate_score = float(candidate.predict(frames))
            candidate_ms = (time.perf_counter() - before) * 1000
            if not all(math.isfinite(score) and 0 <= score <= 1 for score in (current_score, candidate_score)):
                raise ValueError('Invalid comparison score')
            rows.append({'timestampMs': timestamp, 'windowStartMs': start,
                         'labelledEventOverlaps': event_overlaps(clip, start, timestamp),
                         'current': {'score': current_score, 'review': current_score > .5,
                                     'inferenceMs': round(current_ms, 3)},
                         'candidate': {'score': candidate_score, 'review': candidate_score > threshold,
                                       'reviewAtPointFive': candidate_score > .5,
                                       'inferenceMs': round(candidate_ms, 3)}})
        report['clips'][clip['id']] = {
            'sourceGroup': clip['sourceGroup'], 'historicalSplit': clip['split'],
            'syntheticCrop': bool(clip.get('crop')), 'sha256': clip['sha256'],
            'windows': len(rows), 'currentReviewWindows': sum(row['current']['review'] for row in rows),
            'candidateReviewWindows': sum(row['candidate']['review'] for row in rows),
            'disagreementWindows': sum(row['current']['review'] != row['candidate']['review'] for row in rows),
            'samples': rows,
        }
        print(json.dumps({'stage': 'diagnostics', 'clip': clip['id'], 'windows': len(rows)}), flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--base-checkpoint', type=Path, required=True)
    parser.add_argument('--corpus', type=Path, default=ROOT / 'evaluation/corpus.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args.run_dir, args.base_checkpoint, args.corpus, args.output)
        print(json.dumps({'status': report['status'], 'output': str(args.output),
                          'liveModelChanged': False,
                          'clips': {key: {name: value[name] for name in
                                         ('windows', 'currentReviewWindows', 'candidateReviewWindows', 'disagreementWindows')}
                                    for key, value in report['clips'].items()}}), flush=True)
        return 0
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
