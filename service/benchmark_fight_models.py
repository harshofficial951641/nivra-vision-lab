"""Offline classifier comparison only; never changes live alert policy.

Uses identical source-time windows and each checkpoint's own preprocessing.
The inspected smoke corpus is diagnostic, not an unseen release evaluation.
"""
import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import time

import cv2
import numpy as np
import torch

from evaluate import score_clip, validate_manifest
from nivra.x3d_candidate import X3DCandidate, CHECKSUM, SOURCE

ROOT = Path(__file__).resolve().parent
MC3_REVISION = 'a27adffec6651c10639b5b453e0df8564b9be298'
MC3_SOURCE = 'https://github.com/MohamedSebaie/Fight_Detection_From_Surveillance_Cameras-PyTorch_Project/tree/' + MC3_REVISION


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class MC3Candidate:
    def __init__(self, path, expected_sha256):
        if digest(path) != expected_sha256:
            raise ValueError('MC3 checkpoint checksum mismatch')
        from torchvision.models.video import mc3_18
        self.model = mc3_18(weights=None)
        self.model.fc = torch.nn.Linear(self.model.fc.in_features, 2)
        self.model.load_state_dict(torch.load(path, map_location='cpu', weights_only=True), strict=True)
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.model.eval().to(self.device)

    @torch.inference_mode()
    def predict(self, frames):
        indices = np.linspace(0, len(frames) - 1, 16).astype(int)
        images = []
        for index in indices:
            image = cv2.resize(cv2.cvtColor(frames[index], cv2.COLOR_BGR2RGB), (171, 128))
            # Albumentations CenterCrop uses integer floor for the crop origin.
            image = image[8:120, 29:141].astype(np.float32) / 255
            images.append((image - np.array([.43216, .394666, .37645], dtype=np.float32)) /
                          np.array([.22803, .22145, .216989], dtype=np.float32))
        clip = torch.from_numpy(np.stack(images)).permute(3, 0, 1, 2)[None].to(self.device)
        # Publisher class order: ['fight', 'noFight'].
        return float(self.model(clip).softmax(-1)[0, 0])


def windows(clip, manifest):
    path = (manifest.parent / clip['path']).resolve()
    if digest(path) != clip['sha256']:
        raise ValueError('Media checksum mismatch: ' + clip['id'])
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError('Cannot open media: ' + str(path))
    history = deque()
    last_frame = last_check = -1e9
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            timestamp = capture.get(cv2.CAP_PROP_POS_MSEC)
            if timestamp - last_frame < 100:
                continue
            last_frame = timestamp
            if clip.get('crop'):
                h, w = frame.shape[:2]
                x, y, right, bottom = clip['crop']
                frame = frame[round(y*h):round(bottom*h), round(x*w):round(right*w)]
            history.append((timestamp, frame))
            while history and timestamp - history[0][0] > 4000:
                history.popleft()
            if timestamp - history[0][0] >= 3800 and timestamp - last_check >= 400:
                yield timestamp, [image for _, image in history]
                last_check = timestamp
    finally:
        capture.release()


def summarize(clip, rows):
    events = []
    last_alert = -1e9
    # Fixed diagnostic policy shared by both classifiers; no threshold fitting.
    for row in rows:
        if row['fightScore'] > .5 and row['timestampMs'] - last_alert >= 8000:
            last_alert = row['timestampMs']
            events.append({'occurredAtMs': last_alert})
    return {'samples': rows, 'events': events, 'metrics': score_clip(clip, {'events': events}),
            'p50InferenceMs': float(np.percentile([r['inferenceMs'] for r in rows], 50)) if rows else None,
            'p95InferenceMs': float(np.percentile([r['inferenceMs'] for r in rows], 95)) if rows else None}


def run(manifest, output, mc3_sha256):
    records = json.loads(manifest.read_text())
    validate_manifest(records)
    torch.set_num_threads(4)
    report = {'status': 'diagnostic-only; inspected tiny corpus; no live promotion',
              'manifestSha256': digest(manifest), 'implementationSha256': digest(Path(__file__)),
              'policy': {'windowMs': 4000, 'minimumSpanMs': 3800, 'sampleIntervalMs': 100,
                         'predictionIntervalMs': 400, 'framesPerWindow': 16,
                         'threshold': .5, 'cooldownMs': 8000},
              'hardware': torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU',
              'torch': torch.__version__, 'models': {}}
    output.parent.mkdir(parents=True, exist_ok=True)
    for name in ('x3d-m', 'mc3-18'):
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
        model = X3DCandidate() if name == 'x3d-m' else MC3Candidate(ROOT/'models/mc3_18_sebaie.pth', mc3_sha256)
        result = {'source': SOURCE if name == 'x3d-m' else MC3_SOURCE,
                  'checkpointSha256': CHECKSUM if name == 'x3d-m' else mc3_sha256,
                  'scoreMeaning': 'uncalibrated classifier softmax; not violence probability', 'clips': {}}
        warmed = False
        for clip in records:
            rows = []
            for timestamp, frames in windows(clip, manifest):
                if not warmed:
                    for _ in range(3):
                        model.predict(frames)
                    warmed = True
                if torch.cuda.is_available():
                    torch.cuda.synchronize()
                started = time.perf_counter()
                score = model.predict(frames)
                if torch.cuda.is_available():
                    torch.cuda.synchronize()
                latency = (time.perf_counter() - started) * 1000
                value = score['backboneScore'] if name == 'x3d-m' else score
                rows.append({'timestampMs': timestamp, 'fightScore': value, 'inferenceMs': latency})
            result['clips'][clip['id']] = summarize(clip, rows)
            print(name, clip['id'], result['clips'][clip['id']]['metrics'], flush=True)
        result['peakTorchAllocatedMiB'] = torch.cuda.max_memory_allocated()/1024**2 if torch.cuda.is_available() else None
        result['memoryScope'] = 'PyTorch allocations only; excludes driver, decoder and other processes'
        report['models'][name] = result
        output.write_text(json.dumps(report, indent=2))
        del model
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mc3-sha256', required=True)
    args = parser.parse_args()
    run(args.manifest, args.output, args.mc3_sha256)
