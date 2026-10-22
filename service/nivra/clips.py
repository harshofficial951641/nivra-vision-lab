"""Ephemeral incident JPEGs. No filesystem access; owned by the service event loop."""
from collections import OrderedDict, deque
from dataclasses import dataclass, field
import time
from .signing import sign_url, verify_url


def signed_frame_url(path):
    return sign_url(path, ttl=300)


def valid_frame_signature(path, exp, sig):
    return verify_url(path, exp, sig)


@dataclass(frozen=True, slots=True)
class Frame:
    t: float
    jpeg: bytes

    @property
    def size(self):
        return len(self.jpeg) + 128  # Conservative allowance for per-reference metadata.


@dataclass(slots=True)
class Clip:
    camera: str
    peak: float
    created: float
    frames: list[Frame] = field(default_factory=list)


class Clips:
    def __init__(self, *, max_bytes=120 * 1024 * 1024, ttl=900, clock=time.time, elapsed_clock=None):
        self.max_bytes, self.ttl, self.clock = max_bytes, ttl, clock
        self.elapsed_clock = elapsed_clock or (time.monotonic if clock is time.time else clock)
        self.rings = {}
        self.clips = OrderedDict()
        self.expired = OrderedDict()
        self.bytes = 0

    def _forget(self, event_id):
        clip = self.clips.pop(event_id, None)
        if clip:
            self.bytes -= sum(f.size for f in clip.frames)
        self.expired[event_id] = None
        while len(self.expired) > 1024:
            self.expired.popitem(last=False)

    def prune(self):
        now = self.clock()
        for event_id, clip in tuple(self.clips.items()):
            if self.elapsed_clock() - clip.created >= self.ttl:
                self._forget(event_id)
        for camera, ring in tuple(self.rings.items()):
            while ring and ring[0].t < now * 1000 - 10_000:
                self.bytes -= ring.popleft().size
            if not ring:
                self.rings.pop(camera, None)

    def _cap(self):
        while self.clips and (self.bytes > self.max_bytes or len(self.clips) > 500):
            self._forget(next(iter(self.clips)))
        while self.bytes > self.max_bytes and self.rings:
            camera = min(self.rings, key=lambda c: self.rings[c][0].t)
            self.bytes -= self.rings[camera].popleft().size
            if not self.rings[camera]:
                self.rings.pop(camera)

    def receive(self, camera, jpeg):
        self.prune()
        t = self.clock() * 1000
        ring = self.rings.setdefault(camera, deque())
        if ring and t - ring[-1].t < 1000 / 6:
            return
        frame = Frame(t, jpeg)
        ring.append(frame)
        self.bytes += frame.size
        for clip in self.clips.values():
            if clip.camera == camera and clip.peak < t <= clip.peak + 8000:
                clip.frames.append(frame)
                self.bytes += frame.size
        self._cap()

    def capture(self, event_id, camera):
        self.prune()
        if event_id in self.clips or event_id in self.expired:
            return
        now = self.clock()
        frames = list(self.rings.get(camera, ()))
        self.clips[event_id] = Clip(camera, now * 1000, self.elapsed_clock(), frames)
        self.bytes += sum(f.size for f in frames)
        self._cap()

    def delete(self, event_id):
        self._forget(event_id)

    def disconnect(self, camera):
        self.bytes -= sum(f.size for f in self.rings.pop(camera, ()))

    def summary(self, event_id, *, prune=True):
        if prune: self.prune()
        clip = self.clips.get(event_id)
        status = ('recording' if self.clock() * 1000 < clip.peak + 8000 else 'ready') if clip else ('expired' if event_id in self.expired else 'none')
        return dict(status=status, frames=len(clip.frames) if clip else 0)

    def manifest(self, event_id, url):
        summary = self.summary(event_id)
        clip = self.clips.get(event_id)
        return dict(status=summary['status'], startMs=clip.peak - 10_000 if clip else None,
                    peakMs=clip.peak if clip else None, endMs=clip.peak + 8000 if clip else None,
                    frames=[dict(t=f.t, url=url(i)) for i, f in enumerate(clip.frames)] if clip else [])

    def frame(self, event_id, index):
        self.prune()
        clip = self.clips.get(event_id)
        if clip is None or not 0 <= index < len(clip.frames):
            return None
        return clip.frames[index].jpeg

    def close(self):
        self.rings.clear()
        self.clips.clear()
        self.expired.clear()
        self.bytes = 0
