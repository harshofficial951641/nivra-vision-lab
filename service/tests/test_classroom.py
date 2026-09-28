import asyncio
import time
from urllib.parse import urlsplit, parse_qs
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from nivra.server import create_app
from nivra.classroom_store import Store
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
    assert restored.analytics() == dict(total=2,pending=1,resolved=1)
    assert restored.events()[0]['status']=='resolved'
    assert not any('frame' in key or 'image' in key for key in restored.events()[0])
    restored.close()


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
        for n in range(3): camera(client,f'Room {n}')
        assert client.post('/api/v2/cameras',json=dict(name='5',building='Main',floor='1'),headers=ORIGIN).status_code == 409
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

