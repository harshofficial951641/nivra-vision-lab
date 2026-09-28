import copy
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from nivra.server import create_app
from nivra.device_analysis import DeviceResult
from test_classroom import operator, camera, pair, ORIGIN
from test_server import packet


def report(t=100):
    return dict(type='device-result',model='nivra-browser-motion-v1',delegate='GPU',timestampMs=t,
        inferenceMs=25,observedPeople=2,usablePeople=2,
        tracks=[dict(id=1,box=[.1,.1,.4,.8])],
        conflict=dict(status='alert',explanation='Directed motion'),
        events=[dict(id='run-conflict-1',occurredAtMs=100,detail='Review the scene')])


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
