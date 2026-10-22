import copy
import hashlib
import json
import sys

import pytest

import build_training_manifest as builder
from nivra.training_data import ManifestError, generate_windows, load_manifest


def inventory():
    return [
        {'id': name, 'path': f'media/{name}.mp4', 'sha256': character * 64,
         'durationSeconds': 10, 'archive': 'v_c_b_01.rar'}
        for name, character in [('normal', 'a'), ('positive', 'b'), ('ambiguous', 'c'), ('unreviewed', 'd')]
    ]


def review(recordings):
    return {'reviewMethod': '16 sampled RGB frames; provisional assistant review',
            'limitations': ['Not continuous-motion or independent ground-truth review'],
            'recordings': recordings}


def decision(recording_id, value='train-normal', **extra):
    if value == 'train-normal' and 'events' not in extra:
        extra['events'] = [{'startSeconds': 0, 'endSeconds': 4, 'label': 0}]
    return {'id': recording_id, 'decision': value, 'sceneGroup': 'visible-classroom', **extra}


def validate(tmp_path, manifest):
    path = tmp_path / 'candidate.json'
    path.write_text(json.dumps(manifest), encoding='utf-8')
    return load_manifest(path, tmp_path, verify_files=False)


def test_only_explicit_accepted_decisions_enter_training(tmp_path):
    decisions = [decision('normal'),
                 decision('positive', 'train-positive', events=[
                     {'startSeconds': 2, 'endSeconds': 6, 'label': 1}]),
                 decision('ambiguous', 'ambiguous')]
    manifest = builder.build(inventory(), [review(decisions)])
    validated = validate(tmp_path, manifest)
    assert {recording.id for recording in validated.recordings} == {'normal', 'positive'}
    assert len(generate_windows(validated, 'train')) > 0
    assert generate_windows(validated, 'calibration') == ()
    assert generate_windows(validated, 'holdout') == ()


def test_excluded_or_unreviewed_recordings_cannot_be_added_by_inventory_membership(tmp_path):
    manifest = builder.build(inventory(), [review([
        decision('normal'), decision('positive', 'exclude'), decision('ambiguous', 'ambiguous')])])
    assert [recording.id for recording in validate(tmp_path, manifest).recordings] == ['normal']


def test_partial_normal_annotations_preserve_gaps_instead_of_filling_whole_clip(tmp_path):
    intervals = [{'startSeconds': 0, 'endSeconds': 2, 'label': 0},
                 {'startSeconds': 5, 'endSeconds': 10, 'label': 0}]
    manifest = builder.build(inventory(), [review([decision('normal', events=intervals)])])
    assert manifest['recordings'][0]['events'] == intervals
    windows = generate_windows(validate(tmp_path, manifest), 'train')
    assert [(window.start_seconds, window.end_seconds, window.label) for window in windows] == [(6, 10, 0)]


@pytest.mark.parametrize('recording_id,value', [('normal', 'train-normal'), ('positive', 'train-positive')])
def test_accepted_recording_without_intervals_cannot_extrapolate_from_duration(recording_id, value):
    item = {'id': recording_id, 'decision': value, 'sceneGroup': 'sampled-only'}
    document = review([item])
    original = copy.deepcopy(document)
    with pytest.raises(ValueError, match='explicit reviewed intervals'):
        builder.build(inventory(), [document])
    assert document == original


def test_unresolved_vid_cohort_is_train_only_even_if_review_requests_another_split(tmp_path):
    manifest = builder.build(inventory(), [review([
        decision('normal', split='holdout', scene='home'),
        decision('positive', 'train-positive', split='calibration', events=[
            {'startSeconds': 0, 'endSeconds': 8, 'label': 1}])])])
    validated = validate(tmp_path, manifest)
    assert {recording.split for recording in validated.recordings} == {'train'}
    assert len({recording.recording_group for recording in validated.recordings}) == 1


@pytest.mark.parametrize('second_decision', ['train-normal', 'ambiguous', 'exclude'])
def test_duplicate_review_ids_reject_instead_of_silently_selecting_a_label(second_decision):
    reviews = [review([decision('normal')]), review([decision('normal', second_decision)])]
    with pytest.raises(ValueError, match='Duplicate review'):
        builder.build(inventory(), reviews)


@pytest.mark.parametrize('value', ['train-normal', 'train-positive', 'ambiguous', 'exclude'])
def test_unknown_review_id_is_rejected_for_every_decision(value):
    with pytest.raises(ValueError, match='[Uu]nknown|absent|inventory'):
        builder.build(inventory(), [review([decision('stale-id-from-another-inventory', value)])])


def test_duplicate_inventory_ids_reject_instead_of_overwriting_recording_provenance():
    rows = inventory()
    conflicting = copy.deepcopy(rows[0])
    conflicting.update(path='media/another-recording.mp4', sha256='e' * 64)
    with pytest.raises(ValueError, match='Duplicate inventory'):
        builder.build(rows + [conflicting], [review([decision('normal')])])


@pytest.mark.parametrize('extra', [
    {'sha256': 'f' * 64}, {'sourcePath': 'another.mp4'},
    {'sourceArchive': 'different.rar'}, {'archive': 'different.rar'},
    {'durationSeconds': 9}, {'durationSeconds': float('nan')},
])
def test_stale_review_metadata_cannot_be_silently_rebound_to_other_footage(extra):
    with pytest.raises(ValueError, match='does not match inventory'):
        builder.build(inventory(), [review([decision('normal', **extra)])])


@pytest.mark.parametrize('field,value', [('reviewMethod', ''), ('limitations', [])])
def test_review_method_and_limitations_are_required(field, value):
    document = review([decision('normal')])
    document[field] = value
    with pytest.raises(ValueError, match='method and limitations'):
        builder.build(inventory(), [document])


@pytest.mark.parametrize('item', [
    decision('normal', events=[{'startSeconds': 0, 'endSeconds': 4, 'label': 1}]),
    decision('positive', 'train-positive', events=[{'startSeconds': 0, 'endSeconds': 11, 'label': 1}]),
    decision('positive', 'train-positive', events=[
        {'startSeconds': 0, 'endSeconds': 4, 'label': 1},
        {'startSeconds': 2, 'endSeconds': 6, 'label': 0}]),
    decision('normal', events=[]),
])
def test_manifest_validator_rejects_contradictory_or_invalid_review_annotations(tmp_path, item):
    with pytest.raises(ManifestError):
        validate(tmp_path, builder.build(inventory(), [review([item])]))


def setup_cli(tmp_path, monkeypatch, rows, document):
    root = tmp_path / 'data'
    root.mkdir()
    (root / 'inventory.json').write_text(json.dumps(rows), encoding='utf-8')
    reviews = tmp_path / 'review.json'
    reviews.write_text(json.dumps(document), encoding='utf-8')
    output = tmp_path / 'published-manifest.json'
    monkeypatch.setattr(sys, 'argv', ['build_training_manifest.py', '--data-root', str(root),
                                     '--review', str(reviews), '--output', str(output)])
    return root, output


def test_failed_validation_does_not_leave_a_final_manifest(tmp_path, monkeypatch):
    document = review([decision('normal', events=[{'startSeconds': 0, 'endSeconds': 4, 'label': 1}])])
    _, output = setup_cli(tmp_path, monkeypatch, inventory(), document)
    with pytest.raises(ValueError):
        builder.main()
    assert not output.exists(), 'Only fully validated manifests may be published at the requested output path'


def test_legacy_sampled_normal_cannot_publish_full_duration_labels(tmp_path, monkeypatch):
    legacy = {'id': 'normal', 'decision': 'train-normal', 'sceneGroup': 'sampled-only'}
    _, output = setup_cli(tmp_path, monkeypatch, inventory(), review([legacy]))
    with pytest.raises(ValueError, match='unannotated time cannot be filled'):
        builder.main()
    assert not output.exists()


def test_cli_publishes_only_after_media_hash_verification(tmp_path, monkeypatch):
    content = b'known local media bytes'
    rows = inventory()[:1]
    rows[0]['sha256'] = hashlib.sha256(content).hexdigest()
    root, output = setup_cli(tmp_path, monkeypatch, rows, review([decision('normal')]))
    media = root / rows[0]['path']
    media.parent.mkdir(parents=True)
    media.write_bytes(content)
    builder.main()
    assert [row.id for row in load_manifest(output, root, verify_files=True).recordings] == ['normal']


def test_cli_merges_explicit_inventories_without_changing_original(tmp_path, monkeypatch):
    rows = inventory()[:2]
    contents = [b'normal bytes', b'positive bytes']
    for row, content in zip(rows, contents):
        row['sha256'] = hashlib.sha256(content).hexdigest()
    decisions = [decision('normal'), decision('positive', 'train-positive', events=[
        {'startSeconds': 0, 'endSeconds': 10, 'label': 1}])]
    root, output = setup_cli(tmp_path, monkeypatch, rows[:1], review(decisions))
    original = (root / 'inventory.json').read_bytes()
    extra = root / 'extra.json'
    extra.write_text(json.dumps(rows[1:]), encoding='utf-8')
    for row, content in zip(rows, contents):
        media = root / row['path']
        media.parent.mkdir(parents=True, exist_ok=True)
        media.write_bytes(content)
    monkeypatch.setattr(sys, 'argv', sys.argv + ['--inventory', str(root / 'inventory.json'),
                                               '--inventory', str(extra)])
    builder.main()
    assert len(load_manifest(output, root, verify_files=True).recordings) == 2
    assert (root / 'inventory.json').read_bytes() == original


def test_existing_output_is_preserved_on_retry(tmp_path, monkeypatch):
    _, output = setup_cli(tmp_path, monkeypatch, inventory(), review([decision('normal')]))
    output.write_text('existing approved artifact', encoding='utf-8')
    with pytest.raises(FileExistsError):
        builder.main()
    assert output.read_text(encoding='utf-8') == 'existing approved artifact'
