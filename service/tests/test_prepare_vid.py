import hashlib
import io
import json
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

import prepare_vid


def archive_item(content=b'pinned archive'):
    return {'name': 'v_c_b_01.rar', 'id': 10123417, 'bytes': len(content),
            'md5': hashlib.md5(content).hexdigest(), 'publisherCategory': 'classroom'}


def listing(monkeypatch, lines):
    monkeypatch.setattr(prepare_vid.shutil, 'which', lambda name: 'tar.exe')
    monkeypatch.setattr(prepare_vid.subprocess, 'run',
                        lambda *args, **kwargs: SimpleNamespace(stdout='\n'.join(lines)))


def file_line(name, size=12, mode='-rw-r--r--'):
    return f'{mode}  0 owner group {size} Jan 1 2024 {name}'


def test_verified_cached_archive_is_reused_without_network(tmp_path, monkeypatch):
    content = b'pinned archive'
    item = archive_item(content)
    cached = tmp_path / item['name']
    cached.write_bytes(content)
    monkeypatch.setattr(prepare_vid.urllib.request, 'urlopen',
                        lambda *args, **kwargs: pytest.fail('Verified cache must not use network'))
    assert prepare_vid.fetch(item, tmp_path) == cached


@pytest.mark.parametrize('content', [b'short', b'wrong contents'])
def test_changed_archive_cache_is_rejected(tmp_path, content):
    item = archive_item()
    (tmp_path / item['name']).write_bytes(content)
    with pytest.raises(ValueError, match='checksum mismatch'):
        prepare_vid.fetch(item, tmp_path)


def test_complete_download_is_checked_before_atomic_promotion(tmp_path, monkeypatch):
    content = b'pinned archive'
    item = archive_item(content)
    requests = []

    def open_url(request, timeout):
        requests.append((request.full_url, timeout))
        return io.BytesIO(content)

    monkeypatch.setattr(prepare_vid.urllib.request, 'urlopen', open_url)
    cached = prepare_vid.fetch(item, tmp_path)
    assert cached.read_bytes() == content
    assert not cached.with_suffix('.rar.part').exists()
    assert requests == [('https://dataverse.harvard.edu/api/access/datafile/10123417', 120)]


def test_oversize_download_is_never_promoted(tmp_path, monkeypatch):
    item = archive_item()
    monkeypatch.setattr(prepare_vid.urllib.request, 'urlopen',
                        lambda *args, **kwargs: io.BytesIO(b'x' * (item['bytes'] + 1)))
    with pytest.raises(ValueError, match='exceeds pinned size'):
        prepare_vid.fetch(item, tmp_path)
    assert not (tmp_path / item['name']).exists()


def test_partial_download_is_not_accepted_as_valid_cache(tmp_path):
    item = archive_item()
    (tmp_path / (item['name'] + '.part')).write_bytes(b'interrupted')
    with pytest.raises(ValueError, match='checksum mismatch'):
        prepare_vid.fetch(item, tmp_path)
    assert not (tmp_path / item['name']).exists()


def test_archive_inventory_accepts_only_expected_mp4s_and_counts_expanded_bytes(monkeypatch):
    listing(monkeypatch, [file_line('classroom/', 0, 'drwxr-xr-x'),
                          file_line('classroom/clip_01.mp4', 123),
                          file_line('classroom/clip_02.MP4', 456)])
    tar, names, expanded = prepare_vid.archive_members(Path('fixture.rar'))
    assert tar == 'tar.exe'
    assert names == ['classroom/clip_01.mp4', 'classroom/clip_02.MP4']
    assert expanded == 579


@pytest.mark.parametrize('name', ['../clip.mp4', '/clip.mp4', 'C:/clip.mp4',
                                  r'classroom\clip.mp4', 'classroom/../clip.mp4',
                                  'classroom/clip.mp4:stream', 'classroom/clip name.mp4',
                                  'classroom/instructions.py'])
def test_unsafe_archive_names_and_non_media_are_rejected(monkeypatch, name):
    listing(monkeypatch, [file_line(name)])
    with pytest.raises(ValueError):
        prepare_vid.archive_members(Path('fixture.rar'))


@pytest.mark.parametrize('mode', ['lrwxrwxrwx', 'hrw-r--r--', 'crw-r--r--', 'brw-r--r--', 'prw-r--r--'])
def test_archive_links_and_special_files_are_rejected(monkeypatch, mode):
    listing(monkeypatch, [file_line('classroom/clip.mp4', mode=mode)])
    with pytest.raises(ValueError, match='Unsupported archive entry'):
        prepare_vid.archive_members(Path('fixture.rar'))


def test_even_directory_paths_are_checked_before_ignoring_them(monkeypatch):
    listing(monkeypatch, [file_line('../outside/', 0, 'drwxr-xr-x'), file_line('clip.mp4')])
    with pytest.raises(ValueError, match='Unsafe archive path'):
        prepare_vid.archive_members(Path('fixture.rar'))


@pytest.mark.parametrize('lines', [[], [file_line('clip.mp4'), file_line('clip.mp4')],
                                   [file_line('clip.mp4', 5_000_000_001)],
                                   [file_line(f'clip_{index}.mp4', 1) for index in range(5001)]])
def test_empty_duplicate_oversize_and_excessive_archives_are_rejected(monkeypatch, lines):
    listing(monkeypatch, lines)
    with pytest.raises(ValueError, match='Unexpected archive'):
        prepare_vid.archive_members(Path('fixture.rar'))


@pytest.mark.parametrize('names', [('classroom/clip.mp4', 'classroom/CLIP.mp4'),
                                   ('classroom/clip.mp4', 'classroom//clip.mp4'),
                                   ('classroom/clip.mp4', 'classroom/./clip.mp4')])
def test_windows_path_aliases_cannot_overwrite_a_validated_archive_member(monkeypatch, names):
    listing(monkeypatch, [file_line(name) for name in names])
    with pytest.raises(ValueError):
        prepare_vid.archive_members(Path('fixture.rar'))


@pytest.mark.parametrize('name', ['CON.mp4', 'aux.MP4', 'classroom/NUL.mp4', 'COM1.mp4', 'LPT9.mp4'])
def test_windows_reserved_device_names_are_not_valid_media_paths(monkeypatch, name):
    listing(monkeypatch, [file_line(name)])
    with pytest.raises(ValueError):
        prepare_vid.archive_members(Path('fixture.rar'))


def setup_cached_extraction(tmp_path, monkeypatch, marker):
    item = archive_item()
    archive = tmp_path / 'archives' / item['name']
    target = tmp_path / 'media' / archive.stem
    target.mkdir(parents=True)
    (target / '.complete.json').write_text(json.dumps(marker), encoding='utf-8')
    monkeypatch.setattr(prepare_vid, 'fetch', lambda *args: archive)
    monkeypatch.setattr(prepare_vid, '_archive_entries', lambda *args: ('tar.exe', {'clip.mp4': 12}, 12))
    return item, target


def test_completion_marker_must_match_the_pinned_archive_before_media_is_opened(tmp_path, monkeypatch):
    item, _ = setup_cached_extraction(tmp_path, monkeypatch, {'archiveMd5': 'f' * 32})
    monkeypatch.setattr(prepare_vid.cv2, 'VideoCapture',
                        lambda *args: pytest.fail('A stale extraction must be rejected before reading media'))
    with pytest.raises(ValueError):
        prepare_vid.prepare(item, tmp_path)


def test_incomplete_extraction_is_not_merged_or_reused(tmp_path, monkeypatch):
    item, target = setup_cached_extraction(tmp_path, monkeypatch, {})
    (target / '.complete.json').unlink()
    monkeypatch.setattr(prepare_vid.subprocess, 'run',
                        lambda *args, **kwargs: pytest.fail('Must not extract into an existing incomplete directory'))
    with pytest.raises(ValueError, match='Incomplete extraction'):
        prepare_vid.prepare(item, tmp_path)


@pytest.mark.parametrize('contents', [None, b'too short'])
def test_completion_marker_cannot_hide_missing_or_truncated_members(tmp_path, monkeypatch, contents):
    item = archive_item()
    item, target = setup_cached_extraction(tmp_path, monkeypatch, {'archiveMd5': item['md5']})
    if contents is not None:
        (target / 'clip.mp4').write_bytes(contents)
    monkeypatch.setattr(prepare_vid.cv2, 'VideoCapture',
                        lambda *args: pytest.fail('Incomplete cached media must fail before decode'))
    with pytest.raises(ValueError, match='missing or has an unexpected size'):
        prepare_vid.prepare(item, tmp_path)


def fake_capture():
    properties = {prepare_vid.cv2.CAP_PROP_FPS: 30,
                  prepare_vid.cv2.CAP_PROP_FRAME_COUNT: 180,
                  prepare_vid.cv2.CAP_PROP_FRAME_WIDTH: 1280,
                  prepare_vid.cv2.CAP_PROP_FRAME_HEIGHT: 720}
    return SimpleNamespace(get=properties.__getitem__, release=lambda: None)


def test_matching_completed_extraction_is_inventoried_without_inferred_labels(tmp_path, monkeypatch):
    item = archive_item()
    item, target = setup_cached_extraction(tmp_path, monkeypatch, {'archiveMd5': item['md5']})
    content = b'x' * 12
    (target / 'clip.mp4').write_bytes(content)
    monkeypatch.setattr(prepare_vid.cv2, 'VideoCapture', lambda *args: fake_capture())
    monkeypatch.setattr(prepare_vid.subprocess, 'run',
                        lambda *args, **kwargs: pytest.fail('Verified extraction must not be merged/re-extracted'))
    records = prepare_vid.prepare(item, tmp_path)
    assert len(records) == 1
    assert records[0]['sha256'] == hashlib.sha256(content).hexdigest()
    assert records[0]['durationSeconds'] == 6
    assert records[0]['reviewStatus'] == 'pending'
    assert records[0]['label'] is None and records[0]['split'] is None
    assert records[0]['recordingGroup'] is None


def test_failed_extraction_never_writes_completion_marker(tmp_path, monkeypatch):
    item = archive_item()
    monkeypatch.setattr(prepare_vid, 'fetch', lambda *args: tmp_path / 'archives' / item['name'])
    monkeypatch.setattr(prepare_vid, '_archive_entries', lambda *args: ('tar.exe', {'clip.mp4': 12}, 12))
    monkeypatch.setattr(prepare_vid.shutil, 'disk_usage', lambda *args: SimpleNamespace(free=2_000_000_000))
    monkeypatch.setattr(prepare_vid.subprocess, 'run', lambda *args, **kwargs: None)
    with pytest.raises(ValueError, match='missing or has an unexpected size'):
        prepare_vid.prepare(item, tmp_path)
    assert not (tmp_path / 'media' / 'v_c_b_01' / '.complete.json').exists()


def test_windows_junction_attribute_is_rejected_even_without_symlink_mode():
    metadata = SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
    fake_path = SimpleNamespace(lstat=lambda: metadata)
    with pytest.raises(ValueError, match='reparse points'):
        prepare_vid._reject_link(fake_path)


def test_extraction_cannot_follow_a_preexisting_directory_link(tmp_path, monkeypatch):
    root = tmp_path / 'data'
    outside = tmp_path / 'outside'
    root.mkdir()
    outside.mkdir()
    try:
        (root / 'media').symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip('OS does not permit creation of test symlinks')
    item = archive_item()
    monkeypatch.setattr(prepare_vid, 'fetch', lambda *args: root / 'archives' / item['name'])
    monkeypatch.setattr(prepare_vid, '_archive_entries', lambda *args: ('tar.exe', {'clip.mp4': 12}, 12))
    monkeypatch.setattr(prepare_vid.subprocess, 'run',
                        lambda *args, **kwargs: pytest.fail('Extraction must not write through a directory link'))
    with pytest.raises(ValueError):
        prepare_vid.prepare(item, root)
