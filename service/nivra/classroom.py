"""Four-camera pilot: latest-frame scheduling, scoped pairing, metadata-only storage.

JPEG-over-WebSocket deliberately avoids public STUN/TURN services. Remote phones
need an operator-configured HTTPS reverse proxy to this loopback service. No
public endpoint is provisioned here. All model execution stays on this computer.
"""
import asyncio
from collections import deque
import hashlib
from http.cookies import SimpleCookie, CookieError
import json
import math
import os
import secrets
import struct
import time
from urllib.parse import urlsplit
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Request, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .classroom_store import Store
from .socket_tickets import SocketTickets
from .auth import AuthService, Principal, SocketAuth, allowed_origins, install_routes
from .sites import CameraPatch, GPS, GuardProfile, Name, camera_payload, floor_payload, guard_payload, role_dependency, store_call
from .preview_relay import PreviewRelay
from .push import GuardPush, register_routes as register_push_routes
from .device_analysis import DeviceStatus, DeviceMotionStatus, DeviceResult, DeviceMotion, result_payload, MODEL as DEVICE_MODEL, MAX_PEOPLE as DEVICE_MAX_PEOPLE, MAX_REPORT_BYTES
from .clips import Clips, signed_frame_url, valid_frame_signature
from .auth import require_role

ADMIN_COOKIE = 'nivra_operator'
CAMERA_COOKIE = 'nivra_publisher'
GUARD_COOKIE = 'nivra_guard'
GUARD_SNAPSHOT_SECONDS = 10


def pc_pose_payload(poses):
    """Convert the pipeline's existing MediaPipe topology to observed wire joints.

    drawable_pose already maps COCO-17 into 33 slots. Its zero-visibility
    placeholders are absent joints, never measured coordinates.
    """
    if not isinstance(poses, (list, tuple)):
        return []
    result = []
    for pose in poses[:DEVICE_MAX_PEOPLE]:
        if not isinstance(pose, (list, tuple)) or len(pose) != 33:
            continue
        joints = []
        for point in pose:
            values = [point.get(key) for key in ('x', 'y', 'visibility')] if isinstance(point, dict) else []
            valid = len(values) == 3 and all(
                isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value) and 0 <= value <= 1 for value in values)
            joints.append([round(float(value), 4) for value in values] if valid and values[2] > 0 else None)
        if any(point is not None for point in joints):
            result.append(joints)
    return result


class CameraInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: Name
    building: Name
    floor: Name
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


PAIR_CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'

class DevicePairInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str | None = Field(default=None, min_length=30, max_length=100)
    code: str | None = Field(default=None, pattern=r'^[A-HJ-NP-Z2-9]{8}$')

    @field_validator('code', mode='before')
    @classmethod
    def clean_code(cls, value):
        return value.strip().replace(' ', '').replace('-', '').upper() if isinstance(value, str) else value

    @model_validator(mode='after')
    def one_capability(self):
        if (self.token is None) == (self.code is None): raise ValueError('Use one pairing link or code.')
        return self


class PairCodeAttempts:
    """Bound guesses before any cross-workspace scan, without unbounded IP keys."""
    def __init__(self): self.recent = deque()

    def check(self, request):
        now = time.monotonic()
        while self.recent and now-self.recent[0][1] >= 60: self.recent.popleft()
        ip = request.client.host if request.client else 'unknown'
        if len(self.recent) >= 100 or sum(peer == ip for peer, _ in self.recent) >= 20:
            raise HTTPException(429, 'Wait one minute before trying another pairing code.')
        self.recent.append((ip, now))


class EventInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: str = Field(pattern='^(acknowledged|resolved)$')
    revision: int = Field(ge=0)


class TestEventInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    cameraId: str = Field(min_length=1, max_length=100)


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['view', 'confirm', 'dismiss', 'alert', 'on_scene', 'clear']
    revision: int = Field(ge=0)
    reason: Literal['play_sport', 'greeting', 'camera_glitch', 'other'] | None = None
    note: str | None = Field(default=None, max_length=280)
    guard: str | None = Field(default=None, pattern=r'^G[0-9]{1,2}$')

    @field_validator('note')
    @classmethod
    def clean_note(cls, value):
        if value is None: return None
        if any(ord(c) < 32 for c in value): raise ValueError('Control characters are not allowed.')
        return value.strip() or None


class GuardActionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['ack', 'decline', 'on_scene', 'clear']
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
        self.origins = allowed_origins(self.public)
        self.auth = AuthService(self.origins)
        self.socket_tickets = SocketTickets(os.environ.get('NIVRA_SOCKET_ORIGIN', ''))
        self.admin_token = secrets.token_urlsafe(32)
        self.operator_invites, self.operator_sessions = {}, {}
        self.pairs, self.credentials, self.attempts = {}, {}, {}
        self.pair_codes = {'camera': {}, 'guard': {}}
        self.code_attempts = PairCodeAttempts()
        self.guard_pairs, self.guard_credentials, self.guard_attempts = {}, {}, {}
        for session in self.store.device_sessions():
            if session['kind'] == 'camera': self.credentials[session['token_hash']] = session['subject_id']
            else:
                guard = self.store.guard(session['subject_id'])
                self.guard_credentials[session['token_hash']] = (guard['callsign'],time.monotonic()+session['expires']-time.time())
        self.guard_sockets = {}
        self.live, self.pending, self.viewers = {}, {}, set()
        self.relays = {}
        self.socket_auth = {}
        self.order = deque()
        self.wake = asyncio.Event()
        self.task = None
        self.snapshot_task = None
        self.last_test_event_at = float('-inf')
        self.clips = Clips()
        self.clip_task = None
        self.analysis_ms = 0.0
        self.analysis_samples = 0
        self.router = APIRouter(prefix='/api/v2')
        install_routes(self)
        self.push = GuardPush(self)
        self.routes()
        register_push_routes(self)

    def prune_device_pairs(self, kind):
        attribute = 'pairs' if kind == 'camera' else 'guard_pairs'
        now = time.monotonic()
        pairs = {key: value for key, value in getattr(self, attribute).items() if value[1] > now}
        setattr(self, attribute, pairs)
        self.pair_codes[kind] = {key: target for key, target in self.pair_codes[kind].items() if target in pairs}
        return pairs

    def mint_device_pair(self, kind, subject):
        pairs = self.prune_device_pairs(kind)
        # Only hashes persist in memory. Codes and QR tokens share one record.
        token = secrets.token_urlsafe(32)
        for _ in range(8):
            code = ''.join(secrets.choice(PAIR_CODE_ALPHABET) for _ in range(8))
            key = digest(code)
            if all(key not in aliases for aliases in self.pair_codes.values()): break
        else: raise HTTPException(503, 'Could not create a pairing code. Try again.')
        pair_key = digest(token)
        pairs[pair_key] = (subject, time.monotonic()+300)
        self.pair_codes[kind][key] = pair_key
        return token, code

    def device_pair(self, kind, data):
        pairs = self.prune_device_pairs(kind)
        key = self.pair_codes[kind].get(digest(data.code)) if data.code is not None else digest(data.token)
        return key, pairs.get(key)

    def consume_device_pair(self, kind, key):
        pairs = self.pairs if kind == 'camera' else self.guard_pairs
        pairs.pop(key, None)
        self.prune_device_pairs(kind)

    async def start(self):
        self.auth.log_mode()
        self.task = asyncio.create_task(self.work())
        await self.push.start()
        async def expire_clips():
            while True:
                await asyncio.sleep(1)
                self.clips.prune()
        self.clip_task = asyncio.create_task(expire_clips())

    async def stop(self):
        await self.push.stop()
        if self.clip_task:
            self.clip_task.cancel()
            try: await self.clip_task
            except asyncio.CancelledError: pass
        for socket in tuple(self.guard_sockets): await self.close_guard_socket(socket)
        if self.snapshot_task:
            self.snapshot_task.cancel()
            try: await self.snapshot_task
            except asyncio.CancelledError: pass
        for relay in tuple(self.relays.values()): await relay.close()
        self.relays.clear()
        if self.task:
            self.task.cancel()
            try: await self.task
            except asyncio.CancelledError: pass
        self.clips.close()
        self.store.close()

    def authorized(self, request):
        return request.headers.get('origin') in self.origins and self.valid_operator(request)

    def valid_operator(self, request):
        try:
            principal = self.auth.principal(request)
            if principal is not None: return principal.role in ('admin', 'reviewer')
        except HTTPException: return False
        return self.legacy_operator(request)

    def legacy_operator(self, request):
        if self.auth.mode != 'dev': return False
        value = request.cookies.get(ADMIN_COOKIE, '')
        if secrets.compare_digest(value, self.admin_token): return True
        return self.operator_sessions.get(digest(value), 0) > time.monotonic()

    def is_local(self, request):
        try: self.auth.dev_host(request)
        except HTTPException: return False
        return True

    def require_admin(self, request):
        return self.require_principal(request, ('admin',))

    def require_reviewer(self, request):
        return self.require_principal(request, ('reviewer', 'admin'))

    def require_principal(self, request, roles):
        self.auth.origin_check(request)
        principal = self.auth.principal(request)
        if principal is None and self.legacy_operator(request):
            principal = Principal('dev_legacy_operator', None, 'Local operator', 'admin', 'dev')
        if principal is None: raise HTTPException(403 if self.auth.mode == 'dev' else 401, 'Sign in required')
        if principal.role not in roles: raise HTTPException(403, 'NIVRA role required')
        return principal

    def guard_for_principal(self, principal):
        if principal.role != 'guard': raise HTTPException(403, 'Guard role required')
        lookup = getattr(self.store, 'guard_by_user', None)
        if lookup:
            record = lookup(principal.user_id)
            if not record and principal.email: record = self.store.guard_by_email(principal.email)
            if not record and principal.callsign: record = self.store.guard_by_callsign(principal.callsign)
            if not record: raise HTTPException(403, 'Link a guard record before signing in')
            # Demo identities are process-local; do not persist links that would
            # strand a guard after restart or replace a real Clerk association.
            if principal.auth_mode == 'dev': return record['callsign']
            assigned = record.get('user_id') or record.get('userId')
            if assigned and assigned != principal.user_id: raise HTTPException(403, 'Guard record belongs to another user')
            if not assigned:
                try: self.store.link_guard_user(record['id'], principal.user_id)
                except ValueError as error: raise HTTPException(403, 'Guard link unavailable') from error
            return record['callsign']
        if not principal.callsign: raise HTTPException(403, 'Guard callsign required')
        return principal.callsign

    async def websocket_auth(self, socket, roles=('reviewer', 'admin')):
        def legacy():
            if 'guard' in roles:
                guard = self.legacy_guard_identity(socket)
                if guard: return Principal('dev_legacy_guard_'+guard, None, guard, 'guard', 'dev', guard)
            elif self.legacy_operator(socket):
                return Principal('dev_legacy_operator', None, 'Local operator', 'admin', 'dev')
            return None
        def resolve(principal):
            if principal.user_id.startswith('dev_legacy_guard_'): return principal.callsign
            return self.guard_for_principal(principal)
        session = SocketAuth(self.auth, socket, roles, legacy=legacy,
                             resolve=resolve if 'guard' in roles else None)
        return await session.handshake()

    def snapshot(self):
        now = time.monotonic()
        paired_cameras = {row['subject_id'] for row in self.store.db.execute('''
            SELECT DISTINCT session.subject_id FROM device_sessions session
            JOIN cameras camera ON camera.id=session.subject_id
            WHERE session.kind='camera' AND session.expires>? AND camera.enabled=1
            ''', (time.time(),))}
        cameras = []
        for camera in self.store.cameras():
            live = self.live.get(camera['id'])
            fresh = bool(live and now-live['received'] < 6)
            analysis_window = 6 if live and live.get('compute') == 'device' else 5
            analysis_fresh = bool(fresh and live.get('analyzed') and now-live['analyzed'] < analysis_window)
            motion_fresh = bool(fresh and now-live['received'] < 3 and live.get('motionAnalyzed') and now-live['motionAnalyzed'] < 3)
            cameras.append({**camera_payload(camera),
                'paired': camera['id'] in paired_cameras,
                'feed': 'paused' if not camera['enabled'] else 'live' if fresh else 'waiting' if live else 'offline',
                'analysis': 'paused' if not camera['enabled'] else 'current' if analysis_fresh else 'waiting' if fresh and (self.state['models'] or live.get('deviceStatus',{}).get('state') in ('loading','ready')) else 'unavailable',
                'compute': live.get('compute','pc') if live else None,
                'deviceStatus': live.get('deviceStatus') if live else None,
                'generation': live['generation'] if live else None,
                'result': live.get('result') if analysis_fresh else None,
                'motionResult': live.get('motionResult') if motion_fresh else None,
                'motionStatus': live.get('motionStatus') if live else None,
                'framesReceived': live['frames'] if live else 0,
                'framesAnalyzed': live.get('analyzedCount',0) if live else 0,
                'framesReplaced': live['replaced'] if live else 0,
                'error': live.get('error') if live else None})
        events = self.store.events()
        self.clips.prune()
        for event in events: event['clip'] = self.clips.summary(event['id'], prune=False)
        return {'type':'snapshot', 'version':3, 'serverTime':time.time()*1000, 'me':{'role':'reviewer'},
                'site':self.store.site(), 'floors':[floor_payload(floor) for floor in self.store.floors()],
                'guards':[self.guard_payload(guard) for guard in self.store.guards()], 'cameras':cameras, 'events':events,
                'analytics':self.store.analytics(), 'service': 'error' if self.state['error'] else 'ready' if self.state['models'] or self.state.get('relayOnly') else 'loading',
                'runtime': self.runtime(),
                'publicOrigin': self.public or None, 'retention':'event-records-only',
                'experimental':True, 'maxCameras':self.store.max_cameras, 'activeViewers':len(self.viewers), 'maxViewers':8}

    async def broadcast(self, value, binary=False, camera_id=None):
        # Never await a viewer on the camera capture or GPU scheduling path.
        for socket in tuple(self.viewers):
            relay = self.relays.get(socket)
            if relay:
                if not binary:
                    for camera in value['cameras']:
                        if camera['feed'] != 'live': relay.discard(camera['id'])
                authentication = self.socket_auth.get(socket)
                if authentication and not binary:
                    relay.offer('snapshot', {**value, 'me': {'role': authentication.principal.role}})
                else:
                    relay.offer(camera_id if binary else 'snapshot', value, binary)
        if not binary:
            snapshots = {}
            for socket, (guard, key, relay) in tuple(self.guard_sockets.items()):
                authentication = self.socket_auth.get(socket)
                if not self.guard_stream_valid(socket, authentication, key):
                    # The stream's expiry timer closes it; never block capture on a guard.
                    relay.discard('snapshot')
                    continue
                if guard not in snapshots: snapshots[guard] = self.guard_snapshot(guard)
                relay.offer('snapshot', snapshots[guard])

    def guard_stream_valid(self, socket, authentication, key):
        if authentication is None or time.monotonic() >= authentication.deadline: return False
        record = self.store.guard_by_callsign(authentication.identity)
        if not record or record['id'] != authentication.guard_id: return False
        principal = authentication.principal
        if principal.user_id.startswith('dev_legacy_guard_'):
            credential = self.guard_credentials.get(key)
            session = self.store.device_session(key,'guard')
            return credential is not None and credential[1] > time.monotonic() and session is not None and session['subject_id'] == authentication.guard_id
        if self.auth.mode == 'dev':
            try: current = self.auth.dev_principal(socket)
            except HTTPException: return False
            return current is not None and current.user_id == principal.user_id and current.role == 'guard'
        return (principal.user_id not in self.auth.removed_users
                and self.auth.invalid_before.get(principal.user_id, 0) <= getattr(authentication, 'verified_at', 0))

    def guard_identity(self, request):
        try:
            principal = self.auth.principal(request)
            if principal: return self.guard_for_principal(principal)
        except HTTPException: return None
        return self.legacy_guard_identity(request)

    def legacy_guard_identity(self, request):
        if self.auth.mode != 'dev': return None
        key = digest(request.cookies.get(GUARD_COOKIE, ''))
        credential = self.guard_credentials.get(key)
        session = self.store.device_session(key,'guard')
        guard = self.store.guard(session['subject_id']) if session else None
        if credential and credential[1] > time.monotonic() and guard and guard['callsign'] == credential[0]: return credential[0]
        return None

    def camera_identity(self, request):
        key = digest(request.cookies.get(CAMERA_COOKIE,''))
        session = self.store.device_session(key,'camera')
        camera_id = self.credentials.get(key)
        return camera_id if session and session['subject_id'] == camera_id else None

    def require_guard(self, request):
        self.auth.origin_check(request)
        principal = self.auth.principal(request)
        if principal is not None: return self.guard_for_principal(principal)
        origin = request.headers.get('origin')
        read = getattr(request, 'method', '') == 'GET' and origin is None and request.headers.get('sec-fetch-site') in ('same-origin', None)
        guard = self.guard_identity(request)
        if not guard or not (read or origin in self.origins):
            raise HTTPException(403, 'Guard session required')
        return guard

    def guard_payload(self, guard):
        return {**guard_payload(guard), 'presence': self.push.presence(guard['callsign']),
                'push': self.push.has_subscription(guard['id'])}

    def guard_snapshot(self, guard):
        now = time.time()*1000
        record = self.store.guard_by_callsign(guard)
        floor = self.store.floor(record['floor_id']) if record and record['floor_id'] else None
        alerts = self.store.guard_alerts(guard, now) if record else []
        for alert in alerts:
            camera = self.store.camera(alert['camera_id'])
            alert['placement'] = camera_payload(camera)['placement'] if camera else None
            alert['floorId'] = camera['floor_id'] if camera else None
        return dict(type='guard-snapshot', version=2, guard=self.guard_payload(record) if record else None,
                    floor=floor_payload(floor) if floor else None, serverTime=now, alerts=alerts)

    def guard_disconnected(self, socket):
        entry = self.guard_sockets.pop(socket, None)
        self.socket_auth.pop(socket, None)
        if entry: self.schedule_snapshot()
        return entry

    async def close_guard_socket(self, socket):
        entry = self.guard_disconnected(socket)
        if entry:
            await entry[2].close()
            try: await asyncio.wait_for(socket.close(code=1008), .5)
            except Exception: pass

    async def revoke_guard(self, guard=None, key=None):
        if key is not None: self.store.revoke_device_sessions(kind='guard',token_hash=key)
        for credential_key, value in tuple(self.guard_credentials.items()):
            if value[0] == guard or credential_key == key:
                self.store.revoke_device_sessions(kind='guard',token_hash=credential_key)
        record = self.store.guard_by_callsign(guard) if guard is not None else None
        if record: self.store.revoke_device_sessions(kind='guard',subject_id=record['id'])
        self.guard_credentials = {k:v for k,v in self.guard_credentials.items()
                                  if not (v[0] == guard or k == key)}
        if guard is not None:
            self.guard_pairs = {k:v for k,v in self.guard_pairs.items() if v[0] != guard}
            self.prune_device_pairs('guard')
        for socket, (assigned, credential_key, _) in tuple(self.guard_sockets.items()):
            if assigned == guard or credential_key == key: await self.close_guard_socket(socket)

    def schedule_snapshot(self):
        # Four cameras share one bounded update, rather than rebuilding the
        # complete event history and React dashboard on every pose result.
        if self.snapshot_task is None or self.snapshot_task.done():
            async def publish():
                await asyncio.sleep(.2)
                await self.broadcast(self.snapshot())
            self.snapshot_task = asyncio.create_task(publish())

    def enqueue(self, camera_id, value):
        if camera_id in self.pending: self.live[camera_id]['replaced'] += 1
        else: self.order.append(camera_id)
        self.pending[camera_id] = value
        self.wake.set()

    def runtime(self):
        if self.state.get('relayOnly'):
            return dict(device='camera-device', compute='camera-device', personModel='MediaPipe Pose Lite',
                        fightModel=DEVICE_MODEL, maxPeople=DEVICE_MAX_PEOPLE, fallbackReason=self.state.get('fallbackReason'))
        models = self.state.get('models')
        if not models: return None
        cameras = max(1, sum(live['compute'] == 'pc' for live in self.live.values()))
        return dict(models.runtime, analysisMs=round(self.analysis_ms, 2),
                    targetFpsPerCamera=round(min(6, 800 / max(1, self.analysis_ms) / cameras), 2))

    def record_event(self, camera_id, generation, event):
        if not self.store.record(camera_id, generation, event): return False
        # Store.record returns a bool; resolve the inserted row without changing H2's schema/API.
        row = self.store.db.execute('SELECT id FROM events WHERE camera_id=? AND generation=? AND source_id=?',
                                    (camera_id, generation, str(event['id'])[:120])).fetchone()
        if row: self.clips.capture(row['id'], camera_id)
        return True

    def device_fallback(self, reason):
        self.state['relayOnly'] = True
        self.state['fallbackReason'] = reason
        self.state['error'] = None
        self.pending.clear()
        self.order.clear()
        for live in self.live.values():
            live['compute'] = 'device'
            live['pipeline'] = None
            live['video'].clear()
            live['analyzed'], live['result'] = None, None

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
            if not self.state['models'] or self.state.get('relayOnly') or live['compute'] != 'pc': continue
            cameras = max(1, sum(item['compute'] == 'pc' for item in self.live.values()))
            interval = max(1 / 6, self.analysis_ms / 1000 * cameras / .8)
            if time.monotonic() - live.get('analysisStarted', -1e10) < interval:
                continue
            try:
                async with self.inference_lock:
                    if self.live.get(camera_id) is not live or time.monotonic()-received > 1.5: continue
                    if live.get('pipeline') is None:
                        live['pipeline'] = self.pipeline_factory(self.state['models'])
                        live['pipelineEpoch'] = live.get('pipelineEpoch',0)+1
                    window = [(t,image) for t,image in live['video'] if 0 <= header.timestampMs-t <= 4500]
                    live['analysisStarted'] = time.monotonic()
                    result = await asyncio.to_thread(live['pipeline'].process, frame, header.timestampMs, min(50,self.state['models'].runtime.get('maxPeople',8)), video_frames=window)
                elapsed = (time.monotonic() - live['analysisStarted']) * 1000
                self.analysis_samples += 1
                self.analysis_ms = elapsed if not self.analysis_ms else .2 * elapsed + .8 * self.analysis_ms
                if self.live.get(camera_id) is not live or live['generation'] != generation: continue
                live['lastAnalyzedSource'] = header.timestampMs
                live['analyzed'], live['analyzedCount'] = time.monotonic(), live.get('analyzedCount',0)+1
                # Large poses/frames are never persisted. Results stay bounded in RAM.
                live['result'] = {k:result.get(k) for k in ('timestampMs','evidenceTimestampMs','inferenceMs','coverage','tracks','conflict','fightEvidence')}
                live['result']['poses'] = pc_pose_payload(result.get('poses'))
                live['error'] = None
                for event in result.get('conflict',{}).get('events',[]): self.record_event(camera_id,f"{generation}-p{live['pipelineEpoch']}",event)
                if (self.state['models'].runtime.get('device') in ('cpu', 'mps') and self.analysis_samples >= 12
                        and self.analysis_ms * cameras > 800 and os.environ.get('NIVRA_AUTO_RELAY', '1') != '0'):
                    self.device_fallback('Server analysis cannot sustain 1 fps per camera; using camera-device analysis.')
                await self.broadcast(self.snapshot())
            except asyncio.CancelledError: raise
            except Exception:
                if self.state['models'].runtime.get('device') in ('cpu', 'mps') and os.environ.get('NIVRA_AUTO_RELAY', '1') != '0':
                    self.device_fallback('Local model inference is unsupported or failed; using camera-device analysis.')
                live['error'] = 'Analysis failed; feed remains available. Reconnect to retry.'
                live['analyzed'] = None
                live['pipeline'] = None
                await self.broadcast(self.snapshot())

    async def disconnect_camera(self, camera_id, *, revoke=True):
        self.clips.disconnect(camera_id)
        if revoke:
            keys = {key for key, subject in self.credentials.items() if subject == camera_id}
            def keep_ticket(entry):
                if entry.get('path') != '/api/v2/camera/stream': return True
                try: credential = SimpleCookie(entry.get('cookie', '')).get(CAMERA_COOKIE)
                except CookieError: return False
                return credential is None or digest(credential.value) not in keys
            self.socket_tickets.pending = {key: entry for key, entry in self.socket_tickets.pending.items() if keep_ticket(entry)}
            self.store.revoke_device_sessions(kind='camera',subject_id=camera_id)
            self.credentials = {k:v for k,v in self.credentials.items() if v != camera_id}
        self.pairs = {k:v for k,v in self.pairs.items() if v[0] != camera_id}
        self.prune_device_pairs('camera')
        self.pending.pop(camera_id,None)
        self.order = deque(c for c in self.order if c != camera_id)
        live = self.live.pop(camera_id,None)
        if live:
            try: await asyncio.wait_for(live['socket'].close(code=1000, reason='Camera disconnected by operator'), .5)
            except Exception: pass

    def routes(self):
        router = self.router

        @router.post('/session')
        async def session(request: Request):
            self.auth.dev_only()
            if self.authorized(request): return Response(status_code=204)
            if not self.is_local(request):
                raise HTTPException(403,'Unlock this dashboard using a link from the analysis PC.')
            response = Response(status_code=204)
            response.set_cookie(ADMIN_COOKIE,self.admin_token,httponly=True,samesite='strict',path='/api/v2')
            return response

        @router.post('/operator/invite')
        async def invite_operator(request: Request):
            self.auth.dev_only()
            self.require_admin(request)
            if not self.is_local(request) or not self.public:
                raise HTTPException(403, 'Create the public dashboard link on the analysis PC.')
            token = secrets.token_urlsafe(32)
            # Only the newest invitation remains valid; never persist credentials.
            self.operator_invites = {digest(token): time.monotonic()+300}
            return {'url': self.public+'/wall#operator='+token, 'expiresInSeconds': 300}

        @router.post('/operator/redeem')
        async def redeem_operator(data: PairInput, request: Request):
            self.auth.dev_only()
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
            self.auth.dev_only()
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

        @router.post('/operator/socket-ticket')
        async def operator_socket_ticket(request: Request):
            self.require_reviewer(request)
            return self.socket_tickets.mint('operator', request)

        @router.post('/guard/socket-ticket')
        async def guard_socket_ticket(request: Request):
            self.require_guard(request)
            return self.socket_tickets.mint('guard', request)

        @router.post('/camera/socket-ticket')
        async def camera_socket_ticket(request: Request):
            self.auth.origin_check(request)
            camera_id = self.camera_identity(request)
            camera = self.store.camera(camera_id) if camera_id else None
            if not camera or not camera['enabled']:
                raise HTTPException(403, 'Pair this device from the dashboard.')
            return self.socket_tickets.mint('camera', request)

        @router.get('/state')
        async def get_state(request: Request):
            principal = self.require_reviewer(request)
            return {**self.snapshot(), 'me': {'role': principal.role}}

        @router.post('/cameras',status_code=201)
        async def add_camera(data: CameraInput, request: Request):
            self.require_admin(request)
            try: camera = self.store.add_camera(data.name,data.building,data.floor)
            except ValueError as error: raise HTTPException(409,str(error)) from error
            await self.broadcast(self.snapshot())
            return camera_payload(camera)

        @router.delete('/cameras/{camera_id}', status_code=204)
        async def delete_camera(camera_id: str, request: Request):
            self.require_admin(request)
            # Remove the DB identity before awaiting a socket close. No new
            # credential can be redeemed while that close is in progress.
            store_call(self.store.delete_camera, camera_id)
            await self.disconnect_camera(camera_id)
            await self.broadcast(self.snapshot())
            return Response(status_code=204)

        @router.patch('/cameras/{camera_id}', dependencies=[Depends(role_dependency(self, 'admin'))])
        async def update_camera(camera_id: str, data: CameraPatch, request: Request):
            camera = store_call(self.store.patch_camera, camera_id, **data.model_dump(exclude_unset=True))
            if not camera['enabled']: await self.disconnect_camera(camera_id)
            await self.broadcast(self.snapshot())
            return camera_payload(camera)

        @router.post('/cameras/{camera_id}/pair')
        async def pairing(camera_id: str, request: Request):
            self.require_reviewer(request)
            camera = self.store.camera(camera_id)
            if not camera or not camera['enabled']: raise HTTPException(409,'Enable the camera before pairing.')
            await self.disconnect_camera(camera_id)
            camera = self.store.camera(camera_id)
            if not camera or not camera['enabled']: raise HTTPException(409, 'Camera is no longer available.')
            token, code = self.mint_device_pair('camera', camera_id)
            origin = self.public or request.headers['origin']
            await self.broadcast(self.snapshot())
            return {'url':origin+'/camera#pair='+token,'pairingCode':code,'expiresInSeconds':300,'remoteReady':bool(self.public)}

        @router.post('/camera/pair')
        async def redeem(data: DevicePairInput, request: Request):
            if request.headers.get('origin') not in self.origins: raise HTTPException(403,'Origin rejected')
            if data.code is not None: self.code_attempts.check(request)
            # Global bounded redemption rate also covers proxy clients sharing one IP.
            now = time.monotonic()
            self.attempts = {k:v for k,v in self.attempts.items() if now-v < 60}
            if len(self.attempts) >= 20: raise HTTPException(429,'Wait one minute before pairing again.')
            self.attempts[secrets.token_hex(8)] = now
            pair_key, pair = self.device_pair('camera', data)
            if not pair or pair[1] <= now: raise HTTPException(403,'Pairing link expired or already used. Create another link on the dashboard.')
            camera = self.store.camera(pair[0])
            if not camera or not camera['enabled']: raise HTTPException(403, 'Camera is no longer available')
            self.consume_device_pair('camera', pair_key)
            credential = secrets.token_urlsafe(32)
            self.store.save_device_session(digest(credential),'camera',pair[0],time.time()+30*86400)
            self.credentials[digest(credential)] = pair[0]
            self.store.patch_camera(pair[0], gps=None)
            await self.broadcast(self.snapshot())
            response = Response(content=json.dumps(camera_payload(self.store.camera(pair[0]))),media_type='application/json')
            response.set_cookie(CAMERA_COOKIE,credential,httponly=True,samesite='strict',secure=request.headers.get('origin','').startswith('https:'),path='/api/v2/camera',max_age=30*86400)
            return response

        @router.get('/camera/session')
        async def camera_session(request: Request):
            camera_id = self.camera_identity(request)
            if not camera_id: raise HTTPException(403,'Pair this device from the dashboard.')
            return camera_payload(self.store.camera(camera_id))

        @router.post('/camera/logout', status_code=204)
        async def camera_logout(request: Request):
            if request.headers.get('origin') not in self.origins: raise HTTPException(403,'Origin rejected')
            camera_id = self.camera_identity(request)
            if camera_id: await self.disconnect_camera(camera_id)
            response = Response(status_code=204)
            response.delete_cookie(CAMERA_COOKIE,path='/api/v2/camera')
            return response

        @router.post('/camera/location')
        async def camera_location(data: GPS, request: Request):
            if request.headers.get('origin') not in self.origins:
                raise HTTPException(403, 'Origin rejected')
            camera_id = self.camera_identity(request)
            camera = self.store.camera(camera_id) if camera_id else None
            if not camera or not camera['enabled']:
                raise HTTPException(403, 'Pair this device from the dashboard.')
            camera = self.store.patch_camera(camera_id, gps=data.model_dump())
            await self.broadcast(self.snapshot())
            return camera_payload(camera)

        @router.post('/guards/{guard}/pair')
        async def pair_guard(request: Request, guard: str = PathParam(pattern=r'^G[0-9]{1,2}$')):
            self.require_admin(request)
            if not self.store.guard_by_callsign(guard):
                raise HTTPException(404, 'Guard not found')
            await self.revoke_guard(guard=guard)
            token, code = self.mint_device_pair('guard', guard)
            origin = self.public or request.headers['origin']
            return dict(url=origin+'/guard#pair='+token, pairingCode=code, expiresInSeconds=300, remoteReady=bool(self.public))

        @router.post('/guard/pair')
        async def redeem_guard(data: DevicePairInput, request: Request):
            if request.headers.get('origin') not in self.origins: raise HTTPException(403, 'Origin rejected')
            if data.code is not None: self.code_attempts.check(request)
            principal = self.auth.require(request, ('guard',)) if self.auth.mode == 'clerk' else None
            now = time.monotonic()
            self.guard_attempts = {k:v for k,v in self.guard_attempts.items() if now-v < 60}
            if len(self.guard_attempts) >= 20: raise HTTPException(429, 'Wait one minute before pairing again.')
            self.guard_attempts[secrets.token_hex(8)] = now
            pair_key, pair = self.device_pair('guard', data)
            if pair is None or pair[1] <= now:
                raise HTTPException(403, 'Pairing link expired or already used. Create another link on the dashboard.')
            if not self.store.guard_by_callsign(pair[0]):
                raise HTTPException(403, 'Guard is no longer available')
            if principal is not None:
                if self.guard_for_principal(principal) != pair[0]:
                    raise HTTPException(403, 'This pairing link belongs to another guard')
                self.consume_device_pair('guard', pair_key)
                # Clerk remains the authority for HTTP and socket access. A QR
                # link confirms the assigned guard; it never grants cookie access.
                return {'guard': pair[0]}
            self.consume_device_pair('guard', pair_key)
            self.guard_credentials = {k:v for k,v in self.guard_credentials.items() if v[1] > now}
            if len(self.guard_credentials) >= 10 or sum(v[0] == pair[0] for v in self.guard_credentials.values()) >= 2:
                raise HTTPException(429, 'Guard session limit reached.')
            credential = secrets.token_urlsafe(32)
            record = self.store.guard_by_callsign(pair[0])
            self.store.save_device_session(digest(credential),'guard',record['id'],time.time()+12*3600)
            self.guard_credentials[digest(credential)] = (pair[0], now+12*3600)
            response = Response(content=json.dumps({'guard': pair[0]}), media_type='application/json')
            response.set_cookie(GUARD_COOKIE, credential, httponly=True, samesite='strict',
                                secure=request.headers['origin'].startswith('https:'), path='/api/v2/guard', max_age=12*3600)
            return response

        @router.get('/guard/session')
        async def guard_session(request: Request):
            return {'guard': self.require_guard(request)}

        @router.post('/guard/location')
        async def guard_location(data: GPS, request: Request):
            callsign = self.require_guard(request)
            guard = self.store.guard_by_callsign(callsign)
            if not guard: raise HTTPException(403, 'Guard is no longer available')
            updated = self.store.update_guard(guard['id'], gps=data.model_dump())
            await self.broadcast(self.snapshot())
            return self.guard_payload(updated)

        @router.patch('/guard/profile')
        async def guard_profile(data: GuardProfile, request: Request):
            callsign = self.require_guard(request)
            guard = self.store.guard_by_callsign(callsign)
            if not guard: raise HTTPException(403, 'Guard is no longer available')
            updated = self.store.update_guard(guard['id'], floor_name=data.floorName)
            await self.broadcast(self.snapshot())
            return self.guard_payload(updated)

        @router.post('/guard/logout')
        async def guard_logout(request: Request):
            self.auth.dev_only()
            self.require_guard(request)
            await self.revoke_guard(key=digest(request.cookies.get(GUARD_COOKIE, '')))
            response = Response(status_code=204)
            response.delete_cookie(GUARD_COOKIE, path='/api/v2/guard')
            return response

        @router.post('/guard/events/{event_id}')
        async def guard_action(event_id: str, data: GuardActionInput, request: Request):
            guard = self.require_guard(request)
            principal = self.auth.principal(request)
            actor = principal.user_id if principal else 'dev_legacy_guard_'+guard
            try: event = self.store.guard_action(event_id, guard, data.action, data.revision, actor=actor)
            except KeyError as error: raise HTTPException(404, 'Event not found') from error
            except ValueError as error: raise HTTPException(409, str(error)) from error
            if data.action == 'clear': self.clips.delete(event_id)
            await self.broadcast(self.snapshot())
            return event

        @router.websocket('/guard/stream')
        async def guard_stream(socket: WebSocket):
            try: authentication = await self.websocket_auth(socket, roles=('guard',))
            except WebSocketDisconnect: return
            guard = authentication.identity
            record = self.store.guard_by_callsign(guard)
            if not record:
                await socket.close(code=4403, reason='Guard record required.')
                return
            authentication.guard_id = record['id']
            if sum(entry[0] == guard for entry in self.guard_sockets.values()) >= 3:
                await socket.close(code=1013, reason='Guard connection limit reached.')
                return
            key = digest(socket.cookies.get(GUARD_COOKIE, ''))
            relay = PreviewRelay(socket, lambda: self.guard_disconnected(socket))
            self.guard_sockets[socket] = (guard, key, relay)
            self.socket_auth[socket] = authentication
            self.push.seen(guard)
            try:
                relay.offer('snapshot', self.guard_snapshot(guard))
                next_snapshot = time.monotonic()+GUARD_SNAPSHOT_SECONDS
                while socket in self.guard_sockets:
                    await authentication.check()
                    if not self.guard_stream_valid(socket, authentication, key):
                        await authentication.fail(4403)
                    now = time.monotonic()
                    if now >= next_snapshot:
                        relay.offer('snapshot', self.guard_snapshot(guard))
                        next_snapshot = now+GUARD_SNAPSHOT_SECONDS
                    try:
                        message = await asyncio.wait_for(socket.receive(), min(next_snapshot-now, authentication.timeout, 1))
                        if message['type'] == 'websocket.disconnect': break
                        self.push.seen(guard)
                        await authentication.check()
                        if await authentication.consume(message): continue
                        if message.get('text') != 'ping':
                            await self.close_guard_socket(socket)
                            break
                    except asyncio.TimeoutError: pass
            except (WebSocketDisconnect, RuntimeError): pass
            finally:
                self.guard_disconnected(socket)
                await relay.close()

        @router.post('/events/test', status_code=201)
        async def test_event(data: TestEventInput, request: Request):
            self.require_admin(request)
            if self.store.camera(data.cameraId) is None:
                raise HTTPException(404, 'Camera not found')
            if self.store.db.execute("SELECT 1 FROM events WHERE camera_id=? AND model='test' AND decision IS NULL LIMIT 1",
                                     (data.cameraId,)).fetchone():
                raise HTTPException(409, 'This camera already has an undecided test event.')
            now = time.monotonic()
            elapsed = now - self.last_test_event_at
            if elapsed < 10:
                raise HTTPException(429, 'Wait 10 seconds between test events.',
                                    headers={'Retry-After': str(max(1, 10-int(elapsed)))})
            source_id = secrets.token_hex(16)
            self.store.record(data.cameraId, 'test', dict(id=source_id, occurredAtMs=time.time()*1000,
                evidenceModel='test',
                detail='Test alert — not a real incident. Confirm and alert a guard to check their phone rings.'))
            self.last_test_event_at = now
            event = dict(self.store.db.execute('SELECT * FROM events WHERE camera_id=? AND generation=? AND source_id=?',
                                              (data.cameraId, 'test', source_id)).fetchone())
            await self.broadcast(self.snapshot())
            return event

        @router.patch('/events/{event_id}')
        async def transition(event_id: str, data: EventInput, request: Request):
            self.require_reviewer(request)
            try: event = self.store.transition(event_id,data.status,data.revision)
            except KeyError as error: raise HTTPException(404,'Event not found') from error
            except ValueError as error: raise HTTPException(409,str(error)) from error
            await self.broadcast(self.snapshot())
            return event

        @router.post('/events/{event_id}/review')
        async def review(event_id: str, data: ReviewInput, request: Request):
            principal = self.require_reviewer(request)
            try:
                event = self.store.review(event_id, data.action, data.revision,
                                          reason=data.reason, note=data.note, guard=data.guard, actor=principal.user_id)
            except KeyError as error: raise HTTPException(404,'Event not found') from error
            except ValueError as error: raise HTTPException(409,str(error)) from error
            if data.action in ('dismiss', 'clear'): self.clips.delete(event_id)
            if data.action in ('confirm', 'alert') and event.get('alerted_at') is not None:
                await self.push.tick()
            await self.broadcast(self.snapshot())
            return event

        @router.get('/events/{event_id}/clip', dependencies=[Depends(require_role('reviewer'))])
        async def clip_manifest(event_id: str, request: Request):
            if not self.store.db.execute('SELECT 1 FROM events WHERE id=?', (event_id,)).fetchone():
                raise HTTPException(404, 'Event not found')
            return self.clips.manifest(event_id, lambda i: signed_frame_url(f'/api/v2/events/{event_id}/clip/frames/{i}'))

        @router.get('/events/{event_id}/clip/frames/{index}')
        async def clip_frame(event_id: str, index: int, request: Request, exp: int, sig: str):
            if not valid_frame_signature(request.url.path, exp, sig):
                raise HTTPException(403, 'Invalid or expired frame URL')
            frame = self.clips.frame(event_id, index)
            if frame is None: raise HTTPException(404, 'Frame expired or unavailable')
            return Response(frame, media_type='image/jpeg', headers={'Cache-Control': 'no-store'})

        @router.websocket('/operator')
        async def operator(socket: WebSocket):
            try: authentication = await self.websocket_auth(socket)
            except WebSocketDisconnect: return
            if len(self.viewers)>=8:
                await socket.close(code=1013, reason='Close another dashboard tab, then retry.')
                return
            self.viewers.add(socket)
            self.socket_auth[socket] = authentication
            relay = PreviewRelay(socket, lambda: self.viewers.discard(socket))
            self.relays[socket] = relay
            try:
                relay.offer('snapshot', {**self.snapshot(), 'me': {'role': authentication.principal.role}})
                while True:
                    await authentication.check()
                    try:
                        message = await asyncio.wait_for(socket.receive(), min(2, authentication.timeout))
                        if message['type']=='websocket.disconnect': break
                        await authentication.check()
                        if await authentication.consume(message): continue
                        if message.get('text') != 'ping': break
                    except asyncio.TimeoutError:
                        await authentication.check()
                        relay.offer('snapshot', {**self.snapshot(), 'me': {'role': authentication.principal.role}})
            except (WebSocketDisconnect,RuntimeError): pass
            finally:
                self.viewers.discard(socket)
                self.relays.pop(socket, None)
                self.socket_auth.pop(socket, None)
                await relay.close()

        @router.websocket('/camera/stream')
        async def camera_stream(socket: WebSocket):
            camera_id = self.camera_identity(socket)
            camera = self.store.camera(camera_id) if camera_id else None
            if socket.headers.get('origin') not in self.origins or not camera or not camera['enabled'] or camera_id in self.live:
                await socket.close(code=1008)
                return
            await socket.accept()
            generation = secrets.token_hex(12)
            live = dict(socket=socket,generation=generation,received=-1e10,frames=0,replaced=0,pipeline=None,video=deque(maxlen=64),compute='device' if self.state.get('relayOnly') else 'pc',lastDeviceTimestamp=-1,lastMotionTimestamp=-1)
            self.live[camera_id] = live
            last_timestamp = -1
            recent_frames = deque()
            recent_reports = deque()
            try:
                await socket.send_json({'type':'ready','cameraId':camera_id,'generation':generation,'maxFps':12})
                while True:
                    message = await asyncio.wait_for(socket.receive(),15)
                    if message['type'] == 'websocket.disconnect': break
                    if self.camera_identity(socket) != camera_id: raise ValueError('Camera session expired or revoked')
                    if message.get('text') is not None:
                        text = message['text']
                        now = time.monotonic()
                        while recent_reports and now-recent_reports[0] > 1: recent_reports.popleft()
                        if len(text.encode('utf-8')) > MAX_REPORT_BYTES or len(recent_reports) >= 24: raise ValueError('Invalid device report rate or size')
                        recent_reports.append(now)
                        data = json.loads(text)
                        if data.get('type') in ('device-status', 'device-motion-status'):
                            motion = data['type'] == 'device-motion-status'
                            status = (DeviceMotionStatus if motion else DeviceStatus).model_validate(data)
                            live['motionStatus' if motion else 'deviceStatus'] = status.model_dump(exclude={'type'})
                            if live['compute'] != 'device': continue  # Browser detector remains standby.
                            if status.state != 'ready':
                                if motion: live['motionAnalyzed'], live['motionResult'] = None, None
                                else: live['analyzed'], live['result'] = None, None
                            if not motion: live['error'] = status.detail if status.state == 'error' else None
                            await self.broadcast(self.snapshot())
                        elif data.get('type') in ('device-result', 'device-motion'):
                            if live['compute'] != 'device': continue
                            motion = data['type'] == 'device-motion'
                            ready_status = live.get('motionStatus' if motion else 'deviceStatus',{})
                            if ready_status.get('state') != 'ready': raise ValueError('Device analysis not ready')
                            report = (DeviceMotion if motion else DeviceResult).model_validate(data)
                            if report.delegate != ready_status['delegate']: raise ValueError('Unexpected compute delegate')
                            # Source clocks are device-local; compare only to this stream.
                            timestamp_key = 'lastMotionTimestamp' if motion else 'lastDeviceTimestamp'
                            if report.timestampMs <= live[timestamp_key]: raise ValueError('Device timestamps must increase')
                            window = 3000 if motion else 6000
                            if not live['frames'] or now-live['received'] > window / 1000 or not -2000 <= last_timestamp-report.timestampMs <= window:
                                continue
                            live[timestamp_key] = report.timestampMs
                            if motion:
                                live['motionAnalyzed'] = now
                                live['motionResult'] = result_payload(report)
                            else:
                                live['analyzed'], live['analyzedCount'] = now, live.get('analyzedCount',0)+1
                                live['result'] = result_payload(report)
                            new_event = False
                            for event in report.events:
                                payload = dict(id=event.id,occurredAtMs=event.occurredAtMs,evidenceTimestampMs=event.occurredAtMs,detail=event.detail,evidenceModel=DEVICE_MODEL)
                                if self.record_event(camera_id,generation,payload):
                                    new_event = True
                            if new_event: await self.broadcast(self.snapshot())
                            else: self.schedule_snapshot()
                        else: raise ValueError('Unknown device message')
                        continue
                    packet = message.get('bytes', b'')
                    received_at = time.monotonic()
                    while recent_frames and received_at-recent_frames[0] > 1: recent_frames.popleft()
                    # Public networks can deliver several paced frames together.
                    # Permit one bounded eight-frame transport window as burst headroom.
                    if len(recent_frames) >= 24: raise ValueError('Frame rate exceeded')
                    recent_frames.append(received_at)
                    header, frame = self.unpack_frame(packet)
                    if header.timestampMs <= last_timestamp: raise ValueError('Source timestamps must increase')
                    if header.timestampMs-last_timestamp > 1200 or (live.get('dimensions') and live['dimensions'] != frame.shape):
                        live['video'].clear()
                    live['dimensions'] = frame.shape
                    last_timestamp = header.timestampMs
                    now = time.monotonic()
                    live['received'], live['frames'] = now, live['frames']+1
                    length = struct.unpack('<I',packet[:4])[0]
                    self.clips.receive(camera_id, packet[4+length:])
                    if live['compute'] == 'pc':
                        # Temporal X3D input is 224px; bound decoded history per camera.
                        import cv2
                        scale = min(1, 456 / max(frame.shape[:2]))
                        small = cv2.resize(frame, (round(frame.shape[1] * scale), round(frame.shape[0] * scale)))
                        live['video'].append((header.timestampMs,small))
                        while live['video'] and header.timestampMs-live['video'][0][0] > 4500: live['video'].popleft()
                        self.enqueue(camera_id,(generation,header,frame,now))
                    await socket.send_json({'type':'accepted','timestampMs':header.timestampMs})
                    length = struct.unpack('<I',packet[:4])[0]
                    metadata = json.dumps({'cameraId':camera_id,'generation':generation,'timestampMs':header.timestampMs,'width':frame.shape[1],'height':frame.shape[0]}).encode()
                    await self.broadcast(struct.pack('<I',len(metadata))+metadata+packet[4+length:],binary=True,camera_id=camera_id)
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
                    self.clips.disconnect(camera_id)
                    self.live.pop(camera_id,None)
                    self.pending.pop(camera_id,None)
                    self.order = deque(c for c in self.order if c != camera_id)
                await self.broadcast(self.snapshot())
