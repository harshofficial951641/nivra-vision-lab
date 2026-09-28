"""Read relay configuration from hidden stdin; run local and gated listeners together."""
import asyncio
import json
import os
import sys
import uvicorn


async def run(config):
    os.environ['NIVRA_PUBLIC_ORIGIN'] = config['origin']
    os.environ['NIVRA_PERSON_MODEL'] = 'rtmo'
    os.environ['NIVRA_FIGHT_MODEL'] = 'x3d'
    os.environ['NIVRA_ACTION_REGIONS'] = '1'
    from nivra.server import create_app, MAX_FRAME_BYTES
    from nivra.public_gateway import PublicGateway
    app = create_app()
    options = dict(host='127.0.0.1', access_log=False, log_level='warning', ws_max_size=MAX_FRAME_BYTES, ws_max_queue=1, proxy_headers=False)
    local = uvicorn.Server(uvicorn.Config(app, port=8765, **options))
    gateway = uvicorn.Server(uvicorn.Config(PublicGateway(app, config['secret']), port=8766, lifespan='off', **options))
    # Share one model instance, scheduler and database. Only the local listener runs lifespan.
    await asyncio.gather(local.serve(), gateway.serve())


if __name__ == '__main__':
    if sys.stdin.isatty():
        import getpass
        raw = getpass.getpass('Public relay configuration (hidden JSON): ')
    else: raw = sys.stdin.readline()
    asyncio.run(run(json.loads(raw)))
