"""Keep the private Mac relay and its public gateway together.

Only fixed status messages are printed. Credentials travel through private files,
stdin and the server environment, never command arguments or diagnostic output.
"""
import argparse
from collections import deque
import fcntl
import json
import os
from pathlib import Path
import queue
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

from netlify_configure import api, configure
import vercel_environment

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT/'service'/'state'/'public'
ORIGIN = 'https://nivra.tanishq.work'


class StopRequested(BaseException):
    pass


class RetryBudget:
    def __init__(self, limit=3, window=900):
        self.limit, self.window = limit, window
        self.failures = deque()

    def failed(self, now):
        while self.failures and now-self.failures[0] >= self.window:
            self.failures.popleft()
        self.failures.append(now)
        return len(self.failures) < self.limit


def dns_status(hostname):
    try:
        return 'resolved' if socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM) else 'unavailable'
    except socket.gaierror as error:
        missing = {socket.EAI_NONAME, getattr(socket, 'EAI_NODATA', socket.EAI_NONAME)}
        return 'missing' if error.errno in missing else 'unavailable'
    except OSError:
        return 'unavailable'


class TunnelDNSMonitor:
    """Detect an expired Quick Tunnel without treating lost internet as expiry."""
    def __init__(self, upstream, *, resolve=dns_status, interval=20):
        hostname = urlsplit(upstream).hostname or ''
        if not re.fullmatch(r'[a-z0-9-]+\.trycloudflare\.com', hostname):
            raise ValueError('Invalid public tunnel hostname')
        self.hostname, self.resolve, self.interval = hostname, resolve, interval
        self.next_check, self.failures = 0, 0

    def check(self, now):
        if now < self.next_check: return
        self.next_check = now+self.interval
        if self.resolve(self.hostname) == 'missing' and self.resolve('api.trycloudflare.com') == 'resolved':
            self.failures += 1
        else:
            self.failures = 0
        if self.failures >= 3:
            # Never print the hostname, relay credential or request details.
            raise RuntimeError('The public tunnel DNS expired; restarting the relay.')


def private_state():
    STATE.mkdir(parents=True, exist_ok=True)
    os.chmod(STATE, 0o700)


def write_private(path, value):
    temporary = path.with_name(path.name+'.'+secrets.token_hex(6)+'.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(value)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


def status(state, **values):
    write_private(STATE/'service-status.json', json.dumps({
        'state': state, 'updatedAt': time.time(), 'supervisorPid': os.getpid(), **values
    }, indent=2)+'\n')


def terminate(child, timeout=10):
    if child is None or child.poll() is not None:
        return True

    def send(signum):
        try: os.killpg(child.pid, signum)
        except ProcessLookupError: return
        except PermissionError:
            # macOS can deny a process-group signal while permitting the
            # direct child signal, notably for the system caffeinate binary.
            try:
                if signum == signal.SIGKILL: child.kill()
                else: child.terminate()
            except (ProcessLookupError, PermissionError): pass

    try:
        send(signal.SIGTERM)
        child.wait(timeout=timeout)
    except ProcessLookupError:
        pass
    except subprocess.TimeoutExpired:
        send(signal.SIGKILL)
        try: child.wait(timeout=3)
        except subprocess.TimeoutExpired: return False
    return True


def install_signal_handlers():
    def stop(*_):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        raise StopRequested()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)


def publish_environment(site, upstream, secret):
    path = 'accounts/'+site['account_id']+'/env'
    query = '?site_id='+site['id']
    existing = {item['key'] for item in api(path+query)}
    for key, value in [('NIVRA_UPSTREAM', upstream), ('NIVRA_RELAY_SECRET', secret)]:
        if key in existing:
            api(path+'/'+key+query, 'PUT', {'key': key, 'values': [{'context': 'all', 'value': value}]})
        else:
            api(path+query, 'POST', [{'key': key, 'values': [{'context': 'all', 'value': value}]}])


def deployment_target():
    provider = os.environ.get('NIVRA_DEPLOY_PROVIDER', 'vercel')
    if provider == 'netlify': return provider, configure()
    if provider != 'vercel': raise RuntimeError('The configured deployment provider is unsupported.')
    project = vercel_environment.linked_project(ROOT, os.environ.get('NIVRA_VERCEL_PROJECT_ID'))
    return provider, {'id': project['projectId'], 'orgId': project['orgId']}


def frontend_commands(provider, site):
    if provider == 'vercel':
        return [['node', 'scripts/deploy/prepare_vercel.mjs'],
                ['vercel', 'deploy', '--prebuilt', '--prod', '--yes', '--scope', vercel_environment.cli_scope(site)]]
    return [['npx', '--yes', 'netlify-cli', 'deploy', '--prod', '--no-build',
             '--site', site['id'], '--dir', 'dist', '--json']]


def ports_available():
    for port in (8765, 8766):
        with socket.socket() as probe:
            try: probe.bind(('127.0.0.1', port))
            except OSError:
                raise RuntimeError('A local NIVRA listener is already running.') from None


def tunnel_address(tunnel, timeout=60):
    found = queue.Queue(maxsize=1)

    def drain():
        sent = False
        for line in tunnel.stdout:
            match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', line)
            if match and not sent:
                found.put_nowait(match.group(0))
                sent = True
        # All subsequent tunnel diagnostics are discarded, including request data.

    threading.Thread(target=drain, daemon=True).start()
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        try: return found.get(timeout=min(1, max(.01, deadline-time.monotonic())))
        except queue.Empty:
            if tunnel.poll() is not None: break
    raise RuntimeError('Cloudflare did not provide a relay address within the startup deadline.')


def command(children, arguments, *, timeout, env):
    child = subprocess.Popen(arguments, cwd=ROOT, env=env, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
    children.append(child)
    try: code = child.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        terminate(child)
        raise RuntimeError('A deployment command exceeded its deadline.') from None
    if code: raise RuntimeError('A deployment command failed.')


def run():
    private_state()
    children, lock, backend_log = [], None, None
    install_signal_handlers()
    try:
        lock = (STATE/'host.lock').open('a')
        os.chmod(STATE/'host.lock', 0o600)
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another managed NIVRA host is already running.') from None
        ports_available()
        secret_path = STATE/'relay-secret'
        if not secret_path.exists(): write_private(secret_path, secrets.token_urlsafe(48))
        os.chmod(secret_path, 0o600)
        secret = secret_path.read_text().strip()
        if len(secret) < 40: raise RuntimeError('The relay credential must be regenerated locally.')
        provider, site = deployment_target()
        tunnel = subprocess.Popen(['/opt/homebrew/bin/cloudflared', 'tunnel', '--url',
            'http://127.0.0.1:8766', '--no-autoupdate', '--protocol', 'http2'], stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1, start_new_session=True)
        children.append(tunnel)
        upstream = tunnel_address(tunnel)
        log_path = STATE/'backend.log'
        if log_path.exists() and log_path.stat().st_size > 5*1024*1024:
            os.replace(log_path, STATE/'backend.log.1')
            os.chmod(STATE/'backend.log.1', 0o600)
        backend_log = os.fdopen(os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), 'a')
        os.chmod(log_path, 0o600)
        env = {**os.environ, 'NIVRA_AUTH_MODE': os.environ.get('NIVRA_AUTH_MODE', 'dev')}
        backend = subprocess.Popen([str(ROOT/'service'/'.venv'/'bin'/'python'), 'run_public.py'],
            cwd=ROOT/'service', stdin=subprocess.PIPE, stdout=backend_log, stderr=backend_log,
            text=True, env=env, start_new_session=True)
        children.append(backend)
        backend.stdin.write(json.dumps({'origin': ORIGIN, 'socketOrigin': upstream, 'secret': secret})+'\n')
        backend.stdin.close()
        from urllib.request import urlopen
        for _ in range(50):
            if backend.poll() is not None: raise RuntimeError('The relay backend exited during startup.')
            try:
                with urlopen('http://127.0.0.1:8765/api/v1/health', timeout=1): break
            except Exception: time.sleep(.2)
        else: raise RuntimeError('The relay did not become ready before its startup deadline.')
        if provider == 'vercel': vercel_environment.publish(upstream, secret, site['id'])
        else: publish_environment(site, upstream, secret)
        write_private(STATE/'runtime.json', json.dumps({
            'origin': ORIGIN, 'upstream': upstream, 'siteId': site['id'], 'provider': provider, 'startedAt': time.time(),
            'hostPid': os.getpid(), 'backendPid': backend.pid, 'tunnelPid': tunnel.pid
        }, indent=2)+'\n')
        deploy_on_start = os.environ.get('NIVRA_SKIP_FRONTEND_DEPLOY') != '1'
        deploy_pending = deploy_on_start
        if deploy_on_start:
            build_env = {**os.environ, 'VITE_NIVRA_DIRECT_SOCKET_RELAY': '1', 'VERCEL_CLI_USE_NATIVE_BINARY': '0'}
            for attempt in range(3):
                try:
                    command(children, ['npm', 'run', 'build'], timeout=300, env=build_env)
                    for arguments in frontend_commands(provider, site):
                        command(children, arguments, timeout=300, env=build_env)
                    deploy_pending = False
                    break
                except RuntimeError:
                    print(json.dumps({'frontendDeployPending': True, 'attempt': attempt+1,
                        'relayReady': True, 'hostPid': os.getpid()}), flush=True)
                    if attempt < 2: time.sleep(5)
        else: deploy_pending = True
        # A hosting API outage must not restart the healthy relay and invalidate
        # paired phones. Keep its tunnel stable for a manual frontend retry.
        print(json.dumps({'published': None if deploy_pending else ORIGIN,
            'relayReady': True, 'hostPid': os.getpid(), 'frontendDeployPending': deploy_pending}), flush=True)
        monitor = TunnelDNSMonitor(upstream)
        while tunnel.poll() is None and backend.poll() is None:
            monitor.check(time.monotonic())
            time.sleep(2)
        raise RuntimeError('The public relay stopped.')
    finally:
        for child in reversed(children): terminate(child)
        if backend_log: backend_log.close()
        runtime = STATE/'runtime.json'
        try:
            if json.loads(runtime.read_text()).get('hostPid') == os.getpid(): runtime.unlink()
        except (OSError, ValueError): pass
        if lock: lock.close()


def supervise():
    private_state()
    install_signal_handlers()
    budget = RetryBudget()
    child = awake = None
    try:
        while True:
            status('starting', failures=len(budget.failures))
            child = subprocess.Popen([sys.executable, str(Path(__file__).resolve())],
                                     cwd=ROOT, start_new_session=True)
            # The assertion belongs to this host PID and vanishes even on a crash.
            awake = subprocess.Popen(['/usr/bin/caffeinate', '-i', '-w', str(child.pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            status('running', hostPid=child.pid, failures=len(budget.failures))
            code = child.wait()
            terminate(awake)
            awake = None
            if not budget.failed(time.monotonic()):
                status('failed', exitCode=code, failures=len(budget.failures))
                print('NIVRA host stopped after three failures within fifteen minutes.', flush=True)
                return 1
            delay = (5, 20)[min(len(budget.failures)-1, 1)]
            status('retrying', exitCode=code, failures=len(budget.failures), retryInSeconds=delay)
            time.sleep(delay)
    except StopRequested:
        return 0
    finally:
        terminate(child, timeout=25)
        terminate(awake)
        if not budget.failures or len(budget.failures) < budget.limit:
            status('stopped', failures=len(budget.failures))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--supervise', action='store_true', help='Run with bounded recovery and a host-scoped sleep assertion.')
    arguments = parser.parse_args()
    try:
        if arguments.supervise: sys.exit(supervise())
        run()
    except StopRequested:
        sys.exit(0)
    except Exception as error:
        # A remote API exception can carry credential-bearing headers or bodies.
        # Log only its class, never the exception text or child output.
        print('NIVRA public host failed ('+type(error).__name__+').', file=sys.stderr, flush=True)
        sys.exit(1)
