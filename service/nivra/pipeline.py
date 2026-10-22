from collections import deque
from time import perf_counter
import os
import numpy as np
import supervision as sv
from .decision import Decisions
from .models import iou
from .regions import action_view

# COCO-17 to the existing drawing topology. Unavailable landmarks stay invisible.
COCO_TO_MP = {0: 0, 1: 2, 2: 5, 3: 7, 4: 8, 5: 11, 6: 12, 7: 13, 8: 14,
              9: 15, 10: 16, 11: 23, 12: 24, 13: 25, 14: 26, 15: 27, 16: 28}


def drawable_pose(keypoints):
    result = [dict(x=0, y=0, z=0, visibility=0, presence=0) for _ in range(33)]
    for source, target in COCO_TO_MP.items():
        x, y, score = keypoints[source]
        result[target] = dict(x=x, y=y, z=0, visibility=score, presence=score)
    return result


class Pipeline:
    def __init__(self, models, regional_actions=None):
        self.models = models
        self.regional_actions = regional_actions if regional_actions is not None else os.environ.get('NIVRA_ACTION_REGIONS') == '1'
        self.reset()

    def reset(self):
        self.tracker = sv.ByteTrack(track_activation_threshold=.35, lost_track_buffer=30, frame_rate=15,
                                    minimum_consecutive_frames=2)
        self.frames = deque(maxlen=64)
        self.previous = {}
        self.decisions = Decisions()
        self.last_timestamp = -1
        self.last_action = -1e9
        self.last_dimensions = None
        self.actions = {}
        self.evidence_ms = -1e9
        self.region_index = 0
        self.last_fight = -1e9
        self.fight_evidence = None

    def process(self, frame, timestamp, max_people=4, video_frames=None):
        start = perf_counter()
        if timestamp <= self.last_timestamp:
            raise ValueError('Frame timestamps must increase within a stream.')
        gap = timestamp - self.last_timestamp
        dimensions = frame.shape[:2]
        if self.last_timestamp >= 0 and (gap > 1200 or self.last_dimensions != dimensions):
            # Never carry velocities or action windows across missing observations.
            old_events = self.decisions.events
            self.reset()
            self.decisions.events = old_events
            self.decisions.sequence = max([int(e['id'].split('-')[-1]) for e in old_events], default=0)
        elif gap > 600:
            # Irregular scheduling invalidates joint velocity, not every observed
            # RGB frame in the previous four seconds. Coverage reports the gap.
            self.previous.clear()
        self.last_dimensions = dimensions
        self.last_timestamp = timestamp
        crowd = getattr(self.models, 'person_model', 'yolox') == 'rtmo'
        if crowd:
            boxes, scores, keypoints = self.models.crowd_observations(frame)
        else:
            boxes, scores = self.models.detect(frame)
        detections = sv.Detections(xyxy=boxes.astype(np.float32), confidence=scores.astype(np.float32),
                                   class_id=np.zeros(len(boxes), dtype=int),
                                   data={'keypoints': keypoints} if crowd else {})
        tracked = self.tracker.update_with_detections(detections)
        h, w = dimensions
        people, motion = [], {}
        # A confidence-only cap can select spectators over the foreground pair.
        areas = np.prod(np.maximum(0, tracked.xyxy[:, 2:] - tracked.xyxy[:, :2]), axis=1)
        order = np.argsort(-(tracked.confidence * np.sqrt(areas)))[:max_people]
        for index in order:
            box = tracked.xyxy[index]
            track_id = int(tracked.tracker_id[index])
            ambiguous = any(i != index and iou(box, other) > .45 for i, other in enumerate(tracked.xyxy))
            keypoints = tracked.data['keypoints'][index].tolist() if crowd else self.models.keypoints(frame, box)
            prior = self.previous.get(track_id)
            support = False
            if prior and not ambiguous and not prior['ambiguous'] and 0 < timestamp - prior['time'] <= 250:
                dt = (timestamp - prior['time']) / 1000
                scale = max(.1, (box[3] - box[1]) / h)
                for shoulder, wrist in ((5, 9), (6, 10)):
                    if min(keypoints[shoulder][2], keypoints[wrist][2], prior['keypoints'][shoulder][2], prior['keypoints'][wrist][2]) < .55:
                        continue
                    before = np.array(prior['keypoints'][wrist][:2]) - prior['keypoints'][shoulder][:2]
                    after = np.array(keypoints[wrist][:2]) - keypoints[shoulder][:2]
                    speed = np.linalg.norm((after - before) * [w / h, 1]) / scale / dt
                    support |= .8 <= speed <= 8
            motion[track_id] = bool(support)
            self.previous[track_id] = dict(keypoints=keypoints, ambiguous=ambiguous, time=timestamp)
            people.append(dict(id=track_id, box=(box / [w, h, w, h]).tolist(), observed=True,
                               ambiguous=ambiguous, keypoints=keypoints,
                               partial=bool(box[0] <= 2 or box[1] <= 2 or box[2] >= w-2 or box[3] >= h-2)))
        self.previous = {k: v for k, v in self.previous.items() if timestamp - v['time'] < 2000}
        # Small RGB windows are sufficient for the 256-short-side action network.
        import cv2
        factor = min(1, (960 if self.regional_actions else 456) / max(h, w))
        small = cv2.resize(frame, (round(w * factor), round(h * factor)))
        self.frames.append((timestamp, small, people, motion))
        while self.frames and timestamp - self.frames[0][0] > (4500 if getattr(self.models, 'fight', None) else 2200):
            self.frames.popleft()
        # The multi-camera service retains captured RGB independently of the
        # detection queue. Dropping obsolete detection jobs must not discard the
        # observed motion frames required by the temporal models.
        rgb = [(t,image) for t,image in (video_frames or [(r[0],r[1]) for r in self.frames]) if 0 <= timestamp-t <= 4500]
        video = [(t,image) for t,image in rgb if timestamp-t <= 2200]
        fresh_action = False
        action_motion = {}
        if getattr(self.models, 'fight_model', 'ava') != 'x3d' and timestamp - self.last_action >= 400 and len(video) >= 8 and timestamp - video[0][0] >= 1600:
            records = [record for record in self.frames if timestamp-record[0] <= 2200]
            times = np.linspace(video[0][0], timestamp, 32)
            chosen = [min(video, key=lambda r: abs(r[0] - t)) for t in times]
            anchor = min(records,key=lambda r:abs(r[0]-times[16]))
            current_ids = {p['id'] for p in people}
            # An actor box too far from the action keyframe is not a valid ROI.
            if abs(anchor[0]-times[16]) > 600: current_ids = set()
            observed = [p for p in anchor[2] if p['id'] in current_ids]
            sh, sw = small.shape[:2]
            frames = [cv2.resize(record[1],(sw,sh)) if record[1].shape[:2] != (sh,sw) else record[1] for record in chosen]
            boxes = [np.array(p['box']) * [sw, sh, sw, sh] for p in observed]
            if self.regional_actions:
                frames, observed, boxes = action_view(frames, observed, self.region_index)
                self.region_index += 1
            scores = self.models.actions(frames, boxes)
            self.actions = {p['id']: score for p, score in zip(observed, scores)}
            # Ambiguity anywhere in the action window invalidates joint support.
            ambiguous_ids = {p['id'] for r in records for p in r[2] if p['ambiguous']}
            action_motion = {p['id']: p['id'] not in ambiguous_ids and any(r[3].get(p['id'], False) for r in records) for p in observed}
            self.evidence_ms = anchor[0]
            self.last_action = timestamp
            fresh_action = True
        # A cached action result may be displayed but may never issue another decision.
        signals, regions = self.decisions.update(timestamp, people, self.actions if fresh_action else {},
                                                  self.evidence_ms, action_motion)
        if getattr(self.models, 'fight', None) and timestamp-self.last_fight >= 400 and len(rgb) >= 8 and timestamp-rgb[0][0] >= 3800:
            # Sample by source time, not frame index: camera scheduling is uneven.
            targets = np.linspace(max(rgb[0][0], timestamp-4000), timestamp, 16)
            sampled = [min(rgb,key=lambda record:abs(record[0]-target)) for target in targets]
            self.fight_evidence = dict(self.models.fight.predict([r[1] for r in sampled]),
                                       startMs=sampled[0][0], endMs=timestamp, model='x3d-rwf2000-candidate')
            self.decisions.scene_update(timestamp,people,self.fight_evidence['publisherScore'],self.fight_evidence['startMs'])
            self.last_fight = timestamp
            if getattr(self.models, 'fight_model', 'ava') == 'x3d':
                self.evidence_ms = timestamp
        recent = bool(self.decisions.events and timestamp - self.decisions.events[0]['occurredAtMs'] < 4000)
        excluded = max(0, len(tracked) - len(people))
        action_people = sum(p['id'] in self.actions for p in people)
        partial_action = getattr(self.models, 'fight_model', 'ava') != 'x3d' and self.evidence_ms >= 0 and action_people < len(people)
        sparse = gap > 600
        limited = len(people) < 2 or excluded > 0 or partial_action or sparse or any(p['ambiguous'] for p in people)
        status = 'alert' if recent else 'limited' if limited else 'warming' if self.evidence_ms < 0 else 'clear'
        explanation = ('Review the observed physical interaction.' if recent else
                       'Overlapping tracks are ambiguous; individual motion evidence is paused.' if any(p['ambiguous'] for p in people) else
                       'Waiting for two observable people.' if len(people) < 2 else
                       'Sparse video observations; motion between sampled frames may be missed.' if sparse else
                       f'{excluded} tracked people exceed the configured analysis budget; coverage is incomplete.' if excluded else
                       'The latest action window covers only part of the tracked scene; other regions are awaiting analysis.' if partial_action else
                       'Collecting a short video window.' if self.evidence_ms < 0 else
                       'No qualifying physical action in the latest analyzed window. Experimental model.')
        poses = [drawable_pose(p['keypoints']) for p in people if not p['ambiguous']]
        latency = (perf_counter() - start) * 1000
        conflict = dict(status=status, people=len(people), progress=1 if recent else 0,
                        signals=signals, explanation=explanation, events=self.decisions.events,
                        regions=[dict(x=b[0], y=b[1], width=b[2]-b[0], height=b[3]-b[1]) for b in regions],
                        diagnostics=dict(detectedPoses=len(people), usablePeople=sum(not p['ambiguous'] for p in people),
                                         upperBodyOnlyPeople=sum(p['partial'] for p in people), visibleArms=0, usableArms=0,
                                         nearbyPairs=len(people)*(len(people)-1)//2, requiredPulses=1,
                                         reason='ready' if not limited else 'single-person' if len(people)<2 else 'stale'))
        return dict(version=1, backend='local-ai', timestampMs=timestamp, evidenceTimestampMs=max(0, self.evidence_ms),
                    inferenceMs=latency, poseInferenceMs=latency, objectInferenceMs=0, objectTimestampMs=None,
                    posesFresh=True, objectsFresh=False, poses=poses, objects=[], tracks=people, conflict=conflict,
                    runtime=self.models.runtime, experimental=True,
                    fightEvidence=self.fight_evidence,
                    coverage=dict(observedPeople=len(tracked), analyzedPeople=len(people), excludedPeople=excluded,
                                  status='limited' if limited else 'analyzing', personLimit=max_people,
                                  sampleIntervalMs=gap, temporalSamples=len(rgb),
                                  actionView='rotating-regions' if self.regional_actions else 'full-frame',
                                  actionPeople=action_people, actionEvidenceTimestampMs=max(0,self.evidence_ms)),
                    actions=[dict(trackId=k, hit=float(v[63]), push=float(v[75]), grab=float(v[65])) for k,v in self.actions.items()])

