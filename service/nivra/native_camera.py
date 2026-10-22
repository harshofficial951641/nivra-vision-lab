"""Bounded reports from an authenticated native phone. No model runs here."""
import base64
import binascii
import json
import struct
from typing import Literal

from pydantic import Field, model_validator
from .device_analysis import Message, Track, Skeleton

FIGHT_MODEL = 'nivra-x3d-rwf2000-v1'
MAX_VIDEO_BYTES = 3_000_000


class NativePeople(Message):
    type: Literal['native-people-v1']
    model: Literal['apple-vision-body-pose']
    timestampMs: float = Field(ge=0)
    inferenceMs: float = Field(ge=0, le=30000)
    observedPeople: int = Field(ge=0, le=32)
    posePeople: int = Field(ge=0, le=32)
    tracks: list[Track] = Field(max_length=32)
    poses: list[Skeleton] = Field(max_length=32)

    @model_validator(mode='after')
    def counts(self):
        if len(self.tracks) != self.observedPeople or len(self.poses) != self.posePeople:
            raise ValueError('Inconsistent native observations')
        if len({track.id for track in self.tracks}) != len(self.tracks):
            raise ValueError('Duplicate native observation labels')
        return self


class NativeFight(Message):
    type: Literal['native-fight-v1']
    model: Literal['nivra-x3d-rwf2000-v1']
    timestampMs: float = Field(ge=0)
    windowStartMs: float = Field(ge=0)
    windowEndMs: float = Field(ge=0)
    uniqueFrames: int = Field(ge=8, le=16)
    inferenceMs: float = Field(ge=0, le=30000)
    publisherScore: float = Field(ge=0, le=1)
    modelScore: float = Field(ge=0, le=1)
    windowReady: Literal[True]

    @model_validator(mode='after')
    def window(self):
        if not 3800 <= self.windowEndMs-self.windowStartMs <= 4500 or self.windowEndMs != self.timestampMs:
            raise ValueError('A real four-second source window is required')
        return self


class NativeAnalysis(Message):
    type: Literal['native-analysis-v1']
    state: Literal['loading', 'ready', 'error']
    detail: str = Field(max_length=240)
    people: NativePeople | None = None
    fight: NativeFight | None = None


def payload(people, fight):
    """Keep scene classification separate from observed, frame-local skeletons."""
    timestamp = people.timestampMs if people else fight.timestampMs
    count = max(people.observedPeople, people.posePeople) if people else 0
    ready = fight is not None and people is not None and abs(fight.timestampMs-people.timestampMs) <= 1500
    return dict(timestampMs=timestamp, evidenceTimestampMs=fight.timestampMs if fight else timestamp,
        inferenceMs=people.inferenceMs if people else fight.inferenceMs,
        backend='camera-device', model=FIGHT_MODEL, delegate='iOS',
        coverage=dict(observedPeople=count, analyzedPeople=people.posePeople if people else 0,
            excludedPeople=max(0,count-(people.posePeople if people else 0)), status='limited',
            actionPeople=count if ready else 0, maxPeople=32),
        tracks=[dict(id=t.id,box=t.box,observed=True,ambiguous=True) for t in people.tracks] if people else [],
        poses=people.poses if people else [],
        conflict=dict(status='observing' if ready else 'warming', explanation=
            'Phone video model is checking the scene. Review any alert before responding.' if ready else
            'Collecting a four-second video window on the phone.'),
        fightEvidence=dict(publisherScore=fight.publisherScore, modelScore=fight.modelScore,
            startMs=fight.windowStartMs,endMs=fight.windowEndMs,model=FIGHT_MODEL) if fight else None)


def _decode(value, limit):
    if not isinstance(value, str) or len(value) > limit*4//3+8:
        raise ValueError('Invalid encoded video size')
    try: decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error): raise ValueError('Invalid encoded video') from None
    if not 0 < len(decoded) <= limit: raise ValueError('Invalid video size')
    return decoded


def video_packet(data, camera_id, generation, *, after=-1, last_timestamp=-1):
    """Validate the native AVCC batch and convert base64 to one binary packet."""
    expected = {'version','generation','codec','description','width','height','frames'}
    if not isinstance(data, dict) or set(data) != expected or type(data['version']) is not int or data['version'] != 1:
        raise ValueError('Unsupported native video')
    import re
    if not isinstance(data['generation'], str) or not re.fullmatch(r'[A-Za-z0-9-]{1,64}', data['generation']):
        raise ValueError('Invalid video generation')
    if not isinstance(data['codec'], str) or not re.fullmatch(r'avc1\.[0-9a-fA-F]{6}',data['codec']):
        raise ValueError('Invalid video codec')
    if any(type(data[k]) is not int or not 32 <= data[k] <= 1280 for k in ('width','height')):
        raise ValueError('Invalid video dimensions')
    description = _decode(data['description'],4096)
    if len(description) < 7 or description[0] != 1 or description[4]&3 != 3:
        raise ValueError('Expected four-byte AVCC NAL lengths')
    if data['codec'].lower() != 'avc1.'+description[1:4].hex():
        raise ValueError('Video codec differs from configuration')
    frames, binary = [], bytearray()
    if not isinstance(data['frames'],list) or not 1 <= len(data['frames']) <= 90:
        raise ValueError('Invalid video batch')
    import math
    for frame in data['frames']:
        if not isinstance(frame,dict) or set(frame) != {'sequence','timestampMs','keyframe','data'}:
            raise ValueError('Invalid video frame')
        sequence, timestamp = frame['sequence'], frame['timestampMs']
        if type(sequence) is not int or not 0 <= sequence < 2**53 or type(timestamp) not in (int,float) or not math.isfinite(timestamp) or timestamp < 0 or type(frame['keyframe']) is not bool:
            raise ValueError('Invalid video clock')
        if sequence <= after or timestamp <= last_timestamp: raise ValueError('Video clocks must increase')
        encoded = _decode(frame['data'],1_000_000)
        offset = 0
        while offset < len(encoded):
            if len(encoded)-offset < 4: raise ValueError('Truncated AVCC length')
            size = struct.unpack('>I',encoded[offset:offset+4])[0]
            if not 0 < size <= len(encoded)-offset-4: raise ValueError('Truncated AVCC NAL')
            offset += 4+size
        if len(binary)+len(encoded) > 2_000_000: raise ValueError('Video batch too large')
        frames.append(dict(sequence=sequence,timestampMs=timestamp,keyframe=frame['keyframe'],offset=len(binary),length=len(encoded)))
        binary.extend(encoded)
        after,last_timestamp = sequence,timestamp
    metadata = json.dumps(dict(encoding='h264',cameraId=camera_id,generation=generation,
        videoGeneration=data['generation'],width=data['width'],height=data['height'],codec=data['codec'],
        description=data['description'],frames=frames),separators=(',',':')).encode()
    if len(metadata) > 24000: raise ValueError('Video metadata too large')
    return struct.pack('<I',len(metadata))+metadata+binary, after, last_timestamp
