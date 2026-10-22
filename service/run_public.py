"""Read relay configuration from hidden stdin; run local and gated listeners together."""
import asyncio
import json
import os
import sys
import uvicorn


async def run(config):
    os.environ['NIVRA_PUBLIC_ORIGIN'] = config['origin']
    if config.get('socketOrigin'): os.environ['NIVRA_SOCKET_ORIGIN'] = config['socketOrigin']
    from nivra.server import create_app, MAX_FRAME_BYTES
    from nivra.public_gateway import PublicGateway
    from nivra.workspaces import Workspaces
    from pathlib import Path
    # Existing camera pages keep their browser detector. The explicit /fight demo
    # loads only X3D-M on the PC; it never shares operator data or saves footage.
    app = create_app(relay_only=True, enable_fight_demo=bool(config.get('fightDemo')))
    workspaces = Workspaces(app, Path(__file__).resolve().parent/'state'/'workspaces')
    options = dict(host='127.0.0.1', access_log=False, log_level='warning', ws_max_size=MAX_FRAME_BYTES, ws_max_queue=1, proxy_headers=False)
    local = uvicorn.Server(uvicorn.Config(app, port=8765, **options))
    gateway = uvicorn.Server(uvicorn.Config(PublicGateway(workspaces, config['secret'], workspaces), port=8766, lifespan='off', **options))
    # Share one model instance, scheduler and database. Only the local listener runs lifespan.
    try: await asyncio.gather(local.serve(), gateway.serve())
    finally: await workspaces.close()


if __name__ == '__main__':
    if sys.stdin.isatty():
        import getpass
        raw = getpass.getpass('Public relay configuration (hidden JSON): ')
    else: raw = sys.stdin.readline()
    asyncio.run(run(json.loads(raw)))
