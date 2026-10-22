"""Validated local serving options; no certificate generation at runtime."""
import os
from pathlib import Path


def serving_options(env=None):
    env = os.environ if env is None else env
    cert, key = env.get('NIVRA_TLS_CERT'), env.get('NIVRA_TLS_KEY')
    if bool(cert) != bool(key):
        raise ValueError('Set both NIVRA_TLS_CERT and NIVRA_TLS_KEY')
    for value in (cert, key):
        if value and not Path(value).is_file():
            raise ValueError('TLS certificate/key file does not exist')
    try:
        port = int(env.get('NIVRA_PORT', '8443' if cert else '8765'))
    except ValueError as error:
        raise ValueError('NIVRA_PORT must be an integer from 1 to 65535') from error
    if not 1 <= port <= 65535:
        raise ValueError('NIVRA_PORT must be an integer from 1 to 65535')
    return dict(host=env.get('NIVRA_HOST', '0.0.0.0' if cert else '127.0.0.1'), port=port,
                ssl_certfile=cert, ssl_keyfile=key)
