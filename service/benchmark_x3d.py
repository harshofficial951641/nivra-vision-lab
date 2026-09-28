"""Read-only diagnostic for a published classifier; no live-alert promotion."""
import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import time
import cv2
import numpy as np
from nivra.x3d_candidate import X3DCandidate, CHECKSUM, SOURCE
from evaluate import validate_manifest


def run(manifest, output):
    records = json.loads(manifest.read_text())
    validate_manifest(records)
    model = X3DCandidate()
    report = {'experimental': True, 'source': SOURCE, 'checkpointSha256': CHECKSUM,
              'manifestSha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),
              'windowMs': 4000, 'publisherThreshold': .4, 'clips': {}}
    for clip in records:
        path = (manifest.parent / clip['path']).resolve()
        if hashlib.sha256(path.read_bytes()).hexdigest() != clip['sha256']:
            raise ValueError('Media checksum mismatch')
        capture = cv2.VideoCapture(str(path))
        window = deque(maxlen=64)
        last_frame, last_check = -1e9, -1e9
        rows = []
        while True:
            ok, frame = capture.read()
            if not ok: break
            timestamp = capture.get(cv2.CAP_PROP_POS_MSEC)
            if timestamp-last_frame < 100: continue
            last_frame = timestamp
            if clip.get('crop'):
                h,w = frame.shape[:2]
                x,y,right,bottom = clip['crop']
                frame = frame[round(y*h):round(bottom*h),round(x*w):round(right*w)]
            window.append((timestamp,cv2.resize(frame,(224,224))))
            while window and timestamp-window[0][0] > 4000: window.popleft()
            if timestamp-window[0][0] < 3800 or timestamp-last_check < 400: continue
            started=time.perf_counter()
            score=model.predict([f for _,f in window])
            rows.append(dict(timestampMs=timestamp, inferenceMs=(time.perf_counter()-started)*1000, **score))
            last_check=timestamp
        capture.release()
        report['clips'][clip['id']]={'samples':rows,'labelledEvents':len(clip['events']),
            'abovePublisherThreshold':sum(r['publisherScore'] >= .4 for r in rows),
            'p95InferenceMs':float(np.percentile([r['inferenceMs'] for r in rows],95)) if rows else None}
        print(clip['id'],{k:v for k,v in report['clips'][clip['id']].items() if k!='samples'},flush=True)
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('manifest',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    run(args.manifest,args.output)
