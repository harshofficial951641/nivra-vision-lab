"""Admin setup test alerts use the normal event and human review lifecycle."""
import pytest

from test_sites import registry


def test_test_event_records_broadcasts_and_follows_normal_review(registry, monkeypatch):
    client, store = registry
    service = client.app.state.classroom
    floor = store.add_floor('Ground')
    camera = store.add_camera('Entrance', 'Main', 'Ground')
    store.patch_camera(camera['id'], placement=dict(floorId=floor['id'], x=.2, y=.3, angle=0, fov=90, range=.2))
    calls = []
    record = store.record
    def observed(*args):
        calls.append(args)
        return record(*args)
    monkeypatch.setattr(store, 'record', observed)
    with client.websocket_connect('ws://127.0.0.1:8765/api/v2/operator', headers={'origin':'http://127.0.0.1:8765'}) as socket:
        assert socket.receive_json()['events'] == []
        response = client.post('/api/v2/events/test', json={'cameraId': camera['id']})
        assert response.status_code == 201
        event = response.json()
        assert len(calls) == 1 and calls[0][2]['evidenceModel'] == 'test'
        assert event['model'] == 'test' and event['floor_id'] == floor['id']
        assert event['detail'] == 'Test alert — not a real incident. Confirm and alert a guard to check their phone rings.'
        assert event['status'] == 'open' and event['decision'] is None and event['guard'] is None
        snapshot = socket.receive_json()
        assert snapshot['events'][0] == {**event, 'clip': {'status': 'none', 'frames': 0}}
    reviewed = client.post('/api/v2/events/'+event['id']+'/review', json={'action':'confirm','revision':0,'guard':'G2'})
    assert reviewed.status_code == 200 and reviewed.json()['model'] == 'test'
    assert reviewed.json()['decision'] == 'confirmed' and reviewed.json()['alerted_at'] is not None


def test_duplicate_and_global_cooldown_across_cameras_and_admins(registry):
    client, store = registry
    service = client.app.state.classroom
    one, two = store.add_camera('One', 'B', 'F'), store.add_camera('Two', 'B', 'F')
    first = client.post('/api/v2/events/test', json={'cameraId': one['id']}).json()
    assert client.post('/api/v2/events/test', json={'cameraId': one['id']}).status_code == 409
    assert client.post('/api/v2/auth/dev', json={'role':'admin','name':'Another admin'}).status_code == 200
    response = client.post('/api/v2/events/test', json={'cameraId': two['id']})
    assert response.status_code == 429 and 1 <= int(response.headers['retry-after']) <= 10
    service.last_test_event_at -= 10
    # Viewing is not a decision, so the duplicate guard still applies.
    store.review(first['id'], 'view', 0)
    assert client.post('/api/v2/events/test', json={'cameraId': one['id']}).status_code == 409
    store.review(first['id'], 'dismiss', 1, reason='other')
    second = client.post('/api/v2/events/test', json={'cameraId': one['id']})
    assert second.status_code == 201
    assert second.json()['source_id'] != first['source_id'] and second.json()['id'] != first['id']
    assert len(store.events()) == 2


@pytest.mark.parametrize('role', ['reviewer', 'guard'])
def test_test_event_admin_only(registry, role):
    client, store = registry
    camera = store.add_camera('Camera', 'B', 'F')
    assert client.post('/api/v2/auth/dev', json={'role':role,'name':'Other'}).status_code == 200
    assert client.post('/api/v2/events/test', json={'cameraId':camera['id']}).status_code == 403
    client.cookies.clear()
    assert client.post('/api/v2/events/test', json={'cameraId':camera['id']}).status_code in (401, 403)
    assert store.events() == []


def test_test_event_validation_and_missing_camera_do_not_consume_cooldown(registry):
    client, store = registry
    for body in ({}, {'cameraId':''}, {'cameraId':123}, {'cameraId':'x','unexpected':True}):
        assert client.post('/api/v2/events/test', json=body).status_code == 422
    assert client.post('/api/v2/events/test', json={'cameraId':'missing'}).status_code == 404
    camera = store.add_camera('Camera', 'B', 'F')
    # A real undecided event does not prevent a test event on the same camera.
    store.record(camera['id'], 'real', dict(id='one', occurredAtMs=1))
    assert client.post('/api/v2/events/test', json={'cameraId':camera['id']}).status_code == 201
