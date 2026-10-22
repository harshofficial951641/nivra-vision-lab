"""Capability-only LAN listener. The local operator API remains on loopback."""
import asyncio
import hashlib
import json
import re
import secrets
import time
from urllib.parse import urlencode

from fastapi import HTTPException
from .lan_transport import from_host, interface_addresses

PORT = 8871
READ_TIMEOUT = 5
VERIFY_TIMEOUT = 8


class PairingBroker:
    def __init__(self, attach, *, clock=time.monotonic, valid_result=None):
        self.attach, self.clock = attach, clock
        self.valid_result = valid_result or (lambda result: True)
        self.invites = {}
        self.lock = asyncio.Lock()
        self.server = None
        self.connections = set()
        self.closed = False

    async def start(self, *, port=PORT):
        self.closed = False
        self.server = await asyncio.start_server(self.handle, '0.0.0.0', port, limit=8192)

    async def close(self):
        self.closed = True
        self.invites.clear()
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        tasks = tuple(self.connections)
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def invite(self):
        if self.closed or self.server is None:
            raise HTTPException(503, 'Local phone pairing is not ready. Restart NIVRA on this Mac.')
        hosts = []
        try: addresses = interface_addresses()
        except OSError: raise HTTPException(503, 'Could not read this Mac Wi-Fi address. Reconnect Wi-Fi and try again.') from None
        for host in addresses:
            try: hosts.append(from_host(host)['host'])
            except ValueError: continue
        hosts = list(dict.fromkeys(hosts))[:8]
        if not hosts:
            raise HTTPException(409, 'Join the same Wi-Fi router as your phones, then try again.')
        token = secrets.token_urlsafe(32)
        self.invites.clear()
        self.invites[hashlib.sha256(token.encode()).hexdigest()] = {'expires': self.clock()+300}
        query = urlencode(dict(host=hosts[0], hosts=','.join(hosts), port=PORT))
        return {'url': f'nivra://local-camera?{query}#pair={token}', 'expiresInSeconds': 300}

    async def redeem(self, host, body):
        from_host(host)
        if (not isinstance(body, dict) or set(body) != {'token', 'code', 'port'}
                or not isinstance(body['token'], str) or re.fullmatch(r'[A-Za-z0-9_-]{43}', body['token']) is None
                or not isinstance(body['code'], str) or re.fullmatch(r'[A-Z0-9]{8}', body['code']) is None
                or type(body['port']) is not int or body['port'] != 8940):
            raise HTTPException(400, 'Scan the Mac QR again and keep your phone camera open.')
        key = hashlib.sha256(body['token'].encode()).hexdigest()
        claim = hashlib.sha256((host+'\0'+body['code']).encode()).hexdigest()
        async with self.lock:
            entry = self.invites.get(key)
            if self.closed or not entry or entry['expires'] <= self.clock():
                self.invites.pop(key, None)
                raise HTTPException(403, 'This QR expired. Show a new QR on your Mac.')
            if entry.get('claim'):
                if not secrets.compare_digest(entry['claim'], claim):
                    raise HTTPException(403, 'This QR was already used. Show a new QR on your Mac.')
                if not self.valid_result(entry['result']):
                    raise HTTPException(403, 'This camera was removed. Show a new QR on your Mac.')
                return entry['result']
            result = await self.attach(host, body['code'])
            entry.update(claim=claim, result=result)
            return result

    async def read_body(self, reader):
        headers = await reader.readuntil(b'\r\n\r\n')
        if len(headers) > 4096: raise HTTPException(413, 'Pairing request is too large.')
        lines = headers.decode('ascii').split('\r\n')
        if lines[0] != 'POST /pair HTTP/1.1':
            raise HTTPException(404, 'Use the QR shown on your Mac.')
        values = {}
        for line in lines[1:-2]:
            key, separator, value = line.partition(':')
            key = key.lower()
            if not separator or not re.fullmatch(r'[a-z0-9-]+', key) or key in values:
                raise HTTPException(400, 'Invalid pairing request.')
            values[key] = value.strip()
        if 'transfer-encoding' in values or values.get('content-type', '').lower() != 'application/json':
            raise HTTPException(400, 'Use the NIVRA app to scan this QR.')
        length = values.get('content-length', '')
        if not re.fullmatch(r'[0-9]{1,4}', length) or not 0 < int(length) <= 4096:
            raise HTTPException(413, 'Pairing request is too large.')
        return json.loads(await reader.readexactly(int(length)))

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        if self.closed or len(self.connections) >= 16:
            writer.close()
            return
        self.connections.add(task)
        try:
            peer = writer.get_extra_info('peername')
            try: host = from_host(peer[0])['host']
            except (ValueError, TypeError): raise HTTPException(403, 'Join the same private Wi-Fi router.') from None
            body = await asyncio.wait_for(self.read_body(reader), READ_TIMEOUT)
            result = await asyncio.wait_for(self.redeem(host, body), VERIFY_TIMEOUT)
            status, response = 200, result
        except HTTPException as error:
            status, response = error.status_code, {'detail': error.detail}
        except asyncio.TimeoutError:
            status, response = 408, {'detail': 'Pairing took too long. Keep your camera open and scan again.'}
        except (ValueError, UnicodeError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            status, response = 400, {'detail': 'Invalid pairing request. Scan the Mac QR again.'}
        except asyncio.CancelledError:
            raise
        except Exception:
            status, response = 503, {'detail': 'Could not connect this phone. Keep its camera open and try again.'}
        finally:
            # Write below only after a complete bounded request. No access logs or CORS.
            if 'response' in locals():
                payload = json.dumps(response).encode()
                try:
                    writer.write(f'HTTP/1.1 {status} Response\r\nContent-Type: application/json\r\nContent-Length: {len(payload)}\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n'.encode()+payload)
                    await asyncio.wait_for(writer.drain(), 1)
                except (OSError, asyncio.TimeoutError, asyncio.CancelledError): pass
            writer.close()
            self.connections.discard(task)
