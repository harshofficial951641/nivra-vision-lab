"""Separate loopback listener for the authenticated Sites relay, never local bootstrap."""
import secrets
from starlette.responses import JSONResponse


class PublicGateway:
    def __init__(self, app, secret):
        if len(secret) < 40: raise ValueError('A strong relay credential is required.')
        self.app, self.secret = app, secret

    async def __call__(self, scope, receive, send):
        headers = dict(scope.get('headers', []))
        path = scope.get('path', '')
        valid = secrets.compare_digest(headers.get(b'x-nivra-relay', b''), self.secret.encode())
        allowed = (path.startswith('/api/v2/') and path != '/api/v2/operator/invite') or (
            scope.get('method') == 'GET' and (path in ('/', '/camera', '/lab', '/fight', '/favicon.svg')
            or path.startswith(('/assets/', '/brand/', '/mediapipe/', '/models/', '/fight-samples/'))))
        if not valid or not allowed:
            if scope['type'] == 'websocket': await send({'type': 'websocket.close', 'code': 1008})
            else: await JSONResponse({'detail': 'Access denied'}, status_code=403)(scope, receive, send)
            return
        # The gateway cannot masquerade as the local operator, even if callers forge headers.
        scope = {**scope, 'headers': [(k,v) for k,v in scope['headers'] if k not in (b'host', b'x-forwarded-host')] + [
            (b'host', b'127.0.0.1:8765'), (b'x-forwarded-host', b'nivra-public-gateway')]}
        await self.app(scope, receive, send)
