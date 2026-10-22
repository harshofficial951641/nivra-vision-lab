"""Private self-service pilot workspaces, isolated behind the public relay.

Each guest keeps the existing classroom API in its own app/database. Owner and
paired-device capabilities persist only as hashes, scoped to that workspace.
"""
import asyncio
from collections import deque
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time

from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse, Response

from .classroom import ADMIN_COOKIE, CAMERA_COOKIE, GUARD_COOKIE, DevicePairInput, PairCodeAttempts, digest
from .sites import NameInput

OWNER_DAYS = 30
PAIR_PATHS = {'/api/v2/camera/pair': 'pairs', '/api/v2/guard/pair': 'guard_pairs',
              '/api/v2/operator/redeem': 'operator_invites'}
FRAME = re.compile(r'^/api/v2/events/([0-9a-f-]{36})/clip/frames/[0-9]+$')
PLAN = re.compile(r'^/api/v2/files/plan/([0-9a-f-]{36})$')


class Workspaces:
    def __init__(self, primary, directory, *, limit=32, app_factory=None):
        self.primary, self.directory, self.limit = primary, Path(directory), limit
        self.directory.mkdir(parents=True, exist_ok=True)
        os.chmod(self.directory, 0o700)
        path = self.directory/'index.sqlite'
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('''CREATE TABLE IF NOT EXISTS workspaces(
            id TEXT PRIMARY KEY, owner_hash TEXT UNIQUE, expires REAL NOT NULL, created REAL NOT NULL)''')
        self.db.commit()
        os.chmod(path, 0o600)
        self.apps, self.contexts = {}, {}
        self.lock = asyncio.Lock()
        self.created = deque()
        self.code_attempts = PairCodeAttempts()
        self.app_factory = app_factory

    def all_apps(self):
        return [self.primary, *self.apps.values()]

    async def device_app(self, token, kind):
        if not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_-]{30,100}',token): return None
        key = digest(token)
        rows = self.db.execute('SELECT id FROM workspaces WHERE expires>? ORDER BY created LIMIT ?',
                               (time.time(),self.limit)).fetchall()
        allowed = {row['id'] for row in rows}
        for app in [self.primary, *(app for workspace_id,app in self.apps.items() if workspace_id in allowed)]:
            if app.state.classroom.store.device_session(key,kind): return app
        # Look only in registered, unexpired workspace files. Checking a hash
        # must not start every guest app or fall back to the primary owner.
        for row in rows:
            workspace_id = row['id']
            if workspace_id in self.apps or not re.fullmatch(r'[a-f0-9]{32}',workspace_id): continue
            path = self.directory/(workspace_id+'.sqlite')
            if not path.is_file(): continue
            try:
                with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
                    table = 'cameras' if kind == 'camera' else 'guards'
                    extra = ' AND subject.enabled=1' if kind == 'camera' else ''
                    found = db.execute(f'''SELECT 1 FROM device_sessions session
                        JOIN {table} subject ON subject.id=session.subject_id
                        WHERE session.token_hash=? AND session.kind=? AND session.expires>?{extra}''',
                        (key,kind,time.time())).fetchone()
            except sqlite3.DatabaseError:
                continue  # Pre-migration databases have no durable device credentials.
            if found:
                app = await self.load(workspace_id)
                if app.state.classroom.store.device_session(key,kind): return app
        return None

    def metadata(self, workspace_id, app):
        return dict(id=workspace_id, name=app.state.classroom.store.site()['name'], ownerVerification='unverified')

    def owner(self, token):
        if not token: return None
        return self.db.execute('SELECT * FROM workspaces WHERE owner_hash=? AND expires>?',
                               (digest(token), time.time())).fetchone()

    async def load(self, workspace_id):
        async with self.lock:
            return await self._load(workspace_id)

    async def _load(self, workspace_id):
        if workspace_id in self.apps: return self.apps[workspace_id]
        if len(self.apps) >= self.limit: raise HTTPException(429, 'This pilot is at capacity. Try again later.')
        if self.app_factory is None:
            from .server import create_app
            factory = create_app
        else: factory = self.app_factory
        app = factory(database=self.directory/(workspace_id+'.sqlite'), relay_only=True)
        # Guest apps use scoped capability sessions, never public developer login.
        app.state.classroom.auth.mode = 'dev'
        app.state.classroom.clips.max_bytes = 8*1024*1024
        context = app.router.lifespan_context(app)
        await context.__aenter__()
        self.apps[workspace_id], self.contexts[workspace_id] = app, context
        os.chmod(self.directory/(workspace_id+'.sqlite'), 0o600)
        return app

    def authorize_owner(self, app, token, row):
        app.state.classroom.operator_sessions[digest(token)] = time.monotonic()+max(0, row['expires']-time.time())

    async def create(self, request):
        if request.headers.get('origin') != self.primary.state.classroom.public:
            raise HTTPException(403, 'Origin rejected')
        try: data = NameInput.model_validate(await request.json())
        except (ValueError, ValidationError): raise HTTPException(422, 'Use a site name with 1 to 60 characters.') from None
        token = request.cookies.get(ADMIN_COOKIE, '')
        row = self.owner(token)
        if row:
            app = await self.load(row['id'])
            self.authorize_owner(app, token, row)
            return JSONResponse({'workspace': self.metadata(row['id'], app)}, headers={'Cache-Control': 'no-store'})
        async with self.lock:
            now = time.monotonic()
            while self.created and now-self.created[0] >= 60: self.created.popleft()
            if len(self.created) >= 8 or len(self.apps) >= self.limit:
                raise HTTPException(429, 'This pilot is at capacity. Try again later.')
            workspace_id, token = secrets.token_hex(16), secrets.token_urlsafe(32)
            expires = time.time()+OWNER_DAYS*86400
            app = await self._load(workspace_id)
            app.state.classroom.store.update_site(data.name)
            with self.db:
                self.db.execute('INSERT INTO workspaces VALUES(?,?,?,?)',
                                (workspace_id, digest(token), expires, time.time()))
            self.created.append(now)
            self.authorize_owner(app, token, {'expires': expires})
        response = JSONResponse({'workspace': self.metadata(workspace_id, app)}, status_code=201,
                                headers={'Cache-Control': 'no-store'})
        response.set_cookie(ADMIN_COOKIE, token, max_age=OWNER_DAYS*86400, secure=True,
                            httponly=True, samesite='strict', path='/api/v2')
        return response

    def consume(self, scope):
        # The target app is server-only metadata. PublicGateway removes the opaque
        # handshake capability before dispatching to this app's authentication.
        for app in self.all_apps():
            entry = app.state.classroom.socket_tickets.consume(scope)
            if entry is not None: return {**entry, 'target_app': app}
        return None

    async def _body(self, receive):
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] != 'http.request': raise HTTPException(400, 'Invalid request body.')
            body.extend(message.get('body', b''))
            if len(body) > 8192: raise HTTPException(413, 'Request too large.')
            if not message.get('more_body'): break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()
        return bytes(body), replay

    async def target(self, scope, receive):
        path = scope.get('path', '')
        request = HTTPConnection(scope)
        if scope['type'] == 'http' and scope['method'] == 'POST' and path in PAIR_PATHS:
            body, receive = await self._body(receive)
            attribute = PAIR_PATHS[path]
            if attribute in ('pairs', 'guard_pairs'):
                try: data = DevicePairInput.model_validate_json(body)
                except (ValueError, ValidationError): raise HTTPException(422, 'Use one valid pairing link or code.') from None
                self.code_attempts.check(request)
                kind = 'camera' if attribute == 'pairs' else 'guard'
                matches = []
                active = {row['id'] for row in self.db.execute('SELECT id FROM workspaces WHERE expires>?', (time.time(),))}
                allowed = {id(self.primary), *(id(app) for workspace_id, app in self.apps.items() if workspace_id in active)}
                for app in self.all_apps():
                    if id(app) not in allowed: continue
                    _, pair = app.state.classroom.device_pair(kind, data)
                    if pair is not None: matches.append(app)
                # A rare random-code collision must fail closed, never select an
                # arbitrary workspace based on its position or browser cookies.
                if len(matches) == 1: return matches[0], None, receive
            else:
                try: token = json.loads(body).get('token', '')
                except (ValueError, AttributeError): raise HTTPException(422, 'Invalid pairing request.') from None
                if not isinstance(token, str): raise HTTPException(422, 'Invalid pairing request.')
                key = digest(token)
                for app in self.all_apps():
                    if key in getattr(app.state.classroom, attribute): return app, None, receive
            raise HTTPException(403, 'Pairing link expired or already used. Create another link.')
        # Signed image URLs are bearer links and deliberately arrive without
        # cookies through Netlify. Resolve the UUID, then let the child verify it.
        frame, plan = FRAME.fullmatch(path), PLAN.fullmatch(path)
        if frame or plan:
            record_id = (frame or plan).group(1)
            for app in self.all_apps():
                store = app.state.classroom.store
                if (store.db.execute('SELECT 1 FROM events WHERE id=?', (record_id,)).fetchone() if frame else store.floor(record_id)):
                    return app, None, receive
            raise HTTPException(404, 'Evidence not found.')
        if path.startswith('/api/v2/camera/'):
            token = request.cookies.get(CAMERA_COOKIE, '')
            app = await self.device_app(token,'camera')
            if app: return app, None, receive
        elif path.startswith('/api/v2/guard/'):
            token = request.cookies.get(GUARD_COOKIE, '')
            app = await self.device_app(token,'guard')
            if app: return app, None, receive
            # Clerk uses bearer sessions; the primary app still verifies them.
            if request.headers.get('authorization'): return self.primary, None, receive
        else:
            token = request.cookies.get(ADMIN_COOKIE, '')
            row = self.owner(token)
            if row:
                app = await self.load(row['id'])
                self.authorize_owner(app, token, row)
                return app, row['id'], receive
            if self.primary.state.classroom.valid_operator(request): return self.primary, None, receive
            if request.headers.get('authorization'): return self.primary, None, receive
        raise HTTPException(403, 'Create a workspace or pair this phone to continue.')

    async def close_app(self, workspace_id):
        app = self.apps.pop(workspace_id, None)
        context = self.contexts.pop(workspace_id, None)
        if app:
            classroom = app.state.classroom
            classroom.socket_tickets.pending.clear()
            for camera_id in tuple(classroom.live): await classroom.disconnect_camera(camera_id,revoke=False)
            for socket in tuple(classroom.viewers):
                try: await socket.close(code=1000)
                except RuntimeError: pass
            if context: await context.__aexit__(None, None, None)

    async def close(self):
        for workspace_id in tuple(self.apps): await self.close_app(workspace_id)
        self.db.close()

    async def __call__(self, scope, receive, send):
        path = scope.get('path', '')
        try:
            if not path.startswith('/api/'):
                await self.primary(scope, receive, send)
                return
            if scope['type'] == 'http' and path == '/api/v2/workspaces':
                if scope['method'] != 'POST': raise HTTPException(405, 'Use POST to create a workspace.')
                _, receive = await self._body(receive)
                await (await self.create(Request(scope, receive)))(scope, receive, send)
                return
            app, workspace_id, receive = await self.target(scope, receive)
            request = Request(scope)
            push_endpoint = None
            if scope['type'] == 'http' and scope.get('method') == 'POST' and path == '/api/v2/guard/push':
                body, receive = await self._body(receive)
                try:
                    candidate = json.loads(body).get('subscription', {}).get('endpoint')
                    if isinstance(candidate, str): push_endpoint = candidate
                except (ValueError, AttributeError): pass
            if path == '/api/v2/workspaces/current':
                if scope['type'] != 'http' or scope['method'] != 'DELETE': raise HTTPException(405, 'Use DELETE to remove this workspace.')
                if not workspace_id: raise HTTPException(403, 'Only this workspace owner can delete it.')
                app.state.classroom.require_admin(request)
                async with self.lock:
                    with self.db: self.db.execute('DELETE FROM workspaces WHERE id=?', (workspace_id,))
                    await self.close_app(workspace_id)
                    for suffix in ('', '-wal', '-shm'):
                        (self.directory/(workspace_id+'.sqlite'+suffix)).unlink(missing_ok=True)
                response = Response(status_code=204)
                for cookie, cookie_path in ((ADMIN_COOKIE, '/api/v2'), (CAMERA_COOKIE, '/api/v2/camera'), (GUARD_COOKIE, '/api/v2/guard')):
                    response.delete_cookie(cookie, path=cookie_path)
                await response(scope, receive, send)
                return
            logout = workspace_id and path in ('/api/v2/operator/logout', '/api/v2/auth/dev/logout')
            if logout and scope.get('method') == 'POST':
                scope = {**scope, 'path': '/api/v2/operator/logout', 'raw_path': b'/api/v2/operator/logout'}
            start, chunks = None, []

            async def output(message):
                nonlocal start
                if message['type'] == 'http.response.start':
                    if push_endpoint and 200 <= message['status'] < 300:
                        # A browser push subscription belongs to its current
                        # paired workspace, even after the phone changes sites.
                        for other in self.all_apps():
                            if other is app: continue
                            store = other.state.classroom.store
                            with store.db:
                                store.db.execute('DELETE FROM guard_push_subscriptions WHERE endpoint=?', (push_endpoint,))
                    if logout and 200 <= message['status'] < 300:
                        with self.db: self.db.execute('UPDATE workspaces SET owner_hash=NULL,expires=0 WHERE id=?', (workspace_id,))
                    if workspace_id and path == '/api/v2/me' and message['status'] == 200:
                        start = message
                        return
                if start is not None and message['type'] == 'http.response.body':
                    chunks.append(message.get('body', b''))
                    if not message.get('more_body'):
                        payload = json.loads(b''.join(chunks))
                        payload['workspace'] = self.metadata(workspace_id, app)
                        body = json.dumps(payload).encode()
                        headers = [(k, v) for k, v in start.get('headers', []) if k != b'content-length']
                        await send({**start, 'headers': [*headers, (b'content-length', str(len(body)).encode())]})
                        await send({'type': 'http.response.body', 'body': body})
                    return
                await send(message)
            await app(scope, receive, output)
        except HTTPException as error:
            if scope['type'] == 'websocket': await send({'type': 'websocket.close', 'code': 1008})
            else: await JSONResponse({'detail': error.detail}, status_code=error.status_code)(scope, receive, send)
