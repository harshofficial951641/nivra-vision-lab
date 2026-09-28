"""One sender per viewer, with a bounded latest-only mailbox in RAM."""
import asyncio
import time


class PreviewRelay:
    def __init__(self, socket, on_failure):
        self.socket = socket
        self.on_failure = on_failure
        self.pending = {}
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
        if not self.pending: self.wake.clear()

    async def close(self):
        self.closed = True
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            pass
        self.pending.clear()

    async def run(self):
        try:
            while not self.closed:
                await self.wake.wait()
                # Replacing a value preserves its place, so cameras get fair turns.
                key = next(iter(self.pending))
                value, binary, offered = self.pending.pop(key)
                if not self.pending:
                    self.wake.clear()
                if binary and time.monotonic() - offered > .5:
                    continue
                await asyncio.wait_for(
                    self.socket.send_bytes(value) if binary else self.socket.send_json(value), .5)
        except asyncio.CancelledError:
            raise
        except Exception:
            self.closed = True
            self.pending.clear()
            self.on_failure()
            try:
                await asyncio.wait_for(self.socket.close(code=1013), .5)
            except Exception:
                pass
