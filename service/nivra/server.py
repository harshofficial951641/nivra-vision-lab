"""Loopback-only application host and versioned inference stream."""
import asyncio
from contextlib import asynccontextmanager
import json
import secrets
import struct
from pathlib import Path
import cv2
import numpy as np
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

ROOT = Path(__file__).resolve().parents[2]
PORT = 8765
ORIGINS = {f'http://127.0.0.1:{PORT}', f'http://localhost:{PORT}'}
COOKIE = 'nivra_local_session'
MAX_FRAME_BYTES = 1_500_000


class Header(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    version: int = Field(1, ge=1, le=1)
    timestampMs: float = Field(ge=0)
    streamId: int = Field(ge=0, le=2**31-1)
    maxPeople: int = Field(4, ge=2, le=50)


def unpack_frame(packet):
    if len(packet) > MAX_FRAME_BYTES or len(packet) < 8:
        raise ValueError('Frame size is invalid.')
    length = struct.unpack('<I', packet[:4])[0]
    if length > 1024 or length + 4 >= len(packet):
        raise ValueError('Frame header is invalid.')
    header = Header.model_validate_json(packet[4:4+length])
    # Read encoded dimensions before asking OpenCV to allocate the decoded image.
    from PIL import Image
    from io import BytesIO
    encoded = packet[4+length:]
    with Image.open(BytesIO(encoded)) as image:
        w, h = image.size
        if image.format != 'JPEG' or min(w, h) < 32 or max(w, h) > 1280 or not .4 <= w/h <= 2.5:
            raise ValueError('Use JPEG frames up to 1280 px with a supported aspect ratio.')
    frame = cv2.imdecode(np.frombuffer(encoded, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError('Frame could not be decoded.')
    return header, frame


def create_app(model_factory=None, pipeline_factory=None, database=None):
    if model_factory is None:
        from .models import Models
        model_factory = Models
    if pipeline_factory is None:
        from .pipeline import Pipeline
        pipeline_factory = Pipeline
    token = secrets.token_urlsafe(32)
    state = {'models': None, 'error': None, 'busy': False}
    inference_lock = asyncio.Lock()
    from .classroom import Classroom
    classroom = Classroom(state, pipeline_factory, unpack_frame, inference_lock, database)

    @asynccontextmanager
    async def lifespan(app):
        async def load():
            try:
                state['models'] = await asyncio.to_thread(model_factory)
            except Exception as error:
                state['error'] = str(error)
        task = asyncio.create_task(load())
        await classroom.start()
        yield
        await classroom.stop()
        await task

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    from urllib.parse import urlsplit
    hosts = ['127.0.0.1', 'localhost'] + ([urlsplit(classroom.public).hostname] if classroom.public else [])
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)
    app.include_router(classroom.router)
    app.state.classroom = classroom

    @app.middleware('http')
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
        response.headers['Cross-Origin-Embedder-Policy'] = 'require-corp'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/api/v1/health')
    async def health():
        return {'version': 1, 'backend': 'local-ai', 'status': 'error' if state['error'] else 'ready' if state['models'] else 'loading',
                'error': state['error'], 'experimental': True,
                'runtime': state['models'].runtime if state['models'] else None}

    @app.post('/api/v1/session')
    async def session(request: Request):
        if request.headers.get('origin') not in ORIGINS or request.headers.get('host') not in ('127.0.0.1:8765','localhost:8765') or any(h in request.headers for h in ('forwarded','x-forwarded-for','x-forwarded-host','x-forwarded-proto')):
            return JSONResponse({'error': 'Origin rejected'}, status_code=403)
        response = Response(status_code=204)
        response.set_cookie(COOKIE, token, httponly=True, samesite='strict', path='/api/v1', max_age=None)
        return response

    @app.websocket('/api/v1/stream')
    async def stream(socket: WebSocket):
        credential = socket.cookies.get(COOKIE, '')
        if socket.headers.get('origin') not in ORIGINS or not secrets.compare_digest(credential, token):
            await socket.close(code=1008)
            return
        if state['models'] is None or state['busy']:
            await socket.close(code=1013)
            return
        state['busy'] = True
        pipeline = None
        current_stream = -1
        try:
            await socket.accept()
            pipeline = pipeline_factory(state['models'])
            while True:
                message = await asyncio.wait_for(socket.receive(), timeout=600)
                if message['type'] == 'websocket.disconnect':
                    break
                if message.get('text') is not None:
                    if len(message['text']) > 128:
                        raise ValueError('Invalid control packet')
                    control = json.loads(message['text'])
                    if control.get('type') != 'reset' or not isinstance(control.get('streamId'), int) or control['streamId'] <= current_stream:
                        raise ValueError('Invalid reset')
                    pipeline.reset()
                    current_stream = control['streamId']
                    continue
                packet = message.get('bytes', b'')
                header, frame = unpack_frame(packet)
                if header.maxPeople > state['models'].runtime.get('maxPeople', 8):
                    raise ValueError('People limit exceeds this model profile.')
                if header.streamId < current_stream:
                    raise ValueError('Expired stream generation.')
                if header.streamId != current_stream:
                    pipeline.reset()
                    current_stream = header.streamId
                async with inference_lock:
                    result = await asyncio.to_thread(pipeline.process, frame, header.timestampMs, header.maxPeople)
                if 'conflict' in result:
                    result['conflict']['events'] = [dict(event,id=f"{current_stream}-{event['id']}") for event in result['conflict']['events']]
                await socket.send_json({**result, 'streamId': current_stream})
        except WebSocketDisconnect:
            pass
        except (ValueError, asyncio.TimeoutError):
            await socket.close(code=1008, reason='Invalid frame, timestamp, or expired session.')
        except Exception:
            # No frames, credentials, or internal stack details go to logs/browser.
            await socket.close(code=1011, reason='Local inference failed. Restart analysis.')
        finally:
            state['busy'] = False
            if pipeline is not None:
                pipeline.reset()

    @app.get('/camera')
    @app.get('/lab')
    async def application_route():
        return FileResponse(ROOT / 'dist' / 'index.html',headers={'Cache-Control':'no-store'})

    app.mount('/', StaticFiles(directory=str(ROOT / 'dist'), html=True, check_dir=False), name='app')
    return app


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(create_app(), host='127.0.0.1', port=PORT, access_log=False, ws_max_size=MAX_FRAME_BYTES,
                ws_max_queue=1, log_level='warning')
