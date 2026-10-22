import copy
import asyncio
import json
import time
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from nivra.server import create_app
from nivra.device_analysis import DeviceResult, DeviceMotion, MAX_REPORT_BYTES, result_payload
from test_classroom import operator, camera, pair, ORIGIN
from test_server import packet


def test_camera_reports_share_one_pending_dashboard_update(tmp_path):
    async def run():
        service=create_app(database=tmp_path/'db.sqlite',relay_only=True).state.classroom
        sent=[]
        async def broadcast(value): sent.append(value)
        service.broadcast=broadcast
        for _ in range(40): service.schedule_snapshot()
        pending=service.snapshot_task
        assert sent==[]
        await pending
        assert len(sent)==1
        service.schedule_snapshot()
        assert service.snapshot_task is not pending
        await service.stop()
        assert service.snapshot_task.cancelled()
    asyncio.run(run())


def report(t=100):
    return dict(type='device-result',model='nivra-browser-motion-v1',delegate='GPU',timestampMs=t,
        inferenceMs=25,observedPeople=2,usablePeople=2,
        tracks=[dict(id=1,box=[.1,.1,.4,.8])],
        conflict=dict(status='alert',explanation='Directed motion'),
        events=[dict(id='run-conflict-1',occurredAtMs=100,detail='Review the scene')])


def test_thirty_two_people_allowed():
    data=report()
    data.update(observedPeople=32,usablePeople=32,
        tracks=[dict(id=i,box=[.01,.01,.2,.4]) for i in range(32)])
    assert len(DeviceResult.model_validate(data).tracks)==32


def test_crowd_model_keeps_its_own_evidence_version():
    data=report();data['model']='nivra-browser-rtmo-t-motion-v1'
    assert result_payload(DeviceResult.model_validate(data))['model']==data['model']
    data['model']='unvalidated-model'
    with pytest.raises(ValueError): DeviceResult.model_validate(data)


@pytest.mark.parametrize('field', ['observedPeople', 'usablePeople', 'tracks'])
def test_thirty_three_people_rejected(field):
    data=report()
    data.update(observedPeople=32,usablePeople=32,tracks=[])
    data[field]=[dict(id=i,box=[.01,.01,.2,.4]) for i in range(33)] if field=='tracks' else 33
    with pytest.raises(ValueError): DeviceResult.model_validate(data)


@pytest.mark.parametrize('change', [dict(observedPeople=0), dict(usablePeople=3)])
def test_counts_still_reject_tracks_or_analyzed_people_exceeding_observed(change):
    data=report();data.update(change)
    with pytest.raises(ValueError): DeviceResult.model_validate(data)


def test_full_device_capacity_survives_stream_and_dashboard(tmp_path):
    app=create_app(database=tmp_path/'db.sqlite',relay_only=True)
    with TestClient(app,base_url=ORIGIN['origin']) as client:
        operator(client);cam=camera(client);pair(client,cam['id'])
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream',headers=ORIGIN) as ws:
            ws.receive_json()
            ws.send_json(dict(type='device-status',state='ready',delegate='GPU',detail='Device GPU'))
            ws.send_bytes(packet(100));ws.receive_json()
            data=report()
            tracks=[dict(id=i,box=[(i%8)/8,(i//8)/4,(i%8)/8+.1,(i//8)/4+.2]) for i in range(32)]
            data.update(observedPeople=32,usablePeople=10,tracks=tracks,events=[],
                poses=[[[.1234,.5678,.9123] for _ in range(33)] for _ in range(32)],
                conflict=dict(status='clear',explanation='No directed interaction observed.'))
            assert 16384 < len(json.dumps(data).encode('utf-8')) < MAX_REPORT_BYTES
            ws.send_json(data)
            ws.send_bytes(packet(200));ws.receive_json()
            state=client.get('/api/v2/state').json()
            result=state['cameras'][0]['result']
            assert state['runtime']['maxPeople']==32
            assert result['coverage']==dict(observedPeople=32,analyzedPeople=10,excludedPeople=22,
                status='limited',actionPeople=10,maxPeople=32)
            assert [dict(id=t['id'],box=t['box']) for t in result['tracks']]==tracks
            assert result['poses']==data['poses']
            assert state['analytics']['total']==0


@pytest.mark.parametrize('poses', [
    [[[.2,.3,.8]]*33]*33,
    [[[.2,.3,.8]]*32],
    [[[.2,.3,.8,.9]]*33],
    [[[1.1,.3,.8]]*33],
    [[[.2,float('nan'),.8]]*33],
])
def test_rejects_unbounded_or_invalid_skeletons(poses):
    data=report();data['poses']=poses
    with pytest.raises(ValueError): DeviceResult.model_validate(data)


def test_skeletons_are_optional_and_missing_joints_stay_missing():
    assert DeviceResult.model_validate(report()).poses==[]
    data=report();data['poses']=[[None]*32+[[.1,.2,.9]]]
    assert DeviceResult.model_validate(data).poses==data['poses']


def test_motion_channel_preserves_crowd_skeletons_and_records_distinct_reviews(tmp_path):
    app=create_app(database=tmp_path/'motion.sqlite',relay_only=True)
    with TestClient(app,base_url=ORIGIN['origin']) as client:
        operator(client);cam=camera(client);pair(client,cam['id'])
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream',headers=ORIGIN) as ws:
            ws.receive_json()
            ws.send_json(dict(type='device-status',state='ready',delegate='GPU',detail='Ready'))
            ws.send_json(dict(type='device-motion-status',state='ready',delegate='CPU',detail='Motion ready'))
            ws.send_bytes(packet(6000));ws.receive_json()
            crowd=report(6000)
            crowd.update(observedPeople=20,events=[],poses=[[[.1,.2,.9]]*33])
            ws.send_json(crowd)
            motion=report(5900)
            motion.update(type='device-motion',delegate='CPU',poses=[[[.5,.6,.8]]*33],
                events=[dict(id='motion-review-1',occurredAtMs=5900,detail='Human review required')])
            assert DeviceMotion.model_validate(motion).type=='device-motion'
            ws.send_json(motion)
            ws.send_bytes(packet(6100));ws.receive_json()
            state=client.get('/api/v2/state').json()
            camera_state=state['cameras'][0]
            assert camera_state['result']['timestampMs']==6000
            assert camera_state['result']['coverage']['observedPeople']==20
            assert camera_state['result']['poses']==crowd['poses']
            assert camera_state['motionResult']['timestampMs']==5900
            assert camera_state['motionStatus']['delegate']=='CPU'
            assert camera_state['motionResult']['poses']==motion['poses']
            assert state['analytics']['total']==1
            # Repeated source event IDs deduplicate across subsequent motion reports.
            motion['timestampMs']=6000
            ws.send_json(motion)
            ws.send_bytes(packet(6200));ws.receive_json()
            assert client.get('/api/v2/state').json()['analytics']['total']==1
            live=app.state.classroom.live[cam['id']]
            assert live['lastDeviceTimestamp']==6000 and live['lastMotionTimestamp']==6000
            live['motionAnalyzed']=time.monotonic()-3.1
            snapshot=app.state.classroom.snapshot()['cameras'][0]
            assert snapshot['motionResult'] is None and snapshot['result'] is not None
            ws.send_json(dict(type='device-motion-status',state='error',delegate=None,detail='Motion unavailable'))
            ws.send_bytes(packet(6300));ws.receive_json()
            snapshot=client.get('/api/v2/state').json()['cameras'][0]
            assert snapshot['motionStatus']['state']=='error'
            assert snapshot['motionResult'] is None
            assert snapshot['result']['timestampMs']==6000


def test_motion_channel_requires_announced_readiness(tmp_path):
    app=create_app(database=tmp_path/'motion.sqlite',relay_only=True)
    with TestClient(app,base_url=ORIGIN['origin']) as client:
        operator(client);cam=camera(client);pair(client,cam['id'])
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream',headers=ORIGIN) as ws:
            ws.receive_json()
            ws.send_json(dict(type='device-status',state='ready',delegate='GPU',detail='Crowd ready only'))
            data=report();data['type']='device-motion'
            ws.send_json(data)
            with pytest.raises(WebSocketDisconnect): ws.receive_json()


@pytest.mark.parametrize(('source_ms','stale_jpeg','accepted'), [(7500,False,True),(6500,False,False),(7500,True,False)])
def test_motion_reports_require_three_second_source_and_preview_freshness(tmp_path,source_ms,stale_jpeg,accepted):
    app=create_app(database=tmp_path/'motion.sqlite',relay_only=True)
    with TestClient(app,base_url=ORIGIN['origin']) as client:
        operator(client);cam=camera(client);pair(client,cam['id'])
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream',headers=ORIGIN) as ws:
            ws.receive_json()
            ws.send_json(dict(type='device-motion-status',state='ready',delegate='GPU',detail='Motion ready'))
            ws.send_bytes(packet(10000));ws.receive_json()
            live=app.state.classroom.live[cam['id']]
            if stale_jpeg: live['received']=time.monotonic()-3.1
            data=report(source_ms);data.update(type='device-motion',events=[])
            ws.send_json(data)
            ws.send_bytes(packet(10100));ws.receive_json()
            snapshot=client.get('/api/v2/state').json()['cameras'][0]
            assert (snapshot['motionResult'] is not None)==accepted
            assert snapshot['result'] is None


@pytest.mark.parametrize(('source_ms','stale_jpeg','accepted'), [
    (7000,False,True), (3000,False,False), (7000,True,False), (12001,False,False),
])
def test_bounded_slow_device_results_require_recent_preview(tmp_path,source_ms,stale_jpeg,accepted):
    app=create_app(database=tmp_path/'db.sqlite',relay_only=True)
    with TestClient(app,base_url=ORIGIN['origin']) as client:
        operator(client);cam=camera(client);pair(client,cam['id'])
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream',headers=ORIGIN) as ws:
            ws.receive_json()
            ws.send_json(dict(type='device-status',state='ready',delegate='GPU',detail='Device GPU'))
            ws.send_bytes(packet(10000));ws.receive_json()
            live=app.state.classroom.live[cam['id']]
            if stale_jpeg: live['received']=time.monotonic()-7
            data=report(source_ms);data['events']=[]
            ws.send_json(data)
            # The next preview acknowledgment confirms the earlier report was processed.
            ws.send_bytes(packet(10100));ws.receive_json()
            result=client.get('/api/v2/state').json()['cameras'][0]['result']
            assert (result is not None)==accepted
            assert live['lastDeviceTimestamp']==(source_ms if accepted else -1)
            assert not app.state.classroom.store.events()
            if accepted:
                assert result['timestampMs']==7000
                live['analyzed']=time.monotonic()-5.5
                assert app.state.classroom.snapshot()['cameras'][0]['analysis']=='current'
                live['analyzed']=time.monotonic()-6.1
                assert app.state.classroom.snapshot()['cameras'][0]['result'] is None


def test_oversized_device_report_closes_camera_socket(tmp_path):
    app=create_app(database=tmp_path/'db.sqlite',relay_only=True)
    with TestClient(app,base_url=ORIGIN['origin']) as client:
        operator(client);cam=camera(client);pair(client,cam['id'])
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream',headers=ORIGIN) as ws:
            ws.receive_json()
            ws.send_text(' '* (MAX_REPORT_BYTES+1))
            with pytest.raises(WebSocketDisconnect): ws.receive_json()


def test_relay_only_does_not_load_models_or_queue_pc_inference_and_deduplicates_events(tmp_path):
    def forbidden(): raise AssertionError('PC inference must never load')
    app=create_app(forbidden,forbidden,tmp_path/'db.sqlite',relay_only=True)
    with TestClient(app,base_url=ORIGIN['origin']) as client:
        operator(client); cam=camera(client); pair(client,cam['id'])
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream',headers=ORIGIN) as ws:
            ws.receive_json()
            ws.send_json(dict(type='device-status',state='ready',delegate='GPU',detail='Device GPU'))
            ws.send_bytes(packet(100)); assert ws.receive_json()['type']=='accepted'
            ws.send_json(report())
            ws.send_bytes(packet(200)); ws.receive_json()
            ws.send_json(report(200))
            # A following frame acknowledgement is an ordered processing barrier.
            ws.send_bytes(packet(300)); ws.receive_json()
            state=client.get('/api/v2/state').json()
            assert state['service']=='ready' and state['runtime']['compute']=='camera-device'
            assert state['analytics']['total']==1
            assert state['events'][0]['model']=='nivra-browser-motion-v1'
            assert state['cameras'][0]['result']['backend']=='camera-device'
            assert state['cameras'][0]['analysis']=='current'
            service=app.state.classroom
            assert not service.pending and service.state['models'] is None
            assert not service.live[cam['id']]['video']
            ws.send_json(dict(type='device-status',state='error',delegate=None,detail='Unavailable'))
            ws.send_bytes(packet(400)); ws.receive_json()
            state=client.get('/api/v2/state').json()
            assert state['cameras'][0]['analysis']=='unavailable'
            assert state['cameras'][0]['result'] is None
            assert state['cameras'][0]['feed']=='live'


@pytest.mark.parametrize('change', [dict(observedPeople=50),dict(cameraId='other'),dict(timestampMs=float('nan')),dict(events=[dict(id='e',occurredAtMs=999,detail='future')]),dict(tracks=[dict(id=1,box=[0,0,2,1])])])
def test_rejects_unbounded_cross_camera_or_invented_future_reports(change):
    data=copy.deepcopy(report());data.update(change)
    with pytest.raises(ValueError): DeviceResult.model_validate(data)


def test_unannounced_device_results_are_rejected(tmp_path):
    app=create_app(database=tmp_path/'db.sqlite',relay_only=True)
    with TestClient(app,base_url=ORIGIN['origin']) as client:
        operator(client);cam=camera(client);pair(client,cam['id'])
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream',headers=ORIGIN) as ws:
            ws.receive_json();ws.send_json(report())
            with pytest.raises(WebSocketDisconnect): ws.receive_json()
