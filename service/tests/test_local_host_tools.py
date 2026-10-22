"""LaunchAgent policy tests. All process/network/file operations use fakes or tmp_path."""
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def tools(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[2] / 'scripts/deploy/local_host_service.py'
    spec = importlib.util.spec_from_file_location('local_host_tools_tested', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'ROOT', tmp_path / 'repo')
    monkeypatch.setattr(module, 'PLIST', tmp_path / 'LaunchAgents/host.plist')
    monkeypatch.setattr(module, 'LOG', tmp_path / 'Logs/NIVRA/host.log')
    # An unexpected real process or HTTP request must fail the test immediately.
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **kw: pytest.fail('Unexpected process call'))
    monkeypatch.setattr(module, 'OPENER', SimpleNamespace(open=lambda *a, **kw: pytest.fail('Unexpected network call')))
    return module


def test_install_requires_real_prepared_assets(tools):
    with pytest.raises(SystemExit, match='local installation'):
        tools.install()
    assert not tools.PLIST.exists()


def test_install_writes_private_offline_agent_without_running_it(tools):
    import plistlib
    (tools.ROOT / 'service/.venv/bin').mkdir(parents=True)
    (tools.ROOT / 'service/.venv/bin/python').touch()
    (tools.ROOT / 'dist-usb').mkdir()
    (tools.ROOT / 'dist-usb/index.html').touch()
    tools.install()
    value = plistlib.loads(tools.PLIST.read_bytes())
    assert tools.PLIST.stat().st_mode & 0o777 == 0o600
    assert value['ProgramArguments'] == ['/usr/bin/caffeinate', '-i', str(tools.ROOT / 'service/.venv/bin/python'), str(tools.ROOT / 'service/run_local.py')]
    assert value['EnvironmentVariables']['NIVRA_AUTO_RELAY'] == '0'
    assert value['EnvironmentVariables']['NIVRA_CONNECTION'] == 'wireless'
    assert value['KeepAlive'] == {'SuccessfulExit': False}
    assert value['ThrottleInterval'] == 15
    assert value['Umask'] == 0o077
    assert tools.LOG.stat().st_mode & 0o777 == 0o600
    assert tools.LOG.parent.stat().st_mode & 0o777 == 0o700


def test_start_does_not_collide_with_healthy_manual_host(tools, monkeypatch):
    tools.PLIST.parent.mkdir(parents=True)
    tools.PLIST.touch()
    monkeypatch.setattr(tools, 'loaded', lambda: False)
    monkeypatch.setattr(tools, 'health', lambda: {'backend': 'local-ai', 'status': 'loading'})
    tools.start()


def test_bootstrap_returns_when_listener_is_ready_while_models_load(tools, monkeypatch):
    tools.PLIST.parent.mkdir(parents=True)
    tools.PLIST.touch()
    calls = []
    monkeypatch.setattr(tools, 'loaded', lambda: False)
    responses = iter([None, {'backend': 'local-ai', 'status': 'loading'}])
    monkeypatch.setattr(tools, 'health', lambda: next(responses))
    monkeypatch.setattr(tools.subprocess, 'run', lambda args, **kw: calls.append(args))
    tools.start()
    assert calls == [['/bin/launchctl', 'bootstrap', tools.DOMAIN, str(tools.PLIST)]]


def test_failed_readiness_is_bounded_and_reports_private_log(tools, monkeypatch):
    tools.PLIST.parent.mkdir(parents=True)
    tools.PLIST.touch()
    monkeypatch.setattr(tools, 'loaded', lambda: True)
    monkeypatch.setattr(tools, 'health', lambda: None)
    clock = iter([0, 0, 21])
    monkeypatch.setattr(tools.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(tools.time, 'sleep', lambda _: None)
    calls = []
    monkeypatch.setattr(tools.subprocess, 'run', lambda args, **kw: calls.append(args))
    with pytest.raises(SystemExit, match='could not start') as error:
        tools.start()
    assert str(tools.LOG) in str(error.value)
    assert calls == [['/bin/launchctl', 'kickstart', '-k', tools.TARGET]]


@pytest.mark.parametrize('health,config,expected', [
    ({'backend': 'local-ai', 'status': 'loading'}, {'enabled': True, 'transport': 'wireless'}, True),
    ({'backend': 'local-ai'}, {'enabled': True, 'transport': 'usb'}, False),
    ({'backend': 'local-ai'}, {'enabled': False, 'transport': 'wireless'}, False),
    ({'backend': 'relay-only'}, {'enabled': True, 'transport': 'wireless'}, True),
    ([], {}, False),
    ({'backend': 'local-ai'}, [], False),
])
def test_health_requires_wireless_local_host_not_unrelated_old_server(tools, monkeypatch, health, config, expected):
    calls = []
    def open_response(url, timeout):
        calls.append(url)
        assert url.startswith('http://127.0.0.1:8870/')
        assert timeout == 1
        return io.StringIO(json.dumps(config if url.endswith('/config') else health))
    monkeypatch.setattr(tools, 'OPENER', SimpleNamespace(open=open_response))
    assert (tools.health() is not None) is expected
    assert 1 <= len(calls) <= 2


def test_existing_log_permissions_are_repaired_without_erasing_it(tools):
    (tools.ROOT / 'service/.venv/bin').mkdir(parents=True)
    (tools.ROOT / 'service/.venv/bin/python').touch()
    (tools.ROOT / 'dist-usb').mkdir()
    (tools.ROOT / 'dist-usb/index.html').touch()
    tools.LOG.parent.mkdir(parents=True)
    tools.LOG.write_text('existing diagnostic')
    tools.LOG.chmod(0o644)
    tools.install()
    assert tools.LOG.read_text() == 'existing diagnostic'
    assert tools.LOG.stat().st_mode & 0o777 == 0o600



def test_restart_waits_for_launchd_removing_state_before_bootstrap(tools, monkeypatch):
    tools.PLIST.parent.mkdir(parents=True)
    tools.PLIST.touch()
    states = iter([True, True, False, False])
    monkeypatch.setattr(tools, 'loaded', lambda: next(states))
    responses = iter([None, {'backend': 'local-ai', 'status': 'loading'}])
    monkeypatch.setattr(tools, 'health', lambda: next(responses))
    operations = []
    monkeypatch.setattr(tools.subprocess, 'run', lambda args, **kw: operations.append(args))
    monkeypatch.setattr(tools.time, 'sleep', lambda delay: operations.append(('wait', delay)))
    tools.restart()
    assert operations == [
        ['/bin/launchctl', 'bootout', tools.TARGET],
        ('wait', .1),
        ['/bin/launchctl', 'bootstrap', tools.DOMAIN, str(tools.PLIST)],
    ]


def test_restart_times_out_without_starting_a_still_removing_job(tools, monkeypatch):
    monkeypatch.setattr(tools, 'loaded', lambda: True)
    clock = iter([0, 0, 5.1])
    monkeypatch.setattr(tools.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(tools.time, 'sleep', lambda _: None)
    operations = []
    monkeypatch.setattr(tools.subprocess, 'run', lambda args, **kw: operations.append(args))
    monkeypatch.setattr(tools, 'start', lambda: pytest.fail('Must not start a removing job'))
    with pytest.raises(SystemExit, match='still stopping'):
        tools.restart()
    assert operations == [['/bin/launchctl', 'bootout', tools.TARGET]]
