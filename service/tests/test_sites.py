"""Registry, migration, signed file and image sanitization contract tests."""
from concurrent.futures import ThreadPoolExecutor
import asyncio
from io import BytesIO
import sqlite3
from threading import Barrier
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
from fastapi import HTTPException
from PIL import Image, PngImagePlugin
from starlette.requests import Request
import pytest

from nivra import signing, sites
from nivra.classroom_store import Store
from nivra.server import create_app
from test_classroom import create_v1_database

ORIGIN = {'origin': 'http://127.0.0.1:8765'}


@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.setenv('NIVRA_AUTH_MODE', 'dev')
    monkeypatch.delenv('NIVRA_MAX_CAMERAS', raising=False)
    monkeypatch.setattr(sites, 'PLAN_DIR', tmp_path / 'plans')
    app = create_app(database=tmp_path/'site.sqlite', relay_only=True)
    with TestClient(app, base_url='http://127.0.0.1:8765', headers=ORIGIN) as client:
        login = client.post('/api/v2/auth/dev', json={'role': 'admin', 'name': 'Registry test'})
        if login.status_code == 404:
            assert client.post('/api/v2/session').status_code == 204
        else:
            assert login.status_code == 200, login.text
        yield client, app.state.classroom.store


def add_floor(client):
    response = client.post('/api/v2/floors', json={'name': 'Ground floor'})
    assert response.status_code == 201, response.text
    return response.json()


def image_bytes(fmt='PNG', size=(120, 80), color='red'):
    output = BytesIO()
    image = Image.new('RGB', size, color)
    kwargs = {}
    if fmt == 'PNG':
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text('Private', 'must not survive')
        kwargs['pnginfo'] = metadata
    else:
        exif = Image.Exif()
        exif[0x010E] = 'must not survive'
        kwargs['exif'] = exif
    image.save(output, format=fmt, **kwargs)
    return output.getvalue()


def upload(client, floor, data, mime='image/png'):
    return client.put(f"/api/v2/floors/{floor['id']}/plan", files={'file': ('plan.png', data, mime)})


def test_registry_crud_placement_and_snapshot(registry):
    client, store = registry
    assert client.patch('/api/v2/site', json={'name': ' Atrium '}).json()['name'] == 'Atrium'
    assert client.get('/api/v2/site').json() == store.site()
    floor = add_floor(client)
    assert floor == dict(id=floor['id'], name='Ground floor', order=0, plan=None, sample=False, metersPerUnit=None)
    floor = client.patch('/api/v2/floors/'+floor['id'], json={'order': 2, 'name': 'First', 'metersPerUnit': .1}).json()
    assert floor['order'] == 2 and floor['metersPerUnit'] == .1
    assert client.get('/api/v2/floors').json() == [floor]
    cam = client.post('/api/v2/cameras', json=dict(name='Atrium', building='Main', floor='First')).json()
    assert cam['label'] == 'CAM-01' and cam['placement'] is None
    placement = dict(floorId=floor['id'], x=.2, y=.3, angle=90, fov=100, range=.4)
    cam = client.patch('/api/v2/cameras/'+cam['id'], json={'placement': placement, 'label': 'Entrance'}).json()
    assert cam['placement'] == placement and cam['name'] == 'Atrium'
    guard = client.post('/api/v2/guards', json=dict(callsign='G2', name='Guard', floorId=floor['id'], post=dict(x=.5, y=.6))).json()
    assert guard['shift'] == 'off' and guard['presence'] == dict(online=False, lastSeen=None)
    guard = client.patch('/api/v2/guards/'+guard['id'], json={'shift': 'on_shift'}).json()
    assert client.get('/api/v2/guards').json() == [guard]
    store.record(cam['id'], 'gen', dict(id='source', occurredAtMs=100))
    snapshot = client.get('/api/v2/state').json()
    assert snapshot['version'] == 3 and snapshot['serverTime'] > 0
    assert snapshot['me']['role'] in ('reviewer', 'admin')
    assert snapshot['site'] == store.site() and snapshot['floors'] == [floor]
    assert snapshot['cameras'][0]['placement'] == placement
    assert snapshot['events'][0]['floor_id'] == floor['id']
    assert snapshot['events'][0]['clip'] == {'status': 'none', 'frames': 0}
    assert snapshot['maxCameras'] == 12
    assert {'analytics', 'service', 'runtime', 'retention', 'experimental', 'publicOrigin', 'activeViewers', 'maxViewers'} <= snapshot.keys()
    assert client.delete('/api/v2/floors/'+floor['id']).status_code == 204
    assert store.camera(cam['id'])['floor_id'] is None and store.guard(guard['id'])['post_x'] is None
    assert store.events()[0]['floor_id'] == floor['id']  # Historical attribution survives deletion.
    assert client.delete('/api/v2/guards/'+guard['id']).status_code == 204
    assert client.get('/api/v2/guards').json() == []
    assert client.delete('/api/v2/guards/'+guard['id']).status_code == 404


@pytest.mark.parametrize('name', ['', ' ', 'a'*61, 'hello\x00', 'hello\x7f', 'a\n', '\u200b'])
def test_names_reject_empty_long_and_controls(registry, name):
    client, _ = registry
    assert client.post('/api/v2/floors', json={'name': name}).status_code == 422
    assert client.patch('/api/v2/site', json={'name': name}).status_code == 422


@pytest.mark.parametrize('field,value', [('x', -.01), ('y', 1.01), ('angle', 361), ('angle', -1),
                                      ('fov', 9), ('fov', 171), ('range', .01), ('range', 1.01)])
def test_camera_placement_validation(registry, field, value):
    client, store = registry
    floor = add_floor(client)
    cam = store.add_camera('Camera', 'Main', '1')
    placement = dict(floorId=floor['id'], x=0, y=1, angle=360, fov=170, range=.02)
    placement[field] = value
    assert client.patch('/api/v2/cameras/'+cam['id'], json={'placement': placement}).status_code == 422
    assert store.camera(cam['id'])['floor_id'] is None


def test_validation_missing_foreign_records_and_null_patch(registry):
    client, store = registry
    floor = add_floor(client)
    assert client.patch('/api/v2/floors/'+floor['id'], json={'name': None}).status_code == 422
    assert client.patch('/api/v2/floors/'+floor['id'], json={'metersPerUnit': -1}).status_code == 422
    assert client.patch('/api/v2/floors/'+floor['id'], json={'metersPerUnit': 10.01}).status_code == 422
    assert client.patch('/api/v2/floors/'+floor['id'], json={'metersPerUnit': 10}).status_code == 200
    assert client.patch('/api/v2/floors/missing', json={'name': 'Hi'}).status_code == 404
    assert client.post('/api/v2/guards', json={'callsign': 'G2', 'name': 'A', 'floorId': 'missing'}).status_code == 404
    for fields in ({'callsign': 'G123'}, {'callsign': 'G2\n'}, {'callsign': 'g2'}, {'email': 'x@'},
                   {'email': 'a..b@example.com'}, {'email': '.a@example.com'}, {'post': {'x': 2, 'y': 0}},
                   {'post': {'x': .5, 'y': .5}}):
        response = client.post('/api/v2/guards', json={**dict(callsign='G2', name='A'), **fields})
        assert response.status_code == 422, response.text
    cam = store.add_camera('Camera', 'Main', '1')
    assert client.patch('/api/v2/cameras/'+cam['id'], json={'placement': dict(floorId='missing', x=0, y=0, angle=0, fov=10, range=.02)}).status_code == 404
    assert client.patch('/api/v2/cameras/'+cam['id'], json={'name': None}).status_code == 422


def test_guard_email_unique_identity_helpers_and_invite(registry, monkeypatch):
    client, store = registry
    invitations = []
    async def invite(classroom, guard, **kwargs): invitations.append(guard['email'])
    monkeypatch.setattr(sites, 'invite_guard', invite)
    response = client.post('/api/v2/guards', json=dict(callsign='G2', name='Guard', email=' GUARD@Example.com '))
    assert response.status_code == 201
    guard = response.json()
    assert invitations == ['guard@example.com'] and guard['email'] == 'guard@example.com'
    assert client.post('/api/v2/guards', json=dict(callsign='G3', name='Other', email='guard@example.com')).status_code == 409
    assert client.post('/api/v2/guards', json=dict(callsign='G2', name='Other')).status_code == 409
    store.link_guard_user(guard['id'], 'user_guard')
    assert store.guard_by_user('user_guard')['id'] == guard['id']
    assert store.guard_by_email('GUARD@example.com')['id'] == guard['id']
    assert store.set_shift(guard['id'], 'break')['shift'] == 'break'
    other = store.add_guard('G3', 'Other')
    with pytest.raises(ValueError): store.link_guard_user(other['id'], 'user_guard')
    with pytest.raises(ValueError): store.link_guard_user(guard['id'], 'another_user')
    assert store.guard(other['id'])['user_id'] is None


def test_actual_dev_invitation_and_durable_failure_recovery(registry, monkeypatch):
    client, store = registry
    response = client.post('/api/v2/guards', json=dict(callsign='G2', name='Guard', email='guard@example.com'))
    assert response.status_code == 201
    members = client.get('/api/v2/members').json()
    assert any(member['email'] == 'guard@example.com' and member['role'] == 'guard' and member['guardCallsign'] == 'G2' for member in members)
    async def failed(classroom, guard, **kwargs): raise RuntimeError('Upstream unavailable')
    monkeypatch.setattr(sites, 'invite_guard', failed)
    response = client.post('/api/v2/guards', json=dict(callsign='G3', name='Other', email='other@example.com'))
    assert response.status_code == 502
    assert store.guard(response.json()['detail']['guardId'])['email'] == 'other@example.com'


def test_floor_replace_database_failure_keeps_old_file(registry, monkeypatch):
    client, store = registry
    floor = upload(client, add_floor(client), image_bytes()).json()
    old = store.floor(floor['id'])
    def failed(*args, **kwargs): raise RuntimeError('Simulated write failure')
    monkeypatch.setattr(store, 'update_floor', failed)
    with pytest.raises(RuntimeError, match='Simulated write failure'):
        upload(client, floor, image_bytes(color='blue'))
    assert store.floor(floor['id']) == old
    assert [p.name for p in sites.PLAN_DIR.iterdir()] == [sites.Path(old['plan_path']).name]


@pytest.mark.parametrize('fmt', ['PNG', 'JPEG', 'WEBP'])
def test_plan_decode_metadata_strip_and_signed_download(registry, fmt):
    client, store = registry
    floor = add_floor(client)
    response = upload(client, floor, image_bytes(fmt))
    assert response.status_code == 200, response.text
    floor = response.json()
    assert floor['plan']['width'] == 120 and floor['plan']['height'] == 80 and not floor['sample']
    client.cookies.clear()  # Signed file access is independent of session cookies.
    response = client.get(floor['plan']['url'])
    assert response.status_code == 200 and response.headers['content-type'] == 'image/webp'
    assert response.headers['cache-control'] == 'private, max-age=300'
    with Image.open(BytesIO(response.content)) as image:
        image.load()
        assert image.format == 'WEBP'
        assert not {'exif', 'icc_profile', 'xmp', 'Private'} & image.info.keys()
        assert not image.getexif()
    assert store.floor(floor['id'])['plan_hash'] in floor['plan']['url']
    assert client.get(floor['plan']['url'].replace('v=', 'v=bad')).status_code == 403
    assert client.get(floor['plan']['url']+'bad').status_code == 403
    assert client.get('/api/v2/files/plan/'+floor['id']).status_code == 403


def test_plan_downscale_replace_sample_and_delete_cleanup(registry):
    client, store = registry
    floor = add_floor(client)
    floor = upload(client, floor, image_bytes(size=(5000, 1000))).json()
    assert floor['plan']['width'] == 4096 and floor['plan']['height'] == 819
    old_url = floor['plan']['url']
    old = store.floor(floor['id'])['plan_path']
    floor = upload(client, floor, image_bytes(color='blue')).json()
    assert not sites.Path(old).exists() and client.get(old_url).status_code == 404
    old = store.floor(floor['id'])['plan_path']
    sample = client.post('/api/v2/floors/'+floor['id']+'/sample').json()
    assert sample['sample'] and sample['plan'] == dict(url='/demo/mall/plan.svg', width=1000, height=620)
    assert sample['metersPerUnit'] == .1
    assert not sites.Path(old).exists()
    floor = upload(client, floor, image_bytes()).json()
    old = store.floor(floor['id'])['plan_path']
    assert client.delete('/api/v2/floors/'+floor['id']).status_code == 204
    assert not sites.Path(old).exists()


def test_plan_bad_formats_oversize_and_decode_rejected(registry):
    client, store = registry
    floor = add_floor(client)
    for data in (b'<svg xmlns="http://www.w3.org/2000/svg"/>', b'not an image', image_bytes()[:40], image_bytes('GIF')):
        assert upload(client, floor, data).status_code == 415
    assert upload(client, floor, b'x'*(sites.MAX_PLAN_BYTES+1)).status_code == 413
    assert store.floor(floor['id'])['plan_path'] is None
    assert not sites.PLAN_DIR.exists()


def test_signing_expiry_tamper_and_shared_clip_ttl(monkeypatch):
    monkeypatch.setattr(signing, '_SECRET', b'test-only')
    url = signing.sign_url('/api/v2/files/plan/floor?v=hash', now=100)
    query = parse_qs(urlsplit(url).query)
    exp, sig = query['exp'][0], query['sig'][0]
    assert exp == '700'
    assert signing.verify_url('/api/v2/files/plan/floor?v=hash', exp, sig, now=699)
    assert not signing.verify_url('/api/v2/files/plan/floor?v=hash', exp, sig, now=700)
    assert not signing.verify_url('/api/v2/files/plan/other?v=hash', exp, sig, now=101)
    assert not signing.verify_url('/api/v2/files/plan/floor?v=hash', '701', sig, now=101)
    assert not signing.verify_url('/api/v2/files/plan/floor?v=hash', 'bad', sig, now=101)
    assert parse_qs(urlsplit(signing.sign_url('/clip/frame', ttl=300, now=100)).query)['exp'] == ['400']


def test_plan_stream_stops_at_limit_and_malformed_body(registry):
    client, _ = registry
    floor = add_floor(client)
    assert client.put('/api/v2/floors/'+floor['id']+'/plan', content=b'bad',
                      headers={'content-type': 'multipart/form-data; boundary=test'}).status_code == 422
    chunks = 0
    async def receive():
        nonlocal chunks
        chunks += 1
        data = (b'--test\r\nContent-Disposition: form-data; name="file"; filename="x.png"\r\nContent-Type: image/png\r\n\r\n'
                if chunks == 1 else b'x' * (64 * 1024))
        return {'type': 'http.request', 'body': data, 'more_body': True}
    request = Request({'type': 'http', 'headers': [(b'content-type', b'multipart/form-data; boundary=test')]}, receive)
    with pytest.raises(HTTPException) as error: asyncio.run(sites.read_plan(request))
    assert error.value.status_code == 413 and chunks <= 131


def test_plan_url_expiry_at_http_boundary(registry, monkeypatch):
    client, _ = registry
    floor = upload(client, add_floor(client), image_bytes()).json()
    exp = int(parse_qs(urlsplit(floor['plan']['url']).query)['exp'][0])
    monkeypatch.setattr(signing.time, 'time', lambda: exp)
    assert client.get(floor['plan']['url']).status_code == 403


def test_registry_roles_and_no_auth_file_upload(registry):
    client, _ = registry
    floor = add_floor(client)
    client.cookies.clear()
    assert client.get('/api/v2/site').status_code in (401, 403)
    assert upload(client, floor, image_bytes()).status_code in (401, 403)
    login = client.post('/api/v2/auth/dev', json={'role': 'reviewer', 'name': 'Reviewer'})
    if login.status_code == 404: pytest.skip('H1 role module not yet integrated')
    assert login.status_code == 200
    for path in ('site', 'floors', 'guards'):
        assert client.get('/api/v2/'+path).status_code == 200
    assert client.post('/api/v2/floors', json={'name': 'Denied'}).status_code == 403
    assert upload(client, floor, image_bytes()).status_code == 403


def legacy_database(path, version):
    create_v1_database(path)
    with sqlite3.connect(path) as db:
        if version >= 2:
            for column in ('reviewed_at REAL', 'decision TEXT', 'reason TEXT', 'note TEXT', 'guard TEXT',
                           'decided_at REAL', 'alerted_at REAL', 'on_scene_at REAL'):
                db.execute(f'ALTER TABLE events ADD COLUMN {column}')
            db.execute('ALTER TABLE event_audit ADD COLUMN action TEXT')
            db.execute("UPDATE events SET decision='confirmed',guard='G2',note='Preserve'")
        if version >= 3:
            db.execute('ALTER TABLE events ADD COLUMN guard_ack_at REAL')
            db.execute('ALTER TABLE events ADD COLUMN guard_declined_at REAL')
            db.execute('UPDATE events SET guard_ack_at=300')
        db.execute('UPDATE schema_version SET version=?', (version,))


@pytest.mark.parametrize('version', [1, 2, 3])
def test_v4_migration_preserves_all_rows_and_reopens(tmp_path, version):
    path = tmp_path/'legacy.sqlite'
    legacy_database(path, version)
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        old = {table: [dict(row) for row in db.execute(f'SELECT * FROM {table}')] for table in ('events', 'cameras', 'event_audit')}
    store = Store(path)
    assert store.db.execute('SELECT version FROM schema_version').fetchone()[0] == 4
    for table, rows in old.items():
        new = [dict(row) for row in store.db.execute(f'SELECT * FROM {table}')]
        assert len(new) == len(rows)
        assert [{key: row[key] for key in rows[0]} for row in new] == rows
    assert store.camera('camera')['label'] == 'CAM-01'
    site = store.site()
    store.close()
    store = Store(path)
    assert store.site() == site and store.camera('camera')['label'] == 'CAM-01'
    store.close()


@pytest.mark.parametrize('version', [1, 2, 3])
def test_v4_failure_rolls_back_every_migration_step(tmp_path, version):
    path = tmp_path/'broken.sqlite'
    legacy_database(path, version)
    with sqlite3.connect(path) as db:
        db.execute('ALTER TABLE event_audit ADD COLUMN actor TEXT')  # Fail at the last v4 DDL statement.
        old_schema = db.execute('SELECT name,sql FROM sqlite_master ORDER BY name').fetchall()
    with pytest.raises(sqlite3.OperationalError): Store(path)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT version FROM schema_version').fetchone()[0] == version
        assert db.execute('SELECT name,sql FROM sqlite_master ORDER BY name').fetchall() == old_schema
        assert db.execute('SELECT id FROM events').fetchone()[0] == 'event'


def test_camera_cap_labels_concurrent_connections_and_override(tmp_path, monkeypatch):
    monkeypatch.setenv('NIVRA_MAX_CAMERAS', '12')
    path = tmp_path/'cap.sqlite'
    store = Store(path)
    for index in range(11): assert store.add_camera('C', 'B', 'F')['label'] == f'CAM-{index+1:02d}'
    barrier = Barrier(2)
    def create():
        connection = Store(path)
        barrier.wait()
        try: return connection.add_camera('C', 'B', 'F')['label']
        except ValueError: return 'full'
        finally: connection.close()
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: create(), range(2)))
    assert sorted(results) == ['CAM-12', 'full'] and len(store.cameras()) == 12
    monkeypatch.setenv('NIVRA_MAX_CAMERAS', '13')
    assert store.add_camera('C', 'B', 'F')['label'] == 'CAM-13'
    store.close()


def test_record_floor_review_actor_guard_actor_and_realert_reset(tmp_path):
    store = Store(tmp_path/'audit.sqlite')
    floor = store.add_floor('First')
    camera = store.add_camera('Entrance', 'Main', 'First')
    store.patch_camera(camera['id'], placement=dict(floorId=floor['id'], x=.2, y=.3, angle=30, fov=90, range=.3))
    store.record(camera['id'], 'generation', dict(id='event', occurredAtMs=10))
    event = store.events()[0]
    assert event['floor_id'] == floor['id']
    event = store.review(event['id'], 'view', 0, actor='reviewer-a')
    assert event['reviewer_id'] == 'reviewer-a'
    event = store.review(event['id'], 'confirm', 1, actor='reviewer-b', guard='G2')
    assert event['reviewer_id'] == 'reviewer-b'
    store.guard_action(event['id'], 'G2', 'ack', 2, actor='guard-user')
    with store.db: store.db.execute('UPDATE events SET escalated_at=123')
    event = store.review(event['id'], 'alert', 3, actor='reviewer-a', guard='G3')
    assert event['escalated_at'] is None and event['reviewer_id'] == 'reviewer-a'
    assert [row[0] for row in store.db.execute('SELECT actor FROM event_audit ORDER BY revision')] == ['reviewer-a', 'reviewer-b', 'guard-user', 'reviewer-a']
    store.close()
