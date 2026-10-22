import time
from urllib.parse import urlsplit, parse_qs
from fastapi.testclient import TestClient
from nivra.clips import Clips, signed_frame_url, valid_frame_signature
from nivra.server import create_app
from test_classroom import operator, camera, pair, ORIGIN
from test_server import FakeModels, FakePipeline, packet
from test_device_analysis import report


def test_ring_capture_window_disconnect_and_ttl():
    clock = [1000.0]
    clips = Clips(clock=lambda: clock[0])
    for i in range(121):
        clock[0] = 1000 + i / 10
        clips.receive('c', b'jpeg')
    assert 49 <= len(clips.rings['c']) <= 61
    clips.capture('e', 'c')
    peak = clock[0] * 1000
    before = len(clips.clips['e'].frames)
    for i in range(1, 101):
        clock[0] = 1012 + i / 10
        clips.receive('c', b'jpeg')
    assert clips.summary('e')['status'] == 'ready'
    frames = clips.clips['e'].frames
    assert len(frames) > before
    assert all(peak - 10000 <= f.t <= peak + 8000 for f in frames)
    clips.disconnect('c')
    assert not clips.rings and clips.summary('e')['frames'] == len(frames)
    clock[0] = 1012 + 900
    clips.prune()
    assert clips.summary('e') == dict(status='expired', frames=0)
    assert clips.bytes == 0


def test_memory_cap_evicts_oldest_clip_then_ring():
    clock = [1000.0]
    clips = Clips(max_bytes=1000, clock=lambda: clock[0])
    clips.receive('c', b'a'*100)
    clips.capture('a', 'c')
    clips.capture('b', 'c')
    clock[0] += .2
    clips.receive('c', b'b'*100)
    assert clips.bytes <= 1000
    assert clips.summary('a')['status'] == 'expired'
    assert clips.summary('b')['status'] == 'recording'
    clips.receive('huge', b'x'*2000)
    assert clips.bytes <= 1000
    clips.close()
    assert clips.bytes == 0


def test_ttl_uses_elapsed_clock_when_wall_clock_moves_backwards():
    wall, elapsed = [1000.0], [0.0]
    clips = Clips(clock=lambda: wall[0], elapsed_clock=lambda: elapsed[0])
    clips.receive('c', b'jpeg')
    clips.capture('e', 'c')
    wall[0] = 1
    elapsed[0] = 900
    clips.prune()
    assert clips.summary('e')['status'] == 'expired'


def test_large_snapshot_prunes_once_and_expires_clips_without_erasing_history(tmp_path, monkeypatch):
    app = create_app(database=tmp_path/'snapshot.sqlite', relay_only=True)
    service = app.state.classroom
    clock = [1000.0]
    service.clips = Clips(clock=lambda: clock[0])
    cam = service.store.add_camera('Synthetic', 'QA', 'QA')
    try:
        service.clips.receive(cam['id'], b'jpeg')
        for index in range(500):
            service.store.record(cam['id'], 'QA', dict(id=str(index), occurredAtMs=index))
        for event in service.store.events(): service.clips.capture(event['id'], cam['id'])
        original = service.clips.prune
        calls = []
        def counted():
            calls.append(True)
            original()
        monkeypatch.setattr(service.clips, 'prune', counted)
        snapshot = service.snapshot()
        assert len(snapshot['events']) == 500 and len(calls) == 1
        assert all(event['clip'] == dict(status='recording', frames=1) for event in snapshot['events'])
        clock[0] += 900
        calls.clear()
        snapshot = service.snapshot()
        assert len(snapshot['events']) == 500 and len(calls) == 1
        assert all(event['clip'] == dict(status='expired', frames=0) for event in snapshot['events'])
        assert all(event['status'] == 'open' for event in snapshot['events'])
        assert service.clips.bytes == 0
    finally:
        service.store.close()


def test_signed_url_cannot_cross_events_or_change_expiry():
    path = '/api/v2/events/event/clip/frames/0'
    parsed = urlsplit(signed_frame_url(path))
    values = parse_qs(parsed.query)
    exp, sig = int(values['exp'][0]), values['sig'][0]
    assert valid_frame_signature(path, exp, sig)
    assert not valid_frame_signature(path.replace('event/', 'other/'), exp, sig)
    assert not valid_frame_signature(path, exp+1, sig)
    assert not valid_frame_signature(path, 1, sig)


def test_device_clip_auth_review_delete_and_no_store(tmp_path):
    app = create_app(database=tmp_path/'db.sqlite', relay_only=True)
    with TestClient(app, base_url=ORIGIN['origin']) as client:
        operator(client)
        cam = camera(client)
        pair(client, cam['id'])
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream', headers=ORIGIN) as socket:
            socket.receive_json()
            socket.send_json(dict(type='device-status', state='ready', delegate='GPU', detail='Ready'))
            socket.send_bytes(packet(100)); socket.receive_json()
            socket.send_json(report())
            socket.send_bytes(packet(200)); socket.receive_json()
            event = client.get('/api/v2/state').json()['events'][0]
            assert event['clip'] == dict(status='recording', frames=1)
            path = f'/api/v2/events/{event["id"]}/clip'
            clip = client.get(path).json()
            assert clip['endMs'] - clip['peakMs'] == 8000
            assert clip['peakMs'] - clip['startMs'] == 10000
            frame_url = clip['frames'][0]['url']
            response = client.get(frame_url)
            assert response.status_code == 200 and response.content[:2] == b'\xff\xd8'
            assert response.headers['cache-control'] == 'no-store'
            assert response.headers['content-type'] == 'image/jpeg'
            assert client.get(frame_url.replace('sig=', 'sig=x')).status_code == 403
            # Revision failures must leave evidence intact.
            assert client.post(path.removesuffix('/clip')+'/review', headers=ORIGIN,
                               json=dict(action='dismiss', revision=99, reason='other')).status_code == 409
            assert client.get(frame_url).status_code == 200
        assert not app.state.classroom.clips.rings
        assert client.get(frame_url).status_code == 200
        response = client.post(path.removesuffix('/clip')+'/review', headers=ORIGIN,
                               json=dict(action='dismiss', revision=0, reason='other'))
        assert response.status_code == 200
        assert client.get(path).json()['status'] == 'expired'
        assert client.get(frame_url).status_code == 404
        client.cookies.clear()
        assert client.get(path).status_code in (401, 403)


def test_server_event_capture_and_clear(tmp_path):
    class EventPipeline(FakePipeline):
        def process(self, *args, **kwargs):
            result = super().process(*args, **kwargs)
            result['conflict'] = dict(events=[dict(id='event', occurredAtMs=args[1], detail='Review')])
            return result
    app = create_app(FakeModels, EventPipeline, tmp_path/'db.sqlite')
    with TestClient(app, base_url=ORIGIN['origin']) as client:
        operator(client); cam = camera(client); pair(client, cam['id'])
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream', headers=ORIGIN) as socket:
            socket.receive_json()
            socket.send_bytes(packet(100)); socket.receive_json()
            for _ in range(100):
                events = client.get('/api/v2/state').json()['events']
                if events: break
                time.sleep(.01)
            assert events and events[0]['clip']['frames'] == 1
            path = f'/api/v2/events/{events[0]["id"]}'
            assert client.post(path+'/review', headers=ORIGIN, json=dict(action='confirm', revision=0)).status_code == 200
            assert client.post(path+'/review', headers=ORIGIN, json=dict(action='clear', revision=1)).status_code == 200
            assert client.get(path+'/clip').json()['status'] == 'expired'


def test_manifest_reviewer_allowed_guard_denied(tmp_path):
    app = create_app(database=tmp_path/'db.sqlite', relay_only=True)
    with TestClient(app, base_url=ORIGIN['origin']) as client:
        service = app.state.classroom
        cam = service.store.add_camera('C', 'B', '1')
        service.record_event(cam['id'], 'g', dict(id='1', occurredAtMs=1))
        event_id = service.store.events()[0]['id']
        path = f'/api/v2/events/{event_id}/clip'
        for role, code in [('reviewer', 200), ('guard', 403), ('admin', 200)]:
            client.cookies.clear()
            assert client.post('/api/v2/auth/dev', headers=ORIGIN,
                               json=dict(role=role, name='Clip test')).status_code == 200
            assert client.get(path).status_code == code
