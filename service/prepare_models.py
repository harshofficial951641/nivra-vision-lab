"""Download only pinned model artifacts and verify them before use."""
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile
import argparse

ROOT = Path(__file__).resolve().parent


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def prepare(experimental=False):
    manifest = json.loads((ROOT / 'model-manifest.json').read_text())
    directory = ROOT / 'models'
    directory.mkdir(exist_ok=True)
    for model in manifest['models']:
        if model.get('optional') and not experimental:
            continue
        output = directory / model['file']
        if output.exists():
            if digest(output) != model['sha256']:
                raise RuntimeError(f"Checksum mismatch: {output.name}. Existing file was preserved.")
            continue
        temporary = directory / (model['file'] + '.download')
        urllib.request.urlretrieve(model['url'], temporary)
        if digest(temporary) != model['downloadSha256']:
            raise RuntimeError(f"Download checksum mismatch: {model['id']}")
        if model.get('archiveMember'):
            with zipfile.ZipFile(temporary) as archive:
                # Extract one named file, never arbitrary archive paths.
                output.write_bytes(archive.read(model['archiveMember']))
            temporary.unlink()
        else:
            temporary.replace(output)
        if digest(output) != model['sha256']:
            raise RuntimeError(f"Model checksum mismatch: {model['id']}")
        print(f"Verified {model['id']}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--experimental', action='store_true')
    prepare(parser.parse_args().experimental)
