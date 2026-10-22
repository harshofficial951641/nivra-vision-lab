"""Self-service workspace API/stream isolation, persistence and owner revocation."""
from urllib.parse import parse_qs, urlsplit
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from nivra.classroom import ADMIN_COOKIE
from nivra.public_gateway import PublicGateway
from nivra.server import create_app
from nivra.workspaces import Workspaces
from test_server import packet

PUBLIC='https://nivra.tanishq.work'
SOCKET='https://workspace-test.trycloudflare.com'
SECRET='workspace-'+ 's'*48
LOCAL={'origin':'http://127.0.0.1:8765'}
HEADERS={'origin':PUBLIC,'x-nivra-relay':SECRET}

@pytest.fixture
def env(tmp_path,monkeypatch):
    monkeypatch.setenv('NIVRA_AUTH_MODE','dev')
    monkeypatch.setenv('NIVRA_PUBLIC_ORIGIN',PUBLIC)
    monkeypatch.setenv('NIVRA_SOCKET_ORIGIN',SOCKET)
    primary=create_app(database=tmp_path/'primary.sqlite',relay_only=True)
    manager=Workspaces(primary,tmp_path/'guests')
    gateway=PublicGateway(manager,SECRET,manager)
    clients=[]
    with TestClient(primary,base_url=LOCAL['origin'],headers=LOCAL) as local:
        def client():
            c=TestClient(gateway,base_url=PUBLIC,headers=HEADERS);c.portal=local.portal
            clients.append(c)
            return c
        yield manager,local,client
        local.portal.call(manager.close)
        for c in clients:c.close()

def create(client,name):
    r=client.post('/api/v2/workspaces',json={'name':name})
    assert r.status_code==201,r.text
    return r.json()['workspace']

def pair(owner,phone,path):
    r=owner.post(path)
    assert r.status_code==200,r.text
    token=parse_qs(urlsplit(r.json()['url']).fragment)['pair'][0]
    role='camera' if '/cameras/' in path else 'guard'
    r=phone.post('/api/v2/'+role+'/pair',json={'token':token})
    assert r.status_code==200,r.text

def camera(owner,name):
    r=owner.post('/api/v2/cameras',json={'name':name,'building':name,'floor':'2'})
    assert r.status_code==201,r.text
    return r.json()

def ticket(owner,role):
    r=owner.post('/api/v2/'+role+'/socket-ticket',json={})
    assert r.status_code==200,r.text
    return r.json()

def test_creation_private_api_isolation_and_primary_backward_compatibility(env):
    manager,local,client=env
    primary=manager.primary.state.classroom.store.add_camera('Private primary','Primary','1')
    a,b,anon=client(),client(),client()
    assert anon.get('/api/v2/state').status_code==403
    assert anon.get('/api/v2/me').status_code==403
    assert anon.post('/api/v2/workspaces',json={'name':'Bad'},headers={'origin':'https://evil.test'}).status_code==403
    assert anon.post('/api/v2/workspaces',json={'name':''}).status_code==422
    wa,wb=create(a,'Site A'),create(b,'Site B')
    assert wa['id']!=wb['id'] and wa['ownerVerification']=='unverified'
    assert a.get('/api/v2/me').json()['workspace']==wa
    assert a.get('/api/v2/me').json()['role']=='admin'
    assert a.post('/api/v2/workspaces',json={'name':'Resume'}).json()['workspace']==wa
    assert len(manager.apps)==2
    ca,cb=camera(a,'A'),camera(b,'B')
    assert [c['id'] for c in a.get('/api/v2/state').json()['cameras']]==[ca['id']]
    assert [c['id'] for c in b.get('/api/v2/state').json()['cameras']]==[cb['id']]
    assert b.patch('/api/v2/cameras/'+ca['id'],json={'name':'Intrusion'}).status_code==404
    assert primary['id'] not in str(a.get('/api/v2/state').json())
    assert manager.apps[wa['id']].state.classroom.clips.max_bytes==8*1024*1024
    assert local.post('/api/v2/session').status_code==204
    link=local.post('/api/v2/operator/invite').json()['url']
    token=parse_qs(urlsplit(link).fragment)['operator'][0]
    assert anon.post('/api/v2/operator/redeem',json={'token':token}).status_code==204
    assert anon.get('/api/v2/state').json()['cameras'][0]['id']==primary['id']
    assert anon.delete('/api/v2/workspaces/current').status_code==403

def test_camera_guard_pairing_and_frame_websockets_stay_in_private_workspace(env):
    manager,local,client=env
    a,b,phone,guard=client(),client(),client(),client()
    wa,wb=create(a,'A'),create(b,'B')
    ca=camera(a,'Camera A')
    ga=a.post('/api/v2/guards',json={'callsign':'G1','name':'Guard A','floorName':'First'}).json()
    b.post('/api/v2/guards',json={'callsign':'G1','name':'Guard B'})
    pair(a,phone,'/api/v2/cameras/'+ca['id']+'/pair')
    pair(a,guard,'/api/v2/guards/G1/pair')
    assert phone.get('/api/v2/state').status_code==403
    assert guard.get('/api/v2/state').status_code==403
    assert phone.delete('/api/v2/workspaces/current').status_code==403
    assert guard.get('/api/v2/guard/session').json()=={'guard':'G1'}
    gps=dict(latitude=28.6,longitude=77.2,accuracy=10,capturedAt=1000)
    assert guard.post('/api/v2/guard/location',json=gps).json()['id']==ga['id']
    assert b.get('/api/v2/state').json()['guards'][0]['gps'] is None
    owner_t,cam_t,guard_t=ticket(a,'operator'),ticket(phone,'camera'),ticket(guard,'guard')
    direct=TestClient(PublicGateway(manager,SECRET,manager),base_url=SOCKET)
    direct.portal=local.portal
    try:
        with direct.websocket_connect(owner_t['url'],headers={'origin':PUBLIC},subprotocols=['nivra-ticket.'+owner_t['ticket']]) as wall:
            assert wall.accepted_subprotocol=='nivra-ticket.'+owner_t['ticket']
            wall.send_json({'type':'auth','token':None})
            assert wall.receive_json()['cameras'][0]['id']==ca['id']
            with direct.websocket_connect(cam_t['url'],headers={'origin':PUBLIC},subprotocols=['nivra-ticket.'+cam_t['ticket']]) as source:
                assert source.receive_json()['cameraId']==ca['id']
                source.send_bytes(packet(100))
                assert source.receive_json()['type']=='accepted'
                assert wall.receive_bytes()
            with direct.websocket_connect(guard_t['url'],headers={'origin':PUBLIC},subprotocols=['nivra-ticket.'+guard_t['ticket']]) as gs:
                gs.send_json({'type':'auth','token':None})
                assert gs.receive_json()['guard']['name']=='Guard A'
        with pytest.raises(WebSocketDisconnect):
            with direct.websocket_connect(owner_t['url'],headers={'origin':PUBLIC},subprotocols=['nivra-ticket.'+owner_t['ticket']]):pass
    finally:direct.close()

def test_same_browser_owner_guard_camera_cookie_precedence(env):
    _,_,client=env
    a,b,c,mixed=client(),client(),client(),client()
    wa,wb,wc=create(a,'Owner A'),create(b,'Guard B'),create(c,'Camera C')
    b.post('/api/v2/guards',json={'callsign':'G1','name':'Guard B'})
    cc=camera(c,'Camera C')
    mixed.cookies.update(a.cookies)
    pair(b,mixed,'/api/v2/guards/G1/pair')
    pair(c,mixed,'/api/v2/cameras/'+cc['id']+'/pair')
    assert mixed.get('/api/v2/me').json()['workspace']['id']==wa['id']
    assert mixed.get('/api/v2/guard/session').json()['guard']=='G1'
    assert mixed.get('/api/v2/camera/session').json()['id']==cc['id']
    assert mixed.get('/api/v2/state').json()['site']['name']=='Owner A'

@pytest.mark.parametrize('logout',['/api/v2/operator/logout','/api/v2/auth/dev/logout'])
def test_logout_revokes_persisted_owner_even_when_cookie_is_replayed(env,logout):
    manager,_,client=env
    a=client();workspace=create(a,'Logout')
    token=a.cookies.get(ADMIN_COOKIE)
    assert a.post(logout).status_code==204
    a.cookies.set(ADMIN_COOKIE,token,path='/api/v2')
    assert a.get('/api/v2/me').status_code==403
    assert manager.owner(token) is None
    assert manager.db.execute('SELECT owner_hash FROM workspaces WHERE id=?',(workspace['id'],)).fetchone()[0] is None

def test_delete_current_removes_only_calling_owners_guest(env):
    manager,_,client=env
    a,b=client(),client();wa,wb=create(a,'Delete A'),create(b,'Keep B')
    token=a.cookies.get(ADMIN_COOKIE)
    assert a.delete('/api/v2/workspaces/current').status_code==204
    assert wa['id'] not in manager.apps and not (manager.directory/(wa['id']+'.sqlite')).exists()
    assert manager.owner(token) is None
    assert b.get('/api/v2/me').json()['workspace']['id']==wb['id']
    assert a.delete('/api/v2/workspaces/current').status_code==403

def test_owner_cookie_resumes_same_private_database_after_host_restart(env):
    manager,local,client=env
    a,phone=client(),client();workspace=create(a,'Persistent')
    saved_camera=camera(a,'Persistent camera')
    pair(a,phone,'/api/v2/cameras/'+saved_camera['id']+'/pair')
    owner_cookie=a.cookies.get(ADMIN_COOKIE)
    assert owner_cookie.encode() not in (manager.directory/'index.sqlite').read_bytes()
    local.portal.call(manager.close)
    restarted=Workspaces(manager.primary,manager.directory)
    resumed=TestClient(PublicGateway(restarted,SECRET,restarted),base_url=PUBLIC,headers=HEADERS)
    resumed.portal=local.portal
    resumed.cookies.update(a.cookies)
    try:
        assert resumed.get('/api/v2/me').json()['workspace']==workspace
        assert resumed.get('/api/v2/state').json()['cameras'][0]['id']==saved_camera['id']
        assert resumed.post('/api/v2/workspaces',json={'name':'Resume'}).json()['workspace']==workspace
        assert len(restarted.apps)==1
        resumed.cookies.update(phone.cookies)
        assert resumed.get('/api/v2/camera/session').json()['id']==saved_camera['id']
    finally:
        local.portal.call(restarted.close)
        resumed.close()

def test_paired_phones_lazy_resume_their_own_workspaces_before_any_owner_opens(env):
    manager,local,client=env
    a,b,phone=client(),client(),client()
    wa,wb=create(a,'Camera site'),create(b,'Guard site')
    ca=camera(a,'Camera A');camera(b,'Private camera B')
    a.post('/api/v2/guards',json={'callsign':'G1','name':'A guard'})
    gb=b.post('/api/v2/guards',json={'callsign':'G1','name':'B guard'}).json()
    pair(a,phone,'/api/v2/cameras/'+ca['id']+'/pair')
    pair(b,phone,'/api/v2/guards/G1/pair')
    local.portal.call(manager.close)
    restarted=Workspaces(manager.primary,manager.directory)
    resumed=TestClient(PublicGateway(restarted,SECRET,restarted),base_url=PUBLIC,headers=HEADERS)
    resumed.portal=local.portal
    resumed.cookies.update(phone.cookies)
    try:
        assert not restarted.apps
        assert resumed.get('/api/v2/camera/session').json()['id']==ca['id']
        assert set(restarted.apps)=={wa['id']}
        assert resumed.get('/api/v2/guard/session').json()=={'guard':'G1'}
        assert set(restarted.apps)=={wa['id'],wb['id']}
        assert resumed.post('/api/v2/guard/location',json=dict(latitude=28.6,longitude=77.2,accuracy=10,capturedAt=1000)).json()['id']==gb['id']
        assert resumed.get('/api/v2/state').status_code==403
        assert resumed.delete('/api/v2/workspaces/current').status_code==403
        # A guard capability cannot route or authorize a camera session.
        from nivra.classroom import CAMERA_COOKIE,GUARD_COOKIE
        resumed.cookies.clear()
        resumed.cookies.set(CAMERA_COOKIE,phone.cookies.get(GUARD_COOKIE),path='/api/v2/camera')
        assert resumed.get('/api/v2/camera/session').status_code==403
    finally:
        local.portal.call(restarted.close)
        resumed.close()

def test_signed_guest_clip_frames_route_without_browser_cookies(env):
    manager,_,client=env
    a,b,anonymous=client(),client(),client()
    wa=create(a,'Evidence A');create(b,'Evidence B')
    ca=camera(a,'A')
    classroom=manager.apps[wa['id']].state.classroom
    classroom.store.record(ca['id'],'clip-test',dict(id='event',occurredAtMs=1))
    event=classroom.store.events()[0]
    classroom.clips.receive(ca['id'],b'private-clip-test')
    classroom.clips.capture(event['id'],ca['id'])
    manifest=a.get('/api/v2/events/'+event['id']+'/clip').json()
    url=manifest['frames'][0]['url']
    assert b.get('/api/v2/events/'+event['id']+'/clip').status_code==404
    response=anonymous.get(url)
    assert response.status_code==200 and response.content==b'private-clip-test'
    assert anonymous.get('/api/v2/events/'+event['id']+'/clip/frames/0?exp=1&sig='+'0'*64).status_code==403

def test_capacity_is_bounded_but_existing_owner_can_resume(env):
    manager,_,client=env
    manager.limit=1
    a,b=client(),client();workspace=create(a,'Only active guest')
    assert b.post('/api/v2/workspaces',json={'name':'Too many'}).status_code==429
    assert a.post('/api/v2/workspaces',json={'name':'Resume'}).json()['workspace']==workspace
    assert len(manager.apps)==1

def test_phone_push_endpoint_moves_to_its_new_guard_workspace(env):
    from test_guard_push import subscription
    manager,_,client=env
    a,b,phone=client(),client(),client()
    wa,wb=create(a,'Push A'),create(b,'Push B')
    for owner,name in [(a,'Guard A'),(b,'Guard B')]:
        owner.post('/api/v2/guards',json={'callsign':'G1','name':name})
    primary=manager.primary.state.classroom
    primary_guard=primary.store.add_guard('G99','Primary guard')
    sub=subscription()
    primary.push.subscribe(primary_guard['id'],sub)
    pair(a,phone,'/api/v2/guards/G1/pair')
    assert phone.post('/api/v2/guard/push',json={'subscription':sub}).status_code==204
    assert primary.store.db.execute('SELECT COUNT(*) FROM guard_push_subscriptions').fetchone()[0]==0
    pair(b,phone,'/api/v2/guards/G1/pair')
    assert phone.post('/api/v2/guard/push',json={'subscription':sub}).status_code==204
    first=manager.apps[wa['id']].state.classroom.store
    second=manager.apps[wb['id']].state.classroom.store
    assert first.db.execute('SELECT COUNT(*) FROM guard_push_subscriptions').fetchone()[0]==0
    assert second.db.execute('SELECT COUNT(*) FROM guard_push_subscriptions').fetchone()[0]==1


def test_codes_resolve_private_camera_and_guard_without_owner_and_ignore_other_role_cookies(env):
    manager,_,client=env
    a,b,phone=client(),client(),client()
    wa,wb=create(a,'Owner A'),create(b,'Owner B')
    ca,cb=camera(a,'Camera A'),camera(b,'Camera B')
    b.post('/api/v2/guards',json={'callsign':'G1','name':'Guard B'})
    camera_pair=b.post('/api/v2/cameras/'+cb['id']+'/pair').json()
    guard_pair=b.post('/api/v2/guards/G1/pair').json()
    assert phone.post('/api/v2/camera/pair',json={'code':guard_pair['pairingCode']}).status_code==403
    assert phone.post('/api/v2/camera/pair',json={'code':camera_pair['pairingCode']}).json()['id']==cb['id']
    assert phone.post('/api/v2/guard/pair',json={'code':guard_pair['pairingCode']}).json()['guard']=='G1'
    assert phone.get('/api/v2/state').status_code==403
    assert phone.post('/api/v2/operator/redeem',json={'code':guard_pair['pairingCode']}).status_code in (403,422)
    assert phone.get('/api/v2/camera/session').json()['id']==cb['id']
    fresh=b.post('/api/v2/cameras/'+cb['id']+'/pair').json()
    # An owner cookie for A must not redirect the B device capability into A.
    assert a.post('/api/v2/camera/pair',json={'code':fresh['pairingCode']}).json()['id']==cb['id']
    assert a.get('/api/v2/me').json()['workspace']['id']==wa['id']
    assert a.get('/api/v2/camera/session').json()['id']==cb['id']
    assert [c['id'] for c in a.get('/api/v2/state').json()['cameras']]==[ca['id']]
    assert b.get('/api/v2/me').json()['workspace']['id']==wb['id']


@pytest.mark.parametrize('guess', [{'code':'22222222'}, {'token':'x'*32}])
def test_code_guesses_are_limited_before_cross_workspace_lookup_and_do_not_consume_valid_code(env,monkeypatch,guess):
    manager,_,client=env
    owner,phone=client(),client()
    create(owner,'Private')
    c=camera(owner,'Camera')
    pair=owner.post('/api/v2/cameras/'+c['id']+'/pair').json()
    for _ in range(20):
        assert phone.post('/api/v2/camera/pair',json=guess).status_code==403
    scan=manager.all_apps
    def forbidden_scan(): raise AssertionError('Rate check must happen before workspace lookup')
    monkeypatch.setattr(manager,'all_apps',forbidden_scan)
    assert phone.post('/api/v2/camera/pair',json={'code':pair['pairingCode']}).status_code==429
    monkeypatch.setattr(manager,'all_apps',scan)
    manager.code_attempts.recent.clear()
    assert phone.post('/api/v2/camera/pair',json={'code':pair['pairingCode']}).status_code==200


def test_colliding_codes_fail_closed_instead_of_selecting_another_workspace(env):
    from nivra.classroom import digest
    manager,_,client=env
    a,b,phone=client(),client(),client()
    create(a,'A');create(b,'B')
    ca,cb=camera(a,'A'),camera(b,'B')
    pa=a.post('/api/v2/cameras/'+ca['id']+'/pair').json()
    pb=b.post('/api/v2/cameras/'+cb['id']+'/pair').json()
    first,second=[app.state.classroom for app in manager.apps.values()]
    second.pair_codes['camera'][digest(pa['pairingCode'])]=second.pair_codes['camera'][digest(pb['pairingCode'])]
    assert phone.post('/api/v2/camera/pair',json={'code':pa['pairingCode']}).status_code==403
    assert digest(pa['pairingCode']) in first.pair_codes['camera']


def test_code_from_an_expired_private_workspace_cannot_pair_a_new_phone(env):
    manager,_,client=env
    owner,phone=client(),client()
    workspace=create(owner,'Expired guest')
    c=camera(owner,'Camera')
    pair=owner.post('/api/v2/cameras/'+c['id']+'/pair').json()
    with manager.db: manager.db.execute('UPDATE workspaces SET expires=0 WHERE id=?',(workspace['id'],))
    assert phone.post('/api/v2/camera/pair',json={'code':pair['pairingCode']}).status_code==403


def test_camera_deletion_is_owner_scoped_and_denied_to_guard_camera_and_other_workspace(env):
    _,_,client=env
    a,b,phone,guard,anon=client(),client(),client(),client(),client()
    create(a,'A');create(b,'B')
    ca,cb=camera(a,'Camera A'),camera(b,'Camera B')
    a.post('/api/v2/guards',json={'callsign':'G1','name':'Guard A'})
    pair(a,phone,'/api/v2/cameras/'+ca['id']+'/pair')
    pair(a,guard,'/api/v2/guards/G1/pair')
    endpoint='/api/v2/cameras/'+ca['id']
    assert b.delete(endpoint).status_code==404
    for restricted in (phone,guard,anon):assert restricted.delete(endpoint).status_code==403
    assert a.get('/api/v2/state').json()['cameras'][0]['id']==ca['id']
    assert a.delete(endpoint).status_code==204
    assert b.get('/api/v2/state').json()['cameras'][0]['id']==cb['id']
    assert phone.get('/api/v2/camera/session').status_code==403


def test_new_workspace_and_owner_resume_never_seed_camera_records(env):
    manager, local, client = env
    owner = client()
    workspace = create(owner, 'Empty camera setup')
    for _ in range(3):
        state = owner.get('/api/v2/state')
        assert state.status_code == 200
        assert state.json()['cameras'] == []
        assert state.json()['events'] == []
    # Reopening setup/resuming an owner must not create placeholder cameras.
    assert owner.post('/api/v2/workspaces', json={'name': 'Resume'}).json()['workspace'] == workspace
    assert manager.apps[workspace['id']].state.classroom.store.cameras() == []
    local.portal.call(manager.close)
    restarted = Workspaces(manager.primary, manager.directory)
    resumed = TestClient(PublicGateway(restarted, SECRET, restarted), base_url=PUBLIC, headers=HEADERS)
    resumed.portal = local.portal
    resumed.cookies.update(owner.cookies)
    try:
        assert resumed.get('/api/v2/me').json()['workspace'] == workspace
        assert resumed.get('/api/v2/state').json()['cameras'] == []
    finally:
        local.portal.call(restarted.close)
        resumed.close()


def test_explicit_unpaired_and_paired_offline_cameras_are_not_deleted_on_resume(env):
    manager, local, client = env
    owner, phone = client(), client()
    workspace = create(owner, 'Saved camera setup')
    unpaired = camera(owner, 'Camera 1')
    paired = camera(owner, 'Camera 2')
    pair(owner, phone, '/api/v2/cameras/' + paired['id'] + '/pair')
    store = manager.apps[workspace['id']].state.classroom.store
    store.record(paired['id'], 'saved-history', {'id': 'review', 'occurredAtMs': 100})
    history_id = store.events()[0]['id']
    local.portal.call(manager.close)
    restarted = Workspaces(manager.primary, manager.directory)
    resumed = TestClient(PublicGateway(restarted, SECRET, restarted), base_url=PUBLIC, headers=HEADERS)
    resumed.portal = local.portal
    resumed.cookies.update(owner.cookies)
    try:
        state = resumed.get('/api/v2/state').json()
        records = {record['id']: record for record in state['cameras']}
        assert set(records) == {unpaired['id'], paired['id']}
        assert records[unpaired['id']]['paired'] is False
        assert records[paired['id']]['paired'] is True
        assert all(record['feed'] != 'live' for record in records.values())
        assert state['events'][0]['id'] == history_id
    finally:
        local.portal.call(restarted.close)
        resumed.close()
