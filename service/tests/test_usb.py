import asyncio
from io import BytesIO
import json
import os
import plistlib
import socket
import struct
import threading
import tempfile
import time

import pytest
from fastapi.testclient import TestClient
from nivra import usb_transport as transport


def test_usb_discovery_ignores_wifi_and_hides_serial(monkeypatch):
    class Stream:
        def close(self): pass
    monkeypatch.setattr(transport, 'mux', lambda message: (Stream(), {'DeviceList': [
        {'DeviceID': 1, 'Properties': {'ConnectionType': 'Network', 'SerialNumber': 'wifi'}},
        {'DeviceID': 2, 'Properties': {'ConnectionType': 'USB', 'SerialNumber': 'private-device'}}]}))
    devices = transport.list_devices()
    assert len(devices) == 1 and devices[0]['muxId'] == 2
    assert len(devices[0]['id']) == 24 and 'private-device' not in str(devices)


def test_mux_framing_and_raw_connection_survives_response(tmp_path):
    folder = tempfile.TemporaryDirectory(prefix='nvusb-', dir='/tmp')
    path = folder.name+'/mux'
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    server.listen()
    received = []
    def serve():
        peer, _ = server.accept()
        with peer:
            length, version, kind, tag = struct.unpack('<IIII', transport.read_exact(peer, 16))
            received.append(plistlib.loads(transport.read_exact(peer, length-16)))
            data = plistlib.dumps({'Number': 0})
            peer.sendall(struct.pack('<IIII', len(data)+16, version, kind, tag)+data+b'live')
    thread = threading.Thread(target=serve)
    thread.start()
    stream, response = transport.mux({'MessageType': 'Connect'}, path)
    try:
        assert response == {'Number': 0}
        assert transport.read_exact(stream, 4) == b'live'
        assert received[0]['MessageType'] == 'Connect'
    finally:
        stream.close()
        thread.join(2)
        server.close()
        folder.cleanup()


@pytest.mark.parametrize('reply,exception', [
    (b'HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\n\r\n', PermissionError),
    (b'HTTP/1.1 200 OK\r\nContent-Length: 99999999\r\n\r\n', OSError),
    (b'HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nxx', OSError)])
def test_usb_http_rejects_wrong_code_oversized_and_incomplete_frames(monkeypatch, reply, exception):
    client, server = socket.socketpair()
    def serve():
        with server:
            server.recv(4096)
            server.sendall(reply)
    thread = threading.Thread(target=serve)
    thread.start()
    monkeypatch.setattr(transport, 'mux', lambda _: (client, {'Number': 0}))
    with pytest.raises(exception):
        transport.phone_get({'muxId': 1}, 'ABCD2345', '/v1/frame')
    thread.join(2)
    assert client.fileno() == -1


@pytest.fixture
def usb_server(monkeypatch, tmp_path):
    # The launcher sets an explicit standalone environment, not production config.
    before = os.environ.copy()
    import run_usb
    # A cached launcher module does not reapply its environment for later tests.
    os.environ.update(NIVRA_ALLOWED_ORIGINS=run_usb.ORIGIN, NIVRA_AUTH_MODE='dev', NIVRA_PUBLIC_ORIGIN='')
    monkeypatch.setattr(run_usb, 'start', lambda: None)
    monkeypatch.setattr(run_usb, 'close', lambda: None)
    from nivra import server
    monkeypatch.setattr(server, 'create_app', server.create_app)
    # Test the actual server with model loading isolated, never real camera frames.
    original = run_usb.create_app
    def factory(**kwargs):
        return original(model_factory=lambda: type('Models', (), {'runtime': {}})(),
            pipeline_factory=lambda _: None, **kwargs)
    monkeypatch.setattr(run_usb, 'create_app', factory)
    identity = 'a'*24
    monkeypatch.setattr(run_usb, 'list_devices', lambda: [{'id': identity, 'host': '192.168.1.20', 'port': 8940, 'name': 'iPhone'}])
    monkeypatch.setattr(run_usb, 'phone_get', lambda device, code, path: ({}, json.dumps({'name': 'Phone'}).encode()))
    original_pump = run_usb.USBPhones.pump
    async def pump(self, identity, code, link):
        await asyncio.Event().wait()
    monkeypatch.setattr(run_usb.USBPhones, 'pump', pump)
    async def start_broker(self):
        class Listener:
            def close(self): pass
            async def wait_closed(self): pass
        self.server = Listener()
    monkeypatch.setattr(run_usb.PairingBroker, 'start', start_broker)
    app = run_usb.make_app(tmp_path/'usb.sqlite')
    app.state.original_usb_pump = original_pump
    try:
        with TestClient(app, base_url=run_usb.ORIGIN) as client:
            yield client, app, identity
    finally:
        os.environ.clear()
        os.environ.update(before)


def test_usb_add_remove_has_no_ghost_camera_and_local_wall_session(usb_server):
    client, app, identity = usb_server
    origin = {'origin': 'http://127.0.0.1:8870'}
    client.cookies.set('nivra_dev', 'expired-other-local-host', path='/api/v2')
    config = client.get('/api/usb/config')
    assert config.json()['enabled'] is True
    assert any('nivra_dev=' in value and 'Max-Age=0' in value for value in config.headers.get_list('set-cookie'))
    # TestClient's unscoped injected cookie is separate from normal host cookies.
    client.cookies.delete('nivra_dev', path='/api/v2')
    assert client.get('/api/v2/me', headers=origin).json()['role'] == 'admin'
    response = client.post('/api/usb/connect', headers=origin,
        json=dict(deviceId=identity, code='ABCD2345', name='Door', floor='Floor 1'))
    assert response.status_code == 200
    camera_id = response.json()['cameraId']
    assert app.state.classroom.store.camera(camera_id)['floor'] == 'Floor 1'
    assert client.post('/api/usb/connect', headers=origin,
        json=dict(deviceId=identity, code='ABCD2345')).status_code == 409
    assert len(app.state.classroom.store.cameras()) == 1
    assert client.delete('/api/usb/devices/'+identity, headers=origin).status_code == 204
    assert app.state.classroom.store.camera(camera_id) is None
    assert client.get('/api/usb/devices').json()['devices'][0]['linked'] is False


def test_usb_wrong_code_does_not_create_camera_and_cross_origin_rejected(usb_server, monkeypatch):
    import run_usb
    client, app, identity = usb_server
    def denied(*_): raise PermissionError()
    monkeypatch.setattr(run_usb, 'phone_get', denied)
    payload = dict(deviceId=identity, code='ABCD2345')
    assert client.post('/api/usb/connect', headers={'origin': 'https://evil.example'}, json=payload).status_code == 403
    assert client.get('/api/usb/config', headers={'sec-fetch-site': 'cross-site'}).status_code == 403
    assert client.post('/api/usb/connect', json=payload).status_code == 403
    assert client.post('/api/usb/connect', headers={'origin': run_usb.ORIGIN}, json=payload).status_code == 403
    assert app.state.classroom.store.cameras() == []


def test_local_poll_restores_wall_access_after_server_session_changes(usb_server):
    client, app, _ = usb_server
    origin = {'origin': 'http://127.0.0.1:8870'}
    client.get('/api/local/config')
    app.state.classroom.admin_token = 'a-new-private-local-session'
    assert client.get('/api/v2/me', headers=origin).status_code == 403
    assert client.get('/api/local/devices').status_code == 200
    assert client.get('/api/v2/me', headers=origin).json()['role'] == 'admin'


def test_actual_usb_pump_authenticates_and_sends_valid_frame_then_revokes(usb_server, monkeypatch):
    import run_usb
    from types import SimpleNamespace
    from PIL import Image
    from nivra.classroom import CAMERA_COOKIE
    from nivra.server import unpack_frame
    client, app, identity = usb_server
    classroom = app.state.classroom
    camera = classroom.store.add_camera('USB source', 'Mac', 'Room')
    encoded = BytesIO()
    Image.new('RGB', (128, 80)).save(encoded, format='JPEG')
    delivered = []
    authenticated = []
    async def verify():
        accepted = asyncio.Event()
        class Peer:
            first = True
            async def recv(self):
                if self.first:
                    self.first = False
                    return '{"type":"ready"}'
                return '{"type":"accepted","timestampMs":100}'
            async def send(self, packet):
                header, frame = unpack_frame(packet)
                delivered.append((header.maxPeople, frame.shape))
                accepted.set()
        class Channel:
            async def __aenter__(self): return Peer()
            async def __aexit__(self, *args): pass
        def connect(url, **kwargs):
            credential = kwargs['additional_headers']['Cookie'].split('=', 1)[1]
            subject = classroom.camera_identity(SimpleNamespace(cookies={CAMERA_COOKIE: credential}))
            authenticated.append(subject)
            assert subject == camera['id']
            assert kwargs['origin'] == run_usb.ORIGIN
            return Channel()
        monkeypatch.setattr(run_usb, 'connect', connect)
        monkeypatch.setattr(run_usb, 'phone_get', lambda device, code, path:
            ({}, b'{"name":"Phone"}') if path == '/v1/status' else
            ({'X-Nivra-Sequence': '1', 'X-Nivra-Timestamp': '100'}, encoded.getvalue()))
        link = dict(cameraId=camera['id'], name='USB source', state='waiting', detail='')
        task = asyncio.create_task(app.state.original_usb_pump(app.state.usb, identity, 'ABCD2345', link))
        await asyncio.wait_for(accepted.wait(), 2)
        for _ in range(10):
            if link['state'] == 'live': break
            await asyncio.sleep(0)
        assert link['state'] == 'live'
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
    asyncio.run(verify())
    assert authenticated == [camera['id']]
    assert delivered == [(32, (80, 128, 3))]
    assert classroom.store.device_sessions() == []
    assert classroom.credentials == {}


def test_sustained_local_pump_keeps_current_frames_during_slow_analysis_and_reconnect(usb_server, monkeypatch):
    import run_usb
    from nivra.server import unpack_frame
    from PIL import Image
    client, app, identity = usb_server
    classroom = app.state.classroom
    camera = classroom.store.add_camera('Synthetic sustained', 'QA', 'QA')
    out = BytesIO();Image.new('RGB', (128, 80)).save(out, 'JPEG')
    delivered, sequences, connections = [], [0], []
    def source(device, code, path):
        if path == '/v1/status': return {}, b'{"name":"Synthetic"}'
        sequences[0] += 1
        return {'X-Nivra-Sequence':str(sequences[0]), 'X-Nivra-Timestamp':str(sequences[0]*50)}, out.getvalue()
    monkeypatch.setattr(run_usb, 'phone_get', source)
    async def verify():
        done = asyncio.Event()
        analysis_steps = []
        async def slow_analysis():
            while True:
                await asyncio.to_thread(time.sleep, .25)
                analysis_steps.append(True)
        class Peer:
            def __init__(self, number): self.number, self.timestamp, self.first = number, None, True
            async def recv(self):
                if self.first:
                    self.first = False
                    return '{"type":"ready"}'
                if self.number == 0 and self.timestamp == 150:
                    raise OSError('Synthetic temporary disconnect')
                await asyncio.sleep(.002)
                delivered.append((self.timestamp, time.monotonic()))
                if len(delivered) >= 24: done.set()
                return json.dumps(dict(type='accepted',timestampMs=self.timestamp))
            async def send(self, packet):
                header, _ = unpack_frame(packet)
                self.timestamp = header.timestampMs
        class Channel:
            def __init__(self): self.peer = Peer(len(connections));connections.append(self.peer)
            async def __aenter__(self): return self.peer
            async def __aexit__(self, *args): pass
        monkeypatch.setattr(run_usb, 'connect', lambda *_args, **_kwargs: Channel())
        link = dict(cameraId=camera['id'], name='Synthetic', state='waiting', detail='')
        task = asyncio.create_task(app.state.original_usb_pump(app.state.usb, identity, 'ABCD2345', link))
        analysis = asyncio.create_task(slow_analysis())
        try:
            await asyncio.wait_for(done.wait(), 3)
            assert len(connections) == 2
            timestamps = [timestamp for timestamp, _ in delivered]
            assert timestamps == sorted(set(timestamps))
            assert 150 not in timestamps and analysis_steps
            # Count only the stable connection, excluding the deliberately broken one.
            elapsed = delivered[-1][1]-delivered[2][1]
            assert (len(delivered)-3)/elapsed >= 16
            assert link['state'] == 'live'
        finally:
            task.cancel();analysis.cancel()
            await asyncio.gather(task, analysis, return_exceptions=True)
    asyncio.run(verify())
    assert classroom.store.device_sessions() == [] and classroom.credentials == {}


@pytest.mark.parametrize('failure', ['timeout', 'wrong_timestamp'])
def test_local_pump_recovers_from_missing_or_wrong_ack_without_queued_frames(usb_server, monkeypatch, failure):
    import run_usb
    from PIL import Image
    client, app, identity = usb_server
    classroom = app.state.classroom
    camera = classroom.store.add_camera('Synthetic ACK', 'QA', 'QA')
    out = BytesIO();Image.new('RGB', (128, 80)).save(out, 'JPEG')
    monkeypatch.setattr(run_usb, 'ACK_TIMEOUT', .02)
    monkeypatch.setattr(run_usb, 'RECONNECT_DELAYS', (.01,))
    monkeypatch.setattr(run_usb, 'phone_get', lambda device,code,path: ({},b'{}') if path=='/v1/status'
        else ({'X-Nivra-Sequence':'1','X-Nivra-Timestamp':'100'},out.getvalue()))
    channels = []
    async def verify():
        recovered = asyncio.Event()
        class Peer:
            def __init__(self,number): self.number,self.first,self.sends=number,True,0
            async def send(self,packet): self.sends += 1
            async def recv(self):
                if self.first:
                    self.first=False
                    return '{"type":"ready"}'
                if self.number==0:
                    if failure=='timeout': await asyncio.Event().wait()
                    return '{"type":"accepted","timestampMs":99}'
                recovered.set()
                return '{"type":"accepted","timestampMs":100}'
        class Channel:
            def __init__(self): self.peer=Peer(len(channels));channels.append(self.peer)
            async def __aenter__(self): return self.peer
            async def __aexit__(self,*args): pass
        monkeypatch.setattr(run_usb,'connect',lambda *_args,**_kwargs:Channel())
        link=dict(cameraId=camera['id'],name='Synthetic',state='waiting',detail='')
        task=asyncio.create_task(app.state.original_usb_pump(app.state.usb,identity,'ABCD2345',link))
        try:
            await asyncio.wait_for(recovered.wait(),1)
            assert len(channels)==2 and [peer.sends for peer in channels]==[1,1]
        finally:
            task.cancel();await asyncio.gather(task,return_exceptions=True)
    asyncio.run(verify())
    assert classroom.store.device_sessions()==[]


def test_wireless_qr_fallback_without_bonjour_and_resumes_same_camera(usb_server, monkeypatch):
    import run_usb
    client, app, identity = usb_server
    monkeypatch.setattr(run_usb, 'list_devices', lambda: [])
    checked = []
    def status(device, code, path):
        checked.append(device['host'])
        if device['host'] == '192.168.1.4': raise OSError('unreachable')
        return {}, b'{"name":"Hall camera"}'
    monkeypatch.setattr(run_usb, 'phone_get', status)
    response = client.post('/api/local/connect', headers={'origin': run_usb.ORIGIN},
        json=dict(host='192.168.1.4', hosts=['172.20.10.2'], code='ABCD2345'))
    assert response.status_code == 200
    assert checked == ['192.168.1.4', '172.20.10.2']
    assert app.state.usb.links[run_usb.from_host('192.168.1.4')['id']]['device']['host'] == '172.20.10.2'
    assert len(app.state.classroom.store.cameras()) == 1


@pytest.mark.parametrize('host', ['127.0.0.1', '169.254.169.254', '8.8.8.8', 'example.com', '192.168.1.2:80'])
def test_wireless_qr_cannot_target_public_dns_loopback_or_link_local(usb_server, host, monkeypatch):
    import run_usb
    client, app, _ = usb_server
    def forbidden(*args): raise AssertionError('must not connect')
    monkeypatch.setattr(run_usb, 'phone_get', forbidden)
    response = client.post('/api/local/connect', headers={'origin': run_usb.ORIGIN},
        json=dict(host=host, code='ABCD2345'))
    assert response.status_code == 422
    assert app.state.classroom.store.cameras() == []


def test_wireless_stable_phone_identity_prevents_duplicate_cameras_across_interfaces(usb_server, monkeypatch):
    import run_usb
    client, app, _ = usb_server
    monkeypatch.setattr(run_usb, 'phone_get', lambda *args: ({}, b'{"name":"Phone","deviceId":"NIVRA-123456abcdef"}'))
    origin = {'origin': run_usb.ORIGIN}
    first = client.post('/api/local/connect', headers=origin, json={'host':'192.168.1.4','code':'ABCD2345'})
    second = client.post('/api/local/connect', headers=origin, json={'host':'172.20.10.2','code':'ABCD2345'})
    assert first.status_code == 200 and second.status_code == 409
    assert len(app.state.classroom.store.cameras()) == 1


def test_mac_invite_creates_one_camera_using_tcp_peer_and_replay_cannot_undo_removal(usb_server, monkeypatch):
    import run_usb
    from nivra import local_pairing
    client, app, _ = usb_server
    monkeypatch.setattr(local_pairing, 'interface_addresses', lambda: ['192.168.1.4'])
    monkeypatch.setattr(run_usb, 'phone_get', lambda *_: ({},b'{"name":"Native phone","deviceId":"NIVRA-123456abcdef"}'))
    assert client.post('/api/local/invite',headers={'origin':'https://evil.example'}).status_code==403
    response=client.post('/api/local/invite',headers={'origin':run_usb.ORIGIN})
    assert response.status_code==200
    from urllib.parse import urlsplit,parse_qs
    token=parse_qs(urlsplit(response.json()['url']).fragment)['pair'][0]
    body=dict(token=token,code='ABCD2345',port=8940)
    broker=app.state.local_pairing
    async def redeem():
        one,two=await asyncio.gather(broker.redeem('192.168.1.2',body),broker.redeem('192.168.1.2',body))
        assert one==two and one['name']=='Native phone'
        assert len(app.state.classroom.store.cameras())==len(app.state.usb.links)==1
    client.portal.call(redeem)
    identity=next(iter(app.state.usb.links))
    assert app.state.usb.links[identity]['device']['host']=='192.168.1.2'
    assert client.delete('/api/local/devices/'+identity,headers={'origin':run_usb.ORIGIN}).status_code==204
    async def replay():
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as error:await broker.redeem('192.168.1.2',body)
        assert error.value.status_code==403
    client.portal.call(replay)
    assert app.state.classroom.store.cameras()==[]
