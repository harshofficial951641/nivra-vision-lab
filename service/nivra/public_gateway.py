"""Separate loopback listener for the authenticated Sites relay, never local bootstrap."""
import secrets
from starlette.responses import JSONResponse


class PublicGateway:
    def __init__(self, app, secret, tickets=None):
        if len(secret) < 40: raise ValueError('A strong relay credential is required.')
        self.app, self.secret, self.tickets = app, secret, tickets

    async def __call__(self, scope, receive, send):
        headers = dict(scope.get('headers', []))
        path = scope.get('path', '')
        entry = self.tickets.consume(scope) if scope['type'] == 'websocket' and self.tickets else None
        if entry:
            # Authentication material stays on the server. Ignore any caller-supplied
            # cookie/authorization and remove the opaque handshake capability.
            kept = [(k, v) for k, v in scope['headers'] if k not in (b'cookie', b'authorization', b'sec-websocket-protocol')]
            if entry['cookie']: kept.append((b'cookie', entry['cookie'].encode()))
            if entry['authorization']: kept.append((b'authorization', entry['authorization'].encode()))
            scope = {**scope, 'headers': kept, 'subprotocols': []}
        valid = entry is not None or secrets.compare_digest(headers.get(b'x-nivra-relay', b''), self.secret.encode())
        allowed = (path.startswith('/api/v2/') and path != '/api/v2/operator/invite') or (
            scope.get('method') == 'GET' and (path in ('/', '/camera', '/lab', '/fight', '/wall', '/guard', '/setup', '/login', '/guard/login', '/mobile', '/favicon.svg')
            or path.startswith(('/assets/', '/brand/', '/mediapipe/', '/models/', '/fight-samples/'))))
        if not valid or not allowed:
            if scope['type'] == 'websocket': await send({'type': 'websocket.close', 'code': 1008})
            else: await JSONResponse({'detail': 'Access denied'}, status_code=403)(scope, receive, send)
            return
        # The gateway cannot masquerade as the local operator, even if callers forge headers.
        scope = {**scope, 'headers': [(k,v) for k,v in scope['headers'] if k not in (b'host', b'x-forwarded-host')] + [
            (b'host', b'127.0.0.1:8765'), (b'x-forwarded-host', b'nivra-public-gateway')]}
        async def gateway_send(message):
            if entry and message['type'] == 'websocket.accept':
                # Browsers require the server to select a requested protocol.
                # Echo only the capability already consumed and validated here;
                # the application still never receives it in its ASGI scope.
                message = {**message, 'subprotocol': entry['subprotocol']}
            await send(message)

        target = entry.get('target_app', self.app) if entry else self.app
        await target(scope, receive, gateway_send)
