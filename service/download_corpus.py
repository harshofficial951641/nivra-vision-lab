"""Reproduce the licensed smoke corpus. No credentials or external uploads."""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parent/'evaluation'
for clip in json.loads((ROOT/'corpus.json').read_text()):
    path=(ROOT/clip['path']).resolve()
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest()!=clip['sha256']:
            raise RuntimeError(f"Existing clip checksum mismatch: {clip['id']}")
        continue
    if not clip.get('url'):
        raise RuntimeError(f"Restore repository fixture {clip['id']}")
    request=urllib.request.Request(clip['url'],headers={'User-Agent':'Mozilla/5.0 NivraEvaluation/0.1'})
    with urllib.request.urlopen(request,timeout=60) as response:
        data=response.read(100_000_001)
    if len(data)>100_000_000 or hashlib.sha256(data).hexdigest()!=clip['sha256']:
        raise RuntimeError('Clip size or checksum mismatch')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data)
    print(f"Verified {clip['id']}")
