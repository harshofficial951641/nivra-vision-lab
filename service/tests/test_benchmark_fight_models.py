import pytest

from benchmark_fight_models import MC3Candidate, summarize, windows


def record(**extra):
    return dict(id='diagnostic', split='calibration', durationMs=20000,
                events=[dict(startMs=1000, endMs=4000)], **extra)


def test_diagnostic_alert_policy_uses_source_time_and_counts_duplicates():
    rows = [dict(timestampMs=t, fightScore=.9, inferenceMs=10)
            for t in (4000, 4400, 11999, 12000)]
    result = summarize(record(), rows)
    assert [e['occurredAtMs'] for e in result['events']] == [4000, 12000]
    assert result['metrics']['detected'] == 1
    assert result['metrics']['falseAlerts'] == 1


def test_tie_is_not_positive_and_crop_stays_separate():
    result = summarize(record(crop=[0, 0, 1, .7]),
                       [dict(timestampMs=4000, fightScore=.5, inferenceMs=10)])
    assert result['events'] == []
    assert result['metrics']['synthetic'] is True


def test_bad_checkpoint_rejected_before_deserialization(tmp_path):
    path = tmp_path/'checkpoint.pth'
    path.write_bytes(b'not a checkpoint')
    with pytest.raises(ValueError, match='checksum'):
        MC3Candidate(path, '0'*64)


def test_bad_media_rejected_before_decode(tmp_path):
    (tmp_path/'clip.mp4').write_bytes(b'wrong media')
    with pytest.raises(ValueError, match='checksum'):
        list(windows(dict(path='clip.mp4', sha256='0'*64, id='bad'), tmp_path/'corpus.json'))
