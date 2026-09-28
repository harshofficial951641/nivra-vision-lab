import numpy as np
from nivra.pipeline import Pipeline, drawable_pose


class Models:
    runtime={'action':'test'}
    hidden=False
    def detect(self,frame):
        if self.hidden: return np.empty((0,4)),np.array([])
        return np.array([[10,20,100,230],[105,20,195,230],[250,30,265,60]],np.float32),np.array([.7,.7,.99])
    def keypoints(self,frame,box):
        # No visible shoulders, hips, or legs; RGB action can still work.
        return [[.3,.3,0] for _ in range(17)]
    def actions(self,frames,boxes):
        score=np.zeros((len(boxes),80));score[:,63]=.9;return score


def test_visible_foreground_pair_survives_pose_loss_and_spectator_cap():
    pipe=Pipeline(Models());frame=np.zeros((240,320,3),np.uint8)
    for t in range(0,2200,80): result=pipe.process(frame,t,2)
    assert len(result['tracks'])==2
    assert all(p['box'][2] < .7 for p in result['tracks'])
    assert len(result['conflict']['events'])==1
    assert all(j['visibility']==0 for pose in result['poses'] for j in pose)


def test_brief_occlusion_retains_tracks_but_no_predicted_person_is_observed():
    model=Models();pipe=Pipeline(model);frame=np.zeros((240,320,3),np.uint8)
    for t in range(0,400,80): result=pipe.process(frame,t,2)
    ids={p['id'] for p in result['tracks']}
    model.hidden=True
    missing=pipe.process(frame,400,2)
    assert not missing['tracks'] and not missing['conflict']['events']
    model.hidden=False
    returning=pipe.process(frame,480,2)
    assert {p['id'] for p in returning['tracks']}==ids


def test_long_gap_clears_video_evidence_and_duplicate_timestamp_rejected():
    import pytest
    pipe=Pipeline(Models());frame=np.zeros((240,320,3),np.uint8)
    for t in range(0,1200,80): pipe.process(frame,t)
    pipe.process(frame,3000)
    assert len(pipe.frames)==1 and not pipe.actions
    with pytest.raises(ValueError): pipe.process(frame,3000)


def test_unavailable_joints_are_never_invented():
    pose=drawable_pose([[.5,.5,.9] for _ in range(17)])
    assert len(pose)==33 and pose[11]['visibility']==.9
    assert pose[19]['visibility']==0


def test_irregular_sampling_preserves_rgb_but_invalidates_joint_motion():
    model=Models();pipe=Pipeline(model);frame=np.zeros((240,320,3),np.uint8)
    for t in (0,100,200,900): result=pipe.process(frame,t)
    assert len(pipe.frames)==4
    assert result['coverage']['status']=='limited'
    assert result['coverage']['sampleIntervalMs']==700
    assert all(not value for value in pipe.frames[-1][3].values())


def test_fight_window_survives_non_integer_sampling_intervals():
    class Fight:
        calls=0
        def predict(self,frames):
            self.calls+=1
            assert len(frames)==16
            return dict(publisherScore=.1,backboneScore=.1)
    model=Models();model.fight=Fight();pipe=Pipeline(model)
    frame=np.zeros((240,320,3),np.uint8)
    for t in range(0,6500,450): pipe.process(frame,t)
    assert model.fight.calls>=3


def test_temporal_rgb_is_preserved_when_detection_jobs_are_replaced():
    class Fight:
        calls=0
        def predict(self,frames):
            self.calls+=1
            assert len(frames)==16
            # The temporal input contains values from frames that were never
            # submitted to person detection, not only seven scheduled snapshots.
            assert len({int(f[0,0,0]) for f in frames}) > 7
            return dict(publisherScore=.1,backboneScore=.1)
    model=Models();model.fight=Fight();pipe=Pipeline(model)
    frames=[(t,np.full((240,320,3),t//100,np.uint8)) for t in range(0,4300,100)]
    for t in range(0,4300,700):
        result=pipe.process(frames[t//100][1],t,video_frames=[r for r in frames if r[0]<=t])
    assert model.fight.calls==1
    assert result['coverage']['temporalSamples']==43
    assert len(pipe.frames)==7


class CrowdModels(Models):
    person_model = 'rtmo'
    def crowd_observations(self,frame):
        boxes = np.array([[x*30,y*40,x*30+20,y*40+35] for y in range(5) for x in range(10)],np.float32)
        return boxes,np.full(50,.9),np.full((50,17,3),.5)
    def keypoints(self,frame,box):
        raise AssertionError('Crowd mode must not run a pose model per person')


def test_fifty_people_use_one_shared_pose_pass_with_explicit_budget_coverage():
    pipe=Pipeline(CrowdModels());frame=np.zeros((240,320,3),np.uint8)
    for t in (0,80,160): result=pipe.process(frame,t,50)
    assert len(result['tracks'])==50
    assert result['coverage']['excludedPeople']==0
    limited=pipe.process(frame,240,8)
    assert limited['coverage']['excludedPeople']==42
    assert limited['conflict']['status']=='limited'
