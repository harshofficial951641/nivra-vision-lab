import json
import struct
import time
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from nivra.server import create_app, unpack_frame


class FakeModels:
    runtime = {'action': 'test'}


class FakePipeline:
    def __init__(self, models): self.reset()
    def reset(self): self.last = -1
    def process(self, frame, timestamp, max_people, video_frames=None):
        if timestamp <= self.last: raise ValueError('Out of order')
        self.last = timestamp
        return dict(timestampMs=timestamp)


def packet(time=100, stream=1, **extra):
    header = json.dumps(dict(version=1, timestampMs=time, streamId=stream, maxPeople=4, **extra)).encode()
    jpeg = cv2.imencode('.jpg', np.zeros((100,100,3), np.uint8))[1].tobytes()
    return struct.pack('<I',len(header)) + header + jpeg


def test_frame_validation():
    header, frame = unpack_frame(packet())
    assert header.timestampMs == 100 and frame.shape == (100,100,3)
    for invalid in (b'x', packet(float('nan')), packet(-1), packet(secret='unexpected'), b'x' * 1500001):
        with pytest.raises(ValueError): unpack_frame(invalid)


def test_origin_cookie_ordering_and_new_stream():
    with TestClient(create_app(FakeModels, FakePipeline), base_url='http://127.0.0.1:8765') as client:
        for _ in range(100):
            if client.get('/api/v1/health').json()['status']=='ready': break
            time.sleep(.01)
        assert client.post('/api/v1/session', headers={'origin':'https://evil.example'}).status_code == 403
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect('ws://127.0.0.1:8765/api/v1/stream', headers={'origin':'http://127.0.0.1:8765'}): pass
        assert client.post('/api/v1/session', headers={'origin':'http://127.0.0.1:8765'}).status_code == 204
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect('ws://127.0.0.1:8765/api/v1/stream', headers={'origin':'https://evil.example'}): pass
        with client.websocket_connect('ws://127.0.0.1:8765/api/v1/stream', headers={'origin':'http://127.0.0.1:8765'}) as socket:
            socket.send_bytes(packet())
            assert socket.receive_json()['timestampMs']==100
            socket.send_bytes(packet(0,2))
            assert socket.receive_json()['streamId']==2
            socket.send_bytes(packet(0,2))
            with pytest.raises(WebSocketDisconnect): socket.receive_json()


def test_failed_pipeline_initialization_releases_connection_slot():
    attempts = []

    def create_pipeline(models):
        attempts.append(True)
        if len(attempts) == 1:
            raise RuntimeError('Initialization failed')
        return FakePipeline(models)

    headers = {'origin': 'http://127.0.0.1:8765'}
    with TestClient(create_app(FakeModels, create_pipeline), base_url='http://127.0.0.1:8765') as client:
        for _ in range(100):
            if client.get('/api/v1/health').json()['status'] == 'ready': break
            time.sleep(.01)
        client.post('/api/v1/session', headers=headers)
        with client.websocket_connect('ws://127.0.0.1:8765/api/v1/stream', headers=headers) as socket:
            with pytest.raises(WebSocketDisconnect) as error:
                socket.receive_json()
            assert error.value.code == 1011
        with client.websocket_connect('ws://127.0.0.1:8765/api/v1/stream', headers=headers) as socket:
            socket.send_bytes(packet())
            assert socket.receive_json()['timestampMs'] == 100
