import numpy as np
from nivra.decision import Decisions


def people(ambiguous=False):
    return [dict(id=1, box=[.1,.1,.5,.9], observed=True, ambiguous=ambiguous),
            dict(id=2, box=[.4,.1,.8,.9], observed=True, ambiguous=ambiguous)]


def scores(hit=0, grab=0, push=0):
    result = np.zeros(80)
    result[63], result[65], result[75] = hit, grab, push
    return {1: result}


def test_single_strong_hit_needs_no_complete_skeleton():
    engine = Decisions()
    engine.update(2000, people(), scores(hit=.8), 1100, {})
    assert len(engine.events) == 1


def test_grabbing_and_neutral_overlap_stay_quiet():
    engine = Decisions()
    engine.update(2000, people(True), scores(grab=.99), 1100, {1: True})
    assert not engine.events


def test_ambiguous_motion_cannot_support_a_weak_action():
    engine = Decisions()
    engine.update(2000, people(True), scores(hit=.4, push=.9), 1100, {1: True})
    assert not engine.events


def test_strong_video_evidence_survives_overlap_without_actor_attribution():
    engine = Decisions()
    engine.update(2000, people(True), scores(hit=.8), 1100, {})
    assert len(engine.events) == 1
    engine.update(2500, [dict(p, id=p['id']+10) for p in people(True)], {11: scores(hit=.8)[1]}, 1500, {})
    assert len(engine.events) == 1


def test_predicted_or_single_people_never_trigger():
    for candidates in (people()[:1], [dict(p, observed=False) for p in people()]):
        engine = Decisions()
        engine.update(2000, candidates, scores(hit=.99), 1100, {})
        assert not engine.events


def test_stale_or_future_evidence_never_triggers():
    for time in (0, 3000):
        engine = Decisions()
        engine.update(2000, people(), scores(hit=.99), time, {})
        assert not engine.events


def test_pair_cooldown_and_distinct_pair():
    engine = Decisions()
    engine.update(2000, people(), scores(hit=.8), 1100, {})
    engine.update(2400, people(), scores(hit=.8), 1500, {})
    assert len(engine.events) == 1
    other = [dict(p, id=p['id']+2, box=[v+2 if i%2==0 else v for i,v in enumerate(p['box'])]) for p in people()]
    engine.update(2600, other, {3: scores(hit=.8)[1]}, 1700, {})
    assert len(engine.events) == 2


def test_track_id_switch_does_not_duplicate_the_same_incident():
    engine = Decisions()
    engine.update(2000, people(), scores(hit=.8), 1100, {})
    engine.update(2500, [dict(p,id=p['id']+10) for p in people()], {11:scores(hit=.8)[1]}, 1500, {})
    assert len(engine.events)==1


def test_separate_ambiguous_interactions_do_not_share_a_room_wide_cooldown():
    engine = Decisions()
    left = [dict(p, box=[v*.3 for v in p['box']]) for p in people(True)]
    right = [dict(p, id=p['id']+10, box=[v+.65 for v in p['box']]) for p in left]
    engine.update(2000, left + right, {1:scores(hit=.9)[1],11:scores(hit=.9)[1]}, 1100, {})
    assert len(engine.events) == 2


def test_separate_classroom_rows_do_not_form_an_interacting_pair():
    engine = Decisions()
    candidates = [dict(id=1,box=[.2,.1,.3,.25],observed=True,ambiguous=False),
                  dict(id=2,box=[.2,.7,.3,.85],observed=True,ambiguous=False)]
    engine.update(2000,candidates,scores(hit=.99),1100,{})
    assert not engine.events


def test_scene_classifier_is_not_actor_attribution_and_deduplicates():
    engine = Decisions()
    assert not engine.scene_update(4000,people(True),.6,0)
    assert engine.scene_update(4400,people(True),.6,400)
    assert engine.events[0]['objectName']=='Scene interaction'
    assert 'not identified' in engine.events[0]['detail']
    assert not engine.scene_update(4800,people(True),.9,800)
    assert len(engine.events)==1


def test_scene_classifier_requires_observed_people_and_finite_current_evidence():
    for score in (float('nan'),float('inf'),-.1,1.1,.2):
        engine=Decisions()
        assert not engine.scene_update(4000,people(),score,0)
    engine=Decisions()
    assert not engine.scene_update(4000,[dict(p,observed=False) for p in people()],.9,0)
    assert not engine.scene_update(4000,people(),.9,5000)


def test_single_strong_scene_window_can_trigger_without_repeated_hits():
    engine=Decisions()
    assert engine.scene_update(4000,people(),.71,0)
