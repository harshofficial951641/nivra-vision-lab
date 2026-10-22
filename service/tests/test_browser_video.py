"""Paired browser AVCC transport preserves normal device analysis permissions."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from nivra.server import create_app
from test_classroom import operator, camera, pair, ORIGIN
from test_native_camera import batch


def setup(tmp_path):
    app = create_app(database=tmp_path/'browser-video.sqlite', relay_only=True)
    return app


def test_browser_video_ack_and_analysis_use_actual_h264_source_without_jpeg(tmp_path):
    app = setup(tmp_path)
    with TestClient(app, base_url=ORIGIN['origin']) as client:
        operator(client); cam=camera(client); pair(client,cam['id'])
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream',headers=ORIGIN) as ws:
            assert ws.receive_json()['browserVideo'] is True
            ws.send_json({'type':'browser-video-hello','version':1})
            assert ws.receive_json()=={'type':'browser-video-ready','version':1}
            ws.send_json({'type':'browser-video-v1',**batch()})
            assert ws.receive_json()=={'type':'video-accepted','sequence':1,'timestampMs':6000}
            ws.send_json(dict(type='device-status',state='ready',delegate='GPU',detail='Phone detector'))
            ws.send_json(dict(type='device-result',model='nivra-browser-motion-v1',delegate='GPU',
                timestampMs=6000,inferenceMs=20,observedPeople=0,usablePeople=0,tracks=[],poses=[],
                conflict=dict(status='clear',explanation='No people observed'),events=[]))
            ws.send_json({'type':'browser-video-v1',**batch(sequence=2,timestamp=6100)})
            ws.receive_json()
            current=client.get('/api/v2/state').json()['cameras'][0]
            assert current['feed']=='live' and current['compute']=='device'
            assert current['framesReceived']==2
            assert current['result']['timestampMs']==6000
            assert current['result']['delegate']=='GPU'
            assert app.state.classroom.live[cam['id']]['frames']==0


@pytest.mark.parametrize('action',['unnegotiated','repeated-hello','native-escalation','replayed-sequence','new-generation-delta'])
def test_browser_video_rejects_unnegotiated_replay_and_native_privilege(tmp_path,action):
    app=setup(tmp_path)
    with TestClient(app,base_url=ORIGIN['origin']) as client:
        operator(client);cam=camera(client);pair(client,cam['id'])
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream',headers=ORIGIN) as ws:
            ws.receive_json()
            if action!='unnegotiated':
                ws.send_json({'type':'browser-video-hello','version':1});ws.receive_json()
            if action in ('replayed-sequence','new-generation-delta'):
                ws.send_json({'type':'browser-video-v1',**batch()});ws.receive_json()
            message={'type':'browser-video-v1',**batch()}
            if action=='repeated-hello':message={'type':'browser-video-hello','version':1}
            if action=='native-escalation':message={'type':'native-hello','version':1}
            if action=='new-generation-delta':
                message={'type':'browser-video-v1',**batch(sequence=2,timestamp=6100,generation='next-capture')}
                message['frames'][0]['keyframe']=False
            ws.send_json(message)
            with pytest.raises(WebSocketDisconnect):ws.receive_json()


def test_owner_permission_alone_cannot_publish_browser_video(tmp_path):
    with TestClient(setup(tmp_path),base_url=ORIGIN['origin']) as client:
        operator(client);camera(client)
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream',headers=ORIGIN) as ws:ws.receive_json()
