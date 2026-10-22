import base64
import copy
import json
import struct
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from nivra.native_camera import NativeAnalysis, video_packet
from nivra.server import create_app
from test_classroom import operator, camera, pair, ORIGIN
from test_server import packet


def batch(sequence=1,timestamp=6000,generation='capture-one'):
    return dict(version=1,generation=generation,codec='avc1.4d4020',
        description=base64.b64encode(bytes([1,0x4d,0x40,0x20,0xff,0xe1,0])).decode(),
        width=1280,height=720,frames=[dict(sequence=sequence,timestampMs=timestamp,keyframe=True,
            data=base64.b64encode(b'\0\0\0\2\x65\x88').decode())])


def report(timestamp=6000,people=2,score=.71):
    return dict(type='native-analysis-v1',state='ready',detail='Phone model ready',
        people=dict(type='native-people-v1',model='apple-vision-body-pose',timestampMs=timestamp,
            inferenceMs=30,observedPeople=people,posePeople=people,
            tracks=[dict(id=i,box=[.1+i*.02,.1,.4+i*.02,.8]) for i in range(people)],
            poses=[[None]*32+[[.3,.4,.9]] for _ in range(people)]),
        fight=dict(type='native-fight-v1',model='nivra-x3d-rwf2000-v1',timestampMs=timestamp,
            windowStartMs=timestamp-4000,windowEndMs=timestamp,uniqueFrames=16,inferenceMs=100,
            publisherScore=score,modelScore=.95,windowReady=True))


def test_native_video_binary_clock_and_payload():
    encoded,seq,stamp=video_packet(batch(),'camera','stream')
    size=struct.unpack('<I',encoded[:4])[0]
    header=json.loads(encoded[4:4+size])
    assert (seq,stamp)==(1,6000)
    assert header['encoding']=='h264' and header['videoGeneration']=='capture-one'
    assert header['frames']==[dict(sequence=1,timestampMs=6000,keyframe=True,offset=0,length=6)]
    assert encoded[4+size:]==b'\0\0\0\2\x65\x88'


@pytest.mark.parametrize('change',[{'codec':'avc1.ffffff'},{'width':4096},{'description':'?invalid'},
    {'frames':[]},{'version':True},{'extra':'no'}])
def test_native_video_rejects_invalid_or_unbounded_metadata(change):
    with pytest.raises(ValueError): video_packet({**batch(),**change},'camera','stream')


def test_video_rejects_truncated_nal_and_replayed_clocks():
    data=batch()
    data['frames'][0]['data']=base64.b64encode(b'\0\0\0\xff\x65').decode()
    with pytest.raises(ValueError): video_packet(data,'c','g')
    with pytest.raises(ValueError): video_packet(batch(),'c','g',after=1)
    with pytest.raises(ValueError): video_packet(batch(),'c','g',last_timestamp=6000)


@pytest.mark.parametrize('change',[{'uniqueFrames':1},{'windowStartMs':5999},{'windowReady':False},
    {'publisherScore':float('nan')},{'model':'nivra-browser-motion-v1'}])
def test_fight_requires_same_model_real_window_and_bounded_scores(change):
    data=report();data['fight'].update(change)
    with pytest.raises(ValueError): NativeAnalysis.model_validate(data)


@pytest.mark.parametrize('duration',[3799.999999999999,4500.000000000001])
def test_fight_window_accepts_source_timestamp_roundoff(duration):
    data=report()
    data['fight']['windowStartMs']=data['fight']['windowEndMs']-duration
    assert NativeAnalysis.model_validate(data).fight is not None


@pytest.mark.parametrize('duration',[3799.99,4500.01])
def test_fight_window_still_rejects_outside_roundoff_tolerance(duration):
    data=report()
    data['fight']['windowStartMs']=data['fight']['windowEndMs']-duration
    with pytest.raises(ValueError): NativeAnalysis.model_validate(data)


def test_native_phone_reports_do_not_load_or_call_mac_models_and_deduplicate_alerts(tmp_path):
    def forbidden(*_): raise AssertionError('Native phone must not run Mac models')
    app=create_app(database=tmp_path/'db',model_factory=forbidden,pipeline_factory=forbidden,relay_only=True)
    app.state.classroom.state['nativeCamera']=True
    with TestClient(app,base_url=ORIGIN['origin']) as client:
        operator(client);cam=camera(client);pair(client,cam['id'])
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream',headers=ORIGIN) as ws:
            ws.receive_json()
            ws.send_json({'type':'native-hello','version':1})
            assert ws.receive_json()=={'type':'native-ready'}
            ws.send_json({'type':'native-video-v1',**batch()})
            assert ws.receive_json()=={'type':'video-accepted','sequence':1}
            ws.send_json(report(people=20))
            ws.send_bytes(packet(6100));ws.receive_json()
            state=client.get('/api/v2/state').json()
            current=state['cameras'][0]
            assert current['compute']=='native' and current['deviceStatus']['delegate']=='iOS'
            assert current['result']['coverage']['observedPeople']==20
            assert len(current['result']['poses'])==20
            assert state['analytics']['total']==1
            assert state['events'][0]['model']=='nivra-x3d-rwf2000-v1'
            ws.send_json(report(people=20))
            ws.send_bytes(packet(6200));ws.receive_json()
            assert client.get('/api/v2/state').json()['analytics']['total']==1
            assert app.state.classroom.state['models'] is None


@pytest.mark.parametrize(('people','timestamp','score'),[(1,6000,.71),(2,1000,.71),(2,6000,.1)])
def test_no_alert_for_single_person_stale_source_or_low_score(tmp_path,people,timestamp,score):
    app=create_app(database=tmp_path/'db',relay_only=True);app.state.classroom.state['nativeCamera']=True
    with TestClient(app,base_url=ORIGIN['origin']) as client:
        operator(client);cam=camera(client);pair(client,cam['id'])
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream',headers=ORIGIN) as ws:
            ws.receive_json();ws.send_json({'type':'native-hello','version':1});ws.receive_json()
            ws.send_bytes(packet(6000));ws.receive_json()
            data=report(people=people,score=score)
            if timestamp==1000:
                data['people']['timestampMs']=1000
                data['fight']=None
            ws.send_json(data)
            ws.send_bytes(packet(6100));ws.receive_json()
            assert client.get('/api/v2/state').json()['analytics']['total']==0


def test_public_host_rejects_native_protocol_negotiation(tmp_path):
    app=create_app(database=tmp_path/'db',relay_only=True)
    with TestClient(app,base_url=ORIGIN['origin']) as client:
        operator(client);cam=camera(client);pair(client,cam['id'])
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream',headers=ORIGIN) as ws:
            ws.receive_json();ws.send_json({'type':'native-hello','version':1})
            with pytest.raises(WebSocketDisconnect): ws.receive_json()


def test_delayed_report_cannot_flag_after_video_stops(tmp_path):
    app=create_app(database=tmp_path/'db',relay_only=True);app.state.classroom.state['nativeCamera']=True
    with TestClient(app,base_url=ORIGIN['origin']) as client:
        operator(client);cam=camera(client);pair(client,cam['id'])
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream',headers=ORIGIN) as ws:
            ws.receive_json();ws.send_json({'type':'native-hello','version':1});ws.receive_json()
            ws.send_bytes(packet(6000));ws.receive_json()
            app.state.classroom.live[cam['id']]['received']=time.monotonic()-4
            ws.send_json(report())
            ws.send_bytes(packet(6100));ws.receive_json()
            state=client.get('/api/v2/state').json()
            assert state['analytics']['total']==0 and state['cameras'][0]['result'] is None


def test_bridge_reconnect_does_not_repeat_same_recent_incident(tmp_path):
    app=create_app(database=tmp_path/'db',relay_only=True);app.state.classroom.state['nativeCamera']=True
    with TestClient(app,base_url=ORIGIN['origin']) as client:
        operator(client);cam=camera(client);pair(client,cam['id'])
        for _ in range(2):
            with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream',headers=ORIGIN) as ws:
                ws.receive_json();ws.send_json({'type':'native-hello','version':1});ws.receive_json()
                ws.send_bytes(packet(6000));ws.receive_json();ws.send_json(report())
                ws.send_bytes(packet(6100));ws.receive_json()
        assert client.get('/api/v2/state').json()['analytics']['total']==1
