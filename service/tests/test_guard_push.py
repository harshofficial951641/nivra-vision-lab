import asyncio
import json
import threading
import time
from types import SimpleNamespace

import pytest
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from pywebpush import WebPushException

from nivra.classroom_store import Store, GUARD_ALERT_FIELDS
from nivra.push import GuardPush, Subscription, encode_key
from nivra.server import create_app

ORIGIN = {'origin': 'http://127.0.0.1:8765'}


def subscription(endpoint='https://fcm.googleapis.com/push/device'):
    key = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return dict(endpoint=endpoint, expirationTime=None,
                keys=dict(p256dh=encode_key(key), auth=encode_key(b'0123456789abcdef')))


@pytest.fixture
def push_client(tmp_path, monkeypatch):
    monkeypatch.setenv('NIVRA_AUTH_MODE', 'dev')
    for name in ('NIVRA_VAPID_PUBLIC', 'NIVRA_VAPID_PRIVATE', 'NIVRA_VAPID_SUBJECT'):
        monkeypatch.delenv(name, raising=False)
    app = create_app(database=tmp_path / 'push.sqlite', relay_only=True)
    service = app.state.classroom
    service.push.key_path = tmp_path / 'vapid.json'
    service.store.add_guard('G2', 'Guard Two')
    service.store.add_guard('G3', 'Other Guard')
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        response = client.post('/api/v2/auth/dev', headers=ORIGIN, json={'role': 'guard', 'name': 'G2'})
        assert response.status_code == 200, response.text
        yield client, service


def test_push_key_subscription_idempotency_limit_and_delete(push_client):
    client, service = push_client
    first = client.get('/api/v2/guard/push/key')
    assert first.status_code == 200 and set(first.json()) == {'publicKey'}
    assert len(first.json()['publicKey']) == 87
    assert client.get('/api/v2/guard/push/key').json() == first.json()
    body = {'subscription': subscription()}
    for _ in range(2): assert client.post('/api/v2/guard/push', headers=ORIGIN, json=body).status_code == 204
    for i in range(4):
        body = {'subscription': subscription(f'https://fcm.googleapis.com/push/{i}')}
        assert client.post('/api/v2/guard/push', headers=ORIGIN, json=body).status_code == 204
    assert client.post('/api/v2/guard/push', headers=ORIGIN,
                       json={'subscription': subscription('https://fcm.googleapis.com/sixth')}).status_code == 409
    guard = service.store.guard_by_callsign('G2')
    assert service.guard_payload(guard)['push'] is True
    assert client.request('DELETE', '/api/v2/guard/push', headers=ORIGIN,
                          json={'endpoint': 'https://fcm.googleapis.com/push/device'}).status_code == 204
    assert service.push.has_subscription(guard['id'])
    assert client.delete('/api/v2/guard/push', headers=ORIGIN).status_code == 204
    assert client.delete('/api/v2/guard/push', headers=ORIGIN).status_code == 204
    assert not service.push.has_subscription(guard['id'])


@pytest.mark.parametrize('endpoint', [
    'http://fcm.googleapis.com/push/a', 'https://localhost/push',
    'https://fcm.googleapis.com.evil.test/push', 'https://evilnotify.windows.com/push',
    'https://push.apple.com/push', 'https://notify.windows.com/push',
    'https://user:password@fcm.googleapis.com/push', 'https://fcm.googleapis.com:444/push',
    'https://fcm.googleapis.com/push#fragment', 'https://fcm.googleapis.com/\npush',
    'https://127.0.0.1/', 'https://fcm.googleapis.com\\@evil.test/push',
])
def test_reject_bad_push_hosts_and_urls(push_client, endpoint):
    client, service = push_client
    assert client.post('/api/v2/guard/push', headers=ORIGIN,
                       json={'subscription': subscription(endpoint)}).status_code == 422
    assert service.store.db.execute('SELECT COUNT(*) FROM guard_push_subscriptions').fetchone()[0] == 0


@pytest.mark.parametrize('host', ['fcm.googleapis.com', 'updates.push.services.mozilla.com',
                                 'a.notify.windows.com', 'web.push.apple.com', 'a.push.apple.com'])
def test_supported_push_services(host):
    assert Subscription.model_validate(subscription(f'https://{host}/a')).endpoint == f'https://{host}/a'


def test_bad_subscription_keys_and_guard_role_boundary(push_client):
    client, service = push_client
    body = {'subscription': subscription()}
    body['subscription']['keys']['auth'] = 'invalid'
    assert client.post('/api/v2/guard/push', headers=ORIGIN, json=body).status_code == 422
    assert client.post('/api/v2/guard/push', json={'subscription': subscription()}).status_code == 403
    for role in ('reviewer', 'admin'):
        client.post('/api/v2/auth/dev', headers=ORIGIN, json={'role': role, 'name': 'Operator'})
        assert client.get('/api/v2/guard/push/key').status_code == 403
        assert client.post('/api/v2/guard/push', headers=ORIGIN, json={'subscription': subscription()}).status_code == 403
        assert client.delete('/api/v2/guard/push', headers=ORIGIN).status_code == 403
        assert client.post('/api/v2/guard/shift', headers=ORIGIN, json={'shift': 'on_shift'}).status_code == 403
    client.cookies.clear()
    assert client.get('/api/v2/guard/push/key').status_code in (401, 403)


def test_guard_cannot_delete_or_take_over_another_subscription(push_client):
    client, service = push_client
    other = service.store.guard_by_callsign('G3')
    data = subscription()
    service.push.subscribe(other['id'], data)
    assert client.post('/api/v2/guard/push', headers=ORIGIN, json={'subscription': data}).status_code == 409
    assert client.request('DELETE', '/api/v2/guard/push', headers=ORIGIN,
                          json={'endpoint': data['endpoint']}).status_code == 204
    assert service.push.has_subscription(other['id'])


def test_shift_endpoint_and_operator_snapshot(push_client):
    client, service = push_client
    for shift in ('on_shift', 'break', 'off'):
        response = client.post('/api/v2/guard/shift', headers=ORIGIN, json={'shift': shift})
        assert response.status_code == 200 and response.json() == {'shift': shift}
        assert service.store.guard_by_callsign('G2')['shift'] == shift
        assert next(g for g in service.snapshot()['guards'] if g['callsign'] == 'G2')['shift'] == shift
    assert client.post('/api/v2/guard/shift', headers=ORIGIN, json={'shift': 'away'}).status_code == 422
    assert service.store.guard_by_callsign('G3')['shift'] == 'off'


def record_event(store, guard='G2', source='one'):
    camera = store.add_camera('East entrance', 'Main', 'Ground floor')
    store.record(camera['id'], 'test', {'id': source, 'occurredAtMs': 100})
    event = next(e for e in store.events() if e['camera_id'] == camera['id'])
    return store.review(event['id'], 'confirm', 0, guard=guard)


def test_presence_and_guard_stream_v2_whitelist(push_client):
    client, service = push_client
    floor = service.store.add_floor('Ground floor')
    guard = service.store.guard_by_callsign('G2')
    service.store.update_guard(guard['id'], floor_id=floor['id'], post={'x': .4, 'y': .6})
    event = record_event(service.store)
    other = record_event(service.store, 'G3', 'other')
    placement = dict(floorId=floor['id'], x=.2, y=.3, angle=90, fov=60, range=.2)
    service.store.patch_camera(event['camera_id'], placement=placement)
    service.push.clock = lambda: 100.0
    with client.websocket_connect('ws://127.0.0.1:8765/api/v2/guard/stream', headers=ORIGIN) as first:
        snapshot = first.receive_json()
        assert set(snapshot) == {'type', 'version', 'guard', 'floor', 'serverTime', 'alerts'}
        assert snapshot['version'] == 2 and snapshot['type'] == 'guard-snapshot'
        assert snapshot['guard']['callsign'] == 'G2'
        assert snapshot['guard']['presence'] == {'online': True, 'lastSeen': 100000}
        assert snapshot['floor']['id'] == floor['id']
        assert len(snapshot['alerts']) == 1
        alert = snapshot['alerts'][0]
        assert set(alert) == set(GUARD_ALERT_FIELDS) | {'placement', 'floorId'}
        assert alert['id'] == event['id'] and alert['placement'] == placement and alert['floorId'] == floor['id']
        assert other['id'] not in json.dumps(snapshot)
        assert 'Other Guard' not in json.dumps(snapshot)
        client.portal.call(service.broadcast, b'private-camera-frame', True, event['camera_id'])
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/guard/stream', headers=ORIGIN) as second:
            second.receive_json()
            service.push.clock = lambda: 101.0
            first.send_text('ping')
            for _ in range(100):
                if service.push.last_seen['G2'] == 101000: break
                time.sleep(.005)
            assert service.push.presence('G2')['lastSeen'] == 101000
        assert service.push.presence('G2')['online'] is True
    for _ in range(100):
        if not service.push.presence('G2')['online']: break
        time.sleep(.005)
    assert service.push.presence('G2') == {'online': False, 'lastSeen': 101000}
    assert not service.snapshot()['guards'][0]['presence']['online']


def make_push(tmp_path, *, path=None, sender=None, clock=lambda: 100):
    store = Store(path or tmp_path / 'push.sqlite')
    async def broadcast(value): broadcasts.append(value)
    broadcasts = []
    classroom = SimpleNamespace(store=store, guard_sockets={}, schedule_snapshot=lambda: None,
                                broadcast=broadcast, snapshot=lambda: {'events': store.events()})
    push = GuardPush(classroom, clock=clock, sender=sender, key_path=tmp_path / 'vapid.json')
    return push, store, broadcasts


async def drain(push):
    if push.tasks: await asyncio.gather(*tuple(push.tasks))


def test_escalation_clock_restart_max_four_realert_and_ack(tmp_path):
    async def run():
        sends, now = [], [100.0]
        def sender(**kwargs): sends.append(kwargs)
        push, store, broadcasts = make_push(tmp_path, sender=sender, clock=lambda: now[0])
        guard = store.add_guard('G2', 'Guard Two')
        push.subscribe(guard['id'], subscription())
        event = record_event(store)
        with store.db: store.db.execute('UPDATE events SET alerted_at=100000 WHERE id=?', (event['id'],))
        await push.tick(); await drain(push)
        assert len(sends) == 1 and not broadcasts
        now[0] = 129.999
        await push.tick(); await drain(push)
        assert len(sends) == 1
        now[0] = 130
        await push.tick(); await drain(push)
        assert len(sends) == 2 and len(broadcasts) == 1
        assert store.events()[0]['escalated_at'] == 130000
        assert store.events()[0]['revision'] == 2
        assert store.db.execute("SELECT COUNT(*) FROM event_audit WHERE action='escalate'").fetchone()[0] == 1
        store.close()
        push, store, _ = make_push(tmp_path, sender=sender, clock=lambda: now[0])
        await push.tick(); await drain(push)
        assert len(sends) == 2
        for point, expected in ((144.999, 2), (145, 3), (159.999, 3), (160, 4), (300, 4)):
            now[0] = point
            await push.tick(); await drain(push)
            assert len(sends) == expected
        event = store.events()[0]
        event = store.review(event['id'], 'alert', event['revision'], guard='G2')
        now[0] = event['alerted_at'] / 1000
        await push.tick(); await drain(push)
        assert len(sends) == 5 and store.events()[0]['escalated_at'] is None
        store.guard_action(event['id'], 'G2', 'ack', event['revision'])
        now[0] += 90
        await push.tick(); await drain(push)
        assert len(sends) == 5
        payload = json.loads(sends[0]['data'])
        assert payload == dict(type='alert', eventId=event['id'], title='NIVRA alert', body='Go to East entrance', url='/guard')
        assert sends[0]['ttl'] == 60 and sends[0]['headers'] == {'Urgency': 'high'}
        assert sends[0]['timeout'] == 5
        store.close()
    asyncio.run(run())


@pytest.mark.parametrize('status', [404, 410, 503])
def test_expired_subscription_cleanup_and_transient_failure(tmp_path, status):
    async def run():
        def sender(**kwargs):
            raise WebPushException('provider failure', response=SimpleNamespace(status_code=status))
        push, store, _ = make_push(tmp_path, sender=sender, clock=time.time)
        guard = store.add_guard('G2', 'Guard Two')
        push.subscribe(guard['id'], subscription())
        record_event(store)
        await push.tick(); await drain(push)
        assert push.has_subscription(guard['id']) is (status == 503)
        store.close()
    asyncio.run(run())


@pytest.mark.parametrize('action', ['decline', 'clear', 'on_scene'])
def test_escalation_stops_on_terminal_response(tmp_path, action):
    async def run():
        push, store, _ = make_push(tmp_path)
        store.add_guard('G2', 'Guard Two')
        event = record_event(store)
        if action == 'decline': store.guard_action(event['id'], 'G2', action, event['revision'])
        else: store.review(event['id'], action, event['revision'])
        push.clock = lambda: event['alerted_at'] / 1000 + 200
        await push.tick()
        assert store.events()[0]['escalated_at'] is None
        assert store.db.execute('SELECT COUNT(*) FROM guard_push_rounds').fetchone()[0] == 0
        store.close()
    asyncio.run(run())


def test_review_sends_in_background_without_waiting_for_provider(push_client):
    client, service = push_client
    client.post('/api/v2/guard/push', headers=ORIGIN, json={'subscription': subscription()})
    started, release = threading.Event(), threading.Event()
    calls = []
    def sender(**kwargs):
        calls.append(kwargs)
        started.set()
        assert release.wait(5)
    service.push.sender = sender
    client.post('/api/v2/auth/dev', headers=ORIGIN, json={'role': 'admin', 'name': 'Reviewer'})
    camera = service.store.add_camera('East entrance', 'Main', 'Ground')
    service.store.record(camera['id'], 'review', {'id': 'one', 'occurredAtMs': 100})
    event = service.store.events()[0]
    try:
        response = client.post(f'/api/v2/events/{event["id"]}/review', headers=ORIGIN,
                               json={'action': 'confirm', 'guard': 'G2', 'revision': 0})
        assert response.status_code == 200
        assert started.wait(2) and not release.is_set()
    finally:
        release.set()
        client.portal.call(drain, service.push)
    assert len(calls) == 1
    response = client.post(f'/api/v2/events/{event["id"]}/review', headers=ORIGIN,
                           json={'action': 'alert', 'guard': 'G2', 'revision': response.json()['revision']})
    assert response.status_code == 200
    client.portal.call(drain, service.push)
    assert len(calls) == 2


def test_vapid_persists_and_env_pair_validation(tmp_path, monkeypatch):
    for name in ('NIVRA_VAPID_PUBLIC', 'NIVRA_VAPID_PRIVATE', 'NIVRA_VAPID_SUBJECT'):
        monkeypatch.delenv(name, raising=False)
    push, store, _ = make_push(tmp_path)
    original = push.vapid()
    push.keys = None
    assert push.vapid() == original
    store.close()
    monkeypatch.setenv('NIVRA_VAPID_PUBLIC', original['publicKey'])
    push, store, _ = make_push(tmp_path)
    with pytest.raises(ValueError, match='both'): push.vapid()
    monkeypatch.setenv('NIVRA_VAPID_PRIVATE', original['privateKey'])
    assert push.vapid()['publicKey'] == original['publicKey']
    store.close()


def test_push_schema_migration_reopens_preserves_subscriptions(tmp_path):
    path = tmp_path / 'metadata.sqlite'
    store = Store(path)
    assert store.db.execute('SELECT version FROM schema_version').fetchone()[0] == 4
    guard = store.add_guard('G2', 'Guard Two')
    push, other, _ = make_push(tmp_path, path=path)
    push.subscribe(guard['id'], subscription())
    other.close(); store.close()
    reopened = Store(path)
    assert reopened.db.execute('SELECT guard_id FROM guard_push_subscriptions').fetchone()[0] == guard['id']
    reopened.close()


def test_real_pywebpush_encrypts_and_disables_redirects(tmp_path, monkeypatch):
    calls = []
    def request(session, method, url, **kwargs):
        calls.append((method, url, kwargs))
        response = requests.Response()
        response.status_code = 201
        return response
    monkeypatch.setattr(requests.Session, 'request', request)
    push, store, _ = make_push(tmp_path)
    payload = json.dumps({'type': 'alert', 'eventId': 'test', 'url': '/guard'})
    push.send(subscription(), payload, push.vapid())
    assert len(calls) == 1
    method, url, kwargs = calls[0]
    assert method.lower() == 'post' and url == 'https://fcm.googleapis.com/push/device'
    assert kwargs['allow_redirects'] is False
    assert kwargs['headers']['urgency'] == 'high'
    assert str(kwargs['headers']['ttl']) == '60'
    assert payload.encode() not in kwargs['data']
    store.close()
