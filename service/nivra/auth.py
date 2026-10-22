"""NIVRA identity boundary. Clerk I/O is isolated for deterministic offline tests.

HTTP verification runs in a worker thread via AuthMiddleware; socket verification
does likewise. Dev members/sessions are process-local and never create Clerk users.
"""
import asyncio
import base64
from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import secrets
import threading
import time
from urllib.parse import quote, urlsplit

import httpx
import jwt
from fastapi import HTTPException, Request, Response, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.responses import JSONResponse

DEFAULT_ORIGINS = {'http://127.0.0.1:8765', 'http://localhost:8765'}
ROLES = frozenset(('admin', 'reviewer', 'guard'))
DEV_COOKIE = 'nivra_dev'
WS_AUTH_TIMEOUT = 5.0
WS_REAUTH_SECONDS = 50.0


def allowed_origins(public=''):
    values = os.environ.get('NIVRA_ALLOWED_ORIGINS')
    origins = {v.strip().rstrip('/') for v in values.split(',') if v.strip()} if values is not None else set(DEFAULT_ORIGINS)
    if public: origins.add(public)
    for origin in origins:
        parsed = urlsplit(origin)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            raise ValueError('NIVRA_ALLOWED_ORIGINS must contain exact HTTP(S) origins.')
    return origins


def local_demo_host(host):
    if host in ('localhost', 'nivra.local'): return True
    try:
        address = ipaddress.ip_address(host)
        return address.is_loopback or address.is_private and not address.is_unspecified
    except ValueError:
        return False


@dataclass(frozen=True)
class Principal:
    user_id: str
    email: str | None
    name: str
    role: str | None
    auth_mode: str
    callsign: str | None = None
    expires_at: float = float('inf')

    def payload(self, callsign=None):
        return dict(userId=self.user_id, email=self.email, name=self.name, role=self.role,
                    authMode=self.auth_mode, guard={'callsign': callsign or self.callsign} if self.role == 'guard' and (callsign or self.callsign) else None)


class ClerkClient:
    """Only Clerk HTTP adapter. Never logs tokens, secrets, or response bodies."""
    def __init__(self, secret='', transport=None):
        self.secret, self.transport = secret, transport

    def request(self, method, path, *, json=None, params=None):
        try:
            with httpx.Client(timeout=5, transport=self.transport) as client:
                response = client.request(method, 'https://api.clerk.com/v1'+path,
                    headers={'Authorization': 'Bearer '+self.secret}, json=json, params=params)
                response.raise_for_status()
                return response.json() if response.content else {}
        except (httpx.HTTPError, ValueError) as error:
            raise HTTPException(503, 'Identity provider unavailable') from error

    def jwks(self, url):
        try:
            with httpx.Client(timeout=5, transport=self.transport) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise HTTPException(503, 'Identity keys unavailable') from error

    def user(self, user_id):
        return self.request('GET', '/users/'+quote(user_id, safe=''))

    def users(self):
        users, offset = [], 0
        while True:
            page = self.request('GET', '/users', params={'limit': 100, 'offset': offset})
            users.extend(page)
            if len(page) < 100: return users
            offset += len(page)

    def invite(self, email, role, callsign, origin):
        metadata = {'role': role}
        if callsign: metadata['callsign'] = callsign
        return self.request('POST', '/invitations', json={'email_address': email,
            'public_metadata': metadata, 'redirect_url': origin+('/guard' if role == 'guard' else '/login')})

    def set_role(self, user_id, role):
        return self.request('PATCH', '/users/'+quote(user_id, safe='')+'/metadata', json={'public_metadata': {'role': role}})

    def revoke_sessions(self, user_id):
        # Fetch before revoking: mutating while paging would skip active sessions.
        sessions, offset = [], 0
        while True:
            page = self.request('GET', '/sessions', params={'user_id': user_id, 'status': 'active', 'limit': 100, 'offset': offset})
            sessions.extend(page)
            if len(page) < 100: break
            offset += len(page)
        for session in sessions:
            self.request('POST', '/sessions/'+quote(session['id'], safe='')+'/revoke')


def user_fields(user):
    primary = user.get('primary_email_address_id')
    emails = user.get('email_addresses') or []
    email = next((e.get('email_address') for e in emails if e.get('id') == primary), None)
    # Bootstrap uses only the verified primary address.
    verified = any(e.get('id') == primary and (e.get('verification') or {}).get('status') == 'verified' for e in emails)
    name = ' '.join(str(user.get(k) or '') for k in ('first_name', 'last_name')).strip() or user.get('username') or email or user['id']
    return email, name, verified


class AuthService:
    def __init__(self, origins, client=None):
        self.mode = os.environ.get('NIVRA_AUTH_MODE', 'clerk' if os.environ.get('CLERK_SECRET_KEY') else 'dev').lower()
        if self.mode not in ('dev', 'clerk'): raise ValueError('NIVRA_AUTH_MODE must be dev or clerk.')
        self.origins = origins
        self.issuer = os.environ.get('CLERK_ISSUER', '').rstrip('/')
        self.jwks_url = os.environ.get('CLERK_JWKS_URL') or (self.issuer+'/.well-known/jwks.json' if self.issuer else '')
        self.parties = {v.strip().rstrip('/') for v in os.environ.get('NIVRA_AUTHORIZED_PARTIES', ','.join(sorted(origins))).split(',') if v.strip()}
        self.admin_emails = {v.strip().lower() for v in os.environ.get('NIVRA_ADMIN_EMAILS', '').split(',') if v.strip()}
        self.client = client or ClerkClient(os.environ.get('CLERK_SECRET_KEY', ''))
        self.secret = (os.environ.get('NIVRA_DEV_SECRET') or secrets.token_urlsafe(48)).encode()
        self._keys, self._keys_at, self._refresh_at = {}, float('-inf'), float('-inf')
        self._key_lock, self._user_lock = threading.Lock(), threading.Lock()
        self._users = OrderedDict()
        self.members, self.invalid_before, self.removed_users = {}, {}, set()
        self.dev_sessions = {}

    def log_mode(self):
        logging.getLogger(__name__).warning('NIVRA authentication mode: %s', self.mode)

    def _key(self, kid):
        with self._key_lock:
            now = time.monotonic()
            if now-self._keys_at >= 300 or kid not in self._keys:
                # Also rate-limit failures and attacker-controlled unknown kids.
                if now-self._refresh_at >= 5:
                    self._refresh_at = now
                    document = self.client.jwks(self.jwks_url)
                    keys = {}
                    try:
                        for item in document['keys']:
                            if item.get('kty') == 'RSA' and item.get('use', 'sig') == 'sig' and item.get('alg', 'RS256') == 'RS256':
                                keys[item['kid']] = jwt.PyJWK.from_dict(item, algorithm='RS256').key
                    except (KeyError, TypeError, ValueError, jwt.PyJWTError) as error:
                        raise HTTPException(503, 'Identity keys unavailable') from error
                    self._keys, self._keys_at = keys, now
            if now-self._keys_at >= 300 or kid not in self._keys:
                raise HTTPException(401, 'Unknown signing key')
            return self._keys[kid]

    def user(self, user_id):
        with self._user_lock:
            now = time.monotonic()
            cached = self._users.get(user_id)
            if cached and cached[0] > now: return cached[1]
            user = self.client.user(user_id)
            self._users[user_id] = (now+60, user)
            self._users.move_to_end(user_id)
            while len(self._users) > 512: self._users.popitem(last=False)
            return user

    def verify(self, token):
        if not self.issuer or not self.jwks_url:
            raise HTTPException(503, 'Configure CLERK_ISSUER and Clerk signing keys')
        try:
            if not isinstance(token, str) or len(token) > 16384: raise ValueError()
            header = jwt.get_unverified_header(token)
            if header.get('alg') != 'RS256' or not isinstance(header.get('kid'), str): raise ValueError()
            claims = jwt.decode(token, self._key(header['kid']), algorithms=['RS256'],
                issuer=self.issuer, leeway=5, options={'require': ['sub', 'exp', 'nbf', 'iss', 'azp'], 'verify_aud': False})
            if not claims['sub'] or claims['azp'] not in self.parties: raise ValueError()
            if claims['sub'] in self.removed_users: raise HTTPException(403, 'NIVRA role required')
            if claims.get('iat', 0) <= self.invalid_before.get(claims['sub'], -1):
                raise HTTPException(401, 'Refresh your session')
            metadata = claims.get('metadata') or {}
            role, callsign = metadata.get('role'), metadata.get('callsign')
            email, name = claims.get('email') or claims.get('email_address'), claims.get('name') or claims['sub']
            if ('role' not in metadata or (self.admin_emails and not role)
                    or (role == 'guard' and not callsign) or (role in ROLES and (not email or not claims.get('name')))):
                user = self.user(claims['sub'])
                public = user.get('public_metadata') or {}
                if 'role' not in metadata: role = public.get('role')
                callsign = callsign or public.get('callsign')
                email, name, verified = user_fields(user)
                if not role and verified and email and email.lower() in self.admin_emails: role = 'admin'
            if role not in ROLES: role = None
            if not isinstance(callsign, str) or not re.fullmatch(r'G[0-9]{1,2}', callsign): callsign = None
            return Principal(claims['sub'], email, name, role, 'clerk', callsign, float(claims['exp'])+5)
        except (jwt.PyJWTError, ValueError, TypeError, KeyError, AttributeError) as error:
            raise HTTPException(401, 'Invalid or expired session') from error

    def origin_check(self, request):
        origin = request.headers.get('origin')
        read = request.scope.get('method') == 'GET' and origin is None and request.headers.get('sec-fetch-site') in ('same-origin', None)
        if not (read or origin in self.origins): raise HTTPException(403, 'Origin rejected')

    def dev_only(self):
        if self.mode != 'dev': raise HTTPException(404, 'Not found')

    def dev_host(self, request):
        origin = request.headers.get('origin', '')
        host = urlsplit(origin).hostname or ''
        if origin not in self.origins or not local_demo_host(host) or request.headers.get('host') != urlsplit(origin).netloc or any(h in request.headers for h in ('forwarded', 'x-forwarded-for', 'x-forwarded-host', 'x-forwarded-proto', 'x-nivra-relay')):
            raise HTTPException(403, 'Developer sign-in requires an allowed local demo host')

    def dev_token(self, user_id):
        expires = time.time()+8*3600
        payload = base64.urlsafe_b64encode(json.dumps({'sub': user_id, 'exp': expires, 'sid': secrets.token_hex(16)}, separators=(',', ':')).encode()).decode().rstrip('=')
        token = payload+'.'+hmac.new(self.secret, payload.encode(), hashlib.sha256).hexdigest()
        self.dev_sessions = {key: exp for key, exp in self.dev_sessions.items() if exp > time.time()}
        if len(self.dev_sessions) >= 512: raise HTTPException(429, 'Developer session limit reached')
        self.dev_sessions[hashlib.sha256(token.encode()).hexdigest()] = expires
        return token

    def dev_principal(self, request):
        value = request.cookies.get(DEV_COOKIE, '')
        if not value: return None
        try:
            if len(value) > 2048 or hashlib.sha256(value.encode()).hexdigest() not in self.dev_sessions: raise ValueError()
            payload, signature = value.split('.')
            if not hmac.compare_digest(signature, hmac.new(self.secret, payload.encode(), hashlib.sha256).hexdigest()): raise ValueError()
            data = json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload) % 4)))
            member = self.members[data['sub']]
            if data['exp'] <= time.time() or member['role'] not in ROLES: raise ValueError()
            return Principal(member['userId'], member['email'], member['name'], member['role'], 'dev', member['guardCallsign'], data['exp'])
        except (ValueError, TypeError, KeyError):
            raise HTTPException(401, 'Invalid or expired developer session')

    def principal(self, request):
        if self.mode == 'dev': return self.dev_principal(request)
        error = request.scope.get('nivra.auth_error')
        if error: raise error
        return request.scope.get('nivra.principal')

    def require(self, request, roles=ROLES):
        self.origin_check(request)
        principal = self.principal(request)
        if principal is None: raise HTTPException(401, 'Sign in required')
        if principal.role not in roles: raise HTTPException(403, 'NIVRA role required')
        return principal

    def member(self, user):
        email, name, _ = user_fields(user)
        metadata = user.get('public_metadata') or {}
        return dict(userId=user['id'], email=email, name=name, role=metadata.get('role'),
                    guardCallsign=metadata.get('callsign'), lastActiveAt=user.get('last_active_at'))

    def changed(self, user_id, removed=False):
        with self._user_lock:
            self._users.pop(user_id, None)
        self.invalid_before[user_id] = time.time()
        if removed: self.removed_users.add(user_id)
        else: self.removed_users.discard(user_id)

    async def invite_member(self, *, email, role, callsign=None, origin=None):
        """Site-registry invitation hook; no external calls in dev mode."""
        if self.mode == 'dev':
            member = next((m for m in self.members.values() if m['email'] == email), None)
            if member is None:
                member = dict(userId='dev_'+secrets.token_hex(12), email=email, name=email,
                              role=role, guardCallsign=callsign, lastActiveAt=None)
                self.members[member['userId']] = member
            return dict(invitationId=None, status='created', member=member)
        origin = origin or os.environ.get('NIVRA_PUBLIC_ORIGIN', '').rstrip('/') or sorted(self.origins)[0]
        if origin not in self.origins: raise HTTPException(403, 'Invitation origin rejected')
        result = await asyncio.to_thread(self.client.invite, email, role, callsign, origin)
        return dict(invitationId=result['id'], status=result.get('status', 'pending'), member=None)


class AuthMiddleware:
    def __init__(self, app, auth):
        self.app, self.auth = app, auth

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http' and scope['path'].startswith('/api/v2/') and self.auth.mode == 'clerk':
            authorization = dict(scope.get('headers', [])).get(b'authorization', b'').decode('latin1')
            if authorization:
                try:
                    scheme, token = authorization.split(' ', 1)
                    if scheme.lower() != 'bearer': raise HTTPException(401, 'Bearer session required')
                    scope['nivra.principal'] = await asyncio.to_thread(self.auth.verify, token)
                except ValueError:
                    scope['nivra.auth_error'] = HTTPException(401, 'Bearer session required')
                except HTTPException as error:
                    scope['nivra.auth_error'] = error
        await self.app(scope, receive, send)


class SocketAuth:
    """Handshake accepts the socket. Call check() and consume(message) in the loop.

    timeout bounds every receive. consume returns True for auth controls, False
    for application messages, and raises WebSocketDisconnect after closing on
    auth failure. Optional resolve(principal) links a guard record on every auth.
    """
    def __init__(self, auth, socket, roles, legacy=None, resolve=None):
        self.auth, self.socket, self.roles = auth, socket, roles
        self.legacy, self.resolve = legacy, resolve
        self.principal, self.identity = None, None
        self.deadline = float('inf')

    async def fail(self, code):
        await self.socket.close(code=code, reason='Sign in required' if code == 4401 else 'Role or origin rejected')
        raise WebSocketDisconnect(code)

    async def set_principal(self, principal):
        if principal is None: await self.fail(4401)
        if principal.role not in self.roles: await self.fail(4403)
        if self.principal and principal.user_id != self.principal.user_id: await self.fail(4403)
        try:
            identity = self.resolve(principal) if self.resolve else None
        except HTTPException:
            await self.fail(4403)
        if self.resolve and not identity: await self.fail(4403)
        if self.identity and self.identity != identity: await self.fail(4403)
        self.principal, self.identity = principal, identity
        remaining = principal.expires_at-time.time()
        if remaining <= 0: await self.fail(4401)
        self.deadline = time.monotonic()+min(WS_REAUTH_SECONDS if self.auth.mode == 'clerk' else remaining, remaining)

    async def handshake(self):
        if self.socket.headers.get('origin') not in self.auth.origins: await self.fail(4403)
        if self.auth.mode == 'dev':
            try: principal = self.auth.dev_principal(self.socket)
            except HTTPException: await self.fail(4401)
            if principal is None and self.legacy: principal = self.legacy()
            await self.set_principal(principal)
            await self.socket.accept()
        else:
            await self.socket.accept()
            try: message = await asyncio.wait_for(self.socket.receive(), WS_AUTH_TIMEOUT)
            except asyncio.TimeoutError: await self.fail(4401)
            if not await self.consume(message): await self.fail(4401)
        return self

    @property
    def timeout(self):
        return max(.001, self.deadline-time.monotonic())

    async def check(self):
        if time.monotonic() >= self.deadline: await self.fail(4401)
        if self.auth.mode == 'dev':
            try: principal = self.auth.dev_principal(self.socket)
            except HTTPException: await self.fail(4401)
            if principal is None and self.legacy: principal = self.legacy()
            await self.set_principal(principal)
        elif self.principal.user_id in self.auth.removed_users:
            await self.fail(4403)
        elif self.principal.user_id in self.auth.invalid_before:
            # The next token must be minted after a local role change.
            if self.auth.invalid_before[self.principal.user_id] > getattr(self, 'verified_at', 0): await self.fail(4401)

    async def consume(self, message):
        if message['type'] == 'websocket.disconnect': raise WebSocketDisconnect(message.get('code', 1000))
        text = message.get('text', '')
        if text == 'ping': return False
        try:
            if len(text) > 18000: raise ValueError()
            control = json.loads(text)
            if not isinstance(control, dict) or control.get('type') != 'auth': return False
            if self.auth.mode == 'dev':
                await self.check()
            else:
                principal = await asyncio.to_thread(self.auth.verify, control.get('token'))
                await self.set_principal(principal)
                self.verified_at = time.time()
            return True
        except HTTPException as error:
            await self.fail(4403 if error.status_code == 403 else 4401)
        except (ValueError, TypeError):
            await self.fail(4401)


class DevInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: str = Field(pattern='^(admin|reviewer|guard)$')
    name: str = Field(min_length=1, max_length=80)

    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        if not value.strip() or any(ord(c) < 32 for c in value): raise ValueError('Enter a name.')
        return value.strip()


class RoleInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: str = Field(pattern='^(admin|reviewer|guard)$')


class InviteInput(RoleInput):
    email: str = Field(min_length=3, max_length=254, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    callsign: str | None = Field(default=None, pattern=r'^G[0-9]{1,2}$')


def require_role(role):
    """FastAPI dependency shared with the site registry (admin implies reviewer)."""
    async def dependency(request: Request):
        classroom = request.app.state.classroom
        return classroom.require_principal(request, ('reviewer', 'admin') if role == 'reviewer' else (role,))
    return dependency


def install_routes(classroom):
    auth, router = classroom.auth, classroom.router

    @router.get('/me')
    async def me(request: Request):
        principal = classroom.require_principal(request, ROLES)
        callsign = classroom.guard_for_principal(principal) if principal.role == 'guard' else None
        return principal.payload(callsign)

    @router.post('/auth/dev')
    async def dev_login(request: Request):
        auth.dev_only()
        auth.dev_host(request)
        try: data = DevInput.model_validate(await request.json())
        except ValueError as error: raise HTTPException(422, 'Invalid developer sign-in') from error
        existing = next((m for m in auth.members.values() if m['name'] == data.name and m['role'] == data.role), None)
        user_id = existing['userId'] if existing else 'dev_'+secrets.token_hex(12)
        callsign = (data.name.upper() if re.fullmatch(r'G[0-9]{1,2}', data.name.upper()) else 'G1') if data.role == 'guard' else None
        if existing and data.role == 'guard': callsign = existing['guardCallsign'] or callsign
        email = existing['email'] if existing else None
        auth.members[user_id] = dict(userId=user_id, email=email, name=data.name, role=data.role,
                                    guardCallsign=callsign, lastActiveAt=int(time.time()*1000))
        principal = Principal(user_id, email, data.name, data.role, 'dev', callsign)
        response = JSONResponse(principal.payload())
        response.set_cookie(DEV_COOKIE, auth.dev_token(user_id), httponly=True, samesite='strict',
                            secure=request.headers['origin'].startswith('https:'), path='/api/v2', max_age=8*3600)
        return response

    @router.post('/auth/dev/logout')
    async def dev_logout(request: Request):
        auth.dev_only()
        auth.origin_check(request)
        auth.dev_sessions.pop(hashlib.sha256(request.cookies.get(DEV_COOKIE, '').encode()).hexdigest(), None)
        response = Response(status_code=204)
        response.delete_cookie(DEV_COOKIE, path='/api/v2')
        return response

    @router.get('/members')
    async def members(request: Request):
        classroom.require_admin(request)
        if auth.mode == 'dev': return list(auth.members.values())
        return [auth.member(user) for user in await asyncio.to_thread(auth.client.users)
                if (user.get('public_metadata') or {}).get('role') in ROLES]

    @router.post('/members/invite', status_code=201)
    async def invite(data: InviteInput, request: Request):
        classroom.require_admin(request)
        if data.role == 'guard' and not data.callsign: raise HTTPException(422, 'Guard callsign required')
        return await auth.invite_member(email=data.email, role=data.role, callsign=data.callsign, origin=request.headers['origin'])

    @router.patch('/members/{user_id}')
    async def patch_member(user_id: str, data: RoleInput, request: Request):
        classroom.require_admin(request)
        if auth.mode == 'dev':
            if user_id not in auth.members: raise HTTPException(404, 'Member not found')
            auth.members[user_id]['role'] = data.role
            return auth.members[user_id]
        result = await asyncio.to_thread(auth.client.set_role, user_id, data.role)
        auth.changed(user_id)
        return auth.member(result)

    @router.delete('/members/{user_id}', status_code=204)
    async def delete_member(user_id: str, request: Request):
        classroom.require_admin(request)
        if auth.mode == 'dev':
            if auth.members.pop(user_id, None) is None: raise HTTPException(404, 'Member not found')
        else:
            await asyncio.to_thread(auth.client.set_role, user_id, None)
            auth.changed(user_id, removed=True)
            await asyncio.to_thread(auth.client.revoke_sessions, user_id)
        return Response(status_code=204)
