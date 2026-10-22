"""Guard-only Web Push. SQLite stays on the event loop; network I/O runs in threads."""
import asyncio
import base64
import json
import logging
import math
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from py_vapid import Vapid
from pywebpush import WebPushException, webpush

log = logging.getLogger(__name__)


def validate_endpoint(value):
    try:
        url = urlsplit(value)
        host = url.hostname or ''
        allowed = host in ('fcm.googleapis.com', 'updates.push.services.mozilla.com', 'web.push.apple.com')
        allowed = allowed or any(host.endswith(suffix) and host != suffix[1:]
                                 for suffix in ('.notify.windows.com', '.push.apple.com'))
        if (url.scheme != 'https' or not allowed or url.port not in (None, 443)
                or url.username or url.password or url.fragment
                or any(c.isspace() or ord(c) < 32 for c in value) or '\\' in value):
            raise ValueError('Use an HTTPS endpoint from a supported push service.')
    except ValueError as error:
        raise ValueError('Use an HTTPS endpoint from a supported push service.') from error
    return value


def decode_key(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]+={0,2}', value):
        raise ValueError('Invalid push key.')
    try:
        return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
    except ValueError as error:
        raise ValueError('Invalid push key.') from error


class SubscriptionKeys(BaseModel):
    model_config = ConfigDict(extra='forbid')
    p256dh: str = Field(min_length=80, max_length=100)
    auth: str = Field(min_length=20, max_length=30)

    @field_validator('p256dh')
    @classmethod
    def public_key(cls, value):
        raw = decode_key(value)
        if len(raw) != 65 or raw[0] != 4: raise ValueError('Invalid P-256 public key.')
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), raw)
        return value

    @field_validator('auth')
    @classmethod
    def auth_key(cls, value):
        if len(decode_key(value)) != 16: raise ValueError('Invalid push authentication key.')
        return value


class Subscription(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    endpoint: str = Field(min_length=1, max_length=2048)
    expirationTime: float | None = Field(default=None, ge=0)
    keys: SubscriptionKeys
    _endpoint = field_validator('endpoint')(validate_endpoint)


class SubscribeInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    subscription: Subscription


class UnsubscribeInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    endpoint: str = Field(min_length=1, max_length=2048)
    _endpoint = field_validator('endpoint')(validate_endpoint)


class ShiftInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    shift: Literal['on_shift', 'break', 'off']


def encode_key(value):
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


class NoRedirectSession(requests.Session):
    def request(self, method, url, **kwargs):
        kwargs['allow_redirects'] = False
        return super().request(method, url, **kwargs)


class GuardPush:
    def __init__(self, classroom, *, clock=time.time, sender=None, key_path=None):
        self.classroom, self.store = classroom, classroom.store
        self.clock, self.sender = clock, sender
        self.key_path = Path(key_path or Path(__file__).resolve().parents[1] / 'state' / 'vapid.json')
        self.keys = None
        self.tasks = set()
        self.task = None
        self.last_seen = {}
        self.timeout = float(os.environ.get('NIVRA_ACK_TIMEOUT_S', '30'))
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError('NIVRA_ACK_TIMEOUT_S must be finite and positive.')

    def vapid(self):
        if self.keys is not None: return self.keys
        public = os.environ.get('NIVRA_VAPID_PUBLIC')
        private = os.environ.get('NIVRA_VAPID_PRIVATE')
        subject = os.environ.get('NIVRA_VAPID_SUBJECT', 'mailto:nivra@localhost')
        if bool(public) != bool(private):
            raise ValueError('Set both NIVRA_VAPID_PUBLIC and NIVRA_VAPID_PRIVATE.')
        if not (subject.startswith('mailto:') or subject.startswith('https://')):
            raise ValueError('NIVRA_VAPID_SUBJECT must be a mailto: or HTTPS contact.')
        if not public:
            self.key_path.parent.mkdir(parents=True, exist_ok=True)
            if not self.key_path.exists():
                key = ec.generate_private_key(ec.SECP256R1())
                generated = dict(publicKey=encode_key(key.public_key().public_bytes(
                    serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)),
                    privateKey=encode_key(key.private_numbers().private_value.to_bytes(32, 'big')))
                # Publish a complete file atomically, without overwriting another worker's key.
                fd, temporary = tempfile.mkstemp(prefix='.vapid-', dir=self.key_path.parent)
                try:
                    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                        json.dump(generated, stream)
                        stream.flush()
                        os.fsync(stream.fileno())
                    try: os.link(temporary, self.key_path)
                    except FileExistsError: pass
                    else:
                        log.warning('Generated local VAPID keys in %s; preserve this file across restarts.', self.key_path)
                finally:
                    os.unlink(temporary)
            try: self.key_path.chmod(0o600)
            except OSError: log.warning('Could not restrict VAPID file permissions; check the OS ACL.')
            stored = json.loads(self.key_path.read_text(encoding='utf-8'))
            public, private = stored['publicKey'], stored['privateKey']
        scalar = decode_key(private)
        if len(scalar) != 32: raise ValueError('VAPID private key must be a base64url 32-byte scalar.')
        key = ec.derive_private_key(int.from_bytes(scalar, 'big'), ec.SECP256R1())
        expected = encode_key(key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
        if public.rstrip('=') != expected: raise ValueError('VAPID public/private keys do not match.')
        self.keys = dict(publicKey=public, privateKey=private, subject=subject)
        return self.keys

    def presence(self, guard):
        return dict(online=any(entry[0] == guard for entry in self.classroom.guard_sockets.values()),
                    lastSeen=self.last_seen.get(guard))

    def seen(self, guard):
        self.last_seen[guard] = self.clock() * 1000
        self.classroom.schedule_snapshot()

    def has_subscription(self, guard_id):
        return self.store.db.execute('SELECT 1 FROM guard_push_subscriptions WHERE guard_id=? LIMIT 1',
                                     (guard_id,)).fetchone() is not None

    def subscribe(self, guard_id, subscription):
        endpoint = subscription['endpoint']
        with self.store.db:
            self.store.db.execute('BEGIN IMMEDIATE')
            existing = self.store.db.execute('SELECT guard_id FROM guard_push_subscriptions WHERE endpoint=?',
                                            (endpoint,)).fetchone()
            if existing and existing['guard_id'] != guard_id:
                raise HTTPException(409, 'Unsubscribe this device from its previous guard first.')
            count = self.store.db.execute('SELECT COUNT(*) FROM guard_push_subscriptions WHERE guard_id=?',
                                         (guard_id,)).fetchone()[0]
            if not existing and count >= 5: raise HTTPException(409, 'At most five push subscriptions per guard.')
            self.store.db.execute('INSERT OR REPLACE INTO guard_push_subscriptions VALUES(?,?,?)',
                                  (endpoint, guard_id, json.dumps(subscription)))

    def unsubscribe(self, guard_id, endpoint=None):
        with self.store.db:
            self.store.db.execute('DELETE FROM guard_push_subscriptions WHERE guard_id=?' +
                                  (' AND endpoint=?' if endpoint is not None else ''),
                                  (guard_id, endpoint) if endpoint is not None else (guard_id,))

    async def start(self):
        self.task = asyncio.create_task(self.run(), name='guard-escalation')

    async def stop(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        # Drain bounded network calls before the shared SQLite connection closes.
        if self.tasks: await asyncio.gather(*tuple(self.tasks), return_exceptions=True)

    def enqueue(self, event):
        task = asyncio.create_task(self.deliver(event), name='guard-push')
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def deliver(self, event):
        try:
            guard = self.store.guard_by_callsign(event['guard'])
            if not guard: return
            rows = self.store.db.execute('SELECT * FROM guard_push_subscriptions WHERE guard_id=?',
                                         (guard['id'],)).fetchall()
            if not rows: return
            keys = self.vapid()
            payload = json.dumps(dict(type='alert', eventId=event['id'], title='NIVRA alert',
                                     body='Go to ' + event['camera_name'], url='/guard'))
            for row in rows:
                # An ack, reassignment, clear, or unsubscribe may occur while another send yields.
                current = self.store.db.execute('SELECT * FROM events WHERE id=?', (event['id'],)).fetchone()
                if not current or any(current[k] != event[k] for k in ('guard', 'alerted_at')): break
                if (current['status'] != 'acknowledged' or any(current[k] is not None
                        for k in ('guard_ack_at', 'guard_declined_at', 'on_scene_at'))): break
                if not self.store.db.execute('SELECT 1 FROM guard_push_subscriptions WHERE endpoint=? AND guard_id=?',
                                             (row['endpoint'], guard['id'])).fetchone(): continue
                try:
                    await asyncio.to_thread(self.send, json.loads(row['subscription']), payload, keys)
                except WebPushException as error:
                    status = getattr(error.response, 'status_code', None)
                    if status in (404, 410):
                        self.unsubscribe(guard['id'], row['endpoint'])
                        self.classroom.schedule_snapshot()
                    else: log.warning('Guard push rejected (status=%s).', status)
                except Exception:
                    # Never log endpoints, credentials, subscription keys, or provider bodies.
                    log.warning('Guard push delivery failed.')
        except Exception:
            log.warning('Guard push task failed; inspect VAPID configuration and metadata storage.')

    def send(self, subscription, payload, keys):
        validate_endpoint(subscription['endpoint'])
        with NoRedirectSession() as session:
            response = (self.sender or webpush)(subscription_info=subscription, data=payload,
                vapid_private_key=Vapid.from_string(keys['privateKey']),
                vapid_claims={'sub': keys['subject']}, headers={'Urgency': 'high'},
                ttl=60, timeout=5, requests_session=session)
            if response is not None and not 200 <= response.status_code < 300:
                raise WebPushException('Push provider rejected delivery.', response=response)

    async def tick(self):
        now = self.clock() * 1000
        queued, changed = [], False
        with self.store.db:
            self.store.db.execute('BEGIN IMMEDIATE')
            self.store.db.execute('DELETE FROM guard_push_subscriptions WHERE guard_id NOT IN (SELECT id FROM guards)')
            self.store.db.execute('DELETE FROM guard_push_rounds WHERE event_id NOT IN (SELECT id FROM events)')
            events = self.store.db.execute("""SELECT * FROM events WHERE decision='confirmed'
                AND status='acknowledged' AND alerted_at IS NOT NULL AND guard IS NOT NULL
                AND guard_ack_at IS NULL AND guard_declined_at IS NULL AND on_scene_at IS NULL""").fetchall()
            for row in events:
                event = dict(row)
                age = now - event['alerted_at']
                if age < 0: continue
                due = 0 if age < self.timeout * 1000 else min(3, 1 + int((age - self.timeout * 1000) // 15000))
                if due and event['escalated_at'] is None:
                    self.store.db.execute('UPDATE events SET escalated_at=?,updated_at=?,revision=revision+1 WHERE id=?',
                                          (now, now, event['id']))
                    self.store.db.execute('''INSERT INTO event_audit(event_id,status,revision,changed_at,action)
                        VALUES(?,?,?,?,?)''', (event['id'], event['status'], event['revision'] + 1, now, 'escalate'))
                    changed = True
                previous = self.store.db.execute('SELECT * FROM guard_push_rounds WHERE event_id=?', (event['id'],)).fetchone()
                if (previous and previous['alerted_at'] == event['alerted_at']
                        and previous['guard'] == event['guard'] and previous['last_round'] >= due): continue
                # Reserve the round before network I/O. Restarts skip missed rounds, never burst.
                self.store.db.execute('INSERT OR REPLACE INTO guard_push_rounds VALUES(?,?,?,?)',
                                      (event['id'], event['alerted_at'], event['guard'], due))
                queued.append(event)
        for event in queued: self.enqueue(event)
        if changed: await self.classroom.broadcast(self.classroom.snapshot())

    async def run(self):
        while True:
            try: await self.tick()
            except Exception: log.warning('Guard escalation scan failed; retrying in one second.')
            await asyncio.sleep(1)


def register_routes(classroom):
    router, push = classroom.router, classroom.push

    async def guard_record(request):
        # H1 owns require_guard's Clerk-role check; its return value is the callsign.
        identity = classroom.require_guard(request)
        guard = classroom.store.guard_by_callsign(identity)
        if not guard: raise HTTPException(403, 'Guard record required.')
        return guard

    @router.get('/guard/push/key')
    async def push_key(request: Request):
        await guard_record(request)
        return {'publicKey': push.vapid()['publicKey']}

    @router.post('/guard/push', status_code=204)
    async def subscribe(data: SubscribeInput, request: Request):
        guard = await guard_record(request)
        push.subscribe(guard['id'], data.subscription.model_dump(exclude_none=True))
        await classroom.broadcast(classroom.snapshot())
        return Response(status_code=204)

    @router.delete('/guard/push', status_code=204)
    async def unsubscribe(request: Request, data: UnsubscribeInput | None = None):
        guard = await guard_record(request)
        push.unsubscribe(guard['id'], data.endpoint if data else None)
        await classroom.broadcast(classroom.snapshot())
        return Response(status_code=204)

    @router.post('/guard/shift')
    async def shift(data: ShiftInput, request: Request):
        guard = await guard_record(request)
        classroom.store.set_shift(guard['id'], data.shift)
        await classroom.broadcast(classroom.snapshot())
        return {'shift': data.shift}
