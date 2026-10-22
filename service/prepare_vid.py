"""Fetch pinned CC0 VID archives and inventory media. Does not assign reviewed labels.

No dataset scripts are executed. Windows' existing libarchive tar reads RAR files;
archive paths, entry types and expanded size are checked before extraction.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import urllib.request

import cv2

ROOT = Path(__file__).resolve().parent / 'training'


def _reject_link(path):
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    if (stat.S_ISLNK(metadata.st_mode)
            or getattr(metadata, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)):
        raise ValueError(f'Local links/reparse points are not allowed: {path}')


def _safe_child(root, relative):
    """Check unresolved components before opening or creating a local child."""
    path = root / relative
    try:
        parts = path.relative_to(root).parts
    except ValueError as error:
        raise ValueError('Local path escaped its data directory') from error
    if not parts or '..' in parts:
        raise ValueError('Local path escaped its data directory')
    current = root
    for part in parts:
        current /= part
        _reject_link(current)
    if not path.resolve().is_relative_to(root):
        raise ValueError('Local path escaped its data directory')
    return path


def _archive_name(name, directory=False):
    # These archives use ASCII filenames. Reject aliases which Windows would
    # merge, and reserved device names even when they have an MP4 extension.
    if directory and name.endswith('/'):
        name = name[:-1]
    pure = PurePosixPath(name)
    parts = name.split('/')
    reserved = re.compile(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$', re.IGNORECASE)
    if (pure.is_absolute() or '\\' in name or ':' in name
            or not re.fullmatch(r'[A-Za-z0-9_./-]+', name)
            or any(part in ('', '.', '..') or part.endswith('.')
                   or reserved.fullmatch(part.split('.')[0]) for part in parts)):
        raise ValueError('Unsafe archive path')
    return name


def digest(path, algorithm='sha256'):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def fetch(item, directory):
    directory = Path(directory).absolute()
    _reject_link(directory)
    if directory != directory.resolve():
        raise ValueError('Archive directory must not follow local links')
    name = _archive_name(item['name'])
    if '/' in name or not name.lower().endswith('.rar'):
        raise ValueError('Pinned archive name must be a regular RAR basename')
    directory.mkdir(parents=True, exist_ok=True)
    path = _safe_child(directory, name)
    temporary = _safe_child(directory, name + '.part')
    for existing in (path, temporary):
        if existing.exists() and not existing.is_file():
            raise ValueError(f'Archive cache is not a regular file: {existing}')
    if not path.exists() and not temporary.exists():
        request = urllib.request.Request(
            f"https://dataverse.harvard.edu/api/access/datafile/{item['id']}",
            headers={'User-Agent': 'NivraDatasetPreparation/1.0'})
        with urllib.request.urlopen(request, timeout=120) as response, temporary.open('xb') as out:
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > item['bytes']:
                    raise ValueError('Download exceeds pinned size')
                out.write(chunk)
    candidate = path if path.exists() else temporary
    if candidate.stat().st_size != item['bytes'] or digest(candidate, 'md5') != item['md5']:
        recovery = f'; remove only this incomplete file and retry: {temporary}' if candidate == temporary else ''
        raise ValueError(f"Size/checksum mismatch for {item['name']}{recovery}")
    if candidate == temporary:
        temporary.replace(path)
    return path


def _archive_entries(archive):
    tar = shutil.which('tar.exe') or shutil.which('tar')
    if not tar:
        raise RuntimeError('A libarchive tar with RAR support is required')
    result = subprocess.run([tar, '-tvf', str(archive)], capture_output=True, text=True, check=True)
    entries = {}
    aliases = set()
    expanded = 0
    # The publisher's archives contain simple ASCII MP4 paths. Reject anything else.
    pattern = re.compile(r'^([-d][rwx-]{9})\s+\d+\s+\S+\s+\S+\s+(\d+)\s+\S+\s+\d+\s+\S+\s+(.+)$')
    for line in result.stdout.splitlines():
        match = pattern.fullmatch(line)
        if not match:
            raise ValueError(f'Unsupported archive entry: {line[:120]}')
        mode, size, name = match.groups()
        name = _archive_name(name, directory=mode[0] == 'd')
        alias = name.casefold()
        if alias in aliases:
            raise ValueError('Unexpected archive duplicates or Windows path aliases')
        aliases.add(alias)
        if mode[0] == 'd':
            continue
        if PurePosixPath(name).suffix.lower() != '.mp4':
            raise ValueError('Archive contains an unexpected non-MP4 file')
        if int(size) <= 0:
            raise ValueError('Archive contains an empty media file')
        expanded += int(size)
        entries[name] = int(size)
    if not entries or len(entries) > 5000 or expanded > 5_000_000_000:
        raise ValueError('Unexpected archive count, duplicates or expanded size')
    return tar, entries, expanded


def archive_members(archive):
    tar, entries, expanded = _archive_entries(archive)
    return tar, list(entries), expanded


def _check_extracted(root, target, entries):
    for name, size in entries.items():
        path = _safe_child(root, target.relative_to(root) / name)
        if not path.is_file() or path.stat().st_size != size:
            raise ValueError(f'Extracted member is missing or has an unexpected size: {name}')


def prepare(item, root):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    archive = fetch(item, _safe_child(root, 'archives'))
    tar, entries, expanded = _archive_entries(archive)
    target = _safe_child(root, Path('media') / archive.stem)
    marker = _safe_child(root, target.relative_to(root) / '.complete.json')
    if target.exists():
        # Do not merge extraction into a pre-existing directory or follow local links.
        if not target.is_dir() or not marker.is_file():
            raise ValueError(f'Incomplete extraction at {target}; inspect it before retrying')
        try:
            completion = json.loads(marker.read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            raise ValueError(f'Invalid extraction completion marker at {target}') from error
        if not isinstance(completion, dict) or completion.get('archiveMd5') != item['md5']:
            raise ValueError(f'Extraction completion marker does not match pinned archive at {target}')
        _check_extracted(root, target, entries)
    else:
        if shutil.disk_usage(root).free < expanded + 1_000_000_000:
            raise ValueError('Insufficient disk space for bounded extraction')
        target.mkdir(parents=True)
        subprocess.run([tar, '-xf', str(archive), '-C', str(target),
                        '--no-same-owner', '--no-same-permissions'], check=True)
        _check_extracted(root, target, entries)
        marker.write_text(json.dumps({'archiveMd5': item['md5']}), encoding='utf-8')
    records = []
    for name in entries:
        path = _safe_child(root, target.relative_to(root) / name)
        capture = cv2.VideoCapture(str(path))
        fps = capture.get(cv2.CAP_PROP_FPS)
        count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        width, height = capture.get(cv2.CAP_PROP_FRAME_WIDTH), capture.get(cv2.CAP_PROP_FRAME_HEIGHT)
        capture.release()
        if any(not math.isfinite(value) or value <= 0 for value in (fps, count, width, height)):
            raise ValueError(f'Unreadable video {name}')
        records.append({'id': path.stem, 'path': path.relative_to(root.resolve()).as_posix(),
                        'sha256': digest(path), 'durationSeconds': count / fps,
                        'fps': fps, 'width': int(width), 'height': int(height),
                        'archive': item['name'], 'publisherCategory': item['publisherCategory'],
                        'reviewStatus': 'pending', 'label': None, 'split': None,
                        'recordingGroup': None})
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, default=ROOT / 'data' / 'vid')
    parser.add_argument('--archive', action='append', required=True,
                        help='Pinned filename from training/vid-files.json; repeat to select more')
    args = parser.parse_args()
    catalog = json.loads((ROOT / 'vid-files.json').read_text(encoding='utf-8'))
    items = {item['name']: item for item in catalog['files']}
    if any(name not in items for name in args.archive):
        parser.error('Only pinned archive names are accepted')
    root = args.data_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    inventory = []
    for name in args.archive:
        records = prepare(items[name], root)
        inventory.extend(records)
        print(f'{name}: verified and inventoried {len(records)} videos', flush=True)
    _safe_child(root, 'inventory.json').write_text(json.dumps(inventory, indent=2) + '\n', encoding='utf-8')
    print(f'Wrote {len(inventory)} pending records; no labels or splits inferred.')


if __name__ == '__main__':
    main()
