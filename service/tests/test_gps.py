"""GPS authentication, validation, historical destinations and v4 migration."""
import sqlite3
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from nivra.classroom_store import Store
from nivra.server import create_app

ORIGIN = {'origin': 'http://127.0.0.1:8765'}
GPS = dict(latitude=28.6139, longitude=77.209, accuracy=12, capturedAt=123456789)

@pytest.fixture
def gps_site(tmp_path, monkeypatch):
    monkeypatch.setenv('NIVRA_AUTH_MODE', 'dev')
    app = create_app(database=tmp_path/'gps.sqlite', relay_only=True)
    with TestClient(app, base_url='http://127.0.0.1:8765', headers=ORIGIN) as admin:
        assert admin.post('/api/v2/auth/dev', json={'role': 'admin', 'name': 'GPS test'}).status_code == 200
        camera = admin.post('/api/v2/cameras', json=dict(name='Entrance', building='Site', floor='GPS location')).json()
        phone = TestClient(app, base_url='http://127.0.0.1:8765', headers=ORIGIN)
        phone.portal = admin.portal
        def pair():
            link = admin.post(f"/api/v2/cameras/{camera['id']}/pair").json()['url']
            token = parse_qs(urlsplit(link).fragment)['pair'][0]
            assert phone.post('/api/v2/camera/pair', json={'token': token}).status_code == 200
        pair()
        yield admin, phone, app.state.classroom, camera, pair


def test_phone_gps_persists_and_incident_keeps_original_destination(gps_site):
    admin, phone, classroom, camera, pair = gps_site
    response = phone.post('/api/v2/camera/location', json=GPS)
    assert response.status_code == 200, response.text
    assert response.json()['gps'] == GPS
    assert admin.get('/api/v2/state').json()['cameras'][0]['gps'] == GPS
    assert phone.get('/api/v2/camera/session').json()['gps'] == GPS
    store = classroom.store
    store.record(camera['id'], 'gps-test', dict(id='incident', occurredAtMs=1000))
    event = store.events()[0]
    assert event['gps'] == GPS
    changed = {**GPS, 'latitude': 29}
    assert phone.post('/api/v2/camera/location', json=changed).status_code == 200
    assert store.events()[0]['gps'] == GPS
    store.add_guard('G1', 'Guard')
    store.review(event['id'], 'confirm', 0, guard='G1')
    assert classroom.guard_snapshot('G1')['alerts'][0]['gps'] == GPS
    assert store.guard_action(event['id'], 'G1', 'ack', 1)['gps'] == GPS
    pair()
    assert phone.get('/api/v2/camera/session').json()['gps'] is None
    assert store.events()[0]['gps'] == GPS


def test_gps_requires_paired_cookie_and_same_origin(gps_site):
    admin, phone, classroom, camera, pair = gps_site
    assert admin.post('/api/v2/camera/location', json=GPS).status_code == 403
    assert phone.post('/api/v2/camera/location', json=GPS, headers={'origin': 'https://evil.example'}).status_code == 403
    classroom.store.patch_camera(camera['id'], enabled=False)
    assert phone.post('/api/v2/camera/location', json=GPS).status_code == 403


def test_repair_broadcasts_cleared_gps_before_new_phone_reports_location(gps_site, monkeypatch):
    _, phone, classroom, _, pair = gps_site
    assert phone.post('/api/v2/camera/location', json=GPS).status_code == 200
    snapshots = []

    async def broadcast(snapshot):
        snapshots.append(snapshot)

    monkeypatch.setattr(classroom, 'broadcast', broadcast)
    pair()
    # The new phone may deny permission and never send a location update.
    assert snapshots[-1]['cameras'][0]['gps'] is None


@pytest.mark.parametrize('field,value', [('latitude', 91), ('longitude', -181), ('accuracy', -1), ('capturedAt', -1)])
def test_invalid_phone_gps_rejected(gps_site, field, value):
    _, phone, classroom, camera, _ = gps_site
    assert phone.post('/api/v2/camera/location', json={**GPS, field: value}).status_code == 422
    assert classroom.store.camera(camera['id'])['gps'] is None


def test_v4_migration_preserves_camera_and_event_metadata(tmp_path):
    path = tmp_path/'v4.sqlite'
    store = Store(path)
    camera = store.add_camera('Entrance', 'Site', 'Ground')
    store.record(camera['id'], 'legacy', dict(id='event', occurredAtMs=0))
    store.close()
    # Recreate the actual previous schema, with no GPS columns.
    with sqlite3.connect(path) as db:
        db.execute('ALTER TABLE cameras DROP COLUMN gps')
        db.execute('ALTER TABLE events DROP COLUMN gps')
        db.execute('ALTER TABLE guards DROP COLUMN gps')
        db.execute('ALTER TABLE guards DROP COLUMN floor_name')
        db.execute('UPDATE schema_version SET version=4')
    store = Store(path)
    assert store.camera(camera['id'])['name'] == 'Entrance'
    assert store.camera(camera['id'])['gps'] is None
    assert store.events()[0]['gps'] is None
    store.patch_camera(camera['id'], gps=GPS)
    store.close()
    store = Store(path)
    assert store.camera(camera['id'])['gps'] == GPS
    store.close()


def test_guard_cookie_tracks_only_own_location_and_floor(gps_site, monkeypatch):
    admin, phone, classroom, _, _ = gps_site
    guard = admin.post('/api/v2/guards', json={'callsign': 'G1', 'name': 'Asha', 'floorName': ' Ground '}).json()
    other = classroom.store.add_guard('G2', 'Other', floor_name='Second')
    assert guard['floorName'] == 'Ground' and guard['gps'] is None
    link = admin.post('/api/v2/guards/G1/pair').json()['url']
    token = parse_qs(urlsplit(link).fragment)['pair'][0]
    assert phone.post('/api/v2/guard/pair', json={'token': token}).status_code == 200
    snapshots = []

    async def broadcast(snapshot):
        snapshots.append(snapshot)

    monkeypatch.setattr(classroom, 'broadcast', broadcast)
    assert admin.post('/api/v2/guard/location', json=GPS).status_code == 403
    assert phone.post('/api/v2/guard/location', json=GPS, headers={'origin': 'https://evil.example'}).status_code == 403
    assert phone.post('/api/v2/guard/location', json={**GPS, 'guardId': other['id']}).status_code == 422
    response = phone.post('/api/v2/guard/location', json=GPS)
    assert response.status_code == 200 and response.json()['gps'] == GPS
    changed = {**GPS, 'latitude': 29, 'capturedAt': GPS['capturedAt']+1000}
    assert phone.post('/api/v2/guard/location', json=changed).json()['gps'] == changed
    snapshot_guard = next(row for row in snapshots[-1]['guards'] if row['id'] == guard['id'])
    assert snapshot_guard['gps'] == changed
    assert phone.patch('/api/v2/guard/profile', json={'floorName': ' Third '}).json()['floorName'] == 'Third'
    assert phone.patch('/api/v2/guard/profile', json={'floorName': 'Third', 'name': 'Imposter'}).status_code == 422
    assert phone.patch('/api/v2/guard/profile', json={'floorName': ''}).status_code == 422
    assert phone.patch('/api/v2/guard/profile', json={'floorName': None}).json()['floorName'] is None
    assert classroom.store.guard(other['id'])['gps'] is None
    assert classroom.store.guard(other['id'])['floor_name'] == 'Second'
    assert admin.patch('/api/v2/guards/'+guard['id'], json={'floorName': 'First'}).json()['floorName'] == 'First'
    assert classroom.guard_snapshot('G1')['guard']['gps'] == changed


def test_v5_guard_location_migration_and_persistence(tmp_path):
    path = tmp_path/'v5.sqlite'
    store = Store(path)
    guard = store.add_guard('G1', 'Asha')
    store.close()
    with sqlite3.connect(path) as db:
        db.execute('ALTER TABLE guards DROP COLUMN gps')
        db.execute('ALTER TABLE guards DROP COLUMN floor_name')
        db.execute('UPDATE schema_version SET version=5')
    store = Store(path)
    assert store.guard(guard['id'])['gps'] is None
    assert store.guard(guard['id'])['floor_name'] is None
    store.update_guard(guard['id'], gps=GPS, floor_name='Third')
    store.close()
    store = Store(path)
    assert store.guard(guard['id'])['gps'] == GPS
    assert store.guard(guard['id'])['floor_name'] == 'Third'
    store.close()
