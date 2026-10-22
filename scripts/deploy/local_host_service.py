#!/usr/bin/env python3
"""Run the prepared offline camera host independently of the terminal."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import subprocess
import time
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[2]
LABEL = 'work.tanishq.nivra.local-host'
DOMAIN = f'gui/{os.getuid()}'
TARGET = f'{DOMAIN}/{LABEL}'
PLIST = Path.home() / 'Library/LaunchAgents' / f'{LABEL}.plist'
LOG = Path.home() / 'Library/Logs/NIVRA/local-host.log'
OPENER = build_opener(ProxyHandler({}))


def health():
    try:
        with OPENER.open('http://127.0.0.1:8870/api/v1/health', timeout=1) as response:
            value = json.load(response)
        if not isinstance(value, dict) or value.get('backend') != 'local-ai':
            return None
        with OPENER.open('http://127.0.0.1:8870/api/local/config', timeout=1) as response:
            config = json.load(response)
        return value if isinstance(config, dict) and config.get('enabled') is True and config.get('transport') == 'wireless' else None
    except (OSError, ValueError):
        return None


def loaded():
    return subprocess.run(['/bin/launchctl', 'print', TARGET], capture_output=True).returncode == 0


def install():
    python = ROOT / 'service/.venv/bin/python'
    if not python.is_file() or not (ROOT / 'dist-usb/index.html').is_file():
        raise SystemExit('Finish the local installation and run npm run build:local first.')
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.parent.chmod(0o700)
    LOG.touch(mode=0o600, exist_ok=True)
    LOG.chmod(0o600)
    # Documents is a protected launchd working directory on macOS. Use the home
    # directory, absolute project paths, and private logs outside Documents.
    value = {
        'Label': LABEL,
        'ProgramArguments': ['/usr/bin/caffeinate', '-i', str(python), str(ROOT / 'service/run_local.py')],
        'WorkingDirectory': str(Path.home()),
        'EnvironmentVariables': {'PYTHONUNBUFFERED': '1', 'PYTORCH_ENABLE_MPS_FALLBACK': '1',
            'NIVRA_CONNECTION': 'wireless', 'NIVRA_AUTO_RELAY': '0'},
        'RunAtLoad': True,
        'KeepAlive': {'SuccessfulExit': False},
        'ThrottleInterval': 15,
        'StandardOutPath': str(LOG),
        'StandardErrorPath': str(LOG),
        'Umask': 0o077,
    }
    temporary = PLIST.with_suffix('.tmp')
    temporary.write_bytes(plistlib.dumps(value))
    temporary.chmod(0o600)
    temporary.replace(PLIST)


def start():
    if not PLIST.is_file():
        install()
    if not loaded():
        if health():
            return
        subprocess.run(['/bin/launchctl', 'bootstrap', DOMAIN, str(PLIST)], check=True)
    elif not health():
        subprocess.run(['/bin/launchctl', 'kickstart', '-k', TARGET], check=True)
    # Model loading continues after the HTTP listener opens. The browser shows
    # its progress, so launching cameras does not wait for model warm-up.
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if health():
            return
        time.sleep(.25)
    raise SystemExit(f'NIVRA could not start. See {LOG}')


def restart():
    if loaded():
        subprocess.run(['/bin/launchctl', 'bootout', TARGET], check=True)
        # bootout can return while launchd still reports the job as removing.
        deadline = time.monotonic() + 5
        while loaded():
            if time.monotonic() >= deadline:
                raise SystemExit('NIVRA is still stopping. Try again in a moment.')
            time.sleep(.1)
    start()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'start', 'restart', 'status'])
    action = parser.parse_args().action
    if action == 'install':
        install()
    elif action == 'restart':
        restart()
    elif action == 'start':
        start()
    else:
        current = health()
        print(json.dumps({'loaded': loaded(), 'reachable': current is not None,
            'analysis': current.get('status') if current else None,
            'url': 'http://127.0.0.1:8870/local'}))


if __name__ == '__main__':
    main()
