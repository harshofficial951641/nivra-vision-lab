import asyncio
import base64
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
from queue import Queue
import time
from types import SimpleNamespace

import av
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from nivra.native_camera import video_packet
from nivra.server import create_app
from nivra.video_classifier import (Decoder, Episode, FrameRing, MODEL_ID, MODEL_PATH, MODEL_SHA256,
                                    Policy, VideoClassifier, load_model, preprocess, select_device)
from video_classifier_fixtures import synthetic_video, batches
from test_classroom import operator, camera, pair, ORIGIN


@pytest.fixture(scope='module')
def video():
    return synthetic_video()


def inert_worker(inbox, outbox, *args):
    outbox.put(dict(type='ready', device='cpu'))
    while True:
        time.sleep(.05)
        outbox.put(dict(type='heartbeat'))


def hung_worker(inbox, outbox, *args):
    outbox.put(dict(type='ready', device='cpu'))
    time.sleep(60)


def hung_inference_worker(inbox,outbox,*args):
    outbox.put(dict(type='ready',device='cpu'))
    started=time.monotonic()
    while True:
        outbox.put(dict(type='heartbeat',inferenceStarted=started))
        time.sleep(.03)


def wait_ready(service, timeout=45):
    async def wait():
        deadline = time.monotonic()+timeout
        while service.status == 'loading' and time.monotonic() < deadline:
            await asyncio.sleep(.02)
        assert service.status == 'ready', service.snapshot('s')
    return wait()


def test_preprocessing_matches_pinned_source_decode_and_dataset(video, tmp_path):
    """Execute original source functions, substituting RAM capture/cache only."""
    import torch
    source = Path(__file__).parent/'fixtures/movinet_probe_preprocessing.py'
    from torch.utils.data import Dataset
    raw, header, frames = video
    with av.open(BytesIO(raw)) as container:
        decoded = [(float(f.pts*f.time_base*1000), f.to_ndarray(format='bgr24')) for f in container.decode(video=0)]
    class Capture:
        def __init__(self, _): self.index = -1
        def isOpened(self): return True
        def read(self):
            self.index += 1
            return (True, decoded[self.index][1]) if self.index < len(decoded) else (False, None)
        def get(self, _): return decoded[self.index][0]
        def release(self): pass
    cached = {}
    fake_np = SimpleNamespace(**{name: getattr(np, name) for name in dir(np) if not name.startswith('__')})
    fake_np.save = lambda path, value, **kwargs: cached.update(array=value)
    fake_np.load = lambda *args, **kwargs: cached['array']
    namespace = dict(np=fake_np, cv2=SimpleNamespace(VideoCapture=Capture, setNumThreads=cv2.setNumThreads, CAP_PROP_POS_MSEC=cv2.CAP_PROP_POS_MSEC,
        resize=cv2.resize, cvtColor=cv2.cvtColor, COLOR_BGR2RGB=cv2.COLOR_BGR2RGB, __version__=cv2.__version__), Dataset=Dataset,
        torch=torch, math=__import__('math'), SEED=17, CACHE=tmp_path, cache_key=lambda _: 'fixture',
        sha=lambda _: 'fixture', write=lambda *args: None)
    exec(compile(source.read_text(), str(source), 'exec'), namespace)
    window = dict(startMs=0, endMs=4000, sha256='fixture', label=0, id='fixture')
    namespace['decode_record']((dict(id='synthetic', path='RAM', sha256='fixture'), [window]))
    expected = namespace['Clips']([window], 'movinet')[0][0].numpy()
    decoder = Decoder()
    for _, packet in batches(header, frames): decoder.feed(packet)
    # Use a fresh ring ending at 4 seconds, before later windows evict candidates.
    ring = FrameRing()
    with av.open(BytesIO(raw)) as container:
        for frame in container.decode(video=0):
            t = float(frame.pts*frame.time_base*1000)
            ring.add(t, frame)
            if t >= 4000: break
    np.testing.assert_array_equal(preprocess(ring.frames, 4000), expected)


def test_nearest_pts_earlier_ties_half_open_and_two_resizes():
    frames = [(t, np.full((224,224,3), value, np.uint8)) for t, value in [(0,1),(200,2),(300,3),(500,4)]]
    # First and third selected targets are enough to expose tie/order semantics.
    dense = frames+[(t, np.full((224,224,3), t//25 % 255, np.uint8)) for t in range(750,4001,250)]
    out = preprocess(dense, 4000)
    assert out.shape == (8,3,172,172) and out.dtype == np.float32
    assert out[0,0,0,0] == np.float32(1/255)
    assert out[-1,0,0,0] == np.float32(150/255)


def test_decoder_real_h264_and_bounded_ring(video):
    _, header, frames = video
    decoder = Decoder()
    for _, packet in batches(header, frames): decoder.feed(packet)
    assert decoder.decoded == len(frames) and decoder.errors == 0
    assert 0 < len(decoder.ring.frames) <= 48
    end, clip = decoder.ring.window(1000)
    assert end == 7000 and clip.shape == (8,3,172,172)


def test_decoder_rejects_oversized_sps_even_when_transport_header_claims_720p():
    _,header,frames=synthetic_video(seconds=.025,width=1920,height=1080)
    header.update(width=1280,height=720)
    decoder=Decoder()
    decoder.feed(video_packet({**header,'frames':frames},'c','g')[0])
    assert decoder.errors==1 and decoder.decoded==0 and decoder.context is None


@pytest.mark.parametrize('end_frame', [245,259,271,279])
def test_ring_retains_rounded_window_during_scheduler_jitter(video,end_frame):
    raw,_,_=video
    ring=FrameRing()
    with av.open(BytesIO(raw)) as container:
        for index,frame in enumerate(container.decode(video=0)):
            ring.add(float(frame.pts*frame.time_base*1000),frame)
            if index==end_frame: break
    end,clip=ring.window(1000)
    assert end==6000 and clip.shape==(8,3,172,172)


@pytest.mark.parametrize('change', ['missing-keyframe','corrupt','generation','sequence-gap','reconnect','source-gap'])
def test_decoder_recovers_only_at_keyframes(video, change):
    _, header, original = video
    frames = [dict(f) for f in original]
    decoder = Decoder()
    first = {**header, 'frames': frames[:20]}
    decoder.feed(video_packet(first, 'c', 'g')[0])
    old = decoder.decoded
    if change == 'corrupt':
        bad = {**frames[20], 'data': base64.b64encode(b'\0\0\0\x02\x41\xff').decode()}
        decoder.feed(video_packet({**header, 'frames': [bad]}, 'c', 'g')[0])
        assert decoder.errors == 1
    elif change == 'generation':
        header = {**header, 'generation':'new-source'}
    elif change == 'sequence-gap':
        frames[20]['sequence'] += 2
    elif change == 'source-gap':
        frames[20]['timestampMs'] += 300
    elif change == 'reconnect':
        decoder.reset()
    else:
        decoder = Decoder()
        old = 0
    decoder.feed(video_packet({**header, 'frames':[frames[20]]}, 'c', 'g')[0], reset=change=='missing-keyframe')
    assert decoder.context is None
    assert decoder.decoded == old
    for _, packet in batches(header, original[40:]): decoder.feed(packet)
    assert decoder.context is not None and decoder.ring.window(1000) is not None


def test_policy_confirmation_cooldown_hysteresis_and_reconnect():
    episode = Episode(Policy())
    assert not episode.update(4000,.95,'a',1)
    assert episode.update(5000,.95,'a',2)
    for t in range(6000,20000,1000): assert not episode.update(t,.95,'a',t/1000)
    assert not episode.update(4000,.999,'b',3)  # cross-socket cooldown
    assert episode.update(5000,.999,'c',11)     # source reset after cooldown


def test_policy_matches_c2_simulator():
    import importlib.util
    source=Path(__file__).resolve().parents[2]/'scripts/evaluation/classifier/policy.py'
    spec=importlib.util.spec_from_file_location('c2_policy_reference',source)
    reference=importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name]=reference
    spec.loader.exec_module(reference)
    for sequence in ([.4,.4,.8,.95,.7,.7,.7,.7,.7,.7,.7], [.95,.1,.1,.1,.95,.95,.95,.95,.95],
                     [.9,.1,.9,.1,.1,.9], [.5,float('nan'),.5,.5]):
        state=Episode(Policy(qualifying_threshold=.4,strong_threshold=.9))
        expected=reference.simulate([dict(timestampMs=4000+1000*i,probability=p) for i,p in enumerate(sequence)], reference.Policy(.4,.9))
        actual=[4000+1000*i for i,p in enumerate(sequence) if state.update(4000+1000*i,p,'same',4+i)]
        assert actual==expected


def test_policy_missing_invalid_off_and_auto(tmp_path):
    path = tmp_path/'policy.json'
    assert VideoClassifier(mode='auto',policy_path=path).status == 'off'
    policy = dict(schemaVersion=1,model=dict(sha256=MODEL_SHA256),windowMs=4000,strideMs=1000,
        qualifyingThreshold=.8,strongThreshold=.95,thresholdComparison='>=',
        confirmation=dict(consecutiveWindows=3,maxGapMs=1000,strongBypassesConfirmation=True,nonqualifyingResets=True),
        cooldownMs=8000,mergeGapMs=2000,requireTwoPeople=False,defaultEnabled=True)
    path.write_text(json.dumps(policy))
    service = VideoClassifier(mode='auto',policy_path=path)
    assert service.enabled and service.policy.consecutive_windows == 3 and service.policy_source == 'c2'
    path.write_text('{broken')
    assert VideoClassifier(mode='auto',policy_path=path).status == 'error'
    assert VideoClassifier(mode='off',policy_path=path).status == 'off'
    policy['defaultEnabled'] = 'yes'
    path.write_text(json.dumps(policy))
    assert VideoClassifier(mode='on',policy_path=path).status == 'error'


def test_off_mode_no_load_or_transport_change(tmp_path, monkeypatch):
    import nivra.video_classifier as module
    monkeypatch.setattr(module.mp, 'get_context', lambda *a: pytest.fail('off mode spawned'))
    service = VideoClassifier(mode='off',model_path=tmp_path/'absent')
    app = create_app(database=tmp_path/'off.sqlite', relay_only=True, video_classifier=service)
    with TestClient(app,base_url=ORIGIN['origin']) as client:
        assert 'videoClassifier' not in client.get('/api/v1/health').json()['runtime']
        operator(client); cam=camera(client); pair(client,cam['id'])
        from test_native_camera import batch
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream',headers=ORIGIN) as ws:
            ws.receive_json()
            ws.send_json(dict(type='browser-video-hello',version=1)); ws.receive_json()
            ws.send_json(dict(type='browser-video-v1',**batch()))
            assert ws.receive_json() == dict(type='video-accepted',sequence=1,timestampMs=6000)
        assert service.process is None and not service.cameras


@pytest.mark.parametrize('order', ['browser-first','classifier-first'])
def test_record_path_bidirectional_dedupe_and_camera_isolation(tmp_path, order):
    service = VideoClassifier(mode='on',policy_path=tmp_path/'none',worker_target=inert_worker)
    app = create_app(database=tmp_path/'dedupe.sqlite',relay_only=True,video_classifier=service)
    room = app.state.classroom
    first = room.store.add_camera('First','A','1')['id']
    second = room.store.add_camera('Second','A','1')['id']
    browser = dict(id='b1',occurredAtMs=5000,evidenceModel='nivra-browser-motion-v1')
    classifier = dict(id='v1',occurredAtMs=5000,evidenceModel=MODEL_ID)
    events = [browser,classifier] if order=='browser-first' else [classifier,browser]
    assert room.record_event(first,'g',events[0])
    assert not room.record_event(first,'g',events[1])
    assert room.record_event(second,'g',events[1])
    room.store.db.execute('UPDATE events SET received_at=0')
    assert room.record_event(first,'g',{**events[1],'id':'later'})
    room.clips.close(); room.store.close()


def test_queue_overload_resync_and_stale_generation_results():
    service = VideoClassifier(mode='on',policy_path=Path('absent-policy'))
    service.inbox = Queue(maxsize=1)
    service.submit('s','c','g',b'packet',video_generation='v',keyframe=True)
    service.submit('s','c','g',b'packet',video_generation='v',keyframe=False)
    assert service.dropped == 1 and service.cameras[('s','c')]['gate']
    service.inbox.get_nowait()
    service.submit('s','c','g',b'packet',video_generation='v',keyframe=False)
    assert service.inbox.empty()
    service.submit('s','c','g',b'packet',video_generation='v',keyframe=True)
    assert service.inbox.get_nowait()['reset'] is True
    seen=[]
    service.callbacks['s']=lambda *a: seen.append(a)
    service.accept(dict(type='preview',key=('s','c'),token=('old','v'),jpeg=b'bad'))
    assert not seen


@pytest.mark.parametrize('target', [hung_worker,hung_inference_worker])
def test_watchdog_kills_hung_worker_and_never_blocks_loop(tmp_path,target):
    async def run():
        service = VideoClassifier(mode='on',policy_path=tmp_path/'none',worker_target=target,watchdog_seconds=.2)
        await service.attach('s',lambda *a: None)
        await wait_ready(service)
        process = service.process
        lags=[]
        for _ in range(80):
            started=time.monotonic()
            for index in range(40): service.submit('s',str(index%4),'g',b'x'*50000,video_generation='v',keyframe=True)
            await asyncio.sleep(.01)
            lags.append(time.monotonic()-started-.01)
        assert service.status == 'error' and service.process is None
        assert max(lags) < .15
        assert process._closed
        await service.attach('later',lambda *a:None)
        assert service.process is None  # a new workspace cannot restart a failed worker
        await service.detach('later')
        await service.detach('s')
    asyncio.run(run())


def test_real_worker_batches_four_cameras_runtime_and_ram_previews(video, tmp_path):
    async def run():
        messages=[]
        service = VideoClassifier(mode='on',policy_path=tmp_path/'none',device='cpu')
        await service.attach('s', lambda camera, message: messages.append((camera,message)))
        try:
            await wait_ready(service)
            _, header, frames=video
            for data,packet in batches(header,frames):
                for index in range(4):
                    service.submit('s',str(index),'socket-1',packet,video_generation=header['generation'],
                                   keyframe=any(f['keyframe'] for f in data['frames']))
                await asyncio.sleep(.1)
            deadline=time.monotonic()+12
            while not any(m['type']=='score' and m['batchSize']==4 for _,m in messages) and time.monotonic()<deadline:
                await asyncio.sleep(.05)
            scores=[m for _,m in messages if m['type']=='score']
            assert any(m['batchSize']==4 for m in scores), (service.snapshot('s'),len(messages))
            assert {camera for camera,m in messages if m['type']=='score'}=={'0','1','2','3'}
            assert any(m['type']=='preview' and m['jpeg'].startswith(b'\xff\xd8') for _,m in messages)
            jpeg=next(m['jpeg'] for _,m in messages if m['type']=='preview')
            preview=cv2.imdecode(np.frombuffer(jpeg,np.uint8),cv2.IMREAD_COLOR)
            assert preview.shape[:2]==(header['height'],header['width'])
            runtime=service.snapshot('s')
            assert runtime['status']=='ready' and runtime['device']=='cpu', runtime
            assert runtime['cameras']['0']['analysedWindows']>=1
            assert runtime['cameras']['0']['batchSize']>=1
            assert not service.snapshot('other')['cameras']
        finally: await service.detach('s')
    asyncio.run(run())


def test_model_checksum_clip_reset_and_batch_independence():
    import torch
    assert hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest()==MODEL_SHA256
    torch.set_num_threads(2)
    model=load_model(MODEL_PATH,'cpu')
    generator=torch.Generator().manual_seed(72)
    inputs=torch.rand((4,8,3,172,172),generator=generator)
    with torch.inference_mode():
        alone=model(inputs[:1]).clone()
        full=model(inputs)
        after=model(inputs[:1])
        torch.testing.assert_close(full[:1],alone,atol=1e-5,rtol=1e-5)
        torch.testing.assert_close(after,alone,atol=0,rtol=0)
        for n in (2,3): assert model(inputs[:n]).shape==(n,2)


@pytest.mark.parametrize('cuda,mps,expected', [(True,True,'cuda'),(False,True,'mps'),(False,False,'cpu')])
def test_device_selection(cuda,mps,expected):
    torch=SimpleNamespace(cuda=SimpleNamespace(is_available=lambda:cuda),backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda:mps)))
    assert select_device(torch)==expected


def test_classifier_event_wall_review_clip_and_guard_contract(tmp_path):
    from test_classroom import guard_phone, post_review
    from test_native_camera import batch
    service=VideoClassifier(mode='on',policy_path=tmp_path/'none',worker_target=inert_worker)
    app=create_app(database=tmp_path/'journey.sqlite',relay_only=True,video_classifier=service)
    room=app.state.classroom
    with TestClient(app,base_url=ORIGIN['origin']) as client:
        operator(client); cam=camera(client); pair(client,cam['id'])
        phone=guard_phone(client,'G2')
        try:
            with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream',headers=ORIGIN) as ws:
                ready=ws.receive_json()
                ws.send_json(dict(type='browser-video-hello',version=1)); ws.receive_json()
                for index,timestamp in enumerate((6000,7000)):
                    ws.send_json(dict(type='browser-video-v1',**batch(sequence=index+1,timestamp=timestamp)))
                    assert ws.receive_json()['type']=='video-accepted'
                    token=(ready['generation'],'capture-one')
                    jpeg=cv2.imencode('.jpg',np.zeros((64,64,3),np.uint8))[1].tobytes()
                    client.portal.call(room.video_classifier_result,cam['id'],dict(type='preview',token=token,jpeg=jpeg))
                    client.portal.call(room.video_classifier_result,cam['id'],dict(type='score',token=token,epoch=1,endMs=timestamp,score=.95))
                state=client.get('/api/v2/state').json()
                assert len(state['events'])==1
                event=state['events'][0]
                assert event['model']==MODEL_ID
                assert event['detail']=='Video classifier: possible physical conflict. Review the clip.'
                assert event['source_ms']==7000 and event['clip']['frames']>=1
                clip=client.get(f"/api/v2/events/{event['id']}/clip").json()
                assert clip['frames'] and client.get(clip['frames'][0]['url']).content==jpeg
                # Existing owner review/dispatch and guard allowlist stay unchanged.
                confirmed=post_review(client,event,'confirm',guard='G2').json()
                assert confirmed['model']==MODEL_ID and confirmed['decision']=='confirmed'
                alerts=client.portal.call(lambda: room.store.guard_alerts('G2'))
                assert len(alerts)==1 and alerts[0]['detail']==event['detail']
                assert 'model' not in alerts[0]  # guards receive the existing privacy allowlist
                with phone.websocket_connect('ws://127.0.0.1:8765/api/v2/guard/stream',headers=ORIGIN) as guard_stream:
                    alert=guard_stream.receive_json()['alerts'][0]
                    assert alert['id']==event['id'] and alert['detail']==event['detail']
                # A stale socket cannot append footage or create a classifier incident.
                before=room.clips.bytes
                client.portal.call(room.video_classifier_result,cam['id'],dict(type='preview',token=('old','capture-one'),jpeg=jpeg))
                assert room.clips.bytes==before
        finally: phone.close()


def test_health_exposes_auto_off_loading_ready_and_error(tmp_path):
    service=VideoClassifier(mode='auto',policy_path=tmp_path/'absent')
    app=create_app(database=tmp_path/'health.sqlite',relay_only=True,video_classifier=service)
    with TestClient(app,base_url=ORIGIN['origin']) as client:
        health=lambda: client.get('/api/v1/health').json()['runtime']['videoClassifier']
        assert health()['status']=='off' and health()['device'] is None
        service.status='loading'
        assert health()['status']=='loading'
        service.accept(dict(type='ready',device='mps'))
        assert health()['status']=='ready' and health()['device']=='mps'
        service.accept(dict(type='error',detail='Worker failed'))
        assert health()['status']=='error'


def test_guest_workspaces_share_one_worker_and_isolate_stats(tmp_path):
    from nivra.workspaces import Workspaces
    async def run():
        service=VideoClassifier(mode='on',policy_path=tmp_path/'none',worker_target=inert_worker)
        primary=create_app(database=tmp_path/'primary.sqlite',relay_only=True,video_classifier=service)
        manager=Workspaces(primary,tmp_path/'workspaces')
        async with primary.router.lifespan_context(primary):
            first=await manager.load('a'*32)
            second=await manager.load('b'*32)
            assert first.state.classroom.video_classifier is service is second.state.classroom.video_classifier
            assert len(service.callbacks)==3
            process=service.process
            await wait_ready(service)
            service.submit(first.state.classroom.video_scope,'c','g',b'data',video_generation='v',keyframe=True)
            assert 'c' in first.state.classroom.runtime()['videoClassifier']['cameras']
            assert 'c' not in second.state.classroom.runtime()['videoClassifier']['cameras']
            await manager.close()
            assert service.process is process and len(service.callbacks)==1
        assert service.process is None
    asyncio.run(run())


@pytest.mark.skipif(os.environ.get('NIVRA_RUN_VIDEO_CLASSIFIER_CUDA_TEST')!='1',reason='Opt-in shared GPU integration parity')
def test_cuda_model_adapter_parity():
    import torch
    if not torch.cuda.is_available(): pytest.skip('CUDA unavailable')
    torch.set_num_threads(2)
    inputs=torch.rand((4,8,3,172,172),generator=torch.Generator().manual_seed(394))
    cpu=load_model(MODEL_PATH,'cpu')
    cuda=load_model(MODEL_PATH,'cuda')
    with torch.inference_mode():
        for n in (1,2,3,4):
            reference=cpu(inputs[:n])
            actual=cuda(inputs[:n].cuda()).cpu()
            torch.testing.assert_close(actual,reference,atol=1e-5,rtol=1e-5)
        first=cuda(inputs[:1].cuda()).cpu()
        torch.testing.assert_close(first,cpu(inputs[:1]),atol=1e-5,rtol=1e-5)


def test_worker_load_failure_is_reported_without_ingest_stall(tmp_path):
    async def run():
        service=VideoClassifier(mode='on',policy_path=tmp_path/'none',model_path=tmp_path/'missing.pt',device='cpu')
        await service.attach('s',lambda *args:None)
        try:
            deadline=time.monotonic()+45
            while service.status=='loading' and time.monotonic()<deadline: await asyncio.sleep(.02)
            assert service.status=='error'
            assert 'loading' in service.detail
        finally: await service.detach('s')
    asyncio.run(run())


def test_automatic_accelerator_failure_falls_back_honestly_but_explicit_device_does_not(monkeypatch):
    import nivra.video_classifier as module
    monkeypatch.setattr(module,'select_device',lambda *args:'mps')
    calls=[]
    monkeypatch.setattr(module,'load_model',lambda path,device: calls.append(device) or device)
    def warm(model,device):
        if device=='mps': raise NotImplementedError('synthetic unsupported operator')
    monkeypatch.setattr(module,'warm_model',warm)
    model,device,detail=module.prepare_model('unused','auto')
    assert model=='cpu' and device=='cpu' and detail=='MPS warmup failed; using CPU.'
    assert calls==['mps','cpu']
    with pytest.raises(NotImplementedError): module.prepare_model('unused','mps')
    assert calls==['mps','cpu','mps']
