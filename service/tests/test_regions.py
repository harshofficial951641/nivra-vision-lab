import numpy as np
from nivra.regions import action_view


def test_rotating_views_cover_all_corners_and_keep_correct_roi_coordinates():
    frames=[np.zeros((100,200,3),np.uint8)]*32
    people=[dict(id=1,box=[.05,.05,.2,.3]),dict(id=2,box=[.8,.7,.95,.95])]
    seen=set()
    for index in range(5):
        crops, selected, boxes=action_view(frames,people,index)
        h,w=crops[0].shape[:2]
        for person,box in zip(selected,boxes):
            seen.add(person['id'])
            assert 0<=box[0]<box[2]<=w
            assert 0<=box[1]<box[3]<=h
    assert seen=={1,2}


def test_tile_boundary_does_not_turn_a_sliver_into_a_person_region():
    frames=[np.zeros((100,100,3),np.uint8)]*32
    _,selected,_=action_view(frames,[dict(id=1,box=[.6,.6,1,1])],1)
    assert not selected
