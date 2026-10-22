"""Short-lived, single-use websocket capabilities for a split HTTPS/WS relay.

The browser receives an opaque ticket, never HttpOnly cookie values or the
server-to-server relay secret. Tickets are scoped to an origin and socket path.
"""
import secrets
import time
from urllib.parse import urlsplit

from fastapi import HTTPException

PATHS = {'operator': '/api/v2/operator', 'camera': '/api/v2/camera/stream', 'guard': '/api/v2/guard/stream'}
COOKIE_NAMES = ('nivra_operator', 'nivra_publisher', 'nivra_guard', 'nivra_dev')


class SocketTickets:
    def __init__(self, origin=''):
        self.origin = origin.rstrip('/')
        if self.origin:
            url = urlsplit(self.origin)
            if (url.scheme != 'https' or not url.hostname or not url.hostname.endswith('.trycloudflare.com')
                    or url.username or url.password or url.port or url.path or url.query or url.fragment):
                raise ValueError('Socket relay must be an HTTPS Quick Tunnel origin.')
        self.pending = {}

    def mint(self, role, request):
        if not self.origin: raise HTTPException(404, 'Direct socket relay is not configured.')
        now = time.monotonic()
        self.pending = {key: value for key, value in self.pending.items() if value['expires'] > now}
        if len(self.pending) >= 512: raise HTTPException(429, 'Too many pending connections. Try again shortly.')
        token = secrets.token_urlsafe(32)
        cookie = '; '.join(f'{key}={request.cookies[key]}' for key in COOKIE_NAMES if key in request.cookies)
        path = PATHS[role]
        self.pending[token] = dict(path=path, origin=request.headers.get('origin'), cookie=cookie,
                                   authorization=request.headers.get('authorization'), expires=now+30)
        return dict(url=self.origin.replace('https://', 'wss://', 1)+path, ticket=token)

    def consume(self, scope):
        headers = dict(scope.get('headers', []))
        protocols = headers.get(b'sec-websocket-protocol', b'').decode('latin1').split(',')
        tokens = [p.strip()[len('nivra-ticket.'):] for p in protocols if p.strip().startswith('nivra-ticket.')]
        if len(tokens) != 1: return None
        token = tokens[0]
        entry = self.pending.get(token)
        origin = headers.get(b'origin', b'').decode('latin1')
        if not entry or entry['expires'] <= time.monotonic():
            self.pending.pop(token, None)
            return None
        if scope.get('path') != entry['path'] or origin != entry['origin']: return None
        return {**self.pending.pop(token), 'subprotocol': 'nivra-ticket.'+token}
