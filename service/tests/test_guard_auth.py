"""Exercise H1's Clerk verifier through the actual guard routes and stream."""
import time

import pytest
from starlette.websockets import WebSocketDisconnect

from test_auth import identity, clerk_app, ORIGIN
from test_guard_push import subscription


def guard_token(mint, **kwargs):
    return mint(metadata={'role': 'guard', 'callsign': 'G2'}, **kwargs)


def seed(app):
    store = app.state.classroom.store
    guard = store.add_guard('G2', 'Guard Two', email='asha@example.test')
    store.add_guard('G3', 'Other Guard')
    camera = store.add_camera('East entrance', 'Main', 'Ground')
    store.record(camera['id'], 'guard-auth', {'id': 'one', 'occurredAtMs': 10})
    return guard, store.events()[0]


def test_clerk_guard_handshake_broadcast_reauth_and_http(clerk_app, tmp_path):
    app, client, mint = clerk_app
    service = app.state.classroom
    service.push.key_path = tmp_path / 'vapid.json'
    guard, event = seed(app)
    token = guard_token(mint)
    headers = {'origin': ORIGIN, 'Authorization': 'Bearer '+token}
    assert client.get('/api/v2/guard/push/key', headers=headers).status_code == 200
    assert client.post('/api/v2/guard/push', headers=headers, json={'subscription': subscription()}).status_code == 204
    assert client.post('/api/v2/guard/shift', headers=headers, json={'shift': 'on_shift'}).status_code == 200
    service.push.sender = lambda **kwargs: None
    with client.websocket_connect(ORIGIN.replace('http:', 'ws:')+'/api/v2/guard/stream', headers={'origin': ORIGIN}) as socket:
        socket.send_json({'type': 'auth', 'token': token})
        snapshot = socket.receive_json()
        assert snapshot['version'] == 2 and snapshot['guard']['id'] == guard['id']
        assert snapshot['guard']['presence']['online'] is True and snapshot['guard']['push'] is True
        assert snapshot['guard']['userId'] == 'user_1'
        assert not service.guard_credentials
        before = service.push.last_seen['G2']
        socket.send_json({'type': 'auth', 'token': guard_token(mint)})
        for _ in range(100):
            if service.push.last_seen['G2'] > before: break
            time.sleep(.005)
        assert service.push.last_seen['G2'] > before
        response = client.post(f'/api/v2/events/{event["id"]}/review',
            headers={'origin': ORIGIN, 'Authorization': 'Bearer '+mint()},
            json={'action': 'confirm', 'guard': 'G2', 'revision': 0})
        assert response.status_code == 200
        for _ in range(5):
            snapshot = socket.receive_json()
            if snapshot['alerts']: break
        assert snapshot['alerts'][0]['id'] == event['id']
        response = client.post(f'/api/v2/guard/events/{event["id"]}', headers=headers,
                               json={'action': 'ack', 'revision': 1})
        assert response.status_code == 200
        assert service.store.db.execute("SELECT actor FROM event_audit WHERE action='guard:ack'").fetchone()[0] == 'user_1'
    for _ in range(100):
        if not service.push.presence('G2')['online']: break
        time.sleep(.005)
    assert service.push.presence('G2')['online'] is False


@pytest.mark.parametrize('role', ['reviewer', 'admin'])
def test_clerk_wrong_role_never_receives_guard_snapshot(clerk_app, role):
    app, client, mint = clerk_app
    seed(app)
    with client.websocket_connect(ORIGIN.replace('http:', 'ws:')+'/api/v2/guard/stream', headers={'origin': ORIGIN}) as socket:
        socket.send_json({'type': 'auth', 'token': mint(metadata={'role': role})})
        with pytest.raises(WebSocketDisconnect) as error: socket.receive_json()
        assert error.value.code == 4403
    assert not app.state.classroom.guard_sockets


def test_clerk_guard_missing_handshake_and_expired_reauth(clerk_app, monkeypatch):
    app, client, mint = clerk_app
    seed(app)
    monkeypatch.setattr('nivra.auth.WS_AUTH_TIMEOUT', .03)
    url = ORIGIN.replace('http:', 'ws:')+'/api/v2/guard/stream'
    with client.websocket_connect(url, headers={'origin': ORIGIN}) as socket:
        with pytest.raises(WebSocketDisconnect) as error: socket.receive_json()
        assert error.value.code == 4401
    monkeypatch.setattr('nivra.auth.WS_AUTH_TIMEOUT', 5)
    token = guard_token(mint)
    with client.websocket_connect(url, headers={'origin': ORIGIN}) as socket:
        socket.send_json({'type': 'auth', 'token': token})
        assert socket.receive_json()['guard']['callsign'] == 'G2'
        def expire():
            authentication = next(iter(app.state.classroom.socket_auth.values()))
            authentication.deadline = time.monotonic() - 1
        client.portal.call(expire)
        socket.send_json({'type': 'auth', 'token': token})
        with pytest.raises(WebSocketDisconnect) as error:
            while True: socket.receive_json()
        assert error.value.code == 4401


def test_clerk_guard_reauth_rejects_role_change(clerk_app):
    app, client, mint = clerk_app
    seed(app)
    with client.websocket_connect(ORIGIN.replace('http:', 'ws:')+'/api/v2/guard/stream', headers={'origin': ORIGIN}) as socket:
        socket.send_json({'type': 'auth', 'token': guard_token(mint)})
        socket.receive_json()
        socket.send_json({'type': 'auth', 'token': mint(metadata={'role': 'reviewer'})})
        with pytest.raises(WebSocketDisconnect) as error:
            while True: socket.receive_json()
        assert error.value.code == 4403


def test_deleted_guard_socket_cannot_follow_reused_callsign(clerk_app):
    app, client, mint = clerk_app
    service = app.state.classroom
    guard, _ = seed(app)
    with client.websocket_connect(ORIGIN.replace('http:', 'ws:')+'/api/v2/guard/stream', headers={'origin': ORIGIN}) as socket:
        socket.send_json({'type': 'auth', 'token': guard_token(mint)})
        socket.receive_json()
        service.store.delete_guard(guard['id'])
        service.store.add_guard('G2', 'Replacement Guard')
        client.portal.call(service.broadcast, service.snapshot())
        socket.send_text('ping')
        with pytest.raises(WebSocketDisconnect) as error:
            while True:
                snapshot = socket.receive_json()
                assert snapshot['guard']['name'] != 'Replacement Guard'
        assert error.value.code == 4403
