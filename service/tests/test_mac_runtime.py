from types import SimpleNamespace
import pytest
from nivra import models
from nivra.tls import serving_options
from fastapi.testclient import TestClient
from nivra.server import create_app
from test_classroom import operator, camera, pair, ORIGIN
from test_server import FakePipeline, packet
from test_device_analysis import report
import time


@pytest.mark.parametrize('cuda,mps,expected', [(True, True, 'cuda'), (False, True, 'mps'), (False, False, 'cpu')])
def test_device_order_and_cpu_override(monkeypatch, cuda, mps, expected):
    monkeypatch.delenv('NIVRA_DEVICE', raising=False)
    monkeypatch.setattr(models.torch.cuda, 'is_available', lambda: cuda)
    monkeypatch.setattr(models.torch.backends, 'mps', SimpleNamespace(is_available=lambda: mps))
    assert models.select_device() == expected
    monkeypatch.setenv('NIVRA_DEVICE', 'cpu')
    assert models.select_device() == 'cpu'
    with pytest.raises(ValueError): models.select_device('tpu')
    if not cuda:
        with pytest.raises(RuntimeError): models.select_device('cuda')


def test_provider_selection(monkeypatch):
    monkeypatch.setattr(models.ort, 'get_available_providers', lambda: ['CoreMLExecutionProvider', 'CPUExecutionProvider'])
    assert models.onnx_providers('mps') == ['CoreMLExecutionProvider', 'CPUExecutionProvider']
    assert models.onnx_providers('cpu') == ['CPUExecutionProvider']
    assert models.onnx_providers('cuda') == ['CPUExecutionProvider']


def test_tls_options(tmp_path):
    assert serving_options({}) == dict(host='127.0.0.1', port=8765, ssl_certfile=None, ssl_keyfile=None)
    cert, key = tmp_path/'cert', tmp_path/'key'
    cert.touch(); key.touch()
    env = dict(NIVRA_TLS_CERT=str(cert), NIVRA_TLS_KEY=str(key))
    assert serving_options(env)['port'] == 8443
    assert serving_options(env)['host'] == '0.0.0.0'
    assert serving_options(dict(env, NIVRA_PORT='9443'))['port'] == 9443
    for bad in [dict(NIVRA_TLS_CERT=str(cert)), dict(NIVRA_TLS_KEY=str(key)),
                dict(env, NIVRA_TLS_KEY='missing'), dict(NIVRA_PORT='0'),
                dict(NIVRA_PORT='65536'), dict(NIVRA_PORT='not-a-port')]:
        with pytest.raises(ValueError): serving_options(bad)


def test_overload_uses_standby_device_reports(tmp_path, monkeypatch):
    monkeypatch.setenv('NIVRA_AUTO_RELAY', '1')
    class CPUModels:
        runtime = dict(device='cpu')
    app = create_app(CPUModels, FakePipeline, tmp_path/'db.sqlite')
    with TestClient(app, base_url=ORIGIN['origin']) as client:
        operator(client); cam = camera(client); pair(client, cam['id'])
        service = app.state.classroom
        service.analysis_ms, service.analysis_samples = 2000, 11
        with client.websocket_connect('ws://127.0.0.1:8765/api/v2/camera/stream', headers=ORIGIN) as socket:
            socket.receive_json()
            socket.send_json(dict(type='device-status', state='ready', delegate='GPU', detail='Standby'))
            socket.send_bytes(packet(100)); socket.receive_json()
            for _ in range(100):
                if service.state['relayOnly']: break
                time.sleep(.01)
            assert service.state['relayOnly']
            assert service.runtime()['fallbackReason']
            socket.send_json(report())
            socket.send_bytes(packet(200)); socket.receive_json()
            snapshot = client.get('/api/v2/state').json()
            assert snapshot['cameras'][0]['result']['backend'] == 'camera-device'
            assert snapshot['events'][0]['clip']['frames'] > 0


def test_mac_model_load_failure_switches_to_device(tmp_path, monkeypatch):
    monkeypatch.setattr('nivra.server.platform.system', lambda: 'Darwin')
    monkeypatch.setenv('NIVRA_AUTO_RELAY', '1')
    def fail(): raise RuntimeError('Unsupported backend')
    app = create_app(fail, FakePipeline, tmp_path/'db.sqlite')
    with TestClient(app, base_url=ORIGIN['origin']) as client:
        for _ in range(100):
            health = client.get('/api/v1/health').json()
            if health['runtime']: break
            time.sleep(.01)
        assert health['backend'] == 'relay-only'
        assert health['runtime']['device'] == 'camera-device'
        assert health['runtime']['fallbackReason']
