"""One sender per viewer, with a bounded latest-only mailbox in RAM."""
import asyncio
from collections import deque
import json
import struct
import time

SEND_TIMEOUT_SECONDS = 2


class PreviewRelay:
    def __init__(self, socket, on_failure):
        self.socket = socket
        self.on_failure = on_failure
        self.pending = {}
        self.video = {}
        self.video_waiting = set()
        self.closed = False
        self.wake = asyncio.Event()
        self.task = asyncio.create_task(self.run())

    def offer(self, key, value, binary=False):
        if self.closed: return
        # Keys are one snapshot plus at most four registered camera IDs.
        self.pending[key] = (value, binary, time.monotonic())
        self.wake.set()

    def discard(self, key):
        self.pending.pop(key, None)
        self.video.pop(key, None)
        self.video_waiting.discard(key)
        if not self.pending and not self.video: self.wake.clear()

    def offer_video(self, camera_id, value):
        """H264 deltas need ordered delivery; bound slow viewers independently."""
        if self.closed: return
        keyframe = self.has_keyframe(value)
        if camera_id in self.video_waiting:
            if not keyframe: return
            self.video_waiting.discard(camera_id)
        queue = self.video.setdefault(camera_id, deque())
        queue.append((value, time.monotonic()))
        if len(queue) > 40 or sum(len(entry[0]) for entry in queue) > 2_000_000:
            queue.clear()
            if keyframe: queue.append((value,time.monotonic()))
            else:
                self.video.pop(camera_id,None)
                self.video_waiting.add(camera_id)
        self.wake.set()

    @staticmethod
    def has_keyframe(value):
        try:
            size = struct.unpack('<I',value[:4])[0]
            return any(frame.get('keyframe') is True for frame in json.loads(value[4:4+size])['frames'])
        except (ValueError,KeyError,TypeError,struct.error): return False

    async def close(self):
        self.closed = True
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            pass
        self.pending.clear()
        self.video.clear()
        self.video_waiting.clear()

    async def run(self):
        try:
            while not self.closed:
                await self.wake.wait()
                # Replacing a value preserves its place, so cameras get fair turns.
                if self.pending:
                    key = next(iter(self.pending))
                    value, binary, offered = self.pending.pop(key)
                    compressed = False
                elif self.video:
                    key = next(iter(self.video))
                    queue = self.video.pop(key)
                    value, offered = queue.popleft()
                    if queue: self.video[key] = queue
                    binary = True
                    compressed = True
                else:
                    self.wake.clear()
                    continue
                if not self.pending and not self.video:
                    self.wake.clear()
                if binary and time.monotonic() - offered > .5:
                    if compressed:
                        self.video.pop(key,None)
                        self.video_waiting.add(key)
                    continue
                await asyncio.wait_for(
                    self.socket.send_bytes(value) if binary else self.socket.send_json(value), SEND_TIMEOUT_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception:
            self.closed = True
            self.pending.clear()
            self.video.clear()
            self.on_failure()
            try:
                await asyncio.wait_for(self.socket.close(code=1013), .5)
            except Exception:
                pass
