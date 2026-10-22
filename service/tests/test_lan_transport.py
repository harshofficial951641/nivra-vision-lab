from io import BytesIO
import socket
import sys
import threading
import time
from types import SimpleNamespace

import pytest
from nivra import lan_transport as transport


@pytest.mark.parametrize('host', ['127.0.0.1', '169.254.1.2', '8.8.8.8', '100.64.0.1',
    '0.0.0.0', '224.0.0.1', '240.0.0.1', '::1', 'localhost', '192.168.1.2.evil',
    'http://192.168.1.2', '192.168.001.2', '192.168.1.2\r\nX: bad'])
def test_reject_non_private_literal_hosts(host):
    with pytest.raises(ValueError):
        transport.from_host(host)


@pytest.mark.parametrize('host', ['10.0.0.2', '172.16.0.2', '172.31.255.2', '192.168.1.2'])
def test_manual_discovery_identity_is_stable(host):
    one = transport.from_host(host)
    assert one == transport.from_host(host)
    assert len(one['id']) == 24 and one['port'] == 8940
    assert one['id'] == transport.from_host(host, 'Other name')['id']


@pytest.mark.parametrize('port', [80, 443, 8941, '8940', True])
def test_fixed_port_only(port):
    with pytest.raises(ValueError):
        transport.from_host('192.168.1.2', port=port)


class Stream:
    def __init__(self, response):
        self.response = response
        self.sent = b''
        self.closed = False
    def settimeout(self, seconds): self.timeout = seconds
    def connect(self, address): self.address = address
    def sendall(self, data): self.sent += data
    def makefile(self, *_): return BytesIO(self.response)
    def shutdown(self, *_): self.closed = True
    def close(self): self.closed = True


def test_http_frame_uses_literal_ip_key_and_closes_socket(monkeypatch):
    stream = Stream(b'HTTP/1.1 200 OK\r\nContent-Length: 4\r\nX-Nivra-Sequence: 7\r\n\r\njpeg')
    monkeypatch.setattr(transport.socket, 'socket', lambda *_: stream)
    monkeypatch.setattr(transport.socket, 'getaddrinfo', lambda *_: pytest.fail('DNS must not be used'))
    headers, body = transport.phone_get(transport.from_host('192.168.1.2'), 'ABCD2345', '/v1/frame')
    assert body == b'jpeg' and headers['X-Nivra-Sequence'] == '7'
    assert stream.address == ('192.168.1.2', 8940) and stream.timeout == 4
    assert b'X-Nivra-Key: ABCD2345\r\n' in stream.sent
    assert stream.sent.startswith(b'GET /v1/frame HTTP/1.1\r\n') and stream.closed


@pytest.mark.parametrize('reply, exception', [
    (b'401 Unauthorized\r\nContent-Length: 0', PermissionError),
    (b'403 Forbidden\r\nContent-Length: 0', PermissionError),
    (b'302 Redirect\r\nLocation: http://8.8.8.8/\r\nContent-Length: 0', OSError),
    (b'200 OK\r\nContent-Length: 1400001', OSError),
    (b'200 OK', OSError),
    (b'200 OK\r\nContent-Length: -1', OSError),
    (b'200 OK\r\nContent-Length: 0\r\nContent-Length: 0', OSError),
    (b'200 OK\r\nContent-Length: 4\r\nTransfer-Encoding: chunked', OSError),
    (b'200 OK\r\nContent-Length: 4', OSError)])
def test_http_auth_redirect_and_frame_bounds(monkeypatch, reply, exception):
    stream = Stream(b'HTTP/1.1 '+reply+b'\r\n\r\n')
    monkeypatch.setattr(transport.socket, 'socket', lambda *_: stream)
    with pytest.raises(exception):
        transport.phone_get(transport.from_host('10.0.0.2'), 'ABCD2345', '/v1/status')
    assert stream.closed


@pytest.mark.parametrize('code,path', [('ABC1234\r\nInjected: x', '/v1/frame'),
    ('abcd2345', '/v1/frame'), ('ABCD2345', '//evil'), ('ABCD2345', '/v1/frame?url=evil')])
def test_invalid_request_rejected_before_socket(monkeypatch, code, path):
    monkeypatch.setattr(transport.socket, 'socket', lambda *_: pytest.fail('Must not connect'))
    with pytest.raises(ValueError):
        transport.phone_get(transport.from_host('10.0.0.2'), code, path)


def test_discovery_filters_deduplicates_updates_and_removes():
    discovery = transport.Discovery()
    assert discovery.list_devices() == []  # No implicit network startup.
    info = SimpleNamespace(port=8940, addresses=[socket.inet_aton('192.168.1.2'),
        socket.inet_aton('8.8.8.8'), socket.inet_aton('127.0.0.1')])
    zc = SimpleNamespace(get_service_info=lambda *_args, **_kwargs: info)
    discovery._zc = zc
    name = 'Phone.'+transport.SERVICE
    discovery.add_service(zc, transport.SERVICE, name)
    assert discovery.list_devices() == [{**transport.from_host('192.168.1.2', 'Phone'), 'hosts': ['192.168.1.2']}]
    discovery.add_service(zc, transport.SERVICE, 'Duplicate.'+transport.SERVICE)
    assert len(discovery.list_devices()) == 1
    discovery.remove_service(zc, transport.SERVICE, 'Duplicate.'+transport.SERVICE)
    info.port = 80
    discovery.update_service(zc, transport.SERVICE, name)
    assert discovery.list_devices() == []
    info.port = 8940
    discovery.update_service(zc, transport.SERVICE, name)
    result = discovery.list_devices()
    result[0]['host'] = '8.8.8.8'
    assert discovery.list_devices()[0]['host'] == '192.168.1.2'
    discovery.remove_service(zc, transport.SERVICE, name)
    assert discovery.list_devices() == []


def test_discovery_close_clears_and_late_callback_cannot_restore():
    discovery = transport.Discovery()
    closed = []
    def lookup(*_args, **_kwargs):
        discovery.close()
        return SimpleNamespace(port=8940, addresses=[socket.inet_aton('10.0.0.2')])
    zc = SimpleNamespace(get_service_info=lookup, close=lambda: closed.append('closed'))
    discovery._zc = zc
    discovery.add_service(zc, transport.SERVICE, 'Phone.'+transport.SERVICE)
    assert discovery.list_devices() == [] and closed == ['closed']
    discovery.close()


def test_discovery_explicit_start_is_idempotent_and_closes_browser(monkeypatch):
    monkeypatch.setattr(transport, 'interface_addresses', lambda: ('192.168.1.100',))
    events = []
    zc = SimpleNamespace(close=lambda: events.append('close'))
    def zeroconf(**kwargs):
        assert kwargs == {'ip_version': 'ipv4'}
        events.append('start')
        return zc
    def browser(actual, service_type, listener):
        assert actual is zc and service_type == transport.SERVICE
        assert isinstance(listener, transport.Discovery)
        return SimpleNamespace(cancel=lambda: events.append('cancel'))
    monkeypatch.setitem(sys.modules, 'zeroconf', SimpleNamespace(Zeroconf=zeroconf,
        ServiceBrowser=browser, IPVersion=SimpleNamespace(V4Only='ipv4')))
    discovery = transport.Discovery()
    assert events == []
    discovery.start()
    discovery.start()
    discovery.close()
    discovery.close()
    assert events == ['start', 'cancel', 'close']


def test_discovery_cache_is_bounded():
    discovery = transport.Discovery()
    info = SimpleNamespace(port=8940, addresses=[socket.inet_aton('10.0.0.2')])
    zc = SimpleNamespace(get_service_info=lambda *_args, **_kwargs: info)
    discovery._zc = zc
    for number in range(70):
        info.addresses = [socket.inet_aton(f'10.0.0.{number+1}')]
        discovery.add_service(zc, transport.SERVICE, f'Phone{number}.'+transport.SERVICE)
    assert len(discovery.list_devices()) == len(discovery._services) == 64


def test_native_phone_interfaces_merge_and_identity_survives_address_change():
    discovery = transport.Discovery()
    info = SimpleNamespace(port=8940, addresses=[socket.inet_aton('192.168.1.2'),
        socket.inet_aton('10.0.0.2'), socket.inet_aton('8.8.8.8')])
    zc = SimpleNamespace(get_service_info=lambda *_args, **_kwargs: info)
    discovery._zc = zc
    name = 'NIVRA-abcdef123456.'+transport.SERVICE
    discovery.add_service(zc, transport.SERVICE, name)
    devices = discovery.list_devices()
    assert len(devices) == 1
    assert devices[0]['host'] == '192.168.1.2'
    assert devices[0]['hosts'] == ['192.168.1.2', '10.0.0.2']
    identity = devices[0]['id']
    info.addresses = [socket.inet_aton('172.20.10.2')]
    discovery.update_service(zc, transport.SERVICE, name)
    assert discovery.list_devices() == [{**transport.from_host('172.20.10.2', 'NIVRA-abcdef123456'),
        'id': identity, 'hosts': ['172.20.10.2']}]


def test_socket_failure_still_closes_stream(monkeypatch):
    stream = Stream(b'')
    def fail(_): raise TimeoutError('timed out')
    stream.connect = fail
    monkeypatch.setattr(transport.socket, 'socket', lambda *_: stream)
    with pytest.raises(TimeoutError):
        transport.phone_get(transport.from_host('10.0.0.2'), 'ABCD2345', '/v1/frame')
    assert stream.closed


def test_absolute_deadline_interrupts_a_slow_http_header(monkeypatch):
    client, server = socket.socketpair()
    class Connected:
        def settimeout(self, seconds): client.settimeout(seconds)
        def connect(self, _): pass
        def sendall(self, data): client.sendall(data)
        def makefile(self, *args): return client.makefile(*args)
        def shutdown(self, how): client.shutdown(how)
        def close(self): client.close()
    done = threading.Event()
    def drip():
        try:
            server.recv(4096)
            for byte in b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n':
                server.sendall(bytes([byte]))
                if done.wait(.01): break
        except OSError:
            pass
        finally:
            server.close()
    thread = threading.Thread(target=drip)
    monkeypatch.setattr(transport, 'REQUEST_TIMEOUT', .08)
    monkeypatch.setattr(transport.socket, 'socket', lambda *_: Connected())
    thread.start()
    started = time.monotonic()
    try:
        with pytest.raises((OSError, ValueError)):
            transport.phone_get(transport.from_host('10.0.0.2'), 'ABCD2345', '/v1/frame')
        assert time.monotonic()-started < .5
    finally:
        done.set()
        thread.join(1)


@pytest.fixture
def changing_interfaces(monkeypatch):
    current = {'addresses': ('127.0.0.1', '192.168.1.4'), 'now': 0}
    instances = []
    info = SimpleNamespace(port=8940, addresses=[socket.inet_aton('192.168.1.3')])
    def factory(**_kwargs):
        zc = SimpleNamespace(closed=False, get_service_info=lambda *_args, **_kwargs: info)
        zc.close = lambda: setattr(zc, 'closed', True)
        instances.append(zc)
        return zc
    monkeypatch.setitem(sys.modules, 'zeroconf', SimpleNamespace(Zeroconf=factory,
        ServiceBrowser=lambda *_args, **_kwargs: SimpleNamespace(cancel=lambda: None),
        IPVersion=SimpleNamespace(V4Only='ipv4')))
    monkeypatch.setattr(transport, 'interface_addresses', lambda: current['addresses'])
    monkeypatch.setattr(transport.time, 'monotonic', lambda: current['now'])
    return current, instances, info


@pytest.mark.parametrize('addresses,expected', [
    (('127.0.0.1', '192.168.1.4'), 1),
    (('127.0.0.1', '172.20.10.2'), 2),
    (('127.0.0.1',), 2),
    (('127.0.0.1', '192.168.1.4', '172.20.10.2'), 2)])
def test_interface_poll_rebinds_only_on_actual_change(changing_interfaces, addresses, expected):
    current, instances, _ = changing_interfaces
    discovery = transport.Discovery()
    discovery.start()
    current['addresses'] = addresses
    current['now'] = 2.9
    discovery.list_devices()
    assert len(instances) == 1
    current['now'] = 3
    discovery.list_devices()
    assert len(instances) == expected
    assert instances[0].closed == (expected == 2)
    discovery.close()


def test_hotspot_change_rediscovers_same_phone_identity_and_ignores_old_callback(changing_interfaces):
    current, instances, info = changing_interfaces
    discovery = transport.Discovery()
    discovery.start()
    name = 'NIVRA-abcdef123456.'+transport.SERVICE
    discovery.add_service(instances[0], transport.SERVICE, name)
    identity = discovery.list_devices()[0]['id']
    current.update(now=3, addresses=('127.0.0.1', '172.20.10.2'))
    assert discovery.list_devices() == []  # Old-network endpoints are no longer offered.
    discovery.add_service(instances[0], transport.SERVICE, name)
    assert discovery.list_devices() == []
    info.addresses = [socket.inet_aton('172.20.10.1')]
    discovery.add_service(instances[1], transport.SERVICE, name)
    assert discovery.list_devices()[0]['id'] == identity
    assert discovery.list_devices()[0]['host'] == '172.20.10.1'
    discovery.close()


def test_closed_discovery_never_respawns_from_late_poll(changing_interfaces):
    current, instances, _ = changing_interfaces
    discovery = transport.Discovery()
    discovery.start()
    discovery.close()
    current.update(now=100, addresses=('172.20.10.2',))
    assert discovery.list_devices() == []
    assert len(instances) == 1 and instances[0].closed


def test_temporary_rebind_failure_retries_on_next_poll(changing_interfaces, monkeypatch):
    current, instances, _ = changing_interfaces
    discovery = transport.Discovery()
    discovery.start()
    original = discovery._open_transport
    def fail(): raise OSError('Interface not ready')
    monkeypatch.setattr(discovery, '_open_transport', fail)
    current.update(now=3, addresses=('172.20.10.2',))
    assert discovery.list_devices() == [] and instances[0].closed
    monkeypatch.setattr(discovery, '_open_transport', original)
    current['now'] = 4
    discovery.list_devices()
    assert len(instances) == 1
    current['now'] = 6
    discovery.list_devices()
    assert len(instances) == 2
    discovery.close()
