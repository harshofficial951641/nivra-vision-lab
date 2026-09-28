import pytest
from evaluate import validate_manifest, score_clip


def clip(**extra):
    return dict(id='a',sourceGroup='original',split='holdout',annotationStatus='reviewed',durationMs=10000,
                events=[dict(startMs=1000,endMs=2000),dict(startMs=6000,endMs=6500)],**extra)


def test_one_prediction_cannot_satisfy_two_events():
    result=score_clip(clip(),{'events':[{'occurredAtMs':2200}]})
    assert result['detected']==1 and result['missed']==1


def test_false_positives_and_late_events_are_counted():
    result=score_clip(clip(),{'events':[{'occurredAtMs':500},{'occurredAtMs':9999}]})
    assert result['falseAlerts']==2 and result['missed']==2


def test_source_and_crop_must_stay_in_one_split():
    original=clip(); crop=dict(original,id='cropped',split='calibration')
    with pytest.raises(ValueError,match='leakage'): validate_manifest([original,crop])


def test_unreviewed_annotations_cannot_be_evaluated():
    with pytest.raises(ValueError,match='Unreviewed'): validate_manifest([dict(clip(),annotationStatus='pending')])
