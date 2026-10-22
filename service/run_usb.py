"""Local Mac host. Wireless hotspot is the default; USB is an optional adapter."""
import asyncio
from contextlib import asynccontextmanager, suppress
import json
import hashlib
import math
import os
from pathlib import Path
import re
import secrets
import struct
import time

PORT = 8870
ORIGIN = f'http://127.0.0.1:{PORT}'
PULL_INTERVAL = .05
ACK_TIMEOUT = 1
RECONNECT_DELAYS = (.2, .5, 1, 2)
# This host never opens a public socket, uses Clerk, or falls back to phone AI.
os.environ.update(NIVRA_ALLOWED_ORIGINS=ORIGIN, NIVRA_AUTH_MODE='dev',
    NIVRA_PUBLIC_ORIGIN='', NIVRA_SOCKET_ORIGIN='', NIVRA_AUTO_RELAY='0',
    NIVRA_DEVICE='cpu', NIVRA_PERSON_MODEL='rtmo', NIVRA_FIGHT_MODEL='x3d')

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from websockets.asyncio.client import connect
from nivra.classroom import ADMIN_COOKIE, CAMERA_COOKIE, digest
from nivra.auth import DEV_COOKIE
from nivra.local_pairing import PairingBroker
from nivra.server import ROOT, create_app
WIRELESS = os.environ.get('NIVRA_CONNECTION', 'wireless') != 'usb'
if WIRELESS:
    from nivra.lan_transport import list_devices, phone_get, from_host, start, close
else:
    from nivra.usb_transport import list_devices, phone_get


class ConnectPhone(BaseModel):
    model_config = ConfigDict(extra='forbid')
    deviceId: str | None = Field(default=None, pattern=r'^[a-f0-9]{24}$')
    host: str | None = Field(default=None, max_length=15)
    hosts: list[str] = Field(default_factory=list, max_length=8)
    code: str = Field(min_length=8, max_length=12)
    name: str = Field(default='', max_length=60)
    floor: str = Field(default='', max_length=60)

    @model_validator(mode='after')
    def source(self):
        if bool(self.deviceId) == bool(self.host):
            raise ValueError('Choose a nearby phone or scan its QR.')
        if self.hosts and not self.host:
            raise ValueError('Scan the phone QR again.')
        if self.host:
            if not WIRELESS: raise ValueError('Use wireless camera mode.')
            for host in [self.host, *self.hosts]: from_host(host)
        return self


async def phone_status(device, code):
    """Use the reachable interface whether pairing came from discovery or QR."""
    if not WIRELESS:
        _, payload = await asyncio.to_thread(phone_get, device, code, '/v1/status')
        status = json.loads(payload)
        if not isinstance(status, dict): raise ValueError('Invalid phone status')
        return device, status
    deadline, denied = time.monotonic()+8, False
    for host in dict.fromkeys([device['host'], *device.get('hosts', [])]):
        if time.monotonic() >= deadline: break
        candidate = {**device, **from_host(host), 'id': device['id']}
        try:
            _, payload = await asyncio.wait_for(asyncio.to_thread(phone_get, candidate, code, '/v1/status'),
                timeout=min(4, deadline-time.monotonic()))
            status = json.loads(payload)
            if not isinstance(status, dict): raise ValueError('Invalid phone status')
            return candidate, status
        except PermissionError: denied = True
        except Exception: pass
    if denied: raise PermissionError('Check the phone code.')
    raise OSError('Join the same hotspot on your Mac and phone, then scan again.')


class USBPhones:
    def __init__(self, classroom):
        self.classroom = classroom
        self.links = {}
        self.lock = asyncio.Lock()
        with classroom.store.db:
            classroom.store.db.execute('CREATE TABLE IF NOT EXISTS usb_phones(device_id TEXT PRIMARY KEY, camera_id TEXT NOT NULL)')
        for row in classroom.store.db.execute('SELECT device_id,camera_id FROM usb_phones'):
            camera = classroom.store.camera(row['camera_id'])
            if camera:
                self.links[row['device_id']] = dict(cameraId=camera['id'], name=camera['name'],
                    state='waiting', detail='Open the phone camera and enter its code again.', task=None)

    async def devices(self):
        try:
            return await asyncio.to_thread(list_devices)
        except OSError:
            raise HTTPException(503, 'Join the same hotspot as your phones, then try again.') from None

    async def remove(self, identity):
        link = self.links.pop(identity, None)
        if not link:
            raise HTTPException(404, 'Phone is already disconnected.')
        if link['task']:
            link['task'].cancel()
            with suppress(asyncio.CancelledError):
                await link['task']
        if self.classroom.store.camera(link['cameraId']):
            self.classroom.store.delete_camera(link['cameraId'])
        await self.classroom.disconnect_camera(link['cameraId'])
        with self.classroom.store.db:
            self.classroom.store.db.execute('DELETE FROM usb_phones WHERE device_id=?', (identity,))
        await self.classroom.broadcast(self.classroom.snapshot())

    async def stop(self):
        tasks = [link['task'] for link in self.links.values() if link['task']]
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def attach(self, data):
        code = re.sub(r'[\s-]', '', data.code).upper()
        if not re.fullmatch(r'[A-Z0-9]{8}', code):
            raise HTTPException(422, 'Enter the eight-character code shown on the phone.')
        async with self.lock:
            # QR can reach a phone even when the hotspot filters Bonjour.
            device = None
            status = None
            if data.host:
                device = {**from_host(data.host), 'hosts': data.hosts}
            else:
                device = next((d for d in await self.devices() if d['id'] == data.deviceId), None)
            if not device:
                raise HTTPException(404, 'Open the phone camera and join the same hotspot.')
            identity = device['id']
            prior = self.links.get(identity)
            if prior and prior['task'] and not prior['task'].done():
                raise HTTPException(409, 'This phone is already connected.')
            try:
                device, status = await phone_status(device, code)
            except PermissionError:
                raise HTTPException(403, 'Check the code shown on the phone.') from None
            except Exception:
                raise HTTPException(409, 'Open NIVRA on the phone and tap Start camera.') from None
            native_id = status.get('deviceId')
            if isinstance(native_id, str) and re.fullmatch(r'NIVRA-[a-f0-9]{12}', native_id):
                identity = hashlib.sha256(native_id.encode()).hexdigest()[:24]
                device = {**device, 'id': identity}
                prior = self.links.get(identity)
                if prior and prior['task'] and not prior['task'].done():
                    raise HTTPException(409, 'This phone is already connected.')
            name = data.name.strip() or str(status.get('name') or 'Camera')[:60]
            try:
                camera = self.classroom.store.camera(prior['cameraId']) if prior else None
                if camera:
                    camera = self.classroom.store.patch_camera(camera['id'], name=name, floor=data.floor.strip() or camera['floor'], enabled=True)
                else:
                    camera = self.classroom.store.add_camera(name, 'This Mac', data.floor.strip() or 'Not set')
            except ValueError:
                raise HTTPException(409, 'Could not add another camera. Remove an old camera first.') from None
            link = dict(cameraId=camera['id'], name=name, state='waiting', detail='Starting camera…', device=device)
            self.links[identity] = link
            with self.classroom.store.db:
                self.classroom.store.db.execute('INSERT OR REPLACE INTO usb_phones VALUES(?,?)', (identity, camera['id']))
            link['task'] = asyncio.create_task(self.pump(identity, code, link))
            await self.classroom.broadcast(self.classroom.snapshot())
            return {'cameraId': camera['id'], 'name': name}


    async def pump(self, identity, code, link):
        credential = secrets.token_urlsafe(32)
        key = digest(credential)
        self.classroom.store.save_device_session(key, 'camera', link['cameraId'], time.time()+30*86400)
        self.classroom.credentials[key] = link['cameraId']
        failures = 0
        try:
            while self.classroom.store.camera(link['cameraId']):
                try:
                    device = next((d for d in await self.devices() if d['id'] == identity), None) or link.get('device')
                    if not device:
                        raise OSError('Join the same hotspot and keep NIVRA open on the phone.')
                    if WIRELESS:
                        device, _ = await phone_status(device, code)
                        link['device'] = device
                    async with connect(f'ws://127.0.0.1:{PORT}/api/v2/camera/stream',
                            origin=ORIGIN, additional_headers={'Cookie': f'{CAMERA_COOKIE}={credential}'},
                            open_timeout=4, close_timeout=1, max_size=1_500_000) as peer:
                        ready = json.loads(await asyncio.wait_for(peer.recv(), 3))
                        if ready.get('type') != 'ready': raise OSError('Camera connection not ready.')
                        last, last_timestamp = -1, -1
                        while self.classroom.store.camera(link['cameraId']):
                            started = time.monotonic()
                            headers, jpeg = await asyncio.to_thread(phone_get, device, code, '/v1/frame')
                            fields = {k.lower(): v for k, v in headers.items()}
                            sequence = int(fields['x-nivra-sequence'])
                            timestamp = float(fields['x-nivra-timestamp'])
                            if sequence < 0 or not math.isfinite(timestamp) or timestamp < 0:
                                raise OSError('Phone sent invalid frame metadata.')
                            if sequence > last and timestamp > last_timestamp:
                                if len(jpeg) > 1_400_000 or not jpeg.startswith(b'\xff\xd8'):
                                    raise OSError('Phone sent an invalid camera frame.')
                                metadata = json.dumps(dict(version=1, timestampMs=timestamp,
                                    streamId=0, maxPeople=32)).encode()
                                await asyncio.wait_for(peer.send(struct.pack('<I', len(metadata))+metadata+jpeg), ACK_TIMEOUT)
                                acknowledgement = json.loads(await asyncio.wait_for(peer.recv(), ACK_TIMEOUT))
                                if acknowledgement.get('type') != 'accepted' or acknowledgement.get('timestampMs') != timestamp:
                                    raise OSError('Camera frame was not accepted.')
                                last, last_timestamp, failures = sequence, timestamp, 0
                                link.update(state='live', detail='Connected locally' if WIRELESS else 'Connected by USB')
                            await asyncio.sleep(max(.001, PULL_INTERVAL-(time.monotonic()-started)))
                except PermissionError:
                    link.update(state='error', detail='Tap Connect and enter the new code shown on the phone.')
                    break
                except asyncio.CancelledError:
                    raise
                except Exception:
                    link.update(state='reconnecting', detail='Join the same hotspot and keep the phone camera open.')
                    delay = RECONNECT_DELAYS[min(failures, len(RECONNECT_DELAYS)-1)]
                    failures += 1
                    await asyncio.sleep(delay)
        finally:
            self.classroom.credentials.pop(key, None)
            self.classroom.store.revoke_device_sessions(kind='camera', token_hash=key)


def make_app(database=None):
    app = create_app(database=database or Path(__file__).parent/'state'/('local.sqlite' if WIRELESS else 'usb.sqlite'), static_dir=ROOT/'dist-usb')
    classroom = app.state.classroom
    phones = USBPhones(classroom)
    app.state.usb = phones
    async def attach_native(host, code):
        return await phones.attach(ConnectPhone(host=host, code=code))
    broker = PairingBroker(attach_native, valid_result=lambda result:
        bool((camera := classroom.store.camera(result['cameraId'])) and camera['enabled']))
    app.state.local_pairing = broker
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with original_lifespan(application):
            if WIRELESS:
                try: await asyncio.to_thread(start)
                except OSError:
                    # QR reaches the phone directly when multicast is unavailable.
                    pass
            if WIRELESS:
                try: await broker.start()
                except OSError: pass  # Keep manual local pairing usable if port8871 is occupied.
            try:
                yield
            finally:
                await broker.close()
                await phones.stop()
                if WIRELESS: await asyncio.to_thread(close)
    app.router.lifespan_context = lifespan
    routes = APIRouter()

    def local(request):
        if request.client.host not in ('127.0.0.1', '::1', 'testclient'):
            raise HTTPException(403, 'Use NIVRA on this Mac.')
        origin = request.headers.get('origin')
        if origin and origin != ORIGIN:
            raise HTTPException(403, 'Open NIVRA on this Mac.')
        if request.headers.get('sec-fetch-site') not in (None, 'same-origin', 'none'):
            raise HTTPException(403, 'Open NIVRA on this Mac.')
        if request.method != 'GET' and origin != ORIGIN:
            raise HTTPException(403, 'Open NIVRA on this Mac.')

    @routes.get('/')
    async def home():
        return RedirectResponse('/local')

    @routes.get('/usb')
    @routes.get('/local')
    async def setup():
        return FileResponse(ROOT/'dist-usb'/'index.html', headers={'Cache-Control': 'no-store'})

    @routes.post('/api/local/invite')
    async def invite(request: Request):
        local(request)
        return broker.invite()

    @routes.get('/api/usb/config')
    @routes.get('/api/local/config')
    async def config(request: Request, response: Response):
        local(request)
        operator_session(response)
        return {'enabled': True, 'transport': 'wireless' if WIRELESS else 'usb'}

    def operator_session(response):
        # Cookies are shared across localhost ports. An expired session from a
        # different NIVRA host must not shadow this Mac's local operator cookie.
        response.delete_cookie(DEV_COOKIE, path='/api/v2')
        response.set_cookie(ADMIN_COOKIE, classroom.admin_token, httponly=True,
            samesite='strict', path='/api/v2')

    @routes.get('/api/usb/devices')
    @routes.get('/api/local/devices')
    async def devices(request: Request, response: Response):
        local(request)
        # An already-open setup page also recovers after the Mac host restarts.
        operator_session(response)
        found = {d['id']: d for d in await phones.devices()}
        values = []
        for identity in found.keys() | phones.links.keys():
            link = phones.links.get(identity)
            values.append(dict(id=identity, name=link['name'] if link else found[identity]['name'],
                connected=identity in found or bool(link and link['state'] == 'live'), linked=bool(link and link['task'] and not link['task'].done()), cameraId=link['cameraId'] if link else None,
                state=link['state'] if link else 'waiting', detail=link['detail'] if link else 'Open NIVRA on this phone.'))
        state = classroom.state
        return {'devices': values, 'analysis': {'status': 'error' if state['error'] else 'ready' if state['models'] else 'loading',
            'detail': 'Analysis unavailable on this Mac.' if state['error'] else 'Analysis runs on this Mac.' if state['models'] else 'Starting detection on this Mac…'}}

    @routes.post('/api/usb/connect')
    @routes.post('/api/local/connect')
    async def attach(data: ConnectPhone, request: Request):
        local(request)
        return await phones.attach(data)

    @routes.delete('/api/usb/devices/{identity}', status_code=204)
    @routes.delete('/api/local/devices/{identity}', status_code=204)
    async def remove(identity: str, request: Request):
        local(request)
        async with phones.lock:
            await phones.remove(identity)
        return Response(status_code=204)

    # Keep the existing SPA catch-all after these local-only routes.
    static = app.router.routes.pop()
    app.include_router(routes)
    app.router.routes.append(static)
    return app


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(make_app(), host='127.0.0.1', port=PORT, access_log=False,
        ws_max_size=1_500_000)
