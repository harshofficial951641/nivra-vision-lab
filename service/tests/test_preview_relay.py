import asyncio
import json
import struct
from nivra.preview_relay import PreviewRelay


def test_slow_viewer_keeps_latest_per_camera_and_serializes_sends():
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        sent = []

        class Socket:
            async def send_bytes(self, value):
                sent.append(value)
                if value == b'first':
                    entered.set()
                    await release.wait()

            async def send_json(self, value): sent.append(value)

        relay = PreviewRelay(Socket(), lambda: None)
        relay.offer('a', b'first', True)
        await entered.wait()
        for n in range(100):
            relay.offer('a', str(n).encode(), True)
            relay.offer('b', b'other camera', True)
            relay.offer('snapshot', {'latest': n})
        relay.offer('disconnected-camera', b'stale frame', True)
        relay.discard('disconnected-camera')
        assert len(relay.pending) == 3
        assert sent == [b'first']  # no concurrent websocket sends
        release.set()
        for _ in range(20):
            await asyncio.sleep(0)
            if len(sent) == 4: break
        assert sent == [b'first', b'99', b'other camera', {'latest': 99}]
        await relay.close()
        assert not relay.pending
    asyncio.run(run())


def test_stalled_viewer_is_removed_without_blocking_healthy_viewer():
    async def run():
        delivered, removed, closed = asyncio.Event(), asyncio.Event(), asyncio.Event()

        class Stalled:
            async def send_bytes(self, value): await asyncio.Event().wait()
            async def close(self, code):
                assert code == 1013
                closed.set()

        class Healthy:
            async def send_bytes(self, value): delivered.set()

        slow = PreviewRelay(Stalled(), removed.set)
        fast = PreviewRelay(Healthy(), lambda: None)
        slow.offer('a', b'frame', True)
        fast.offer('a', b'frame', True)
        await asyncio.wait_for(delivered.wait(), .1)
        assert not removed.is_set()
        await asyncio.wait_for(closed.wait(), 1)
        assert removed.is_set()
        await slow.close()
        await fast.close()
    asyncio.run(run())


def test_compressed_video_preserves_order_but_bounds_and_revokes_slow_viewer():
    async def run():
        sent=[]
        class Socket:
            async def send_bytes(self,value): sent.append(value)
        relay=PreviewRelay(Socket(),lambda:None)
        def packet(i):
            header=json.dumps({'frames':[{'keyframe':i%10==0}]}).encode()
            return struct.pack('<I',len(header))+header+bytes([i])*100_000
        for i in range(50): relay.offer_video('camera',packet(i))
        assert len(relay.video['camera'])==10
        for _ in range(80):
            await asyncio.sleep(0)
            if len(sent)==10: break
        assert [value[-1] for value in sent]==list(range(40,50))
        relay.offer_video('camera',b'revoked');relay.discard('camera')
        assert not relay.video
        await relay.close()
    asyncio.run(run())
