"""Process-scoped signed URLs shared by floor plans and RAM clip frames."""
import hashlib
import hmac
import os
import secrets
import time
from urllib.parse import urlencode

_SECRET = os.environ.get('NIVRA_URL_SECRET', '').encode() or secrets.token_bytes(32)


def signature(path: str, exp: int) -> str:
    return hmac.new(_SECRET, f'{path}\n{exp}'.encode(), hashlib.sha256).hexdigest()


def sign_url(path: str, *, ttl: int = 600, now: float | None = None) -> str:
    """Sign the exact path, including any existing version query string."""
    exp = int(time.time() if now is None else now) + ttl
    return path + ('&' if '?' in path else '?') + urlencode({'exp': exp, 'sig': signature(path, exp)})


def verify_url(path: str, exp: int | str, sig: str, *, now: float | None = None) -> bool:
    try:
        expiry = int(exp)
        if expiry <= (time.time() if now is None else now): return False
        return hmac.compare_digest(signature(path, expiry), sig)
    except (ValueError, TypeError, OverflowError):
        return False
