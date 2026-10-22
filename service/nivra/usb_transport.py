"""USB-only iPhone transport through macOS usbmuxd. No IP network or downloads."""
import hashlib
import http.client
import plistlib
import socket
import struct

MAX_BODY = 1_400_000


def read_exact(stream, count):
    data = bytearray()
    while len(data) < count:
        chunk = stream.recv(count-len(data))
        if not chunk:
            raise OSError('USB connection closed')
        data.extend(chunk)
    return bytes(data)


def mux(message, path='/var/run/usbmuxd'):
    stream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stream.settimeout(4)
    try:
        stream.connect(path)
        body = plistlib.dumps({'ClientVersionString': 'NIVRA USB/1',
            'ProgName': 'NIVRA', 'kLibUSBMuxVersion': 3, **message})
        stream.sendall(struct.pack('<IIII', len(body)+16, 1, 8, 1)+body)
        length, version, kind, tag = struct.unpack('<IIII', read_exact(stream, 16))
        if not 16 <= length <= 1_000_000 or (version, kind, tag) != (1, 8, 1):
            raise OSError('Invalid USB response')
        response = plistlib.loads(read_exact(stream, length-16))
        return stream, response
    except BaseException:
        stream.close()
        raise


def list_devices():
    stream, response = mux({'MessageType': 'ListDevices'})
    stream.close()
    result = []
    for device in response.get('DeviceList', []):
        properties = device.get('Properties', {})
        # Never silently use Wi-Fi pairing. USB is the user's explicit requirement.
        if properties.get('ConnectionType') != 'USB':
            continue
        serial = properties.get('SerialNumber', '')
        if not serial:
            continue
        result.append({'id': hashlib.sha256(serial.encode()).hexdigest()[:24],
            'muxId': device['DeviceID'], 'name': properties.get('DeviceName') or 'iPhone'})
    return result


def phone_get(device, code, path):
    if path not in ('/v1/status', '/v1/frame'):
        raise ValueError('Unsupported USB request')
    stream, response = mux({'MessageType': 'Connect', 'DeviceID': device['muxId'],
        'PortNumber': socket.htons(8940)})
    try:
        if response.get('Number') != 0:
            raise OSError('Open NIVRA on the phone and tap Use USB camera.')
        stream.sendall((f'GET {path} HTTP/1.1\r\nHost: localhost\r\n'
            f'X-Nivra-Key: {code}\r\nConnection: close\r\n\r\n').encode('ascii'))
        reply = http.client.HTTPResponse(stream)
        reply.begin()
        if reply.status in (401, 403):
            raise PermissionError('Check the code shown on the phone.')
        if reply.status != 200:
            raise OSError('Waiting for the phone camera. Keep NIVRA open.')
        length = reply.length
        if length is None or not 0 <= length <= MAX_BODY:
            raise OSError('Invalid USB frame size')
        data = reply.read(MAX_BODY+1)
        if len(data) != length:
            raise OSError('Incomplete USB frame')
        return dict(reply.getheaders()), data
    finally:
        stream.close()
