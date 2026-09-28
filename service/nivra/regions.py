"""Deterministic overlapping action views, independent of foreground size."""
import numpy as np

VIEWS = ((0,0,1,1), (0,0,.65,.65), (.35,0,1,.65), (0,.35,.65,1), (.35,.35,1,1))


def action_view(frames, people, index):
    """Cycle full scene and four overlapping views; never fabricate hidden pixels."""
    h,w = frames[0].shape[:2]
    x,y,right,bottom = VIEWS[index % len(VIEWS)]
    x,y,right,bottom = round(x*w),round(y*h),round(right*w),round(bottom*h)
    selected, boxes = [], []
    for person in people:
        box = np.asarray(person['box']) * [w,h,w,h]
        clipped = np.array([max(x,box[0]),max(y,box[1]),min(right,box[2]),min(bottom,box[3])])
        area = np.maximum(0,clipped[2:]-clipped[:2]).prod()
        original = np.maximum(0,box[2:]-box[:2]).prod()
        if original <= 0 or area/original < .7:
            continue
        selected.append(person)
        boxes.append(clipped - [x,y,x,y])
    return [frame[y:bottom,x:right] for frame in frames], selected, boxes
