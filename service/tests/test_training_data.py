import copy
import hashlib
import json

import pytest

from nivra.training_data import ManifestError, generate_windows, load_manifest, window_label


def manifest():
    return {
        'schemaVersion': 1,
        'sources': [{'id': 'staged', 'url': 'https://example.org/original-data',
                     'license': 'CC0-1.0', 'evidence': ['https://example.org/media-license'],
                     'trainingAllowed': True}],
        'recordings': [{'id': 'normal', 'sourceId': 'staged', 'recordingGroup': 'session-one',
                        'path': 'media/normal.mp4', 'sha256': 'a' * 64, 'durationSeconds': 8,
                        'split': 'train', 'reviewStatus': 'reviewed', 'domain': 'classroom',
                        'label': 0, 'events': [{'startSeconds': 0, 'endSeconds': 8, 'label': 0}]}],
    }


def load(tmp_path, data=None, verify_files=False):
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(manifest() if data is None else data), encoding='utf-8')
    return load_manifest(path, tmp_path / 'data', verify_files=verify_files)


def test_valid_manifest_exposes_typed_resolved_records_and_windows(tmp_path):
    result = load(tmp_path)
    assert result.schema_version == 1
    assert result.sources[0].training_allowed is True
    assert result.recordings[0].path == tmp_path / 'data' / 'media' / 'normal.mp4'
    windows = generate_windows(result, 'train')
    assert [(window.start_seconds, window.end_seconds, window.label) for window in windows] == [
        (0, 4, 0), (4, 8, 0)]


@pytest.mark.parametrize('field,value', [('trainingAllowed', False), ('trainingAllowed', 'true'),
                                        ('evidence', []), ('evidence', ''), ('license', ''),
                                        ('url', 'file:///unverified')])
def test_model_data_requires_explicit_rights_and_evidence(tmp_path, field, value):
    data = manifest()
    data['sources'][0][field] = value
    with pytest.raises(ManifestError):
        load(tmp_path, data)


def test_unknown_source_is_rejected(tmp_path):
    data = manifest()
    data['recordings'][0]['sourceId'] = 'mirror-without-rights'
    with pytest.raises(ManifestError, match='unknown source'):
        load(tmp_path, data)


@pytest.mark.parametrize('split', ['train', 'calibration', 'holdout'])
@pytest.mark.parametrize('field,value', [('reviewStatus', 'pending'), ('label', None), ('label', True)])
def test_fit_and_evaluation_need_known_reviewed_labels(tmp_path, split, field, value):
    data = manifest()
    data['recordings'][0].update(split=split)
    data['recordings'][0][field] = value
    with pytest.raises(ManifestError):
        load(tmp_path, data)


def test_pending_unlicensed_diagnostic_cannot_produce_windows(tmp_path):
    data = manifest()
    data['sources'][0]['trainingAllowed'] = False
    data['recordings'][0].update(split='diagnostic', reviewStatus='pending', label=None, events=[])
    result = load(tmp_path, data)
    assert generate_windows(result, 'train') == ()
    assert window_label(result.recordings[0], 0, 4) is None
    with pytest.raises(ManifestError, match='only'):
        generate_windows(result, 'diagnostic')


@pytest.mark.parametrize('split', ['calibration', 'holdout', 'diagnostic'])
def test_recording_lineage_cannot_cross_splits(tmp_path, split):
    data = manifest()
    duplicate = copy.deepcopy(data['recordings'][0])
    duplicate.update(id='other-view', path='media/other.mp4', sha256='b' * 64, split=split)
    data['recordings'].append(duplicate)
    with pytest.raises(ManifestError, match='leakage through recordingGroup'):
        load(tmp_path, data)


def test_hash_duplicate_cannot_hide_behind_new_recording_group(tmp_path):
    data = manifest()
    duplicate = copy.deepcopy(data['recordings'][0])
    duplicate.update(id='renamed-copy', recordingGroup='invented-group', split='holdout')
    data['recordings'].append(duplicate)
    with pytest.raises(ManifestError, match='leakage through SHA-256'):
        load(tmp_path, data)


@pytest.mark.parametrize('path', ['../outside.mp4', '/outside.mp4', 'C:/outside.mp4',
                                  'C:outside.mp4', r'\\server\share\clip.mp4', '.', ''])
def test_media_paths_cannot_escape_data_root(tmp_path, path):
    data = manifest()
    data['recordings'][0]['path'] = path
    with pytest.raises(ManifestError):
        load(tmp_path, data)


def test_existing_symlink_cannot_escape_data_root(tmp_path):
    root = tmp_path / 'data'
    root.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    try:
        (root / 'media').symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip('OS does not permit creation of test symlinks')
    with pytest.raises(ManifestError, match='escapes data root'):
        load(tmp_path)


def test_file_verification_detects_missing_and_modified_media(tmp_path):
    data = manifest()
    with pytest.raises(ManifestError, match='missing'):
        load(tmp_path, data, verify_files=True)
    media = tmp_path / 'data' / 'media' / 'normal.mp4'
    media.parent.mkdir(parents=True)
    media.write_bytes(b'locally downloaded media')
    with pytest.raises(ManifestError, match='mismatch'):
        load(tmp_path, data, verify_files=True)
    data['recordings'][0]['sha256'] = hashlib.sha256(media.read_bytes()).hexdigest()
    assert load(tmp_path, data, verify_files=True).recordings[0].path == media


@pytest.mark.parametrize('duration', [0, -1, float('nan'), float('inf'), True])
def test_invalid_duration_is_rejected(tmp_path, duration):
    data = manifest()
    data['recordings'][0]['durationSeconds'] = duration
    with pytest.raises(ManifestError):
        load(tmp_path, data)


@pytest.mark.parametrize('event', [
    {'startSeconds': -1, 'endSeconds': 2, 'label': 0},
    {'startSeconds': 2, 'endSeconds': 2, 'label': 0},
    {'startSeconds': 3, 'endSeconds': 2, 'label': 0},
    {'startSeconds': 0, 'endSeconds': 9, 'label': 0},
    {'startSeconds': 0, 'endSeconds': 2, 'label': None},
    {'startSeconds': 0, 'endSeconds': float('nan'), 'label': 0},
])
def test_invalid_temporal_annotations_are_rejected(tmp_path, event):
    data = manifest()
    data['recordings'][0]['events'] = [event]
    with pytest.raises(ManifestError):
        load(tmp_path, data)


def test_contradictory_intervals_are_rejected_but_touching_boundaries_are_valid(tmp_path):
    data = manifest()
    data['recordings'][0].update(label=1, events=[
        {'startSeconds': 0, 'endSeconds': 4, 'label': 0},
        {'startSeconds': 3, 'endSeconds': 8, 'label': 1}])
    with pytest.raises(ManifestError, match='contradictory'):
        load(tmp_path, data)
    data['recordings'][0]['events'][1]['startSeconds'] = 4
    assert [window.label for window in generate_windows(load(tmp_path, data), 'train')] == [0, 1]


def test_sparse_positive_never_labels_the_whole_recording_or_becomes_negative(tmp_path):
    data = manifest()
    data['recordings'][0].update(label=1, durationSeconds=12, events=[
        {'startSeconds': 1, 'endSeconds': 3, 'label': 1},
        {'startSeconds': 5, 'endSeconds': 6.99, 'label': 1},
        {'startSeconds': 8, 'endSeconds': 12, 'label': 0}])
    result = load(tmp_path, data)
    assert [(window.start_seconds, window.label) for window in generate_windows(result, 'train')] == [(0, 1), (8, 0)]
    assert window_label(result.recordings[0], 4, 8) is None


def test_normal_label_does_not_fill_unannotated_gaps(tmp_path):
    data = manifest()
    data['recordings'][0]['events'] = [{'startSeconds': 0, 'endSeconds': 3.99, 'label': 0}]
    assert generate_windows(load(tmp_path, data), 'train') == ()


def test_overlapping_same_label_intervals_count_union_not_double(tmp_path):
    data = manifest()
    data['recordings'][0].update(label=1, events=[
        {'startSeconds': 0, 'endSeconds': 1.1, 'label': 1},
        {'startSeconds': .1, 'endSeconds': 1.2, 'label': 1}])
    assert generate_windows(load(tmp_path, data), 'train') == ()


def test_short_clips_are_not_stretched_and_last_full_window_covers_tail(tmp_path):
    data = manifest()
    data['recordings'][0].update(durationSeconds=3, events=[{'startSeconds': 0, 'endSeconds': 3, 'label': 0}])
    assert generate_windows(load(tmp_path, data), 'train') == ()
    data['recordings'][0].update(durationSeconds=9, events=[{'startSeconds': 0, 'endSeconds': 9, 'label': 0}])
    windows = generate_windows(load(tmp_path, data), 'train')
    assert [(window.start_seconds, window.end_seconds) for window in windows] == [(0, 4), (4, 8), (5, 9)]


@pytest.mark.parametrize('kwargs', [{'window_seconds': 0}, {'stride_seconds': -1},
                                    {'positive_fraction': .49}, {'positive_fraction': 1.1}])
def test_invalid_window_configuration_fails(tmp_path, kwargs):
    with pytest.raises(ManifestError):
        generate_windows(load(tmp_path), 'train', **kwargs)


def test_unknown_schema_fields_fail_instead_of_ignoring_annotation_typos(tmp_path):
    data = manifest()
    data['recordings'][0]['event'] = data['recordings'][0]['events']
    with pytest.raises(ManifestError, match='unknown'):
        load(tmp_path, data)
