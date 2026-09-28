from urllib.parse import urlsplit, parse_qs
import time
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from nivra.server import create_app
from nivra.public_gateway import PublicGateway
from test_server import FakeModels, FakePipeline, packet

PUBLIC = 'https://nivra-vision-lab.topperly.chatgpt.site'
LOCAL = {'origin': 'http://127.0.0.1:8765'}
SECRET = 'test-relay-' + 'r'*44


def test_public_auth_pairing_stream_expiry_and_logout(monkeypatch, tmp_path):
    monkeypatch.setenv('NIVRA_PUBLIC_ORIGIN', PUBLIC)
    app = create_app(FakeModels, FakePipeline, tmp_path/'db.sqlite')
    with TestClient(app, base_url='http://127.0.0.1:8765') as local:
        assert local.post('/api/v2/session', headers=LOCAL).status_code == 204
        invite = local.post('/api/v2/operator/invite', headers=LOCAL).json()['url']
        token = parse_qs(urlsplit(invite).fragment)['operator'][0]
        remote = TestClient(PublicGateway(app, SECRET), base_url=PUBLIC)
        headers = {'origin': PUBLIC, 'x-nivra-relay': SECRET}
        assert remote.get('/api/v2/state').status_code == 403
        assert remote.get('/api/v2/state', headers=headers).status_code == 403
        assert remote.post('/api/v2/session', headers={**headers, 'origin': LOCAL['origin']}).status_code == 403
        assert remote.post('/api/v2/operator/redeem', json={'token': token}, headers=headers).status_code == 204
        assert remote.post('/api/v2/operator/redeem', json={'token': token}, headers=headers).status_code == 403
        assert remote.post('/api/v2/session', headers=headers).status_code == 204
        assert remote.post('/api/v2/operator/invite', headers=headers).status_code == 403
        cam = remote.post('/api/v2/cameras', json={'name':'Room A','building':'School','floor':'1'}, headers=headers).json()
        pairing = remote.post(f'/api/v2/cameras/{cam["id"]}/pair', headers=headers).json()
        assert pairing['remoteReady'] and pairing['url'].startswith(PUBLIC+'/camera#pair=')
        camera_token = parse_qs(urlsplit(pairing['url']).fragment)['pair'][0]
        phone = TestClient(PublicGateway(app, SECRET), base_url=PUBLIC)
        assert phone.post('/api/v2/camera/pair', json={'token':camera_token}, headers=headers).status_code == 200
        assert phone.get('/api/v2/state', headers=headers).status_code == 403
        with phone.websocket_connect(PUBLIC.replace('https:', 'wss:')+'/api/v2/camera/stream', headers=headers) as source:
            assert source.receive_json()['type'] == 'ready'
            source.send_bytes(packet(100))
            assert source.receive_json()['type'] == 'accepted'
        assert remote.post('/api/v2/operator/logout', headers=headers).status_code == 204
        assert remote.get('/api/v2/state', headers=headers).status_code == 403
        # Expiration is enforced server-side, regardless of the browser countdown.
        invite = local.post('/api/v2/operator/invite', headers=LOCAL).json()['url']
        app.state.classroom.operator_invites = {k:time.monotonic()-1 for k in app.state.classroom.operator_invites}
        assert remote.post('/api/v2/operator/redeem', json={'token':parse_qs(urlsplit(invite).fragment)['operator'][0]}, headers=headers).status_code == 403
        for path in ('/api/v1/session', '/api/v1/health', '/server/index.js', '/api/v2/operator/invite'):
            assert remote.get(path, headers=headers).status_code == 403
        with pytest.raises(WebSocketDisconnect):
            with phone.websocket_connect(PUBLIC.replace('https:', 'wss:')+'/api/v2/camera/stream', headers={'origin':PUBLIC}): pass

