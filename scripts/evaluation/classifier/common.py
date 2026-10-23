"""Pinned local inputs. No downloads, sockets, environment or service state."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PRIVATE = Path(r'D:\nivra-work\classifier')
DOCS = ROOT / 'docs/evaluations/video-classifier'
RUN = Path(r'D:\nivra-work\runs\backbones\probe-c93e6cc85e1d8739')
TRAINING = Path(r'C:\Users\harsh.DESKTOP-VE90R6D\Downloads\nivra-vision-lab\service\training_v4')
MODEL = RUN / 'movinet/export/model.pt'
MODEL_SHA = '78e372a5ec6ad97925c3cdac2e0de0f5e9315ebd38fb151fa429d69304aaef87'
TRAIN_SHA = 'bf2942793bbdfc51281c8e9c47afe1a4c566c1b0beba0fb34b5cccd8b6d4fec7'
DEV_SHA = 'dd215f1a8569ab7e78ae27cf94b3d6165ec21d1aef461405c1ddf4e58cc9c00e'
PREPROCESSING = dict(color='RGB', dtype='float32', layout='B,T,C,H,W', range=[0, 1],
                     resize=[224, 172], interpolation='OpenCV INTER_LINEAR, square full-frame at both stages',
                     normalization='divide by 255 only; no channel mean/std',
                     baseTargets=16, baseEndpoint=False, selectedIndices=[0, 2, 4, 6, 8, 10, 12, 15],
                     targetOffsetsMs=[0, 500, 1000, 1500, 2000, 2500, 3000, 3750],
                     nearest='actual source PTS inside half-open window; earlier timestamp wins ties',
                     windowMs=4000, strideMs=1000, clipReset=True)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temp.replace(path)


def frozen():
    path = PRIVATE / 'frozen/split.json'
    expected = (path.with_suffix('.sha256')).read_text().strip()
    if sha(path) != expected:
        raise ValueError('frozen split changed')
    return read(path), expected
