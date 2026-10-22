"""Paired-phone capabilities survive restarts without widening role or workspace scope."""
import sqlite3
import time
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
import pytest
from starlette.websockets import WebSocketDisconnect
from nivra.classroom import CAMERA_COOKIE, GUARD_COOKIE, digest
from nivra.classroom_store import Store
from nivra.server import create_app
from test_classroom import ORIGIN, operator, camera, pair
from test_server import packet


def guard_pair(client, callsign='G1'):
    link=client.post(f'/api/v2/guards/{callsign}/pair',headers=ORIGIN).json()['url']
    token=parse_qs(urlsplit(link).fragment)['pair'][0]
    return client.post('/api/v2/guard/pair',json={'token':token},headers=ORIGIN)


def phone(client, camera_token=None, guard_token=None):
    result=TestClient(client.app,base_url=ORIGIN['origin'])
    result.portal=client.portal
    if camera_token: result.cookies.set(CAMERA_COOKIE,camera_token,path='/api/v2/camera')
    if guard_token: result.cookies.set(GUARD_COOKIE,guard_token,path='/api/v2/guard')
    return result


def test_phone_sessions_survive_real_classroom_restart_without_owner_login(tmp_path):
    path=tmp_path/'durable.sqlite'
    with TestClient(create_app(database=path,relay_only=True),base_url=ORIGIN['origin']) as client:
        operator(client);cam=camera(client)
        guard=client.post('/api/v2/guards',json={'callsign':'G1','name':'Guard'},headers=ORIGIN).json()
        pair(client,cam['id']);camera_token=client.cookies.get(CAMERA_COOKIE)
        response=guard_pair(client);assert response.status_code==200
        guard_token=client.cookies.get(GUARD_COOKIE)
        assert next(cookie for cookie in client.cookies.jar if cookie.name==CAMERA_COOKIE).expires > time.time()+29*86400
        assert next(cookie for cookie in client.cookies.jar if cookie.name==GUARD_COOKIE).expires < time.time()+12*3600+5
        rows=[dict(row) for row in client.app.state.classroom.store.db.execute('SELECT * FROM device_sessions')]
        assert {row['subject_id'] for row in rows}=={cam['id'],guard['id']}
        assert {row['token_hash'] for row in rows}=={digest(camera_token),digest(guard_token)}
        assert camera_token not in str(rows) and guard_token not in str(rows)
    with TestClient(create_app(database=path,relay_only=True),base_url=ORIGIN['origin']) as client:
        restored = client.app.state.classroom.snapshot()['cameras']
        assert next(value for value in restored if value['id']==cam['id'])['paired'] is True
        device=phone(client,camera_token,guard_token)
        assert device.get('/api/v2/camera/session').json()['id']==cam['id']
        assert device.get('/api/v2/guard/session').json()=={'guard':'G1'}
        assert device.get('/api/v2/state').status_code==403
        with device.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream',headers=ORIGIN) as socket:
            assert socket.receive_json()['cameraId']==cam['id']
            socket.send_bytes(packet(100));assert socket.receive_json()['type']=='accepted'
        with device.websocket_connect('ws://127.0.0.1:8765/api/v2/guard/stream',headers=ORIGIN) as socket:
            assert socket.receive_json()['guard']['id']==guard['id']
        device.close()


def test_snapshot_pairing_is_durable_valid_capability_not_gps_or_frames(tmp_path):
    with TestClient(create_app(database=tmp_path/'paired.sqlite',relay_only=True),base_url=ORIGIN['origin']) as client:
        operator(client);cam=camera(client)
        service=client.app.state.classroom
        def current():
            return next(value for value in service.snapshot()['cameras'] if value['id']==cam['id'])
        assert current()['paired'] is False
        pair(client,cam['id'])
        assert current()['paired'] is True and current()['framesReceived']==0
        key=digest(client.cookies.get(CAMERA_COOKIE))
        assert key not in str(service.snapshot())
        with service.store.db:
            service.store.db.execute('UPDATE device_sessions SET expires=?',(time.time()-1,))
        assert current()['paired'] is False
        pair(client,cam['id'])
        assert current()['paired'] is True
        assert client.post('/api/v2/camera/logout',headers=ORIGIN).status_code==204
        assert current()['paired'] is False
        pair(client,cam['id'])
        assert client.patch('/api/v2/cameras/'+cam['id'],json={'enabled':False},headers=ORIGIN).status_code==200
        assert current()['paired'] is False
        assert client.patch('/api/v2/cameras/'+cam['id'],json={'enabled':True},headers=ORIGIN).status_code==200
        assert current()['paired'] is False


def test_snapshot_reads_all_pairing_states_in_one_query(tmp_path):
    with TestClient(create_app(database=tmp_path/'queries.sqlite',relay_only=True),base_url=ORIGIN['origin']) as client:
        operator(client)
        first=camera(client);second=camera(client)
        pair(client,first['id'])
        service=client.app.state.classroom
        queries=[]
        service.store.db.set_trace_callback(queries.append)
        try: snapshot=service.snapshot()
        finally: service.store.db.set_trace_callback(None)
        assert sum('FROM device_sessions' in query for query in queries)==1
        states={value['id']:value['paired'] for value in snapshot['cameras']}
        assert states[first['id']] is True and states[second['id']] is False


def test_replacement_disable_and_logout_revoke_persisted_camera_capability(tmp_path):
    with TestClient(create_app(database=tmp_path/'db.sqlite',relay_only=True),base_url=ORIGIN['origin']) as client:
        operator(client);cam=camera(client);pair(client,cam['id'])
        original=phone(client,client.cookies.get(CAMERA_COOKIE))
        with original.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream',headers=ORIGIN) as socket:
            socket.receive_json()
            assert client.patch('/api/v2/cameras/'+cam['id'],json={'enabled':False},headers=ORIGIN).status_code==200
        assert original.get('/api/v2/camera/session').status_code==403
        assert client.patch('/api/v2/cameras/'+cam['id'],json={'enabled':True},headers=ORIGIN).status_code==200
        assert original.get('/api/v2/camera/session').status_code==403
        pair(client,cam['id']);replacement=phone(client,client.cookies.get(CAMERA_COOKIE))
        pair(client,cam['id'])
        assert replacement.get('/api/v2/camera/session').status_code==403
        current=phone(client,client.cookies.get(CAMERA_COOKIE))
        assert current.post('/api/v2/camera/logout',headers=ORIGIN).status_code==204
        assert client.get('/api/v2/camera/session').status_code==403
        assert not client.app.state.classroom.store.device_sessions()
        original.close();replacement.close();current.close()


def test_guard_replacement_and_reused_callsign_never_restore_old_capability(tmp_path):
    with TestClient(create_app(database=tmp_path/'db.sqlite',relay_only=True),base_url=ORIGIN['origin']) as client:
        operator(client)
        guard=client.post('/api/v2/guards',json={'callsign':'G1','name':'First'},headers=ORIGIN).json()
        assert guard_pair(client).status_code==200
        original=phone(client,guard_token=client.cookies.get(GUARD_COOKIE))
        assert guard_pair(client).status_code==200
        assert original.get('/api/v2/guard/session').status_code==403
        replacement=phone(client,guard_token=client.cookies.get(GUARD_COOKIE))
        assert client.delete('/api/v2/guards/'+guard['id'],headers=ORIGIN).status_code==204
        other=client.post('/api/v2/guards',json={'callsign':'G1','name':'Replacement'},headers=ORIGIN).json()
        assert other['id']!=guard['id']
        assert replacement.get('/api/v2/guard/session').status_code==403
        assert not client.app.state.classroom.store.device_sessions()
        original.close();replacement.close()


def test_expired_rows_and_unpersisted_memory_credentials_cannot_authorize(tmp_path):
    with TestClient(create_app(database=tmp_path/'db.sqlite',relay_only=True),base_url=ORIGIN['origin']) as client:
        operator(client);cam=camera(client);pair(client,cam['id'])
        client.post('/api/v2/guards',json={'callsign':'G1','name':'Guard'},headers=ORIGIN)
        assert guard_pair(client).status_code==200
        service=client.app.state.classroom
        with service.store.db: service.store.db.execute('UPDATE device_sessions SET expires=?',(time.time()-1,))
        assert client.get('/api/v2/camera/session').status_code==403
        assert client.get('/api/v2/guard/session').status_code==403
        forged='f'*43
        service.credentials[digest(forged)]=cam['id']
        service.guard_credentials[digest(forged)]=('G1',time.monotonic()+60)
        device=phone(client,forged,forged)
        assert device.get('/api/v2/camera/session').status_code==403
        assert device.get('/api/v2/guard/session').status_code==403
        device.close()


def test_schema_six_migrates_to_hash_only_session_storage(tmp_path):
    path=tmp_path/'old.sqlite'
    store=Store(path);cam=store.add_camera('Before','Main','1');store.close()
    with sqlite3.connect(path) as db:
        db.execute('DROP TABLE device_sessions')
        db.execute('UPDATE schema_version SET version=6')
    store=Store(path)
    assert store.camera(cam['id'])['name']=='Before'
    assert store.db.execute('SELECT version FROM schema_version').fetchone()[0]==7
    assert store.device_sessions()==[]
    store.close()


def test_active_camera_cannot_continue_after_durable_session_expires(tmp_path):
    with TestClient(create_app(database=tmp_path/'db.sqlite',relay_only=True),base_url=ORIGIN['origin']) as client:
        operator(client);cam=camera(client);pair(client,cam['id'])
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream',headers=ORIGIN) as socket:
            socket.receive_json()
            socket.send_bytes(packet(100));socket.receive_json()
            store=client.app.state.classroom.store
            with store.db: store.db.execute('UPDATE device_sessions SET expires=?',(time.time()-1,))
            socket.send_bytes(packet(200))
            with pytest.raises(WebSocketDisconnect): socket.receive_json()
