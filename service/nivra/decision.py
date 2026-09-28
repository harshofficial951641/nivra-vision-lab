"""Temporal review decisions; scores are not calibrated violence probabilities."""
from dataclasses import dataclass


def interaction_distance(a, b):
    """Box edge gap in two dimensions, normalized to the smaller person."""
    dx = max(0, a[0] - b[2], b[0] - a[2])
    dy = max(0, a[1] - b[3], b[1] - a[3])
    scale = max(.01, min(max(a[2]-a[0], a[3]-a[1]), max(b[2]-b[0], b[3]-b[1])))
    return (dx*dx + dy*dy)**.5 / scale


@dataclass(frozen=True)
class Thresholds:
    hit: float = .55
    push: float = .6
    supported_hit: float = .35
    cooldown_ms: int = 8000


class Decisions:
    def __init__(self, thresholds=Thresholds()):
        self.thresholds = thresholds
        self.last_event = {}
        self.events = []
        self.sequence = 0
        self.incidents = []
        self.scene_confirmation = None
        self.last_scene_event = -1e10

    def scene_update(self, timestamp, people, score, evidence_start):
        """Whole-scene classifier evidence cannot identify an actor or target."""
        if not valid_score(score) or score < .4 or not 0 <= evidence_start < timestamp or len([p for p in people if p['observed']]) < 2:
            self.scene_confirmation = None
            return False
        prior = self.scene_confirmation
        self.scene_confirmation = timestamp
        confirmed = score >= .7 or (prior is not None and 0 < timestamp-prior <= 1000)
        recent = self.events and timestamp-self.events[0]['occurredAtMs'] < self.thresholds.cooldown_ms
        if not confirmed or recent or timestamp-self.last_scene_event < self.thresholds.cooldown_ms:
            return False
        self.sequence += 1
        self.last_scene_event = timestamp
        self.events.insert(0, {'id': f'local-conflict-{self.sequence}', 'type': 'physical-conflict',
                              'title': 'Possible physical conflict', 'objectName': 'Scene interaction',
                              'occurredAtMs': timestamp, 'evidenceTimestampMs': timestamp,
                              'evidenceStartMs': evidence_start, 'evidenceModel': 'x3d-rwf2000-candidate',
                              'detail': 'Experimental fight-classifier evidence in the video window. Actor and target are not identified; inspect the live scene.'})
        self.events = self.events[:6]
        return True

    def update(self, timestamp, people, actions, evidence_ms, motion):
        signals, regions = [], []
        fresh = 0 <= timestamp - evidence_ms <= 1800
        self.incidents = [incident for incident in self.incidents if timestamp - incident['time'] < self.thresholds.cooldown_ms]
        eligible = [p for p in people if p['observed']]
        for actor in eligible:
            score = actions.get(actor['id']) if fresh else None
            if score is None:
                continue
            a = actor['box']
            targets = [p for p in eligible if p['id'] != actor['id'] and
                       interaction_distance(a, p['box']) <= .4]
            if not targets:
                continue
            # AVA IDs are one-indexed; model output is zero-indexed.
            hit, push = float(score[63]), float(score[75])
            supported = motion.get(actor['id'], False) and not actor['ambiguous']
            # Strong RGB evidence can still flag an overlapping interaction. It
            # attributes no actor identity and never uses ambiguous joint motion.
            minimum_hit = max(.7, self.thresholds.hit) if actor['ambiguous'] else self.thresholds.hit
            qualifies = hit >= minimum_hit or (supported and hit >= self.thresholds.supported_hit) or (supported and push >= self.thresholds.push)
            if not qualifies:
                continue
            target = min(targets, key=lambda p: interaction_distance(a, p['box']))
            # Ambiguity cannot give every interaction in a classroom one global key.
            pair = tuple(sorted([actor['id'], target['id']]))
            signals = ['Video action: possible hit' if hit >= self.thresholds.supported_hit else 'Video action: possible push']
            if supported:
                signals.append('Supporting visible arm motion')
            regions = [actor['box'], target['box']]
            ids = {actor['id'], target['id']}
            union = [min(b[0] for b in regions), min(b[1] for b in regions), max(b[2] for b in regions), max(b[3] for b in regions)]
            def same_region(other):
                intersect = max(0,min(union[2],other[2])-max(union[0],other[0])) * max(0,min(union[3],other[3])-max(union[1],other[1]))
                area = (union[2]-union[0])*(union[3]-union[1]) + (other[2]-other[0])*(other[3]-other[1]) - intersect
                return intersect / max(area,1e-6) > .5
            if any(ids.intersection(old['ids']) or same_region(old['region']) for old in self.incidents):
                continue
            if timestamp - self.last_event.get(pair, -1e10) < self.thresholds.cooldown_ms:
                continue
            self.last_event[pair] = timestamp
            self.incidents.append(dict(time=timestamp,ids=ids,region=union))
            self.sequence += 1
            self.events.insert(0, {'id': f'local-conflict-{self.sequence}', 'type': 'physical-conflict',
                                  'title': 'Possible physical conflict', 'objectName': 'Two-person interaction',
                                  'occurredAtMs': timestamp, 'evidenceTimestampMs': evidence_ms,
                                  'detail': 'Local video action evidence. Experimental; review the scene before responding.'})
            self.events = self.events[:6]
        self.last_event = {k: v for k, v in self.last_event.items() if timestamp - v < 30000}
        return signals, regions


def valid_score(score):
    import math
    return isinstance(score, (int, float)) and math.isfinite(score) and 0 <= score <= 1
