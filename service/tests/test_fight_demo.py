import asyncio
from contextlib import asynccontextmanager, contextmanager
import json
import struct
import threading
import time

import cv2
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import numpy as np
import pytest
from starlette.websockets import WebSocketDisconnect

from nivra.fight_demo import COOKIE, PREFIX, FightDemo, FightWindow
from nivra.server import unpack_frame

ORIGIN = 'http://127.0.0.1:8765'
HEADERS = {'origin': ORIGIN}
PUBLIC = 'https://nivra-demo.example'
STREAM = 'ws://127.0.0.1:8765' + PREFIX + '/stream'


class FakeModel:
    device = 'cuda'

    def __init__(self, score=.8):
        self.score = score
        self.calls = []

    def predict(self, frames):
        self.calls.append([frame.shape for frame in frames])
        return {'backboneScore': self.score}


def packet(timestamp=0, stream=1, **extra):
    header = json.dumps(dict(version=1, timestampMs=timestamp, streamId=stream,
                             maxPeople=4, **extra)).encode()
    jpeg = cv2.imencode('.jpg', np.zeros((100, 100, 3), np.uint8))[1].tobytes()
    return struct.pack('<I', len(header)) + header + jpeg


def application(model=None, **options):
    model = model or FakeModel()
    demo = FightDemo(unpack_frame, allowed_origins={ORIGIN, PUBLIC},
                     model_factory=lambda: model, frame_interval=0, **options)

    @asynccontextmanager
    async def lifespan(app):
        await demo.start()
        try:
            yield
        finally:
            await demo.stop()

    app = FastAPI(lifespan=lifespan)
    app.include_router(demo.router)

    @app.get('/api/v2/state')
    async def operator_cookie_visibility(request: Request):
        return {'cookies': request.cookies}

    return app, demo, model


def ready(client):
    for _ in range(100):
        status = client.get(PREFIX + '/health').json()['status']
        if status != 'loading':
            return status
        time.sleep(.01)
    raise AssertionError('Model did not initialize')


def bootstrap(client):
    assert ready(client) == 'ready'
    assert client.post(PREFIX + '/session', headers=HEADERS).status_code == 204


@contextmanager
def connect(client, **kwargs):
    with client.websocket_connect(STREAM, headers=HEADERS, **kwargs) as socket:
        assert socket.receive_json()['type'] == 'ready'
        yield socket


@pytest.mark.parametrize('score,expected', [(.8, 'review'), (.2, 'clear')])
def test_real_source_span_and_gpu_output(score, expected):
    app, demo, model = application(FakeModel(score))
    with TestClient(app, base_url=ORIGIN) as client:
        bootstrap(client)
        with connect(client) as socket:
            for timestamp in range(0, 800, 100):
                socket.send_bytes(packet(timestamp))
                assert socket.receive_json()['status'] == 'warming'
            assert not model.calls
            # A seek/discontinuity cannot manufacture a usable four-second clip.
            socket.send_bytes(packet(4000))
            assert socket.receive_json()['status'] == 'warming'
            for timestamp in range(4500, 8001, 500):
                socket.send_bytes(packet(timestamp))
                result = socket.receive_json()
            assert result == {'type': 'result', 'streamId': 1, 'timestampMs': 8000,
                              'status': expected, 'classifierScore': score,
                              'analyzed': True,
                              'inferenceMs': result['inferenceMs'], 'windowSeconds': 4,
                              'model': 'X3D-M', 'experimental': True}
            assert len(model.calls) == 1
            assert all(shape == (224, 224, 3) for shape in model.calls[0])
            socket.send_bytes(packet(8200))
            assert socket.receive_json()['classifierScore'] == score
            assert len(model.calls) == 1
        assert client.get(PREFIX + '/health').json()['busy'] is False
    assert demo.model is None and not demo.sessions


def test_cookie_is_ephemeral_and_separate_from_operator_routes():
    app, demo, _ = application()
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.post(PREFIX + '/session', headers={'origin': 'https://evil.example'}).status_code == 403
        assert client.post(PREFIX + '/session', headers={'origin': PUBLIC}).status_code == 403
        bootstrap(client)
        cookie = client.cookies.get(COOKIE)
        assert cookie in demo.sessions
        response = client.post(PREFIX + '/session', headers=HEADERS)
        assert client.cookies.get(COOKIE) == cookie
        assert len(demo.sessions) == 1
        header = response.headers['set-cookie'].lower()
        assert 'httponly' in header and 'samesite=strict' in header
        assert 'path=/api/v2/fight' in header and 'max-age=1200' in header
        assert client.get('/api/v2/state').json() == {'cookies': {}}
    assert not demo.sessions


def test_public_gateway_origin_and_secure_cookie():
    app, _, _ = application()
    with TestClient(app, base_url=ORIGIN) as client:
        headers = {'origin': PUBLIC, 'host': '127.0.0.1:8765',
                   'x-forwarded-host': 'nivra-public-gateway'}
        response = client.post(PREFIX + '/session', headers=headers)
        assert response.status_code == 204
        assert 'Secure' in response.headers['set-cookie']
        cookie = response.cookies.get(COOKIE)
        with client.websocket_connect(STREAM,
                                      headers={**headers, 'cookie': f'{COOKIE}={cookie}'}) as socket:
            assert socket.receive_json()['type'] == 'ready'
            socket.send_bytes(packet())
            assert socket.receive_json()['status'] == 'warming'
        for field in ('forwarded', 'x-forwarded-for', 'x-forwarded-proto'):
            assert client.post(PREFIX + '/session', headers={**HEADERS, field: 'untrusted'}).status_code == 403


def test_missing_foreign_and_expired_session_rejected():
    now = [100.]
    app, _, _ = application(clock=lambda: now[0])
    with TestClient(app, base_url=ORIGIN) as client:
        assert ready(client) == 'ready'
        with pytest.raises(WebSocketDisconnect) as error:
            with connect(client):
                pass
        assert error.value.code == 1008
        bootstrap(client)
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(STREAM, headers={'origin': 'https://evil.example'}):
                pass
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(STREAM, headers={**HEADERS, 'cookie': f'{COOKIE}=foreign'}):
                pass
        now[0] += 1201
        with pytest.raises(WebSocketDisconnect) as error:
            with connect(client):
                pass
        assert error.value.code == 1008


def test_session_limit_and_expiry_reclaim_capacity():
    now = [100.]
    app, demo, _ = application(clock=lambda: now[0], max_sessions=2)
    with TestClient(app, base_url=ORIGIN) as client:
        for _ in range(2):
            client.cookies.clear()
            assert client.post(PREFIX + '/session', headers=HEADERS).status_code == 204
        client.cookies.clear()
        assert client.post(PREFIX + '/session', headers=HEADERS).status_code == 503
        assert len(demo.sessions) == 2
        now[0] += 1201
        assert client.post(PREFIX + '/session', headers=HEADERS).status_code == 204
        assert len(demo.sessions) == 1


def test_one_stream_disconnect_releases_slot():
    app, _, _ = application()
    with TestClient(app, base_url=ORIGIN) as client:
        bootstrap(client)
        with connect(client) as first:
            assert client.get(PREFIX + '/health').json()['busy'] is True
            with pytest.raises(WebSocketDisconnect) as error:
                with connect(client):
                    pass
            assert error.value.code == 1013
            first.send_bytes(packet())
            assert first.receive_json()['status'] == 'warming'
        with connect(client) as second:
            second.send_bytes(packet())
            assert second.receive_json()['status'] == 'warming'


def test_new_generation_and_control_reset_discard_history():
    app, _, model = application()
    with TestClient(app, base_url=ORIGIN) as client:
        bootstrap(client)
        with connect(client) as socket:
            for timestamp in range(0, 4001, 500):
                socket.send_bytes(packet(timestamp))
                result = socket.receive_json()
            assert result['status'] == 'review'
            socket.send_json({'type': 'reset', 'streamId': 2})
            assert socket.receive_json() == {'type': 'reset', 'streamId': 2}
            socket.send_bytes(packet(0, 2))
            assert socket.receive_json()['status'] == 'warming'
            socket.send_bytes(packet(0, 3))
            assert socket.receive_json()['status'] == 'warming'
            socket.send_bytes(packet(100, 2))
            with pytest.raises(WebSocketDisconnect) as error:
                socket.receive_json()
            assert error.value.code == 1008
        assert len(model.calls) == 1


@pytest.mark.parametrize('invalid', [b'x', b'x' * 1_500_001, packet(float('nan')),
                                    packet(-1), packet(secret='unexpected'), packet(stream=True)],
                         ids=['short', 'oversized', 'nan', 'negative', 'extra-field', 'boolean-id'])
def test_invalid_binary_closes_and_releases(invalid):
    app, _, _ = application()
    with TestClient(app, base_url=ORIGIN) as client:
        bootstrap(client)
        with connect(client) as socket:
            socket.send_bytes(invalid)
            with pytest.raises(WebSocketDisconnect) as error:
                socket.receive_json()
            assert error.value.code == 1008
        with connect(client) as socket:
            socket.send_bytes(packet())
            assert socket.receive_json()['status'] == 'warming'


@pytest.mark.parametrize('control', [{'type': 'reset', 'streamId': True},
                                     {'type': 'reset', 'streamId': 1, 'path': 'secret'},
                                     {'type': 'reset', 'streamId': -1}, []])
def test_invalid_reset_closes(control):
    app, _, _ = application()
    with TestClient(app, base_url=ORIGIN) as client:
        bootstrap(client)
        with connect(client) as socket:
            socket.send_json(control)
            with pytest.raises(WebSocketDisconnect) as error:
                socket.receive_json()
            assert error.value.code == 1008


def test_repeated_timestamp_before_sampling_and_idle_expiry():
    app, _, _ = application(idle_timeout=.05)
    with TestClient(app, base_url=ORIGIN) as client:
        bootstrap(client)
        with connect(client) as socket:
            socket.send_bytes(packet(100))
            socket.receive_json()
            socket.send_bytes(packet(110))
            socket.receive_json()
            socket.send_bytes(packet(110))
            with pytest.raises(WebSocketDisconnect) as error:
                socket.receive_json()
            assert error.value.code == 1008
        with connect(client) as socket:
            with pytest.raises(WebSocketDisconnect) as error:
                socket.receive_json()
            assert error.value.code == 1008


def test_gpu_unavailable_reports_generic_error_without_cpu_fallback():
    model = FakeModel()
    model.device = 'cpu'
    app, _, _ = application(model)
    with TestClient(app, base_url=ORIGIN) as client:
        assert ready(client) == 'error'
        health = client.get(PREFIX + '/health').json()
        assert health['device'] is None and 'error' not in health
        client.post(PREFIX + '/session', headers=HEADERS)
        with pytest.raises(WebSocketDisconnect) as error:
            with connect(client):
                pass
        assert error.value.code == 1013


def test_inference_cancellation_joins_thread_before_releasing_gpu_slot():
    async def scenario():
        entered = threading.Event()
        release = threading.Event()

        class BlockingModel(FakeModel):
            def predict(self, frames):
                entered.set()
                assert release.wait(5)
                return super().predict(frames)

        class Socket:
            headers = {'origin': ORIGIN, 'host': '127.0.0.1:8765'}
            cookies = {COOKIE: 'test-session'}

            def __init__(self):
                self.messages = asyncio.Queue()
                self.closed = None

            async def accept(self):
                pass

            async def receive(self):
                return await self.messages.get()

            async def send_json(self, result):
                pass

            async def close(self, code=1000, reason=''):
                self.closed = code

        demo = FightDemo(unpack_frame, allowed_origins={ORIGIN},
                         model_factory=BlockingModel, frame_interval=0)
        await demo.start()
        await demo._load_task
        demo.sessions['test-session'] = time.monotonic() + 60
        first = Socket()
        for timestamp in range(0, 4001, 500):
            first.messages.put_nowait({'type': 'websocket.receive', 'bytes': packet(timestamp)})
        task = asyncio.create_task(demo.stream(first))
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            task.cancel()
            await asyncio.sleep(.02)
            assert demo.busy and not task.done()
            second = Socket()
            await demo.stream(second)
            assert second.closed == 1013
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert not demo.busy
            third = Socket()
            third.messages.put_nowait({'type': 'websocket.disconnect'})
            await demo.stream(third)
            assert third.closed is None
        finally:
            release.set()
            if not task.done():
                await asyncio.gather(task, return_exceptions=True)
            await demo.stop()

    asyncio.run(scenario())


def test_history_stays_bounded_and_dimension_changes_reset():
    history = FightWindow()
    frame = np.zeros((100, 100, 3), np.uint8)
    for timestamp in range(0, 10_001, 100):
        history.add(timestamp, frame)
    assert len(history.frames) <= 41
    assert history.frames[-1][0] - history.frames[0][0] <= 4000
    assert history.add(10100, np.zeros((120, 100, 3), np.uint8)) is None
    assert len(history.frames) == 1


def test_sparse_source_frames_clear_stale_score():
    history = FightWindow()
    frame = np.zeros((100, 100, 3), np.uint8)
    for timestamp in range(0, 4001, 100):
        if history.add(timestamp, frame) is not None:
            history.score = .8
    assert history.score == .8
    for timestamp in range(4800, 12001, 800):
        if history.add(timestamp, frame) is not None:
            history.score = .8
    assert history.score is None
