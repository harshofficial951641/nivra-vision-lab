"""Direct WebSockets carry a scoped opaque ticket, never HttpOnly cookies."""
import time
from urllib.parse import parse_qs, urlsplit
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from nivra.server import create_app
from nivra.public_gateway import PublicGateway
from nivra.socket_tickets import SocketTickets
from test_server import packet

PUBLIC='https://nivra.tanishq.work'
SOCKET='https://socket-test.trycloudflare.com'
SECRET='s'*50
LOCAL={'origin':'http://127.0.0.1:8765'}
HEADERS={'origin':PUBLIC,'x-nivra-relay':SECRET}

@pytest.fixture
def relay(tmp_path,monkeypatch):
    monkeypatch.setenv('NIVRA_AUTH_MODE','dev')
    monkeypatch.setenv('NIVRA_PUBLIC_ORIGIN',PUBLIC)
    monkeypatch.setenv('NIVRA_SOCKET_ORIGIN',SOCKET)
    app=create_app(database=tmp_path/'tickets.sqlite',relay_only=True)
    gateway=PublicGateway(app,SECRET,app.state.classroom.socket_tickets)
    with TestClient(app,base_url=LOCAL['origin'],headers=LOCAL) as local:
        assert local.post('/api/v2/session').status_code==204
        remote=TestClient(gateway,base_url=PUBLIC,headers=HEADERS)
        remote.portal=local.portal
        link=local.post('/api/v2/operator/invite').json()['url']
        assert remote.post('/api/v2/operator/redeem',json={'token':parse_qs(urlsplit(link).fragment)['operator'][0]}).status_code==204
        yield local,remote,TestClient(gateway,base_url=SOCKET),app.state.classroom


def ticket_socket(client,role):
    response=client.post(f'/api/v2/{role}/socket-ticket',json={})
    assert response.status_code==200,response.text
    result=response.json()
    assert set(result)=={'url','ticket'}
    assert len(result['ticket'])>=40 and '?' not in result['url']
    return result


def test_operator_ticket_works_once_without_browser_cookie_or_relay_secret(relay):
    local,remote,direct,classroom=relay
    assert direct.get('/api/v2/state').status_code==403
    t=ticket_socket(remote,'operator')
    assert all(cookie.value not in str(t) for cookie in remote.cookies.jar)
    with direct.websocket_connect(t['url'],headers={'origin':PUBLIC},subprotocols=['nivra-ticket.'+t['ticket']]) as ws:
        assert ws.accepted_subprotocol == 'nivra-ticket.'+t['ticket']
        ws.send_json({'type':'auth','token':None})
        assert ws.receive_json()['type']=='snapshot'
    with pytest.raises(WebSocketDisconnect):
        with direct.websocket_connect(t['url'],headers={'origin':PUBLIC},subprotocols=['nivra-ticket.'+t['ticket']]):pass


def test_camera_and_guard_roles_cannot_mint_operator_tickets(relay):
    local,remote,direct,classroom=relay
    cam=remote.post('/api/v2/cameras',json=dict(name='Entrance',building='Site',floor='2')).json()
    link=remote.post('/api/v2/cameras/'+cam['id']+'/pair').json()['url']
    phone=TestClient(remote.app,base_url=PUBLIC,headers=HEADERS);phone.portal=local.portal
    assert phone.post('/api/v2/camera/pair',json={'token':parse_qs(urlsplit(link).fragment)['pair'][0]}).status_code==200
    assert phone.post('/api/v2/operator/socket-ticket',json={}).status_code==403
    assert phone.post('/api/v2/guard/socket-ticket',json={}).status_code==403
    t=ticket_socket(phone,'camera')
    with direct.websocket_connect(t['url'],headers={'origin':PUBLIC},subprotocols=['nivra-ticket.'+t['ticket']]) as ws:
        assert ws.accepted_subprotocol == 'nivra-ticket.'+t['ticket']
        assert ws.receive_json()['type']=='ready'
        ws.send_bytes(packet(100))
        assert ws.receive_json()['type']=='accepted'
    classroom.store.add_guard('G1','Guard One')
    link=remote.post('/api/v2/guards/G1/pair').json()['url']
    guard=TestClient(remote.app,base_url=PUBLIC,headers=HEADERS);guard.portal=local.portal
    assert guard.post('/api/v2/guard/pair',json={'token':parse_qs(urlsplit(link).fragment)['pair'][0]}).status_code==200
    assert guard.post('/api/v2/operator/socket-ticket',json={}).status_code==403
    assert guard.post('/api/v2/camera/socket-ticket',json={}).status_code==403
    t=ticket_socket(guard,'guard')
    with direct.websocket_connect(t['url'],headers={'origin':PUBLIC},subprotocols=['nivra-ticket.'+t['ticket']]) as ws:
        assert ws.accepted_subprotocol == 'nivra-ticket.'+t['ticket']
        ws.send_json({'type':'auth','token':None})
        assert ws.receive_json()['guard']['callsign']=='G1'


def test_tickets_enforce_origin_path_expiry_and_revocation(relay):
    _,remote,direct,classroom=relay
    t=ticket_socket(remote,'operator')
    for url,origin in [(t['url'],'https://evil.example'),(SOCKET.replace('https:','wss:')+'/api/v2/guard/stream',PUBLIC)]:
        with pytest.raises(WebSocketDisconnect):
            with direct.websocket_connect(url,headers={'origin':origin},subprotocols=['nivra-ticket.'+t['ticket']]):pass
    assert t['ticket'] in classroom.socket_tickets.pending
    classroom.socket_tickets.pending[t['ticket']]['expires']=time.monotonic()-1
    with pytest.raises(WebSocketDisconnect):
        with direct.websocket_connect(t['url'],headers={'origin':PUBLIC},subprotocols=['nivra-ticket.'+t['ticket']]):pass
    t=ticket_socket(remote,'operator')
    assert remote.post('/api/v2/operator/logout').status_code==204
    with pytest.raises(WebSocketDisconnect):
        with direct.websocket_connect(t['url'],headers={'origin':PUBLIC},subprotocols=['nivra-ticket.'+t['ticket']]):pass


@pytest.mark.parametrize('origin',['http://example.trycloudflare.com','https://evil.example','https://x.trycloudflare.com/path','https://x.trycloudflare.com:443'])
def test_relay_origin_is_restricted(origin):
    with pytest.raises(ValueError):SocketTickets(origin)


def test_gateway_selects_only_validated_ticket_and_hides_it_from_application():
    token = 'opaque-ticket-'+'a'*40
    protocol = 'nivra-ticket.'+token
    tickets = SocketTickets(SOCKET)
    tickets.pending[token] = dict(path='/api/v2/operator', origin=PUBLIC,
        cookie='nivra_operator=trusted-server-cookie', authorization='Bearer trusted-server-session',
        expires=time.monotonic()+30)
    observed = []

    async def application(scope, receive, send):
        assert (await receive())['type'] == 'websocket.connect'
        observed.append(scope)
        await send({'type': 'websocket.accept', 'subprotocol': 'application-must-not-select-this'})
        await send({'type': 'websocket.close', 'code': 1000})

    client = TestClient(PublicGateway(application, SECRET, tickets), base_url=SOCKET)
    try:
        with client.websocket_connect('/api/v2/operator', headers={
            'origin': PUBLIC, 'cookie': 'nivra_operator=caller-forgery', 'authorization': 'Bearer caller-forgery'
        }, subprotocols=['unrelated-protocol', protocol]) as ws:
            assert ws.accepted_subprotocol == protocol
    finally:
        client.close()
    assert token not in tickets.pending
    scope = observed[0]
    assert scope['subprotocols'] == []
    assert token not in repr(scope)
    headers = dict(scope['headers'])
    assert b'sec-websocket-protocol' not in headers
    assert headers[b'cookie'] == b'nivra_operator=trusted-server-cookie'
    assert headers[b'authorization'] == b'Bearer trusted-server-session'


def test_camera_removal_closes_feed_and_revokes_cookie_sessions_codes_and_only_its_tickets(relay):
    local,owner,direct,classroom=relay
    direct.portal=local.portal
    camera=owner.post('/api/v2/cameras',json={'name':'Remove me','building':'QA','floor':'1'}).json()
    phone=TestClient(owner.app,base_url=PUBLIC,headers=HEADERS);phone.portal=local.portal
    link=owner.post('/api/v2/cameras/'+camera['id']+'/pair').json()
    assert phone.post('/api/v2/camera/pair',json={'code':link['pairingCode']}).status_code==200
    active=ticket_socket(phone,'camera')
    pending=ticket_socket(phone,'camera')
    operator=ticket_socket(owner,'operator')
    # Pending aliases can overlap a live close; removal must invalidate them too.
    token,code=classroom.mint_device_pair('camera',camera['id'])
    try:
        with direct.websocket_connect(active['url'],headers={'origin':PUBLIC},subprotocols=['nivra-ticket.'+active['ticket']]) as feed:
            assert feed.receive_json()['type']=='ready'
            feed.send_bytes(packet(100))
            assert feed.receive_json()['type']=='accepted'
            assert owner.delete('/api/v2/cameras/'+camera['id']).status_code==204
            with pytest.raises(WebSocketDisconnect):feed.receive_json()
        assert camera['id'] not in classroom.live
        assert camera['id'] not in classroom.pending
        assert not any(subject==camera['id'] for subject in classroom.credentials.values())
        assert classroom.store.db.execute("SELECT count(*) FROM device_sessions WHERE kind='camera' AND subject_id=?",(camera['id'],)).fetchone()[0]==0
        assert pending['ticket'] not in classroom.socket_tickets.pending
        assert operator['ticket'] in classroom.socket_tickets.pending
        assert phone.get('/api/v2/camera/session').status_code==403
        assert phone.post('/api/v2/camera/socket-ticket',json={}).status_code==403
        assert phone.post('/api/v2/camera/pair',json={'token':token}).status_code==403
        assert phone.post('/api/v2/camera/pair',json={'code':code}).status_code==403
        with pytest.raises(WebSocketDisconnect):
            with direct.websocket_connect(pending['url'],headers={'origin':PUBLIC},subprotocols=['nivra-ticket.'+pending['ticket']]):pass
        assert not owner.get('/api/v2/state').json()['cameras']
    finally:phone.close()
