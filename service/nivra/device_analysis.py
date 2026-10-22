"""Strict camera-scoped reports from the original browser detector; no inference."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

MODEL = 'nivra-browser-motion-v1'
CROWD_MODEL = 'nivra-browser-rtmo-t-motion-v1'
MAX_PEOPLE = 32
MAX_REPORT_BYTES = 65536
Coordinate = Annotated[float, Field(ge=0, le=1)]
Joint = Annotated[list[Coordinate], Field(min_length=3, max_length=3)]
Skeleton = Annotated[list[Joint | None], Field(min_length=33, max_length=33)]


class Message(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, strict=True)


class DeviceStatus(Message):
    type: Literal['device-status']
    state: Literal['loading', 'ready', 'error']
    delegate: Literal['GPU', 'CPU'] | None
    detail: str = Field(max_length=240)


class DeviceMotionStatus(DeviceStatus):
    type: Literal['device-motion-status']


class Track(Message):
    id: int = Field(ge=0, le=2**31-1)
    box: list[float] = Field(min_length=4, max_length=4)

    @model_validator(mode='after')
    def bounds(self):
        x1, y1, x2, y2 = self.box
        if not all(0 <= v <= 1 for v in self.box) or x2 <= x1 or y2 <= y1:
            raise ValueError('Invalid visible region')
        return self


class Conflict(Message):
    status: Literal['warming', 'clear', 'observing', 'alert', 'limited']
    explanation: str = Field(max_length=600)


class Event(Message):
    id: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9-]+$')
    occurredAtMs: float = Field(ge=0)
    detail: str = Field(max_length=600)


class DeviceResult(Message):
    type: Literal['device-result']
    model: Literal['nivra-browser-motion-v1', 'nivra-browser-rtmo-t-motion-v1']
    delegate: Literal['GPU', 'CPU']
    timestampMs: float = Field(ge=0)
    inferenceMs: float = Field(ge=0, le=30000)
    observedPeople: int = Field(ge=0, le=MAX_PEOPLE)
    usablePeople: int = Field(ge=0, le=MAX_PEOPLE)
    tracks: list[Track] = Field(max_length=MAX_PEOPLE)
    poses: list[Skeleton] = Field(default_factory=list, max_length=MAX_PEOPLE)
    conflict: Conflict
    events: list[Event] = Field(max_length=2)

    @model_validator(mode='after')
    def consistent(self):
        if self.usablePeople > self.observedPeople or len(self.tracks) > self.observedPeople:
            raise ValueError('Inconsistent person counts')
        if len({t.id for t in self.tracks}) != len(self.tracks):
            raise ValueError('Duplicate tracks')
        if any(not 0 <= self.timestampMs - e.occurredAtMs <= 5000 for e in self.events):
            raise ValueError('Stale or future event')
        return self


class DeviceMotion(DeviceResult):
    type: Literal['device-motion']


def result_payload(report):
    return dict(timestampMs=report.timestampMs, evidenceTimestampMs=report.timestampMs,
        inferenceMs=report.inferenceMs, backend='camera-device', model=report.model,
        delegate=report.delegate,
        # This detector does not measure whole-classroom visibility.
        coverage=dict(observedPeople=report.observedPeople, analyzedPeople=report.usablePeople,
            excludedPeople=report.observedPeople-report.usablePeople, status='limited',
            actionPeople=report.usablePeople, maxPeople=MAX_PEOPLE),
        tracks=[dict(id=t.id, box=t.box, observed=True, ambiguous=True) for t in report.tracks],
        poses=report.poses,
        conflict=report.conflict.model_dump())
