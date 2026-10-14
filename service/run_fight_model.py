"""Run the installed X3D-M classifier on a local video or an explicit webcam.

Console JSON only: no upload, recording or live-app policy modification.
"""
import argparse
from collections import deque
import json
from pathlib import Path
import sys
import time

import cv2

from nivra.x3d_candidate import X3DCandidate


class FightWindow:
    """Bounded causal source-time history; discard discontinuous observations."""
    def __init__(self):
        self.frames = deque(maxlen=48)
        self.last_sample = self.last_prediction = -1e9
        self.dimensions = None

    def add(self, timestamp, frame):
        dimensions = frame.shape[:2]
        if timestamp < self.last_sample:
            raise ValueError('Source timestamps moved backwards')
        if timestamp - self.last_sample > 1200 or dimensions != self.dimensions:
            self.frames.clear()
            self.last_prediction = -1e9
        if timestamp - self.last_sample < 100:
            return None
        self.last_sample = timestamp
        self.dimensions = dimensions
        self.frames.append((timestamp, cv2.resize(frame, (224, 224))))
        while self.frames and timestamp - self.frames[0][0] > 4000:
            self.frames.popleft()
        if len(self.frames) < 8 or timestamp - self.frames[0][0] < 3800:
            return None
        if timestamp - self.last_prediction < 400:
            return None
        self.last_prediction = timestamp
        return [image for _, image in self.frames]


def run(source, camera=None):
    if camera is None and not source.is_file():
        raise ValueError('Video does not exist: ' + str(source))
    capture = cv2.VideoCapture(camera if camera is not None else str(source))
    try:
        if not capture.isOpened():
            raise ValueError('Cannot open the selected video or camera')
        model = X3DCandidate()
        print(json.dumps({'status': 'ready', 'model': 'X3D-M fight candidate',
                          'device': model.device, 'input': 'webcam' if camera is not None else source.name,
                          'experimental': True, 'windowSeconds': 4,
                          'note': 'Scene classifier scores are uncalibrated; review signals are not confirmed fights.'}), flush=True)
        history = FightWindow()
        started = time.perf_counter()
        windows = signals = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                if camera is not None:
                    raise ValueError('Camera stopped returning frames')
                break
            timestamp = ((time.perf_counter()-started)*1000 if camera is not None
                         else capture.get(cv2.CAP_PROP_POS_MSEC))
            frames = history.add(timestamp, frame)
            if frames is None:
                continue
            before = time.perf_counter()
            scores = model.predict(frames)
            positive = scores['backboneScore'] > .5
            windows += 1
            signals += int(positive)
            print(json.dumps({'timestampMs': round(timestamp, 2),
                              'signal': 'review-physical-interaction' if positive else 'no-fight-signal',
                              'classifierScore': scores['backboneScore'],
                              'inferenceMs': round((time.perf_counter()-before)*1000, 2)}), flush=True)
        print(json.dumps({'status': 'complete', 'analyzedWindows': windows,
                          'positiveWindows': signals,
                          'note': 'Windows overlap; positive windows are not an incident count.'}), flush=True)
        if windows == 0:
            raise ValueError('No usable four-second window; use a longer video with continuous timestamps')
    finally:
        capture.release()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--video', type=Path, help='Local video path')
    inputs.add_argument('--camera', type=int, help='Explicit webcam index, for example 0; Ctrl+C stops')
    args = parser.parse_args()
    try:
        run(args.video, args.camera)
    except KeyboardInterrupt:
        print(json.dumps({'status': 'stopped'}), flush=True)
    except (ValueError, RuntimeError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
