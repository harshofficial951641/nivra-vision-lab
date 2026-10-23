"""Causal per-camera scene policy. Milliseconds; thresholds are inclusive.

This is an integration contract, not an import of service code. C1 must apply
these parameters to Decisions.scene_update and implement episode merging.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math


@dataclass(frozen=True)
class Policy:
    qualifying_threshold: float
    strong_threshold: float
    consecutive_windows: int = 2
    stride_ms: int = 1000
    cooldown_ms: int = 8000
    merge_gap_ms: int = 2000
    require_two_people: bool = False

    def __post_init__(self):
        if not 0 <= self.qualifying_threshold <= self.strong_threshold <= 1:
            raise ValueError('thresholds must satisfy 0 <= qualifying <= strong <= 1')
        if self.consecutive_windows < 1 or self.stride_ms <= 0:
            raise ValueError('positive confirmation count and stride required')
        if self.cooldown_ms < 0 or self.merge_gap_ms < self.stride_ms:
            raise ValueError('invalid cooldown or merge gap')

    def json(self):
        return asdict(self)


class CameraPolicy:
    """One instance per camera; reset on source generation / recording change."""

    def __init__(self, policy: Policy):
        self.policy = policy
        self.last_timestamp = None
        self.last_qualifying = None
        self.consecutive = 0
        self.episode_alerted = False
        self.last_alert = -math.inf

    def update(self, timestamp_ms, probability, observed_people=None):
        p = self.policy
        if not math.isfinite(timestamp_ms) or timestamp_ms < 0:
            raise ValueError('invalid timestamp')
        if self.last_timestamp is not None and timestamp_ms <= self.last_timestamp:
            raise ValueError('scores must be strictly increasing')
        if self.last_qualifying is not None and timestamp_ms - self.last_qualifying > p.merge_gap_ms:
            self.episode_alerted = False
        contiguous = self.last_timestamp is not None and timestamp_ms - self.last_timestamp <= p.stride_ms + 1e-4
        self.last_timestamp = timestamp_ms
        valid = isinstance(probability, (int, float)) and math.isfinite(probability) and 0 <= probability <= 1
        qualifies = valid and probability >= p.qualifying_threshold
        if p.require_two_people and (observed_people is None or observed_people < 2):
            qualifies = False
        if not qualifies:
            self.consecutive = 0
            return False
        self.consecutive = self.consecutive + 1 if contiguous and self.consecutive else 1
        self.last_qualifying = timestamp_ms
        confirmed = probability >= p.strong_threshold or self.consecutive >= p.consecutive_windows
        if not confirmed or self.episode_alerted or timestamp_ms - self.last_alert < p.cooldown_ms:
            return False
        self.last_alert = timestamp_ms
        self.episode_alerted = True
        return True


def simulate(windows, policy):
    state = CameraPolicy(policy)
    return [w['timestampMs'] for w in windows
            if state.update(w['timestampMs'], w['probability'], w.get('observedPeople'))]
