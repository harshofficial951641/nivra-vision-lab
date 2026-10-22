"""Fetch only pinned inert assets for an offline diagnostic; never load a model."""
import hashlib
import json
from pathlib import Path
import urllib.request

MODEL = 'cliffer1/videomae-base-finetuned-kinetics-violence-nonviolence-tuned'
REVISION = '613844b1d2d27f68944619bf91885a9befb101ac'
FILES = {
    'config.json': ('59e7a7ba3196e7d7272304b16dc59e15b09b9f17832d76e8cbd9755487afa8ed', 100_000),
    'preprocessor_config.json': ('4bc9b255ff212041bc28127d4fa0ae1630abca52bb2d882f3e4c0b9e5b763f06', 100_000),
    'README.md': ('0d2adb5b283c3c4bd8fd087d5ce85d0c2a6528c7ca6cc6ff65da51645452614f', 100_000),
    'model.safetensors': ('5166b055ebee1439d6517c5bf2d516dce7a1f65afc53367f43b5848970853d53', 344_937_328),
}
DESTINATION = Path(__file__).resolve().parent / 'cache' / 'cliffer1-videomae' / REVISION


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    DESTINATION.mkdir(parents=True, exist_ok=True)
    records = []
    for name, (expected, limit) in FILES.items():
        target = DESTINATION / name
        url = f'https://huggingface.co/{MODEL}/resolve/{REVISION}/{name}'
        if target.exists():
            if not target.is_file() or digest(target) != expected:
                raise ValueError('Existing asset does not match pin: ' + name)
        else:
            partial = target.with_suffix(target.suffix + '.partial')
            # Exclusive creation preserves evidence from any interrupted attempt.
            total = 0
            with partial.open('xb') as output:
                with urllib.request.urlopen(url, timeout=30) as response:
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if total > limit:
                            raise ValueError('Asset exceeds pinned byte limit: ' + name)
                        output.write(chunk)
            if name == 'model.safetensors' and total != limit:
                raise ValueError('Checkpoint byte count mismatch')
            if digest(partial) != expected:
                raise ValueError('Downloaded asset checksum mismatch: ' + name)
            partial.rename(target)
        records.append({'file': name, 'url': url, 'bytes': target.stat().st_size,
                        'sha256': expected})
        print(json.dumps({'verified': name, 'bytes': target.stat().st_size}), flush=True)
    report = {'schemaVersion': 1, 'model': MODEL, 'revision': REVISION,
              'status': 'staged-not-executed', 'files': records,
              'purpose': 'offline development diagnostic; no redistribution or live promotion',
              'rights': {'checkpointCard': 'CC-BY-NC-4.0', 'trainingData': 'unknown'}}
    # A deterministic receipt can be checked against an earlier complete staging.
    receipt = DESTINATION / 'staging.json'
    content = json.dumps(report, indent=2) + '\n'
    if receipt.exists() and receipt.read_text(encoding='utf-8') != content:
        raise ValueError('Existing staging receipt differs')
    if not receipt.exists():
        receipt.write_text(content, encoding='utf-8')
    print(str(DESTINATION), flush=True)


if __name__ == '__main__':
    main()
