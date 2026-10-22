"""PC/USB pose results reach the wall without inventing missing COCO joints."""
import time

from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from nivra.classroom import pc_pose_payload
from nivra.device_analysis import Skeleton, MAX_PEOPLE
from nivra.pipeline import drawable_pose, COCO_TO_MP
from nivra.server import create_app
from test_classroom import ORIGIN, operator, camera, pair
from test_server import FakeModels, packet


def observed_pose():
    return drawable_pose([[.123456, .654321, .9] for _ in range(17)])


def test_coco_mapping_preserves_only_observed_joints_and_matches_device_schema():
    source = observed_pose()
    output = pc_pose_payload([source])
    assert len(output) == 1 and len(output[0]) == 33
    observed = set(COCO_TO_MP.values())
    assert {index for index, point in enumerate(output[0]) if point is not None} == observed
    assert output[0][11] == [.1235, .6543, .9]
    assert output[0][1] is None  # COCO has no MediaPipe inner-eye landmark.
    assert TypeAdapter(list[Skeleton]).validate_python(output) == output
    assert source[11]['x'] == .123456  # Never modify the pipeline's result.


def test_invalid_missing_outside_and_zero_confidence_joints_are_not_clamped_or_filled():
    source = observed_pose()
    source[11]['x'] = -0.01
    source[12]['y'] = 1.01
    source[13]['visibility'] = float('nan')
    source[14] = {'x': .2, 'y': .3}  # No inferred confidence.
    source[15]['visibility'] = 0
    source[16]['x'] = True
    output = pc_pose_payload([source])
    assert all(output[0][index] is None for index in (11, 12, 13, 14, 15, 16))
    assert output[0][23] == [.1235, .6543, .9]
    assert pc_pose_payload([drawable_pose([[0, 0, 0]] * 17)]) == []
    assert pc_pose_payload([source[:17]]) == []  # A COCO list is not a MediaPipe topology.
    assert pc_pose_payload(None) == []
    assert pc_pose_payload([observed_pose()] * (MAX_PEOPLE + 4)) == [pc_pose_payload([observed_pose()])[0]] * MAX_PEOPLE


def test_actual_classroom_pc_worker_exposes_compact_skeletons_in_its_snapshot(tmp_path):
    class Pipeline:
        def __init__(self, _models): pass
        def process(self, _frame, timestamp, _people, video_frames=None):
            return dict(timestampMs=timestamp, evidenceTimestampMs=timestamp, inferenceMs=3,
                        poses=[observed_pose()], tracks=[],
                        conflict={'status': 'clear', 'events': []})

    app = create_app(model_factory=FakeModels, pipeline_factory=Pipeline, database=tmp_path/'pc.sqlite')
    with TestClient(app, base_url=ORIGIN['origin']) as client:
        operator(client)
        cam = camera(client)
        pair(client, cam['id'])
        for _ in range(200):
            if app.state.classroom.state['models'] is not None: break
            time.sleep(.01)
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream', headers=ORIGIN) as socket:
            assert socket.receive_json()['type'] == 'ready'
            socket.send_bytes(packet(100))
            assert socket.receive_json()['type'] == 'accepted'
            for _ in range(200):
                current = client.get('/api/v2/state', headers=ORIGIN).json()['cameras'][0]
                if current['result'] is not None: break
                time.sleep(.01)
            assert current['compute'] == 'pc'
            assert current['result']['timestampMs'] == 100
            assert current['result']['poses'] == pc_pose_payload([observed_pose()])
            assert current['result']['poses'][0][1] is None
