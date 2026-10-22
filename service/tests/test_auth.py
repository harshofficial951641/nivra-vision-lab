"""Real RSA/JWT verification with an in-process fake Clerk HTTP transport."""
import asyncio
import copy
import json
import time
from urllib.parse import parse_qs, urlsplit

from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient
import httpx
import jwt
import pytest
from starlette.websockets import WebSocketDisconnect

from nivra.auth import AuthService, ClerkClient, Principal, SocketAuth, allowed_origins
from nivra.classroom import GUARD_COOKIE, digest
from nivra.public_gateway import PublicGateway
from nivra.server import create_app

ORIGIN = 'http://127.0.0.1:8765'
ISSUER = 'https://test.clerk.accounts.dev'


@pytest.fixture
def identity(monkeypatch):
    for name in ('NIVRA_AUTH_MODE', 'CLERK_SECRET_KEY', 'CLERK_JWKS_URL', 'NIVRA_ALLOWED_ORIGINS', 'NIVRA_ADMIN_EMAILS', 'NIVRA_PUBLIC_ORIGIN'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('NIVRA_AUTH_MODE', 'clerk')
    monkeypatch.setenv('CLERK_ISSUER', ISSUER)
    monkeypatch.setenv('NIVRA_AUTHORIZED_PARTIES', ORIGIN)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid='key-1', alg='RS256', use='sig')
    users = {'user_1': {'id': 'user_1', 'first_name': 'Asha', 'last_name': 'Patel',
        'primary_email_address_id': 'email_1', 'email_addresses': [{'id': 'email_1',
        'email_address': 'asha@example.test', 'verification': {'status': 'verified'}}],
        'public_metadata': {'role': 'reviewer'}, 'last_active_at': 123}}
    calls, keys = [], [jwk]

    def handler(request):
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, body, dict(request.url.params)))
        if request.url.path == '/.well-known/jwks.json':
            assert 'authorization' not in request.headers
            return httpx.Response(200, json={'keys': keys})
        path = request.url.path.removeprefix('/v1')
        if path == '/invitations': return httpx.Response(200, json={'id': 'inv_test', 'status': 'pending'})
        if path == '/users': return httpx.Response(200, json=list(users.values()))
        if path.endswith('/metadata'):
            user = users[path.split('/')[2]]
            user['public_metadata'].update(body['public_metadata'])
            return httpx.Response(200, json=user)
        if path.startswith('/users/'):
            return httpx.Response(200, json=users[path.split('/')[2]])
        if path == '/sessions': return httpx.Response(200, json=[{'id': 'sess_1'}, {'id': 'sess_2'}])
        if path.endswith('/revoke'): return httpx.Response(200, json={'status': 'revoked'})
        return httpx.Response(404)

    client = ClerkClient('fake-test-secret', transport=httpx.MockTransport(handler))

    def mint(*, kid='key-1', remove=(), **changes):
        claims = dict(sub='user_1', iss=ISSUER, azp=ORIGIN, exp=time.time()+120,
                      nbf=time.time()-1, iat=time.time(), name='Asha', email='asha@example.test', metadata={'role': 'reviewer'})
        claims.update(changes)
        for name in remove: claims.pop(name, None)
        return jwt.encode(claims, key, algorithm='RS256', headers={'kid': kid})

    return client, mint, calls, users, keys


@pytest.fixture
def clerk_app(identity, tmp_path):
    app = create_app(database=tmp_path/'auth.sqlite', relay_only=True)
    app.state.classroom.auth.client = identity[0]
    with TestClient(app, base_url=ORIGIN) as client:
        yield app, client, identity[1]


def headers(mint, role='reviewer', **claims):
    return {'Origin': ORIGIN, 'Authorization': 'Bearer '+mint(metadata={'role': role}, **claims)}


def test_valid_jwt_and_cached_jwks(identity):
    client, mint, calls, _, _ = identity
    auth = AuthService({ORIGIN}, client)
    principal = auth.verify(mint())
    assert principal.user_id == 'user_1' and principal.role == 'reviewer'
    assert principal.auth_mode == 'clerk'
    auth.verify(mint())
    assert len(calls) == 1 and calls[0][1] == '/.well-known/jwks.json'


@pytest.mark.parametrize('changes', [dict(exp=time.time()-30), dict(nbf=time.time()+60),
    dict(azp='https://evil.test'), dict(iss='https://other.clerk.accounts.dev'),
    dict(kid='unknown'), dict(remove=('exp',)), dict(remove=('nbf',)), dict(remove=('azp',)),
    dict(metadata=['bad'])])
def test_invalid_jwt(identity, changes):
    auth = AuthService({ORIGIN}, identity[0])
    with pytest.raises(HTTPException) as error: auth.verify(identity[1](**changes))
    assert error.value.status_code == 401


def test_jwks_rotation_and_kid_miss_rate_limit(identity):
    client, mint, calls, _, keys = identity
    auth = AuthService({ORIGIN}, client)
    auth.verify(mint())
    for _ in range(4):
        with pytest.raises(HTTPException): auth.verify(mint(kid='key-2'))
    assert len(calls) == 1
    keys.append({**keys[0], 'kid': 'key-2'})
    auth._refresh_at -= 6
    assert auth.verify(mint(kid='key-2')).role == 'reviewer'
    assert len(calls) == 2


def test_roles_claim_then_backend_then_verified_bootstrap(identity, monkeypatch):
    client, mint, calls, users, _ = identity
    monkeypatch.setenv('NIVRA_ADMIN_EMAILS', 'asha@example.test')
    auth = AuthService({ORIGIN}, client)
    assert auth.verify(mint(metadata={'role': 'guard', 'callsign': 'G2'})).role == 'guard'
    assert not any('/users/' in call[1] for call in calls)
    assert auth.verify(mint(remove=('metadata',))).role == 'reviewer'
    auth.verify(mint(remove=('metadata',)))
    assert sum('/users/' in call[1] for call in calls) == 1
    users['user_1']['public_metadata'] = {}
    auth._users.clear()
    assert auth.verify(mint(remove=('metadata',))).role == 'admin'
    users['user_1']['email_addresses'][0]['verification']['status'] = 'unverified'
    auth._users.clear()
    assert auth.verify(mint(remove=('metadata',))).role is None


def test_http_roles_me_actor_and_camera_pairing(clerk_app):
    app, client, mint = clerk_app
    service = app.state.classroom
    camera = service.store.add_camera('Cam', 'Main', '1')
    service.store.record(camera['id'], 'gen', {'id': 'one', 'occurredAtMs': 1})
    event = service.store.events()[0]
    assert client.get('/api/v2/me').status_code == 401
    assert client.get('/api/v2/me', headers=headers(mint, 'unknown')).status_code == 403
    response = client.get('/api/v2/me', headers=headers(mint))
    assert response.json() == dict(userId='user_1', name='Asha', email='asha@example.test', role='reviewer', guard=None, authMode='clerk')
    assert client.get('/api/v2/site', headers=headers(mint)).status_code == 200
    assert client.patch('/api/v2/site', headers=headers(mint), json={'name': 'Denied'}).status_code == 403
    assert client.get('/api/v2/state', headers=headers(mint, 'guard')).status_code == 403
    assert client.post('/api/v2/cameras', headers=headers(mint), json={'name': 'Cam', 'building': 'Main', 'floor': '1'}).status_code == 403
    assert client.post(f'/api/v2/cameras/{camera["id"]}/pair', headers=headers(mint)).status_code == 200
    response = client.post(f'/api/v2/events/{event["id"]}/review', headers=headers(mint), json={'action': 'view', 'revision': 0})
    assert response.status_code == 200 and response.json()['reviewer_id'] == 'user_1'


@pytest.mark.parametrize('path', ['/auth/dev', '/auth/dev/logout', '/session', '/operator/invite', '/operator/redeem'])
def test_dev_routes_disabled_in_clerk(clerk_app, path):
    _, client, _ = clerk_app
    response = client.post('/api/v2'+path, headers={'Origin': ORIGIN}, json={'token': 'x'*40})
    assert response.status_code == 404


def test_legacy_cookie_cannot_unlock_clerk(clerk_app):
    app, client, _ = clerk_app
    client.cookies.set('nivra_operator', app.state.classroom.admin_token)
    assert client.get('/api/v2/state').status_code == 401


def test_clerk_guard_qr_requires_matching_identity_and_preserves_token_on_denial(clerk_app):
    app, client, mint = clerk_app
    service = app.state.classroom
    service.store.add_guard('G1', 'First guard')
    service.store.add_guard('G2', 'Second guard')
    assert client.post('/api/v2/guards/G1/pair', headers=headers(mint)).status_code == 403
    response = client.post('/api/v2/guards/G1/pair', headers=headers(mint, 'admin'))
    assert response.status_code == 200
    token = parse_qs(urlsplit(response.json()['url']).fragment)['pair'][0]
    request = {'json': {'token': token}}
    assert client.post('/api/v2/guard/pair', headers={'Origin': ORIGIN}, **request).status_code == 401
    for role in ('reviewer', 'admin'):
        assert client.post('/api/v2/guard/pair', headers=headers(mint, role), **request).status_code == 403
    wrong_guard = {'Origin': ORIGIN, 'Authorization': 'Bearer '+mint(sub='user_other',
        email='other@example.test', metadata={'role': 'guard', 'callsign': 'G2'})}
    assert client.post('/api/v2/guard/pair', headers=wrong_guard, **request).status_code == 403
    assert digest(token) in service.guard_pairs
    matching_guard = {'Origin': ORIGIN, 'Authorization': 'Bearer '+mint(metadata={'role': 'guard', 'callsign': 'G1'})}
    response = client.post('/api/v2/guard/pair', headers=matching_guard, **request)
    assert response.status_code == 200 and response.json() == {'guard': 'G1'}
    assert 'set-cookie' not in response.headers
    assert not service.guard_credentials
    assert client.get('/api/v2/guard/session', headers=matching_guard).json() == {'guard': 'G1'}
    assert client.get('/api/v2/guard/session').status_code == 403
    assert client.post('/api/v2/guard/pair', headers=matching_guard, **request).status_code == 403
    # Even a valid developer pairing cookie cannot authorize Clerk mode.
    service.guard_credentials[digest('legacy')] = ('G1', time.monotonic()+60)
    client.cookies.set(GUARD_COOKIE, 'legacy', path='/api/v2/guard')
    assert client.get('/api/v2/guard/session').status_code == 403


def test_guard_qr_missing_record_cannot_revoke_or_create_pair(clerk_app):
    app, client, mint = clerk_app
    service = app.state.classroom
    service.guard_credentials['existing'] = ('G9', time.monotonic()+60)
    response = client.post('/api/v2/guards/G9/pair', headers=headers(mint, 'admin'))
    assert response.status_code == 404
    assert 'existing' in service.guard_credentials
    assert not service.guard_pairs


def test_dev_login_logout_tamper_and_role_isolation(monkeypatch, tmp_path):
    monkeypatch.setenv('NIVRA_AUTH_MODE', 'dev')
    app = create_app(database=tmp_path/'dev.sqlite', relay_only=True)
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.post('/api/v2/auth/dev', headers={'Origin': 'https://evil.test'}, json={'name': 'Asha', 'role': 'admin'}).status_code == 403
        response = client.post('/api/v2/auth/dev', headers={'Origin': ORIGIN}, json={'name': 'Asha', 'role': 'reviewer'})
        assert response.status_code == 200
        assert 'HttpOnly' in response.headers['set-cookie'] and 'SameSite=strict' in response.headers['set-cookie']
        assert client.get('/api/v2/me').json()['role'] == 'reviewer'
        assert client.get('/api/v2/members').status_code == 403
        cookie = client.cookies.get('nivra_dev')
        assert client.post('/api/v2/auth/dev/logout', headers={'Origin': ORIGIN}).status_code == 204
        client.cookies.set('nivra_dev', cookie)
        assert client.get('/api/v2/me').status_code == 401
        client.cookies.set('nivra_dev', cookie+'x')
        assert client.get('/api/v2/me').status_code == 401


def test_members_invite_patch_delete_and_backend_requests(clerk_app, identity):
    app, client, mint = clerk_app
    _, _, calls, users, _ = identity
    users['user_2'] = {**copy.deepcopy(users['user_1']), 'id': 'user_2'}
    admin = headers(mint, 'admin')
    assert len(client.get('/api/v2/members', headers=admin).json()) == 2
    response = client.post('/api/v2/members/invite', headers=admin, json={'email': 'guard@example.test', 'role': 'guard', 'callsign': 'G2'})
    assert response.status_code == 201
    assert response.json() == {'invitationId': 'inv_test', 'status': 'pending', 'member': None}
    invitation = next(call[2] for call in calls if call[1] == '/v1/invitations')
    assert invitation == {'email_address': 'guard@example.test', 'public_metadata': {'role': 'guard', 'callsign': 'G2'}, 'redirect_url': ORIGIN+'/guard'}
    response = client.patch('/api/v2/members/user_2', headers=admin, json={'role': 'admin'})
    assert response.json()['role'] == 'admin'
    assert client.delete('/api/v2/members/user_2', headers=admin).status_code == 204
    assert users['user_2']['public_metadata']['role'] is None
    assert sum(path.endswith('/revoke') for _, path, _, _ in calls) == 2
    assert client.get('/api/v2/me', headers=headers(mint, sub='user_2')).status_code == 403


def test_operator_handshake_reauth_and_role(clerk_app, monkeypatch):
    app, client, mint = clerk_app
    with client.websocket_connect('ws://127.0.0.1:8765/api/v2/operator', headers={'Origin': ORIGIN}) as socket:
        socket.send_json({'type': 'auth', 'token': mint()})
        assert socket.receive_json()['me'] == {'role': 'reviewer'}
        socket.send_json({'type': 'auth', 'token': mint(metadata={'role': 'admin'})})
        socket.send_text('ping')
        assert socket.receive_json()['me'] == {'role': 'admin'}
        socket.send_json({'type': 'auth', 'token': mint(metadata={'role': 'guard', 'callsign': 'G2'})})
        assert socket.receive()['code'] == 4403
    with client.websocket_connect('ws://127.0.0.1:8765/api/v2/operator', headers={'Origin': ORIGIN}) as socket:
        socket.send_json({'type': 'auth', 'token': mint(exp=time.time()-60)})
        assert socket.receive()['code'] == 4401
    monkeypatch.setattr('nivra.auth.WS_AUTH_TIMEOUT', .04)
    with client.websocket_connect('ws://127.0.0.1:8765/api/v2/operator', headers={'Origin': ORIGIN}) as socket:
        assert socket.receive()['code'] == 4401
    monkeypatch.setattr('nivra.auth.WS_REAUTH_SECONDS', .08)
    with client.websocket_connect('ws://127.0.0.1:8765/api/v2/operator', headers={'Origin': ORIGIN}) as socket:
        socket.send_json({'type': 'auth', 'token': mint()})
        assert socket.receive_json()['type'] == 'snapshot'
        socket.send_text('ping')
        message = socket.receive()
        while message['type'] == 'websocket.send': message = socket.receive()
        assert message['code'] == 4401


def test_guard_socket_helper_and_linking(clerk_app):
    app, client, mint = clerk_app
    service = app.state.classroom
    record = service.store.add_guard('G2', 'Asha')
    token = mint(metadata={'role': 'guard', 'callsign': 'G2'})
    assert client.get('/api/v2/me', headers={'Origin': ORIGIN, 'Authorization': 'Bearer '+token}).json()['guard'] == {'callsign': 'G2'}
    assert service.store.guard(record['id'])['user_id'] == 'user_1'

    class Socket:
        headers = {'origin': ORIGIN}
        cookies = {}
        async def accept(self): pass
        async def close(self, **kwargs): self.code = kwargs['code']
        async def receive(self): return {'type': 'websocket.receive', 'text': json.dumps({'type': 'auth', 'token': self.token})}

    socket = Socket()
    socket.token = token
    result = asyncio.run(service.websocket_auth(socket, roles=('guard',)))
    assert result.identity == 'G2'
    socket.token = mint()
    with pytest.raises(WebSocketDisconnect) as error: asyncio.run(service.websocket_auth(socket, roles=('guard',)))
    assert error.value.code == 4403


def test_origin_configuration_and_local_dev_only(monkeypatch, tmp_path):
    monkeypatch.setenv('NIVRA_AUTH_MODE', 'dev')
    monkeypatch.setenv('NIVRA_ALLOWED_ORIGINS', 'https://192.168.1.10:8443,http://localhost:9999')
    monkeypatch.setenv('NIVRA_PUBLIC_ORIGIN', 'https://demo.example.test')
    app = create_app(database=tmp_path/'origins.sqlite', relay_only=True)
    assert app.state.classroom.origins == {'https://192.168.1.10:8443', 'http://localhost:9999', 'https://demo.example.test'}
    with TestClient(app, base_url='https://192.168.1.10:8443') as client:
        response = client.post('/api/v2/auth/dev', headers={'Origin': 'https://192.168.1.10:8443'}, json={'role': 'admin', 'name': 'Asha'})
        assert response.status_code == 200 and 'Secure' in response.headers['set-cookie']
        assert client.post('https://demo.example.test/api/v2/auth/dev', headers={'Origin': 'https://demo.example.test'}, json={'role': 'admin', 'name': 'Asha'}).status_code == 403


def test_gateway_preserves_authorization_and_ws_auth(clerk_app):
    app, _, mint = clerk_app
    secret = 'fake-relay-'+'a'*45
    gateway = TestClient(PublicGateway(app, secret), base_url=ORIGIN)
    try:
        request_headers = {**headers(mint), 'X-Nivra-Relay': secret}
        assert gateway.get('/api/v2/me', headers=request_headers).json()['userId'] == 'user_1'
        with gateway.websocket_connect('/api/v2/operator', headers={'Origin': ORIGIN, 'X-Nivra-Relay': secret}) as socket:
            socket.send_json({'type': 'auth', 'token': mint()})
            assert socket.receive_json()['type'] == 'snapshot'
    finally: gateway.close()


def test_jwt_rejects_wrong_signature_and_algorithm(identity):
    client, mint, _, _, _ = identity
    auth = AuthService({ORIGIN}, client)
    wrong = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = jwt.decode(mint(), options={'verify_signature': False})
    for token in (jwt.encode(claims, wrong, algorithm='RS256', headers={'kid': 'key-1'}),
                  jwt.encode(claims, 'test-secret', algorithm='HS256', headers={'kid': 'key-1'})):
        with pytest.raises(HTTPException) as error: auth.verify(token)
        assert error.value.status_code == 401


def test_five_second_leeway_and_user_cache_expiry(identity):
    client, mint, calls, _, _ = identity
    auth = AuthService({ORIGIN}, client)
    assert auth.verify(mint(exp=time.time()-2, nbf=time.time()+2)).role == 'reviewer'
    auth.verify(mint(remove=('metadata',)))
    expires, user = auth._users['user_1']
    auth._users['user_1'] = (time.monotonic()-1, user)
    auth.verify(mint(remove=('metadata',)))
    assert sum('/users/' in path for _, path, _, _ in calls) == 2


def test_dev_members_and_guard_link_survive_logout(monkeypatch, tmp_path):
    monkeypatch.setenv('NIVRA_AUTH_MODE', 'dev')
    app = create_app(database=tmp_path/'dev-members.sqlite', relay_only=True)
    with TestClient(app, base_url=ORIGIN) as client:
        origin = {'Origin': ORIGIN}
        assert client.post('/api/v2/auth/dev', headers=origin, json={'name': 'Admin', 'role': 'admin'}).status_code == 200
        member = client.post('/api/v2/members/invite', headers=origin,
            json={'email': 'reviewer@example.test', 'role': 'reviewer'}).json()['member']
        path = '/api/v2/members/'+member['userId']
        assert client.patch(path, headers=origin, json={'role': 'guard'}).json()['role'] == 'guard'
        assert client.delete(path, headers=origin).status_code == 204
        assert all(m['userId'] != member['userId'] for m in client.get('/api/v2/members').json())
        guard = app.state.classroom.store.add_guard('G2', 'Demo guard')
        for _ in range(2):
            response = client.post('/api/v2/auth/dev', headers=origin, json={'name': 'G2', 'role': 'guard'})
            assert response.status_code == 200
            assert client.get('/api/v2/me').json()['guard'] == {'callsign': 'G2'}
            assert app.state.classroom.store.guard(guard['id'])['user_id'] is None
            assert client.post('/api/v2/auth/dev/logout', headers=origin).status_code == 204


def test_guard_action_records_actor_and_rejects_other_identity(clerk_app):
    app, client, mint = clerk_app
    store = app.state.classroom.store
    store.add_guard('G2', 'Asha')
    camera = store.add_camera('Cam', 'Main', '1')
    store.record(camera['id'], 'guard-gen', {'id': 'one', 'occurredAtMs': 1})
    event = store.review(store.events()[0]['id'], 'confirm', 0, guard='G2', actor='reviewer_1')
    token = mint(metadata={'role': 'guard', 'callsign': 'G2'})
    response = client.post('/api/v2/guard/events/'+event['id'],
        headers={'Origin': ORIGIN, 'Authorization': 'Bearer '+token}, json={'action': 'ack', 'revision': 1})
    assert response.status_code == 200
    row = store.db.execute("SELECT actor FROM event_audit WHERE action='guard:ack'").fetchone()
    assert row['actor'] == 'user_1'
    token = mint(sub='user_other', metadata={'role': 'guard', 'callsign': 'G2'})
    assert client.get('/api/v2/me', headers={'Origin': ORIGIN, 'Authorization': 'Bearer '+token}).status_code == 403


def test_default_mode_and_origin_defaults(monkeypatch):
    for name in ('NIVRA_AUTH_MODE', 'CLERK_SECRET_KEY', 'NIVRA_ALLOWED_ORIGINS'):
        monkeypatch.delenv(name, raising=False)
    assert AuthService(allowed_origins()).mode == 'dev'
    assert allowed_origins() == {ORIGIN, 'http://localhost:8765'}
    monkeypatch.setenv('CLERK_SECRET_KEY', 'fake-test-secret')
    assert AuthService(allowed_origins()).mode == 'clerk'


def test_guard_websocket_rsa_handshake_renewal_and_roles(clerk_app, monkeypatch):
    app, client, mint = clerk_app
    app.state.classroom.store.add_guard('G2', 'Asha')
    token = mint(metadata={'role': 'guard', 'callsign': 'G2'})
    with client.websocket_connect('ws://127.0.0.1:8765/api/v2/guard/stream', headers={'Origin': ORIGIN}) as socket:
        socket.send_json({'type': 'auth', 'token': token})
        assert socket.receive_json()['guard']['callsign'] == 'G2'
        socket.send_json({'type': 'auth', 'token': token})
        socket.send_text('ping')
        socket.send_json({'type': 'auth', 'token': mint()})
        message = socket.receive()
        while message['type'] == 'websocket.send': message = socket.receive()
        assert message['code'] == 4403
    monkeypatch.setattr('nivra.auth.WS_REAUTH_SECONDS', .08)
    with client.websocket_connect('ws://127.0.0.1:8765/api/v2/guard/stream', headers={'Origin': ORIGIN}) as socket:
        socket.send_json({'type': 'auth', 'token': token})
        assert socket.receive_json()['type'] == 'guard-snapshot'
        message = socket.receive()
        while message['type'] == 'websocket.send': message = socket.receive()
        assert message['code'] == 4401


def test_dev_guard_websocket_uses_signed_cookie(monkeypatch, tmp_path):
    monkeypatch.setenv('NIVRA_AUTH_MODE', 'dev')
    app = create_app(database=tmp_path/'guard-dev.sqlite', relay_only=True)
    app.state.classroom.store.add_guard('G2', 'Demo guard')
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.post('/api/v2/auth/dev', headers={'Origin': ORIGIN}, json={'role': 'guard', 'name': 'G2'}).status_code == 200
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/guard/stream', headers={'Origin': ORIGIN}) as socket:
            assert socket.receive_json()['guard']['callsign'] == 'G2'
            assert client.post('/api/v2/auth/dev/logout', headers={'Origin': ORIGIN}).status_code == 204
            message = socket.receive()
            while message['type'] == 'websocket.send': message = socket.receive()
            assert message['code'] == 4401


def test_clerk_guard_location_and_floor_are_scoped_to_authenticated_guard(clerk_app):
    app, client, mint = clerk_app
    service = app.state.classroom
    own = service.store.add_guard('G1', 'Asha')
    other = service.store.add_guard('G2', 'Other')
    gps = dict(latitude=28.6, longitude=77.2, accuracy=10, capturedAt=time.time()*1000)
    guard_headers = {'Origin': ORIGIN, 'Authorization': 'Bearer '+mint(metadata={'role': 'guard', 'callsign': 'G1'})}
    assert client.post('/api/v2/guard/location', headers={'Origin': ORIGIN}, json=gps).status_code == 403
    assert client.post('/api/v2/guard/location', headers=headers(mint, 'admin'), json=gps).status_code == 403
    assert client.post('/api/v2/guard/location', headers=guard_headers, json=gps).json()['gps'] == gps
    assert client.patch('/api/v2/guard/profile', headers=guard_headers, json={'floorName': 'Third'}).json()['floorName'] == 'Third'
    assert service.store.guard(own['id'])['gps'] == gps
    assert service.store.guard(other['id'])['gps'] is None
    assert service.store.guard(other['id'])['floor_name'] is None
