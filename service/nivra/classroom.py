"""Four-camera pilot: latest-frame scheduling, scoped pairing, metadata-only storage.

JPEG-over-WebSocket deliberately avoids public STUN/TURN services. Remote phones
need an operator-configured HTTPS reverse proxy to this loopback service. No
public endpoint is provisioned here. All model execution stays on this computer.
"""
import asyncio
from collections import deque
import hashlib
import json
import os
import secrets
import struct
import time
from urllib.parse import urlsplit
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .classroom_store import Store

ADMIN_COOKIE = 'nivra_operator'
CAMERA_COOKIE = 'nivra_publisher'
LOCAL_ORIGINS = {'http://127.0.0.1:8765', 'http://localhost:8765'}


class CameraInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=50)
    building: str = Field(min_length=1, max_length=70)
    floor: str = Field(min_length=1, max_length=40)
    enabled: bool = True

    @field_validator('name', 'building', 'floor')
    @classmethod
    def clean(cls, value):
        value = value.strip()
        if not value or any(ord(c) < 32 for c in value): raise ValueError('Enter a location name.')
        return value


class PairInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(min_length=30, max_length=100)


class EventInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: str = Field(pattern='^(acknowledged|resolved)$')
    revision: int = Field(ge=0)


def public_origin():
    value = os.environ.get('NIVRA_PUBLIC_ORIGIN', '').rstrip('/')
    if value:
        parsed = urlsplit(value)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            raise ValueError('NIVRA_PUBLIC_ORIGIN must be a single HTTPS origin.')
    return value


def digest(value): return hashlib.sha256(value.encode()).hexdigest()


class Classroom:
    def __init__(self, state, pipeline_factory, unpack_frame, inference_lock, database=None):
        self.state, self.pipeline_factory, self.unpack_frame = state, pipeline_factory, unpack_frame
        self.inference_lock = inference_lock
        self.store = Store(database or os.environ.get('NIVRA_METADATA_DB', str(Path(__file__).resolve().parents[1]/'state'/'classrooms.sqlite')))
        self.public = public_origin()
        self.origins = LOCAL_ORIGINS | ({self.public} if self.public else set())
        self.admin_token = secrets.token_urlsafe(32)
        self.operator_invites, self.operator_sessions = {}, {}
        self.pairs, self.credentials, self.attempts = {}, {}, {}
        self.live, self.pending, self.viewers = {}, {}, set()
        self.order = deque()
        self.wake = asyncio.Event()
        self.task = None
        self.router = APIRouter(prefix='/api/v2')
        self.routes()

    async def start(self): self.task = asyncio.create_task(self.work())

    async def stop(self):
        if self.task:
            self.task.cancel()
            try: await self.task
            except asyncio.CancelledError: pass
        self.store.close()

    def authorized(self, request):
        return request.headers.get('origin') in self.origins and self.valid_operator(request)

    def valid_operator(self, request):
        value = request.cookies.get(ADMIN_COOKIE, '')
        if secrets.compare_digest(value, self.admin_token): return True
        return self.operator_sessions.get(digest(value), 0) > time.monotonic()

    def is_local(self, request):
        return (request.headers.get('origin') in LOCAL_ORIGINS
                and request.headers.get('host') in ('127.0.0.1:8765', 'localhost:8765')
                and not any(h in request.headers for h in ('forwarded', 'x-forwarded-for', 'x-forwarded-host', 'x-forwarded-proto', 'x-nivra-relay')))

    def require_admin(self, request):
        # Same-origin fetches can omit Origin for GET. Cookie plus Sec-Fetch-Site
        # covers those reads; all mutations and WebSockets require exact Origin.
        origin = request.headers.get('origin')
        read = getattr(request, 'method', '') == 'GET' and origin is None and request.headers.get('sec-fetch-site') in ('same-origin', None)
        if not (read or origin in self.origins) or not self.valid_operator(request):
            raise HTTPException(403, 'Operator session required')

    def snapshot(self):
        now = time.monotonic()
        cameras = []
        for camera in self.store.cameras():
            live = self.live.get(camera['id'])
            fresh = bool(live and now-live['received'] < 6)
            analysis_fresh = bool(fresh and live.get('analyzed') and now-live['analyzed'] < 5)
            cameras.append({**camera, 'enabled': bool(camera['enabled']),
                'feed': 'paused' if not camera['enabled'] else 'live' if fresh else 'waiting' if live else 'offline',
                'analysis': 'paused' if not camera['enabled'] else 'current' if analysis_fresh else 'waiting' if fresh and self.state['models'] else 'unavailable',
                'generation': live['generation'] if live else None,
                'result': live.get('result') if analysis_fresh else None,
                'framesReceived': live['frames'] if live else 0,
                'framesAnalyzed': live.get('analyzedCount',0) if live else 0,
                'framesReplaced': live['replaced'] if live else 0,
                'error': live.get('error') if live else None})
        return {'type':'snapshot', 'version':2, 'cameras':cameras, 'events':self.store.events(),
                'analytics':self.store.analytics(), 'service': 'error' if self.state['error'] else 'ready' if self.state['models'] else 'loading',
                'runtime': self.state['models'].runtime if self.state['models'] else None,
                'publicOrigin': self.public or None, 'retention':'event-records-only',
                'experimental':True, 'maxCameras':4}

    async def broadcast(self, value, binary=False):
        async def send(socket):
            try:
                await asyncio.wait_for(socket.send_bytes(value) if binary else socket.send_json(value), .5)
            except Exception:
                self.viewers.discard(socket)
                try: await socket.close(code=1013)
                except Exception: pass
        await asyncio.gather(*(send(socket) for socket in tuple(self.viewers)))

    def enqueue(self, camera_id, value):
        if camera_id in self.pending: self.live[camera_id]['replaced'] += 1
        else: self.order.append(camera_id)
        self.pending[camera_id] = value
        self.wake.set()

    async def work(self):
        while True:
            await self.wake.wait()
            if not self.order:
                self.wake.clear()
                continue
            camera_id = self.order.popleft()
            entry = self.pending.pop(camera_id, None)
            live = self.live.get(camera_id)
            if not entry or not live or entry[0] != live['generation'] or time.monotonic()-entry[3] > 1.5:
                continue
            generation, header, frame, received = entry
            if not self.state['models']: continue
            try:
                async with self.inference_lock:
                    if self.live.get(camera_id) is not live or time.monotonic()-received > 1.5: continue
                    if live.get('pipeline') is None:
                        live['pipeline'] = self.pipeline_factory(self.state['models'])
                        live['pipelineEpoch'] = live.get('pipelineEpoch',0)+1
                    window = [(t,image) for t,image in live['video'] if 0 <= header.timestampMs-t <= 4500]
                    result = await asyncio.to_thread(live['pipeline'].process, frame, header.timestampMs, min(50,self.state['models'].runtime.get('maxPeople',8)), video_frames=window)
                if self.live.get(camera_id) is not live or live['generation'] != generation: continue
                live['lastAnalyzedSource'] = header.timestampMs
                live['analyzed'], live['analyzedCount'] = time.monotonic(), live.get('analyzedCount',0)+1
                # Large poses/frames are never persisted. Results stay bounded in RAM.
                live['result'] = {k:result.get(k) for k in ('timestampMs','evidenceTimestampMs','inferenceMs','coverage','tracks','conflict','fightEvidence')}
                live['error'] = None
                for event in result.get('conflict',{}).get('events',[]): self.store.record(camera_id,f"{generation}-p{live['pipelineEpoch']}",event)
                await self.broadcast(self.snapshot())
            except asyncio.CancelledError: raise
            except Exception:
                live['error'] = 'Analysis failed; feed remains available. Reconnect to retry.'
                live['analyzed'] = None
                live['pipeline'] = None
                await self.broadcast(self.snapshot())

    async def disconnect_camera(self, camera_id):
        self.credentials = {k:v for k,v in self.credentials.items() if v != camera_id}
        self.pairs = {k:v for k,v in self.pairs.items() if v[0] != camera_id}
        self.pending.pop(camera_id,None)
        self.order = deque(c for c in self.order if c != camera_id)
        live = self.live.pop(camera_id,None)
        if live:
            try: await live['socket'].close(code=1000, reason='Camera disconnected by operator')
            except Exception: pass

    def routes(self):
        router = self.router

        @router.post('/session')
        async def session(request: Request):
            if self.authorized(request): return Response(status_code=204)
            if not self.is_local(request):
                raise HTTPException(403,'Unlock this dashboard using a link from the analysis PC.')
            response = Response(status_code=204)
            response.set_cookie(ADMIN_COOKIE,self.admin_token,httponly=True,samesite='strict',path='/api/v2')
            return response

        @router.post('/operator/invite')
        async def invite_operator(request: Request):
            self.require_admin(request)
            if not self.is_local(request) or not self.public:
                raise HTTPException(403, 'Create the public dashboard link on the analysis PC.')
            token = secrets.token_urlsafe(32)
            # Only the newest invitation remains valid; never persist credentials.
            self.operator_invites = {digest(token): time.monotonic()+300}
            return {'url': self.public+'/#operator='+token, 'expiresInSeconds': 300}

        @router.post('/operator/redeem')
        async def redeem_operator(data: PairInput, request: Request):
            if not self.public or request.headers.get('origin') != self.public:
                raise HTTPException(403, 'Open the public dashboard link.')
            now = time.monotonic()
            expires = self.operator_invites.pop(digest(data.token), 0)
            if expires < now:
                raise HTTPException(403, 'Dashboard link expired or already used. Generate a new link on the analysis PC.')
            self.operator_sessions = {k:v for k,v in self.operator_sessions.items() if v > now}
            if len(self.operator_sessions) >= 16: raise HTTPException(429, 'Operator session limit reached.')
            token = secrets.token_urlsafe(32)
            self.operator_sessions[digest(token)] = now+8*3600
            response = Response(status_code=204)
            response.set_cookie(ADMIN_COOKIE, token, httponly=True, secure=True, samesite='strict', path='/api/v2', max_age=8*3600)
            return response

        @router.post('/operator/logout')
        async def logout(request: Request):
            self.require_admin(request)
            key = digest(request.cookies.get(ADMIN_COOKIE, ''))
            self.operator_sessions.pop(key, None)
            for socket in tuple(self.viewers):
                if digest(socket.cookies.get(ADMIN_COOKIE, '')) == key:
                    await socket.close(code=1000)
                    self.viewers.discard(socket)
            response = Response(status_code=204)
            response.delete_cookie(ADMIN_COOKIE, path='/api/v2')
            return response

        @router.get('/state')
        async def get_state(request: Request):
            self.require_admin(request)
            return self.snapshot()

        @router.post('/cameras',status_code=201)
        async def add_camera(data: CameraInput, request: Request):
            self.require_admin(request)
            try: camera = self.store.add_camera(data.name,data.building,data.floor)
            except ValueError as error: raise HTTPException(409,str(error)) from error
            await self.broadcast(self.snapshot())
            return camera

        @router.patch('/cameras/{camera_id}')
        async def update_camera(camera_id: str, data: CameraInput, request: Request):
            self.require_admin(request)
            if not self.store.camera(camera_id): raise HTTPException(404,'Camera not found')
            camera = self.store.update_camera(camera_id,data.name,data.building,data.floor,data.enabled)
            if not data.enabled: await self.disconnect_camera(camera_id)
            await self.broadcast(self.snapshot())
            return camera

        @router.post('/cameras/{camera_id}/pair')
        async def pairing(camera_id: str, request: Request):
            self.require_admin(request)
            camera = self.store.camera(camera_id)
            if not camera or not camera['enabled']: raise HTTPException(409,'Enable the camera before pairing.')
            await self.disconnect_camera(camera_id)
            token = secrets.token_urlsafe(32)
            self.pairs[digest(token)] = (camera_id,time.monotonic()+300)
            origin = self.public or request.headers['origin']
            await self.broadcast(self.snapshot())
            return {'url':origin+'/camera#pair='+token,'expiresInSeconds':300,'remoteReady':bool(self.public)}

        @router.post('/camera/pair')
        async def redeem(data: PairInput, request: Request):
            if request.headers.get('origin') not in self.origins: raise HTTPException(403,'Origin rejected')
            # Global bounded redemption rate also covers proxy clients sharing one IP.
            now = time.monotonic()
            self.attempts = {k:v for k,v in self.attempts.items() if now-v < 60}
            if len(self.attempts) >= 20: raise HTTPException(429,'Wait one minute before pairing again.')
            self.attempts[secrets.token_hex(8)] = now
            pair = self.pairs.pop(digest(data.token),None)
            if not pair or pair[1] < now: raise HTTPException(403,'Pairing link expired or already used. Create another link on the dashboard.')
            credential = secrets.token_urlsafe(32)
            self.credentials[digest(credential)] = pair[0]
            response = Response(content=json.dumps(self.store.camera(pair[0])),media_type='application/json')
            response.set_cookie(CAMERA_COOKIE,credential,httponly=True,samesite='strict',secure=request.headers.get('origin','').startswith('https:'),path='/api/v2/camera')
            return response

        @router.get('/camera/session')
        async def camera_session(request: Request):
            camera_id = self.credentials.get(digest(request.cookies.get(CAMERA_COOKIE,'')))
            if not camera_id: raise HTTPException(403,'Pair this device from the dashboard.')
            return self.store.camera(camera_id)

        @router.patch('/events/{event_id}')
        async def transition(event_id: str, data: EventInput, request: Request):
            self.require_admin(request)
            try: event = self.store.transition(event_id,data.status,data.revision)
            except KeyError as error: raise HTTPException(404,'Event not found') from error
            except ValueError as error: raise HTTPException(409,str(error)) from error
            await self.broadcast(self.snapshot())
            return event

        @router.websocket('/operator')
        async def operator(socket: WebSocket):
            if not self.authorized(socket) or len(self.viewers)>=3:
                await socket.close(code=1008)
                return
            await socket.accept()
            self.viewers.add(socket)
            try:
                await socket.send_json(self.snapshot())
                while True:
                    if not self.valid_operator(socket):
                        await socket.close(code=1008)
                        break
                    try:
                        message = await asyncio.wait_for(socket.receive(),2)
                        if message['type']=='websocket.disconnect': break
                        if message.get('text') != 'ping': break
                    except asyncio.TimeoutError: await socket.send_json(self.snapshot())
            except (WebSocketDisconnect,RuntimeError): pass
            finally: self.viewers.discard(socket)

        @router.websocket('/camera/stream')
        async def camera_stream(socket: WebSocket):
            camera_id = self.credentials.get(digest(socket.cookies.get(CAMERA_COOKIE,'')))
            camera = self.store.camera(camera_id) if camera_id else None
            if socket.headers.get('origin') not in self.origins or not camera or not camera['enabled'] or camera_id in self.live:
                await socket.close(code=1008)
                return
            await socket.accept()
            generation = secrets.token_hex(12)
            live = dict(socket=socket,generation=generation,received=-1e10,frames=0,replaced=0,pipeline=None,video=deque(maxlen=64))
            self.live[camera_id] = live
            last_timestamp, last_preview = -1, -1e10
            recent_frames = deque()
            try:
                await socket.send_json({'type':'ready','cameraId':camera_id,'generation':generation,'maxFps':12})
                while True:
                    packet = await asyncio.wait_for(socket.receive_bytes(),15)
                    received_at = time.monotonic()
                    while recent_frames and received_at-recent_frames[0] > 1: recent_frames.popleft()
                    if len(recent_frames) >= 15: raise ValueError('Frame rate exceeded')
                    recent_frames.append(received_at)
                    header, frame = self.unpack_frame(packet)
                    if header.timestampMs <= last_timestamp: raise ValueError('Source timestamps must increase')
                    if header.timestampMs-last_timestamp > 1200 or (live['video'] and live['video'][-1][1].shape != frame.shape):
                        live['video'].clear()
                    last_timestamp = header.timestampMs
                    now = time.monotonic()
                    live['received'], live['frames'] = now, live['frames']+1
                    live['video'].append((header.timestampMs,frame))
                    while live['video'] and header.timestampMs-live['video'][0][0] > 4500: live['video'].popleft()
                    self.enqueue(camera_id,(generation,header,frame,now))
                    if now-last_preview >= .24:
                        length = struct.unpack('<I',packet[:4])[0]
                        metadata = json.dumps({'cameraId':camera_id,'generation':generation,'timestampMs':header.timestampMs,'width':frame.shape[1],'height':frame.shape[0]}).encode()
                        await self.broadcast(struct.pack('<I',len(metadata))+metadata+packet[4+length:],binary=True)
                        last_preview = now
                    await socket.send_json({'type':'accepted','timestampMs':header.timestampMs})
            except (WebSocketDisconnect,RuntimeError): pass
            except (ValueError,asyncio.TimeoutError):
                try: await socket.close(code=1008,reason='Invalid frame or camera timed out')
                except Exception: pass
            except Exception:
                # Invalid text/image packets must not log payloads or leave a
                # camera marked live. The client gets a bounded failure state.
                try: await socket.close(code=1008,reason='Unsupported camera frame')
                except Exception: pass
            finally:
                if self.live.get(camera_id) is live:
                    self.live.pop(camera_id,None)
                    self.pending.pop(camera_id,None)
                    self.order = deque(c for c in self.order if c != camera_id)
                await self.broadcast(self.snapshot())
