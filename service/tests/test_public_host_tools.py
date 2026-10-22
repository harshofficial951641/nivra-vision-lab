"""The host tools remain bounded and keep credentials out of launchd."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'/'deploy'))
import public_host
import public_host_service
import vercel_environment


def tunnel_monitor(state, calls=None):
    def probe(url, **kwargs):
        label = 'local' if url.startswith('http://127.0.0.1') else 'control' if 'api.trycloudflare.com' in url else 'tunnel'
        if calls is not None:
            calls.append((label, kwargs))
        return state[label]
    return public_host.TunnelHealthMonitor('https://qa-test.trycloudflare.com', 'private-test-secret', probe=probe)


def test_resolving_but_http_blackholed_tunnel_requires_three_confirmed_checks():
    import pytest
    calls = []
    monitor = tunnel_monitor(dict(local=True, control=True, tunnel=False), calls)
    monitor.check(0)
    for moment in (1, 2, 19):
        monitor.check(moment)
    assert monitor.failures == 1 and len(calls) == 3
    monitor.check(20)
    assert monitor.failures == 2
    with pytest.raises(RuntimeError, match='stopped responding') as error:
        monitor.check(40)
    assert 'qa-test' not in str(error.value) and 'private-test-secret' not in str(error.value)
    assert len(calls) == 9
    assert all('secret' not in options for label, options in calls if label == 'control')


def test_healthy_tunnel_resets_transient_failures():
    state = dict(local=True, control=True, tunnel=False)
    monitor = tunnel_monitor(state)
    monitor.check(0)
    monitor.check(20)
    state['tunnel'] = True
    monitor.check(40)
    assert monitor.failures == 0
    state['tunnel'] = False
    monitor.check(60)
    assert monitor.failures == 1


def test_offline_or_unhealthy_local_application_never_restarts_tunnel():
    for failed_dependency in ('control', 'local'):
        state = dict(local=True, control=True, tunnel=False)
        monitor = tunnel_monitor(state)
        monitor.check(0)
        monitor.check(20)
        state[failed_dependency] = False
        for moment in range(40, 400, 20):
            monitor.check(moment)
        assert monitor.failures == 0
        state[failed_dependency] = True
        monitor.check(400)
        assert monitor.failures == 1


def test_monitor_has_only_one_inflight_check_even_for_concurrent_callers():
    import threading
    entered, release = threading.Event(), threading.Event()
    calls = []
    def probe(url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            entered.set()
            assert release.wait(2)
        return True
    monitor = public_host.TunnelHealthMonitor('https://qa-test.trycloudflare.com', 'test', probe=probe)
    worker = threading.Thread(target=monitor.check, args=(0,))
    worker.start()
    try:
        assert entered.wait(2)
        for moment in (20, 40, 60):
            monitor.check(moment)
        assert len(calls) == 1
    finally:
        release.set()
        worker.join(2)
    assert not worker.is_alive() and len(calls) == 3


def test_application_probe_accepts_backend_json_but_rejects_cloudflare_html():
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            seen.append((self.path, self.headers.get('X-Nivra-Relay')))
            if self.path == '/redirect':
                self.send_response(302)
                self.send_header('Location', '/must-not-follow')
                self.end_headers()
                return
            body = (b'<html>Forbidden</html>' if self.path == '/html' else
                    json.dumps({'detail': 'Create a workspace or pair this phone to continue.'}).encode())
            self.send_response(403)
            self.send_header('Content-Type', 'text/html' if self.path == '/html' else 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = 'http://127.0.0.1:'+str(server.server_port)
    try:
        assert public_host.application_probe(base+'/application', secret='private-test-secret')
        assert not public_host.application_probe(base+'/html', secret='private-test-secret')
        assert not public_host.application_probe(base+'/redirect', secret='private-test-secret')
        assert public_host.application_probe(base+'/html', application=False)
        assert not any(path == '/must-not-follow' for path, _ in seen)
        assert seen[-1][1] is None
    finally:
        server.shutdown()
        server.server_close()
        worker.join(2)


def test_probe_hard_deadline_kills_and_reaps_each_stuck_dns_worker(monkeypatch):
    import time
    children = []
    original = public_host.subprocess.Popen
    def record(arguments, **kwargs):
        assert 'private-test-secret' not in str(arguments)
        child = original(arguments, **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(public_host.subprocess, 'Popen', record)
    monkeypatch.setattr(public_host, '_HTTP_PROBE_SCRIPT', 'import time; time.sleep(60)')
    began = time.monotonic()
    for _ in range(3):
        assert not public_host.application_probe('https://qa-test.trycloudflare.com/api/v2/state',
            secret='private-test-secret', timeout=.05)
        assert all(child.poll() is not None for child in children)
    assert len(children) == 3 and time.monotonic()-began < 2


def test_timed_out_deploy_exits_before_a_retry():
    import os
    import pytest
    children = []
    with pytest.raises(RuntimeError, match='deadline'):
        public_host.command(children, [sys.executable, '-c', 'import time; time.sleep(60)'],
                            timeout=.05, env=os.environ.copy())
    assert len(children) == 1 and children[0].poll() is not None


def test_vercel_environment_uses_confirmed_project_and_stdin_only(tmp_path, monkeypatch):
    monkeypatch.delenv('NIVRA_VERCEL_SCOPE',raising=False)
    import json
    import subprocess
    (tmp_path/'.vercel').mkdir()
    (tmp_path/'.vercel/project.json').write_text(json.dumps(dict(projectName='nivra',projectId='prj_nivra',orgId='team_owner')))
    calls=[]
    def run(arguments, **kwargs):
        calls.append((arguments,kwargs))
        return subprocess.CompletedProcess(arguments,0)
    monkeypatch.setattr(vercel_environment.subprocess,'run',run)
    secret='private-relay-value-'+'x'*40
    upstream='https://example-relay.trycloudflare.com'
    vercel_environment.publish(upstream,secret,'prj_nivra',tmp_path)
    assert len(calls)==2
    for (arguments,kwargs),key,value in zip(calls,['NIVRA_UPSTREAM','NIVRA_RELAY_SECRET'],[upstream,secret]):
        assert arguments==['vercel','env','add',key,'production','--force','--yes',
            '--project','prj_nivra','--scope','team_owner','--type','secret']
        assert value not in arguments
        assert kwargs['input']==value+'\n' and kwargs['timeout']==90
        assert kwargs['stdout']==subprocess.DEVNULL and kwargs['stderr']==subprocess.DEVNULL
        assert kwargs['env']['VERCEL_CLI_USE_NATIVE_BINARY']=='0'


def test_vercel_environment_rejects_different_project_before_any_write(tmp_path, monkeypatch):
    import json
    import pytest
    (tmp_path/'.vercel').mkdir()
    (tmp_path/'.vercel/project.json').write_text(json.dumps(dict(projectName='other',projectId='prj_other',orgId='team_owner')))
    def forbidden(*args,**kwargs): raise AssertionError('must not publish')
    monkeypatch.setattr(vercel_environment.subprocess,'run',forbidden)
    with pytest.raises(RuntimeError,match='confirmed NIVRA'):
        vercel_environment.publish('https://relay.trycloudflare.com','x'*48,'prj_nivra',tmp_path)


def test_host_defaults_to_confirmed_vercel_without_netlify_configuration(monkeypatch):
    monkeypatch.delenv('NIVRA_VERCEL_SCOPE',raising=False)
    monkeypatch.delenv('NIVRA_DEPLOY_PROVIDER',raising=False)
    monkeypatch.setenv('NIVRA_VERCEL_PROJECT_ID','prj_nivra')
    def forbidden(): raise AssertionError('must not configure Netlify')
    monkeypatch.setattr(public_host,'configure',forbidden)
    monkeypatch.setattr(vercel_environment,'linked_project',lambda root,expected: dict(projectId=expected,orgId='team_owner'))
    provider,site=public_host.deployment_target()
    assert (provider,site)==('vercel',dict(id='prj_nivra',orgId='team_owner'))
    assert public_host.frontend_commands(provider,site)==[
        ['node','scripts/deploy/prepare_vercel.mjs'],
        ['vercel','deploy','--prebuilt','--prod','--yes','--scope','team_owner']]


def test_retry_budget_stops_after_three_failures_and_resets_after_quiet_period():
    budget = public_host.RetryBudget()
    assert budget.failed(0)
    assert budget.failed(20)
    assert not budget.failed(40)
    assert budget.failed(940)
    assert len(budget.failures) == 1


def test_launch_agent_uses_exact_paths_and_no_inherited_credentials(tmp_path,monkeypatch):
    for key in ('NIVRA_VERCEL_SCOPE','NIVRA_VERCEL_PROJECT_ID','NIVRA_DEPLOY_PROVIDER'):
        monkeypatch.delenv(key,raising=False)
    root = tmp_path/'repo with spaces'
    state = tmp_path/'state'
    definition = public_host_service.agent_definition(root, state, tmp_path/'home', '/tools/node/bin/node')
    assert definition['ProgramArguments'] == [str(root/'service/.venv/bin/python'),
        str(root/'scripts/deploy/public_host.py'), '--supervise']
    assert definition['WorkingDirectory'] == str(tmp_path/'home')
    assert definition['KeepAlive'] is False
    assert definition['RunAtLoad'] is True
    assert set(definition['EnvironmentVariables']) == {'PATH', 'HOME', 'PYTHONUNBUFFERED'}
    assert definition['EnvironmentVariables']['PATH'].startswith('/tools/node/bin:')
    assert definition['StandardErrorPath'] == str(tmp_path/'home/Library/Logs/NIVRA/public-host.log')


def test_vercel_scope_override_is_shared_by_environment_and_deployment(tmp_path,monkeypatch):
    import json
    import subprocess
    (tmp_path/'.vercel').mkdir()
    (tmp_path/'.vercel/project.json').write_text(json.dumps(dict(projectName='nivra',projectId='prj_nivra',orgId='team_owner')))
    monkeypatch.setenv('NIVRA_VERCEL_SCOPE','topperly4-3974s-projects')
    calls=[]
    def run(arguments,**kwargs):
        calls.append(arguments)
        return subprocess.CompletedProcess(arguments,0)
    monkeypatch.setattr(vercel_environment.subprocess,'run',run)
    vercel_environment.publish('https://relay.trycloudflare.com','x'*48,'prj_nivra',tmp_path)
    commands=public_host.frontend_commands('vercel',dict(id='prj_nivra',orgId='team_owner'))
    for arguments in [*calls,commands[-1]]:
        assert arguments[arguments.index('--scope')+1]=='topperly4-3974s-projects'


def test_launch_agent_persists_only_validated_public_deployment_settings(tmp_path,monkeypatch):
    import json
    (tmp_path/'.vercel').mkdir()
    (tmp_path/'.vercel/project.json').write_text(json.dumps(dict(projectName='nivra',projectId='prj_nivra',orgId='team_owner')))
    monkeypatch.delenv('NIVRA_VERCEL_PROJECT_ID',raising=False)
    monkeypatch.setenv('NIVRA_VERCEL_SCOPE','topperly4-3974s-projects')
    monkeypatch.setenv('NIVRA_DEPLOY_PROVIDER','vercel')
    monkeypatch.setenv('NIVRA_RELAY_SECRET','must-not-be-in-plist')
    monkeypatch.setenv('VERCEL_TOKEN','must-not-be-in-plist')
    environment=public_host_service.agent_definition(tmp_path,tmp_path/'state',tmp_path/'home','/tools/node')['EnvironmentVariables']
    assert environment['NIVRA_VERCEL_SCOPE']=='topperly4-3974s-projects'
    assert environment['NIVRA_VERCEL_PROJECT_ID']=='prj_nivra'
    assert environment['NIVRA_DEPLOY_PROVIDER']=='vercel'
    assert 'NIVRA_RELAY_SECRET' not in environment and 'VERCEL_TOKEN' not in environment


def test_invalid_scope_rejected_before_cli_or_agent_install(tmp_path,monkeypatch):
    import pytest
    monkeypatch.setenv('NIVRA_VERCEL_SCOPE','--token=unsafe scope')
    with pytest.raises(RuntimeError,match='scope'):
        public_host.frontend_commands('vercel',dict(id='prj_nivra',orgId='team_owner'))
    with pytest.raises(RuntimeError,match='scope'):
        public_host_service.agent_definition(tmp_path,tmp_path/'state',tmp_path/'home','/tools/node')


def test_private_writes_replace_atomically_without_changing_permissions(tmp_path):
    path = tmp_path/'status.json'
    public_host.write_private(path, 'first')
    path.chmod(0o644)
    public_host.write_private(path, 'second')
    assert path.read_text() == 'second'
    assert path.stat().st_mode & 0o777 == 0o600
    assert list(tmp_path.iterdir()) == [path]


def test_tunnel_discovery_is_bounded_when_it_exits_without_address():
    class Tunnel:
        stdout = iter(['diagnostic line with no public URL\n'])
        def poll(self): return 1
    import pytest
    with pytest.raises(RuntimeError, match='startup deadline'):
        public_host.tunnel_address(Tunnel(), timeout=.01)


def test_status_pid_checks_distinguish_dead_and_live_processes(monkeypatch):
    assert not public_host_service.pid_alive(None)
    assert not public_host_service.pid_alive(1)
    monkeypatch.setattr(public_host_service.os, 'kill', lambda pid, sig: None)
    assert public_host_service.pid_alive(123)

    def missing(pid, sig): raise ProcessLookupError()
    monkeypatch.setattr(public_host_service.os, 'kill', missing)
    assert not public_host_service.pid_alive(123)


def test_publish_environment_replaces_existing_keys_without_duplicate_creation(monkeypatch):
    calls = []

    def api(path, method='GET', data=None):
        calls.append((path, method, data))
        if method == 'GET': return [{'key': 'NIVRA_UPSTREAM'}, {'key': 'NIVRA_RELAY_SECRET'}]

    monkeypatch.setattr(public_host, 'api', api)
    public_host.publish_environment({'account_id': 'owner', 'id': 'nivra'}, 'https://new.trycloudflare.com', 'test-secret')
    assert calls == [
        ('accounts/owner/env?site_id=nivra', 'GET', None),
        ('accounts/owner/env/NIVRA_UPSTREAM?site_id=nivra', 'PUT', {'key': 'NIVRA_UPSTREAM', 'values': [{'context': 'all', 'value': 'https://new.trycloudflare.com'}]}),
        ('accounts/owner/env/NIVRA_RELAY_SECRET?site_id=nivra', 'PUT', {'key': 'NIVRA_RELAY_SECRET', 'values': [{'context': 'all', 'value': 'test-secret'}]}),
    ]


def test_publish_environment_creates_only_missing_key(monkeypatch):
    calls = []

    def api(path, method='GET', data=None):
        calls.append((path, method, data))
        if method == 'GET': return [{'key': 'NIVRA_UPSTREAM'}, {'key': 'UNRELATED_KEY'}]

    monkeypatch.setattr(public_host, 'api', api)
    public_host.publish_environment({'account_id': 'owner', 'id': 'nivra'}, 'https://new.trycloudflare.com', 'test-secret')
    assert [call[1] for call in calls] == ['GET', 'PUT', 'POST']
    assert calls[-1] == ('accounts/owner/env?site_id=nivra', 'POST', [
        {'key': 'NIVRA_RELAY_SECRET', 'values': [{'context': 'all', 'value': 'test-secret'}]}
    ])


def test_termination_falls_back_to_direct_child_when_group_signal_is_denied(monkeypatch):
    def denied(pid, signum): raise PermissionError()
    monkeypatch.setattr(public_host.os, 'killpg', denied)

    class Child:
        pid = 123
        stopped = False
        def poll(self): return None
        def terminate(self): self.stopped = True
        def wait(self, timeout): return 0

    child = Child()
    assert public_host.terminate(child)
    assert child.stopped


def test_termination_escalates_direct_child_when_group_kill_is_denied(monkeypatch):
    def denied(pid, signum): raise PermissionError()
    monkeypatch.setattr(public_host.os, 'killpg', denied)

    class Child:
        pid = 123
        waits = 0
        killed = False
        def poll(self): return None
        def terminate(self): pass
        def kill(self): self.killed = True
        def wait(self, timeout):
            self.waits += 1
            if self.waits == 1: raise public_host.subprocess.TimeoutExpired('test-child', timeout)
            return 0

    child = Child()
    assert public_host.terminate(child, timeout=.01)
    assert child.killed


def test_status_reports_live_direct_host_separately_from_stale_supervisor(tmp_path, monkeypatch):
    import json
    saved = {'state': 'running', 'supervisorPid': 100, 'hostPid': 101, 'failures': 0,
             'credential': 'NEVER-PRINT-THIS-SECRET'}
    runtime = {'hostPid': 200, 'backendPid': 201, 'tunnelPid': 202,
               'relaySecret': 'NEVER-PRINT-THIS-SECRET', 'upstream': 'https://private.example.test'}
    (tmp_path/'service-status.json').write_text(json.dumps(saved))
    (tmp_path/'runtime.json').write_text(json.dumps(runtime))
    monkeypatch.setattr(public_host_service, 'pid_alive', lambda pid: pid in {200, 201, 202})
    result = public_host_service.service_status(tmp_path, False)
    assert result['mode'] == 'direct'
    assert result['state'] == 'processes-running'
    assert result['hostPid'] == 200
    assert result['hostAlive'] and result['backendAlive'] and result['tunnelAlive']
    assert result['supervisor']['supervisorPid'] == 100
    assert result['supervisor']['state'] == 'stopped'
    assert result['checkScope'] == 'process-liveness-only'
    assert 'NEVER-PRINT' not in json.dumps(result)
    assert 'private.example.test' not in json.dumps(result)
    assert json.loads((tmp_path/'runtime.json').read_text()) == runtime


def test_status_marks_direct_host_degraded_when_child_has_exited(tmp_path, monkeypatch):
    import json
    (tmp_path/'runtime.json').write_text(json.dumps({'hostPid': 200, 'backendPid': 201, 'tunnelPid': 202}))
    monkeypatch.setattr(public_host_service, 'pid_alive', lambda pid: pid in {200, 201})
    result = public_host_service.service_status(tmp_path, False)
    assert result['mode'] == 'direct' and result['state'] == 'degraded'
    assert result['hostAlive'] and result['backendAlive'] and not result['tunnelAlive']


def test_status_ignores_dead_runtime_and_malformed_status_files(tmp_path, monkeypatch):
    (tmp_path/'runtime.json').write_text('{"hostPid": 200}')
    (tmp_path/'service-status.json').write_text('[]')
    monkeypatch.setattr(public_host_service, 'pid_alive', lambda pid: False)
    result = public_host_service.service_status(tmp_path, False)
    assert result['mode'] == 'stopped' and not result['hostAlive']
