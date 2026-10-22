"""Local iPhone discovery and bounded HTTP camera reads. No import-time networking."""
import hashlib
import http.client
import ipaddress
import re
import socket
import threading
import time

SERVICE = '_nivra-camera._tcp.local.'
PORT = 8940
MAX_BODY = 1_400_000
REQUEST_TIMEOUT = 4
PRIVATE_NETWORKS = tuple(ipaddress.IPv4Network(value) for value in
    ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))


def interface_addresses():
    import ifaddr
    return tuple(sorted({str(ipaddress.IPv4Address(address.ip))
        for adapter in ifaddr.get_adapters() for address in adapter.ips
        if isinstance(address.ip, str) and ':' not in address.ip}))


def from_host(host, name='iPhone', port=PORT):
    """Validate manual and discovered endpoints with exactly the same policy."""
    if not isinstance(host, str) or type(port) is not int or port != PORT:
        raise ValueError('Use the phone local IPv4 address and port 8940.')
    try:
        address = ipaddress.IPv4Address(host)
    except ipaddress.AddressValueError:
        raise ValueError('Use the phone local IPv4 address.') from None
    if not any(address in network for network in PRIVATE_NETWORKS) or any((
            address.is_loopback, address.is_link_local, address.is_multicast,
            address.is_reserved, address.is_unspecified)):
        raise ValueError('Use the phone private IPv4 address.')
    host = str(address)
    name = ''.join(char for char in str(name) if char.isprintable()).strip()[:60] or 'iPhone'
    return {'id': hashlib.sha256(f'{host}:{PORT}'.encode()).hexdigest()[:24],
        'name': name, 'host': host, 'port': PORT}


class Discovery:
    def __init__(self):
        self._lock = threading.Lock()
        self._lifecycle = threading.RLock()
        self._active = False
        self._addresses = None
        self._next_check = 0
        self._services = {}
        self._zc = None
        self._browser = None

    def start(self):
        with self._lifecycle:
            if self._active:
                return
            self._addresses = interface_addresses()
            self._next_check = time.monotonic()+3
            self._active = True
            try:
                self._open_transport()
            except BaseException:
                self._active = False
                raise

    def _open_transport(self):
        from zeroconf import IPVersion, ServiceBrowser, Zeroconf
        with self._lock:
            if self._zc is not None:
                return
            zc = Zeroconf(ip_version=IPVersion.V4Only)
            self._zc = zc
        try:
            browser = ServiceBrowser(zc, SERVICE, listener=self)
        except BaseException:
            self._close_transport()
            raise
        with self._lock:
            if self._zc is zc:
                self._browser = browser
                return
        browser.cancel()

    def close(self):
        with self._lifecycle:
            self._active = False
            self._close_transport()

    def _close_transport(self):
        with self._lock:
            zc, browser = self._zc, self._browser
            self._zc = self._browser = None
            self._services.clear()
        if browser is not None:
            browser.cancel()
        if zc is not None:
            zc.close()

    def _refresh_interfaces(self):
        # Called from the host's worker-thread polling, never from Bonjour callbacks.
        # Serializing lifecycle changes prevents a late poll reopening a closed host.
        if not self._lifecycle.acquire(blocking=False):
            return
        try:
            now = time.monotonic()
            if not self._active or now < self._next_check:
                return
            self._next_check = now+3
            try:
                addresses = interface_addresses()
            except OSError:
                return
            if addresses == self._addresses and self._zc is not None:
                return
            self._close_transport()
            self._addresses = addresses
            try:
                self._open_transport()
            except Exception:
                # Interface churn can briefly leave no usable socket. Next poll retries.
                self._close_transport()
        finally:
            self._lifecycle.release()

    def add_service(self, zc, service_type, name):
        self.update_service(zc, service_type, name)

    def update_service(self, zc, service_type, name):
        if service_type != SERVICE or not isinstance(name, str) or len(name) > 255:
            return
        with self._lock:
            if self._zc is not zc:
                return
        try:
            info = zc.get_service_info(service_type, name, timeout=1000)
            devices = []
            if info is not None:
                label = name.removesuffix('.'+SERVICE)
                for packed in info.addresses:
                    try:
                        devices.append(from_host(str(ipaddress.IPv4Address(packed)), label, info.port))
                    except (ValueError, TypeError):
                        continue
                if devices:
                    # One advertised phone can have several hotspot/Wi-Fi interfaces.
                    # Native identity survives an address change; legacy names retain IP identity.
                    preferred = devices[0]
                    if re.fullmatch(r'NIVRA-[a-f0-9]{12}', label):
                        preferred['id'] = hashlib.sha256(label.encode()).hexdigest()[:24]
                    preferred['hosts'] = list(dict.fromkeys(device['host'] for device in devices))[:8]
                    devices = [preferred]
        except (OSError, ValueError):
            return
        with self._lock:
            if self._zc is not zc:
                return
            self._services.pop(name, None)
            if devices and len(self._services) < 64:
                self._services[name] = devices[:8]

    def remove_service(self, zc, service_type, name):
        with self._lock:
            if self._zc is zc and service_type == SERVICE:
                self._services.pop(name, None)

    def list_devices(self):
        self._refresh_interfaces()
        with self._lock:
            devices = {device['id']: {**device, 'hosts': list(device['hosts'])}
                for values in self._services.values() for device in values}
        return sorted(devices.values(), key=lambda device: (device['name'], device['id']))[:64]


discovery = Discovery()
start = discovery.start
close = discovery.close
list_devices = discovery.list_devices


def phone_get(device, code, path):
    endpoint = from_host(device.get('host'), port=device.get('port', PORT))
    video = isinstance(path, str) and re.fullmatch(r'/v1/video\?after=[0-9]{1,16}', path) is not None
    if path not in ('/v1/status', '/v1/frame', '/v1/analysis') and not video:
        raise ValueError('Unsupported camera request.')
    if not isinstance(code, str) or re.fullmatch(r'[A-Z0-9]{8}', code) is None:
        raise ValueError('Enter the eight-character phone code.')
    # A validated literal address goes straight to a TCP socket. No DNS, proxy or redirect.
    stream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    stream.settimeout(REQUEST_TIMEOUT)
    def expire():
        # asyncio cancellation cannot stop the worker thread doing this read.
        # Shutdown also interrupts buffered HTTP headers/bodies sent one byte at a time.
        try:
            stream.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        finally:
            stream.close()
    deadline = threading.Timer(REQUEST_TIMEOUT, expire)
    deadline.daemon = True
    deadline.start()
    reply = None
    try:
        stream.connect((endpoint['host'], PORT))
        stream.sendall((f'GET {path} HTTP/1.1\r\nHost: {endpoint["host"]}:{PORT}\r\n'
            f'X-Nivra-Key: {code}\r\nConnection: close\r\n\r\n').encode('ascii'))
        reply = http.client.HTTPResponse(stream)
        reply.begin()
        if reply.status in (401, 403):
            raise PermissionError('Check the code shown on the phone.')
        if reply.status == 204 and (video or path == '/v1/analysis'):
            return dict(reply.getheaders()), b''
        if reply.status != 200:
            raise OSError('Waiting for the phone camera. Keep NIVRA open.')
        lengths = reply.headers.get_all('Content-Length', [])
        if (len(lengths) != 1 or not re.fullmatch(r'[0-9]+', lengths[0])
                or reply.headers.get('Transfer-Encoding') is not None):
            raise OSError('Invalid camera frame size.')
        length = int(lengths[0])
        if not 0 <= length <= (3_000_000 if video else MAX_BODY):
            raise OSError('Invalid camera frame size.')
        data = reply.read(length)
        if len(data) != length:
            raise OSError('Incomplete camera frame.')
        return dict(reply.getheaders()), data
    except http.client.HTTPException:
        raise OSError('Invalid or interrupted camera response.') from None
    finally:
        deadline.cancel()
        if reply is not None: reply.close()
        stream.close()
        deadline.join(timeout=.1)
