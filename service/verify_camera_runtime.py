"""Real-model, paced JPEG replay through the actual camera WebSocket ASGI route.

Uses disposable metadata and in-process TestClient transport; no listening port,
no production database, no model mocks, and no recorded images written to disk.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import secrets
import struct
import tempfile
import time
import cv2
import numpy as np
from fastapi.testclient import TestClient


def run(args):
    os.environ['NIVRA_DEVICE'] = args.device
    os.environ['NIVRA_PERSON_MODEL'] = 'rtmo'
    os.environ['NIVRA_FIGHT_MODEL'] = 'x3d'
    os.environ['NIVRA_AUTO_RELAY'] = '0' if args.no_fallback else '1'
    from nivra.models import Models
    from nivra.pipeline import Pipeline
    from nivra.server import create_app
    from nivra.classroom import CAMERA_COOKIE, digest
    model = Models()
    timings = []

    class MeasuredPipeline(Pipeline):
        def process(self, *pos, **kw):
            result = super().process(*pos, **kw)
            timings.append(result['inferenceMs'])
            return result

    capture = cv2.VideoCapture(str(args.video))
    source_fps = capture.get(cv2.CAP_PROP_FPS)
    encoded = []
    index = 0
    while True:
        ok, frame = capture.read()
        if not ok: break
        if index / source_fps >= len(encoded) / 12:
            scale = min(1, 640 / max(frame.shape[:2]))
            frame = cv2.resize(frame, (round(frame.shape[1]*scale), round(frame.shape[0]*scale)))
            encoded.append(cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])[1].tobytes())
        index += 1
    capture.release()
    if not encoded: raise ValueError('No readable video frames')
    with tempfile.TemporaryDirectory(prefix='nivra-runtime-') as directory:
        app = create_app(lambda: model, MeasuredPipeline, Path(directory)/'metadata.sqlite')
        service = app.state.classroom
        with TestClient(app, base_url='http://127.0.0.1:8765') as client:
            cameras = [service.store.add_camera(f'QA replay {i+1}', 'Disposable', '1') for i in range(args.cameras)]
            start = time.monotonic()
            ending_runtime = []

            def publish(camera):
                credential = secrets.token_urlsafe(32)
                service.credentials[digest(credential)] = camera['id']
                headers = {'origin': 'http://127.0.0.1:8765', 'cookie': f'{CAMERA_COOKIE}={credential}'}
                with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream', headers=headers) as socket:
                    socket.receive_json()
                    i = 0
                    while time.monotonic() - start < args.seconds:
                        timestamp = (time.monotonic() - start) * 1000
                        header = json.dumps(dict(version=1, streamId=1, timestampMs=timestamp, maxPeople=50)).encode()
                        socket.send_bytes(struct.pack('<I', len(header)) + header + encoded[i % len(encoded)])
                        assert socket.receive_json()['type'] == 'accepted'
                        i += 1
                        time.sleep(max(0, start + i / 12 - time.monotonic()))
                    live = service.live[camera['id']]
                    ending_runtime.append(service.runtime())
                    return dict(received=live['frames'], analyzed=live.get('analyzedCount', 0),
                                replaced=live['replaced'], error=live.get('error'))

            with ThreadPoolExecutor(max_workers=args.cameras) as pool:
                counts = list(pool.map(publish, cameras))
            duration = time.monotonic() - start
            events = service.store.events()
            clips = [service.clips.summary(event['id']) for event in events]
            result = dict(device=args.device, runtime=ending_runtime[0], cameras=args.cameras, seconds=round(duration, 2),
                          video=args.video.name, transport='actual ASGI WebSocket route; in-process TestClient',
                          fallbackEnabled=not args.no_fallback, frames=counts,
                          analyzedFps=round(sum(c['analyzed'] for c in counts)/duration, 3),
                          perCameraFps=[round(c['analyzed']/duration, 3) for c in counts],
                          inferenceMs=dict(count=len(timings), mean=round(float(np.mean(timings)), 2) if timings else None,
                                           p50=round(float(np.percentile(timings, 50)), 2) if timings else None,
                                           p95=round(float(np.percentile(timings, 95)), 2) if timings else None),
                          events=len(events), clips=clips)
            print(json.dumps(result, indent=2))
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', choices=['cpu', 'cuda', 'mps'], required=True)
    parser.add_argument('--cameras', type=int, choices=range(1, 13), default=1)
    parser.add_argument('--seconds', type=int, default=22)
    parser.add_argument('--video', type=Path, default=Path(__file__).parent/'evaluation/media/grappling.webm')
    parser.add_argument('--no-fallback', action='store_true', help='Measure overloaded server without switching to browser analysis')
    parser.add_argument('--output', type=Path)
    run(parser.parse_args())
