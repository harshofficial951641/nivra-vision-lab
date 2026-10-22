import asyncio
import hashlib
import json
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import HTTPException
from nivra import local_pairing as pairing


@pytest.fixture
def broker(monkeypatch):
    clock, calls = [1000.0], []
    async def attach(host, code):
        calls.append((host, code))
        await asyncio.sleep(0)
        return {'cameraId': 'camera-one', 'name': 'Phone'}
    result = pairing.PairingBroker(attach, clock=lambda: clock[0])
    result.server = object()
    monkeypatch.setattr(pairing, 'interface_addresses', lambda: ['127.0.0.1', '8.8.8.8', '192.168.1.4', '10.0.0.2'])
    return result, clock, calls


def capability(broker):
    response = broker.invite()
    assert response['expiresInSeconds'] == 300
    url = urlsplit(response['url'])
    assert url.scheme == 'nivra' and url.netloc == 'local-camera'
    assert parse_qs(url.query) == {'host': ['192.168.1.4'], 'hosts': ['192.168.1.4,10.0.0.2'], 'port': ['8871']}
    token = parse_qs(url.fragment)['pair'][0]
    assert len(token) == 43
    return {'token': token, 'code': 'ABCD2345', 'port': 8940}


def test_two_visible_qrs_remain_valid_and_redeem_is_same_session_idempotent(broker):
    service, clock, calls = broker
    old = capability(service)
    body = capability(service)
    assert len(service.invites) == 2
    async def verify():
        assert (await service.redeem('192.168.1.4', old))['cameraId'] == 'camera-one'
        first, retry = await asyncio.gather(service.redeem('192.168.1.2', body), service.redeem('192.168.1.2', body))
        assert first == retry == {'cameraId': 'camera-one', 'name': 'Phone'}
        assert calls == [('192.168.1.4', 'ABCD2345'), ('192.168.1.2', 'ABCD2345')]
        for host, changed in [('192.168.1.3', body), ('192.168.1.2', {**body, 'code': 'WXYZ2345'})]:
            with pytest.raises(HTTPException) as used: await service.redeem(host, changed)
            assert used.value.status_code == 403
        assert body['token'] not in str(service.invites) and body['code'] not in str(service.invites)
        clock[0] += 300
        with pytest.raises(HTTPException): await service.redeem('192.168.1.2', body)
    asyncio.run(verify())


def test_invites_prune_expired_and_bound_tabs(broker):
    service, clock, _ = broker
    first = capability(service)
    for _ in range(16): capability(service)
    assert len(service.invites) == 16
    assert hashlib.sha256(first['token'].encode()).hexdigest() not in service.invites
    clock[0] += 301
    capability(service)
    assert len(service.invites) == 1


def test_failed_phone_verification_does_not_consume_token(broker):
    service, _, calls = broker
    body = capability(service)
    original = service.attach
    async def denied(*_): raise HTTPException(409, 'Keep the camera open.')
    async def verify():
        service.attach = denied
        with pytest.raises(HTTPException): await service.redeem('192.168.1.2', body)
        assert 'claim' not in next(iter(service.invites.values()))
        service.attach = original
        assert (await service.redeem('192.168.1.2', body))['cameraId'] == 'camera-one'
    asyncio.run(verify())


def test_success_replay_cannot_restore_removed_camera(broker):
    service, _, calls = broker
    body = capability(service)
    async def verify():
        await service.redeem('192.168.1.2', body)
        service.valid_result = lambda result: False
        with pytest.raises(HTTPException) as error: await service.redeem('192.168.1.2', body)
        assert error.value.status_code == 403 and len(calls) == 1
    asyncio.run(verify())


@pytest.mark.parametrize('changed', [{'port': 80}, {'port': True}, {'code': 'ABCD\r\nX'},
    {'code': 'abcd2345'}, {'token': 'x'*42}, {'host': '8.8.8.8'}])
def test_strict_native_payload_cannot_target_another_endpoint(broker, changed):
    service, _, calls = broker
    body = {**capability(service), **changed}
    async def verify():
        with pytest.raises(HTTPException) as error: await service.redeem('192.168.1.2', body)
        assert error.value.status_code == 400
    asyncio.run(verify())
    assert not calls


class Writer:
    def __init__(self, host='192.168.1.2'): self.host, self.data, self.closed = host, b'', False
    def get_extra_info(self, _): return (self.host, 12345)
    def write(self, value): self.data += value
    async def drain(self): pass
    def close(self): self.closed = True


def request(body, *, method='POST /pair HTTP/1.1', extra=None):
    data = json.dumps(body).encode()
    headers = f'{method}\r\nContent-Type: application/json\r\nContent-Length: {len(data)}\r\n'
    return headers.encode()+(extra or b'')+b'\r\n'+data


def exchange(service, raw, host='192.168.1.2'):
    async def verify():
        reader = asyncio.StreamReader(limit=8192)
        reader.feed_data(raw);reader.feed_eof()
        writer = Writer(host)
        await service.handle(reader, writer)
        assert writer.closed and not service.connections
        header, body = writer.data.split(b'\r\n\r\n', 1)
        assert b'Access-Control-Allow-Origin' not in header
        return int(header.split()[1]), json.loads(body)
    return asyncio.run(verify())


def test_pair_only_http_listener_and_private_peer_scope(broker):
    service, _, calls = broker
    body = capability(service)
    assert exchange(service, request(body)) == (200, {'cameraId': 'camera-one', 'name': 'Phone'})
    for method in ['GET /pair HTTP/1.1', 'OPTIONS /pair HTTP/1.1', 'POST /api/v2/state HTTP/1.1', 'POST /pair?x=1 HTTP/1.1']:
        assert exchange(service, request(body, method=method))[0] == 404
    for peer in ['8.8.8.8', '127.0.0.1', '169.254.1.2', '100.64.0.2', '::1']:
        assert exchange(service, request(body), peer)[0] == 403
    assert len(calls) == 1


@pytest.mark.parametrize('raw,status', [
    (b'POST /pair HTTP/1.1\r\nContent-Length: 4097\r\nContent-Type: application/json\r\n\r\n', 413),
    (b'POST /pair HTTP/1.1\r\nContent-Length: 2\r\nContent-Length: 2\r\nContent-Type: application/json\r\n\r\n{}', 400),
    (b'POST /pair HTTP/1.1\r\nContent-Length: 2\r\nTransfer-Encoding: chunked\r\nContent-Type: application/json\r\n\r\n{}', 400),
    (b'POST /pair HTTP/1.1\r\nContent-Length: 2\r\nContent-Type: text/plain\r\n\r\n{}', 400),
    (b'POST /pair HTTP/1.1\r\nContent-Length: 200\r\nContent-Type: application/json\r\n\r\n{}', 400),
    (b'POST /pair HTTP/1.1\r\nX-Padding: '+b'x'*4100+b'\r\n\r\n', 413)])
def test_http_bounds_and_ambiguous_headers_rejected(broker, raw, status):
    service, _, calls = broker
    assert exchange(service, raw)[0] == status
    assert not calls


def test_slow_body_deadline_and_close_clear_capabilities(broker, monkeypatch):
    service, _, _ = broker
    body = capability(service)
    monkeypatch.setattr(pairing, 'READ_TIMEOUT', .01)
    async def verify():
        reader = asyncio.StreamReader();writer = Writer()
        await service.handle(reader, writer)
        assert writer.data.startswith(b'HTTP/1.1 408 ')
        service.server = None
        await service.close()
        assert not service.invites and not service.connections
        with pytest.raises(HTTPException): await service.redeem('192.168.1.2', body)
    asyncio.run(verify())


def test_phone_verification_deadline_does_not_consume_capability(broker, monkeypatch):
    service, _, _ = broker
    body = capability(service)
    async def slow(*_): await asyncio.Event().wait()
    service.attach = slow
    monkeypatch.setattr(pairing, 'VERIFY_TIMEOUT', .01)
    assert exchange(service, request(body))[0] == 408
    assert 'claim' not in next(iter(service.invites.values()))


def test_connection_cap_and_shutdown_cancel_waiting_requests(broker):
    service, _, _ = broker
    async def verify():
        writers = [Writer() for _ in range(17)]
        tasks = [asyncio.create_task(service.handle(asyncio.StreamReader(), writer)) for writer in writers]
        await asyncio.sleep(0)
        assert len(service.connections) == 16 and writers[-1].closed
        service.server = None
        await service.close()
        await asyncio.gather(*tasks, return_exceptions=True)
        assert not service.connections and all(writer.closed for writer in writers)
    asyncio.run(verify())


def test_real_listener_lifecycle_keeps_loopback_out_of_lan_pairing():
    async def verify():
        async def forbidden(*_): pytest.fail('Loopback peer cannot pair')
        service = pairing.PairingBroker(forbidden)
        await service.start(port=0)
        port = service.server.sockets[0].getsockname()[1]
        try:
            reader, writer = await asyncio.open_connection('127.0.0.1', port)
            writer.write(b'POST /pair HTTP/1.1\r\n\r\n');await writer.drain()
            assert (await reader.readline()).startswith(b'HTTP/1.1 403 ')
            writer.close();await writer.wait_closed()
        finally:
            await service.close()
        assert service.server is None and not service.connections
    asyncio.run(verify())


def test_occupied_pair_port_cannot_produce_a_valid_invitation(monkeypatch):
    async def occupied(*_args, **_kwargs): raise OSError('Address already in use')
    monkeypatch.setattr(pairing.asyncio, 'start_server', occupied)
    async def verify():
        async def attach(*_): pytest.fail('No listener means no pairing')
        service = pairing.PairingBroker(attach)
        with pytest.raises(OSError): await service.start()
        with pytest.raises(HTTPException) as error: service.invite()
        assert error.value.status_code == 503 and not service.invites
        await service.close()
    asyncio.run(verify())
