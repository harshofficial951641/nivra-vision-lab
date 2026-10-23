"""Optional RAM-only browser-video classifier, isolated from asyncio and camera rules.

No torch/PyAV import, subprocess, or camera work occurs in off mode. A single
spawned worker owns all decoder contexts and one stateless-per-clip TorchScript
model. Bounded queues discard overload; the supervisor fails closed on a hang.
"""
from __future__ import annotations

import asyncio
import base64
from collections import deque
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
from queue import Empty, Full
import struct
import time
from typing import Callable

MODEL_ID = 'movinet-a0-vid-v1'
MODEL_SHA256 = '78e372a5ec6ad97925c3cdac2e0de0f5e9315ebd38fb151fa429d69304aaef87'
ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = Path(__file__).parent / 'assets' / 'movinet_a0_fight.pt'
POLICY_PATH = ROOT / 'docs/evaluations/video-classifier/policy.json'
WINDOW_MS = 4000
MAX_CAMERAS = 32
BROWSER_MODELS = {'nivra-browser-motion-v1', 'nivra-browser-rtmo-t-motion-v1'}


@dataclass(frozen=True)
class Policy:
    qualifying_threshold: float = .9
    strong_threshold: float = .99
    consecutive_windows: int = 2
    cooldown_ms: int = 8000
    stride_ms: int = 1000
    merge_gap_ms: int = 2000
    require_two_people: bool = False
    default_enabled: bool = False

    @property
    def interval_ms(self): return self.stride_ms

    @classmethod
    def read(cls, path: Path):
        """Absent policy is a disabled placeholder; malformed policy fails closed.

        Exact schema exported by scripts/evaluation/classifier/evaluate.py.
        Values are never silently clamped/tuned; mismatched model fails closed.
        """
        if not path.exists():
            return cls(), 'placeholder'
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        confirmation = value['confirmation']
        if (value['schemaVersion'] != 1 or value['model']['sha256'] != MODEL_SHA256
                or value['windowMs'] != WINDOW_MS or value['thresholdComparison'] != '>='
                or confirmation['maxGapMs'] != value['strideMs']
                or confirmation['strongBypassesConfirmation'] is not True
                or confirmation['nonqualifyingResets'] is not True):
            raise ValueError('Unsupported video classifier policy contract')
        policy = cls(value['qualifyingThreshold'], value['strongThreshold'], confirmation['consecutiveWindows'],
                     value['cooldownMs'], value['strideMs'], value['mergeGapMs'], value['requireTwoPeople'], value['defaultEnabled'])
        if (type(policy.default_enabled) is not bool
                or type(policy.consecutive_windows) is not int or not 1 <= policy.consecutive_windows <= 30
                or type(policy.cooldown_ms) is not int or policy.cooldown_ms != 8000
                or type(policy.stride_ms) is not int or policy.stride_ms != 1000
                or type(policy.merge_gap_ms) is not int or not policy.stride_ms <= policy.merge_gap_ms <= 30000
                or policy.require_two_people is not False
                or any(type(v) not in (float, int) or not math.isfinite(v)
                       for v in (policy.qualifying_threshold, policy.strong_threshold))
                or not 0 <= policy.qualifying_threshold <= policy.strong_threshold <= 1):
            raise ValueError('Invalid video classifier policy')
        return policy, 'c2'


class Episode:
    """C2 CameraPolicy semantics, plus a reconnect-safe wall-clock cooldown."""
    def __init__(self, policy: Policy):
        self.policy = policy
        self.hits = 0
        self.latched = False
        self.last_source = None
        self.last_epoch = None
        self.last_qualifying = None
        self.last_alert = -math.inf
        self.last_wall_alert = -math.inf

    def update(self, timestamp: float, score: float, epoch, now: float, observed_people=None) -> bool:
        if not math.isfinite(timestamp) or timestamp < 0: return False
        if epoch == self.last_epoch and self.last_source is not None and timestamp <= self.last_source:
            return False
        if epoch != self.last_epoch:
            self.hits, self.latched, self.last_qualifying = 0, False, None
            self.last_source, self.last_alert = None, -math.inf
        if self.last_qualifying is not None and timestamp-self.last_qualifying > self.policy.merge_gap_ms:
            self.latched = False
        contiguous = self.last_source is not None and timestamp-self.last_source <= self.policy.stride_ms+1e-4
        self.last_source, self.last_epoch = timestamp, epoch
        qualifies = (isinstance(score, (int,float)) and math.isfinite(score)
                     and 0 <= score <= 1 and score >= self.policy.qualifying_threshold)
        if self.policy.require_two_people and (observed_people is None or observed_people < 2): qualifies = False
        if not qualifies:
            self.hits = 0
            return False
        self.hits = self.hits+1 if contiguous and self.hits else 1
        self.last_qualifying = timestamp
        confirmed = score >= self.policy.strong_threshold or self.hits >= self.policy.consecutive_windows
        if (not confirmed or self.latched or timestamp-self.last_alert < self.policy.cooldown_ms
                or now-self.last_wall_alert < self.policy.cooldown_ms/1000): return False
        self.last_alert, self.last_wall_alert, self.latched = timestamp, now, True
        return True


def preprocess(frames, end_ms: float):
    """Training decode_record + Clips(epoch=0), including the two resize stages.

    Frames are (actual source PTS ms, RGB uint8 224x224); input is already the
    result of cv2.resize(BGR,224) then cvtColor(BGR2RGB). Nearest in [end-4s,end),
    earlier ties; 16 half-open targets, then floor(linspace(0,15,8)).
    """
    import cv2
    import numpy as np
    available = [(t, image) for t, image in frames if end_ms-WINDOW_MS <= t < end_ms]
    if not available:
        raise ValueError('Incomplete video window')
    targets = np.linspace(end_ms-WINDOW_MS, end_ms, 16, endpoint=False)
    indices = np.linspace(0, 15, 8).astype(int)
    selected = [min(available, key=lambda row: (abs(row[0]-targets[i]), row[0])) for i in indices]
    if any(abs(t-targets[i]) > 250 for i, (t, _) in zip(indices, selected)):
        raise ValueError('Video window has missing source frames')
    return np.stack([cv2.resize(image, (172, 172)) for _, image in selected]).transpose(0, 3, 1, 2).astype(np.float32)/255


class FrameRing:
    """Keep only both actual-PTS neighbours of the 250ms training target grid.

    All 40fps frames decode, but only ~8fps candidates resize/stay in RAM. Both
    neighbours retain exact nearest-PTS selection at moving window boundaries.
    """
    def __init__(self):
        self.frames = deque(maxlen=80)
        self.previous = None
        self.anchor = self.target = None
        self.last = -math.inf
        self.epoch = 0

    def add(self, timestamp, frame):
        import cv2
        if timestamp <= self.last or timestamp-self.last > 250:
            self.frames.clear()
            self.previous = None
            self.anchor = self.target = timestamp
            self.epoch += 1
        if self.anchor is None:
            self.anchor = self.target = timestamp
        if self.target <= timestamp:
            for t, source in ([self.previous] if self.previous else []) + [(timestamp, frame)]:
                if not self.frames or t > self.frames[-1][0]:
                    bgr = source.to_ndarray(format='bgr24')
                    self.frames.append((t, cv2.cvtColor(cv2.resize(bgr, (224, 224)), cv2.COLOR_BGR2RGB)))
            while self.target <= timestamp:
                self.target += 250
        self.previous = (timestamp, frame)
        self.last = timestamp
        # A scored window ends on a 1s source grid and can trail the latest
        # decoded frame by nearly 1s. Retain its oldest neighbour as well.
        while self.frames and self.frames[0][0] < timestamp-5500:
            self.frames.popleft()

    def window(self, interval_ms):
        if self.anchor is None or self.last-self.anchor < WINDOW_MS:
            return None
        end = self.anchor+WINDOW_MS+math.floor((self.last-self.anchor-WINDOW_MS)/interval_ms)*interval_ms
        return end, preprocess(self.frames, end)


class Decoder:
    def __init__(self):
        self.context = None
        self.identity = None
        self.ring = FrameRing()
        self.last_sequence = None
        self.last_timestamp = None
        self.errors = 0
        self.decoded = 0
        self.decode_seconds = self.decode_cpu_seconds = 0.
        self.last_received = time.monotonic()
        self.last_scored = -math.inf
        self.last_end = -math.inf
        self.last_preview = -math.inf

    def reset(self):
        self.context = None  # PyAV CodecContext releases buffers when dereferenced.
        self.identity = None
        self.ring = FrameRing()
        self.last_sequence = self.last_timestamp = None
        self.last_end = -math.inf

    def feed(self, packet: bytes, reset=False):
        import av
        from fractions import Fraction
        size = struct.unpack('<I', packet[:4])[0]
        header = json.loads(packet[4:4+size])
        encoded = memoryview(packet)[4+size:]
        identity = (header['generation'], header['videoGeneration'], header['description'], header['width'], header['height'])
        if reset or self.identity != identity:
            self.reset()
        started, cpu = time.perf_counter(), time.thread_time()
        try:
            for item in header['frames']:
                if self.last_sequence is not None and (item['sequence'] != self.last_sequence+1
                        or item['timestampMs']-self.last_timestamp > 250):
                    self.reset()
                if self.context is None:
                    if not item['keyframe']:
                        continue
                    self.context = av.CodecContext.create('h264', 'r')
                    self.context.thread_count = 1
                    # Bound native allocation from SPS too, before decoding a
                    # paired publisher's claimed header dimensions can be checked.
                    self.context.options = {'max_pixels': str(1280*1280)}
                    self.context.extradata = base64.b64decode(header['description'], validate=True)
                    self.identity = identity
                data = bytes(encoded[item['offset']:item['offset']+item['length']])
                chunk = av.Packet(data)
                chunk.pts = chunk.dts = round(item['timestampMs']*1000)
                chunk.time_base = Fraction(1, 1_000_000)
                for frame in self.context.decode(chunk):
                    if (frame.width != header['width'] or frame.height != header['height']
                            or max(frame.width, frame.height) > 1280):
                        raise ValueError('Decoded video dimensions differ')
                    timestamp = float(frame.pts*frame.time_base*1000) if frame.pts is not None else item['timestampMs']
                    self.ring.add(timestamp, frame)
                    self.decoded += 1
                self.last_sequence, self.last_timestamp = item['sequence'], item['timestampMs']
            self.last_received = time.monotonic()
        except Exception:
            self.errors += 1
            self.reset()
        finally:
            self.decode_seconds += time.perf_counter()-started
            self.decode_cpu_seconds += time.thread_time()-cpu


def select_device(torch, requested='auto'):
    if requested not in ('auto', 'cuda', 'mps', 'cpu'):
        raise ValueError('Invalid classifier device')
    if requested != 'auto':
        if requested == 'cuda' and not torch.cuda.is_available():
            raise RuntimeError('CUDA unavailable')
        if requested == 'mps' and not torch.backends.mps.is_available():
            raise RuntimeError('MPS unavailable')
        return requested
    return 'cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu'


def load_model(path, device):
    """Load pinned bytes and rebind CPU trace's tensor-factory Device constants.

    map_location moves weights/tensor constants, but does not move the original
    port's traced arange(device='cpu') nodes. Rebind only Device-valued literals
    before the first execution. No weights, arithmetic, or serialized bytes change.
    Torch 2.5.1 is pinned; CPU/CUDA logit and batch parity tests guard this adapter.
    """
    import torch
    if hashlib.sha256(Path(path).read_bytes()).hexdigest() != MODEL_SHA256:
        raise ValueError('Classifier checksum mismatch')
    model = torch.jit.load(str(path), map_location=device).eval()
    if device != 'cpu':
        def rebind(graph):
            for node in graph.nodes():
                if (node.kind() == 'prim::Constant' and str(node.output().type()) == 'Device'
                        and node.hasAttribute('value') and node.kindOf('value') == 's'):
                    node.s_('value', device)
                for block in node.blocks(): rebind(block)
        for module in model.modules():
            for method in module._c._method_names():
                rebind(module._c._get_method(method).graph)
    return model


def warm_model(model, device):
    import torch
    with torch.inference_mode():
        for batch_size in (1, 4, 4, 4):
            model(torch.zeros(batch_size, 8, 3, 172, 172, device=device))


def prepare_model(path, requested='auto'):
    """Prefer accelerators, but report an explicit CPU fallback if unsupported.

    Explicit benchmark device requests never fall back. An automatic MPS/CUDA
    warmup failure cannot silently disable the classifier on a prepared Mac.
    Integrity/configuration failures remain errors rather than fallback triggers.
    """
    import torch
    preferred = select_device(torch, requested)
    devices = [preferred]
    if requested == 'auto' and preferred != 'cpu': devices.append('cpu')
    failures = []
    for device in devices:
        model = None
        try:
            model = load_model(path, device)
            warm_model(model, device)
            detail = f'{", ".join(failures)} warmup failed; using CPU.' if failures else None
            return model, device, detail
        except (RuntimeError, NotImplementedError):
            model = None
            if device == 'cpu' or requested != 'auto': raise
            failures.append(device.upper())


def worker(inbox, outbox, model_path, policy, device):
    """Spawn target; every native decode/tensor operation stays in this process."""
    def emit(message):
        try: outbox.put_nowait(message)
        except Full: pass
    phase = 'loading'
    try:
        import cv2
        import numpy as np
        import torch
        cv2.setNumThreads(1)
        torch.set_num_threads(2)
        model, device, fallback = prepare_model(model_path, device)
        emit(dict(type='ready', device=device, detail=fallback))
        cameras = {}
        from concurrent.futures import ThreadPoolExecutor
        inference_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='movinet-inference')
        inflight = None
        inflight_rows = []
        inference_started = None
        def infer(batch):
            started = time.perf_counter()
            with torch.inference_mode():
                tensor = torch.from_numpy(np.stack([row[2][1] for row in batch])).to(device)
                logits = model(tensor)
                if logits.shape != (len(batch), 2) or not bool(torch.isfinite(logits).all()):
                    raise ValueError('Invalid classifier output')
                probabilities = logits.softmax(1)[:, 1].cpu().tolist()
            return probabilities, (time.perf_counter()-started)*1000
        heartbeat = 0.
        pending_since = None
        decode_cpu_ms = decoded_frames = computed_windows = stale_packets = 0
        inference_samples = deque(maxlen=1024)
        while True:
            # Bound decode work per turn so continuous ingest cannot starve scores.
            for _ in range(16):
                try: job = inbox.get(timeout=.01 if _ == 0 else 0)
                except Empty: break
                if job is None:
                    inference_pool.shutdown(wait=False, cancel_futures=True)
                    return
                key = job['key']
                if job.get('forget'):
                    cameras.pop(key, None)
                    continue
                if time.monotonic()-job['received'] > .75:
                    cameras.pop(key, None)
                    stale_packets += 1
                    continue
                if key not in cameras and len(cameras) >= MAX_CAMERAS:
                    continue
                current = cameras.get(key)
                if current is None or current['token'] != job['token'] or current['revision'] != job['revision']:
                    current = cameras[key] = dict(decoder=Decoder(), token=job['token'], revision=job['revision'], serial=0)
                decoder = current['decoder']
                previous_epoch = decoder.ring.epoch
                old_ring = decoder.ring
                old_cpu, old_decoded = decoder.decode_cpu_seconds, decoder.decoded
                phase = 'decode'
                decoder.feed(job['packet'], job['reset'])
                decode_cpu_ms += (decoder.decode_cpu_seconds-old_cpu)*1000
                decoded_frames += decoder.decoded-old_decoded
                if decoder.ring is not old_ring or decoder.ring.epoch != previous_epoch:
                    current['serial'] += 1
                if decoder.ring.frames and decoder.ring.last-decoder.last_preview >= 250:
                    decoder.last_preview = decoder.ring.last
                    # Human review retains source geometry; only model inputs
                    # use the training contract's square resize.
                    preview = decoder.ring.previous[1].to_ndarray(format='bgr24')
                    height, width = preview.shape[:2]
                    scale = min(1., 640/max(width, height))
                    if scale < 1: preview = cv2.resize(preview, (round(width*scale), round(height*scale)))
                    ok, jpeg = cv2.imencode('.jpg', preview, [cv2.IMWRITE_JPEG_QUALITY, 75])
                    if ok: emit(dict(type='preview', key=key, token=current['token'], revision=current['revision'], jpeg=jpeg.tobytes()))
            now = time.monotonic()
            if inflight is not None and inflight.done():
                phase = 'inference'
                probabilities, elapsed = inflight.result()
                computed_windows += len(inflight_rows)
                inference_samples.append(elapsed)
                for (key, current, value), score in zip(inflight_rows, probabilities):
                    live = current['live']
                    if cameras.get(key) is not live or current['serial'] != live['serial']: continue
                    decoder = current['decoder']
                    emit(dict(type='score', key=key, token=current['token'], revision=current['revision'], epoch=current['serial'],
                              endMs=value[0], score=score, inferenceMs=elapsed, batchSize=len(inflight_rows),
                              decodedFrames=decoder.decoded, decodeMs=decoder.decode_seconds*1000,
                              decodeCpuMs=decoder.decode_cpu_seconds*1000))
                inflight, inflight_rows, inference_started = None, [], None
            for key in list(cameras):
                if now-cameras[key]['decoder'].last_received > 3:
                    del cameras[key]
            rows = []
            for key, current in cameras.items():
                if inflight is not None: break
                decoder = current['decoder']
                if now-decoder.last_scored < policy.interval_ms/1000:
                    continue
                phase = 'preprocessing'
                value = decoder.ring.window(policy.interval_ms)
                if value is None or value[0] <= decoder.last_end:
                    continue
                rows.append((key, current, value))
            # Give other cameras up to 50ms to reach the same source window.
            # No wait blocks decode or the owner loop; this is a scheduler gate.
            if rows and len(rows) < min(4, len(cameras)):
                if pending_since is None: pending_since = now
                if now-pending_since < .05: rows = []
            else:
                pending_since = None
            if rows:
                # Oldest due first across >4 cameras; one bounded batch in flight.
                batch = sorted(rows, key=lambda row: row[1]['decoder'].last_scored)[:4]
                for _, current, value in batch:
                    current['decoder'].last_end, current['decoder'].last_scored = value[0], now
                # Snapshot decoder epoch now; future results must not acquire a
                # newer epoch if a corrupt/gapped stream resets during inference.
                inflight_rows = [(key, dict(current, serial=current['serial']), value) for key,current,value in batch]
                # Keep the live identity separately from the immutable epoch copy.
                for saved, original in zip(inflight_rows, batch): saved[1]['live'] = original[1]
                inference_started = time.monotonic()
                inflight = inference_pool.submit(infer, batch)
            if time.monotonic()-heartbeat >= .25:
                emit(dict(type='heartbeat', inferenceStarted=inference_started, metrics=dict(decodeCpuMs=decode_cpu_ms, decodedFrames=decoded_frames,
                    computedWindows=computed_windows, stalePackets=stale_packets, inferenceMs=list(inference_samples),
                    cameras={str(key):dict(decodedFrames=current['decoder'].decoded, buffered=len(current['decoder'].ring.frames),
                                          sourceMs=current['decoder'].ring.last, anchorMs=current['decoder'].ring.anchor)
                             for key,current in cameras.items()})))
                heartbeat = time.monotonic()
    except Exception as error:
        # Internal errors never expose packet contents, paths, or model internals.
        emit(dict(type='error', detail=f'Video classifier failed during {phase} ({type(error).__name__}); restart the backend to retry.'))


class VideoClassifier:
    def __init__(self, *, mode=None, policy_path=None, model_path=None, device=None,
                 watchdog_seconds=10., load_timeout=90., worker_target=worker):
        self.mode = mode or os.environ.get('NIVRA_VIDEO_CLASSIFIER', 'auto')
        self.policy, self.policy_source = Policy(), 'placeholder'
        self.status, self.detail, self.device = 'off', None, None
        self.model_path, self.requested_device = Path(model_path or MODEL_PATH), device or 'auto'
        self.watchdog_seconds, self.load_timeout = watchdog_seconds, load_timeout
        self.worker_target = worker_target
        self.callbacks: dict[str, Callable] = {}
        self.cameras = {}
        self.process = self.inbox = self.outbox = self.task = None
        self.enabled = False
        self.last_alive = self.started = 0.
        self.dropped = 0
        self.worker_metrics = {}
        self.inference_started = None
        if self.mode == 'off': return  # Even a broken policy must be irrelevant.
        try:
            if self.mode not in ('on', 'auto'): raise ValueError('Invalid mode')
            self.policy, self.policy_source = Policy.read(Path(policy_path or POLICY_PATH))
            self.enabled = self.mode == 'on' or self.policy.default_enabled
            if self.enabled: self.status = 'loading'
        except Exception:
            self.status, self.detail = 'error', 'Invalid video classifier configuration; classifier disabled.'

    async def attach(self, scope, callback):
        self.callbacks[scope] = callback
        if not self.enabled or self.status == 'error' or self.process is not None: return
        context = mp.get_context('spawn')
        self.inbox, self.outbox = context.Queue(maxsize=16), context.Queue(maxsize=64)
        self.process = context.Process(target=self.worker_target,
            args=(self.inbox, self.outbox, str(self.model_path), self.policy, self.requested_device), daemon=True)
        self.last_alive = self.started = time.monotonic()
        try:
            self.process.start()
            self.task = asyncio.create_task(self._poll())
        except Exception:
            self.status, self.detail = 'error', 'Video classifier could not start.'
            await self._terminate()

    async def detach(self, scope):
        self.callbacks.pop(scope, None)
        for key in list(self.cameras):
            if key[0] == scope: self.forget(*key)
        if self.callbacks or self.process is None: return
        if self.task:
            self.task.cancel()
            try: await self.task
            except asyncio.CancelledError: pass
        await self._terminate()

    async def _terminate(self):
        if self.process is not None:
            if self.process.pid is not None:
                if self.process.is_alive(): self.process.terminate()
                await asyncio.to_thread(self.process.join, 2)
                if self.process.is_alive():
                    self.process.kill()
                    await asyncio.to_thread(self.process.join, 1)
            self.process.close()
            self.process = None
        for queue in (self.inbox, self.outbox):
            if queue is not None:
                queue.cancel_join_thread()
                queue.close()

    def submit(self, scope, camera, generation, packet, *, video_generation, keyframe):
        if not self.enabled or self.status not in ('loading', 'ready') or self.inbox is None: return
        key = (scope, camera)
        if key not in self.cameras and len(self.cameras) >= MAX_CAMERAS:
            self.dropped += 1
            return
        token = (generation, video_generation)
        state = self.cameras.setdefault(key, dict(token=token, gate=True, epoch=0, count=0, first=None, last=None, timestamps=deque(maxlen=30)))
        if state['token'] != token:
            state.update(token=token, gate=True)
        if state['gate'] and not keyframe: return
        reset = state['gate']
        revision = state['epoch']+int(reset)
        try:
            self.inbox.put_nowait(dict(key=key, token=token, revision=revision, packet=packet, reset=reset, received=time.monotonic()))
            state['gate'] = False
            state['epoch'] = revision
        except Full:
            state['gate'] = True
            self.dropped += 1

    def forget(self, scope, camera):
        key = (scope, camera)
        self.cameras.pop(key, None)
        if self.inbox is not None and self.enabled:
            try: self.inbox.put_nowait(dict(key=key, forget=True))
            except (Full, ValueError): pass

    def accept(self, message):
        """Dispatch on the owner event loop; stale sockets/workspaces are ignored."""
        now = time.monotonic()
        if message['type'] in ('ready', 'heartbeat'):
            self.last_alive = now
            if 'metrics' in message: self.worker_metrics = message['metrics']
            if 'inferenceStarted' in message: self.inference_started = message['inferenceStarted']
            if message['type'] == 'ready':
                self.status, self.device = 'ready', message['device']
                self.detail = message.get('detail')
            return
        if message['type'] == 'error':
            self.status, self.detail = 'error', message['detail']
            return
        key = message['key']
        current = self.cameras.get(key)
        if (current is None or current['gate'] or current['token'] != message['token']
                or message.get('revision', current['epoch']) != current['epoch']): return
        if message['type'] == 'score':
            current.update(last=now, count=current['count']+1, first=current['first'] or now,
                           inferenceMs=message['inferenceMs'], batchSize=message['batchSize'],
                           decodeCpuMs=message['decodeCpuMs'], decodedFrames=message['decodedFrames'])
            current['timestamps'].append(now)
        callback = self.callbacks.get(key[0])
        if callback:
            try: callback(key[1], message)
            except Exception:
                self.status, self.detail = 'error', 'Video classifier alert delivery failed; classifier stopped.'

    async def _poll(self):
        while True:
            for _ in range(64):
                try: message = self.outbox.get_nowait()
                except Empty: break
                self.accept(message)
            now = time.monotonic()
            limit = self.load_timeout if self.status == 'loading' else self.watchdog_seconds
            if (self.status == 'error' or not self.process.is_alive() or now-self.last_alive > limit
                    or (self.inference_started is not None and now-self.inference_started > self.watchdog_seconds)):
                if self.status != 'error':
                    self.status, self.detail = 'error', 'Video classifier watchdog stopped an unresponsive worker.'
                await self._terminate()
                return
            await asyncio.sleep(.02)

    def snapshot(self, scope):
        now = time.monotonic()
        cameras = {}
        for (owner, camera), current in self.cameras.items():
            if owner != scope: continue
            times = [t for t in current['timestamps'] if now-t < 10]
            windows = (len(times)-1)/(times[-1]-times[0]) if len(times) > 1 else 0.
            if self.status != 'ready' or not times or now-times[-1] > 2.5: windows = 0.
            cameras[camera] = dict(analysedFps=round(windows*8, 3), windowsPerSecond=round(windows, 3),
                                  analysedWindows=current['count'], inferenceMs=current.get('inferenceMs'),
                                  batchSize=current.get('batchSize'), waitingForKeyframe=current['gate'])
        return dict(status=self.status, model=MODEL_ID, device=self.device, detail=self.detail,
                    mode=self.mode, policySource=self.policy_source, policy=asdict(self.policy),
                    droppedPackets=self.dropped, cameras=cameras)
