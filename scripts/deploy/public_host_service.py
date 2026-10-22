"""Install and control the current user's NIVRA LaunchAgent. No sudo or login tokens."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT/'service'/'state'/'public'
LABEL = 'work.tanishq.nivra.public-host'
PLIST = Path.home()/'Library'/'LaunchAgents'/(LABEL+'.plist')
DOMAIN = 'gui/'+str(os.getuid())
TARGET = DOMAIN+'/'+LABEL


def agent_log(home=None):
    return (Path.home() if home is None else Path(home))/'Library/Logs/NIVRA/public-host.log'


def agent_definition(root=ROOT, state=STATE, home=None, node=None):
    home = Path.home() if home is None else Path(home)
    node = shutil.which('node') if node is None else node
    if not node: raise RuntimeError('Install Node before installing the NIVRA agent.')
    node_dir = str(Path(node).resolve().parent)
    environment = {'PATH': node_dir+':/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
                   'HOME': str(home), 'PYTHONUNBUFFERED': '1'}
    # Only explicit non-secret deployment settings survive installation.
    scope = os.environ.get('NIVRA_VERCEL_SCOPE')
    if scope is not None:
        from vercel_environment import cli_scope
        environment['NIVRA_VERCEL_SCOPE'] = cli_scope({'orgId': ''})
    project_id = os.environ.get('NIVRA_VERCEL_PROJECT_ID')
    linked = root/'.vercel/project.json'
    if linked.exists():
        from vercel_environment import linked_project
        project_id = linked_project(root, project_id or json.loads(linked.read_text()).get('projectId'))['projectId']
    if project_id:
        if not re.fullmatch(r'prj_[A-Za-z0-9_]+', project_id):
            raise RuntimeError('The Vercel project ID is invalid.')
        environment['NIVRA_VERCEL_PROJECT_ID'] = project_id
    provider = os.environ.get('NIVRA_DEPLOY_PROVIDER')
    if provider is not None:
        if provider not in ('vercel', 'netlify'): raise RuntimeError('The deployment provider is invalid.')
        environment['NIVRA_DEPLOY_PROVIDER'] = provider
    return {
        'Label': LABEL,
        'ProgramArguments': [str(root/'service'/'.venv'/'bin'/'python'),
                             str(root/'scripts'/'deploy'/'public_host.py'), '--supervise'],
        'WorkingDirectory': str(home),
        'EnvironmentVariables': environment,
        'RunAtLoad': True,
        'KeepAlive': False,
        'ThrottleInterval': 60,
        'ExitTimeOut': 40,
        'ProcessType': 'Background',
        'StandardOutPath': str(agent_log(home)),
        'StandardErrorPath': str(agent_log(home)),
    }


def install():
    for path in (ROOT/'service'/'.venv'/'bin'/'python', Path('/opt/homebrew/bin/cloudflared')):
        if not path.is_file(): raise RuntimeError('A required local runtime is missing.')
    if not shutil.which('npm') or not shutil.which('npx'):
        raise RuntimeError('Node, npm and npx must be on PATH during installation.')
    STATE.mkdir(parents=True, exist_ok=True)
    os.chmod(STATE, 0o700)
    log = agent_log()
    log.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(log.parent, 0o700)
    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.close(fd)
    os.chmod(log, 0o600)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    temporary = PLIST.with_suffix('.plist.tmp')
    with temporary.open('wb') as stream: plistlib.dump(agent_definition(), stream)
    os.chmod(temporary, 0o600)
    os.replace(temporary, PLIST)
    print('Installed '+str(PLIST)+'. The current host was not stopped or started.')


def launchctl(*arguments, check=True):
    return subprocess.run(['/bin/launchctl', *arguments], capture_output=True, text=True, check=check)


def wait_for_listeners_to_stop(timeout=40):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        active = False
        for port in (8765, 8766):
            with socket.socket() as probe:
                probe.settimeout(.2)
                active |= probe.connect_ex(('127.0.0.1', port)) == 0
        if not active: return
        time.sleep(.25)
    raise RuntimeError('The previous relay did not release its listeners.')


def pid_alive(pid):
    if not isinstance(pid, int) or pid <= 1: return False
    try: os.kill(pid, 0)
    except ProcessLookupError: return False
    except PermissionError: return True
    return True


def service_status(state, loaded):
    def read(name):
        try:
            value = json.loads((state/name).read_text())
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError): return {}

    saved = read('service-status.json')
    values = {'loaded': loaded}
    values.update({key: saved[key] for key in ('state', 'updatedAt', 'supervisorPid', 'hostPid',
        'failures', 'retryInSeconds', 'exitCode') if key in saved})
    values['supervisorAlive'] = pid_alive(values.get('supervisorPid'))
    values['hostAlive'] = pid_alive(values.get('hostPid'))
    if values.get('state') == 'running':
        if not values['supervisorAlive']: values['state'] = 'stopped'
        elif not values['hostAlive']: values['state'] = 'starting-or-recovering'

    runtime = read('runtime.json')
    runtime_host_alive = pid_alive(runtime.get('hostPid'))
    values['mode'] = 'supervised' if values['supervisorAlive'] else 'stopped'
    if runtime_host_alive and (not values['supervisorAlive'] or runtime.get('hostPid') != saved.get('hostPid')):
        # A manually launched host can outlive an earlier failed supervisor.
        # Keep that stale supervisor record separate from the active host.
        previous = {key: values.pop(key) for key in ('state', 'updatedAt', 'supervisorPid',
            'supervisorAlive', 'failures', 'retryInSeconds', 'exitCode') if key in values}
        values['supervisor'] = previous
        values['mode'] = 'direct'
        values['hostPid'] = runtime['hostPid']
        values['hostAlive'] = True
    if runtime_host_alive and values.get('hostPid') == runtime.get('hostPid'):
        for key in ('backend', 'tunnel'):
            pid = runtime.get(key+'Pid')
            values[key+'Alive'] = pid_alive(pid)
            if isinstance(pid, int): values[key+'Pid'] = pid
        if values['mode'] == 'direct':
            values['state'] = 'processes-running' if values['backendAlive'] and values['tunnelAlive'] else 'degraded'
    # Never copy upstream URLs, credentials or arbitrary runtime fields to output.
    values['checkScope'] = 'process-liveness-only'
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'start', 'restart', 'stop', 'status', 'uninstall', 'detach'))
    action = parser.parse_args().action
    if sys.platform != 'darwin': raise RuntimeError('This helper requires macOS.')
    if action == 'install': install()
    elif action == 'detach':
        from public_host import ports_available, private_state
        ports_available()
        private_state()
        fd = os.open(STATE/'supervisor.log', os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.chmod(STATE/'supervisor.log', 0o600)
        with os.fdopen(fd, 'a') as log:
            child = subprocess.Popen([str(ROOT/'service/.venv/bin/python'),
                str(ROOT/'scripts/deploy/public_host.py'), '--supervise'], cwd=ROOT,
                stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        print('Detached NIVRA supervisor started with PID '+str(child.pid)+'.')
    elif action == 'start':
        if not PLIST.exists(): raise RuntimeError('Run install first.')
        launchctl('bootstrap', DOMAIN, str(PLIST))
        print('LaunchAgent loaded. Read status while the relay starts and redeploys.')
    elif action == 'restart':
        # kickstart -k uses SIGKILL and can strand the separate tunnel/backend
        # process groups. Unload gracefully before starting a new supervisor.
        launchctl('bootout', DOMAIN, str(PLIST))
        wait_for_listeners_to_stop()
        launchctl('bootstrap', DOMAIN, str(PLIST))
        print('NIVRA agent restart requested. Valid paired-phone sessions are preserved.')
    elif action in ('stop', 'uninstall'):
        result = launchctl('bootout', DOMAIN, str(PLIST), check=False)
        if result.returncode and launchctl('print', TARGET, check=False).returncode == 0:
            raise RuntimeError('The LaunchAgent did not stop.')
        if action == 'uninstall': PLIST.unlink(missing_ok=True)
        print('NIVRA agent stopped.' if action == 'stop' else 'NIVRA agent stopped and uninstalled.')
    elif action == 'status':
        loaded = launchctl('print', TARGET, check=False).returncode == 0
        print(json.dumps(service_status(STATE, loaded), indent=2))


if __name__ == '__main__':
    try: main()
    except Exception as error:
        # Do not print launchctl/API stderr or inherited environment content.
        print('NIVRA service command failed ('+type(error).__name__+').', file=sys.stderr)
        sys.exit(1)
