"""Bounded, ephemeral public access to the fixed local X3D fight candidate.

This router does not use operator sessions, classroom storage, camera URLs or
filesystem inputs. Frames exist only in the active connection's short history.
"""
import asyncio
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import json
import math
import secrets
import struct
import time
from urllib.parse import urlsplit

import cv2
from fastapi import APIRouter, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

COOKIE = 'nivra_fight_session'
PREFIX = '/api/v2/fight'
MAX_FRAME_BYTES = 1_500_000


class FightWindow:
    """Causal four-second source history, independent of frame arrival speed."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.frames = deque(maxlen=48)
        self.last_received = self.last_sample = self.last_prediction = -1e9
        self.dimensions = None
        self.score = None

    def add(self, timestamp, frame):
        if timestamp <= self.last_received:
            raise ValueError('Non-increasing source timestamp')
        dimensions = frame.shape[:2]
        if timestamp - self.last_received > 1200 or dimensions != self.dimensions:
            self.frames.clear()
            self.last_sample = self.last_prediction = -1e9
            self.score = None
        self.last_received = timestamp
        self.dimensions = dimensions
        if timestamp - self.last_sample < 100:
            return None
        self.last_sample = timestamp
        self.frames.append((timestamp, cv2.resize(frame, (224, 224))))
        while self.frames and timestamp - self.frames[0][0] > 4000:
            self.frames.popleft()
        # The 200 ms tolerance matches the installed console candidate and
        # accommodates source sampling jitter; eight fast frames cannot warm up.
        if len(self.frames) < 8 or timestamp - self.frames[0][0] < 3800:
            if timestamp - self.last_prediction > 1200:
                self.score = None
            return None
        if timestamp - self.last_prediction < 400:
            return None
        self.last_prediction = timestamp
        return [image for _, image in self.frames]


def _strict_header(packet):
    """Reject coerced types and duplicate fields before image decoding."""
    if not isinstance(packet, bytes) or not 8 <= len(packet) <= MAX_FRAME_BYTES:
        raise ValueError('Invalid frame size')
    length = struct.unpack('<I', packet[:4])[0]
    if length > 1024 or length + 4 >= len(packet):
        raise ValueError('Invalid header size')

    def fields(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate header field')
            result[key] = value
        return result

    header = json.loads(packet[4:4 + length], object_pairs_hook=fields)
    if not isinstance(header, dict) or not {'version', 'streamId', 'timestampMs'} <= header.keys():
        raise ValueError('Invalid frame header')
    if header.keys() - {'version', 'streamId', 'timestampMs', 'maxPeople'}:
        raise ValueError('Unexpected frame field')
    for key in ('version', 'streamId', 'maxPeople'):
        if key in header and type(header[key]) is not int:
            raise ValueError('Invalid integer header field')
    timestamp = header['timestampMs']
    if type(timestamp) not in (int, float) or not math.isfinite(timestamp):
        raise ValueError('Invalid timestamp')


class FightDemo:
    """Own the model lifetime and a single connection, with injectable tests."""

    def __init__(self, unpack_frame, *, allowed_origins, model_factory=None,
                 clock=time.monotonic, session_ttl=1200, max_sessions=32,
                 idle_timeout=30, stream_timeout=900, frame_interval=.05,
                 require_cuda=True):
        self.unpack_frame = unpack_frame
        self.allowed_origins = set(allowed_origins)
        self.model_factory = model_factory
        self.clock = clock
        self.session_ttl = session_ttl
        self.max_sessions = max_sessions
        self.idle_timeout = idle_timeout
        self.stream_timeout = stream_timeout
        self.frame_interval = frame_interval
        self.require_cuda = require_cuda
        self.router = APIRouter(prefix=PREFIX)
        self.model = None
        self.failed = False
        self.busy = False
        self.sessions = {}
        self._executor = None
        self._load_task = None
        self._active_socket = None
        self._active_done = asyncio.Event()
        self._active_done.set()
        self._stopped = False
        self.router.add_api_route('/health', self.health, methods=['GET'])
        self.router.add_api_route('/session', self.session, methods=['POST'])
        self.router.add_api_websocket_route('/stream', self.stream)

    async def start(self):
        if self._load_task is not None:
            return
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='nivra-fight')
        self._load_task = asyncio.create_task(self._load())

    async def _work(self, function, *args):
        future = asyncio.get_running_loop().run_in_executor(self._executor, function, *args)
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            # Cancellation cannot stop a running CUDA thread. Wait for its real
            # completion before finally releases the GPU connection slot.
            try:
                await asyncio.shield(future)
            except Exception:
                pass
            raise

    async def _load(self):
        try:
            factory = self.model_factory
            if factory is None:
                def factory():
                    from .x3d_candidate import X3DCandidate
                    return X3DCandidate()
            model = await self._work(factory)
            device = str(getattr(model, 'device', ''))
            if self.require_cuda and not (device == 'cuda' or device.startswith('cuda:')):
                raise RuntimeError('GPU unavailable')
            self.model = model
        except Exception:
            self.failed = True

    async def stop(self):
        self._stopped = True
        if self._active_socket is not None:
            try:
                await self._active_socket.close(code=1001)
            except (RuntimeError, WebSocketDisconnect):
                pass
        await self._active_done.wait()
        if self._load_task is not None:
            await asyncio.shield(self._load_task)
        self.model = None
        self.sessions.clear()
        if self._executor is not None:
            # All submitted jobs have completed before this synchronous join.
            self._executor.shutdown(wait=True)
            self._executor = None

    async def health(self):
        status = ('disabled' if self._stopped else 'error' if self.failed else
                  'ready' if self.model is not None else 'loading')
        return {'status': status, 'backend': 'pc-gpu', 'model': 'X3D-M',
                'device': 'cuda' if self.model is not None else None,
                'experimental': True, 'windowSeconds': 4, 'busy': self.busy}

    def _same_origin(self, connection):
        origin = connection.headers.get('origin', '')
        if origin not in self.allowed_origins:
            return False
        host = connection.headers.get('host', '').lower()
        forwarded = any(name in connection.headers for name in
                        ('forwarded', 'x-forwarded-for', 'x-forwarded-host', 'x-forwarded-proto'))
        if not forwarded:
            return host == urlsplit(origin).netloc.lower()
        # Only the existing bounded public gateway rewrites the upstream Host.
        # These sessions grant access solely to the deliberately public router.
        return (connection.headers.get('x-forwarded-host') == 'nivra-public-gateway'
                and host in ('127.0.0.1:8765', 'localhost:8765')
                and origin.startswith('https://'))

    def _expire_sessions(self):
        now = self.clock()
        for token, expiry in list(self.sessions.items()):
            if expiry <= now:
                del self.sessions[token]

    async def session(self, request: Request):
        if not self._same_origin(request):
            return JSONResponse({'error': 'Origin rejected'}, status_code=403)
        self._expire_sessions()
        token = request.cookies.get(COOKIE, '')
        if token not in self.sessions:
            if len(self.sessions) >= self.max_sessions:
                return JSONResponse({'error': 'Demo is busy. Try again later.'}, status_code=503)
            token = secrets.token_urlsafe(32)
            self.sessions[token] = self.clock() + self.session_ttl
        lifetime = max(1, math.ceil(self.sessions[token] - self.clock()))
        response = Response(status_code=204)
        response.set_cookie(COOKIE, token, max_age=lifetime, httponly=True,
                            secure=request.headers.get('origin', '').startswith('https://'),
                            samesite='strict', path=PREFIX)
        response.headers['Cache-Control'] = 'no-store'
        return response

    async def stream(self, socket: WebSocket):
        self._expire_sessions()
        token = socket.cookies.get(COOKIE, '')
        if not self._same_origin(socket) or token not in self.sessions:
            await socket.close(code=1008)
            return
        if self.busy or self.model is None or self._stopped:
            await socket.close(code=1013)
            return
        self.busy = True
        self._active_done.clear()
        self._active_socket = socket
        history = FightWindow()
        current_stream = -1
        started = self.clock()
        last_received = -1e9
        try:
            await socket.accept()
            await socket.send_json({'type': 'ready', 'model': 'X3D-M',
                                    'windowSeconds': 4, 'device': 'cuda',
                                    'experimental': True})
            while not self._stopped:
                now = self.clock()
                remaining = min(self.sessions.get(token, now) - now,
                                started + self.stream_timeout - now)
                if remaining <= 0:
                    raise ValueError('Session expired')
                message = await asyncio.wait_for(socket.receive(), min(self.idle_timeout, remaining))
                if message['type'] == 'websocket.disconnect':
                    break
                delay = self.frame_interval - (self.clock() - last_received)
                if delay > 0:
                    await asyncio.sleep(delay)
                last_received = self.clock()
                if (self.sessions.get(token, 0) <= last_received or
                        last_received - started >= self.stream_timeout):
                    raise ValueError('Session expired')
                if message.get('text') is not None:
                    text = message['text']
                    if len(text.encode('utf-8')) > 128:
                        raise ValueError('Invalid control packet')
                    control = json.loads(text)
                    if (not isinstance(control, dict) or set(control) != {'type', 'streamId'} or
                            control['type'] != 'reset' or type(control['streamId']) is not int or
                            not current_stream < control['streamId'] <= 2**31 - 1):
                        raise ValueError('Invalid reset')
                    history.reset()
                    current_stream = control['streamId']
                    await socket.send_json({'type': 'reset', 'streamId': current_stream})
                    continue
                packet = message.get('bytes', b'')
                _strict_header(packet)
                header, frame = self.unpack_frame(packet)
                if header.streamId < current_stream:
                    raise ValueError('Expired stream generation')
                if header.streamId > current_stream:
                    history.reset()
                    current_stream = header.streamId
                frames = history.add(header.timestampMs, frame)
                inference_ms = 0
                if frames is not None:
                    before = time.perf_counter()
                    prediction = await self._work(self.model.predict, frames)
                    inference_ms = round((time.perf_counter() - before) * 1000, 2)
                    score = float(prediction['backboneScore'])
                    if not math.isfinite(score) or not 0 <= score <= 1:
                        raise RuntimeError('Invalid classifier output')
                    history.score = score
                status = ('warming' if history.score is None else
                          'review' if history.score > .5 else 'clear')
                await socket.send_json({'type': 'result', 'streamId': current_stream,
                                        'timestampMs': header.timestampMs, 'status': status,
                                        'classifierScore': history.score,
                                        'analyzed': frames is not None,
                                        'inferenceMs': inference_ms, 'windowSeconds': 4,
                                        'model': 'X3D-M', 'experimental': True})
        except WebSocketDisconnect:
            pass
        except (ValueError, asyncio.TimeoutError):
            await self._close(socket, 1008, 'Invalid input or session expired.')
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._close(socket, 1011, 'Inference unavailable. Restart analysis.')
        finally:
            history.reset()
            self._active_socket = None
            self.busy = False
            self._active_done.set()

    @staticmethod
    async def _close(socket, code, reason):
        try:
            await socket.close(code=code, reason=reason)
        except (RuntimeError, WebSocketDisconnect):
            pass
