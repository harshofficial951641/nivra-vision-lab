import asyncio
from concurrent.futures import ThreadPoolExecutor
import sqlite3
from threading import Barrier
import time
from urllib.parse import urlsplit, parse_qs
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from nivra.server import create_app
from nivra.classroom_store import Store
from nivra.classroom import digest, GUARD_COOKIE
from test_server import FakeModels, FakePipeline, packet

ORIGIN = {'origin':'http://127.0.0.1:8765'}


def operator(client):
    assert client.post('/api/v2/session',headers=ORIGIN).status_code == 204


def camera(client, name='Classroom 8A'):
    response = client.post('/api/v2/cameras',json=dict(name=name,building='Main',floor='Floor 1'),headers=ORIGIN)
    assert response.status_code == 201
    return response.json()


def pair(client, camera_id):
    result = client.post(f'/api/v2/cameras/{camera_id}/pair',headers=ORIGIN).json()
    token = parse_qs(urlsplit(result['url']).fragment)['pair'][0]
    response = client.post('/api/v2/camera/pair',json={'token':token},headers=ORIGIN)
    assert response.status_code == 200
    return token


def test_distinct_device_interactions_are_saved_without_camera_global_cooldown(tmp_path):
    app=create_app(database=tmp_path/'multi.sqlite',relay_only=True)
    with TestClient(app,base_url=ORIGIN['origin']) as client:
        operator(client);cam=camera(client);pair(client,cam['id'])
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream',headers=ORIGIN) as ws:
            ws.receive_json()
            ws.send_json(dict(type='device-status',state='ready',delegate='GPU',detail='Device GPU'))
            ws.send_bytes(packet(1000));ws.receive_json()
            def report(timestamp, ids):
                return dict(type='device-result',model='nivra-browser-motion-v1',delegate='GPU',
                    timestampMs=timestamp,inferenceMs=25,observedPeople=4,usablePeople=4,tracks=[],
                    conflict=dict(status='alert',explanation='Distinct interactions need review'),
                    events=[dict(id=identity,occurredAtMs=1000 if identity!='pair-three' else 1100,
                        detail='Review the scene') for identity in ids])
            ws.send_json(report(1000,['pair-two','pair-one']))
            ws.send_bytes(packet(1100));ws.receive_json()
            ws.send_json(report(1100,['pair-three','pair-two']))
            ws.send_bytes(packet(1200));ws.receive_json()
            state=client.get('/api/v2/state').json()
            assert state['analytics']['total']==3
            assert {event['source_id'] for event in app.state.classroom.store.events()}=={'pair-one','pair-two','pair-three'}
            assert all(event['status']=='open' for event in state['events'])


def test_metadata_idempotency_and_concurrent_acknowledgement(tmp_path):
    path = tmp_path/'metadata.sqlite'
    store = Store(path)
    cam = store.add_camera('8A','Main','1')
    event = dict(id='1',occurredAtMs=150,evidenceTimestampMs=100,detail='Review')
    assert store.record(cam['id'],'generation-1',event)
    assert not store.record(cam['id'],'generation-1',event)
    assert store.record(cam['id'],'generation-2',event)
    event_id = store.events()[0]['id']
    store.transition(event_id,'acknowledged',0)
    with pytest.raises(ValueError): store.transition(event_id,'resolved',0)
    store.transition(event_id,'resolved',1)
    with pytest.raises(ValueError): store.transition(event_id,'acknowledged',2)
    store.close()
    restored = Store(path)
    assert restored.analytics() == dict(total=2,pending=1,resolved=1,confirmed=0,falseAlarms=0)
    assert restored.events()[0]['status']=='resolved'
    assert not any('frame' in key or 'image' in key for key in restored.events()[0])
    restored.close()


@pytest.fixture
def review_client(tmp_path):
    app = create_app(FakeModels, FakePipeline, tmp_path/'review.sqlite')
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        operator(client)
        cam = camera(client)
        store = app.state.classroom.store
        assert store.record(cam['id'], 'review-generation', dict(id='1', occurredAtMs=150, detail='Review'))
        yield client, store, store.events()[0]


def post_review(client, event, action, **fields):
    return client.post(f'/api/v2/events/{event["id"]}/review', headers=ORIGIN,
                       json=dict(action=action, revision=event['revision'], **fields))


def test_review_happy_path_and_snapshot_broadcast(review_client):
    client, store, event = review_client
    started = time.time()*1000
    with client.websocket_connect('ws://127.0.0.1:8765/api/v2/operator', headers=ORIGIN) as socket:
        assert socket.receive_json()['events'][0] == {**event, 'clip': {'status': 'none', 'frames': 0}}
        for revision, (action, fields) in enumerate([
            ('view', {}), ('confirm', dict(guard='G2', note='  Staff notified.  ')),
            ('on_scene', {}), ('clear', {}),
        ], start=1):
            response = post_review(client, event, action, **fields)
            assert response.status_code == 200, response.text
            event = response.json()
            assert event['revision'] == revision
            assert started <= event['updated_at'] <= time.time()*1000
            snapshot_event = socket.receive_json()['events'][0]
            assert {key: value for key, value in snapshot_event.items() if key != 'clip'} == event
    assert event['status'] == 'resolved' and event['decision'] == 'confirmed'
    assert event['guard'] == 'G2' and event['note'] == 'Staff notified.'
    assert event['reason'] is None
    assert started <= event['reviewed_at'] <= event['decided_at'] == event['alerted_at']
    assert event['alerted_at'] <= event['on_scene_at'] <= event['updated_at']
    assert not any('frame' in key or 'image' in key for key in event)
    audit = [dict(row) for row in store.db.execute('SELECT * FROM event_audit ORDER BY revision')]
    assert [row['action'] for row in audit] == ['view', 'confirm', 'on_scene', 'clear']
    assert [row['revision'] for row in audit] == [1, 2, 3, 4]
    assert [row['status'] for row in audit] == ['acknowledged']*3 + ['resolved']
    assert audit[-1]['changed_at'] == event['updated_at']
    assert client.get('/api/v2/state').json()['analytics'] == dict(total=1,pending=0,resolved=1,confirmed=1,falseAlarms=0)


@pytest.mark.parametrize('reason', ['play_sport', 'greeting', 'camera_glitch', 'other'])
def test_review_dismiss_and_analytics(review_client, reason):
    client, store, event = review_client
    response = post_review(client, event, 'dismiss', reason=reason, note='  ')
    assert response.status_code == 200
    event = response.json()
    assert event['status'] == 'resolved' and event['decision'] == 'false_alarm'
    assert event['reason'] == reason and event['note'] is None
    assert event['decided_at'] == event['reviewed_at'] == event['updated_at']
    assert store.analytics() == dict(total=1,pending=0,resolved=1,confirmed=0,falseAlarms=1)
    assert store.db.execute('SELECT action FROM event_audit').fetchone()[0] == 'dismiss'
    assert post_review(client, event, 'confirm').status_code == 409


def test_review_conflicts_and_idempotent_view(review_client):
    client, store, original = review_client
    for action in ('dismiss', 'alert', 'on_scene', 'clear'):
        response = post_review(client, original, action)
        assert response.status_code == 409
        assert response.json() == {'detail': 'Invalid review action.'}
    assert store.events()[0] == original
    assert store.db.execute('SELECT COUNT(*) FROM event_audit').fetchone()[0] == 0
    event = post_review(client, original, 'view').json()
    assert post_review(client, original, 'view').json() == event
    response = post_review(client, original, 'confirm')
    assert response.status_code == 409
    assert response.json() == {'detail': 'Event changed. Refresh and try again.'}
    confirmed = post_review(client, event, 'confirm').json()
    assert confirmed['reviewed_at'] == event['reviewed_at']
    assert confirmed['guard'] is None and confirmed['alerted_at'] is None
    for action in ('confirm', 'dismiss', 'alert', 'on_scene'):
        assert post_review(client, confirmed, action).status_code == 409
    assert post_review(client, original, 'view').json() == confirmed
    cleared = post_review(client, confirmed, 'clear').json()
    assert post_review(client, original, 'view').json() == cleared
    for action in ('confirm', 'dismiss', 'alert', 'on_scene', 'clear'):
        assert post_review(client, cleared, action, guard='G2', reason='other').status_code == 409
    assert store.db.execute('SELECT COUNT(*) FROM event_audit').fetchone()[0] == 3


def test_review_confirm_without_view_and_realert(review_client):
    client, store, event = review_client
    event = post_review(client, event, 'confirm', note='Confirmed').json()
    assert event['reviewed_at'] == event['decided_at']
    event = post_review(client, event, 'alert', guard='G2').json()
    first_alert = event['alerted_at']
    event = post_review(client, event, 'on_scene').json()
    assert post_review(client, event, 'on_scene').status_code == 409
    event = post_review(client, event, 'alert', guard='G12').json()
    assert event['guard'] == 'G12' and event['alerted_at'] >= first_alert
    assert event['on_scene_at'] is None and event['note'] == 'Confirmed'
    assert post_review(client, event, 'on_scene').status_code == 200


@pytest.mark.parametrize('fields', [
    {'guard': 'g2'}, {'guard': 'G123'}, {'guard': 'G2\n'}, {'guard': ''},
    {'note': 'x'*281}, *({'note': f'{chr(c)}ok'} for c in range(32)),
    {'reason': 'unknown'}, {'action': 'unknown'}, {'revision': -1}, {'unexpected': True},
])
def test_review_input_validation(review_client, fields):
    client, store, event = review_client
    response = client.post(f'/api/v2/events/{event["id"]}/review', headers=ORIGIN,
                           json=dict({'action': 'confirm', 'revision': 0}, **fields))
    assert response.status_code == 422
    assert store.events()[0] == event
    assert store.db.execute('SELECT COUNT(*) FROM event_audit').fetchone()[0] == 0


def test_review_auth_missing_event_and_legacy_patch(review_client):
    client, store, event = review_client
    assert post_review(client, dict(id='missing', revision=0), 'view').status_code == 404
    assert client.post(f'/api/v2/events/{event["id"]}/review', json=dict(action='view', revision=0)).status_code == 403
    response = client.patch(f'/api/v2/events/{event["id"]}', headers=ORIGIN,
                            json=dict(status='acknowledged', revision=0))
    assert response.status_code == 200
    assert post_review(client, event, 'view').json() == response.json()
    assert client.patch(f'/api/v2/events/{event["id"]}', headers=ORIGIN,
                        json=dict(status='resolved', revision=1)).status_code == 200
    assert all(row[0] is None for row in store.db.execute('SELECT action FROM event_audit'))
    client.cookies.delete('nivra_operator')
    assert post_review(client, event, 'view').status_code == 403


def create_v1_database(path):
    # Deliberately use the original DDL, independent of Store's current schema.
    with sqlite3.connect(path) as db:
        db.executescript('''
            CREATE TABLE schema_version(version INTEGER NOT NULL);
            INSERT INTO schema_version VALUES(1);
            CREATE TABLE cameras(id TEXT PRIMARY KEY, name TEXT NOT NULL,
                building TEXT NOT NULL, floor TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
                created REAL NOT NULL);
            CREATE TABLE events(id TEXT PRIMARY KEY, camera_id TEXT NOT NULL,
                generation TEXT NOT NULL, source_id TEXT NOT NULL, received_at REAL NOT NULL,
                camera_name TEXT NOT NULL, location TEXT NOT NULL, source_ms REAL NOT NULL,
                evidence_ms REAL NOT NULL, model TEXT NOT NULL, detail TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open', revision INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL, UNIQUE(camera_id,generation,source_id));
            CREATE TABLE event_audit(event_id TEXT NOT NULL, status TEXT NOT NULL,
                revision INTEGER NOT NULL, changed_at REAL NOT NULL);
            INSERT INTO cameras VALUES('camera', '8A', 'Main', '1', 1, 100);
            INSERT INTO events VALUES('event', 'camera', 'generation', 'source', 100,
                '8A', 'Main / 1', 150, 100, 'model', 'Review', 'acknowledged', 1, 200);
            INSERT INTO event_audit VALUES('event', 'acknowledged', 1, 200);
        ''')


def test_migrate_v1_database_preserves_rows_and_reopens(tmp_path):
    path = tmp_path/'v1.sqlite'
    create_v1_database(path)
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        old_event = dict(db.execute('SELECT * FROM events').fetchone())
        old_camera = dict(db.execute('SELECT * FROM cameras').fetchone())
    store = Store(path)
    assert store.db.execute('SELECT version FROM schema_version').fetchone()[0] == 7
    event = store.events()[0]
    assert {key: event[key] for key in old_event} == old_event
    assert {key: store.camera('camera')[key] for key in old_camera} == old_camera
    assert store.camera('camera')['label'] == 'CAM-01'
    added = {'reviewed_at','decision','reason','note','guard','decided_at','alerted_at','on_scene_at','guard_ack_at','guard_declined_at','floor_id','reviewer_id','escalated_at','gps'}
    assert event.keys() - old_event.keys() == added
    assert all(event[key] is None for key in added)
    assert dict(store.db.execute('SELECT * FROM event_audit').fetchone()) == dict(
        event_id='event', status='acknowledged', revision=1, changed_at=200, action=None, actor=None)
    event = store.review('event', 'confirm', 1, guard='G2')
    assert store.record('camera', 'new-generation', dict(id='new', occurredAtMs=500))
    store.close()
    restored = Store(path)
    assert next(row for row in restored.events() if row['id'] == 'event') == event
    assert restored.analytics() == dict(total=2,pending=1,resolved=0,confirmed=1,falseAlarms=0)
    restored.close()


def test_migration_rolls_back_all_ddl_on_failure(tmp_path):
    path = tmp_path/'broken.sqlite'
    create_v1_database(path)
    with sqlite3.connect(path) as db:
        db.execute('DROP TABLE event_audit')
    with pytest.raises(sqlite3.OperationalError): Store(path)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT version FROM schema_version').fetchone()[0] == 1
        assert 'reviewed_at' not in {row[1] for row in db.execute('PRAGMA table_info(events)')}
        assert db.execute('SELECT id FROM events').fetchone()[0] == 'event'


def test_fresh_v7_and_unknown_future_schema(tmp_path):
    path = tmp_path/'schema.sqlite'
    store = Store(path)
    assert store.db.execute('SELECT version FROM schema_version').fetchone()[0] == 7
    assert store.analytics() == dict(total=0,pending=0,resolved=0,confirmed=0,falseAlarms=0)
    with store.db: store.db.execute('UPDATE schema_version SET version=8')
    store.close()
    with pytest.raises(ValueError, match='Unsupported classroom metadata schema'): Store(path)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT version FROM schema_version').fetchone()[0] == 8


def test_concurrent_reviews_have_only_one_winner(tmp_path):
    path = tmp_path/'concurrent.sqlite'
    store = Store(path)
    cam = store.add_camera('8A', 'Main', '1')
    store.record(cam['id'], 'generation', dict(id='1', occurredAtMs=100))
    event = store.events()[0]
    barrier = Barrier(2)

    def review(action):
        connection = Store(path)
        try:
            barrier.wait(timeout=5)
            try: return connection.review(event['id'], action, 0, reason='other')
            except ValueError as error: return str(error)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(review, ['confirm', 'dismiss']))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert 'Event changed. Refresh and try again.' in results
    assert store.events()[0]['revision'] == 1
    assert store.db.execute('SELECT COUNT(*) FROM event_audit').fetchone()[0] == 1
    store.close()


def test_review_audit_failure_rolls_back_event(review_client):
    client, store, event = review_client
    with store.db:
        store.db.execute('''CREATE TRIGGER reject_audit BEFORE INSERT ON event_audit
            BEGIN SELECT RAISE(ABORT, 'audit failed'); END''')
    with pytest.raises(sqlite3.IntegrityError, match='audit failed'):
        store.review(event['id'], 'confirm', 0)
    assert store.events()[0] == event
    assert store.db.execute('SELECT COUNT(*) FROM event_audit').fetchone()[0] == 0


GUARD_FIELDS = {'id', 'camera_id', 'camera_name', 'location', 'detail', 'note',
                'received_at', 'alerted_at', 'guard_ack_at', 'guard_declined_at',
                'on_scene_at', 'status', 'revision', 'gps'}


def guard_pair_token(client, guard='G2'):
    store = client.app.state.classroom.store
    if not store.guard_by_callsign(guard): store.add_guard(guard, 'Guard '+guard)
    response = client.post(f'/api/v2/guards/{guard}/pair', headers=ORIGIN)
    assert response.status_code == 200
    data = response.json()
    assert data['expiresInSeconds'] == 300
    assert '/guard#pair=' in data['url']
    return parse_qs(urlsplit(data['url']).fragment)['pair'][0]


def guard_phone(client, guard='G2'):
    token = guard_pair_token(client, guard)
    phone = TestClient(client.app, base_url='http://127.0.0.1:8765')
    phone.portal = client.portal
    response = phone.post('/api/v2/guard/pair', headers=ORIGIN, json={'token': token})
    assert response.status_code == 200
    assert response.json() == {'guard': guard}
    return phone


def guard_action(phone, event, action, **extra):
    return phone.post(f'/api/v2/guard/events/{event["id"]}', headers=ORIGIN,
                      json=dict(action=action, revision=event['revision'], **extra))


def test_guard_stream_alert_and_full_lifecycle(review_client):
    client, store, event = review_client
    phone = guard_phone(client)
    with phone.websocket_connect('ws://127.0.0.1:8765/api/v2/guard/stream', headers=ORIGIN) as socket:
        initial = socket.receive_json()
        assert set(initial) == {'type', 'version', 'guard', 'floor', 'serverTime', 'alerts'}
        assert initial['type'] == 'guard-snapshot' and initial['version'] == 2
        assert initial['guard']['callsign'] == 'G2' and initial['alerts'] == []
        assert initial['floor'] is None and initial['guard']['presence']['online'] is True
        assert abs(initial['serverTime']-time.time()*1000) < 5000
        client.portal.call(client.app.state.classroom.broadcast, b'private-camera-frame', True, event['camera_id'])
        event = post_review(client, event, 'confirm', guard='G2', note='Please attend').json()
        alert = socket.receive_json()['alerts'][0]
        assert set(alert) == GUARD_FIELDS | {'placement', 'floorId'}
        assert alert == {**{key: event[key] for key in GUARD_FIELDS}, 'placement': None, 'floorId': None}
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/operator', headers=ORIGIN) as operator_socket:
            operator_socket.receive_json()
            for action in ['ack', 'on_scene', 'clear']:
                response = guard_action(phone, alert, action)
                assert response.status_code == 200, response.text
                updated = response.json()
                assert set(updated) == GUARD_FIELDS
                assert updated['revision'] == alert['revision']+1
                assert socket.receive_json()['alerts'][0] == {**updated, 'placement': None, 'floorId': None}
                assert operator_socket.receive_json()['events'][0]['revision'] == updated['revision']
                alert = updated
        assert alert['status'] == 'resolved'
        assert event['alerted_at'] <= alert['guard_ack_at'] <= alert['on_scene_at']
        assert alert['guard_declined_at'] is None
    assert [row[0] for row in store.db.execute('SELECT action FROM event_audit ORDER BY revision')] == [
        'confirm', 'guard:ack', 'guard:on_scene', 'guard:clear']
    phone.close()


def test_guard_conflicts_decline_and_realert(review_client):
    client, store, event = review_client
    phone = guard_phone(client)
    event = post_review(client, event, 'confirm', guard='G2').json()
    for action in ['on_scene', 'clear']:
        assert guard_action(phone, event, action).status_code == 409
    declined = guard_action(phone, event, 'decline').json()
    assert declined['guard_declined_at'] is not None and declined['guard_ack_at'] is None
    for action in ['ack', 'decline', 'on_scene', 'clear']:
        assert guard_action(phone, declined, action).status_code == 409
    response = guard_action(phone, event, 'ack')
    assert response.status_code == 409
    assert response.json() == {'detail': 'Event changed. Refresh and try again.'}
    event = post_review(client, declined, 'alert', guard='G2').json()
    assert all(event[key] is None for key in ['guard_ack_at', 'guard_declined_at', 'on_scene_at'])
    event = guard_action(phone, event, 'ack').json()
    for action in ['ack', 'decline', 'clear']:
        assert guard_action(phone, event, action).status_code == 409
    event = guard_action(phone, event, 'on_scene').json()
    assert guard_action(phone, event, 'on_scene').status_code == 409
    event = post_review(client, event, 'alert', guard='G2').json()
    assert all(event[key] is None for key in ['guard_ack_at', 'guard_declined_at', 'on_scene_at'])
    # Operator override actions still work without a guard acknowledgement.
    event = post_review(client, event, 'on_scene').json()
    event = post_review(client, event, 'clear').json()
    for action in ['ack', 'decline', 'on_scene', 'clear']:
        assert guard_action(phone, event, action).status_code == 409
    phone.close()


def test_guard_isolation_and_reassignment(review_client):
    client, store, event = review_client
    one, two = guard_phone(client, 'G1'), guard_phone(client, 'G2')
    event = post_review(client, event, 'confirm', guard='G1').json()
    with one.websocket_connect('ws://127.0.0.1:8765/api/v2/guard/stream', headers=ORIGIN) as first:
        with two.websocket_connect('ws://127.0.0.1:8765/api/v2/guard/stream', headers=ORIGIN) as second:
            assert first.receive_json()['alerts'][0]['id'] == event['id']
            assert second.receive_json()['alerts'] == []
            denied = guard_action(two, event, 'ack')
            missing = guard_action(two, dict(id='missing', revision=0), 'ack')
            assert denied.status_code == missing.status_code == 404
            assert denied.json() == missing.json() == {'detail': 'Event not found'}
            event = post_review(client, event, 'alert', guard='G2').json()
            assert first.receive_json()['alerts'] == []
            assert second.receive_json()['alerts'][0]['id'] == event['id']
            assert guard_action(one, event, 'ack').status_code == 404
    assert one.get('/api/v2/state').status_code == 403
    assert one.post('/api/v2/guards/G3/pair', headers=ORIGIN).status_code == 403
    assert post_review(one, event, 'clear').status_code == 403
    one.close(); two.close()


def test_guard_pair_auth_cookie_used_expired_and_revoke(review_client):
    client, store, event = review_client
    service = client.app.state.classroom
    token = guard_pair_token(client)
    assert token not in service.guard_pairs and digest(token) in service.guard_pairs
    phone = TestClient(client.app, base_url='http://127.0.0.1:8765')
    phone.portal = client.portal
    assert phone.get('/api/v2/guard/session').status_code == 403
    assert phone.post('/api/v2/guard/pair', headers={'origin':'https://bad.example'}, json={'token':token}).status_code == 403
    response = phone.post('/api/v2/guard/pair', headers=ORIGIN, json={'token':token})
    assert response.status_code == 200
    header = response.headers['set-cookie'].lower()
    assert 'httponly' in header and 'samesite=strict' in header
    assert 'path=/api/v2/guard' in header and 'max-age=43200' in header
    assert 'secure' not in header
    credential = phone.cookies.get(GUARD_COOKIE)
    assert credential not in service.guard_credentials and digest(credential) in service.guard_credentials
    assert GUARD_COOKIE not in phone.build_request('GET', '/api/v2/state').headers.get('cookie', '')
    assert phone.get('/api/v2/guard/session').json() == {'guard':'G2'}
    assert phone.post('/api/v2/guard/pair', headers=ORIGIN, json={'token':token}).status_code == 403
    with phone.websocket_connect('ws://127.0.0.1:8765/api/v2/guard/stream', headers=ORIGIN) as socket:
        socket.receive_json()
        new_token = guard_pair_token(client)
        with pytest.raises(WebSocketDisconnect) as closed: socket.receive_json()
        assert closed.value.code == 1008
    assert phone.get('/api/v2/guard/session').status_code == 403
    service.guard_pairs[digest(new_token)] = ('G2', time.monotonic()-1)
    assert phone.post('/api/v2/guard/pair', headers=ORIGIN, json={'token':new_token}).status_code == 403
    older = guard_pair_token(client)
    guard_pair_token(client)
    assert phone.post('/api/v2/guard/pair', headers=ORIGIN, json={'token':older}).status_code == 403
    phone.close()


def test_guard_secure_pair_logout_and_expiry(review_client, monkeypatch):
    client, store, event = review_client
    service = client.app.state.classroom
    public = 'https://localhost'
    service.public = public
    service.origins.add(public)
    token = guard_pair_token(client)
    phone = TestClient(client.app, base_url=public)
    phone.portal = client.portal
    headers = {'origin':public}
    response = phone.post('/api/v2/guard/pair', headers=headers, json={'token':token})
    assert response.status_code == 200 and 'Secure' in response.headers['set-cookie']
    with phone.websocket_connect('wss://localhost/api/v2/guard/stream', headers=headers) as socket:
        socket.receive_json()
        assert phone.post('/api/v2/guard/logout', headers=ORIGIN).status_code == 204
        with pytest.raises(WebSocketDisconnect): socket.receive_json()
    assert phone.get('/api/v2/guard/session').status_code == 403
    assert not service.guard_credentials
    phone.close()
    phone = guard_phone(client)
    key = digest(phone.cookies.get(GUARD_COOKIE))
    service.guard_credentials[key] = ('G2', time.monotonic()-1)
    assert phone.get('/api/v2/guard/session').status_code == 403
    assert guard_action(phone, event, 'ack').status_code == 403
    with pytest.raises(WebSocketDisconnect) as closed:
        with phone.websocket_connect('ws://127.0.0.1:8765/api/v2/guard/stream', headers=ORIGIN): pass
    assert closed.value.code == 4401
    phone.close()


def test_guard_stream_auth_limit_keepalive_and_active_expiry(review_client, monkeypatch):
    client, store, event = review_client
    monkeypatch.setattr('nivra.classroom.GUARD_SNAPSHOT_SECONDS', .05)
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/guard/stream', headers=ORIGIN): pass
    assert closed.value.code == 4401
    phone = guard_phone(client)
    for headers in ({}, {'origin':'https://bad.example'}):
        with pytest.raises(WebSocketDisconnect) as closed:
            with phone.websocket_connect('ws://127.0.0.1:8765/api/v2/guard/stream', headers=headers): pass
        assert closed.value.code == 4403
    with phone.websocket_connect('ws://127.0.0.1:8765/api/v2/guard/stream', headers=ORIGIN) as first:
        snapshot = first.receive_json()
        assert first.receive_json()['serverTime'] > snapshot['serverTime']
        with phone.websocket_connect('ws://127.0.0.1:8765/api/v2/guard/stream', headers=ORIGIN) as second:
            second.receive_json()
            with phone.websocket_connect('ws://127.0.0.1:8765/api/v2/guard/stream', headers=ORIGIN) as third:
                third.receive_json()
                with phone.websocket_connect('ws://127.0.0.1:8765/api/v2/guard/stream', headers=ORIGIN) as fourth:
                    with pytest.raises(WebSocketDisconnect) as closed: fourth.receive_json()
                    assert closed.value.code == 1013
        service = client.app.state.classroom
        service.guard_credentials[digest(phone.cookies.get(GUARD_COOKIE))] = ('G2', time.monotonic()-1)
        with pytest.raises(WebSocketDisconnect) as closed:
            while True: first.receive_json()
        assert closed.value.code == 4401
    phone.close()


def test_guard_pair_rate_and_credential_limits(review_client):
    client, store, event = review_client
    service = client.app.state.classroom
    phone = TestClient(client.app, base_url='http://127.0.0.1:8765')
    phone.portal = client.portal
    for _ in range(20):
        assert phone.post('/api/v2/guard/pair', headers=ORIGIN, json={'token':'x'*32}).status_code == 403
    token = guard_pair_token(client)
    assert phone.post('/api/v2/guard/pair', headers=ORIGIN, json={'token':token}).status_code == 429
    assert digest(token) in service.guard_pairs
    service.guard_attempts = {key:time.monotonic()-61 for key in service.guard_attempts}
    assert phone.post('/api/v2/guard/pair', headers=ORIGIN, json={'token':token}).status_code == 200
    token = guard_pair_token(client)
    service.guard_credentials = {str(i):('G2', time.monotonic()+100) for i in range(2)}
    assert phone.post('/api/v2/guard/pair', headers=ORIGIN, json={'token':token}).status_code == 429
    token = guard_pair_token(client)
    service.guard_credentials = {str(i):(f'G{i+10}', time.monotonic()+100) for i in range(10)}
    assert phone.post('/api/v2/guard/pair', headers=ORIGIN, json={'token':token}).status_code == 429
    token = guard_pair_token(client)
    service.guard_credentials = {key:(value[0], time.monotonic()-1) for key,value in service.guard_credentials.items()}
    assert phone.post('/api/v2/guard/pair', headers=ORIGIN, json={'token':token}).status_code == 200
    assert len(service.guard_credentials) == 1
    phone.close()


@pytest.mark.parametrize('payload', [dict(action='confirm',revision=0), dict(action='ack',revision=-1),
                                  dict(action='ack',revision=0,guard='G1')])
def test_guard_input_validation(review_client, payload):
    client, store, event = review_client
    phone = guard_phone(client)
    assert phone.post(f'/api/v2/guard/events/{event["id"]}', headers=ORIGIN, json=payload).status_code == 422
    assert client.post('/api/v2/guards/G123/pair', headers=ORIGIN).status_code == 422
    assert client.post('/api/v2/guards/g2/pair', headers=ORIGIN).status_code == 422
    assert phone.post('/api/v2/guard/logout').status_code == 403
    assert phone.post(f'/api/v2/guard/events/{event["id"]}', json=dict(action='ack', revision=0)).status_code == 403
    phone.close()


def test_guard_alert_filter_order_and_limit(review_client):
    client, store, event = review_client
    now = time.time()*1000
    for number in range(15):
        store.record(event['camera_id'], 'guard-filter', dict(id=str(number),occurredAtMs=number))
    with store.db:
        for number, row in enumerate(store.events()):
            store.db.execute('''UPDATE events SET decision='confirmed',guard='G2',status='acknowledged',
                alerted_at=?,updated_at=? WHERE id=?''', (now+number, now, row['id']))
    alerts = store.guard_alerts('G2', now)
    assert len(alerts) == 10
    assert [row['alerted_at'] for row in alerts] == sorted([row['alerted_at'] for row in alerts], reverse=True)
    assert all(set(row) == GUARD_FIELDS for row in alerts)
    newest = alerts[0]['id']
    with store.db:
        store.db.execute("UPDATE events SET status='resolved', updated_at=? WHERE id=?", (now-30*60*1000, newest))
    assert store.guard_alerts('G2', now)[0]['id'] == newest
    assert newest not in {row['id'] for row in store.guard_alerts('G2', now+1)}
    for changes in ["guard='G1'", "decision=NULL", "alerted_at=NULL"]:
        with store.db:
            store.db.execute("UPDATE events SET guard='G2',decision='confirmed',alerted_at=?,status='acknowledged' WHERE id=?", (now+100, newest))
            store.db.execute(f'UPDATE events SET {changes} WHERE id=?', (newest,))
        assert newest not in {row['id'] for row in store.guard_alerts('G2', now)}


def test_migrate_v2_to_v4_preserves_review_data(tmp_path):
    path = tmp_path/'v2.sqlite'
    create_v1_database(path)
    with sqlite3.connect(path) as db:
        for column in ['reviewed_at REAL','decision TEXT','reason TEXT','note TEXT','guard TEXT',
                       'decided_at REAL','alerted_at REAL','on_scene_at REAL']:
            db.execute(f'ALTER TABLE events ADD COLUMN {column}')
        db.execute('ALTER TABLE event_audit ADD COLUMN action TEXT')
        db.execute('UPDATE schema_version SET version=2')
        db.execute("UPDATE events SET decision='confirmed',guard='G2',alerted_at=300,note='Attend'")
        db.execute("UPDATE event_audit SET action='confirm'")
    store = Store(path)
    event = store.events()[0]
    assert store.db.execute('SELECT version FROM schema_version').fetchone()[0] == 7
    assert event['decision'] == 'confirmed' and event['guard'] == 'G2' and event['note'] == 'Attend'
    assert event['guard_ack_at'] is None and event['guard_declined_at'] is None
    assert store.db.execute('SELECT action FROM event_audit').fetchone()[0] == 'confirm'
    assert store.guard_action('event', 'G2', 'ack', 1)['guard_ack_at'] is not None
    store.close()


def test_v3_migration_failure_rolls_back_v1_to_v2_too(tmp_path):
    path = tmp_path/'bad-v1.sqlite'
    create_v1_database(path)
    with sqlite3.connect(path) as db:
        # A conflicting column simulates a failed second migration step.
        db.execute('ALTER TABLE events ADD COLUMN guard_declined_at REAL')
    with pytest.raises(sqlite3.OperationalError): Store(path)
    with sqlite3.connect(path) as db:
        columns = {row[1] for row in db.execute('PRAGMA table_info(events)')}
        assert 'guard_ack_at' not in columns and 'decision' not in columns
        assert db.execute('SELECT version FROM schema_version').fetchone()[0] == 1
        assert 'action' not in {row[1] for row in db.execute('PRAGMA table_info(event_audit)')}


def test_roles_one_use_pair_expiry_limit_and_proxy_bootstrap(tmp_path):
    app = create_app(FakeModels,FakePipeline,tmp_path/'db.sqlite')
    with TestClient(app,base_url='http://127.0.0.1:8765') as client:
        assert client.get('/api/v2/state').status_code == 403
        assert client.post('/api/v2/session',headers={'origin':'https://bad.example'}).status_code == 403
        assert client.post('/api/v2/session',headers={**ORIGIN,'x-forwarded-for':'1.2.3.4'}).status_code == 403
        operator(client)
        cam = camera(client)
        token = pair(client,cam['id'])
        assert client.post('/api/v2/camera/pair',json={'token':token},headers=ORIGIN).status_code == 403
        for n in range(11): camera(client,f'Room {n}')
        assert client.post('/api/v2/cameras',json=dict(name='13',building='Main',floor='1'),headers=ORIGIN).status_code == 409
        assert client.post('/api/v2/cameras',json=dict(name=' ',building='Main',floor='1'),headers=ORIGIN).status_code == 422
        client.cookies.delete('nivra_operator')
        assert client.get('/api/v2/camera/session').status_code == 200
        assert client.get('/api/v2/state').status_code == 403
        assert client.post('/api/v2/cameras',json=dict(name='8B',building='Main',floor='1'),headers=ORIGIN).status_code == 403
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect('ws://127.0.0.1:8765/api/v2/operator',headers=ORIGIN): pass


def test_two_cameras_reconnect_and_pausing_revokes_device(tmp_path):
    app = create_app(FakeModels,FakePipeline,tmp_path/'db.sqlite')
    with TestClient(app,base_url='http://127.0.0.1:8765') as client:
        operator(client)
        one,two = camera(client),camera(client,'8B')
        pair(client,one['id'])
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream',headers=ORIGIN) as first:
            first_generation = first.receive_json()['generation']
            first.send_bytes(packet(100)); assert first.receive_json()['type']=='accepted'
            pair(client,two['id'])
            with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream',headers=ORIGIN) as second:
                second.receive_json(); second.send_bytes(packet(100)); second.receive_json()
                for _ in range(100):
                    cameras = client.get('/api/v2/state').json()['cameras']
                    if all(c['framesAnalyzed'] == 1 for c in cameras): break
                    time.sleep(.01)
                assert all(c['framesAnalyzed']==1 and c['feed']=='live' for c in cameras)
                assert cameras[0]['generation'] != cameras[1]['generation']
                # Disabling camera closes its existing connection and invalidates cookie.
                assert client.patch('/api/v2/cameras/'+two['id'],json=dict(name='8B',building='Main',floor='1',enabled=False),headers=ORIGIN).status_code==200
                with pytest.raises(WebSocketDisconnect): second.receive_json()
            assert client.get('/api/v2/camera/session').status_code==403
        pair(client,one['id'])
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream',headers=ORIGIN) as restarted:
            assert restarted.receive_json()['generation'] != first_generation
            restarted.send_bytes(packet(0)); assert restarted.receive_json()['timestampMs']==0
            restarted.send_bytes(packet(0))
            with pytest.raises(WebSocketDisconnect): restarted.receive_json()


def test_latest_only_queue_and_fair_order(tmp_path):
    app = create_app(FakeModels,FakePipeline,tmp_path/'db.sqlite')
    service = app.state.classroom
    service.live = {'a':{'replaced':0},'b':{'replaced':0}}
    service.enqueue('a',('old',))
    service.enqueue('b',('b',))
    service.enqueue('a',('latest',))
    assert list(service.order)==['a','b']
    assert service.pending['a']==('latest',)
    assert service.live['a']['replaced']==1
    assert len(service.pending)==2
    service.store.close()


def test_remote_origin_cannot_bootstrap_operator(tmp_path,monkeypatch):
    monkeypatch.setenv('NIVRA_PUBLIC_ORIGIN','https://camera.example')
    app = create_app(FakeModels,FakePipeline,tmp_path/'db.sqlite')
    with TestClient(app,base_url='https://camera.example') as client:
        assert client.post('/api/v2/session',headers={'origin':'https://camera.example'}).status_code==403
        assert client.post('/api/v2/session',headers=ORIGIN).status_code==403
        assert client.post('/api/v1/session',headers=ORIGIN).status_code==403


def test_remote_publisher_is_scoped_and_malformed_frame_closes(tmp_path,monkeypatch):
    monkeypatch.setenv('NIVRA_PUBLIC_ORIGIN','https://camera.example')
    app=create_app(FakeModels,FakePipeline,tmp_path/'db.sqlite')
    with TestClient(app,base_url='http://127.0.0.1:8765') as client:
        operator(client);cam=camera(client)
        result=client.post('/api/v2/cameras/'+cam['id']+'/pair',headers=ORIGIN).json()
        assert result['remoteReady'] and result['url'].startswith('https://camera.example/camera#')
        token=parse_qs(urlsplit(result['url']).fragment)['pair'][0]
        response=client.post('https://camera.example/api/v2/camera/pair',headers={'origin':'https://camera.example'},json={'token':token})
        assert response.status_code==200
        assert 'Secure' in response.headers['set-cookie']
        assert client.get('https://camera.example/api/v2/state').status_code==403
        with client.websocket_connect('wss://camera.example/api/v2/camera/stream',headers={'origin':'https://camera.example'}) as publisher:
            assert publisher.receive_json()['cameraId']==cam['id']
            publisher.send_text('invalid frame')
            with pytest.raises(WebSocketDisconnect): publisher.receive_json()

@pytest.mark.parametrize('kind', ['camera', 'guard'])
@pytest.mark.parametrize('first', ['code', 'token'])
def test_device_pair_code_and_qr_are_one_capability(review_client, kind, first):
    import re
    client, store, _ = review_client
    service = client.app.state.classroom
    if kind == 'camera':
        subject = camera(client)['id']; path = f'/api/v2/cameras/{subject}/pair'
    else:
        store.add_guard('G2', 'Asha'); path = '/api/v2/guards/G2/pair'
    response = client.post(path, headers=ORIGIN).json()
    code = response['pairingCode']; token = parse_qs(urlsplit(response['url']).fragment)['pair'][0]
    assert re.fullmatch(r'[A-HJ-NP-Z2-9]{8}', code) and response['expiresInSeconds'] == 300
    aliases = service.pair_codes[kind]
    assert code not in aliases and aliases[digest(code)] == digest(token)
    phone = TestClient(client.app, base_url=ORIGIN['origin']); phone.portal = client.portal
    try:
        other = 'guard' if kind == 'camera' else 'camera'
        assert phone.post(f'/api/v2/{other}/pair', headers=ORIGIN, json={'code': code}).status_code == 403
        value = code[:4].lower()+' '+code[4:].lower() if first == 'code' else token
        assert phone.post(f'/api/v2/{kind}/pair', headers=ORIGIN, json={first:value}).status_code == 200
        second = {'token':token} if first == 'code' else {'code':code}
        assert phone.post(f'/api/v2/{kind}/pair', headers=ORIGIN, json=second).status_code == 403
        assert digest(code) not in service.pair_codes[kind]
        assert phone.get('/api/v2/state', headers=ORIGIN).status_code == 403
        assert phone.post('/api/v2/operator/redeem', headers=ORIGIN, json={'code':code}).status_code == 422
    finally: phone.close()

@pytest.mark.parametrize('kind', ['camera', 'guard'])
def test_pair_codes_expire_rotate_and_are_invalid_after_device_removal(review_client, kind):
    client, store, _ = review_client
    service = client.app.state.classroom
    if kind == 'camera':
        record = camera(client); subject = record['id']; path = f'/api/v2/cameras/{subject}/pair'; delete = '/api/v2/cameras/'+subject
    else:
        record = store.add_guard('G2', 'Asha'); subject = 'G2'; path = '/api/v2/guards/G2/pair'; delete = '/api/v2/guards/'+record['id']
    first = client.post(path, headers=ORIGIN).json()
    second = client.post(path, headers=ORIGIN).json()
    assert client.post(f'/api/v2/{kind}/pair', headers=ORIGIN, json={'code':first['pairingCode']}).status_code == 403
    key = service.pair_codes[kind][digest(second['pairingCode'])]
    pairs = service.pairs if kind == 'camera' else service.guard_pairs
    pairs[key] = (subject, time.monotonic()-1)
    assert client.post(f'/api/v2/{kind}/pair', headers=ORIGIN, json={'code':second['pairingCode']}).status_code == 403
    assert not service.pair_codes[kind]
    third = client.post(path, headers=ORIGIN).json()
    if kind == 'camera':
        assert client.patch(delete, headers=ORIGIN, json={'name':record['name'],'building':record['building'],'floor':record['floor'],'enabled':False}).status_code == 200
    else:
        assert client.delete(delete, headers=ORIGIN).status_code == 204
    assert client.post(f'/api/v2/{kind}/pair', headers=ORIGIN, json={'code':third['pairingCode']}).status_code == 403
    assert not service.pair_codes[kind]

@pytest.mark.parametrize('payload', [{}, {'code':'ABCD1234'}, {'code':'AAAAAAAA','token':'x'*32}, {'code':'AAAAAAAA','owner':True}])
def test_device_code_input_cannot_be_ambiguous_or_grant_owner(review_client, payload):
    client, _, _ = review_client
    assert client.post('/api/v2/camera/pair', headers=ORIGIN, json=payload).status_code == 422


def test_pair_code_attempts_are_bounded_per_ip_and_globally_and_expire(monkeypatch):
    from types import SimpleNamespace
    from fastapi import HTTPException
    from nivra.classroom import PairCodeAttempts
    now = [100.0]
    monkeypatch.setattr(time, 'monotonic', lambda:now[0])
    limiter = PairCodeAttempts()
    request = lambda ip:SimpleNamespace(client=SimpleNamespace(host=ip))
    for _ in range(20): limiter.check(request('one'))
    with pytest.raises(HTTPException) as error: limiter.check(request('one'))
    assert error.value.status_code == 429
    for i in range(80): limiter.check(request(str(i)))
    with pytest.raises(HTTPException) as error: limiter.check(request('new-ip'))
    assert error.value.status_code == 429 and len(limiter.recent) == 100
    now[0] += 60
    limiter.check(request('one'))
    assert len(limiter.recent) == 1


def test_owner_removes_camera_without_losing_event_or_audit_and_label_can_be_reused(review_client):
    client, store, event = review_client
    subject = event['camera_id']
    old_label = store.camera(subject)['label']
    viewed = post_review(client, event, 'view').json()
    events = store.events()
    audit = [dict(row) for row in store.db.execute('SELECT * FROM event_audit')]
    link = client.post('/api/v2/cameras/'+subject+'/pair', headers=ORIGIN).json()
    assert client.delete('/api/v2/cameras/'+subject, headers=ORIGIN).status_code == 204
    assert store.camera(subject) is None
    assert store.events() == events
    assert [dict(row) for row in store.db.execute('SELECT * FROM event_audit')] == audit
    assert client.get('/api/v2/state', headers=ORIGIN).json()['events'][0]['id'] == viewed['id']
    assert client.post('/api/v2/camera/pair', headers=ORIGIN, json={'code':link['pairingCode']}).status_code == 403
    token = parse_qs(urlsplit(link['url']).fragment)['pair'][0]
    assert client.post('/api/v2/camera/pair', headers=ORIGIN, json={'token':token}).status_code == 403
    assert client.delete('/api/v2/cameras/'+subject, headers=ORIGIN).status_code == 404
    replacement = camera(client)
    assert replacement['id'] != subject and replacement['label'] == old_label
    assert store.events()[0]['camera_id'] == subject


def test_reviewer_cannot_remove_cameras(review_client):
    client, store, event = review_client
    reviewer = TestClient(client.app, base_url=ORIGIN['origin']); reviewer.portal = client.portal
    try:
        assert reviewer.post('/api/v2/auth/dev', headers=ORIGIN, json={'name':'Reviewer','role':'reviewer'}).status_code == 200
        assert reviewer.delete('/api/v2/cameras/'+event['camera_id'], headers=ORIGIN).status_code == 403
        assert store.camera(event['camera_id']) is not None
    finally: reviewer.close()
